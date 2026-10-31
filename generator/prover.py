"""Prover9 and Mace4 (LADR), wrapped so that results are deterministic and never silently wrong.

What this module guarantees:
  * Every symbol is renamed on the way in: constants become c_<name>, predicates p_<name>, bound
    variables x1, x2, ...  (Prover9 reads any free name starting with u-z as a *variable*; without the
    renaming, `wutbu(wonbis)` would mean "everything wutbus".)
  * Search is limited by a deterministic resource (Prover9: max_given; Mace4: end_size), not by
    wall-clock time, so the same input gives the same answer on any machine. A wall-clock limit exists
    only as a safety net; hitting it raises LadrTimeout instead of being treated as "not proved".
  * Every outcome is explicit: prove() returns PROVED, NOT_PROVED (search exhausted: no proof exists)
    or UNKNOWN (resource limit reached); find_model() returns a model or None. LADR errors raise LadrError.
  * Every model Mace4 returns is re-checked with our own model checker (logic.holds).
  * The LADR version is read from each run and must be the pinned one (LADR_VERSION), unless the
    environment variable FRAGMENTS_ALLOW_ANY_LADR=1 is set.

label_terms() combines these into the inference label and its certificate.
"""
import os
import re
import shutil
import subprocess
from dataclasses import dataclass

import logic as L

LADR_VERSION = "2009-11A"          # the final LADR release; see docs/LADR.md
PROVER9_MAX_GIVEN = 2000            # deterministic search limit for Prover9
MACE4_END_SIZE = 4                  # Mace4 searches domains of size 2..MACE4_END_SIZE (see find_model)
WALL_CLOCK_SAFETY = 120             # seconds; only a safety net, see LadrTimeout

PROVED, NOT_PROVED, UNKNOWN = "proved", "not_proved", "unknown"


class LadrError(RuntimeError):
    """Prover9/Mace4 reported an error, is the wrong version, or disagrees with the model checker."""


class LadrTimeout(LadrError):
    """The wall-clock safety limit was hit. This should not happen with the deterministic limits; it is
    raised rather than reported as UNKNOWN because a wall-clock result would differ between machines."""


def prover9_path():
    return os.environ.get("PROVER9") or shutil.which("prover9")


def mace4_path():
    return os.environ.get("MACE4") or shutil.which("mace4")


def ladr_available():
    return bool(prover9_path() and mace4_path())


# ---------------------------------------------------------------- translation to LADR syntax

def to_ladr(t, env=None, counter=None):
    """A formula in Prover9/Mace4 syntax, with every symbol renamed (see the module docstring)."""
    env = {} if env is None else env
    counter = counter if counter is not None else [0]
    k = t[0]
    if k == "var":
        return env[t[1]]
    if k == "const":
        return "c_" + t[1]
    if k == "pred":
        return f"p_{t[1]}({','.join(to_ladr(a, env, counter) for a in t[2])})"
    if k == "not":
        return f"-({to_ladr(t[1], env, counter)})"
    if k in ("and", "or", "imp"):
        op = {"and": "&", "or": "|", "imp": "->"}[k]
        return f"({to_ladr(t[1], env, counter)} {op} {to_ladr(t[2], env, counter)})"
    if k in ("forall", "exists"):
        counter[0] += 1
        v = f"x{counter[0]}"
        q = "all" if k == "forall" else "exists"
        return f"({q} {v} {to_ladr(t[2], {**env, t[1]: v}, counter)})"
    raise ValueError(f"unknown formula node {k!r}")


def _input(assumptions, goals=(), options=()):
    lines = list(options)
    lines.append("formulas(assumptions).")
    lines += [to_ladr(a) + "." for a in assumptions]
    lines.append("end_of_list.")
    if goals:
        lines.append("formulas(goals).")
        lines += [to_ladr(g) + "." for g in goals]
        lines.append("end_of_list.")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- running

def _run(program, path, text):
    if not path:
        raise LadrError(f"{program} is not installed (see docs/LADR.md)")
    try:
        r = subprocess.run([path], input=text, capture_output=True, text=True, timeout=WALL_CLOCK_SAFETY)
    except subprocess.TimeoutExpired:
        raise LadrTimeout(f"{program} exceeded the {WALL_CLOCK_SAFETY}s safety limit on:\n{text}")
    out = r.stdout + r.stderr
    if "%%ERROR" in out or "Fatal error" in out:
        raise LadrError(f"{program} reported an error on input:\n{text}\noutput:\n{out[-2000:]}")
    _check_version(program, out)
    return out


def _check_version(program, out):
    m = re.search(rf"{program} \(\d+\) version (\S+?),", out)
    found = m.group(1) if m else None
    if found != LADR_VERSION and os.environ.get("FRAGMENTS_ALLOW_ANY_LADR") != "1":
        raise LadrError(f"{program} version {found!r} found, {LADR_VERSION!r} required "
                        "(set FRAGMENTS_ALLOW_ANY_LADR=1 to override for experiments)")


@dataclass
class ProofResult:
    status: str          # PROVED, NOT_PROVED or UNKNOWN
    proof: str = ""      # the proof's clause lines (no timing lines), if PROVED


def normalise_proof(raw):
    """The clauses of the first proof, without Prover9's comment lines (which include timings)."""
    m = re.search(r"=+ PROOF =+\n(.*?)\n=+ end of proof =+", raw, re.S)
    body = m.group(1) if m else ""
    return "\n".join(l.rstrip() for l in body.splitlines() if l.strip() and not l.startswith("%"))


def prove(assumptions, goal, max_given=PROVER9_MAX_GIVEN):
    """Does `assumptions` entail `goal` (formulas as terms)?"""
    opts = [f"assign(max_given, {max_given})."]
    out = _run("Prover9", prover9_path(), _input(assumptions, [goal], opts))
    if "THEOREM PROVED" in out:
        return ProofResult(PROVED, normalise_proof(out))
    if "SEARCH FAILED" in out and "sos_empty" in out:
        return ProofResult(NOT_PROVED)
    return ProofResult(UNKNOWN)


# ---------------------------------------------------------------- Mace4 models

_ELEMENTS = "abcdefghijklmnopqrstuvwxyz"


def parse_mace4_model(out, signature):
    """Our model dict from Mace4's first `interpretation(...)` block. Symbols of the signature that the
    formulas did not mention get an arbitrary fixed value (first element, empty extension): they cannot
    affect the truth of the formulas the model was built for."""
    m = re.search(r"interpretation\(\s*(\d+)\s*,(.*?)\]\)\.", out, re.S)
    if not m:
        return None
    n = int(m.group(1))
    D = list(_ELEMENTS[:n])
    consts = {c: D[0] for c in signature["consts"]}
    preds = {p: set() for p in signature["preds"]}
    for kind, name, args, values in re.findall(r"(function|relation)\((\w+)(\([_,]*\))?\s*,\s*\[([\d,\s]*)\]\)", m.group(2)):
        vals = [int(v) for v in values.replace(" ", "").replace("\n", "").split(",") if v != ""]
        arity = 0 if not args else args.count("_")
        if kind == "function" and arity == 0 and name.startswith("c_"):
            consts[name[2:]] = D[vals[0]]
        elif kind == "relation" and name.startswith("p_"):
            p = name[2:]
            if arity == 1:
                preds[p] = {D[i] for i, v in enumerate(vals) if v}
            elif arity == 2:
                preds[p] = {(D[i // n], D[i % n]) for i, v in enumerate(vals) if v}
    return {"D": D, "consts": consts, "preds": preds}


def find_model(formulas, signature, end_size=MACE4_END_SIZE):
    """A model of all `formulas` with at most `end_size` elements, or None if there is none that small.
    The model is re-checked with logic.holds; a disagreement raises LadrError."""
    # Mace4 starts at size 2 at the smallest. Nothing is lost: the formulas have no equality, so a model can be
    # enlarged by duplicating an element without changing any truth value, and a 1-element model implies a
    # 2-element one.
    opts = ["assign(start_size, 2).", f"assign(end_size, {end_size})."]
    out = _run("Mace4", mace4_path(), _input(formulas, (), opts))
    model = parse_mace4_model(out, signature)
    if model is None:
        return None
    for f in formulas:
        if not L.holds(f, model):
            raise LadrError(f"Mace4 model does not satisfy {L.tptp(f)} by our model checker:\n{out[-2000:]}")
    return model


# ---------------------------------------------------------------- inference labels

def signature_of(lex):
    """{"consts": {...}, "preds": {name: arity}} for a fragment lexicon (word -> (category, meaning))."""
    consts = {m for c, m in lex.values() if c == "PN"}
    preds = {m: (2 if c == "TV" else 1) for c, m in lex.values() if c in ("N", "IV", "TV")}
    return {"consts": consts, "preds": preds}


def label_terms(prem_terms, concl_term, lex):
    """The inference label and certificate for premises and a conclusion (formulas as terms).

    Returns (label, certificate) where label is one of
      "entailment"     premises |- conclusion is proved, and a model of premises + conclusion exists
      "contradiction"  premises |- ~conclusion is proved, and a model of premises + ~conclusion exists
      "neutral"        models of premises + conclusion and of premises + ~conclusion both exist
      "inconsistent"   the premises are jointly unsatisfiable (both proofs exist; no label is defined)
      None             undecided within the deterministic limits
    The certificate is {"proof": ...} for entailment/contradiction and {"models": [m_true, m_false]}
    for neutral. Any disagreement between the prover and the model finder raises LadrError: it would mean
    a translation bug like the u-z one.
    """
    sig = signature_of(lex)
    neg = ("not", concl_term)
    ent = prove(prem_terms, concl_term)
    con = prove(prem_terms, neg)
    m_true = find_model(list(prem_terms) + [concl_term], sig)
    m_false = find_model(list(prem_terms) + [neg], sig)
    if ent.status == PROVED and m_false is not None:
        raise LadrError("Prover9 proved the conclusion but Mace4 found a model of premises + ~conclusion")
    if con.status == PROVED and m_true is not None:
        raise LadrError("Prover9 proved ~conclusion but Mace4 found a model of premises + conclusion")
    if ent.status == PROVED and con.status == PROVED:
        return "inconsistent", {}
    if ent.status == PROVED and m_true is not None:
        return "entailment", {"proof": ent.proof}
    if con.status == PROVED and m_false is not None:
        return "contradiction", {"proof": con.proof}
    if m_true is not None and m_false is not None:
        return "neutral", {"models": [L.model_to_json(m_true), L.model_to_json(m_false)]}
    return None, {}


def label_terms_by_sampling(prem_terms, concl_term, lex, rng, max_domain=3, samples=3000):
    """Development fallback when LADR is not installed: finds neutral items only (by random models,
    checked exactly); entailment and contradiction cannot be established this way and give None."""
    from fragment import random_model
    m_true = m_false = None
    for _ in range(samples):
        m = random_model(rng, lex, rng.choice(range(1, max_domain + 1)))
        if not all(L.holds(p, m) for p in prem_terms):
            continue
        if L.holds(concl_term, m):
            m_true = m_true or m
        else:
            m_false = m_false or m
        if m_true and m_false:
            return "neutral", {"models": [L.model_to_json(m_true), L.model_to_json(m_false)]}
    return None, {}
