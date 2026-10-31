"""First-order formulas: the term language, TPTP printing and reading, and the model checker.

Formulas are nested tuples:
  ('var', 'X')                variable
  ('const', 'tam')            constant (a proper name)
  ('pred', 'p', (t1, ...))    atom
  ('not', A)  ('and', A, B)  ('or', A, B)  ('imp', A, B)
  ('forall', 'X', A)  ('exists', 'X', A)

A model is a dict
  {"D": ["a", "b"], "consts": {"tam": "a"}, "preds": {"walks": {"a"}, "sees": {("a", "b")}}}
Unary extensions hold domain elements, binary extensions hold pairs (tuples).
"""
import itertools
import re


# ---------------------------------------------------------------- printing (TPTP)

def tptp(t):
    """Print a formula in TPTP first-order syntax, fully bracketed."""
    k = t[0]
    if k in ("var", "const"):
        return t[1]
    if k == "pred":
        return f"{t[1]}({','.join(tptp(a) for a in t[2])})"
    if k == "not":
        return f"~{_unit(t[1])}"
    if k in ("and", "or", "imp"):
        op = {"and": "&", "or": "|", "imp": "=>"}[k]
        return f"({tptp(t[1])} {op} {tptp(t[2])})"
    if k in ("forall", "exists"):
        q = "!" if k == "forall" else "?"
        return f"{q} [{t[1]}] : {_unit(t[2])}"
    raise ValueError(f"unknown formula node {k!r}")


def _unit(t):
    """A sub-formula printed so that it can follow ~ or a quantifier's colon."""
    s = tptp(t)
    if t[0] == "pred" or s.startswith("("):
        return s
    return f"({s})"


def canon(t):
    """Rename bound variables V1, V2, ... in order of binding, so alpha-equivalent formulas print identically."""
    counter = itertools.count(1)

    def go(t, env):
        k = t[0]
        if k == "var":
            return ("var", env.get(t[1], t[1]))
        if k == "const":
            return t
        if k == "pred":
            return ("pred", t[1], tuple(go(a, env) for a in t[2]))
        if k == "not":
            return ("not", go(t[1], env))
        if k in ("and", "or", "imp"):
            return (k, go(t[1], env), go(t[2], env))
        v = f"V{next(counter)}"
        return (k, v, go(t[2], {**env, t[1]: v}))

    return go(t, {})


def symbols(t):
    """(constants, {predicate: arity}) occurring in a formula."""
    consts, preds = set(), {}

    def go(t):
        k = t[0]
        if k == "const":
            consts.add(t[1])
        elif k == "pred":
            preds[t[1]] = len(t[2])
            for a in t[2]:
                go(a)
        elif k == "not":
            go(t[1])
        elif k in ("and", "or", "imp"):
            go(t[1]); go(t[2])
        elif k in ("forall", "exists"):
            go(t[2])

    go(t)
    return consts, preds


def free_variables(t, bound=frozenset()):
    k = t[0]
    if k == "var":
        return set() if t[1] in bound else {t[1]}
    if k == "const":
        return set()
    if k == "pred":
        return set().union(*(free_variables(a, bound) for a in t[2])) if t[2] else set()
    if k == "not":
        return free_variables(t[1], bound)
    if k in ("and", "or", "imp"):
        return free_variables(t[1], bound) | free_variables(t[2], bound)
    return free_variables(t[2], bound | {t[1]})


# ---------------------------------------------------------------- reading (TPTP or the spec's notation)

class FormulaSyntaxError(ValueError):
    pass


_TOKEN = re.compile(r"\s*(<=>|=>|->|[!?]|\[|\]|:|\(|\)|,|&|\||~|[A-Za-z_][A-Za-z0-9_]*)")


def _tokenize(s):
    toks, pos = [], 0
    s = s.rstrip()
    while pos < len(s):
        m = _TOKEN.match(s, pos)
        if not m:
            raise FormulaSyntaxError(f"unexpected character {s[pos:].strip()[:1]!r} at position {pos}")
        toks.append(m.group(1))
        pos = m.end()
    return toks


def parse_formula(s):
    """Read a closed first-order formula.

    Accepted notations (they may not be mixed within one quantifier, but otherwise freely):
      TPTP:           ! [X] : (p(X) => ? [Y,Z] : (q(Y) & r(X,Z)))     ~  &  |  =>  <=>
      the spec's own: forall x (p(x) -> exists y (q(y) & r(x,y)))

    Precedence, tightest first: ~ and quantifiers (whose scope is the next unit), then &, then |,
    then => / -> (right-associative) and <=>. A name is a variable exactly when an enclosing
    quantifier binds it; any other name in argument position is a constant. Free variables are an error.
    """
    toks = _tokenize(s)
    if not toks:
        raise FormulaSyntaxError("empty formula")
    pos = 0

    def peek():
        return toks[pos] if pos < len(toks) else None

    def take(expected=None):
        nonlocal pos
        if pos >= len(toks):
            raise FormulaSyntaxError(f"formula ends early" + (f"; expected {expected!r}" if expected else ""))
        x = toks[pos]
        if expected is not None and x != expected:
            raise FormulaSyntaxError(f"expected {expected!r} but found {x!r}")
        pos += 1
        return x

    def name():
        x = take()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", x):
            raise FormulaSyntaxError(f"expected a name but found {x!r}")
        return x

    def implication(bound):
        left = disjunction(bound)
        if peek() in ("=>", "->"):
            take()
            return ("imp", left, implication(bound))
        if peek() == "<=>":
            take()
            right = disjunction(bound)
            return ("and", ("imp", left, right), ("imp", right, left))
        return left

    def disjunction(bound):
        left = conjunction(bound)
        while peek() == "|":
            take(); left = ("or", left, conjunction(bound))
        return left

    def conjunction(bound):
        left = unit(bound)
        while peek() == "&":
            take(); left = ("and", left, unit(bound))
        return left

    def quantified(kind, variables, bound):
        body = unit(bound | set(variables))
        for v in reversed(variables):
            body = (kind, v, body)
        return body

    def unit(bound):
        t = peek()
        if t is None:
            raise FormulaSyntaxError("formula ends early")
        if t == "~":
            take(); return ("not", unit(bound))
        if t in ("!", "?"):
            take(); take("[")
            vs = [name()]
            while peek() == ",":
                take(); vs.append(name())
            take("]"); take(":")
            return quantified("forall" if t == "!" else "exists", vs, bound)
        if t in ("forall", "exists") and pos + 1 < len(toks) and re.fullmatch(r"[A-Za-z_]\w*", toks[pos + 1]):
            take()
            return quantified(t, [name()], bound)
        if t == "(":
            take(); e = implication(bound); take(")")
            return e
        p = name()
        if peek() != "(":
            raise FormulaSyntaxError(f"{p!r} is used as a formula; atoms need arguments, e.g. {p}(X)")
        take("(")
        args = [term(bound)]
        while peek() == ",":
            take(); args.append(term(bound))
        take(")")
        return ("pred", p, tuple(args))

    def term(bound):
        n = name()
        if n in bound:
            return ("var", n)
        if n[0].isupper():
            raise FormulaSyntaxError(f"variable {n} is not bound by any quantifier")
        return ("const", n)

    f = implication(frozenset())
    if pos != len(toks):
        raise FormulaSyntaxError(f"unexpected {toks[pos]!r} after the end of the formula")
    return f


# ---------------------------------------------------------------- models and evaluation

class ModelError(ValueError):
    pass


def model_from_json(m, signature=None):
    """Turn the JSON form {"D": [...], "tam": "a", "walks": ["a"], "sees": [["a","b"]]} into a model,
    checking it. If `signature` ({"consts": set, "preds": {name: arity}}) is given, every symbol in it
    must be interpreted and no other symbol may appear."""
    if not isinstance(m, dict):
        raise ModelError("a model must be a JSON object")
    D = m.get("D")
    if not isinstance(D, list) or not D or not all(isinstance(d, str) for d in D):
        raise ModelError('"D" must be a non-empty list of element names (strings)')
    if len(set(D)) != len(D):
        raise ModelError('"D" lists an element twice')
    dom = set(D)
    consts, preds = {}, {}
    for k, v in m.items():
        if k == "D":
            continue
        if isinstance(v, str):
            if v not in dom:
                raise ModelError(f"constant {k} denotes {v!r}, which is not in D")
            consts[k] = v
        elif isinstance(v, list):
            ext = set()
            for e in v:
                if isinstance(e, str):
                    if e not in dom:
                        raise ModelError(f"{k} contains {e!r}, which is not in D")
                    ext.add(e)
                elif isinstance(e, list) and len(e) == 2 and all(isinstance(x, str) for x in e):
                    if not set(e) <= dom:
                        raise ModelError(f"{k} contains {e}, which is not a pair of elements of D")
                    ext.add(tuple(e))
                else:
                    raise ModelError(f"{k} contains {e!r}; expected an element or a pair [x, y]")
            kinds = {type(e) for e in ext}
            if len(kinds) > 1:
                raise ModelError(f"{k} mixes elements and pairs")
            preds[k] = ext
        else:
            raise ModelError(f"{k}: expected an element name or a list, found {type(v).__name__}")
    model = {"D": list(D), "consts": consts, "preds": preds}
    if signature is not None:
        check_signature(model, signature)
    return model


def check_signature(model, signature):
    missing = [c for c in sorted(signature["consts"]) if c not in model["consts"]]
    missing += [p for p in sorted(signature["preds"]) if p not in model["preds"]]
    if missing:
        raise ModelError("the model does not interpret " + ", ".join(missing))
    extra = [k for k in list(model["consts"]) + list(model["preds"])
             if k not in signature["consts"] and k not in signature["preds"]]
    if extra:
        raise ModelError("the model interprets symbols that are not in the lexicon: " + ", ".join(sorted(extra)))
    for p, arity in signature["preds"].items():
        ext = model["preds"][p]
        if ext and any((isinstance(e, tuple) and len(e) == 2) != (arity == 2) for e in ext):
            raise ModelError(f"{p} has arity {arity}, but its extension has the wrong shape")


def model_to_json(m):
    """The inverse of model_from_json, with sorted extensions (deterministic output)."""
    out = {"D": list(m["D"])}
    out.update({c: v for c, v in m["consts"].items()})
    for p, ext in m["preds"].items():
        out[p] = [list(e) if isinstance(e, tuple) else e for e in sorted(ext)]
    return out


def holds(t, m, env=None):
    """Truth of formula t in model m under the variable assignment env. Exact; raises KeyError on a symbol
    the model does not interpret (callers that take outside input validate the model first)."""
    env = env or {}
    k = t[0]
    if k == "pred":
        args = tuple(env[a[1]] if a[0] == "var" else m["consts"][a[1]] for a in t[2])
        return (args[0] if len(args) == 1 else args) in m["preds"][t[1]]
    if k == "not":
        return not holds(t[1], m, env)
    if k == "and":
        return holds(t[1], m, env) and holds(t[2], m, env)
    if k == "or":
        return holds(t[1], m, env) or holds(t[2], m, env)
    if k == "imp":
        return (not holds(t[1], m, env)) or holds(t[2], m, env)
    if k == "forall":
        return all(holds(t[2], m, {**env, t[1]: d}) for d in m["D"])
    if k == "exists":
        return any(holds(t[2], m, {**env, t[1]: d}) for d in m["D"])
    raise ValueError(f"unknown formula node {k!r}")
