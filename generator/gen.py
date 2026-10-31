#!/usr/bin/env python3
"""Generate a fragment package, its items and their gold for one seed.

  python3 gen.py --seed 1 --out out/seed1 [--n-parse 40 --n-interp 40 --n-infer 30]

Every item is built once, as an abstract (canonical) tree, and then realised in each of the four variants:
  nonce      invented words, the grammar's canonical word order
  english    the same trees with English words
  scrambled  the same trees and words in the scrambled word order
  counter    the same words and trees, but the determiners meaning `every` and `no` swap meanings
So item n is the same abstract item in every variant (the twins), and all variants share the same models.
Gold is computed separately for each variant from that variant's own lexicon and grammar.

Writes, per variant:
  <out>/<variant>/{lexicon.txt,grammar.txt,semantics.txt,models.json,items.jsonl}
  <out>/<variant>/gold/{gold.jsonl,models_hidden.json,gold_as_submission.jsonl}
"""
import argparse
import json
import os
import random
import sys

import fragment as F
import prover as P

VARIANTS = ["nonce", "english", "scrambled", "counter"]


# ---------------------------------------------------------------- the four variants of one fragment

def variant_specs(seed):
    """For each variant: its lexicon, its word order, and the map from nonce words to its words."""
    base = F.make_lexicon(random.Random(seed))
    dets = [w for w, (c, _) in base.items() if c == "Det"]           # meanings: every, some, no
    identity = {w: w for w in base}
    english = F.english_word_map(base)
    return {
        "nonce": {"lex": base, "order": "svo", "words": identity},
        "english": {"lex": F.english_lexicon(base), "order": "svo", "words": english},
        "scrambled": {"lex": base, "order": "scrambled", "words": identity},
        "counter": {"lex": F.make_lexicon(random.Random(seed), counter_english=(dets[0], dets[2])),
                    "order": "svo", "words": identity},
    }


def realise(tree, spec):
    """(tree, surface words) of a canonical nonce tree in one variant."""
    t = F.rename_words(tree, spec["words"])
    return t, F.words_of(t, spec["order"])


# ---------------------------------------------------------------- building items

def perturbation(rng, lex):
    """A recipe for a one-word change that should leave the fragment: (operation, relative position, word).
    The same recipe is applied to each variant's surface string, so the ungrammatical twins correspond."""
    return rng.choice(["swap", "drop", "insert"]), rng.random(), rng.choice(list(lex))


def apply_perturbation(words, recipe, word_map):
    op, frac, word = recipe
    ws = list(words)
    if op == "swap" and len(ws) > 1:
        i = min(int(frac * (len(ws) - 1)), len(ws) - 2)
        ws[i], ws[i + 1] = ws[i + 1], ws[i]
    elif op == "drop" and len(ws) > 1:
        del ws[min(int(frac * len(ws)), len(ws) - 1)]
    else:
        ws.insert(min(int(frac * (len(ws) + 1)), len(ws)), word_map[word])
    return ws


def related(rng, tree, lex):
    """A conclusion built from the premise tree by one edit: change the subject determiner, negate or
    un-negate the VP, drop the subject's relative clause, or replace the subject by a proper name."""
    _, _, (np, vp) = tree
    op = rng.choice(["det", "neg", "rc", "subj"])
    dets = [w for w, (c, _) in lex.items() if c == "Det"]
    if op == "det" and np[1] in (0, 2):
        np = (np[0], np[1], (("Det", rng.choice(dets)),) + np[2][1:])
    elif op == "neg":
        vp = vp[2][1] if vp[1] == 2 else ("VP", 2, ("not", vp))
    elif op == "rc" and np[1] == 2:
        np = ("NP", 0, np[2][:2])
    elif op == "subj":
        pns = [w for w, (c, _) in lex.items() if c == "PN"]
        np = ("NP", 1, (("PN", rng.choice(pns)),))
    return ("S", 0, (np, vp))


class Labeller:
    """Inference labels, computed once per distinct problem (english and scrambled share nonce's formulas)."""

    def __init__(self, use_ladr):
        self.use_ladr, self.cache = use_ladr, {}

    def __call__(self, prem_terms, concl_term, lex, sample_seed):
        key = tuple(F.tptp(t) for t in prem_terms) + (F.tptp(concl_term),)
        if key not in self.cache:
            if self.use_ladr:
                self.cache[key] = P.label_terms(prem_terms, concl_term, lex)
            else:
                self.cache[key] = P.label_terms_by_sampling(prem_terms, concl_term, lex, random.Random(sample_seed))
        return self.cache[key]


def truth_table(rs, models, n_released):
    return [{(f"M{j+1}" if j < n_released else f"H{j+1-n_released}"): F.holds(r, m) for j, m in enumerate(models)}
            for r in rs]


def build_fragment(seed, n_parse, n_interp, n_infer, n_models=2, n_hidden=3, use_ladr=True):
    specs = variant_specs(seed)
    base = specs["nonce"]["lex"]
    model_rng = random.Random(f"{seed}-models")
    models = [F.random_model(model_rng, base, model_rng.choice([2, 3])) for _ in range(n_models + n_hidden)]
    released, hidden = models[:n_models], models[n_models:]
    rng = random.Random(f"{seed}-items")
    label = Labeller(use_ladr)

    items = {v: [] for v in VARIANTS}
    gold = {v: [] for v in VARIANTS}
    nid = 0

    def emit(kind, per_variant):
        """per_variant: variant -> (item fields, gold fields)."""
        nonlocal nid
        nid += 1
        for v in VARIANTS:
            item, g = per_variant[v]
            items[v].append({"id": nid, "type": kind, **item})
            gold[v].append({"id": nid, "type": kind, **g})

    # parse items: half grammatical, half a one-word perturbation that is ungrammatical in every variant
    for i in range(n_parse):
        tree, _ = F.generate(rng, base)
        lvl = F.level(tree)
        if i % 2 == 0:
            out = {}
            for v, sp in specs.items():
                t, ws = realise(tree, sp)
                trees = F.parse(ws, sp["lex"], sp["order"])
                out[v] = ({"sentence": " ".join(ws)},
                          {"grammatical": True, "trees": [F.tree_str(x) for x in trees], "level": lvl})
            emit("parse", out)
        else:
            for _ in range(10):
                recipe = perturbation(rng, base)
                bad = {v: apply_perturbation(realise(tree, sp)[1], recipe, sp["words"]) for v, sp in specs.items()}
                if not any(F.parse(bad[v], sp["lex"], sp["order"]) for v, sp in specs.items()):
                    break
            else:
                continue
            emit("parse", {v: ({"sentence": " ".join(bad[v])}, {"grammatical": False, "level": lvl}) for v in VARIANTS})

    # interpret items: all readings, and their truth on the released and hidden models
    for _ in range(n_interp):
        tree, _ = F.generate(rng, base)
        out, n_readings = {}, set()
        for v, sp in specs.items():
            t, ws = realise(tree, sp)
            rs = F.readings(t, sp["lex"])
            n_readings.add(len(rs))
            out[v] = [{"sentence": " ".join(ws)},
                      {"readings": [F.tptp(r) for r in rs], "truth": truth_table(rs, models, n_models)}]
        lvl = max(F.level(tree), 3 if max(n_readings) > 1 else 1)
        for v in VARIANTS:
            out[v][1]["level"] = lvl
        emit("interpret", {v: tuple(x) for v, x in out.items()})

    # infer items: the conclusion is usually a related sentence, so all three labels occur. The label is
    # decided by Prover9/Mace4 in each variant; items are kept only if every variant has a label, and the
    # label counts are balanced on the nonce variant.
    counts = {"entailment": 0, "contradiction": 0, "neutral": 0}
    cap = (n_infer + 2) // 3
    tries = 0
    while sum(counts.values()) < n_infer and tries < n_infer * 60:
        tries += 1
        prem_trees = [F.generate(rng, base)[0]]
        if rng.random() < 0.4:
            prem_trees.append(F.generate(rng, base)[0])
        concl_tree = related(rng, prem_trees[0], base) if rng.random() < 0.8 else F.generate(rng, base)[0]
        sample_seed = rng.randrange(10**6)
        out = {}
        for v, sp in specs.items():
            prem = [realise(t, sp) for t in prem_trees]
            concl = realise(concl_tree, sp)
            pt = [F.readings(t, sp["lex"])[0] for t, _ in prem]
            ct = F.readings(concl[0], sp["lex"])[0]
            lab, cert = label(pt, ct, sp["lex"], sample_seed)
            out[v] = (lab, {"premises": [" ".join(w) for _, w in prem], "conclusion": " ".join(concl[1])},
                      {"label": lab, "lfs": {"premises": [F.tptp(t) for t in pt], "conclusion": F.tptp(ct)},
                       "certificate": cert})
        # "inconsistent" (premises jointly unsatisfiable) and undecided items have no label: skip them
        if any(out[v][0] not in counts for v in VARIANTS) or counts[out["nonce"][0]] >= cap:
            continue
        counts[out["nonce"][0]] += 1
        lvl = max(F.level(t) for t in prem_trees + [concl_tree])
        emit("infer", {v: (out[v][1], {**out[v][2], "level": lvl}) for v in VARIANTS})

    files = {}
    for v, sp in specs.items():
        files.update({
            f"{v}/lexicon.txt": F.lexicon_txt(sp["lex"]),
            f"{v}/grammar.txt": F.grammar_txt(sp["order"]),
            f"{v}/semantics.txt": F.semantics_txt(sp["lex"]),
            f"{v}/models.json": F.models_json(released),
            f"{v}/items.jsonl": jsonl(items[v]),
            f"{v}/gold/gold.jsonl": jsonl(gold[v]),
            f"{v}/gold/models_hidden.json": F.models_json(hidden, prefix="H"),
            f"{v}/gold/gold_as_submission.jsonl": jsonl(as_submission(gold[v])),
        })
    return files, counts


def as_submission(gold):
    """The compiled specification as a system: the gold rewritten in the submission format."""
    sub = []
    for g in gold:
        if g["type"] == "parse":
            sub.append({"id": g["id"], "grammatical": g["grammatical"], **({"tree": g["trees"][0]} if g["grammatical"] else {})})
        elif g["type"] == "interpret":
            sub.append({"id": g["id"], "lfs": g["readings"],
                        "truth": [{k: val for k, val in t.items() if k.startswith("M")} for t in g["truth"]]})
        else:
            sub.append({"id": g["id"], "label": g["label"], "lfs": g["lfs"], "certificate": g["certificate"]})
    return sub


def jsonl(rows):
    return "".join(json.dumps(x) + "\n" for x in rows)


def write(path, s):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", default=None)
    ap.add_argument("--n-parse", type=int, default=40)
    ap.add_argument("--n-interp", type=int, default=40)
    ap.add_argument("--n-infer", type=int, default=30)
    ap.add_argument("--without-ladr", action="store_true",
                    help="development only: no Prover9/Mace4; infer items are neutral-only and found by sampling")
    a = ap.parse_args()
    if not a.without_ladr and not P.ladr_available():
        sys.exit("Prover9/Mace4 not found (see docs/LADR.md). Gold must be computed with the pinned LADR; "
                 "use --without-ladr only for development.")
    out = a.out or f"out/seed{a.seed}"
    files, counts = build_fragment(a.seed, a.n_parse, a.n_interp, a.n_infer, use_ladr=not a.without_ladr)
    for p, s in files.items():
        write(os.path.join(out, p), s)
    print(f"wrote {out}: variants {', '.join(VARIANTS)}; infer labels (nonce) {counts}")


if __name__ == "__main__":
    main()
