"""Thin wrapper around the Vocal Bridge CLI (`vb`) for the L4 outbound-call
port (Phase 7).

Ported from jupyter_notebook/training_course/L4/helpers.py, reshaped to this
repo's helper-tuple convention (success, payload, error) so router code never
raises on a transport failure and never shells out directly. The `vb` binary
ships with the `vocal-bridge` package already pinned in requirements.txt and
authenticates via VOCAL_BRIDGE_API_KEY from the process env.

One deviation from the notebook: the notebook pins the caller agent once with
`vb agent use` on the learner's machine. Cloud Run containers are stateless,
so every call path re-pins VOCAL_BRIDGE_CALLER_AGENT_ID first.

All env is read per-call (the vb_test.py pattern) — importing this module
needs no credentials, no CLI, no network.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Optional, Tuple

logger = logging.getLogger(__name__)

_JSON_MARKER = "--- JSON ---"

CALLER_PROMPT_BASE_PATH = Path(__file__).parent / "assets" / "tool_caller_prompt_base.md"


def run_vb(
    *args: str,
    json_output: bool = False,
    timeout: int = 60,
) -> Tuple[bool, Any, Optional[str]]:
    """Run `vb <args>` and return (success, payload, error). With
    json_output=True the payload is the parsed JSON block the CLI prints
    after its human-readable table (anchored on the `--- JSON ---` marker,
    same as the L4 notebook)."""
    cmd = ["vb", *args]
    if json_output and "--json" not in args:
        cmd.append("--json")
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        return False, None, "vb CLI not found on PATH"
    except subprocess.TimeoutExpired:
        return False, None, f"vb {' '.join(args)} timed out after {timeout}s"

    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        return False, None, f"vb {' '.join(args)} failed: {detail}"

    out = proc.stdout
    if not json_output:
        return True, out, None
    if _JSON_MARKER in out:
        out = out.split(_JSON_MARKER, 1)[1]
    for i, ch in enumerate(out):
        if ch in "{[":
            try:
                return True, json.loads(out[i:]), None
            except json.JSONDecodeError as exc:
                return False, None, f"vb output JSON parse failed: {exc}"
    return False, None, "no JSON found in vb output"


def _pin_caller_agent() -> Tuple[bool, Optional[str]]:
    """Pin the configured caller agent for subsequent prompt/call commands."""
    agent_id = os.environ.get("VOCAL_BRIDGE_CALLER_AGENT_ID", "").strip()
    if not agent_id:
        return False, "VOCAL_BRIDGE_CALLER_AGENT_ID not set"
    ok, _, error = run_vb("agent", "use", agent_id)
    return ok, error


def set_caller_purpose(purpose: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """Inject the per-call purpose into the caller agent's prompt and push it
    via `vb prompt set`, exactly as the L4 notebook does. Returns
    (success, full_prompt, error)."""
    try:
        base = CALLER_PROMPT_BASE_PATH.read_text().rstrip()
    except OSError as exc:
        return False, None, f"caller prompt base unreadable: {exc}"
    full = (
        f"{base}\n\n"
        f"══════════════════════════════════════════════════════════\n"
        f"CONTEXT FOR THIS CALL\n"
        f"══════════════════════════════════════════════════════════\n\n"
        f"PURPOSE OF THIS CALL: {purpose}\n\n"
        f"Bring this up naturally in your first substantive turn.\n"
        f"Don't recite it verbatim — weave it in conversationally\n"
        f"once the callee has greeted you.\n"
    )
    with tempfile.NamedTemporaryFile(
        "w", suffix=".md", prefix="vb_caller_prompt_", delete=False
    ) as tmp:
        tmp.write(full)
        tmp_path = tmp.name
    try:
        ok, _, error = run_vb("prompt", "set", "-f", tmp_path)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
    if not ok:
        return False, None, error
    return True, full, None


def place_call(purpose: str, name: str | None = None) -> Tuple[bool, Optional[dict], Optional[str]]:
    """Pin the caller agent, inject the purpose, optionally refresh the
    outbound greeting from env, then dial the configured callee. Returns a
    sanitized payload — call_id and status only, so nothing transport-level
    (and never the callee number) leaks to an LLM or API client."""
    callee = os.environ.get("VOCAL_BRIDGE_CALLEE_PHONE", "").strip()
    if not callee:
        return False, None, "VOCAL_BRIDGE_CALLEE_PHONE not set"

    ok, error = _pin_caller_agent()
    if not ok:
        return False, None, error

    greeting = os.environ.get("VOCAL_BRIDGE_OUTBOUND_GREETING", "").strip()
    if greeting:
        # Greeting refresh is best-effort — the agent keeps its provisioned
        # greeting if this fails, which is a cosmetic difference, not a
        # broken call.
        g_ok, _, g_error = run_vb("config", "set", "--outbound-greeting", greeting)
        if not g_ok:
            logger.warning("outbound greeting update failed: %s", g_error)

    ok, _, error = set_caller_purpose(purpose)
    if not ok:
        return False, None, error

    args = ["call", callee]
    if name:
        args += ["--name", name]
    ok, raw, error = run_vb(*args, json_output=True)
    if not ok:
        return False, None, error
    return True, {
        "call_id": raw.get("call_id"),
        "status": raw.get("status", "initiated"),
    }, None


def _sessions_from_payload(payload: Any) -> list:
    """`vb logs list --json` shape varies by CLI version (bare list vs dict
    with a logs/sessions key) — accept both, like the notebook."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        return payload.get("logs") or payload.get("sessions") or []
    return []


def latest_session(status: str | None = None) -> Tuple[bool, Optional[dict], Optional[str]]:
    """Most recent session log for the pinned agent; (True, None, None) means
    the CLI ran but there are no sessions yet."""
    ok, error = _pin_caller_agent()
    if not ok:
        return False, None, error
    args = ["logs", "list", "-n", "1"]
    if status:
        args += ["--status", status]
    ok, payload, error = run_vb(*args, json_output=True)
    if not ok:
        return False, None, error
    sessions = _sessions_from_payload(payload)
    return True, sessions[0] if sessions else None, None


def find_session(session_id: str, lookback: int = 50) -> Tuple[bool, Optional[dict], Optional[str]]:
    """Find one session by id among the most recent `lookback` logs.
    (True, None, None) means the query ran but no such session."""
    ok, error = _pin_caller_agent()
    if not ok:
        return False, None, error
    ok, payload, error = run_vb("logs", "list", "-n", str(lookback), json_output=True)
    if not ok:
        return False, None, error
    for session in _sessions_from_payload(payload):
        # Live CLI payloads key the id as `id` (observed 2026-07-08 on the
        # deployed service); older/newer shapes may use `session_id`.
        if isinstance(session, dict) and session_id in (
            session.get("id"), session.get("session_id")
        ):
            return True, session, None
    return True, None, None


def download_recording(session_id: str, out_path: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """Download the call recording via `vb logs download`. Returns
    (success, local_path, error)."""
    ok, error = _pin_caller_agent()
    if not ok:
        return False, None, error
    ok, _, error = run_vb("logs", "download", session_id, "-o", out_path, timeout=120)
    if not ok:
        return False, None, error
    if not os.path.exists(out_path):
        return False, None, f"vb logs download reported success but {out_path} is missing"
    return True, out_path, None
