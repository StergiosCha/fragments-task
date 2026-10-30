#!/usr/bin/env python3
"""Prompting baseline: the specification in context, few-shot from a practice variant, one call per item.

  OPENAI_BASE_URL=... OPENAI_API_KEY=... MODEL=... python3 baseline.py --variant out/seed1/nonce --practice out/seed0/nonce --out sub.jsonl
  (ANTHROPIC_API_KEY instead selects the Anthropic API.)

This script makes no API call unless the env vars are set; --dry-run prints the first prompt and exits.
"""
import argparse, json, os, sys

SPEC_FILES = ["lexicon.txt", "grammar.txt", "semantics.txt", "models.json"]

SYSTEM = """You are given the complete specification of a small formal language: a lexicon, a grammar, compositional semantic rules mapping sentences to first-order logic, and finite models. Follow the specification exactly, even where it contradicts what the words look like. Answer with one JSON object and nothing else.
Formats:
 parse:     {"grammatical": true|false, "tree": "[S [NP ...] [VP ...]]"}   (tree only if grammatical)
 interpret: {"lfs": ["<TPTP formula>", ...], "truth": [{"M1": true|false, ...}, ...]}   (one entry per reading)
 infer:     {"label": "entailment"|"contradiction"|"neutral", "lfs": {"premises": [...], "conclusion": "..."}, "certificate": {"proof": "..."} or {"models": [<model>, <model>]}}
"""


def spec_text(variant):
    return "\n".join(f"=== {f} ===\n" + open(os.path.join(variant, f)).read() for f in SPEC_FILES)


def fewshot(practice, k=2):
    items = list(map(json.loads, open(os.path.join(practice, "items.jsonl"))))
    gold = {g["id"]: g for g in map(json.loads, open(os.path.join(practice, "gold/gold_as_submission.jsonl")))}
    shots = []
    for kind in ["parse", "interpret", "infer"]:
        for it in [i for i in items if i["type"] == kind][:k]:
            q = {k2: v for k2, v in it.items() if k2 not in ("id",)}
            a = {k2: v for k2, v in gold[it["id"]].items() if k2 != "id"}
            shots.append(f"Item: {json.dumps(q)}\nAnswer: {json.dumps(a)}")
    return "\n\n".join(shots)


def call(prompt, system):
    if os.environ.get("ANTHROPIC_API_KEY"):
        import anthropic
        c = anthropic.Anthropic()
        r = c.messages.create(model=os.environ.get("MODEL", "claude-sonnet-5"), max_tokens=1500, system=system,
                              messages=[{"role": "user", "content": prompt}])
        return r.content[0].text
    if os.environ.get("OPENAI_API_KEY"):
        from openai import OpenAI
        c = OpenAI(base_url=os.environ.get("OPENAI_BASE_URL"))
        r = c.chat.completions.create(model=os.environ["MODEL"], messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}])
        return r.choices[0].message.content
    sys.exit("set ANTHROPIC_API_KEY or OPENAI_API_KEY (+MODEL) to run the baseline")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", required=True); ap.add_argument("--practice", required=True)
    ap.add_argument("--out", default="submission.jsonl"); ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    system = SYSTEM + "\n\nSPECIFICATION\n" + spec_text(a.variant) + "\n\nEXAMPLES FROM A PRACTICE FRAGMENT (different lexicon)\n" + fewshot(a.practice)
    items = list(map(json.loads, open(os.path.join(a.variant, "items.jsonl"))))
    if a.dry_run:
        print(system); print("Item:", json.dumps({k: v for k, v in items[0].items() if k != "id"})); return
    with open(a.out, "w") as f:
        for it in items:
            q = {k: v for k, v in it.items() if k != "id"}
            txt = call("Item: " + json.dumps(q) + "\nAnswer:", system)
            try: ans = json.loads(txt[txt.index("{"): txt.rindex("}") + 1])
            except Exception: ans = {}
            f.write(json.dumps({"id": it["id"], **ans}) + "\n")
    print("wrote", a.out)


if __name__ == "__main__":
    main()
