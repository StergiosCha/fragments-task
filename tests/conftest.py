import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "generator"))

import prover  # noqa: E402

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def pytest_collection_modifyitems(config, items):
    """Tests marked `ladr` need the real Prover9/Mace4. They are skipped when LADR is missing, except in CI
    (FRAGMENTS_REQUIRE_LADR=1), where a missing LADR is a failure."""
    if prover.ladr_available():
        return
    if os.environ.get("FRAGMENTS_REQUIRE_LADR") == "1":
        raise pytest.UsageError("FRAGMENTS_REQUIRE_LADR=1 but prover9/mace4 were not found")
    skip = pytest.mark.skip(reason="Prover9/Mace4 not installed (see docs/LADR.md)")
    for item in items:
        if "ladr" in item.keywords:
            item.add_marker(skip)
