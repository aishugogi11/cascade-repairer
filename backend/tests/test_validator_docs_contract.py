"""Docs-contract tests from the Phase 2 validation report.

These read repo-root files (README.md, Makefile, jupyter_notebook/Dockerfile,
AGENTS.md) that sit outside the backend image's build context, so per TODO.md
D4 (Option A) every test here skips inside the CI container and only runs from
a full checkout.
"""
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
README = REPO_ROOT / "README.md"
MAKEFILE = REPO_ROOT / "Makefile"
JUPYTER_DOCKERFILE = REPO_ROOT / "jupyter_notebook" / "Dockerfile"
AGENTS_MD = REPO_ROOT / "AGENTS.md"

pytestmark = pytest.mark.skipif(
    not README.exists(),
    reason="repo-root files absent (running inside the backend image)",
)

# Matches ?token=<value> in documented Jupyter URLs.
TOKEN_RE = re.compile(r"\?token=([A-Za-z0-9_-]+)")


def test_readme_jupyter_token_matches_dockerfile():
    match = re.search(
        r"--IdentityProvider\.token=([A-Za-z0-9_-]+)",
        JUPYTER_DOCKERFILE.read_text(),
    )
    assert match, "no --IdentityProvider.token=... in jupyter_notebook/Dockerfile"
    served_token = match.group(1)

    readme_tokens = set(TOKEN_RE.findall(README.read_text()))
    makefile_tokens = set(TOKEN_RE.findall(MAKEFILE.read_text()))
    assert readme_tokens == {served_token}, (
        f"README documents token(s) {readme_tokens}, Dockerfile serves {served_token!r}"
    )
    assert makefile_tokens == {served_token}, (
        f"Makefile documents token(s) {makefile_tokens}, Dockerfile serves {served_token!r}"
    )


# Markdown inline links: capture the target up to a ')' or '#' anchor.
MD_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)#\s]+)[^)]*\)")


def test_readme_relative_links_exist():
    targets = MD_LINK_RE.findall(README.read_text())
    local = [t for t in targets if not t.startswith(("http://", "https://", "mailto:"))]
    missing = [t for t in local if not (REPO_ROOT / t).exists()]
    assert not missing, f"README links to nonexistent local paths: {missing}"


def test_agents_md_has_required_sections_and_no_cloud_run_url():
    text = AGENTS_MD.read_text()
    for heading in (
        "## Branch Strategy",
        "## Constitution",
        "## Per-feature specs",
        "## Skills",
        "## Ideas inbox",
        "## Working agreements",
    ):
        assert heading in text, f"AGENTS.md missing section: {heading}"
    # Deployment specifics (Cloud Run service) belong in README, not agent rules.
    assert "vocal-bridge-be-dev" not in text
