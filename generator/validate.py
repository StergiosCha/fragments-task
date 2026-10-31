#!/usr/bin/env python3
"""Check a submission file against the submission format (docs/SUBMISSION.md) before scoring it.

  python3 validate.py --variant ../fragments/practice_seed0/nonce --submission my_nonce.jsonl

Prints every problem with its line number. Exit status 0 if the file can be scored as it is, 1 if not.
`errors` are lines that cannot be scored, which count as unanswered; `warnings` (missing items, unknown
fields) do not stop scoring.
"""
import argparse
import json
import os
import sys
from dataclasses import dataclass, field

import logic as L
from check_gold import read_spec
from prover import signature_of

LABELS = ("entailment", "contradiction", "neutral")
FIELDS = {"parse": {"id", "grammatical", "tree"},
          "interpret": {"id", "lfs", "truth"},
          "infer": {"id", "label", "lfs", "certificate"}}


@dataclass
class Report:
    answers: dict = field(default_factory=dict)       # id -> parsed answer (only lines without errors)
    errors: list = field(default_factory=list)        # (line number or None, message)
    warnings: list = field(default_factory=list)

    def error(self, line, msg):
        self.errors.append((line, msg))

    def warn(self, line, msg):
        self.warnings.append((line, msg))

    def lines(self):
        fmt = lambda kind, ln, msg: f"{kind} line {ln}: {msg}" if ln else f"{kind}: {msg}"
        return [fmt("error", *e) for e in self.errors] + [fmt("warning", *w) for w in self.warnings]


class Variant:
    """Everything the validator and scorer need to know about one variant of a fragment."""

    def __init__(self, path, with_gold=True):
        self.path = str(path)
        self.name = os.path.basename(os.path.normpath(self.path))
        self.lex, self.order = read_spec(self.path)
        self.signature = signature_of(self.lex)
        self.items = {i["id"]: i for i in _jsonl(os.path.join(self.path, "items.jsonl"))}
        self.released = _models(os.path.join(self.path, "models.json"))
        if with_gold:
            self.gold = {g["id"]: g for g in _jsonl(os.path.join(self.path, "gold", "gold.jsonl"))}
            self.hidden = _models(os.path.join(self.path, "gold", "models_hidden.json"))


def _jsonl(path):
    with open(path) as f:
        return [json.loads(l) for l in f if l.strip()]


def _models(path):
    with open(path) as f:
        return {name: L.model_from_json(m) for name, m in json.load(f).items()}


def check_formula(text, signature, what):
    """The parsed formula, or raise ValueError with a message naming `what`."""
    if not isinstance(text, str):
        raise ValueError(f"{what} must be a string, found {type(text).__name__}")
    try:
        f = L.parse_formula(text)
    except L.FormulaSyntaxError as e:
        raise ValueError(f"{what}: {e}")
    consts, preds = L.symbols(f)
    for c in sorted(consts - set(signature["consts"])):
        raise ValueError(f"{what}: {c!r} is not a proper name of the lexicon (variables must be bound)")
    for p, n in sorted(preds.items()):
        if p not in signature["preds"]:
            raise ValueError(f"{what}: {p!r} is not a predicate of the lexicon")
        if signature["preds"][p] != n:
            raise ValueError(f"{what}: {p} takes {signature['preds'][p]} argument(s), not {n}")
    return f


def check_answer(ans, item, variant):
    """Raise ValueError (with a participant-readable message) if the answer cannot be scored.
    Returns a list of warnings (problems that do not affect the score)."""
    kind = item["type"]
    warnings = []
    if kind == "parse":
        if not isinstance(ans.get("grammatical"), bool):
            raise ValueError('parse answers need "grammatical": true or false')
        if ans["grammatical"] and not isinstance(ans.get("tree"), str):
            raise ValueError('a grammatical parse answer needs "tree" as a string, e.g. "[S [NP [PN tam]] [VP [IV walks]]]"')
    elif kind == "interpret":
        lfs = ans.get("lfs")
        if not isinstance(lfs, list) or not lfs:
            raise ValueError('interpret answers need "lfs": a non-empty list of formulas, one per reading')
        for k, lf in enumerate(lfs):
            check_formula(lf, variant.signature, f"lfs[{k}]")
        # "truth" is asked for by the task page but is not scored at present (organisers' question), so a
        # malformed "truth" is only a warning.
        truth = ans.get("truth")
        if not isinstance(truth, list) or len(truth) != len(lfs):
            warnings.append('"truth" should be a list with one object per formula in "lfs", e.g. [{"M1": true, "M2": false}]')
        else:
            for k, row in enumerate(truth):
                if not isinstance(row, dict) or set(row) != set(variant.released) or \
                        not all(isinstance(v, bool) for v in row.values()):
                    warnings.append(f'truth[{k}] should give true/false for exactly the models {", ".join(sorted(variant.released))}')
    elif kind == "infer":
        if ans.get("label") not in LABELS:
            raise ValueError(f'"label" must be one of {", ".join(LABELS)}')
        lfs = ans.get("lfs")
        if not isinstance(lfs, dict) or not isinstance(lfs.get("premises"), list) or "conclusion" not in lfs:
            raise ValueError('infer answers need "lfs": {"premises": [...], "conclusion": "..."}')
        if len(lfs["premises"]) != len(item["premises"]):
            raise ValueError(f'"lfs.premises" has {len(lfs["premises"])} formula(s); the item has {len(item["premises"])} premise(s)')
        for k, p in enumerate(lfs["premises"]):
            check_formula(p, variant.signature, f"lfs.premises[{k}]")
        check_formula(lfs["conclusion"], variant.signature, "lfs.conclusion")
        cert = ans.get("certificate")
        if not isinstance(cert, dict):
            raise ValueError('infer answers need "certificate": {"proof": "..."} or {"models": [m1, m2]}')
        if ans["label"] == "neutral":
            ms = cert.get("models")
            if not isinstance(ms, list) or len(ms) != 2:
                raise ValueError('a neutral certificate is {"models": [m1, m2]}: two models of the premises')
            for k, m in enumerate(ms):
                try:
                    L.model_from_json(m, variant.signature)
                except L.ModelError as e:
                    raise ValueError(f"certificate.models[{k}]: {e}")
        elif not isinstance(cert.get("proof"), str) or not cert["proof"].strip():
            raise ValueError(f'an {ans["label"]} certificate is {{"proof": "..."}} with a non-empty proof')
    return warnings


TRACKS = ("model-alone", "model-with-tools")
SYSTEM_TYPES = ("prompted-model", "prover-loop", "program-synthesis", "neuro-symbolic", "fine-tuned")


def validate_metadata(path):
    """(metadata, problems) for a submission directory's submission.json (see docs/SUBMISSION.md)."""
    if not os.path.exists(path):
        return {}, ["missing: every submission declares its track and system type in submission.json"]
    try:
        with open(path) as f:
            meta = json.load(f)
    except json.JSONDecodeError as e:
        return {}, [f"not valid JSON ({e.msg} at line {e.lineno})"]
    if not isinstance(meta, dict):
        return {}, ["must be one JSON object"]
    problems = []
    for key in ("team", "system"):
        if not isinstance(meta.get(key), str) or not meta[key].strip():
            problems.append(f'"{key}" must be a non-empty string')
    if meta.get("track") not in TRACKS:
        problems.append(f'"track" must be one of {", ".join(TRACKS)}')
    if meta.get("system_type") not in SYSTEM_TYPES:
        problems.append(f'"system_type" must be one of {", ".join(SYSTEM_TYPES)}')
    return meta, problems


def validate(lines, variant):
    """Validate submission lines (strings) against a variant. Returns a Report."""
    rep = Report()
    seen = set()                                       # ids that appeared on some line, valid or not
    for n, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            ans = json.loads(line)
        except json.JSONDecodeError as e:
            rep.error(n, f"not valid JSON ({e.msg} at column {e.colno})")
            continue
        if not isinstance(ans, dict):
            rep.error(n, "each line must be one JSON object")
            continue
        i = ans.get("id")
        if not isinstance(i, int) or isinstance(i, bool):
            rep.error(n, '"id" must be the integer id of an item')
            continue
        if i not in variant.items:
            rep.error(n, f"there is no item with id {i}")
            continue
        if i in seen:
            rep.error(n, f"item {i}: answered more than once; only the first answer is used")
            continue
        seen.add(i)
        item = variant.items[i]
        try:
            for w in check_answer(ans, item, variant):
                rep.warn(n, f"item {i}: {w}")
        except ValueError as e:
            rep.error(n, f"item {i}: {e}")
            continue
        rep.answers[i] = ans
        extra = set(ans) - FIELDS[item["type"]]
        if extra:
            rep.warn(n, f"item {i}: fields {', '.join(sorted(extra))} are not part of a {item['type']} answer and are ignored")
    missing = sorted(set(variant.items) - seen)
    if missing:
        shown = ", ".join(map(str, missing[:20])) + (" ..." if len(missing) > 20 else "")
        rep.warn(None, f"{len(missing)} item(s) not answered (scored as wrong): {shown}")
    return rep


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--variant", required=True, help="variant directory (with lexicon.txt, items.jsonl, ...)")
    ap.add_argument("--submission", required=True, help="JSON-lines submission for that variant")
    a = ap.parse_args()
    v = Variant(a.variant, with_gold=False)
    with open(a.submission) as f:
        rep = validate(f.read().splitlines(), v)
    for line in rep.lines():
        print(line)
    print(f"{len(rep.answers)} of {len(v.items)} answers can be scored; "
          f"{len(rep.errors)} error(s), {len(rep.warnings)} warning(s)")
    sys.exit(1 if rep.errors else 0)


if __name__ == "__main__":
    main()
