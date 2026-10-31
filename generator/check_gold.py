#!/usr/bin/env python3
"""Independent check of a variant's gold, starting from the released specification files.

  python3 check_gold.py ../fragments/practice_seed0/nonce [more variant directories ...]

It rebuilds the lexicon and word order from lexicon.txt, semantics.txt and grammar.txt, rather than from
the generator's internals, and then checks every item:
  parse      the gold says grammatical exactly when the sentence parses, and lists exactly its derivations
  interpret  the gold readings are the readings of the parse, and the truth values are right on every model
  infer      the logical forms are those of the sentences; neutral certificates are valid models; and no
             entailment or contradiction label is refuted by a model. The search covers every model of the
             item's own symbols with up to 2 elements, plus random models with 3 and 4 elements. This can
             only *refute* a label, not prove it; with LADR installed, the label is also recomputed.
Prints one line per problem and exits with status 1 if there is any.
"""
import itertools
import json
import os
import random
import re
import sys

import fragment as F
import logic as L
import prover as P


class SpecError(ValueError):
    pass


def read_spec(variant_dir):
    """(lexicon, word order) reconstructed from the three text files of the specification."""
    def read(name):
        with open(os.path.join(variant_dir, name)) as f:
            return f.read()

    cats = {}
    for line in read("lexicon.txt").splitlines():
        if line.strip():
            cat, words = line.split(":", 1)
            for w in words.split(","):
                cats[w.strip()] = cat.strip()
    det_meaning = {text: name for name, text in F.DET_TEXT.items()}
    lex = {}
    for line in read("semantics.txt").splitlines():
        m = re.fullmatch(r"(\S+) = (.+)", line.strip())
        if not m or m.group(1) not in cats:
            continue
        w, rhs = m.groups()
        if cats[w] == "Det":
            if rhs not in det_meaning:
                raise SpecError(f"determiner {w}: meaning {rhs!r} is not one of every/some/no")
            lex[w] = ("Det", det_meaning[rhs])
        else:
            lex[w] = (cats[w], rhs)
    missing = sorted(set(cats) - set(lex))
    if missing:
        raise SpecError(f"no meaning in semantics.txt for {', '.join(missing)}")
    grammar = read("grammar.txt")
    orders = [o for o in F.ORDERS if F.grammar_txt(o) == grammar]
    if not orders:
        raise SpecError("grammar.txt matches no known word order")
    return lex, orders[0]


def load_models(path):
    with open(path) as f:
        return {name: L.model_from_json(m) for name, m in json.load(f).items()}


def _alpha(formula_text):
    return L.tptp(L.canon(L.parse_formula(formula_text)))


def all_small_models(formulas, size):
    """Every model of the formulas' own symbols with `size` elements."""
    consts, preds = set(), {}
    for f in formulas:
        c, p = L.symbols(f)
        consts |= c; preds.update(p)
    D = [chr(97 + i) for i in range(size)]
    consts, preds = sorted(consts), sorted(preds.items())
    tuples = {1: D, 2: list(itertools.product(D, D))}
    choices = [list(itertools.product(D, repeat=len(consts)))]
    for _, arity in preds:
        dom = tuples[arity]
        choices.append([frozenset(x for x, keep in zip(dom, bits) if keep)
                        for bits in itertools.product([0, 1], repeat=len(dom))])
    for combo in itertools.product(*choices):
        yield {"D": D, "consts": dict(zip(consts, combo[0])),
               "preds": {name: set(ext) for (name, _), ext in zip(preds, combo[1:])}}


def refuting_model(prem, concl, label, lex, samples=3000, seed=0):
    """A model showing the label is wrong, if one is found (see the module docstring)."""
    def refutes(m):
        if not all(L.holds(p, m) for p in prem):
            return False
        return (not L.holds(concl, m)) if label == "entailment" else L.holds(concl, m)

    for size in (1, 2):
        for m in all_small_models(prem + [concl], size):
            if refutes(m):
                return m
    rng = random.Random(seed)
    for _ in range(samples):
        m = F.random_model(rng, lex, rng.choice([3, 4]))
        if refutes(m):
            return m
    return None


def check_variant(variant_dir, use_ladr=None):
    """A list of problems (strings); empty if the gold checks out."""
    use_ladr = P.ladr_available() if use_ladr is None else use_ladr
    problems = []
    try:
        lex, order = read_spec(variant_dir)
    except SpecError as e:
        return [f"{variant_dir}: specification: {e}"]
    sig = P.signature_of(lex)
    models = {**load_models(os.path.join(variant_dir, "models.json")),
              **load_models(os.path.join(variant_dir, "gold", "models_hidden.json"))}
    for name, m in models.items():
        try:
            L.check_signature(m, sig)
        except L.ModelError as e:
            problems.append(f"model {name}: {e}")
    with open(os.path.join(variant_dir, "items.jsonl")) as f:
        items = {i["id"]: i for i in map(json.loads, f)}
    with open(os.path.join(variant_dir, "gold", "gold.jsonl")) as f:
        gold = {g["id"]: g for g in map(json.loads, f)}
    if set(items) != set(gold):
        problems.append(f"items and gold have different ids: {sorted(set(items) ^ set(gold))}")

    def first_reading(sentence):
        trees = F.parse(sentence.split(), lex, order)
        if not trees:
            raise ValueError(f"{sentence!r} does not parse")
        return F.readings(trees[0], lex)[0]

    for i, g in sorted(gold.items()):
        it = items.get(i)
        if it is None:
            continue
        say = lambda msg: problems.append(f"item {i} ({g['type']}): {msg}")
        if it["type"] != g["type"]:
            say(f"type {it['type']} in items but {g['type']} in gold")
            continue
        try:
            if g["type"] == "parse":
                trees = F.parse(it["sentence"].split(), lex, order)
                if g["grammatical"] != bool(trees):
                    say(f"gold grammatical={g['grammatical']}, but the sentence {'parses' if trees else 'does not parse'}")
                elif trees and sorted(g["trees"]) != sorted(F.tree_str(t) for t in trees):
                    say("gold trees differ from the parser's derivations")
            elif g["type"] == "interpret":
                trees = F.parse(it["sentence"].split(), lex, order)
                if len(trees) != 1:
                    say(f"sentence has {len(trees)} parses")
                    continue
                mine = sorted(L.tptp(L.canon(r)) for r in F.readings(trees[0], lex))
                if sorted(_alpha(r) for r in g["readings"]) != mine:
                    say(f"gold readings {g['readings']} differ from the composition rules' {mine}")
                for r, row in zip(g["readings"], g["truth"]):
                    f = L.parse_formula(r)
                    for name, value in row.items():
                        if L.holds(f, models[name]) != value:
                            say(f"truth of {r} in {name} is {not value}, gold says {value}")
            else:
                prem = [first_reading(s) for s in it["premises"]]
                concl = first_reading(it["conclusion"])
                if [_alpha(p) for p in g["lfs"]["premises"]] != [L.tptp(L.canon(p)) for p in prem] or \
                        _alpha(g["lfs"]["conclusion"]) != L.tptp(L.canon(concl)):
                    say("gold logical forms differ from the sentences' readings")
                label = g["label"]
                if label == "neutral":
                    m_true, m_false = (L.model_from_json(m, sig) for m in g["certificate"]["models"])
                    if not (all(L.holds(p, m_true) and L.holds(p, m_false) for p in prem)
                            and L.holds(concl, m_true) and not L.holds(concl, m_false)):
                        say("neutral certificate is not a pair of premise models that differ on the conclusion")
                elif label in ("entailment", "contradiction"):
                    m = refuting_model(prem, concl, label, lex, seed=i)
                    if m is not None:
                        say(f"label {label} is refuted by the model {json.dumps(L.model_to_json(m))}")
                else:
                    say(f"unknown label {label!r}")
                if use_ladr:
                    lab, _ = P.label_terms(prem, concl, lex)
                    if lab != label:
                        say(f"Prover9/Mace4 give {lab}, gold says {label}")
        except (ValueError, KeyError, L.ModelError) as e:
            say(f"could not be checked: {e}")
    return problems


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    bad = 0
    for d in sys.argv[1:]:
        problems = check_variant(d)
        for p in problems:
            print(f"{d}: {p}")
        print(f"{d}: {'OK' if not problems else f'{len(problems)} problem(s)'}")
        bad += bool(problems)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
