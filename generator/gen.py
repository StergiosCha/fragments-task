#!/usr/bin/env python3
"""Generate a fragment package + items + gold for one seed.

  python3 gen.py --seed 1 --out out/seed1 [--n-parse 40 --n-interp 40 --n-infer 30]

Writes, per variant (nonce, english, scrambled, counter):
  <out>/<variant>/{lexicon.txt,grammar.txt,semantics.txt,models.json,items.jsonl}
  <out>/<variant>/gold/{gold.jsonl,models_hidden.json,gold_as_submission.jsonl}
"""
import argparse, json, os, random, sys
import fragment as F
import prover as P

VARIANTS = ["nonce", "english", "scrambled", "counter"]


def write(path, s):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f: f.write(s)


def perturb(rng, words, lex):
    """One-word perturbation that leaves the fragment: swap two adjacent words, drop a word, or insert a random word.
    Returns None if the perturbed string is still grammatical."""
    ws = list(words)
    op = rng.choice(["swap", "drop", "insert"])
    if op == "swap" and len(ws) > 1:
        i = rng.randrange(len(ws) - 1); ws[i], ws[i + 1] = ws[i + 1], ws[i]
    elif op == "drop" and len(ws) > 1:
        del ws[rng.randrange(len(ws))]
    else:
        ws.insert(rng.randrange(len(ws) + 1), rng.choice(list(lex)))
    return ws


def related(rng, tree, lex, order):
    """A conclusion built from the premise tree by one edit: change the subject determiner, negate or
    un-negate the VP, or drop the subject's relative clause. Returns (tree, words)."""
    S, _, (np, vp) = tree
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
    t = ("S", 0, (np, vp))
    return t, words_of(t, order)


def words_of(tree, order):
    """Surface string of a canonical tree under a word order."""
    rules = F.surface_rules(order)
    if isinstance(tree, str): return [tree]
    if len(tree) == 2: return [tree[1]]
    sym, ri, kids = tree
    rhs, perm = rules[sym][ri]
    out = []
    for pos in range(len(rhs)): out += words_of(kids[perm[pos]], order)
    return out


def build_variant(seed, variant, n_parse, n_interp, n_infer, n_models=2, n_hidden=3, use_ladr=True):
    rng = random.Random(f"{seed}-{variant}")
    base = F.make_lexicon(random.Random(seed))  # same nonce words across variants
    order = "scrambled" if variant == "scrambled" else "svo"
    if variant == "counter":
        dets = [w for w, (c, _) in base.items() if c == "Det"]
        lex = F.make_lexicon(random.Random(seed), counter_english=(dets[0], dets[2]))  # every <-> no
    elif variant == "english":
        lex = F.english_lexicon(base)
    else:
        lex = base
    models = [F.random_model(rng, lex, rng.choice([2, 3])) for _ in range(n_models + n_hidden)]
    released, hidden = models[:n_models], models[n_models:]

    items, gold, sub = [], [], []
    nid = 0

    def emit(kind, item, g):
        nonlocal nid
        nid += 1
        items.append({"id": nid, "type": kind, **item})
        gold.append({"id": nid, "type": kind, **g})

    # parse items: half grammatical, half perturbed
    for i in range(n_parse):
        tree, words = F.generate(rng, lex, order)
        if i % 2 == 0:
            trees = F.parse(words, lex, order)
            emit("parse", {"sentence": " ".join(words)}, {"grammatical": True, "trees": [F.tree_str(t) for t in trees], "level": F.level(tree)})
        else:
            for _ in range(10):
                ws = perturb(rng, words, lex)
                if not F.parse(ws, lex, order): break
            else:
                continue
            emit("parse", {"sentence": " ".join(ws)}, {"grammatical": False, "level": F.level(tree)})

    # interpret items: all readings + truth on released and hidden models
    for _ in range(n_interp):
        tree, words = F.generate(rng, lex, order)
        rs = F.readings(tree, lex)
        truth = [{(f"M{j+1}" if j < n_models else f"H{j+1-n_models}"): F.holds(r, m) for j, m in enumerate(models)} for r in rs]
        emit("interpret", {"sentence": " ".join(words)},
             {"readings": [F.tptp(r) for r in rs], "truth": truth, "level": max(F.level(tree), 3 if len(rs) > 1 else 1)})

    # infer items: conclusion is a related sentence (shared vocabulary), so entailment/contradiction
    # occur often enough to balance; the prover/sampler assigns the label regardless of how it was built
    counts = {"entailment": 0, "contradiction": 0, "neutral": 0}
    cap = (n_infer + 2) // 3
    tries = 0
    while sum(counts.values()) < n_infer and tries < n_infer * 60:
        tries += 1
        prem_t, prem_w = F.generate(rng, lex, order)
        prems = [(prem_t, prem_w)]
        if rng.random() < 0.4: prems.append(F.generate(rng, lex, order))
        concl = related(rng, prem_t, lex, order) if rng.random() < 0.8 else F.generate(rng, lex, order)
        pt = [F.readings(t, lex)[0] for t, _ in prems]
        ct = F.readings(concl[0], lex)[0]
        sub_rng = random.Random(rng.randrange(10**6))
        if use_ladr:
            lab, cert = P.label_terms(pt, ct, lex)
        else:
            lab, cert = P.label_terms_by_sampling(pt, ct, lex, sub_rng)
        # "inconsistent" (premises jointly unsatisfiable) has no defined label; such items are skipped
        if lab not in counts or counts[lab] >= cap: continue
        counts[lab] += 1
        emit("infer", {"premises": [" ".join(w) for _, w in prems], "conclusion": " ".join(concl[1])},
             {"label": lab, "lfs": {"premises": [F.tptp(t) for t in pt], "conclusion": F.tptp(ct)}, "certificate": cert,
              "level": max([F.level(t) for t, _ in prems] + [F.level(concl[0])])})

    # the compiled-spec reference submission: gold rewritten as a submission
    for g in gold:
        if g["type"] == "parse":
            sub.append({"id": g["id"], "grammatical": g["grammatical"], **({"tree": g["trees"][0]} if g["grammatical"] else {})})
        elif g["type"] == "interpret":
            sub.append({"id": g["id"], "lfs": g["readings"], "truth": [{k: v for k, v in t.items() if k.startswith("M")} for t in g["truth"]]})
        else:
            sub.append({"id": g["id"], "label": g["label"], "lfs": g["lfs"], "certificate": g["certificate"]})

    d = f"{variant}"
    return {
        f"{d}/lexicon.txt": F.lexicon_txt(lex),
        f"{d}/grammar.txt": F.grammar_txt(order),
        f"{d}/semantics.txt": F.semantics_txt(lex),
        f"{d}/models.json": F.models_json(released),
        f"{d}/items.jsonl": "".join(json.dumps(x) + "\n" for x in items),
        f"{d}/gold/gold.jsonl": "".join(json.dumps(x) + "\n" for x in gold),
        f"{d}/gold/models_hidden.json": F.models_json(hidden, prefix="H"),
        f"{d}/gold/gold_as_submission.jsonl": "".join(json.dumps(x) + "\n" for x in sub),
    }, counts


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
    for v in VARIANTS:
        files, counts = build_variant(a.seed, v, a.n_parse, a.n_interp, a.n_infer, use_ladr=not a.without_ladr)
        for p, s in files.items(): write(os.path.join(out, p), s)
        print(f"{v:10s} parse+interpret+infer written; infer labels {counts}")
    print("wrote", out)


if __name__ == "__main__":
    main()
