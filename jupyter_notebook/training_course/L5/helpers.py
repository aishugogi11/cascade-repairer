"""Helpers for Lesson 5 — Voice AI Evals.

Wraps `vb eval <session_id>` and parses the JSON report into a Python dict
the notebook can iterate on.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from dotenv import load_dotenv, find_dotenv


def load_env():
    load_dotenv(find_dotenv())

def vb(*args: str, json_output: bool = False) -> Any:
    cmd = ["vb", *args]
    if json_output and "--json" not in args:
        cmd.append("--json")
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
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


def eval_session(
    session_id: str,
    objective: str | None = None,
    scenario: str | None = None,
) -> dict[str, Any]:
    """Run `vb eval <session_id> --json` with optional objective/scenario."""
    args = ["eval", session_id, "--json"]
    if objective:
        args += ["--objective", objective]
    if scenario:
        args += ["--scenario", scenario]
    return vb(*args, json_output=True)
