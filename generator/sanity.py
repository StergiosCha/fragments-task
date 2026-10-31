#!/usr/bin/env python3
"""Sanity tables: reference systems that show the scorer measures what it should.

  python3 sanity.py --fragment ../fragments/practice_seed0 [--out sanity/] [--markdown sanity.md]

Systems (each is written as a submission directory under --out, then scored):
  specification     the gold itself; must score 100% on every metric (the ceiling in every results table)
  random            a random grammaticality, a tree that is never right, the logical form of another random interpret
                    item, a random label with an empty certificate
  majority          the most frequent grammaticality and label of the fragment's gold; no interpretations
  appearance        trusts how words look: answers every counter item as if the determiners kept their nonce
                    meanings (that is, with the nonce twin's gold); identical to the specification elsewhere
  scope-blind       gives only the first reading of every sentence
  negation-dropping deletes every negation from its logical forms
  argument-swapping swaps the two arguments of every two-place predicate in its logical forms
Each deliberately wrong system must lose points exactly where it is wrong: that is checked in tests/test_sanity.py.
"""
import argparse
import collections
import copy
import json
import os
import random
import sys

import logic as L
import prover as P
import score as S
from validate import Variant

VARIANTS = S.VARIANTS
SYSTEMS = ["specification", "random", "majority", "appearance", "scope-blind", "negation-dropping", "argument-swapping"]
SHOWN = ["parse/grammaticality", "parse/derivation", "interpret/reading-set", "infer/label", "infer/certificate"]


def gold_answers(fragment, v):
    with open(os.path.join(fragment, v, "gold", "gold_as_submission.jsonl")) as f:
        return [json.loads(l) for l in f]


def items(fragment, v):
    with open(os.path.join(fragment, v, "items.jsonl")) as f:
        return {i["id"]: i for i in map(json.loads, f)}


def map_formulas(row, fn):
    """The answer row with fn applied to every formula in it."""
    row = copy.deepcopy(row)
    if isinstance(row.get("lfs"), list):
        row["lfs"] = [L.tptp(fn(L.parse_formula(x))) for x in row["lfs"]]
    elif isinstance(row.get("lfs"), dict):
        row["lfs"]["premises"] = [L.tptp(fn(L.parse_formula(x))) for x in row["lfs"]["premises"]]
        row["lfs"]["conclusion"] = L.tptp(fn(L.parse_formula(row["lfs"]["conclusion"])))
    return row


def transform(t, node):
    """Apply `node` bottom-up to every sub-formula."""
    k = t[0]
    if k == "not":
        t = ("not", transform(t[1], node))
    elif k in ("and", "or", "imp"):
        t = (k, transform(t[1], node), transform(t[2], node))
    elif k in ("forall", "exists"):
        t = (k, t[1], transform(t[2], node))
    return node(t)


def drop_negation(t):
    return transform(t, lambda s: s[1] if s[0] == "not" else s)


def swap_arguments(t):
    return transform(t, lambda s: ("pred", s[1], s[2][::-1]) if s[0] == "pred" and len(s[2]) == 2 else s)


def system_answers(name, fragment, v, rng):
    gold = gold_answers(fragment, v)
    its = items(fragment, v)
    if name == "specification":
        return gold
    if name == "appearance":
        return gold_answers(fragment, "nonce") if v == "counter" else gold
    if name == "scope-blind":
        out = copy.deepcopy(gold)
        for r in out:
            if isinstance(r.get("lfs"), list):
                r["lfs"], r["truth"] = r["lfs"][:1], r["truth"][:1]
        return out
    if name == "negation-dropping":
        return [map_formulas(r, drop_negation) for r in gold]
    if name == "argument-swapping":
        return [map_formulas(r, swap_arguments) for r in gold]
    released = sorted(Variant(os.path.join(fragment, v), with_gold=False).released)
    interpret_lfs = [r["lfs"][0] for r in gold if its[r["id"]]["type"] == "interpret"]
    if name == "random":
        out = []
        for r in gold:
            kind = its[r["id"]]["type"]
            if kind == "parse":
                g = rng.random() < 0.5
                out.append({"id": r["id"], "grammatical": g, **({"tree": "[S]"} if g else {})})
            elif kind == "interpret":
                out.append({"id": r["id"], "lfs": [rng.choice(interpret_lfs)], "truth": [{m: rng.random() < 0.5 for m in released}]})
            else:
                out.append({"id": r["id"], "label": rng.choice(["entailment", "contradiction", "neutral"]),
                            "lfs": r["lfs"], "certificate": {"proof": "none"}})
        return out
    if name == "majority":
        g_parse = collections.Counter(r["grammatical"] for r in gold if its[r["id"]]["type"] == "parse").most_common(1)[0][0]
        labels = collections.Counter(r["label"] for r in gold if its[r["id"]]["type"] == "infer")
        label = sorted(labels.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
        out = []
        for r in gold:
            kind = its[r["id"]]["type"]
            if kind == "parse":
                out.append({"id": r["id"], "grammatical": g_parse, **({"tree": "[S]"} if g_parse else {})})
            elif kind == "infer":
                out.append({"id": r["id"], "label": label, "lfs": r["lfs"], "certificate": {"proof": "none"}})
        return out
    raise ValueError(name)


def write_system(name, fragment, out_dir, seed=0):
    d = os.path.join(out_dir, name)
    os.makedirs(d, exist_ok=True)
    rng = random.Random(f"{seed}-{name}")
    for v in VARIANTS:
        with open(os.path.join(d, f"{v}.jsonl"), "w") as f:
            f.writelines(json.dumps(r) + "\n" for r in system_answers(name, fragment, v, rng))
    with open(os.path.join(d, "submission.json"), "w") as f:
        json.dump({"team": "organisers", "system": f"sanity: {name}", "track": "model-with-tools",
                   "system_type": "program-synthesis"}, f)
    return d


def score_system(fragment, sub_dir, use_ladr):
    tables = {}
    for v in VARIANTS:
        with open(os.path.join(sub_dir, f"{v}.jsonl")) as f:
            results, _ = S.score_variant(Variant(os.path.join(fragment, v)), f.read().splitlines(), use_ladr)
        tables[v] = S.tally(results)
    return tables, S.drops(tables)


def markdown(rows):
    """rows: system -> (tables, drops). One table per variant, plus the drop."""
    short = {m: m.split("/")[1] for m in SHOWN}
    out = []
    for v in VARIANTS:
        out.append(f"\n**{v}** (all levels, % correct)\n")
        out.append("| system | " + " | ".join(short[m] for m in SHOWN) + " |")
        out.append("|---" * (len(SHOWN) + 1) + "|")
        for name, (tables, _) in rows.items():
            cells = [tables[v][m]["all"]["score"] for m in SHOWN]
            out.append(f"| {name} | " + " | ".join("–" if c is None else f"{c:.1f}" for c in cells) + " |")
    out.append("\n**nonce → counter drop** (points)\n")
    out.append("| system | " + " | ".join(short[m] for m in SHOWN) + " |")
    out.append("|---" * (len(SHOWN) + 1) + "|")
    for name, (_, d) in rows.items():
        cells = [d[m]["all"] for m in SHOWN]
        out.append(f"| {name} | " + " | ".join("–" if c is None else f"{c:+.1f}" for c in cells) + " |")
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fragment", required=True)
    ap.add_argument("--out", default="sanity")
    ap.add_argument("--markdown", help="write the tables to this file as well")
    ap.add_argument("--without-ladr", action="store_true", help="leave proof certificates unchecked")
    a = ap.parse_args()
    use_ladr = P.ladr_available()
    if not use_ladr and not a.without_ladr:
        sys.exit("Prover9 not found (see docs/LADR.md); use --without-ladr to leave proof certificates unchecked")
    rows = {name: score_system(a.fragment, write_system(name, a.fragment, a.out), use_ladr) for name in SYSTEMS}
    md = markdown(rows)
    print(md)
    if a.markdown:
        with open(a.markdown, "w") as f:
            f.write(md)


if __name__ == "__main__":
    main()
