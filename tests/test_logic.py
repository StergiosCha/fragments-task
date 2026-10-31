"""The formula language: printing, reading, and the model checker."""
import pytest

import logic as L

P = lambda name, *args: ("pred", name, tuple(args))
X, Y = ("var", "X"), ("var", "Y")
tam, ren = ("const", "tam"), ("const", "ren")


# ---------------------------------------------------------------- printing

def test_tptp_prints_fully_bracketed():
    f = ("forall", "X", ("imp", P("cat", X), ("exists", "Y", ("and", P("dog", Y), P("sees", X, Y)))))
    assert L.tptp(f) == "! [X] : (cat(X) => ? [Y] : (dog(Y) & sees(X,Y)))"


def test_tptp_negation_and_quantifier_units():
    assert L.tptp(("not", P("walks", tam))) == "~walks(tam)"
    assert L.tptp(("not", ("exists", "X", P("walks", X)))) == "~(? [X] : walks(X))"
    assert L.tptp(("forall", "X", ("not", P("walks", X)))) == "! [X] : (~walks(X))"


def test_canon_renames_bound_variables_only():
    a = ("forall", "X7", P("sees", ("var", "X7"), tam))
    b = ("forall", "Q", P("sees", ("var", "Q"), tam))
    assert L.canon(a) == L.canon(b) == ("forall", "V1", P("sees", ("var", "V1"), tam))


# ---------------------------------------------------------------- reading

@pytest.mark.parametrize("text", [
    "! [X] : (cat(X) => ? [Y] : (dog(Y) & sees(X,Y)))",
    "~walks(tam)",
    "~(? [X] : walks(X))",
    "((walks(tam) & sleeps(ren)) | walks(ren))",
])
def test_parse_inverts_tptp(text):
    assert L.tptp(L.parse_formula(text)) == text


def test_parse_precedence_and_binds_tighter_than_implication():
    f = L.parse_formula("! [X] : (p(X) => q(X) & r(X))")
    assert f == ("forall", "X", ("imp", P("p", X), ("and", P("q", X), P("r", X))))


def test_parse_precedence_or_between_and_and_implication():
    assert L.parse_formula("p(tam) | q(tam) & r(tam)") == ("or", P("p", tam), ("and", P("q", tam), P("r", tam)))
    assert L.parse_formula("p(tam) => q(tam) | r(tam)") == ("imp", P("p", tam), ("or", P("q", tam), P("r", tam)))


def test_parse_implication_is_right_associative():
    assert L.parse_formula("p(tam) => q(tam) => r(tam)") == ("imp", P("p", tam), ("imp", P("q", tam), P("r", tam)))


def test_parse_multi_variable_binder():
    assert L.parse_formula("! [X,Y] : sees(X,Y)") == ("forall", "X", ("forall", "Y", P("sees", X, Y)))


def test_parse_iff_is_two_implications():
    a, b = P("p", tam), P("q", tam)
    assert L.parse_formula("p(tam) <=> q(tam)") == ("and", ("imp", a, b), ("imp", b, a))


def test_parse_spec_notation():
    f = L.parse_formula(r"forall x (cat(x) -> exists y (dog(y) & sees(x,y)))")
    g = L.parse_formula("! [X] : (cat(X) => ? [Y] : (dog(Y) & sees(X,Y)))")
    assert L.canon(f) == L.canon(g)


def test_parse_lowercase_bound_name_is_a_variable_free_one_a_constant():
    f = L.parse_formula("forall x (sees(x, tam))")
    assert f == ("forall", "x", P("sees", ("var", "x"), tam))


@pytest.mark.parametrize("text, message", [
    ("sees(X, tam)", "not bound"),
    ("! [X] : cat(X) &", "ends early"),
    ("cat(tam))", "unexpected"),
    ("cat", "atoms need arguments"),
    ("", "empty"),
    ("cat(tam) $ dog(tam)", "unexpected character"),
])
def test_parse_errors_are_explained(text, message):
    with pytest.raises(L.FormulaSyntaxError, match=message):
        L.parse_formula(text)


# ---------------------------------------------------------------- models

M = {"D": ["a", "b", "c"], "consts": {"tam": "a", "ren": "c"},
     "preds": {"cat": {"a", "b"}, "dog": {"c"}, "walks": {"a"}, "sees": {("a", "c"), ("b", "c")}}}


@pytest.mark.parametrize("text, value", [
    ("! [X] : (cat(X) => ? [Y] : (dog(Y) & sees(X,Y)))", True),     # every cat sees some dog
    ("! [X] : (cat(X) => walks(X))", False),                          # b is a cat that does not walk
    ("? [X] : (cat(X) & walks(X))", True),
    ("~(? [X] : (dog(X) & walks(X)))", True),                          # no dog walks
    ("sees(tam,ren)", True),
    ("sees(ren,tam)", False),
    ("? [Y] : (dog(Y) & ! [X] : (cat(X) => sees(X,Y)))", True),       # inverse scope: one dog all cats see
    ("! [X] : (dog(X) => ? [Y] : sees(X,Y))", False),
])
def test_holds_known_answers(text, value):
    assert L.holds(L.parse_formula(text), M) is value


def test_model_json_round_trip():
    j = L.model_to_json(M)
    assert j["sees"] == [["a", "c"], ["b", "c"]]
    assert L.model_from_json(j) == M


SIG = {"consts": {"tam", "ren"}, "preds": {"cat": 1, "dog": 1, "walks": 1, "sees": 2}}


@pytest.mark.parametrize("change, message", [
    ({"D": []}, "non-empty"),
    ({"D": ["a", "a"]}, "twice"),
    ({"tam": "z"}, "not in D"),
    ({"cat": ["z"]}, "not in D"),
    ({"sees": [["a", "z"]]}, "not a pair of elements"),
    ({"sees": [["a", "b", "c"]]}, "expected an element or a pair"),
    ({"cat": ["a", ["a", "b"]]}, "mixes"),
    ({"tam": 3}, "expected an element name or a list"),
])
def test_model_validation_messages(change, message):
    j = {**L.model_to_json(M), **change}
    with pytest.raises(L.ModelError, match=message):
        L.model_from_json(j, SIG)


def test_model_signature_missing_and_extra_symbols():
    j = L.model_to_json(M)
    del j["dog"]
    with pytest.raises(L.ModelError, match="does not interpret dog"):
        L.model_from_json(j, SIG)
    with pytest.raises(L.ModelError, match="not in the lexicon: fish"):
        L.model_from_json({**L.model_to_json(M), "fish": []}, SIG)


def test_model_signature_arity():
    with pytest.raises(L.ModelError, match="arity"):
        L.model_from_json({**L.model_to_json(M), "walks": [["a", "b"]]}, SIG)
