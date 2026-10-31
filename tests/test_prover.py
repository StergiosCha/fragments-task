"""The Prover9/Mace4 wrappers. Tests marked `ladr` run the real programs (in CI, or locally once LADR is
installed); the others test the translation, the output parsing and the labelling logic without them."""
import random

import pytest

import fragment as F
import logic as L
import prover as P

parse = L.parse_formula

# The practice fragment's lexicon (seed 0): `wonbis` and `wutbu` start with w, a Prover9 variable letter.
LEX = F.make_lexicon(random.Random(0))
SIG = P.signature_of(LEX)


# ---------------------------------------------------------------- translation

def test_constants_starting_with_u_to_z_are_renamed():
    """Regression: Prover9 reads free names beginning with u-z as variables."""
    assert P.to_ladr(parse("wutbu(wonbis)")) == "p_wutbu(c_wonbis)"


def test_bound_variables_are_renamed_consistently():
    f = parse("! [X1] : (zispam(X1) => ? [X1] : gigup(X1,wonbis))")      # inner X1 shadows the outer one
    assert P.to_ladr(f) == "(all x1 (p_zispam(x1) -> (exists x2 p_gigup(x2,c_wonbis))))"


def test_negation_and_connectives():
    assert P.to_ladr(parse("~(mippos(mislup) | wutbu(wonbis))")) == "-((p_mippos(c_mislup) | p_wutbu(c_wonbis)))"


def test_input_file_layout():
    text = P._input([parse("wutbu(wonbis)")], [parse("wutbu(mislup)")], ["assign(max_given, 5)."])
    assert text == ("assign(max_given, 5).\nformulas(assumptions).\np_wutbu(c_wonbis).\nend_of_list.\n"
                    "formulas(goals).\np_wutbu(c_mislup).\nend_of_list.\n")


# ---------------------------------------------------------------- parsing LADR output

PROOF_OUTPUT = """
============================== prooftrans ============================
Prover9 (64) version 2009-11A, November 2009.
============================== PROOF =================================

% Proof 1 at 0.00 (+ 0.00) seconds.
% Length of proof is 3.
% Level of proof is 1.

2 p_wutbu(c_wonbis).  [assumption].
3 -p_wutbu(c_mislup).  [assumption].
5 $F.  [resolve(2,a,3,a)].

============================== end of proof ==========================
THEOREM PROVED
"""


def test_normalise_proof_drops_comment_lines_with_timings():
    assert P.normalise_proof(PROOF_OUTPUT) == (
        "2 p_wutbu(c_wonbis).  [assumption].\n3 -p_wutbu(c_mislup).  [assumption].\n5 $F.  [resolve(2,a,3,a)].")


MACE4_OUTPUT = """
Mace4 (64) version 2009-11A, November 2009.
============================== MODEL =================================

interpretation( 2, [number=1, seconds=0], [

        function(c_wonbis, [ 1 ]),

        function(f1(_), [ 0, 0 ]),

        relation(p_wutbu(_), [ 0, 1 ]),

        relation(p_gigup(_,_), [
			   0, 1,
			   0, 0 ])
]).

============================== end of model ==========================
"""


def test_parse_mace4_model():
    m = P.parse_mace4_model(MACE4_OUTPUT, SIG)
    assert m["D"] == ["a", "b"]
    assert m["consts"]["wonbis"] == "b"
    assert m["consts"]["mislup"] == "a"                    # not mentioned: fixed default
    assert m["preds"]["wutbu"] == {"b"}
    assert m["preds"]["gigup"] == {("a", "b")}             # row-major: index 1 = (0, 1)
    assert m["preds"]["dorom"] == set()                    # not mentioned: empty
    assert "f1" not in m["preds"] and "f1" not in m["consts"]   # Skolem functions are ignored


def test_parse_mace4_no_model():
    assert P.parse_mace4_model("Mace4 (64) version 2009-11A, November 2009.\nExiting with failure.\n", SIG) is None


def test_version_check(monkeypatch):
    monkeypatch.delenv("FRAGMENTS_ALLOW_ANY_LADR", raising=False)
    P._check_version("Prover9", "Prover9 (64) version 2009-11A, November 2009.")
    with pytest.raises(P.LadrError, match="required"):
        P._check_version("Prover9", "Prover9 (64) version 2017-01B, January 2017.")
    monkeypatch.setenv("FRAGMENTS_ALLOW_ANY_LADR", "1")
    P._check_version("Prover9", "Prover9 (64) version 2017-01B, January 2017.")


# ---------------------------------------------------------------- the labelling logic, with LADR stubbed

def _stub(monkeypatch, ent, con, m_true, m_false):
    """Replace prove/find_model by fixed answers: ent/con are statuses, m_true/m_false models or None."""
    def prove(assumptions, goal):
        return P.ProofResult(con if goal[0] == "not" else ent, "proof text")

    def find_model(formulas, signature):
        return m_false if formulas[-1][0] == "not" else m_true

    monkeypatch.setattr(P, "prove", prove)
    monkeypatch.setattr(P, "find_model", find_model)


SOME_MODEL = {"D": ["a"], "consts": {}, "preds": {}}
PREM, CONCL = [parse("wutbu(wonbis)")], parse("wutbu(mislup)")


@pytest.mark.parametrize("ent, con, m_true, m_false, label", [
    (P.PROVED, P.UNKNOWN, SOME_MODEL, None, "entailment"),
    (P.UNKNOWN, P.PROVED, None, SOME_MODEL, "contradiction"),
    (P.UNKNOWN, P.UNKNOWN, SOME_MODEL, SOME_MODEL, "neutral"),
    (P.PROVED, P.PROVED, None, None, "inconsistent"),
    (P.PROVED, P.UNKNOWN, None, None, None),        # premises not shown consistent: undecided
    (P.UNKNOWN, P.UNKNOWN, SOME_MODEL, None, None),
    (P.UNKNOWN, P.UNKNOWN, None, None, None),
])
def test_label_decision_table(monkeypatch, ent, con, m_true, m_false, label):
    _stub(monkeypatch, ent, con, m_true, m_false)
    assert P.label_terms(PREM, CONCL, LEX)[0] == label


@pytest.mark.parametrize("ent, con, m_true, m_false", [
    (P.PROVED, P.UNKNOWN, SOME_MODEL, SOME_MODEL),   # proof of conclusion, yet a model where it is false
    (P.UNKNOWN, P.PROVED, SOME_MODEL, SOME_MODEL),
])
def test_prover_and_model_finder_disagreeing_is_an_error(monkeypatch, ent, con, m_true, m_false):
    _stub(monkeypatch, ent, con, m_true, m_false)
    with pytest.raises(P.LadrError, match="Mace4 found a model"):
        P.label_terms(PREM, CONCL, LEX)


def test_missing_ladr_is_an_error_not_a_silent_no(monkeypatch):
    monkeypatch.setenv("PROVER9", "")
    monkeypatch.setattr(P.shutil, "which", lambda name: None)
    with pytest.raises(P.LadrError, match="not installed"):
        P.prove(PREM, CONCL)


# ---------------------------------------------------------------- the real programs

@pytest.mark.ladr
def test_real_entailment_and_its_proof():
    prem = [parse("! [X] : (zispam(X) => gigup(X,wonbis))"), parse("? [X] : (zispam(X) & mippos(X))")]
    concl = parse("? [X] : (zispam(X) & gigup(X,wonbis))")
    label, cert = P.label_terms(prem, concl, LEX)
    assert label == "entailment"
    assert "$F" in cert["proof"] and "seconds" not in cert["proof"]


@pytest.mark.ladr
def test_practice_counter_item_47_is_a_contradiction():
    """Regression for the u-z bug: the first practice release labelled this item `entailment`."""
    prem = [parse("~wutbu(mislup)"), parse("wutbu(wonbis)")]
    assert P.label_terms(prem, parse("wutbu(mislup)"), LEX)[0] == "contradiction"


@pytest.mark.ladr
def test_real_neutral_models_are_checked():
    prem = [parse("wutbu(wonbis)")]
    concl = parse("? [X] : (zukka(X) & gigup(X,wonbis))")
    label, cert = P.label_terms(prem, concl, LEX)
    assert label == "neutral"
    m_true, m_false = (L.model_from_json(m, SIG) for m in cert["models"])
    assert all(L.holds(p, m_true) and L.holds(p, m_false) for p in prem)
    assert L.holds(concl, m_true) and not L.holds(concl, m_false)


@pytest.mark.ladr
def test_real_inconsistent_premises():
    prem = [parse("wutbu(wonbis)"), parse("~wutbu(wonbis)")]
    assert P.label_terms(prem, parse("mippos(mislup)"), LEX)[0] == "inconsistent"


@pytest.mark.ladr
def test_real_prover_is_deterministic():
    prem = [parse("! [X] : (petfat(X) => wutbu(X))"), parse("petfat(wonbis)")]
    runs = {P.prove(prem, parse("wutbu(wonbis)")).proof for _ in range(3)}
    assert len(runs) == 1


@pytest.mark.ladr
def test_real_find_model_none_when_unsatisfiable():
    assert P.find_model([parse("wutbu(wonbis)"), parse("~wutbu(wonbis)")], SIG) is None


@pytest.mark.ladr
def test_real_not_proved_when_search_space_is_exhausted():
    assert P.prove([parse("wutbu(wonbis)")], parse("wutbu(mislup)")).status in (P.NOT_PROVED, P.UNKNOWN)
