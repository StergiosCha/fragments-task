"""A Montague fragment as data: grammar, lexicon, compositional semantics, finite models.

Year-one coverage: quantification (level 1), negation (2), relative clauses and
scope ambiguity (3). Logical forms are first-order; the semantics is written as
an explicit lambda-term evaluator over a tiny term language so that the gold is
computed, never annotated.

Terms (nested tuples):
  ('var', 'x')            variable
  ('const', 'tam')        constant
  ('pred', 'p', (t1..))   atom
  ('and', A, B) ('or', A, B) ('not', A) ('imp', A, B)
  ('forall', 'x', A) ('exists', 'x', A)
"""
import itertools, json, random

CATS = ["PN", "N", "IV", "TV", "Det"]

# --- grammar: fixed shape for year one; word order comes from the variant ---
RULES = {  # lhs -> list of rhs sequences (symbols in canonical SVO order)
    "S":  [["NP", "VP"]],
    "NP": [["Det", "N"], ["PN"], ["Det", "N", "RC"]],
    "RC": [["that", "VP"], ["that", "NP", "TV"]],
    "VP": [["IV"], ["TV", "NP"], ["not", "VP"]],
}
FUNCTION_WORDS = ["that", "not"]

DET_MEANINGS = {  # name -> (how to combine restrictor P and scope Q)
    "every": lambda P, Q, x: ("forall", x, ("imp", P, Q)),
    "some":  lambda P, Q, x: ("exists", x, ("and", P, Q)),
    "no":    lambda P, Q, x: ("not", ("exists", x, ("and", P, Q))),
}
DET_TEXT = {
    "every": "\\P.\\Q. forall x (P(x) -> Q(x))",
    "some":  "\\P.\\Q. exists x (P(x) & Q(x))",
    "no":    "\\P.\\Q. ~exists x (P(x) & Q(x))",
}
SEMANTICS_TEXT = """[S NP VP]        = NP(VP)
[NP Det N]       = Det(N)
[NP PN]          = PN
[NP Det N RC]    = Det(\\x. N(x) & RC(x))
[RC that VP]     = \\x. VP(x)
[RC that NP TV]  = \\x. NP(\\y. TV(y,x))
[VP IV]          = IV
[VP TV NP]       = \\x. NP(\\y. TV(x,y))
[VP not VP]      = \\x. ~VP(x)
"""


def nonce_words(rng, n, used):
    ons, nuc, cod = "bdfgklmnprstvwz", "aeiou", ["", "", "k", "p", "t", "m", "n", "s"]
    out = []
    while len(out) < n:
        w = rng.choice(ons) + rng.choice(nuc) + rng.choice(cod) + rng.choice(ons) + rng.choice(nuc) + rng.choice(cod)
        if w not in used:
            used.add(w); out.append(w)
    return out


def make_lexicon(rng, counter_english=None):
    """lexicon: word -> (cat, meaning-key). PN/N/IV/TV meanings are their own predicate names."""
    used = set()
    pn = nonce_words(rng, 2, used); n = nonce_words(rng, 3, used)
    iv = nonce_words(rng, 2, used); tv = nonce_words(rng, 2, used)
    det = nonce_words(rng, 3, used)
    det_sem = {det[0]: "every", det[1]: "some", det[2]: "no"}
    if counter_english:  # swap the meanings of two determiners
        a, b = counter_english
        det_sem[a], det_sem[b] = det_sem[b], det_sem[a]
    lex = {}
    for w in pn: lex[w] = ("PN", w)
    for w in n: lex[w] = ("N", w)
    for w in iv: lex[w] = ("IV", w)
    for w in tv: lex[w] = ("TV", w)
    for w in det: lex[w] = ("Det", det_sem[w])
    return lex


ENGLISH = {"PN": ["Tam", "Ren"], "N": ["farmer", "donkey", "cat"], "IV": ["walks", "sleeps"],
           "TV": ["sees", "likes"], "Det": ["every", "some", "no"]}


def english_lexicon(lex):
    """Same categories and meanings, English surface words (the English-word twin)."""
    out, idx = {}, {c: 0 for c in CATS}
    for w, (c, m) in lex.items():
        e = ENGLISH[c][idx[c]]; idx[c] += 1
        out[e] = (c, m)
    return out


# --- word order variants: a permutation of each rule's rhs ---
ORDERS = {
    "svo": {},
    "scrambled": {("S", 0): [1, 0], ("VP", 1): [1, 0], ("NP", 0): [1, 0], ("NP", 2): [2, 1, 0], ("RC", 1): [2, 1, 0]},
}


def surface_rules(order):
    perm = ORDERS[order]
    out = {}
    for lhs, rhss in RULES.items():
        out[lhs] = []
        for i, rhs in enumerate(rhss):
            p = perm.get((lhs, i), list(range(len(rhs))))
            out[lhs].append(([rhs[j] for j in p], p))  # (surface rhs, position -> canonical index)
    return out


# --- parsing: all derivations, recursive descent over the small CFG ---
def parse(words, lex, order="svo"):
    rules = surface_rules(order)

    def term(sym, i):  # yields (tree, next index)
        if sym in FUNCTION_WORDS:
            if i < len(words) and words[i] == sym: yield (sym, i + 1)
            return
        if sym in CATS:
            if i < len(words) and lex.get(words[i], (None,))[0] == sym: yield ((sym, words[i]), i + 1)
            return
        for ri, (rhs, perm) in enumerate(rules[sym]):
            for kids, j in seq(rhs, i):
                canon = [None] * len(kids)
                for pos, k in enumerate(kids): canon[perm[pos]] = k
                yield ((sym, ri, tuple(canon)), j)

    def seq(rhs, i):
        if not rhs: yield ([], i); return
        for k, j in term(rhs[0], i):
            for rest, m in seq(rhs[1:], j): yield ([k] + rest, m)

    return [t for t, j in term("S", 0) if j == len(words)]


def tree_str(t):
    if isinstance(t, str): return t
    if len(t) == 2: return f"[{t[0]} {t[1]}]"
    return "[" + t[0] + " " + " ".join(tree_str(k) for k in t[2]) + "]"


# --- semantics: a tree denotes a set of readings (scope ambiguity yields several) ---
_fresh = itertools.count()


def fresh():
    return "X" + str(next(_fresh))


def readings(tree, lex):
    """Returns a list of closed formulas (terms); >1 only for scope ambiguity."""
    global _fresh
    _fresh = itertools.count(1)
    return [f for f in _interp_S(tree, lex)]


def _np(tree, lex):
    """An NP denotes a list of (quantifier-builder) functions Q -> formula, where Q : var -> formula;
    each list element is one reading of the NP."""
    _, ri, kids = tree
    if ri == 1:  # PN
        c = kids[0][1]
        return [lambda Q, c=c: Q(("const", lex[c][1]))]
    det = DET_MEANINGS[lex[kids[0][1]][1]]
    noun = lex[kids[1][1]][1]
    if ri == 0:
        def q(Q, det=det, noun=noun):
            x = fresh(); v = ("var", x)
            return det(("pred", noun, (v,)), Q(v), x)
        return [q]
    # Det N RC: restrictor is N(x) & RC(x); RC may itself be ambiguous
    outs = []
    for rc in _rc(kids[2], lex):
        def q(Q, det=det, noun=noun, rc=rc):
            x = fresh(); v = ("var", x)
            return det(("and", ("pred", noun, (v,)), rc(v)), Q(v), x)
        outs.append(q)
    return outs


def _rc(tree, lex):
    _, ri, kids = tree
    if ri == 0:  # that VP
        return [lambda v, vp=vp: vp(v) for vp in _vp(kids[1], lex)]
    tvname = lex[kids[2][1]][1]  # that NP TV  (object relative: x such that NP TV x)
    return [lambda v, np=np, tv=tvname: np(lambda y: ("pred", tv, (y, v))) for np in _np(kids[1], lex)]


def _vp(tree, lex):
    """A VP denotes a list of functions var -> formula (one per reading)."""
    _, ri, kids = tree
    if ri == 0:
        p = lex[kids[0][1]][1]
        return [lambda v, p=p: ("pred", p, (v,))]
    if ri == 2:
        return [lambda v, vp=vp: ("not", vp(v)) for vp in _vp(kids[1], lex)]
    tv = lex[kids[0][1]][1]
    return [lambda v, np=np, tv=tv: np(lambda y: ("pred", tv, (v, y))) for np in _np(kids[1], lex)]


def _interp_S(tree, lex):
    _, _, (np_t, vp_t) = tree
    out = []
    for np in _np(np_t, lex):
        for vp in _vp(vp_t, lex):
            out.append(np(vp))                       # subject wide scope
            # object wide scope, if the VP contains a quantified object NP
            if vp_t[1] == 1 and vp_t[2][1][1] != 1:
                for onp in _np(vp_t[2][1], lex):
                    tv = lex[vp_t[2][0][1]][1]
                    out.append(onp(lambda y: np(lambda x: ("pred", tv, (x, y)))))
    # dedupe readings equal up to renaming of bound variables (PN subjects give no second reading)
    seen, uniq = set(), []
    for f in out:
        k = tptp(canon(f))
        if k not in seen: seen.add(k); uniq.append(f)
    return uniq


def canon(t, env=None, n=None):
    """Rename bound variables in order of binding so alpha-equivalent terms print identically."""
    env = env or {}; n = n or itertools.count(1)
    k = t[0]
    if k == "var": return ("var", env.get(t[1], t[1]))
    if k in ("const",): return t
    if k == "pred": return ("pred", t[1], tuple(canon(a, env, n) for a in t[2]))
    if k == "not": return ("not", canon(t[1], env, n))
    if k in ("and", "or", "imp"): return (k, canon(t[1], env, n), canon(t[2], env, n))
    v = "V" + str(next(n))
    return (k, v, canon(t[2], {**env, t[1]: v}, n))


# --- printing: TPTP first-order syntax ---
def tptp(t):
    k = t[0]
    if k == "var": return t[1]
    if k == "const": return t[1]
    if k == "pred": return f"{t[1]}({','.join(tptp(a) for a in t[2])})"
    if k == "not": return f"~{par(t[1])}"
    if k == "and": return f"({tptp(t[1])} & {tptp(t[2])})"
    if k == "or": return f"({tptp(t[1])} | {tptp(t[2])})"
    if k == "imp": return f"({tptp(t[1])} => {tptp(t[2])})"
    if k == "forall": return f"! [{t[1]}] : {par(t[2])}"
    if k == "exists": return f"? [{t[1]}] : {par(t[2])}"
    raise ValueError(k)


def par(t):
    s = tptp(t)
    return s if t[0] in ("pred", "not", "and", "or", "imp") and s.startswith("(") or t[0] == "pred" else f"({s})"


# --- models and evaluation ---
def random_model(rng, lex, size):
    D = [chr(97 + i) for i in range(size)]
    m = {"D": D, "consts": {}, "preds": {}}
    for w, (c, meaning) in lex.items():
        if c == "PN": m["consts"][meaning] = rng.choice(D)
        elif c in ("N", "IV"): m["preds"][meaning] = sorted({d for d in D if rng.random() < 0.5})
        elif c == "TV": m["preds"][meaning] = sorted({(x, y) for x in D for y in D if rng.random() < 0.35})
    return m


def holds(t, m, env=None):
    env = env or {}
    k = t[0]
    if k == "pred":
        args = tuple(env[a[1]] if a[0] == "var" else m["consts"][a[1]] for a in t[2])
        ext = m["preds"][t[1]]
        return (args[0] if len(args) == 1 else list(args)) in [e if isinstance(e, str) else list(e) for e in ext]
    if k == "not": return not holds(t[1], m, env)
    if k == "and": return holds(t[1], m, env) and holds(t[2], m, env)
    if k == "or": return holds(t[1], m, env) or holds(t[2], m, env)
    if k == "imp": return (not holds(t[1], m, env)) or holds(t[2], m, env)
    if k == "forall": return all(holds(t[2], m, {**env, t[1]: d}) for d in m["D"])
    if k == "exists": return any(holds(t[2], m, {**env, t[1]: d}) for d in m["D"])
    raise ValueError(k)


# --- surface generation ---
def generate(rng, lex, order="svo", depth=0):
    """Random tree + its surface string under the given word order."""
    rules = surface_rules(order)
    words_of = {c: [w for w, (cc, _) in lex.items() if cc == c] for c in CATS}

    def gen(sym, d):
        if sym in FUNCTION_WORDS: return sym, [sym]
        if sym in CATS:
            w = rng.choice(words_of[sym]); return (sym, w), [w]
        choices = list(enumerate(rules[sym]))
        if d > 1:  # cap recursion: no RC or 'not' deeper than 2
            choices = [(i, r) for i, r in choices if "RC" not in r[0] and "not" not in r[0]]
        ri, (rhs, perm) = rng.choice(choices)
        kids, words = [], []
        for s in rhs:
            k, ws = gen(s, d + 1); kids.append(k); words += ws
        canon = [None] * len(kids)
        for pos, k in enumerate(kids): canon[perm[pos]] = k
        return (sym, ri, tuple(canon)), words

    return gen("S", depth)


def level(tree):
    """Phenomenon level of a tree: 3 if any RC or scope ambiguity, 2 if 'not', else 1."""
    s = tree_str(tree)
    if "[RC" in s: return 3
    if "not" in s: return 2
    return 1


# --- the package files ---
def lexicon_txt(lex):
    by = {c: [w for w, (cc, _) in lex.items() if cc == c] for c in CATS}
    return "\n".join(f"{c}: {', '.join(by[c])}" for c in CATS) + "\n"


def grammar_txt(order):
    rules = surface_rules(order)
    return "\n".join(f"{lhs} -> " + " | ".join(" ".join(rhs) for rhs, _ in rhss) for lhs, rhss in rules.items()) + "\n"


def semantics_txt(lex):
    dets = "\n".join(f"{w} = {DET_TEXT[m]}" for w, (c, m) in lex.items() if c == "Det")
    words = "\n".join(f"{w} = {m}" for w, (c, m) in lex.items() if c in ("PN", "N", "IV", "TV"))
    return SEMANTICS_TEXT + "\n" + dets + "\n" + words + "\n"


def models_json(models):
    return json.dumps({f"M{i+1}": {"D": m["D"], **m["consts"], **m["preds"]} for i, m in enumerate(models)}, indent=1)
