"""The sanity systems: the specification scores 100%, and each deliberately wrong system loses points where it is
wrong and nowhere else."""
import os

import pytest

import gen
import sanity

SIZES = dict(n_parse=12, n_interp=24, n_infer=6)


@pytest.fixture(scope="module")
def scores(tmp_path_factory):
    root = tmp_path_factory.mktemp("sanity")
    frag = root / "frag"
    files, _ = gen.build_fragment(0, use_ladr=False, **SIZES)
    for p, s in files.items():
        gen.write(os.path.join(frag, p), s)
    return {name: sanity.score_system(str(frag), sanity.write_system(name, str(frag), str(root / "subs")), use_ladr=False)
            for name in sanity.SYSTEMS}


def score(scores, system, variant, metric):
    return scores[system][0][variant][metric]["all"]["score"]


def test_specification_is_the_ceiling(scores):
    tables, drops = scores["specification"]
    for v in gen.VARIANTS:
        for m, cells in tables[v].items():
            assert cells["all"]["score"] in (100.0, None), (v, m)
    assert all(d["all"] in (0.0, None) for d in drops.values())


def test_appearance_fails_only_on_counter(scores):
    for v in ("nonce", "english", "scrambled"):
        assert score(scores, "appearance", v, "interpret/reading-set") == 100.0
    assert score(scores, "appearance", "counter", "interpret/reading-set") < 100.0
    assert scores["appearance"][1]["interpret/reading-set"]["all"] < 0           # a nonce -> counter drop
    assert score(scores, "appearance", "counter", "parse/derivation") == 100.0     # same words, same trees


def test_scope_blind_loses_only_on_ambiguous_items(scores):
    assert any(score(scores, "scope-blind", v, "interpret/reading-recall") < 100.0 for v in gen.VARIANTS)
    for v in gen.VARIANTS:
        assert score(scores, "scope-blind", v, "interpret/truth-agreement") == 100.0   # what it says is right
        level1 = scores["scope-blind"][0][v]["interpret/reading-set"]["1"]["score"]
        assert level1 in (100.0, None)                                             # no ambiguity below level 3


@pytest.mark.parametrize("system", ["negation-dropping", "argument-swapping"])
def test_formula_errors_cost_interpretation_and_certificates_not_parsing(scores, system):
    for v in gen.VARIANTS:
        assert score(scores, system, v, "parse/grammaticality") == 100.0
        assert score(scores, system, v, "infer/label") == 100.0
    assert all(score(scores, system, v, "interpret/reading-set") < 100.0 for v in gen.VARIANTS)


def test_random_and_majority_are_far_below_the_ceiling(scores):
    for system in ("random", "majority"):
        for v in gen.VARIANTS:
            assert score(scores, system, v, "parse/derivation") == 0.0
            assert score(scores, system, v, "interpret/reading-set") < 50.0
