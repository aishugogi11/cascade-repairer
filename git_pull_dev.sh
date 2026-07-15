#!/bin/bash
#
# Commit -> push -> open/update PR -> merge only with evidence -> sync dev.
#
# Works from whatever branch you're on. A one-argument feature-branch run
# commits, pushes, and opens a draft PR, then stops for independent validation.
# Add a non-placeholder "## Validation evidence" section in GitHub and re-run,
# or pass a body file on the second run to update, verify, and merge the PR.
#
# Usage:
#   ./git_pull_dev.sh                                      # on the base branch
#   ./git_pull_dev.sh "my message" /tmp/pr-body.md          # feature branch
#   PR_BODY_FILE=/tmp/pr-body.md ./git_pull_dev.sh "title" # equivalent
#   DRY_RUN=1 BASE_BRANCH=main ./git_pull_dev.sh "title" /tmp/pr-body.md
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

print_pr_body_help() {
  printf '%s\n' \
    "!!! Merging requires real validation output in the PR description." \
    "!!! Usage: ./git_pull_dev.sh \"commit / PR title\" /tmp/pr-body.md" \
    "!!! Or:    PR_BODY_FILE=/tmp/pr-body.md ./git_pull_dev.sh \"title\"" \
    "!!! Or edit the draft PR body in GitHub, then re-run the one-argument command." \
    "!!! Required body shape:" \
    "!!!   ## Summary" \
    "!!!   What changed and why." \
    "!!!" \
    "!!!   ## Validation evidence" \
    "!!!   Paste the commands, transcript, and output required by validation.md."
}

body_stream_has_evidence() {
  awk '
    BEGIN { in_evidence = 0; has_evidence = 0 }
    {
      normalized = tolower($0)
      if (normalized ~ /^##[[:space:]]+validation evidence([[:space:]].*)?$/) {
        in_evidence = 1
        next
      }
      if (in_evidence && normalized ~ /^##[[:space:]]+/) {
        in_evidence = 0
      }
      if (in_evidence) {
        line = normalized
        gsub(/^[[:space:]]+|[[:space:]]+$/, "", line)
        sub(/^[-*+>][[:space:]]*/, "", line)
        if (line != "" && line !~ /^```/ && line !~ /^<.*>$/ &&
            line !~ /^(todo|tbd|pending|add evidence here)([[:space:]].*)?[.!]?$/ &&
            line !~ /^paste([[:space:]].*)?here[.!]?$/) {
          has_evidence = 1
        }
      }
    }
    END { exit(has_evidence ? 0 : 1) }
  '
}

validate_pr_body_file() {
  local body_file="$1"
  if [ ! -f "${body_file}" ]; then
    echo "!!! PR body file not found: ${body_file}" >&2
    print_pr_body_help >&2
    return 1
  fi
  if ! grep -q '[^[:space:]]' "${body_file}"; then
    echo "!!! PR body file is empty: ${body_file}" >&2
    print_pr_body_help >&2
    return 1
  fi
  if ! body_stream_has_evidence < "${body_file}"; then
    echo "!!! PR body lacks a populated '## Validation evidence' section: ${body_file}" >&2
    print_pr_body_help >&2
    return 1
  fi
}

validate_pr_body_text() {
  local body_text="$1"
  if ! printf '%s\n' "${body_text}" | grep -q '[^[:space:]]'; then
    echo "!!! Refusing to merge a PR with an empty description." >&2
    print_pr_body_help >&2
    return 1
  fi
  if ! printf '%s\n' "${body_text}" | body_stream_has_evidence; then
    echo "!!! Refusing to merge: PR description lacks populated validation evidence." >&2
    print_pr_body_help >&2
    return 1
  fi
}

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
PR_BODY_FILE="${2:-${PR_BODY_FILE:-}}"

if [ "$#" -gt 2 ]; then
  echo "!!! Too many arguments." >&2
  print_pr_body_help >&2
  exit 2
fi

# Validate supplied evidence before staging or pushing. A new PR with no body
# file takes the draft/deferred path; an existing PR may reuse its valid body.
if [ "${CURRENT_BRANCH}" != "${BASE_BRANCH}" ] && [ -n "${PR_BODY_FILE}" ]; then
  validate_pr_body_file "${PR_BODY_FILE}"
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
  if [ -n "${PR_BODY_FILE}" ]; then
    echo "==> DRY RUN: PR body passed the validation-evidence guard"
    echo "==> DRY RUN: would create/update ${CURRENT_BRANCH} -> ${BASE_BRANCH}"
    echo "==> DRY RUN: would verify the remote PR body before merging"
    echo "==> DRY RUN: would mark a draft PR ready if needed"
    echo "==> DRY RUN: would merge with ${MERGE_METHOD} ${MERGE_EXTRA} and delete the branch"
  else
    echo "==> DRY RUN: would create/reuse a draft PR with validation pending"
    echo "==> DRY RUN: would stop before merge; re-run with a PR body file after validation"
    echo "==> Done (merge deferred)."
    exit 0
  fi
else
  if gh pr view "${CURRENT_BRANCH}" >/dev/null 2>&1; then
    echo "==> Reusing existing PR for ${CURRENT_BRANCH}"
    if [ -n "${PR_BODY_FILE}" ]; then
      echo "==> Updating PR description from ${PR_BODY_FILE}"
      gh pr edit "${CURRENT_BRANCH}" --body-file "${PR_BODY_FILE}"
    fi
  else
    echo "==> Opening PR: ${CURRENT_BRANCH} -> ${BASE_BRANCH}"
    if [ -n "${PR_BODY_FILE}" ]; then
      gh pr create \
        --base "${BASE_BRANCH}" \
        --head "${CURRENT_BRANCH}" \
        --title "${COMMIT_MSG}" \
        --body-file "${PR_BODY_FILE}"
    else
      PENDING_PR_BODY="$(printf '%s\n' \
        "## Summary" "" "${COMMIT_MSG}" "" \
        "## Validation evidence" "" \
        "Pending independent validation. Re-run this script with a populated PR body file before merge.")"
      gh pr create \
        --base "${BASE_BRANCH}" \
        --head "${CURRENT_BRANCH}" \
        --title "${COMMIT_MSG}" \
        --body "${PENDING_PR_BODY}" \
        --draft
      echo "==> Draft PR opened; merge deferred until independent validation evidence is supplied."
      echo "==> Re-run: ./git_pull_dev.sh \"${COMMIT_MSG}\" /tmp/pr-body.md"
      exit 0
    fi
  fi

  # Verify GitHub received the evidence-bearing description before any merge.
  REMOTE_PR_BODY="$(gh pr view "${CURRENT_BRANCH}" --json body --jq .body)"
  if ! validate_pr_body_text "${REMOTE_PR_BODY}"; then
    echo "==> Merge deferred. Add validation evidence, then re-run with the body file." >&2
    exit 0
  fi
  echo "==> PR description verified: populated validation evidence is present"

  if [ "$(gh pr view "${CURRENT_BRANCH}" --json isDraft --jq .isDraft)" = "true" ]; then
    echo "==> Marking validated draft PR ready for merge"
    gh pr ready "${CURRENT_BRANCH}"
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
