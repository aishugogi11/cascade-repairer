#!/usr/bin/env bash
# One-time provisioning for the Phase 8 web-call VB agent (AI Agent mode).
#
# Creates a Vocal Bridge agent per the L3 recipe
# (jupyter_notebook/training_course/L3/L3.ipynb, Step 4): AI Agent mode on,
# Background System off (they are mutually exclusive in VB), empty greeting
# (the backend agent owns identity), deploy target web. Prompt and ai-agent
# config are the checked-in assets under backend/api/assets/web_call/.
#
# Prereqs: the `vb` CLI on PATH (ships with the `vocal-bridge` package in
# backend/requirements.txt) and VOCAL_BRIDGE_API_KEY in the environment.
#
# Safe to re-run: each run CREATES a new agent and prints its id; it never
# mutates existing agents. After running, set the printed id where the
# backend reads it:
#
#   Cloud Run (merge semantics — survives redeploys):
#     gcloud run services update vocal-bridge-be-dev \
#       --region us-west1 \
#       --update-env-vars VOCAL_BRIDGE_WEB_AGENT_ID=<id>
#
#   Local dev: add VOCAL_BRIDGE_WEB_AGENT_ID=<id> to backend/.env
set -euo pipefail

ASSETS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../api/assets/web_call" && pwd)"

if [[ -z "${VOCAL_BRIDGE_API_KEY:-}" ]]; then
  echo "ERROR: VOCAL_BRIDGE_API_KEY is not set" >&2
  exit 1
fi

vb agent create \
  --name "vocal-bridge-web-call" \
  --style "Chatty" \
  --prompt-file "${ASSETS_DIR}/prompt.md" \
  --ai-agent-file "${ASSETS_DIR}/ai-agent.json" \
  --background-enabled false \
  --greeting "" \
  --deploy-targets web \
  --json

echo
echo "Set the agent id from the JSON above as VOCAL_BRIDGE_WEB_AGENT_ID (see header)."
