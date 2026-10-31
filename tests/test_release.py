"""Release hygiene: only public data is committed (docs/SEEDS.md), and the docs match the code."""
import os
import subprocess

import validate

from conftest import REPO

# test_seed1 has been public since the first commit; whether to rename or remove it is an open question for the
# organisers (docs/SEEDS.md). Nothing else but practice fragments may be committed.
ALLOWED_NON_PRACTICE = {"test_seed1"}


def tracked(path):
    out = subprocess.run(["git", "ls-files", path], cwd=REPO, capture_output=True, text=True, check=True).stdout
    return [l for l in out.splitlines() if l]


def test_only_practice_fragments_are_committed():
    folders = {p.split("/")[1] for p in tracked("fragments")}
    unexpected = sorted(f for f in folders if not f.startswith("practice_") and f not in ALLOWED_NON_PRACTICE)
    assert not unexpected, f"non-practice fragments committed: {unexpected} (see docs/SEEDS.md)"


def test_new_fragment_folders_are_ignored_by_git():
    out = subprocess.run(["git", "check-ignore", "-q", "fragments/test_seed99/nonce/items.jsonl"], cwd=REPO)
    assert out.returncode == 0
    out = subprocess.run(["git", "check-ignore", "-q", "fragments/practice_seed0/nonce/items.jsonl"], cwd=REPO)
    assert out.returncode == 1


def test_documented_tracks_and_system_types_are_the_validators():
    with open(os.path.join(REPO, "docs", "SUBMISSION.md")) as f:
        doc = f.read()
    for name in validate.TRACKS + validate.SYSTEM_TYPES:
        assert f"`{name}`" in doc


def test_task_page_examples_use_the_submission_format():
    """The draft task page once showed a singular "lf"; its examples must parse as submission lines."""
    with open(os.path.join(REPO, "lab-materials", "task_page.md")) as f:
        text = f.read()
    assert '"lf":' not in text
    assert '"lfs": ["' in text and '"truth": [{' in text


def test_participant_guide_links_resolve():
    for doc in ("PARTICIPANTS.md", "SUBMISSION.md", "LADR.md", "SEEDS.md"):
        assert os.path.exists(os.path.join(REPO, "docs", doc))
    with open(os.path.join(REPO, "docs", "PARTICIPANTS.md")) as f:
        assert "(SUBMISSION.md)" in f.read()
