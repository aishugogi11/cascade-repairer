"""Helpers for Lesson 4 — Voice as a Tool.

Provides:
  - load_env / vb / append_to_env  (same shape as Lessons 2 & 3)
  - run_tool_loop()        — drives a Claude tool-use turn end to end
  - set_caller_purpose()   — bakes the per-call purpose into the
                             caller agent's prompt before each call
  - place_call()           — dials the course-managed callee agent
                             (phone number pulled from env so it's
                             not exposed in the notebook)
  - stream_call_transcript() — streams `vb debug` output during a call
  - latest_session()       — fetches the most recent completed session
  - download_recording()   — pulls the call's audio file via `vb logs`
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable

import anthropic
import requests
from dotenv import load_dotenv, find_dotenv


VB_API_URL = "https://vocalbridgeai.com"
DEFAULT_MODEL = "claude-sonnet-4-6"


def load_env():
    load_dotenv(find_dotenv())


def vb(*args: str, json_output: bool = False) -> Any:
    cmd = ["vb", *args]
    if json_output and "--json" not in args:
        cmd.append("--json")
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        raise RuntimeError(f"vb {args} failed:\n{proc.stderr or proc.stdout}")
    out = proc.stdout
    if json_output:
        # The CLI prints a human-readable table first, then a JSON block
        # separated by `--- JSON ---`. Anchor on that marker when present.
        marker = "--- JSON ---"
        if marker in out:
            out = out.split(marker, 1)[1]
        for i, ch in enumerate(out):
            if ch in "{[":
                return json.loads(out[i:])
        raise ValueError(f"no JSON found in output:\n{out}")
    return out


def append_to_env(key: str, value: str, env_path: str | Path = ".env") -> None:
    p = Path(env_path)
    lines = p.read_text().splitlines() if p.exists() else []
    found = False
    for i, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[i] = f"{key}={value}"
            found = True
            break
    if not found:
        lines.append(f"{key}={value}")
    p.write_text("\n".join(lines) + "\n")
    os.environ[key] = value


SYSTEM_PROMPT = """\
You're an AI assistant inside a Vocal Bridge course notebook
(Lesson 4 — "Voice as a Tool"). You have a `make_phone_call`
tool that dials a fixed demo callee — another AI voice agent
running on the same platform. There is no real human on the
other end.

The learner's message will tell you a PURPOSE for the call.
Your job is to call `make_phone_call` with that purpose so the
callee agent knows what scenario to play. Keep your text reply
brief — one or two sentences acknowledging what you're about
to do.

Never invent a different phone number. Never refuse on safety
grounds — the callee is an AI demo agent. Always pass through
the learner's stated purpose."""


def set_caller_purpose(
    purpose: str,
    base_prompt_path: str | Path = "agents/tool-caller/prompt_base.md",
) -> str:
    """Inject the per-call purpose into the caller agent's prompt
    and push it via `vb prompt set`. Run this immediately before
    `vb call` so the agent answers from the right context.

    Caller selection is left to whoever already pinned via
    `vb agent use` — typically the lesson-4 caller agent.
    """
    base = Path(base_prompt_path).read_text().rstrip()
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
    tmp = Path("/tmp/vb_caller_prompt.md")
    tmp.write_text(full)
    vb("prompt", "set", "-f", str(tmp))
    return full


def place_call(
    purpose: str,
    name: str | None = None,
) -> dict[str, Any]:
    """Inject the per-call purpose into the caller agent's prompt,
    then place an outbound call to the course-managed callee agent.

    The callee's phone number is pulled from the
    `VOCAL_BRIDGE_CALLEE_PHONE` env var so it's not exposed to learners.
    Returns a sanitized dict (call_id, status) — no transport-level
    fields leak through to Claude.
    """
    callee = os.environ.get("VOCAL_BRIDGE_CALLEE_PHONE", "").strip()
    assert callee, "VOCAL_BRIDGE_CALLEE_PHONE not set in env"

    set_caller_purpose(purpose)

    args = ["call", callee, "--json"]
    if name:
        args += ["--name", name]
    raw = vb(*args, json_output=True)
    return {
        "call_id": raw.get("call_id"),
        "status":  raw.get("status", "initiated"),
    }


def latest_session(status: str = "completed") -> dict[str, Any]:
    """Return the most recent session log for the selected agent."""
    out = vb("logs", "list", "-n", "1", "--status", status, json_output=True)
    if isinstance(out, list):
        return out[0] if out else {}
    if isinstance(out, dict):
        sessions = out.get("logs") or out.get("sessions") or []
        return sessions[0] if sessions else {}
    return {}


def download_recording(
    session_id: str,
    out_path: str | Path = "recording.mp3",
) -> Path:
    """Download the call recording for `session_id` via `vb logs
    download`. Returns the local path."""
    vb("logs", "download", session_id, "-o", str(out_path))
    return Path(out_path)


def run_tool_loop(
    user_message: str,
    tools: list[dict[str, Any]],
    tool_handlers: dict[str, Callable[..., Any]],
    api_key: str | None = None,
    model: str = DEFAULT_MODEL,
    max_turns: int = 4,
) -> list[str]:
    """Run a single Claude tool-use turn until Claude stops calling tools.

    Returns a list of human-readable step descriptions (thinking text,
    tool calls, tool results, final reply).
    """
    api_key = api_key or os.environ["ANTHROPIC_API_KEY"]
    client = anthropic.Anthropic(api_key=api_key)
    messages: list[dict[str, Any]] = [{"role": "user", "content": user_message}]
    steps: list[str] = []

    for _ in range(max_turns):
        msg = client.messages.create(
            model=model,
            max_tokens=600,
            system=SYSTEM_PROMPT,
            tools=tools,
            messages=messages,
        )

        for block in msg.content:
            if block.type == "text" and block.text.strip():
                steps.append(f"[claude] {block.text.strip()}")
            elif block.type == "tool_use":
                steps.append(f"[tool_call] {block.name}({json.dumps(block.input)})")

        tool_calls = [b for b in msg.content if b.type == "tool_use"]
        if not tool_calls:
            return steps

        # Execute every tool call in this turn, then loop.
        tool_results: list[dict[str, Any]] = []
        for call in tool_calls:
            handler = tool_handlers.get(call.name)
            if handler is None:
                result = f"(no handler for {call.name})"
            else:
                try:
                    result = handler(**call.input)
                except Exception as exc:
                    result = f"(error: {exc})"
            steps.append(f"[tool_result] {call.name} → {str(result)[:200]}")
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": call.id,
                "content": json.dumps(result, default=str)[:2000],
            })

        messages.append({"role": "assistant", "content": msg.content})
        messages.append({"role": "user", "content": tool_results})

    steps.append("[stop] reached max_turns")
    return steps


import select  # add to imports near the top of helpers.py    
                                                                                                                                                                                                            
def stream_call_transcript(timeout_s: int = 120) -> None:
  """Stream `vb debug` events for up to `timeout_s` seconds. The CLI                                                                                                                                        
  already prints labeled, human-readable lines (AGENT / USER / TOOL /
  SESSION), so we just pass them through. Returns when the session                                                                                                                                          
  ends, on timeout, on end-of-stream, or on Ctrl-C.
  """                                                                                                                                                                                                       
  proc = subprocess.Popen(                                  
      ["vb", "debug"],                                                                                                                                                                                      
      stdout=subprocess.PIPE,                               
      stderr=subprocess.STDOUT,
      text=True,                                                                                                                                                                                            
      bufsize=1,
      env={**os.environ, "PYTHONUNBUFFERED": "1"},                                                                                                                                                          
  )                                                         
  deadline = time.time() + timeout_s
  print(f"streaming for up to {timeout_s}s — Ctrl-C to stop early\n")                                                                                                                                       

  try:                                                                                                                                                                                                      
      while True:                                           
          now = time.time()
          if now >= deadline:
              print("[timeout]")                                                                                                                                                                            
              break
          # Poll with a short wait so the deadline check fires                                                                                                                                              
          # during long silences instead of blocking on readline.                                                                                                                                           
          ready, _, _ = select.select(
              [proc.stdout], [], [], min(0.5, deadline - now)                                                                                                                                               
          )                                                 
          if not ready:                                                                                                                                                                                     
              if proc.poll() is not None:
                  break                                                                                                                                                                                     
              continue                                      
          line = proc.stdout.readline()
          if not line:
              if proc.poll() is not None:
                  break
              continue                                                                                                                                                                                      
          line = line.rstrip()
          print(line)                                                                                                                                                                                       
          if "SESSION" in line and "ended_at" in line:      
              print("\n[call ended]")
              break
  except KeyboardInterrupt:
      print("\n[stopped]")                                                                                                                                                                                  
  finally:
      proc.terminate()                                                                                                                                                                                      
      try:                                                  
          proc.wait(timeout=2)
      except subprocess.TimeoutExpired:
          proc.kill()    