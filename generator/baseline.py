#!/usr/bin/env python3
"""Prompting baseline: the four specification files in the context, one request per item, one JSON line per answer.

Works with any OpenAI-compatible chat-completions endpoint, hosted or local (vLLM, llama.cpp server, Ollama, ...):

  export FRAGMENTS_BASE_URL=http://localhost:8000/v1      # the endpoint (required)
  export FRAGMENTS_MODEL=my-model                          # the model name (required)
  export FRAGMENTS_API_KEY=...                             # if the endpoint needs one
  python3 baseline.py --fragment ../fragments/practice_seed0 --out ../runs/practice-mymodel

This writes a submission directory (docs/SUBMISSION.md): <variant>.jsonl for each variant, submission.json, and
log/<variant>.jsonl with every prompt sent and every raw reply received. Re-running the same command resumes:
items already answered are skipped. --dry-run prints the first prompt and calls nothing.

Fixed settings, so that runs can be repeated: temperature 0 and seed 0 by default (--temperature, --seed); the
endpoint may or may not honour the seed. No examples are given by default (zero-shot); --shots takes examples
from another fragment, which must not share any word with the one being solved.
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

from validate import Variant, check_answer

VARIANTS = ["nonce", "english", "scrambled", "counter"]
SPEC_FILES = ["lexicon.txt", "grammar.txt", "semantics.txt", "models.json"]

INSTRUCTIONS = """You are given the complete specification of a small formal language: a lexicon, a grammar, compositional \
semantic rules mapping sentences to first-order logic, and finite models. Follow the specification exactly, even where \
it contradicts what the words look like. Answer each item with one JSON object and nothing else.

Answer formats:
 parse:     {"grammatical": true or false, "tree": "[S [NP ...] [VP ...]]"}      (give "tree" only if grammatical)
 interpret: {"lfs": ["<formula>", ...], "truth": [{"M1": true or false, ...}, ...]}  (one formula and one truth object per reading)
 infer:     {"label": "entailment" or "contradiction" or "neutral",
             "lfs": {"premises": ["<formula>", ...], "conclusion": "<formula>"},
             "certificate": {"proof": "<proof>"} for entailment or contradiction,
                            {"models": [<model>, <model>]} for neutral: two models of the premises, the conclusion
                            true in one and false in the other, written like the models in models.json}
Formulas are in TPTP syntax: ! [X] : (...) for all, ? [X] : (...) there is, ~ & | =>, upper-case variables,
names and predicates as in semantics.txt. Trees list each node's children in the order of the rules in grammar.txt."""


# ---------------------------------------------------------------- prompts

def spec_text(variant_dir):
    parts = []
    for name in SPEC_FILES:
        with open(os.path.join(variant_dir, name)) as f:
            parts.append(f"=== {name} ===\n{f.read().rstrip()}")
    return "\n\n".join(parts)


def item_text(item):
    return "Item: " + json.dumps({k: v for k, v in item.items() if k != "id"})


def words_of_lexicon(variant_dir):
    with open(os.path.join(variant_dir, "lexicon.txt")) as f:
        return {w.strip() for line in f for w in line.split(":", 1)[-1].split(",") if w.strip()}


def shots_text(shot_dir, k):
    """k examples per item type from another fragment's variant, with their gold answers."""
    with open(os.path.join(shot_dir, "items.jsonl")) as f:
        items = [json.loads(l) for l in f]
    with open(os.path.join(shot_dir, "gold", "gold_as_submission.jsonl")) as f:
        gold = {g["id"]: g for g in map(json.loads, f)}
    out = []
    for kind in ("parse", "interpret", "infer"):
        for it in [i for i in items if i["type"] == kind][:k]:
            answer = {key: val for key, val in gold[it["id"]].items() if key != "id"}
            out.append(f"{item_text(it)}\nAnswer: {json.dumps(answer)}")
    return ("EXAMPLES FROM A DIFFERENT FRAGMENT (its own specification follows the examples' words, not yours):\n\n"
            + spec_text(shot_dir) + "\n\n" + "\n\n".join(out))


def system_prompt(variant_dir, shot_dir=None, k=2):
    parts = [INSTRUCTIONS, "SPECIFICATION\n\n" + spec_text(variant_dir)]
    if shot_dir:
        parts.append(shots_text(shot_dir, k))
    return "\n\n".join(parts)


# ---------------------------------------------------------------- the endpoint

class Endpoint:
    """A minimal client for an OpenAI-compatible /chat/completions endpoint (standard library only)."""

    def __init__(self, base_url, model, api_key=None, temperature=0.0, seed=0, max_tokens=2000,
                 retries=5, backoff=2.0, timeout=300):
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.model, self.api_key = model, api_key
        self.temperature, self.seed, self.max_tokens = temperature, seed, max_tokens
        self.retries, self.backoff, self.timeout = retries, backoff, timeout

    def request_body(self, system, user):
        return {"model": self.model, "temperature": self.temperature, "seed": self.seed, "max_tokens": self.max_tokens,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}

    def complete(self, body):
        """The reply text, retrying on rate limits, server errors and network errors."""
        data = json.dumps(body).encode()
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        for attempt in range(self.retries + 1):
            try:
                req = urllib.request.Request(self.url, data=data, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    reply = json.loads(r.read().decode())
                return reply["choices"][0]["message"]["content"] or ""
            except urllib.error.HTTPError as e:
                if e.code not in (408, 409, 429) and e.code < 500 or attempt == self.retries:
                    raise RuntimeError(f"HTTP {e.code} from {self.url}: {e.read().decode(errors='replace')[:500]}")
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                if attempt == self.retries:
                    raise RuntimeError(f"cannot reach {self.url}: {e}")
            time.sleep(self.backoff * 2 ** attempt)


# ---------------------------------------------------------------- answers

def extract_answer(text):
    """The first JSON object in the reply (models often wrap it in prose or ``` fences), or {} if there is none."""
    dec = json.JSONDecoder()
    for start in (i for i, ch in enumerate(text) if ch == "{"):
        try:
            obj, _ = dec.raw_decode(text, start)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    return {}


def run_variant(endpoint, variant_dir, out_dir, shot_dir=None, k=2, limit=None, log=print):
    """Answer every item of one variant, appending to <out>/<variant>.jsonl and its log; resumes if re-run."""
    name = os.path.basename(os.path.normpath(variant_dir))
    variant = Variant(variant_dir, with_gold=False)
    sub_path = os.path.join(out_dir, f"{name}.jsonl")
    log_path = os.path.join(out_dir, "log", f"{name}.jsonl")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    done = set()
    if os.path.exists(sub_path):
        with open(sub_path) as f:
            done = {json.loads(l)["id"] for l in f if l.strip()}
    system = system_prompt(variant_dir, shot_dir, k)
    todo = [i for i in variant.items.values() if i["id"] not in done][:limit]
    with open(sub_path, "a") as sub, open(log_path, "a") as lg:
        for n, item in enumerate(todo, 1):
            body = endpoint.request_body(system, item_text(item) + "\nAnswer:")
            reply = endpoint.complete(body)
            answer = extract_answer(reply)
            try:
                check_answer({"id": item["id"], **answer}, item, variant)
                problem = None
            except ValueError as e:
                problem = str(e)
            lg.write(json.dumps({"id": item["id"], "request": body, "reply": reply, "answer": answer,
                                 "format_problem": problem}) + "\n")
            sub.write(json.dumps({**answer, "id": item["id"]}) + "\n")
            sub.flush(); lg.flush()
            log(f"{name}: {len(done) + n}/{len(variant.items)} (item {item['id']}{', format problem' if problem else ''})")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fragment", required=True, help="fragment directory with nonce/, english/, scrambled/, counter/")
    ap.add_argument("--out", required=True, help="submission directory to write (created if missing)")
    ap.add_argument("--variants", nargs="+", default=VARIANTS, choices=VARIANTS)
    ap.add_argument("--shots", help="variant directory of a DIFFERENT fragment to take examples from (default: none)")
    ap.add_argument("--k", type=int, default=2, help="examples per item type with --shots")
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--max-tokens", type=int, default=2000)
    ap.add_argument("--limit", type=int, help="answer at most this many items per variant (for trying things out)")
    ap.add_argument("--dry-run", action="store_true", help="print the first prompt and exit")
    a = ap.parse_args()

    if a.shots:
        shared = words_of_lexicon(a.shots) & set().union(*(words_of_lexicon(os.path.join(a.fragment, v)) for v in a.variants))
        if shared:
            sys.exit(f"--shots shares words with the fragment ({', '.join(sorted(shared)[:5])}...): its examples would "
                     "give away answers or contradict the specification. Use a fragment with a different lexicon.")
    if a.dry_run:
        first_dir = os.path.join(a.fragment, a.variants[0])
        item = Variant(first_dir, with_gold=False).items
        print(system_prompt(first_dir, a.shots, a.k))
        print("\n--- user ---\n" + item_text(next(iter(item.values()))) + "\nAnswer:")
        return

    base_url, model = os.environ.get("FRAGMENTS_BASE_URL"), os.environ.get("FRAGMENTS_MODEL")
    if not base_url or not model:
        sys.exit("set FRAGMENTS_BASE_URL (an OpenAI-compatible endpoint, e.g. http://localhost:8000/v1) and FRAGMENTS_MODEL")
    endpoint = Endpoint(base_url, model, os.environ.get("FRAGMENTS_API_KEY"), a.temperature, a.seed, a.max_tokens)
    os.makedirs(a.out, exist_ok=True)
    meta = {"team": "organisers", "system": f"prompting baseline: {model}, {'zero-shot' if not a.shots else f'{a.k}-shot'}",
            "track": "model-alone", "system_type": "prompted-model",
            "settings": {"model": model, "temperature": a.temperature, "seed": a.seed, "max_tokens": a.max_tokens,
                         "shots": a.shots, "k": a.k if a.shots else 0}}
    with open(os.path.join(a.out, "submission.json"), "w") as f:
        json.dump(meta, f, indent=1)
    for v in a.variants:
        run_variant(endpoint, os.path.join(a.fragment, v), a.out, a.shots, a.k, a.limit)
    print(f"wrote {a.out}; score it with: python3 score.py --fragment {a.fragment} --submission {a.out}")


if __name__ == "__main__":
    main()
