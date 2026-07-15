#!/bin/bash
#
# Commit -> push -> open PR into dev -> merge it -> pull latest dev.
#
# Works from whatever branch you're on. Usage:
#   ./git_pull_dev.sh                 # default commit message
#   ./git_pull_dev.sh "my message"    # custom commit message / PR title
#
set -euo pipefail

MERGE_METHOD="--merge"   # or --squash / --rebase (must be enabled on the repo)
# --admin bypasses branch-protection requirements and merges immediately (needs
# admin rights) so the pull in step 4 reflects the merge. Swap for --auto to
# instead queue the merge until required checks pass (won't merge right now).
MERGE_EXTRA="--admin"

# Base branch to integrate into. Resolution order:
#   1. BASE_BRANCH env var, if you set one:  BASE_BRANCH=main ./git_pull_dev.sh
#   2. the repo's default branch, via gh
#   3. the repo's default branch, via git (origin/HEAD)
if [ -n "${BASE_BRANCH:-}" ]; then
  :
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

# 1. Commit any pending changes on the current branch.
git add -A
if git diff --cached --quiet; then
  echo "==> No staged changes to commit."
else
  echo "==> Committing on ${CURRENT_BRANCH}: ${COMMIT_MSG}"
  git commit -m "${COMMIT_MSG}"
fi

# 2. Push the current branch to GitHub (creating the upstream if needed).
echo "==> Pushing ${CURRENT_BRANCH} to origin"
git push -u origin "${CURRENT_BRANCH}"

# 3. Open (or reuse) a PR into dev, then merge it.
if [ "${CURRENT_BRANCH}" = "${BASE_BRANCH}" ]; then
  echo "==> On ${BASE_BRANCH}; skipping PR/merge (a branch can't PR into itself)."
else
  if gh pr view "${CURRENT_BRANCH}" >/dev/null 2>&1; then
    echo "==> Reusing existing PR for ${CURRENT_BRANCH}"
  else
    echo "==> Opening PR: ${CURRENT_BRANCH} -> ${BASE_BRANCH}"
    gh pr create --base "${BASE_BRANCH}" --head "${CURRENT_BRANCH}" --fill
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
echo "==> Syncing ${BASE_BRANCH} from origin"
git checkout "${BASE_BRANCH}"
git pull origin "${BASE_BRANCH}"

echo "==> Done."
