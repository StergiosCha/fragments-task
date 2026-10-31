"""Validator and scorer: the format checks, every metric, certificates, and the nonce -> counter drop."""
import json
import os
import random
import subprocess
import sys

import pytest

import fragment as F
import gen
import logic as L
import score as S
from validate import Variant, validate, validate_metadata

from conftest import REPO

SIZES = dict(n_parse=12, n_interp=12, n_infer=6)


@pytest.fixture(scope="module")
def frag(tmp_path_factory):
    """A generated fragment (without LADR) written to disk; returns its directory."""
    root = tmp_path_factory.mktemp("frag")
    files, _ = gen.build_fragment(0, use_ladr=False, **SIZES)
    for p, s in files.items():
        gen.write(os.path.join(root, p), s)
    return root


def gold_lines(frag, v):
    return (frag / v / "gold" / "gold_as_submission.jsonl").read_text().splitlines()


def answers(frag, v):
    return [json.loads(l) for l in gold_lines(frag, v)]


def run(frag, v, rows):
    results, rep = S.score_variant(Variant(frag / v), [json.dumps(r) for r in rows], use_ladr=False)
    return S.tally(results), rep


def first(rows, kind, frag=None, v=None, **where):
    items = {i["id"]: i for i in map(json.loads, (frag / v / "items.jsonl").read_text().splitlines())} if frag else {}
    for r in rows:
        if items and items[r["id"]]["type"] != kind:
            continue
        if all(r.get(k) == val for k, val in where.items()):
            return r
    pytest.skip(f"no {kind} item {where}")


# ---------------------------------------------------------------- the specification as a system

def test_specification_scores_100_everywhere(frag):
    for v in gen.VARIANTS:
        t, rep = run(frag, v, answers(frag, v))
        assert rep.errors == [] and rep.warnings == []
        for m in S.METRICS:
            cell = t[m]["all"]
            assert cell["score"] in (100.0, None), (v, m, cell)
        assert t["infer/certificate"]["all"]["unchecked"] == 0     # this fixture has neutral items only


@pytest.mark.ladr
def test_specification_scores_100_with_ladr(tmp_path):
    files, _ = gen.build_fragment(0, use_ladr=True, **SIZES)
    for p, s in files.items():
        gen.write(os.path.join(tmp_path, p), s)
    for v in gen.VARIANTS:
        results, rep = S.score_variant(Variant(tmp_path / v), gold_lines(tmp_path, v), use_ladr=True)
        t = S.tally(results)
        assert all(t[m]["all"]["score"] == 100.0 for m in S.METRICS), (v, t)
        assert t["infer/certificate"]["all"]["unchecked"] == 0


def test_empty_submission_scores_zero_and_warns(frag):
    t, rep = run(frag, "nonce", [])
    assert all(t[m]["all"]["score"] in (0.0, None) for m in S.METRICS)
    assert "not answered" in rep.warnings[0][1]


# ---------------------------------------------------------------- deliberately wrong systems are penalised

def test_appearance_trusting_system_is_penalised_on_counter(frag):
    """Interpret counter items with the nonce meanings, as a system that ignores the swap would."""
    nonce_lex = F.make_lexicon(random.Random(0))
    items = {i["id"]: i for i in map(json.loads, (frag / "counter" / "items.jsonl").read_text().splitlines())}
    rows = answers(frag, "counter")
    swapped = 0
    for r in rows:
        it = items[r["id"]]
        if it["type"] == "interpret":
            (t,) = F.parse(it["sentence"].split(), nonce_lex)
            r["lfs"] = [F.tptp(x) for x in F.readings(t, nonce_lex)]
            swapped += any(w in ("gesdam", "tamwup") for w in it["sentence"].split())
    t, _ = run(frag, "counter", rows)
    assert swapped > 0
    assert t["interpret/reading-set"]["all"]["score"] < 100


def test_label_flipping_system_is_penalised(frag):
    rows = answers(frag, "nonce")
    for r in rows:
        if "label" in r:
            r["label"] = "entailment"
            r["certificate"] = {"proof": "trust me"}
    t, _ = run(frag, "nonce", rows)
    assert t["infer/label"]["all"]["score"] == 0.0          # the fixture's infer items are all neutral
    assert t["infer/certificate"]["all"]["unchecked"] > 0   # proofs cannot be checked without LADR


def test_negation_dropping_system_is_penalised(frag):
    rows = answers(frag, "nonce")
    changed = 0
    for r in rows:
        if "lfs" in r and isinstance(r["lfs"], list):
            new = [lf.replace("~", "") for lf in r["lfs"]]
            changed += new != r["lfs"]
            r["lfs"] = new
    t, _ = run(frag, "nonce", rows)
    assert changed and t["interpret/reading-set"]["all"]["score"] < 100


def test_grammaticality_and_tree_errors(frag):
    rows = answers(frag, "nonce")
    for r in rows:
        if "grammatical" in r and r["grammatical"]:
            r["tree"] = r["tree"].replace("[S ", "[S  ")         # whitespace only: still right
    t, _ = run(frag, "nonce", rows)
    assert t["parse/derivation"]["all"]["score"] == 100.0
    for r in rows:
        if "grammatical" in r:
            r["grammatical"] = not r["grammatical"]
            r["tree"] = "[S]"
    t, _ = run(frag, "nonce", rows)
    assert t["parse/grammaticality"]["all"]["score"] == 0.0 and t["parse/derivation"]["all"]["score"] == 0.0


# ---------------------------------------------------------------- interpret metrics

def interpret_item(frag, v, ambiguous):
    for g in map(json.loads, (frag / v / "gold" / "gold.jsonl").read_text().splitlines()):
        if g["type"] == "interpret" and (len(g["readings"]) > 1) == ambiguous:
            return g
    pytest.skip("no such interpret item")


def test_equivalent_but_different_formula_counts(frag):
    g = interpret_item(frag, "nonce", ambiguous=False)
    f = L.parse_formula(g["readings"][0])
    double_negated = L.tptp(("not", ("not", f)))
    rows = [{"id": g["id"], "lfs": [double_negated], "truth": [{"M1": True, "M2": True}]}]
    results, rep = S.score_variant(Variant(frag / "nonce"), [json.dumps(r) for r in rows], use_ladr=False)
    (r,) = [x for x in results if x["id"] == g["id"]]
    assert r["interpret/reading-set"] and r["interpret/truth-agreement"]


def test_partial_readings_of_an_ambiguous_item(frag):
    g = interpret_item(frag, "nonce", ambiguous=True)
    row = {"id": g["id"], "lfs": g["readings"][:1], "truth": [{"M1": True, "M2": True}]}
    results, _ = S.score_variant(Variant(frag / "nonce"), [json.dumps(row)], use_ladr=False)
    (r,) = [x for x in results if x["id"] == g["id"]]
    assert r["interpret/truth-agreement"] and not r["interpret/reading-set"] and not r["interpret/reading-recall"]


def test_unbracketed_formula_is_read_with_standard_precedence(frag):
    """`A & B => C` means `(A & B) => C`, as in logic textbooks (the old reader got this wrong)."""
    v = Variant(frag / "nonce")
    equiv = S.ModelEquivalence({**v.released, **v.hidden})
    loose = L.parse_formula("! [Q] : (zispam(Q) & mippos(Q) => wutbu(Q))")
    tight = L.parse_formula("! [Q] : ((zispam(Q) & mippos(Q)) => wutbu(Q))")
    assert loose == tight and equiv.same(loose, tight)


# ---------------------------------------------------------------- infer certificates

def neutral_answer(frag, v="nonce"):
    for r in answers(frag, v):
        if r.get("label") == "neutral":
            return r
    pytest.skip("no neutral item")


def cert_ok(frag, row, v="nonce"):
    results, rep = S.score_variant(Variant(frag / v), [json.dumps(row)], use_ladr=False)
    (r,) = [x for x in results if x["id"] == row["id"]]
    return r["infer/certificate"], rep


def test_neutral_certificate_in_either_order(frag):
    row = neutral_answer(frag)
    row["certificate"]["models"].reverse()
    assert cert_ok(frag, row)[0] is True


def test_neutral_certificate_with_the_same_model_twice_is_invalid(frag):
    row = neutral_answer(frag)
    row["certificate"]["models"] = [row["certificate"]["models"][0]] * 2
    assert cert_ok(frag, row)[0] is False


def test_neutral_certificate_with_an_incomplete_model_is_an_error_not_a_crash(frag):
    row = neutral_answer(frag)
    row["certificate"]["models"][0] = {"D": ["a"]}
    ok, rep = cert_ok(frag, row)
    assert ok is False and any("does not interpret" in w[1] for w in rep.warnings)


def test_certificate_needs_the_gold_formulas(frag):
    row = neutral_answer(frag)
    row["lfs"]["conclusion"] = "~(" + row["lfs"]["conclusion"] + ")"
    assert cert_ok(frag, row)[0] is False


def test_certificate_with_too_few_premises_is_an_error(frag):
    for row in answers(frag, "nonce"):
        if row.get("label") and len(row["lfs"]["premises"]) == 2:
            row["lfs"]["premises"] = row["lfs"]["premises"][:1]
            ok, rep = cert_ok(frag, row)
            assert ok is False and any("the item has 2 premise(s)" in w[1] for w in rep.warnings)
            return
    pytest.skip("no two-premise item")


# ---------------------------------------------------------------- validation messages

@pytest.mark.parametrize("line, message", [
    ('{"id": 1, "grammatical": tru', "not valid JSON"),
    ('[1, 2]', "one JSON object"),
    ('{"grammatical": true}', '"id" must be'),
    ('{"id": 9999, "grammatical": true}', "no item with id 9999"),
])
def test_line_level_errors(frag, line, message):
    rep = validate([line], Variant(frag / "nonce"))
    assert message in rep.errors[0][1] and rep.errors[0][0] == 1


def item_of_type(frag, kind):
    for i in map(json.loads, (frag / "nonce" / "items.jsonl").read_text().splitlines()):
        if i["type"] == kind:
            return i


@pytest.mark.parametrize("kind, answer, message", [
    ("parse", {"grammatical": "yes"}, '"grammatical": true or false'),
    ("parse", {"grammatical": True}, 'needs "tree"'),
    ("interpret", {"lfs": []}, "non-empty list"),
    ("interpret", {"lfs": ["walks(tam"]}, "lfs[0]"),
    ("interpret", {"lfs": ["blicket(X)"]}, "not bound"),
    ("interpret", {"lfs": ["blicket(wonbis)"]}, "not a predicate of the lexicon"),
    ("interpret", {"lfs": ["mippos(tam)"]}, "not a proper name"),
    ("interpret", {"lfs": ["mippos(wonbis,wonbis)"]}, "takes 1 argument"),
    ("infer", {"label": "yes"}, '"label" must be one of'),
])
def test_answer_level_errors(frag, kind, answer, message):
    item = item_of_type(frag, kind)
    rep = validate([json.dumps({"id": item["id"], **answer})], Variant(frag / "nonce"))
    assert rep.errors and message in rep.errors[0][1], rep.errors


def test_a_malformed_certificate_leaves_the_label_scorable(frag):
    """Label and certificate are reported separately: a bad certificate does not void a right label."""
    row = neutral_answer(frag)
    row["certificate"] = {"proof": "not a pair of models"}
    results, rep = S.score_variant(Variant(frag / "nonce"), [json.dumps(row)], use_ladr=False)
    (r,) = [x for x in results if x["id"] == row["id"]]
    assert r["infer/label"] is True and r["infer/certificate"] is False
    assert not rep.errors and any("certificate cannot be valid" in w[1] for w in rep.warnings)
    row["lfs"] = ["a"]
    results, rep = S.score_variant(Variant(frag / "nonce"), [json.dumps(row)], use_ladr=False)
    (r,) = [x for x in results if x["id"] == row["id"]]
    assert r["infer/label"] is True and r["infer/certificate"] is False


def test_duplicate_answers_keep_the_first(frag):
    item = item_of_type(frag, "parse")
    lines = [json.dumps({"id": item["id"], "grammatical": False}), json.dumps({"id": item["id"], "grammatical": True, "tree": "x"})]
    rep = validate(lines, Variant(frag / "nonce"))
    assert rep.answers[item["id"]]["grammatical"] is False
    assert "more than once" in rep.errors[0][1] and rep.errors[0][0] == 2


def test_malformed_truth_is_only_a_warning(frag):
    item = item_of_type(frag, "interpret")
    rep = validate([json.dumps({"id": item["id"], "lfs": ["mippos(wonbis)"]})], Variant(frag / "nonce"))
    assert not rep.errors and any('"truth"' in w[1] for w in rep.warnings)


def test_unknown_fields_are_warned_about(frag):
    item = item_of_type(frag, "parse")
    rep = validate([json.dumps({"id": item["id"], "grammatical": False, "confidence": 0.9})], Variant(frag / "nonce"))
    assert any("confidence" in w[1] for w in rep.warnings)


def test_metadata(tmp_path):
    p = tmp_path / "submission.json"
    assert "missing" in validate_metadata(str(p))[1][0]
    p.write_text(json.dumps({"team": "A", "system": "B", "track": "model-alone", "system_type": "prompted-model"}))
    assert validate_metadata(str(p))[1] == []
    p.write_text(json.dumps({"team": "A", "system": "B", "track": "tools", "system_type": "llm"}))
    problems = validate_metadata(str(p))[1]
    assert any('"track"' in x for x in problems) and any('"system_type"' in x for x in problems)


# ---------------------------------------------------------------- reporting

def test_drop_is_counter_minus_nonce():
    def table(score):
        return {m: {l: {"score": score} for l in S.LEVELS} for m in S.METRICS}
    d = S.drops({"nonce": table(90.0), "counter": table(60.0)})
    assert d["interpret/reading-set"]["all"] == -30.0
    assert S.drops({"nonce": table(90.0)}) == {}


def test_command_line_on_a_submission_directory(frag, tmp_path):
    sub = tmp_path / "sub"
    sub.mkdir()
    for v in gen.VARIANTS:
        (sub / f"{v}.jsonl").write_text("\n".join(gold_lines(frag, v)) + "\n")
    (sub / "submission.json").write_text(json.dumps(
        {"team": "organisers", "system": "specification", "track": "model-with-tools", "system_type": "program-synthesis"}))
    out = tmp_path / "results.json"
    r = subprocess.run([sys.executable, "score.py", "--fragment", str(frag), "--submission", str(sub),
                        "--json", str(out), "--without-ladr"], cwd=os.path.join(REPO, "generator"),
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "nonce -> counter drop" in r.stdout
    res = json.loads(out.read_text())
    assert res["submission"]["system"] == "specification"
    assert res["scores"]["counter"]["interpret/reading-set"]["all"]["score"] == 100.0
    assert res["drop_nonce_to_counter"]["infer/label"]["all"] == 0.0


def test_command_line_validator_exit_status(frag, tmp_path):
    bad = tmp_path / "bad.jsonl"
    bad.write_text('{"id": 1, "grammatical": tru\n')
    r = subprocess.run([sys.executable, "validate.py", "--variant", str(frag / "nonce"), "--submission", str(bad)],
                       cwd=os.path.join(REPO, "generator"), capture_output=True, text=True)
    assert r.returncode == 1 and "error line 1: not valid JSON" in r.stdout
