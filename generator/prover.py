"""Label an inference item with Prover9/Mace4 (TPTP formulas), with model-enumeration fallback.

label(premises, conclusion) -> ("entailment"|"contradiction"|"neutral", certificate)
certificate: {"proof": "<prover9 proof text>"} or {"models": [m_true, m_false]} for neutral
"""
import itertools, shutil, subprocess, tempfile, os, re
from fragment import holds

PROVER9 = shutil.which("prover9")
MACE4 = shutil.which("mace4")


def _p9(fmla):
    """TPTP -> Prover9 syntax."""
    s = fmla.replace("=>", "->").replace("~", "-")
    s = re.sub(r"!\s*\[(\w+)\]\s*:", r"all \1", s)
    s = re.sub(r"\?\s*\[(\w+)\]\s*:", r"exists \1", s)
    return s


def _run(cmd, inp, timeout=10):
    try:
        r = subprocess.run(cmd, input=inp, capture_output=True, text=True, timeout=timeout)
        return r.stdout + r.stderr
    except subprocess.TimeoutExpired:
        return ""


def _prove(assumptions, goal, timeout=10):
    inp = "formulas(assumptions).\n" + "".join(f"{_p9(a)}.\n" for a in assumptions) + "end_of_list.\nformulas(goals).\n" + f"{_p9(goal)}.\nend_of_list.\n"
    out = _run([PROVER9], inp, timeout)
    if "THEOREM PROVED" in out:
        m = re.search(r"=+ PROOF =+(.*?)=+ end of proof =+", out, re.S)
        return m.group(1).strip() if m else "proved"
    return None


def label_terms(prem_terms, concl_term, tptp, lex, max_domain=3, samples=3000, seed=0):
    """Terms in, label + certificate out.
    Order: Prover9 first (entailment, then contradiction, with a short timeout); if neither proves, sample
    small random models of the premises to find one making the conclusion true and one making it false,
    which is the neutral certificate. Items where neither side settles are discarded by the caller."""
    import random
    from fragment import tptp as T, random_model
    prem = [T(t) for t in prem_terms]; concl = T(concl_term)
    if PROVER9:
        pr = _prove(prem, concl, timeout=3)
        if pr is not None: return "entailment", {"proof": pr}
        pr = _prove(prem, "~(" + concl + ")", timeout=3)
        if pr is not None: return "contradiction", {"proof": pr}
    rng = random.Random(seed)
    m_true = m_false = None
    for _ in range(samples):
        m = random_model(rng, lex, rng.choice(range(1, max_domain + 1)))
        if not all(holds(p, m) for p in prem_terms): continue
        if holds(concl_term, m): m_true = m_true or m
        else: m_false = m_false or m
        if m_true and m_false: return "neutral", {"models": [_slim(m_true), _slim(m_false)]}
    return None, {}


def _slim(m):
    return {"D": m["D"], **m["consts"], **{k: [list(e) if isinstance(e, tuple) else e for e in v] for k, v in m["preds"].items()}}


