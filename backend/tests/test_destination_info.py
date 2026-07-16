"""Phase 35 tests — the destination_info Tavily tool, hermetic.

Tavily is mocked at the client boundary (`_tavily_client` / `_tavily_search`);
no TAVILY_API_KEY, no network. The load-bearing contracts: the pinned trip's
destination and dates garnish the query server-side, an unpinned session
searches the question verbatim, results are condensed speakable strings
(URL-free, capped), every failure path returns the speakable fallback instead
of raising, and the tool is always registered — key or no key.
"""
import asyncio
import inspect
import time
from datetime import date
from unittest.mock import MagicMock

import pytest

from api import concierge
from api.helpers.bigquery_helper import bq_helper
from api.repositories.models import ItineraryItem, Trip


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.setattr(concierge, "_SESSION_TRIPS", {})


def _pin_trip(session_id="room-1"):
    trip = Trip(
        trip_id="t-1", user_id="demo-traveler",
        title="The Complete Trip — hackathon demo", status="booked",
        origin="MSP", destinations=["SFO", "Mountain View"],
        start_date=date(2026, 7, 17), end_date=date(2026, 7, 19),
    )
    items = [ItineraryItem(trip_id="t-1", type="flight", status="booked")]
    concierge._SESSION_TRIPS[session_id] = concierge.TripContext(
        trip=trip, items=items, summary="summary"
    )


def _capture_search(monkeypatch, reply="Plenty going on."):
    queries = []

    def fake_search(query):
        queries.append(query)
        return reply

    monkeypatch.setattr(concierge, "_tavily_search", fake_search)
    return queries


# --- query garnish (trip-aware, server-side) ---------------------------------


def test_pinned_trip_garnishes_query_with_destination_and_dates(monkeypatch):
    queries = _capture_search(monkeypatch)
    _pin_trip()

    reply = asyncio.run(
        concierge.destination_info_impl("room-1", "what's happening there?")
    )

    assert reply == "Plenty going on."
    assert len(queries) == 1
    assert "what's happening there?" in queries[0]
    assert "SFO, Mountain View" in queries[0]
    assert "2026-07-17" in queries[0] and "2026-07-19" in queries[0]


def test_unpinned_session_searches_question_verbatim(monkeypatch):
    queries = _capture_search(monkeypatch)

    reply = asyncio.run(
        concierge.destination_info_impl(
            "room-1", "what's happening in Los Angeles this weekend?"
        )
    )

    assert reply == "Plenty going on."
    assert queries == ["what's happening in Los Angeles this weekend?"]


# --- condensing (_tavily_search) ----------------------------------------------


class _FakeTavily:
    def __init__(self, response):
        self._response = response
        self.calls = []

    def search(self, query, **kwargs):
        self.calls.append((query, kwargs))
        return self._response


def _fake_client(monkeypatch, response):
    client = _FakeTavily(response)
    monkeypatch.setattr(concierge, "_tavily_client", lambda: client)
    return client


def test_search_prefers_tavily_answer_and_uses_voice_settings(monkeypatch):
    client = _fake_client(
        monkeypatch,
        {"answer": "The Getty is free all weekend.", "results": [{"content": "x"}]},
    )
    assert concierge._tavily_search("q") == "The Getty is free all weekend."
    _, kwargs = client.calls[0]
    # The spec's deliberate divergences from the proof notebook.
    assert kwargs["search_depth"] == "basic"
    assert kwargs["include_answer"] is True
    assert kwargs["max_results"] == 3


def test_search_falls_back_to_result_snippets(monkeypatch):
    _fake_client(
        monkeypatch,
        {"answer": "", "results": [
            {"content": "Jazz festival downtown."},
            {"content": "  Farmers market Sunday.  "},
            {"content": ""},
        ]},
    )
    assert (
        concierge._tavily_search("q")
        == "Jazz festival downtown. Farmers market Sunday."
    )


def test_search_strips_urls_and_caps_length(monkeypatch):
    long_tail = "word " * 300
    _fake_client(
        monkeypatch,
        {"answer": f"See https://example.com/events for more. {long_tail}"},
    )
    result = concierge._tavily_search("q")
    assert "https://" not in result and "example.com" not in result
    assert result.startswith("See for more.".split()[0])
    assert len(result) <= concierge._DESTINATION_INFO_MAX_CHARS
    # The cap lands on a word boundary — a mid-word slice would be spoken.
    assert result.split()[-1] == "word"


def test_search_strips_bare_urls_and_markdown(monkeypatch):
    """Phase 35 validation finding: bare www. URLs and Markdown passed the
    original https?://-only pattern into a spoken string."""
    _fake_client(
        monkeypatch,
        {"answer": (
            "Try **CicLAvia** at www.example.com/events. "
            "See [more events](https://la.com/x) _tonight_."
        )},
    )
    result = concierge._tavily_search("q")
    # The speakable content survives...
    assert "CicLAvia" in result
    assert "more events" in result and "tonight" in result
    # ...the Markdown delimiters and every URL form do not.
    assert "*" not in result and "_" not in result and "[" not in result
    assert "www." not in result and "https://" not in result
    assert "example.com" not in result and "la.com" not in result


def test_search_raises_without_key_or_content(monkeypatch):
    # No key: _tavily_client returns None (fresh_state deleted the env var).
    with pytest.raises(RuntimeError):
        concierge._tavily_search("q")
    # Key but nothing usable in the response.
    _fake_client(monkeypatch, {"answer": "", "results": []})
    with pytest.raises(RuntimeError):
        concierge._tavily_search("q")


# --- failure paths never raise (the voice turn must survive anything) --------


def test_missing_key_returns_speakable_fallback():
    reply = asyncio.run(concierge.destination_info_impl("room-1", "things to do?"))
    assert reply == concierge._DESTINATION_INFO_FALLBACK


def test_client_exception_returns_speakable_fallback(monkeypatch):
    def boom(query):
        raise ValueError("tavily fell over")

    monkeypatch.setattr(concierge, "_tavily_search", boom)
    reply = asyncio.run(concierge.destination_info_impl("room-1", "things to do?"))
    assert reply == concierge._DESTINATION_INFO_FALLBACK


def test_timeout_returns_speakable_fallback(monkeypatch):
    monkeypatch.setattr(concierge, "_TAVILY_TIMEOUT_S", 0.05)

    def slow(query):
        time.sleep(0.5)
        return "too late"

    monkeypatch.setattr(concierge, "_tavily_search", slow)
    reply = asyncio.run(concierge.destination_info_impl("room-1", "things to do?"))
    assert reply == concierge._DESTINATION_INFO_FALLBACK


def test_empty_results_return_speakable_fallback(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
    _fake_client(monkeypatch, {"answer": "", "results": []})
    reply = asyncio.run(concierge.destination_info_impl("room-1", "things to do?"))
    assert reply == concierge._DESTINATION_INFO_FALLBACK


def test_destination_info_does_not_mutate_booking_or_trip_state(monkeypatch):
    """Phase 35 validation's proposed guard: the lookup is read-only — no
    repository write, no options-slot touch, no pinned-context drift."""
    _capture_search(monkeypatch)
    _pin_trip()
    monkeypatch.setattr(
        concierge, "_SESSION_FLIGHT_OPTIONS", {"room-1": ["option-sentinel"]}
    )
    latest_sentinel = ("room-1", ["option-sentinel"], "recorded-at")
    monkeypatch.setattr(concierge, "_LATEST_SEARCH", latest_sentinel)
    dml, select = MagicMock(), MagicMock()
    monkeypatch.setattr(bq_helper, "run_dml", dml)
    monkeypatch.setattr(bq_helper, "run_select", select)
    context_before = concierge._SESSION_TRIPS["room-1"].model_dump_json()
    options_before = {"room-1": ["option-sentinel"]}

    reply = asyncio.run(concierge.destination_info_impl("room-1", "things to do?"))

    assert reply == "Plenty going on."
    assert concierge._SESSION_TRIPS["room-1"].model_dump_json() == context_before
    assert concierge._SESSION_FLIGHT_OPTIONS == options_before
    assert concierge._LATEST_SEARCH is latest_sentinel
    dml.assert_not_called()
    select.assert_not_called()


# --- registration & discipline ------------------------------------------------


def test_tool_always_registered_without_key():
    # fresh_state deleted TAVILY_API_KEY — the always-register decision.
    agent = concierge.build_agent("room-1")
    assert "destination_info" in {t.name for t in agent.tools}


def test_instructions_carry_the_subtle_offer_clause():
    assert "destination_info" in concierge.BASE_INSTRUCTIONS
    assert "don't offer it unprompted" in concierge.BASE_INSTRUCTIONS


def test_impl_runs_search_off_the_event_loop():
    """The sync Tavily call must ride asyncio.to_thread inside wait_for (the
    standing blocking-call rule) — source-inspected, the validation.md seam."""
    source = inspect.getsource(concierge.destination_info_impl)
    assert "asyncio.to_thread(_tavily_search" in source
    assert "asyncio.wait_for(" in source
