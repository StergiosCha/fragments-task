"""The gold pipeline: twins across variants, determinism, and the independent gold checker."""
import json
import os
import shutil

import pytest

import check_gold
import fragment as F
import gen

from conftest import REPO

SIZES = dict(n_parse=12, n_interp=12, n_infer=6)


@pytest.fixture(scope="module")
def fragment_files():
    files, _ = gen.build_fragment(0, use_ladr=False, **SIZES)
    return files


def rows(files, path):
    return [json.loads(l) for l in files[path].splitlines()]


def write_fragment(files, root):
    for p, s in files.items():
        gen.write(os.path.join(root, p), s)


# ---------------------------------------------------------------- twins

def test_all_variants_have_the_same_items(fragment_files):
    ids = {v: [(i["id"], i["type"]) for i in rows(fragment_files, f"{v}/items.jsonl")] for v in gen.VARIANTS}
    assert len(ids["nonce"]) > 20
    assert all(ids[v] == ids["nonce"] for v in gen.VARIANTS)


def test_twins_share_one_abstract_tree(fragment_files):
    specs = gen.variant_specs(0)
    back = {v: {new: old for old, new in sp["words"].items()} for v, sp in specs.items()}
    items = {v: rows(fragment_files, f"{v}/items.jsonl") for v in gen.VARIANTS}
    gold = rows(fragment_files, "nonce/gold/gold.jsonl")
    checked = 0
    for n, g in enumerate(gold):
        if g["type"] == "infer" or (g["type"] == "parse" and not g["grammatical"]):
            continue
        trees = set()
        for v, sp in specs.items():
            (t,) = F.parse(items[v][n]["sentence"].split(), sp["lex"], sp["order"])
            trees.add(F.rename_words(t, back[v]))
        assert len(trees) == 1, items["nonce"][n]
        checked += 1
    assert checked > 10


def test_counter_twin_has_the_same_words_as_nonce(fragment_files):
    assert fragment_files["counter/items.jsonl"] == fragment_files["nonce/items.jsonl"]
    assert fragment_files["counter/lexicon.txt"] == fragment_files["nonce/lexicon.txt"]
    assert fragment_files["counter/semantics.txt"] != fragment_files["nonce/semantics.txt"]


def test_variants_share_models(fragment_files):
    for name in ("models.json", "gold/models_hidden.json"):
        assert len({fragment_files[f"{v}/{name}"] for v in gen.VARIANTS}) == 1


def test_levels_are_the_same_in_every_variant(fragment_files):
    levels = {v: [g["level"] for g in rows(fragment_files, f"{v}/gold/gold.jsonl")] for v in gen.VARIANTS}
    assert all(levels[v] == levels["nonce"] for v in gen.VARIANTS)


def test_ungrammatical_twins_are_ungrammatical_everywhere(fragment_files):
    specs = gen.variant_specs(0)
    for v, sp in specs.items():
        items = rows(fragment_files, f"{v}/items.jsonl")
        for i, g in zip(items, rows(fragment_files, f"{v}/gold/gold.jsonl")):
            if g["type"] == "parse" and not g["grammatical"]:
                assert F.parse(i["sentence"].split(), sp["lex"], sp["order"]) == []


# ---------------------------------------------------------------- determinism

def test_same_seed_gives_byte_identical_output(fragment_files):
    again, _ = gen.build_fragment(0, use_ladr=False, **SIZES)
    assert again == fragment_files


def test_different_seeds_give_different_fragments(fragment_files):
    other, _ = gen.build_fragment(5, use_ladr=False, **SIZES)
    assert other["nonce/lexicon.txt"] != fragment_files["nonce/lexicon.txt"]


@pytest.mark.ladr
def test_with_ladr_same_seed_gives_byte_identical_output():
    a, _ = gen.build_fragment(3, use_ladr=True, **SIZES)
    b, _ = gen.build_fragment(3, use_ladr=True, **SIZES)
    assert a == b


# ---------------------------------------------------------------- the independent checker

def test_generated_gold_passes_the_checker(fragment_files, tmp_path):
    write_fragment(fragment_files, tmp_path)
    for v in gen.VARIANTS:
        assert check_gold.check_variant(tmp_path / v, use_ladr=False) == []


@pytest.mark.ladr
def test_generated_gold_with_ladr_passes_the_checker(tmp_path):
    files, counts = gen.build_fragment(0, use_ladr=True, **SIZES)
    assert counts["entailment"] and counts["contradiction"] and counts["neutral"]
    write_fragment(files, tmp_path)
    for v in gen.VARIANTS:
        assert check_gold.check_variant(tmp_path / v, use_ladr=True) == []


def corrupt(fragment_files, tmp_path, variant, change):
    """Write the fragment with one gold line changed by `change(gold_row) -> bool` (True when changed)."""
    write_fragment(fragment_files, tmp_path)
    path = tmp_path / variant / "gold" / "gold.jsonl"
    gold = [json.loads(l) for l in path.read_text().splitlines()]
    for g in gold:
        if change(g):
            break
    else:
        pytest.skip("no suitable item")
    path.write_text("".join(json.dumps(g) + "\n" for g in gold))
    return check_gold.check_variant(tmp_path / variant, use_ladr=False)


def test_checker_catches_a_wrong_entailment_label(fragment_files, tmp_path):
    def change(g):
        if g["type"] == "infer" and g["label"] == "neutral":
            g["label"] = "entailment"; return True
    problems = corrupt(fragment_files, tmp_path, "nonce", change)
    assert any("label entailment is refuted" in p for p in problems)


def test_checker_catches_a_wrong_truth_value(fragment_files, tmp_path):
    def change(g):
        if g["type"] == "interpret":
            g["truth"][0]["H1"] = not g["truth"][0]["H1"]; return True
    assert any("truth of" in p for p in corrupt(fragment_files, tmp_path, "counter", change))


def test_checker_catches_a_reading_with_the_wrong_meaning(fragment_files, tmp_path):
    """Gold computed with the nonce meanings on the counter variant must be caught."""
    write_fragment(fragment_files, tmp_path)
    shutil.copy(tmp_path / "nonce" / "gold" / "gold.jsonl", tmp_path / "counter" / "gold" / "gold.jsonl")
    problems = check_gold.check_variant(tmp_path / "counter", use_ladr=False)
    assert any("differ from the composition rules" in p for p in problems)


def test_checker_catches_a_wrong_grammaticality(fragment_files, tmp_path):
    def change(g):
        if g["type"] == "parse" and g["grammatical"]:
            g["grammatical"] = False; return True
    assert any("parses" in p for p in corrupt(fragment_files, tmp_path, "scrambled", change))


# ---------------------------------------------------------------- the committed practice fragment

@pytest.mark.xfail(strict=True, reason="practice_seed0/counter item 47 has a wrong label (u-z bug, audit §0.1); "
                                       "remove this marker when the practice fragment is regenerated")
def test_committed_practice_gold_passes_the_checker():
    for v in gen.VARIANTS:
        assert check_gold.check_variant(os.path.join(REPO, "fragments", "practice_seed0", v), use_ladr=False) == []
