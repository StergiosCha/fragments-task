"""Grammar, parser, semantic composition and phenomenon levels, with known answers."""
import itertools
import random

import pytest

import fragment as F
import logic as L

LEX = F.make_lexicon(random.Random(0))
# seed 0: PN wonbis, mislup | N petfat, zukka, zispam | IV mippos, wutbu | TV dorom, gigup
#         Det gesdam = every, zusdit = some, tamwup = no
EVERY, SOME, NO = "gesdam", "zusdit", "tamwup"


def np(det, n):
    return ("NP", 0, (("Det", det), ("N", n)))


def pn(name):
    return ("NP", 1, (("PN", name),))


def np_rc(det, n, rc):
    return ("NP", 2, (("Det", det), ("N", n), rc))


def vp_iv(iv):
    return ("VP", 0, (("IV", iv),))


def vp_tv(tv, obj):
    return ("VP", 1, (("TV", tv), obj))


def vp_not(vp):
    return ("VP", 2, ("not", vp))


def S(subj, vp):
    return ("S", 0, (subj, vp))


def readings(tree):
    return sorted(L.tptp(L.canon(r)) for r in F.readings(tree, LEX))


def canon_text(*texts):
    return sorted(L.tptp(L.canon(L.parse_formula(t))) for t in texts)


# ---------------------------------------------------------------- parser

def test_lexicon_of_seed_0():
    assert F.lexicon_txt(LEX) == ("PN: wonbis, mislup\nN: petfat, zukka, zispam\nIV: mippos, wutbu\n"
                                  "TV: dorom, gigup\nDet: gesdam, zusdit, tamwup\n")
    assert [LEX[d][1] for d in (EVERY, SOME, NO)] == ["every", "some", "no"]


def test_parse_svo_and_scrambled_give_the_same_tree():
    t = S(np_rc(EVERY, "zispam", ("RC", 1, ("that", pn("wonbis"), ("TV", "gigup")))), vp_iv("mippos"))
    svo = F.words_of(t, "svo")
    scr = F.words_of(t, "scrambled")
    assert svo == "gesdam zispam that wonbis gigup mippos".split()
    assert scr == "mippos gigup wonbis that zispam gesdam".split()
    assert F.parse(svo, LEX, "svo") == [t]
    assert F.parse(scr, LEX, "scrambled") == [t]
    assert F.parse(scr, LEX, "svo") == [] and F.parse(svo, LEX, "scrambled") == []


@pytest.mark.parametrize("sentence", [
    "gesdam zispam", "gesdam mippos", "wonbis gigup", "wonbis not", "that wonbis mippos", "wonbis mippos mippos",
])
def test_parse_rejects_non_sentences(sentence):
    assert F.parse(sentence.split(), LEX) == []


def all_trees(depth):
    """Every canonical tree up to a nesting depth, with one word per category (structure only)."""
    word = {"PN": "wonbis", "N": "zispam", "IV": "mippos", "TV": "gigup", "Det": EVERY}

    def gen(sym, d):
        if sym in F.FUNCTION_WORDS:
            return [sym]
        if sym in F.CATS:
            return [(sym, word[sym])]
        if d > depth:
            return []
        out = []
        for ri, rhs in enumerate(F.RULES[sym]):
            for kids in itertools.product(*[gen(s, d + 1) for s in rhs]):
                out.append((sym, ri, tuple(kids)))
        return out

    return gen("S", 0)


@pytest.mark.parametrize("order", ["svo", "scrambled"])
def test_every_small_sentence_has_exactly_one_parse(order):
    trees = all_trees(4)
    assert len(trees) > 100
    for t in trees:
        assert F.parse(F.words_of(t, order), LEX, order) == [t]


# ---------------------------------------------------------------- composition

def test_proper_name_and_intransitive():
    assert readings(S(pn("wonbis"), vp_iv("mippos"))) == ["mippos(wonbis)"]


def test_three_determiners():
    assert readings(S(np(EVERY, "zispam"), vp_iv("mippos"))) == canon_text("! [X] : (zispam(X) => mippos(X))")
    assert readings(S(np(SOME, "zispam"), vp_iv("mippos"))) == canon_text("? [X] : (zispam(X) & mippos(X))")
    assert readings(S(np(NO, "zispam"), vp_iv("mippos"))) == canon_text("~(? [X] : (zispam(X) & mippos(X)))")


def test_negation_of_the_vp():
    assert readings(S(np(EVERY, "zispam"), vp_not(vp_iv("mippos")))) == canon_text("! [X] : (zispam(X) => ~mippos(X))")


def test_transitive_with_proper_name_object():
    assert readings(S(np(EVERY, "zispam"), vp_tv("gigup", pn("wonbis")))) == \
        canon_text("! [X] : (zispam(X) => gigup(X,wonbis))")


def test_subject_relative_clause():
    t = S(np_rc(SOME, "zispam", ("RC", 0, ("that", vp_iv("mippos")))), vp_iv("wutbu"))
    assert readings(t) == canon_text("? [X] : ((zispam(X) & mippos(X)) & wutbu(X))")


def test_object_relative_clause_argument_order():
    """[RC that NP TV] = \\x. NP(\\y. TV(y,x)): in 'zispam that wonbis gigup', wonbis is the one who gigups."""
    t = S(np_rc(SOME, "zispam", ("RC", 1, ("that", pn("wonbis"), ("TV", "gigup")))), vp_iv("wutbu"))
    assert readings(t) == canon_text("? [X] : ((zispam(X) & gigup(wonbis,X)) & wutbu(X))")


def test_quantified_object_currently_gives_both_scopes():
    """Documents the current behaviour (audit B2/B3: the scope rule is an open question for organisers)."""
    t = S(np(EVERY, "zispam"), vp_tv("gigup", np(SOME, "zukka")))
    assert readings(t) == canon_text("! [X] : (zispam(X) => ? [Y] : (zukka(Y) & gigup(X,Y)))",
                                     "? [Y] : (zukka(Y) & ! [X] : (zispam(X) => gigup(X,Y)))")


def test_counter_lexicon_swaps_every_and_no_only():
    counter = F.make_lexicon(random.Random(0), counter_english=(EVERY, NO))
    assert (counter[EVERY][1], counter[SOME][1], counter[NO][1]) == ("no", "some", "every")
    t = S(np(EVERY, "zispam"), vp_iv("mippos"))
    assert sorted(L.tptp(L.canon(r)) for r in F.readings(t, counter)) == \
        canon_text("~(? [X] : (zispam(X) & mippos(X)))")
    assert "gesdam = \\P.\\Q. ~exists x (P(x) & Q(x))" in F.semantics_txt(counter)


# ---------------------------------------------------------------- levels

def test_levels_come_from_the_rules():
    assert F.level(S(np(EVERY, "zispam"), vp_iv("mippos"))) == 1
    assert F.level(S(np(EVERY, "zispam"), vp_not(vp_iv("mippos")))) == 2
    rc = ("RC", 0, ("that", vp_not(vp_iv("mippos"))))
    assert F.level(S(np_rc(EVERY, "zispam", rc), vp_iv("wutbu"))) == 3


def test_level_does_not_look_at_spelling():
    """Regression: a word containing 'not' used to put the sentence at level 2."""
    assert F.level(("S", 0, (("NP", 1, (("PN", "notkas"),)), ("VP", 0, (("IV", "nothing"),))))) == 1
