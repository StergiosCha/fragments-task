"""The prompting baseline, against a fake OpenAI-compatible server that answers with the gold."""
import http.server
import json
import os
import subprocess
import sys
import threading

import pytest

import baseline as B
import gen
import score as S
from validate import Variant

from conftest import REPO

SIZES = dict(n_parse=6, n_interp=6, n_infer=3)


@pytest.fixture(scope="module")
def frag(tmp_path_factory):
    root = tmp_path_factory.mktemp("frag")
    files, _ = gen.build_fragment(0, use_ladr=False, **SIZES)
    for p, s in files.items():
        gen.write(os.path.join(root, p), s)
    return root


class FakeServer:
    """Replies to each item with its gold answer, wrapped in prose; fails the first `fail_first` requests with 429."""

    def __init__(self, frag, fail_first=0):
        self.answers, self.requests, self.fail_left = {}, [], fail_first
        for v in gen.VARIANTS:
            items = [json.loads(l) for l in (frag / v / "items.jsonl").read_text().splitlines()]
            gold = {g["id"]: g for g in map(json.loads, (frag / v / "gold" / "gold_as_submission.jsonl").read_text().splitlines())}
            spec = B.spec_text(frag / v)               # nonce and counter items read the same: tell them apart
            for it in items:
                self.answers[(spec, B.item_text(it))] = {k: val for k, val in gold[it["id"]].items() if k != "id"}
        server = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                server.requests.append({"path": self.path, "auth": self.headers.get("Authorization"), "body": body})
                if server.fail_left > 0:
                    server.fail_left -= 1
                    self.send_response(429); self.end_headers(); self.wfile.write(b"slow down"); return
                user = body["messages"][1]["content"].rsplit("\nAnswer:", 1)[0]
                system = body["messages"][0]["content"]
                (answer,) = [a for (spec, it), a in server.answers.items() if it == user and spec in system]
                text = "Here is my answer:\n```json\n" + json.dumps(answer) + "\n```"
                out = json.dumps({"choices": [{"message": {"role": "assistant", "content": text}}]}).encode()
                self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
                self.wfile.write(out)

            def log_message(self, *args):
                pass

        self.httpd = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_port}/v1"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()


@pytest.fixture
def server(frag):
    s = FakeServer(frag)
    yield s
    s.close()


def endpoint(url, **kw):
    return B.Endpoint(url, "fake-model", api_key="k", backoff=0.01, **kw)


def test_prompt_contains_the_whole_specification(frag):
    system = B.system_prompt(frag / "counter")
    for name in B.SPEC_FILES:
        assert (frag / "counter" / name).read_text().strip() in system
    assert "EXAMPLES" not in system                         # zero-shot by default


def test_baseline_with_gold_answers_scores_100(frag, server, tmp_path):
    out = tmp_path / "run"
    for v in gen.VARIANTS:
        B.run_variant(endpoint(server.url), frag / v, out, log=lambda *_: None)
    for v in gen.VARIANTS:
        results, rep = S.score_variant(Variant(frag / v), (out / f"{v}.jsonl").read_text().splitlines(), use_ladr=False)
        assert rep.errors == []
        t = S.tally(results)
        assert all(t[m]["all"]["score"] in (100.0, None) for m in S.METRICS)


def test_requests_have_fixed_settings_and_are_logged(frag, server, tmp_path):
    out = tmp_path / "run"
    B.run_variant(endpoint(server.url, temperature=0.0, seed=7), frag / "nonce", out, log=lambda *_: None)
    req = server.requests[0]
    assert req["path"] == "/v1/chat/completions" and req["auth"] == "Bearer k"
    assert req["body"]["temperature"] == 0.0 and req["body"]["seed"] == 7 and req["body"]["model"] == "fake-model"
    logs = [json.loads(l) for l in (out / "log" / "nonce.jsonl").read_text().splitlines()]
    n_items = len((frag / "nonce" / "items.jsonl").read_text().splitlines())
    assert len(logs) == n_items
    assert logs[0]["request"]["messages"][0]["content"].startswith("You are given")
    assert "```json" in logs[0]["reply"] and logs[0]["format_problem"] is None


def test_resume_skips_answered_items(frag, server, tmp_path):
    out = tmp_path / "run"
    B.run_variant(endpoint(server.url), frag / "nonce", out, limit=3, log=lambda *_: None)
    assert len(server.requests) == 3
    B.run_variant(endpoint(server.url), frag / "nonce", out, log=lambda *_: None)
    lines = (out / "nonce.jsonl").read_text().splitlines()
    ids = [json.loads(l)["id"] for l in lines]
    assert len(ids) == len(set(ids)) == len((frag / "nonce" / "items.jsonl").read_text().splitlines())
    assert len(server.requests) == len(ids)


def test_retries_after_rate_limiting(frag, tmp_path):
    s = FakeServer(frag, fail_first=2)
    try:
        B.run_variant(endpoint(s.url), frag / "nonce", tmp_path / "run", limit=1, log=lambda *_: None)
        assert len(s.requests) == 3
    finally:
        s.close()


def test_gives_up_with_a_clear_message(frag, tmp_path):
    s = FakeServer(frag, fail_first=100)
    try:
        with pytest.raises(RuntimeError, match="HTTP 429"):
            B.run_variant(endpoint(s.url, retries=1), frag / "nonce", tmp_path / "run", limit=1, log=lambda *_: None)
    finally:
        s.close()


@pytest.mark.parametrize("text, expected", [
    ('{"grammatical": false}', {"grammatical": False}),
    ('Sure! ```json\n{"label": "neutral"}\n``` hope that helps {not json}', {"label": "neutral"}),
    ('The set {a, b} ... answer: {"grammatical": true, "tree": "[S]"}', {"grammatical": True, "tree": "[S]"}),
    ("no json here", {}),
])
def test_extract_answer(text, expected):
    assert B.extract_answer(text) == expected


def test_shots_must_come_from_a_fragment_with_other_words(frag, tmp_path):
    r = subprocess.run([sys.executable, "baseline.py", "--fragment", str(frag), "--out", str(tmp_path / "x"),
                        "--shots", str(frag / "nonce"), "--dry-run"], cwd=os.path.join(REPO, "generator"),
                       capture_output=True, text=True)
    assert r.returncode != 0 and "shares words" in r.stderr


def test_shots_from_another_fragment(frag, tmp_path):
    other = tmp_path / "other"
    files, _ = gen.build_fragment(5, use_ladr=False, **SIZES)
    for p, s in files.items():
        gen.write(os.path.join(other, p), s)
    system = B.system_prompt(frag / "nonce", other / "nonce", k=1)
    assert "EXAMPLES FROM A DIFFERENT FRAGMENT" in system and (other / "nonce" / "lexicon.txt").read_text().strip() in system


def test_dry_run_calls_nothing(frag, tmp_path):
    r = subprocess.run([sys.executable, "baseline.py", "--fragment", str(frag), "--out", str(tmp_path / "x"), "--dry-run"],
                       cwd=os.path.join(REPO, "generator"), capture_output=True, text=True, env={**os.environ,
                       "FRAGMENTS_BASE_URL": "http://127.0.0.1:9/v1", "FRAGMENTS_MODEL": "m"})
    assert r.returncode == 0 and "SPECIFICATION" in r.stdout and not (tmp_path / "x").exists()
