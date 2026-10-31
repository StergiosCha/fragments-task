#!/usr/bin/env python3
"""Score a submission against the gold of one variant.

  python3 score.py --variant out/seed1/nonce --submission out/seed1/nonce/gold/gold_as_submission.jsonl

Metrics (scoring_criteria.md, Part A):
  parse      grammaticality accuracy; tree match (submitted tree is one of the gold derivations)
  interpret  truth-vector agreement on released+hidden models for every submitted reading, set equality
             of readings modulo truth-vector equivalence, reading recall
  infer      label accuracy; certificate validity (proof re-checked with Prover9, or the two models
             re-checked with the model checker)
All reported per level.
"""
import argparse, json, os, re, collections
import fragment as F
from prover import _prove, PROVER9

# minimal TPTP parser (the subset gen.py emits) so submitted formulas can be model-checked
TOK = re.compile(r"\s*(=>|[!?]|\[|\]|:|\(|\)|,|&|\||~|[A-Za-z_][A-Za-z0-9_]*)")


def from_spec_notation(s):
    """Accept the specification's own notation as well as TPTP: `forall x (...)`, `exists x (...)`, `->`,
    lowercase bound variables. Bound variable names are uppercased so the TPTP parser reads them as variables."""
    if "forall" not in s and "exists" not in s and "->" not in s:
        return s
    bound = set(re.findall(r"\b(?:forall|exists)\s+([a-z]\w*)", s))
    s = s.replace("->", "=>")
    s = re.sub(r"\bforall\s+([a-z]\w*)\s*", lambda m: f"! [V_{m.group(1)}] : ", s)
    s = re.sub(r"\bexists\s+([a-z]\w*)\s*", lambda m: f"? [V_{m.group(1)}] : ", s)
    for v in bound:
        s = re.sub(rf"(?<![\w\[]){re.escape(v)}(?!\w)", f"V_{v}", s)
    return s


def norm_tree(t):
    """Trees are compared up to whitespace only; structure and labels must match exactly."""
    if not isinstance(t, str): return None
    return re.sub(r"\s+", " ", t).replace(" ]", "]").replace("[ ", "[").strip()


def parse_tptp(s):
    s = from_spec_notation(s)
    toks = TOK.findall(s); pos = [0]

    def peek(): return toks[pos[0]] if pos[0] < len(toks) else None
    def take(t=None):
        x = toks[pos[0]]; pos[0] += 1
        if t and x != t: raise ValueError(f"expected {t} got {x}")
        return x

    def binop():
        left = unary()
        while peek() in ("&", "|", "=>"):
            op = take(); right = unary()
            left = ({"&": "and", "|": "or", "=>": "imp"}[op], left, right)
        return left

    def unary():
        t = peek()
        if t == "~": take(); return ("not", unary())
        if t in ("!", "?"):
            q = take(); take("["); v = take(); take("]"); take(":")
            return ("forall" if q == "!" else "exists", v, unary())
        if t == "(": take(); e = binop(); take(")"); return e
        name = take()
        if peek() == "(":
            take(); args = [atom()]
            while peek() == ",": take(); args.append(atom())
            take(")"); return ("pred", name, tuple(args))
        return ("var", name) if name[0].isupper() else ("const", name)

    def atom():
        n = take()
        return ("var", n) if n[0].isupper() else ("const", n)

    e = binop()
    if pos[0] != len(toks): raise ValueError("trailing tokens")
    return e


def load_models(path, prefix):
    raw = json.load(open(path))
    out = {}
    for name, m in raw.items():
        D = m["D"]; consts, preds = {}, {}
        for k, v in m.items():
            if k == "D": continue
            if isinstance(v, str): consts[k] = v
            else: preds[k] = [tuple(e) if isinstance(e, list) else e for e in v]
        out[name] = {"D": D, "consts": consts, "preds": preds}
    return out


def vec(term, models):
    try: return tuple(F.holds(term, m) for m in models.values())
    except Exception: return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", required=True)
    ap.add_argument("--submission", required=True)
    a = ap.parse_args()
    gold = {g["id"]: g for g in map(json.loads, open(os.path.join(a.variant, "gold/gold.jsonl")))}
    sub = {s["id"]: s for s in map(json.loads, open(a.submission))}
    models = {**load_models(os.path.join(a.variant, "models.json"), "M"),
              **load_models(os.path.join(a.variant, "gold/models_hidden.json"), "H")}
    lex = {}  # predicate names are taken from the gold; nothing lexical is needed for checking
    tally = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0]))  # [metric][level] -> [hit, n]

    def mark(metric, lvl, ok):
        t = tally[metric][lvl]; t[0] += bool(ok); t[1] += 1
        t = tally[metric]["all"]; t[0] += bool(ok); t[1] += 1

    for gid, g in gold.items():
        s = sub.get(gid, {}); L = g["level"]
        if g["type"] == "parse":
            mark("parse/grammaticality", L, s.get("grammatical") == g["grammatical"])
            if g["grammatical"]:
                mark("parse/tree", L, norm_tree(s.get("tree")) in {norm_tree(t) for t in g["trees"]})
        elif g["type"] == "interpret":
            gvecs = {vec(parse_tptp(r), models) for r in g["readings"]}
            svecs = set()
            for lf in s.get("lfs", []):
                try: svecs.add(vec(parse_tptp(lf), models))
                except Exception: svecs.add(None)
            mark("interpret/truth-agreement", L, bool(svecs) and svecs <= gvecs)
            mark("interpret/reading-set", L, svecs == gvecs)
            mark("interpret/reading-recall", L, len(gvecs & svecs) == len(gvecs))
        else:
            mark("infer/label", L, s.get("label") == g["label"])
            mark("infer/certificate", L, check_cert(s, g, models))
    print(f"{'metric':30s} " + " ".join(f"{l:>8}" for l in ["1", "2", "3", "all"]))
    for metric in sorted(tally):
        row = []
        for l in [1, 2, 3, "all"]:
            h, n = tally[metric].get(l, [0, 0])
            row.append(f"{100*h/n:7.1f}%" if n else "      -")
        print(f"{metric:30s} " + " ".join(row))


def check_cert(s, g, models):
    """A certificate is valid if (a) the submitted lfs agree in truth value with the gold lfs on all models, and
    (b) for entailment/contradiction a proof re-checks (or, without Prover9, the label matches), for neutral the
    two submitted models are models of the premises in which the conclusion differs."""
    try:
        lfs = s["lfs"]; prem = [parse_tptp(p) for p in lfs["premises"]]; concl = parse_tptp(lfs["conclusion"])
        gprem = [parse_tptp(p) for p in g["lfs"]["premises"]]; gconcl = parse_tptp(g["lfs"]["conclusion"])
    except Exception:
        return False
    if any(vec(p, models) != vec(q, models) for p, q in zip(prem, gprem)) or vec(concl, models) != vec(gconcl, models):
        return False
    cert = s.get("certificate", {})
    if s.get("label") == "neutral":
        ms = cert.get("models")
        if not ms or len(ms) != 2: return False
        m_true, m_false = [load_models_inline(m) for m in ms]
        return (all(F.holds(p, m_true) for p in prem) and F.holds(concl, m_true)
                and all(F.holds(p, m_false) for p in prem) and not F.holds(concl, m_false))
    if "proof" in cert and PROVER9:
        goal = F.tptp(concl) if s.get("label") == "entailment" else "~(" + F.tptp(concl) + ")"
        return _prove([F.tptp(p) for p in prem], goal) is not None
    return s.get("label") == g["label"] and "enumeration_bound" in cert  # no-prover fallback


def load_models_inline(m):
    D = m["D"]; consts, preds = {}, {}
    for k, v in m.items():
        if k == "D": continue
        if isinstance(v, str): consts[k] = v
        else: preds[k] = [tuple(e) if isinstance(e, list) else e for e in v]
    return {"D": D, "consts": consts, "preds": preds}


if __name__ == "__main__":
    main()
