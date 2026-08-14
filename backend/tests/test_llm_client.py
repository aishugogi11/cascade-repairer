"""Text-LLM seam — Featherless when keyed, OpenAI otherwise. Hermetic."""
from api import llm_client


def test_default_without_featherless_is_openai(monkeypatch):
    monkeypatch.delenv("FEATHERLESS_API_KEY", raising=False)
    monkeypatch.delenv("CONCIERGE_LLM_MODEL", raising=False)
    assert llm_client.featherless_configured() is False
    assert llm_client.provider_name() == "openai"
    assert llm_client.text_model_id() == "gpt-5.4-mini"
    assert llm_client.agents_model() == "gpt-5.4-mini"
    llm_client.configure_agents_sdk()  # no-op, must not raise


def test_featherless_key_selects_llama_and_ignores_gpt_override(monkeypatch):
    monkeypatch.setenv("FEATHERLESS_API_KEY", "fl-test")
    monkeypatch.delenv("FEATHERLESS_MODEL", raising=False)
    monkeypatch.setenv("CONCIERGE_LLM_MODEL", "gpt-5.4-mini")
    assert llm_client.provider_name() == "featherless"
    assert llm_client.text_model_id() == llm_client.DEFAULT_FEATHERLESS_MODEL
    model = llm_client.agents_model()
    assert model.model == llm_client.DEFAULT_FEATHERLESS_MODEL


def test_featherless_model_env_wins(monkeypatch):
    monkeypatch.setenv("FEATHERLESS_API_KEY", "fl-test")
    monkeypatch.setenv("FEATHERLESS_MODEL", "Qwen/Qwen2.5-7B-Instruct")
    assert llm_client.text_model_id() == "Qwen/Qwen2.5-7B-Instruct"


def test_non_gpt_concierge_override_on_featherless(monkeypatch):
    monkeypatch.setenv("FEATHERLESS_API_KEY", "fl-test")
    monkeypatch.delenv("FEATHERLESS_MODEL", raising=False)
    monkeypatch.setenv("CONCIERGE_LLM_MODEL", "meta-llama/Meta-Llama-3.1-70B-Instruct")
    assert llm_client.text_model_id() == "meta-llama/Meta-Llama-3.1-70B-Instruct"
