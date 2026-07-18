"""Phase 40 tests — the per-trip email-address registry, hermetic.

Pure module state, no I/O. The load-bearing contracts: addresses normalize
on store (spoken capture adds case and whitespace a mailbox never wants),
get on an unknown trip is None (None means Call 2 makes no email offer),
and clear/_reset actually forget — a declined offer must leave nothing.
"""
import pytest

from api import trip_emails


@pytest.fixture(autouse=True)
def fresh_registry():
    trip_emails._reset()
    yield
    trip_emails._reset()


def test_store_get_round_trips_per_trip():
    trip_emails.store("t-1", "josh@example.com")
    trip_emails.store("t-2", "other@example.com")

    assert trip_emails.get("t-1") == "josh@example.com"
    assert trip_emails.get("t-2") == "other@example.com"


def test_store_normalizes_case_and_whitespace():
    trip_emails.store("t-1", "  Josh.Janzen@Example.COM ")

    assert trip_emails.get("t-1") == "josh.janzen@example.com"


def test_store_replaces_prior_address():
    trip_emails.store("t-1", "first@example.com")
    trip_emails.store("t-1", "second@example.com")

    assert trip_emails.get("t-1") == "second@example.com"


def test_get_unknown_trip_is_none():
    assert trip_emails.get("t-unknown") is None


def test_clear_forgets_only_that_trip():
    trip_emails.store("t-1", "one@example.com")
    trip_emails.store("t-2", "two@example.com")

    trip_emails.clear("t-1")

    assert trip_emails.get("t-1") is None
    assert trip_emails.get("t-2") == "two@example.com"


def test_clear_unknown_trip_is_a_no_op():
    trip_emails.clear("t-unknown")  # must not raise


def test_reset_empties_everything():
    trip_emails.store("t-1", "one@example.com")

    trip_emails._reset()

    assert trip_emails.get("t-1") is None
