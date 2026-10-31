#!/usr/bin/env python3
"""Score a submission (docs/SUBMISSION.md) against the gold of a fragment.

  # a whole submission: a directory with nonce.jsonl, english.jsonl, scrambled.jsonl, counter.jsonl
  # (any subset) and optionally submission.json (track and system type)
  python3 score.py --fragment ../fragments/practice_seed0 --submission my_submission/ [--json results.json]

  # one variant
  python3 score.py --variant ../fragments/practice_seed0/nonce --submission my_nonce.jsonl

Metrics, as in the task page's scoring table; each is the share of items scored as correct:
  parse/grammaticality       the grammaticality judgement is right
  parse/derivation           the tree is one of the gold derivations (grammatical items only)
  interpret/truth-agreement  every submitted formula agrees with a gold reading on every model, released and withheld
  interpret/reading-set      the submitted readings and the gold readings are the same set (modulo equivalence)
  interpret/reading-recall   every gold reading is among the submitted ones
  infer/label                the label is right
  infer/certificate          the certificate is valid (reported separately from the label): the formulas agree with
                             the gold ones, and the proof is re-derived by Prover9 from them, or the two models
                             are models of the premises in which the conclusion differs
Every metric is reported per variant and per phenomenon level (1, 2, 3, all), and the nonce -> counter drop
(counter minus nonce, in points) is reported for each metric.

"Equivalent" means: the same truth value in every released and withheld model of the variant
(ModelEquivalence below). This is the current method; the audit (AUDIT.md §3.2) shows it accepts some
non-equivalent formulas, and a stronger check is an open question for the organisers.
"""
import argparse
import collections
import json
import os
import re
import sys

import logic as L
import prover as P
from validate import Variant, validate, validate_metadata

VARIANTS = ["nonce", "english", "scrambled", "counter"]
METRICS = ["parse/grammaticality", "parse/derivation", "interpret/truth-agreement", "interpret/reading-set",
           "interpret/reading-recall", "infer/label", "infer/certificate"]
LEVELS = ["1", "2", "3", "all"]


class ModelEquivalence:
    """Formulas are equivalent when they have the same truth value in every one of the given models."""

    def __init__(self, models):
        self.models = [models[k] for k in sorted(models)]

    def key(self, formula):
        return tuple(L.holds(formula, m) for m in self.models)

    def same(self, f, g):
        return self.key(f) == self.key(g)


def norm_tree(t):
    """Trees are compared up to whitespace only; structure and labels must match exactly."""
    return re.sub(r"\s+", " ", t).replace(" ]", "]").replace("[ ", "[").strip() if isinstance(t, str) else None


# ---------------------------------------------------------------- one item

def score_item(gold, ans, variant, equiv, use_ladr):
    """{metric: True/False/None} for one item; None means 'not applicable' or 'could not be checked'."""
    kind = gold["type"]
    if kind == "parse":
        grammatical = ans is not None and ans["grammatical"] == gold["grammatical"]
        out = {"parse/grammaticality": grammatical}
        if gold["grammatical"]:
            out["parse/derivation"] = (ans is not None and ans["grammatical"] is True
                                       and norm_tree(ans["tree"]) in {norm_tree(t) for t in gold["trees"]})
        return out
    if kind == "interpret":
        gkeys = {equiv.key(L.parse_formula(r)) for r in gold["readings"]}
        skeys = {equiv.key(L.parse_formula(lf)) for lf in ans["lfs"]} if ans else set()
        return {"interpret/truth-agreement": bool(skeys) and skeys <= gkeys,
                "interpret/reading-set": skeys == gkeys,
                "interpret/reading-recall": gkeys <= skeys}
    return {"infer/label": ans is not None and ans["label"] == gold["label"],
            "infer/certificate": False if ans is None else certificate_valid(ans, gold, variant, equiv, use_ladr)}


def certificate_valid(ans, gold, variant, equiv, use_ladr):
    """True/False, or None when a proof cannot be checked because LADR is not installed."""
    prem = [L.parse_formula(p) for p in ans["lfs"]["premises"]]
    concl = L.parse_formula(ans["lfs"]["conclusion"])
    gprem = [L.parse_formula(p) for p in gold["lfs"]["premises"]]
    gconcl = L.parse_formula(gold["lfs"]["conclusion"])
    if len(prem) != len(gprem) or not all(equiv.same(p, q) for p, q in zip(prem, gprem)) \
            or not equiv.same(concl, gconcl):
        return False
    cert = ans["certificate"]
    if ans["label"] == "neutral":
        m1, m2 = (L.model_from_json(m, variant.signature) for m in cert["models"])
        if not all(L.holds(p, m) for p in prem for m in (m1, m2)):
            return False
        return L.holds(concl, m1) != L.holds(concl, m2)       # either order: the conclusion differs
    if not use_ladr:
        return None
    goal = concl if ans["label"] == "entailment" else ("not", concl)
    return P.prove(prem, goal).status == P.PROVED


# ---------------------------------------------------------------- one variant, one submission

def score_variant(variant, lines, use_ladr):
    """(per-item results, validation report) for one variant's submission lines."""
    rep = validate(lines, variant)
    equiv = ModelEquivalence({**variant.released, **variant.hidden})
    results = []
    for i, g in sorted(variant.gold.items()):
        r = score_item(g, rep.answers.get(i), variant, equiv, use_ladr)
        results.append({"id": i, "type": g["type"], "level": g["level"], **r})
    return results, rep


def tally(results):
    """metric -> level -> {"correct", "n", "unchecked"}."""
    t = {m: {l: {"correct": 0, "n": 0, "unchecked": 0} for l in LEVELS} for m in METRICS}
    for r in results:
        for m in METRICS:
            if m not in r:
                continue
            for l in (str(r["level"]), "all"):
                cell = t[m][l]
                if r[m] is None:
                    cell["unchecked"] += 1
                else:
                    cell["n"] += 1
                    cell["correct"] += r[m]
    for m in METRICS:
        for cell in t[m].values():
            cell["score"] = round(100 * cell["correct"] / cell["n"], 2) if cell["n"] else None
    return t


def drops(tables):
    """For each metric and level: counter score minus nonce score, in points (None if either is missing)."""
    if "nonce" not in tables or "counter" not in tables:
        return {}
    out = {}
    for m in METRICS:
        out[m] = {}
        for l in LEVELS:
            a, b = tables["nonce"][m][l]["score"], tables["counter"][m][l]["score"]
            out[m][l] = None if a is None or b is None else round(b - a, 2)
    return out


# ---------------------------------------------------------------- printing

def fmt(x, signed=False):
    if x is None:
        return "       -"
    return f"{x:+7.1f} " if signed else f"{x:7.1f}%"


def print_table(title, table, signed=False):
    print(f"\n{title}")
    print(f"  {'metric':28s}" + "".join(f"{('level ' + l) if l != 'all' else 'all':>9s}" for l in LEVELS))
    for m in METRICS:
        cells = table[m]
        row = [cells[l] if signed else cells[l]["score"] for l in LEVELS]
        print(f"  {m:28s}" + "".join(f" {fmt(x, signed)}" for x in row))
    if not signed:
        unchecked = table["infer/certificate"]["all"]["unchecked"]
        if unchecked:
            print(f"  ({unchecked} proof certificate(s) not checked: Prover9 is not installed; "
                  "they are left out of infer/certificate)")


# ---------------------------------------------------------------- command line

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fragment", help="fragment directory containing nonce/, english/, scrambled/, counter/")
    ap.add_argument("--variant", help="score one variant directory instead of a whole fragment")
    ap.add_argument("--submission", required=True,
                    help="submission directory (with <variant>.jsonl files), or one .jsonl file with --variant")
    ap.add_argument("--json", help="also write the results as JSON to this file")
    ap.add_argument("--details", help="also write per-item results (JSON lines) to this file")
    ap.add_argument("--without-ladr", action="store_true",
                    help="score without Prover9: proof certificates are reported as unchecked")
    a = ap.parse_args()
    use_ladr = P.ladr_available()
    if not use_ladr and not a.without_ladr:
        sys.exit("Prover9 not found (see docs/LADR.md); official scores need it. "
                 "Use --without-ladr to score everything except proof certificates.")
    if bool(a.fragment) == bool(a.variant):
        sys.exit("give either --fragment (with a submission directory) or --variant (with a submission file)")

    if a.variant:
        jobs = {os.path.basename(os.path.normpath(a.variant)): (a.variant, a.submission)}
        meta, meta_problems = {}, []
    else:
        if not os.path.isdir(a.submission):
            sys.exit("with --fragment, --submission must be a directory containing <variant>.jsonl files")
        jobs = {v: (os.path.join(a.fragment, v), os.path.join(a.submission, f"{v}.jsonl"))
                for v in VARIANTS if os.path.exists(os.path.join(a.submission, f"{v}.jsonl"))}
        if not jobs:
            sys.exit(f"no {', '.join(v + '.jsonl' for v in VARIANTS)} found in {a.submission}")
        meta, meta_problems = validate_metadata(os.path.join(a.submission, "submission.json"))

    tables, validation, details = {}, {}, []
    for v, (vdir, sub) in jobs.items():
        with open(sub) as f:
            results, rep = score_variant(Variant(vdir), f.read().splitlines(), use_ladr)
        tables[v] = tally(results)
        validation[v] = {"errors": [m for m in rep.lines() if m.startswith("error")],
                         "warnings": [m for m in rep.lines() if m.startswith("warning")]}
        details += [{"variant": v, **r} for r in results]

    for p in meta_problems:
        print(f"submission.json: {p}")
    for v, val in validation.items():
        for line in val["errors"] + val["warnings"]:
            print(f"{v}: {line}")
    for v, t in tables.items():
        print_table(f"variant {v}", t)
    d = drops(tables)
    if d:
        print_table("nonce -> counter drop (counter minus nonce, points)", d, signed=True)

    if a.json:
        with open(a.json, "w") as f:
            json.dump({"submission": meta, "scores": tables, "drop_nonce_to_counter": d,
                       "validation": validation, "ladr": use_ladr}, f, indent=1)
    if a.details:
        with open(a.details, "w") as f:
            f.writelines(json.dumps(r) + "\n" for r in details)


if __name__ == "__main__":
    main()
