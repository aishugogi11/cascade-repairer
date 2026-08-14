"""Text-LLM seam: Featherless when configured, otherwise OpenAI.

STT/TTS stay on OpenAI. Featherless is OpenAI-compatible chat completions
only (https://api.featherless.ai/v1). Tests stay hermetic: no key required.
"""
from __future__ import annotations

import os
from typing import Any, Optional

FEATHERLESS_BASE = "https://api.featherless.ai/v1"
DEFAULT_FEATHERLESS_MODEL = "meta-llama/Meta-Llama-3.1-8B-Instruct"
DEFAULT_OPENAI_MODEL = "gpt-5.4-mini"
_APP_HEADERS = {
    "HTTP-Referer": "https://talktomytrip.com",
    "X-Title": "Cascade Repairer",
}


def featherless_configured() -> bool:
    return bool(os.environ.get("FEATHERLESS_API_KEY", "").strip())


def openai_configured() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY", "").strip())


def text_llm_configured() -> bool:
    return featherless_configured() or openai_configured()


def text_model_id() -> str:
    if featherless_configured():
        feather = os.environ.get("FEATHERLESS_MODEL", "").strip()
        if feather:
            return feather
        override = os.environ.get("CONCIERGE_LLM_MODEL", "").strip()
        if override and not override.startswith("gpt-"):
            return override
        return DEFAULT_FEATHERLESS_MODEL
    return os.environ.get("CONCIERGE_LLM_MODEL", DEFAULT_OPENAI_MODEL)


def provider_name() -> str:
    return "featherless" if featherless_configured() else "openai"


def sync_chat_client():
    """Blocking OpenAI SDK client for chat.completions (parse, classifiers)."""
    from openai import OpenAI

    if featherless_configured():
        return OpenAI(
            base_url=FEATHERLESS_BASE,
            api_key=os.environ["FEATHERLESS_API_KEY"].strip(),
            default_headers=_APP_HEADERS,
        )
    return OpenAI()


def async_chat_client():
    from openai import AsyncOpenAI

    if featherless_configured():
        return AsyncOpenAI(
            base_url=FEATHERLESS_BASE,
            api_key=os.environ["FEATHERLESS_API_KEY"].strip(),
            default_headers=_APP_HEADERS,
        )
    return AsyncOpenAI()


def agents_model() -> Any:
    """Value for Agent(model=...). Featherless uses Chat Completions, not Responses."""
    model_id = text_model_id()
    if not featherless_configured():
        return model_id
    from agents import OpenAIChatCompletionsModel

    return OpenAIChatCompletionsModel(
        model=model_id,
        openai_client=async_chat_client(),
    )


def configure_agents_sdk() -> None:
    """Point the Agents SDK at Featherless when a key is present.

    Safe to call more than once. No-op without FEATHERLESS_API_KEY so
    hermetic tests keep the default OpenAI path.
    """
    if not featherless_configured():
        return
    from agents import (
        set_default_openai_api,
        set_default_openai_client,
        set_tracing_disabled,
    )

    set_default_openai_client(async_chat_client())
    set_default_openai_api("chat_completions")
    set_tracing_disabled(True)
