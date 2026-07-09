"""Skill-mirror sync test from the Phase 2 validation report.

Per TODO.md D3, this is a read-only comparison — a stale mirror fails the test
and is fixed by running `make copy-skills`, never by editing the mirror. Per
D4 (Option A) it skips inside the CI container, where repo-root dirs are
outside the backend build context.
"""
import filecmp
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE = REPO_ROOT / "skills" / "openai-agents-sdk"
MIRROR = REPO_ROOT / ".claude" / "skills" / "openai-agents-sdk"

pytestmark = pytest.mark.skipif(
    not SOURCE.exists(),
    reason="repo-root skills/ absent (running inside the backend image)",
)


def _diffs(dcmp):
    problems = [
        (dcmp.left, name)
        for name in dcmp.left_only + dcmp.right_only + dcmp.diff_files
    ]
    for sub in dcmp.subdirs.values():
        problems.extend(_diffs(sub))
    return problems


def test_openai_agents_skill_mirror_matches_source():
    assert MIRROR.exists(), "mirror missing — run `make copy-skills`"
    problems = _diffs(filecmp.dircmp(SOURCE, MIRROR))
    assert not problems, (
        f"mirror out of sync with skills/ source: {problems} — run `make copy-skills`"
    )
