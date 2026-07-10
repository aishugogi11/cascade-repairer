"""Cascaded voice pipeline core — the L2/L3 architecture as working code.

The three stages of the course's cascaded architecture (STT → LLM → TTS),
each importable on its own so the demo router can expose them individually.
Two deliberate deviations from the notebooks, both spec'd in
specs/2026-07-08-course-lesson-demo-routers/requirements.md:

- The notebooks delegate STT/TTS to the Vocal Bridge platform; here the
  stages run on the OpenAI audio APIs so the cascade is individually
  demoable over plain HTTP (the `openai` package already ships with
  openai-agents, and OPENAI_API_KEY is already set on Cloud Run).
- The notebooks' LLM is Anthropic; the agent layer here is the OpenAI
  Agents SDK per the mission (`agent_reply` is the L3 query-server handler
  shape: spoken turn in as text, speakable text out).

Session history is an in-process dict (session_id → Agents SDK input list)
— the same deliberate single-instance scope as the Phase 5 session registry.
Clients and models are created per call; importing this module needs no
credentials.
"""
import os
from typing import Dict, List, Optional

from agents import Agent, Runner
from openai import OpenAI

DEFAULT_STT_MODEL = "gpt-4o-mini-transcribe"
DEFAULT_LLM_MODEL = "gpt-5.4-mini"
DEFAULT_TTS_MODEL = "gpt-4o-mini-tts"
DEFAULT_TTS_VOICE = "alloy"

# TTS rejects inputs over 4096 chars; replies are prompted to stay short,
# so truncation is a guard, not an expected path.
_TTS_MAX_CHARS = 4096

AGENT_INSTRUCTIONS = (
    "You are the voice of a travel assistant for a demo of the cascaded "
    "voice architecture (speech-to-text, then you, then text-to-speech). "
    "Your replies are spoken aloud: keep them to one or two short, "
    "conversational sentences. No markdown, no lists, no stage directions."
)

_HISTORY: Dict[str, List] = {}


def _stt_model() -> str:
    return os.environ.get("CASCADE_STT_MODEL", DEFAULT_STT_MODEL)


def _llm_model() -> str:
    return os.environ.get("CASCADE_LLM_MODEL", DEFAULT_LLM_MODEL)


def _tts_model() -> str:
    return os.environ.get("CASCADE_TTS_MODEL", DEFAULT_TTS_MODEL)


def _tts_voice() -> str:
    return os.environ.get("CASCADE_TTS_VOICE", DEFAULT_TTS_VOICE)


def transcribe(audio_bytes: bytes, filename: str = "audio.wav") -> str:
    """Stage 1 — STT. Blocking; callers on the event loop use
    asyncio.to_thread."""
    client = OpenAI()
    result = client.audio.transcriptions.create(
        model=_stt_model(),
        file=(filename, audio_bytes),
    )
    return result.text


async def agent_reply(text: str, session_id: Optional[str] = None) -> str:
    """Stage 2 — the agent turn, a plain `await Runner.run(...)` (the
    concurrency_core pattern). With a session_id, prior turns of that
    session are replayed as input so the conversation is multi-turn."""
    agent = Agent(
        name="Cascade Demo Agent",
        model=_llm_model(),
        instructions=AGENT_INSTRUCTIONS,
    )
    history = _HISTORY.get(session_id, []) if session_id else []
    result = await Runner.run(
        agent,
        history + [{"role": "user", "content": text}],
        max_turns=4,
    )
    if session_id:
        _HISTORY[session_id] = result.to_input_list()
    return str(result.final_output)


def synthesize(text: str) -> bytes:
    """Stage 3 — TTS to mp3 bytes. Blocking; callers on the event loop use
    asyncio.to_thread."""
    client = OpenAI()
    response = client.audio.speech.create(
        model=_tts_model(),
        voice=_tts_voice(),
        input=text[:_TTS_MAX_CHARS],
        response_format="mp3",
    )
    return response.content
