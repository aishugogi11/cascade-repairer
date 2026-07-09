"""Runner — drives a target backend over HTTP and measures it.

The harness treats the backend as a black box: it times real round trips
against the same endpoints the demo uses, so the numbers reflect what judges
will experience. Deliberately synchronous (this is a CLI, not the FastAPI
process) and deliberately resilient: a failed turn is recorded in the result,
never raised — one bad turn must not void a whole eval run.

Deviation from the L5 notebook, by design: the notebook evaluates completed
Vocal Bridge phone calls only. Here latency/WER come from direct HTTP
measurement of our own architectures, and the notebook's `vb eval` LLM judge
survives as the optional MOS leg (`eval_vb_session`).

WER caveat (recorded in notes): the audio is synthesized from the ground
truth by our own TTS, so the score is a TTS→STT consistency floor, not a
human-speech WER estimate.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import httpx

from api.eval_harness.metrics import mos_from_vb_score, summarize_latencies, wer
from api.eval_harness.scenario_loader import Scenario
from api.vb_cli import run_vb

# Generous ceiling: /converse chains STT + agent + TTS against live OpenAI.
_TIMEOUT_S = 120.0


@dataclass
class TurnTiming:
    turn_index: int
    ttfb_ms: Optional[float] = None
    e2e_ms: Optional[float] = None
    error: Optional[str] = None


@dataclass
class ArchitectureResult:
    architecture: str
    scenario: str
    turn_timings: List[TurnTiming] = field(default_factory=list)
    wer: Optional[float] = None
    stt_transcript: Optional[str] = None
    wer_error: Optional[str] = None
    notes_extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def ttfb_samples(self) -> List[float]:
        return [t.ttfb_ms for t in self.turn_timings if t.ttfb_ms is not None]

    @property
    def e2e_samples(self) -> List[float]:
        return [t.e2e_ms for t in self.turn_timings if t.e2e_ms is not None]

    @property
    def ttfb_ms(self) -> Optional[float]:
        return summarize_latencies(self.ttfb_samples)["mean_ms"]

    @property
    def e2e_latency_ms(self) -> Optional[float]:
        return summarize_latencies(self.e2e_samples)["mean_ms"]

    @property
    def failed(self) -> bool:
        """True when the run produced nothing measurable at all."""
        return not self.ttfb_samples and self.wer is None


def _timed_post(
    client: httpx.Client, url: str, **kwargs: Any
) -> Tuple[Optional[httpx.Response], Optional[float], Optional[float], Optional[str]]:
    """POST and return (response, ttfb_ms, e2e_ms, error). TTFB is time to
    response headers, e2e is time to the last body byte."""
    started = time.perf_counter()
    try:
        with client.stream("POST", url, **kwargs) as response:
            ttfb_ms = (time.perf_counter() - started) * 1000
            body = response.read()
            e2e_ms = (time.perf_counter() - started) * 1000
            if response.status_code >= 400:
                detail = body[:200].decode("utf-8", errors="replace")
                return None, None, None, f"HTTP {response.status_code}: {detail}"
            # read() caches the body, so .content/.json() work after close.
            return response, round(ttfb_ms, 1), round(e2e_ms, 1), None
    except httpx.HTTPError as exc:
        return None, None, None, f"{type(exc).__name__}: {exc}"


def _synthesize(client: httpx.Client, base_url: str, text: str) -> Tuple[Optional[bytes], Optional[str]]:
    """TTS the given text via the backend's own cascade stage; (mp3, error)."""
    response, _, _, error = _timed_post(
        client, f"{base_url}/v1/cascade_demo/tts", json={"text": text}
    )
    if error:
        return None, f"tts failed: {error}"
    return response.content, None


def run_cascaded(base_url: str, scenario: Scenario) -> ArchitectureResult:
    """Cascaded architecture: WER via a TTS→STT round trip on the ground
    truth, latency via timed /converse turns sharing one session."""
    result = ArchitectureResult(architecture="cascaded", scenario=scenario.name)
    base_url = base_url.rstrip("/")

    with httpx.Client(timeout=_TIMEOUT_S) as client:
        # WER leg — synthesize the ground truth, transcribe it, compare.
        audio, error = _synthesize(client, base_url, scenario.ground_truth)
        if error:
            result.wer_error = error
        else:
            response, _, _, error = _timed_post(
                client,
                f"{base_url}/v1/cascade_demo/stt",
                files={"file": ("ground_truth.mp3", audio, "audio/mpeg")},
            )
            if error:
                result.wer_error = f"stt failed: {error}"
            else:
                transcript = response.json().get("transcript", "")
                result.stt_transcript = transcript
                result.wer = round(wer(scenario.ground_truth, transcript), 4)

        # Latency leg — each turn synthesized first (synthesis is fixture
        # prep, not measured latency), then a timed /converse round trip.
        session_id: Optional[str] = None
        for index, turn_text in enumerate(scenario.turns):
            audio, error = _synthesize(client, base_url, turn_text)
            if error:
                result.turn_timings.append(TurnTiming(index, error=error))
                continue
            data = {"session_id": session_id} if session_id else {}
            response, ttfb_ms, e2e_ms, error = _timed_post(
                client,
                f"{base_url}/v1/cascade_demo/converse",
                files={"file": (f"turn_{index}.mp3", audio, "audio/mpeg")},
                data=data,
            )
            if error:
                result.turn_timings.append(TurnTiming(index, error=error))
                continue
            session_id = response.headers.get("X-Session-Id", session_id)
            result.turn_timings.append(TurnTiming(index, ttfb_ms, e2e_ms))

    result.notes_extra["wer_leg"] = "tts->stt round trip (consistency floor, not human-speech wer)"
    return result


def run_concierge(base_url: str, scenario: Scenario) -> ArchitectureResult:
    """Concierge architecture: timed text turns through the delegated-query
    endpoint the VB widget uses. Text out is the last byte (VB owns TTS), so
    ttfb == e2e by construction; WER does not apply."""
    result = ArchitectureResult(architecture="concierge", scenario=scenario.name)
    base_url = base_url.rstrip("/")
    session_name = f"eval-{uuid.uuid4().hex[:8]}"

    with httpx.Client(timeout=_TIMEOUT_S) as client:
        for index, turn_text in enumerate(scenario.turns):
            _, ttfb_ms, e2e_ms, error = _timed_post(
                client,
                f"{base_url}/v1/web_call/query",
                json={"query": turn_text, "session_name": session_name},
            )
            if error:
                result.turn_timings.append(TurnTiming(index, error=error))
                continue
            result.turn_timings.append(TurnTiming(index, ttfb_ms, e2e_ms))

    result.notes_extra["latency_leg"] = "text turn: ttfb == e2e (json response, vb owns tts)"
    result.notes_extra["vb_session_name"] = session_name
    return result


RUNNERS = {
    "cascaded": run_cascaded,
    "concierge": run_concierge,
    # "realtime" deliberately absent — the real-time port is a stretch goal.
}


def eval_vb_session(session_id: str, objective: str) -> Tuple[Optional[float], str]:
    """The actual L5 pattern: `vb eval <session_id> --objective … --json`
    scores a completed call 0–10; map onto 1–5 MOS. Returns (mos, summary) —
    (None, reason) on any failure, never raises."""
    ok, payload, error = run_vb(
        "eval", session_id, "--objective", objective, json_output=True, timeout=120
    )
    if not ok:
        return None, f"vb eval failed: {error}"
    if not isinstance(payload, dict):
        return None, "vb eval returned no report object"
    score = payload.get("score")
    if not isinstance(score, (int, float)):
        return None, f"vb eval report has no numeric score: {json.dumps(payload)[:200]}"
    summary = {
        "vb_session": session_id,
        "score": score,
        "suggestions": payload.get("suggestions"),
    }
    return mos_from_vb_score(score), json.dumps(summary)


def resolve_git_sha() -> Optional[str]:
    """GIT_SHA env (set on Cloud Run builds) wins; fall back to the local
    repo; None when neither exists — a row without a SHA beats a crash."""
    sha = os.environ.get("GIT_SHA", "").strip()
    if sha:
        return sha
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None
