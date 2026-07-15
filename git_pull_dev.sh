#!/bin/bash
#
# Commit -> push -> open/update PR -> evidence check -> merge it -> sync dev.
#
# Works from whatever branch you're on. The single optional argument is both
# the commit message and PR title.
#
# PR evidence guard (Phase 31 — a non-empty-only check let four phases merge
# with placeholder bodies): the merge is BLOCKED unless the PR description
# carries all three evidence sections and no auto-generated placeholder:
#   ### Mock walkthrough
#   ### Live run
#   ### Pytest
# Write them in PR_BODY.md at the repo root (gitignored) and this script uses
# it as the PR description verbatim; without that file a template with the
# three headings (and a placeholder notice that fails the guard until
# replaced) is generated. A hand-edited PR body on GitHub is never clobbered.
# SKIP_EVIDENCE=1 bypasses the check, loudly, for PRs with no runtime surface.
#
# Usage:
#   ./git_pull_dev.sh
#   ./git_pull_dev.sh "my commit message / PR title"
#   DRY_RUN=1 BASE_BRANCH=main ./git_pull_dev.sh "preview only"
#   SKIP_EVIDENCE=1 ./git_pull_dev.sh "chore: docs only"
#
# If someone invokes this Bash script as `sh git_pull_dev.sh`, re-enter Bash
# instead of relying on the host's /bin/sh implementation.
if [ -z "${BASH_VERSION:-}" ]; then
  exec bash "$0" "$@"
fi

set -euo pipefail

MERGE_METHOD="--merge"   # or --squash / --rebase (must be enabled on the repo)
# --admin bypasses branch-protection requirements and merges immediately (needs
# admin rights) so the pull in step 4 reflects the merge. Swap for --auto to
# instead queue the merge until required checks pass (won't merge right now).
MERGE_EXTRA="--admin"
DRY_RUN="${DRY_RUN:-0}"

# Base branch to integrate into. Resolution order:
#   1. BASE_BRANCH env var, if you set one:  BASE_BRANCH=main ./git_pull_dev.sh
#   2. vb/dev — this repo's integration branch (CI/CD deploys on push to it)
#   3. the repo's default branch, via gh
#   4. the repo's default branch, via git (origin/HEAD)
# gh/origin/HEAD resolve to `main` (the stable branch) in this checkout, and
# this script merges with --admin immediately, so vb/dev is pinned ahead of
# them; an explicit BASE_BRANCH= still wins, and the fallbacks remain in case
# the integration branch is ever renamed.
if [ -n "${BASE_BRANCH:-}" ]; then
  :
elif git show-ref --verify --quiet refs/remotes/origin/vb/dev; then
  BASE_BRANCH="vb/dev"
elif BASE_BRANCH="$(gh repo view --json defaultBranchRef --jq .defaultBranchRef.name 2>/dev/null)" \
     && [ -n "${BASE_BRANCH}" ]; then
  :
elif BASE_BRANCH="$(git symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null | sed 's#^origin/##')" \
     && [ -n "${BASE_BRANCH}" ]; then
  :
else
  echo "!!! Could not auto-detect the base branch. Set it explicitly:" >&2
  echo "!!!   BASE_BRANCH=your-branch ./git_pull_dev.sh" >&2
  exit 1
fi
echo "==> Base branch: ${BASE_BRANCH}"

CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
COMMIT_MSG="${1:-chore: sync work on ${CURRENT_BRANCH}}"

if [ "$#" -gt 1 ]; then
  echo "!!! Expected at most one argument: the commit message / PR title." >&2
  echo "!!! Usage: ./git_pull_dev.sh \"my commit message / PR title\"" >&2
  exit 2
fi

# The three sections the merge guard requires, and the placeholder marker
# that fails it until the template is actually filled in.
PLACEHOLDER_MARK="Placeholder description generated automatically"

if [ -f "PR_BODY.md" ]; then
  # The evidence draft (gitignored) is the PR description, verbatim.
  PR_BODY="$(cat PR_BODY.md)"
  BODY_SOURCE="PR_BODY.md"
  echo "==> PR description from PR_BODY.md"
else
  PR_BODY="$(printf '%s\n' \
    "## Summary" "" "${COMMIT_MSG}" "" \
    "### Mock walkthrough" "" "_fill in before merge_" "" \
    "### Live run" "" "_fill in before merge_" "" \
    "### Pytest" "" "_fill in before merge_" "" \
    "_${PLACEHOLDER_MARK} by git_pull_dev.sh — replace the fill-ins (or write PR_BODY.md) before merging._")"
  BODY_SOURCE="template"
fi

# 1. Commit any pending changes on the current branch.
if [ "${DRY_RUN}" = "1" ]; then
  echo "==> DRY RUN: would stage and commit changes as: ${COMMIT_MSG}"
else
  git add -A
  if git diff --cached --quiet; then
    echo "==> No staged changes to commit."
  else
    echo "==> Committing on ${CURRENT_BRANCH}: ${COMMIT_MSG}"
    git commit -m "${COMMIT_MSG}"
  fi
fi

# 2. Push the current branch to GitHub (creating the upstream if needed).
if [ "${DRY_RUN}" = "1" ]; then
  echo "==> DRY RUN: would push ${CURRENT_BRANCH} to origin"
else
  echo "==> Pushing ${CURRENT_BRANCH} to origin"
  git push -u origin "${CURRENT_BRANCH}"
fi

# 3. Open (or reuse) a PR into dev, then merge it.
if [ "${CURRENT_BRANCH}" = "${BASE_BRANCH}" ]; then
  echo "==> On ${BASE_BRANCH}; skipping PR/merge (a branch can't PR into itself)."
elif [ "${DRY_RUN}" = "1" ]; then
  echo "==> DRY RUN: would create/update ${CURRENT_BRANCH} -> ${BASE_BRANCH}"
  echo "==> DRY RUN: would set the PR description from ${BODY_SOURCE}"
  echo "==> DRY RUN: would mark a draft PR ready if needed"
  echo "==> DRY RUN: would check the PR body for the three evidence sections"
  echo "==> DRY RUN: would merge with ${MERGE_METHOD} ${MERGE_EXTRA} and delete the branch"
else
  if gh pr view "${CURRENT_BRANCH}" >/dev/null 2>&1; then
    echo "==> Reusing existing PR for ${CURRENT_BRANCH}"
    if [ "${BODY_SOURCE}" = "PR_BODY.md" ]; then
      echo "==> Updating PR title and description from PR_BODY.md"
      gh pr edit "${CURRENT_BRANCH}" --title "${COMMIT_MSG}" --body "${PR_BODY}"
    else
      # Never clobber a hand-written body with the template — this exact
      # clobber produced the placeholder-only bodies of PRs #53/#54
      # (Phase 31). Only an empty or still-placeholder body is replaced.
      EXISTING_BODY="$(gh pr view "${CURRENT_BRANCH}" --json body --jq .body)"
      if [ -z "${EXISTING_BODY}" ] \
         || printf '%s' "${EXISTING_BODY}" | grep -qF "${PLACEHOLDER_MARK}"; then
        echo "==> Updating PR title and template description"
        gh pr edit "${CURRENT_BRANCH}" --title "${COMMIT_MSG}" --body "${PR_BODY}"
      else
        echo "==> Updating PR title only (keeping the existing description)"
        gh pr edit "${CURRENT_BRANCH}" --title "${COMMIT_MSG}"
      fi
    fi
  else
    echo "==> Opening PR: ${CURRENT_BRANCH} -> ${BASE_BRANCH}"
    gh pr create \
      --base "${BASE_BRANCH}" \
      --head "${CURRENT_BRANCH}" \
      --title "${COMMIT_MSG}" \
      --body "${PR_BODY}"
  fi

  if [ "$(gh pr view "${CURRENT_BRANCH}" --json isDraft --jq .isDraft)" = "true" ]; then
    echo "==> Marking draft PR ready for merge"
    gh pr ready "${CURRENT_BRANCH}"
  fi

  # The evidence guard (Phase 31): no merge without the three evidence
  # sections in the PR body, and never with the placeholder still present.
  BODY_NOW="$(gh pr view "${CURRENT_BRANCH}" --json body --jq .body)"
  MISSING=""
  for section in "### Mock walkthrough" "### Live run" "### Pytest"; do
    if ! printf '%s' "${BODY_NOW}" | grep -qF "${section}"; then
      MISSING="${MISSING}    missing section: ${section}"$'\n'
    fi
  done
  if printf '%s' "${BODY_NOW}" | grep -qF "${PLACEHOLDER_MARK}"; then
    MISSING="${MISSING}    the auto-generated placeholder is still in the body"$'\n'
  fi
  if [ -n "${MISSING}" ]; then
    if [ "${SKIP_EVIDENCE:-0}" = "1" ]; then
      echo "==> WARNING: SKIP_EVIDENCE=1 — merging despite missing evidence:"
      printf '%s' "${MISSING}"
    else
      echo "!!! PR evidence guard: refusing to merge — the description lacks required evidence:" >&2
      printf '%s' "${MISSING}" >&2
      echo "!!! Write the evidence into PR_BODY.md (repo root, gitignored) and re-run this" >&2
      echo "!!! script, or edit the PR description on GitHub. SKIP_EVIDENCE=1 bypasses, loudly." >&2
      exit 1
    fi
  fi

  # GitHub may need a moment to compute mergeability after a fresh push/PR, so
  # retry a couple of times for that transient case.
  echo "==> Merging PR into ${BASE_BRANCH} (${MERGE_METHOD} ${MERGE_EXTRA})"
  merged=""
  for attempt in 1 2 3; do
    if gh pr merge "${CURRENT_BRANCH}" ${MERGE_METHOD} ${MERGE_EXTRA} --delete-branch; then
      merged="yes"
      break
    fi
    echo "    merge not ready (attempt ${attempt}); retrying in 3s..."
    sleep 3
  done
  if [ -z "${merged}" ]; then
    echo "!!! Could not merge automatically. Merge the PR manually on GitHub, then re-run."
    echo "!!! (Causes: not a repo admin so --admin can't bypass protection, a real"
    echo "!!!  merge conflict, or ${MERGE_METHOD#--} merges disabled on the repo.)"
  fi
fi

# 4. Pull the latest dev from origin (now includes the merge).
if [ "${DRY_RUN}" = "1" ]; then
  echo "==> DRY RUN: would sync ${BASE_BRANCH} from origin"
else
  echo "==> Syncing ${BASE_BRANCH} from origin"
  git checkout "${BASE_BRANCH}"
  git pull origin "${BASE_BRANCH}"
fi

echo "==> Done."
