"""Phase 11 tests — the eval harness (api/eval_harness/).

Hermetic: HTTP goes through httpx.MockTransport, `vb` and git through mocks,
and the repository boundary is monkeypatched — no GCP credentials, no
OPENAI_API_KEY, no vb binary, no network.
"""
import json
from unittest.mock import MagicMock

import httpx
import pytest

from api.eval_harness import metrics, runner
from api.eval_harness import __main__ as harness_main
from api.eval_harness.runner import ArchitectureResult, TurnTiming
from api.eval_harness.scenario_loader import (
    SCENARIOS_DIR,
    Scenario,
    ScenarioError,
    load_scenario,
    load_scenarios,
)

SCENARIO = Scenario(
    name="test-scenario",
    description="a test",
    turns=["hello there", "read it back"],
    ground_truth="my flight was cancelled",
    objective="acknowledge the cancellation",
)


# ── metrics: wer ───────────────────────────────────────────────────────


def test_wer_identical_is_zero():
    assert metrics.wer("the same words here", "the same words here") == 0.0


def test_wer_single_substitution_in_five_words():
    assert metrics.wer("one two three four five", "one two tree four five") == 0.2


def test_wer_empty_hypothesis_is_one():
    assert metrics.wer("some reference text", "") == 1.0


def test_wer_case_and_punctuation_invariant():
    assert metrics.wer("Hello, world! It's fine.", "hello world it's fine") == 0.0


def test_wer_both_empty_is_zero():
    assert metrics.wer("", "") == 0.0


def test_wer_can_exceed_one():
    assert metrics.wer("yes", "no no no") > 1.0


# ── metrics: mos mapping ───────────────────────────────────────────────


def test_mos_score_zero_maps_to_one():
    assert metrics.mos_from_vb_score(0) == 1.0


def test_mos_score_ten_maps_to_five():
    assert metrics.mos_from_vb_score(10) == 5.0


def test_mos_out_of_range_clamps():
    assert metrics.mos_from_vb_score(-3) == 1.0
    assert metrics.mos_from_vb_score(14) == 5.0


def test_mos_midpoint():
    assert metrics.mos_from_vb_score(5) == 3.0


# ── metrics: latency summary ───────────────────────────────────────────


def test_summarize_latencies_math():
    summary = metrics.summarize_latencies([100.0, 200.0, 300.0])
    assert summary == {"count": 3, "mean_ms": 200.0, "p50_ms": 200.0, "max_ms": 300.0}


def test_summarize_latencies_empty():
    summary = metrics.summarize_latencies([])
    assert summary["count"] == 0
    assert summary["mean_ms"] is None


# ── scenario loader ────────────────────────────────────────────────────


def test_every_checked_in_fixture_loads():
    scenarios = load_scenarios()
    assert len(scenarios) >= 2
    for scenario in scenarios:
        assert scenario.name and scenario.turns and scenario.objective


def test_checked_in_fixture_dir_is_the_packaged_one():
    assert SCENARIOS_DIR.is_dir()
    assert list(SCENARIOS_DIR.glob("*.yaml"))


def test_missing_field_fails_naming_the_file(tmp_path):
    bad = tmp_path / "broken.yaml"
    bad.write_text("name: broken\ndescription: d\nturns: ['hi']\n")  # no ground_truth/objective
    with pytest.raises(ScenarioError, match="broken.yaml"):
        load_scenario(bad)


def test_non_mapping_yaml_fails_naming_the_file(tmp_path):
    bad = tmp_path / "list.yaml"
    bad.write_text("- just\n- a\n- list\n")
    with pytest.raises(ScenarioError, match="list.yaml"):
        load_scenario(bad)


def test_blank_turn_rejected(tmp_path):
    bad = tmp_path / "blank.yaml"
    bad.write_text(
        "name: blank\ndescription: d\nturns: ['ok', '  ']\n"
        "ground_truth: g\nobjective: o\n"
    )
    with pytest.raises(ScenarioError, match="blank.yaml"):
        load_scenario(bad)


# ── runner: cascaded ───────────────────────────────────────────────────


def _mock_client_factory(handler):
    """Patch runner.httpx.Client so runs go through a MockTransport.
    runner.httpx IS the httpx module, so grab the real class first."""
    real_client = httpx.Client

    def factory(**kwargs):
        return real_client(transport=httpx.MockTransport(handler))
    return factory


def _cascade_handler(fail_turn_paths=()):
    calls = {"converse": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/v1/cascade_demo/tts":
            return httpx.Response(200, content=b"mp3-bytes", headers={"content-type": "audio/mpeg"})
        if path == "/v1/cascade_demo/stt":
            return httpx.Response(200, json={"transcript": "my flight was cancelled"})
        if path == "/v1/cascade_demo/converse":
            calls["converse"] += 1
            if calls["converse"] in fail_turn_paths:
                return httpx.Response(502, json={"error": "cascade failed"})
            return httpx.Response(
                200, content=b"reply-mp3",
                headers={"content-type": "audio/mpeg", "X-Session-Id": "sess-1"},
            )
        raise AssertionError(f"unexpected path {path}")

    return handler


def test_run_cascaded_measures_wer_and_latency(monkeypatch):
    monkeypatch.setattr(runner.httpx, "Client", _mock_client_factory(_cascade_handler()))
    result = runner.run_cascaded("http://target", SCENARIO)
    assert result.architecture == "cascaded"
    assert result.wer == 0.0  # transcript matches ground truth exactly
    assert len(result.turn_timings) == 2
    assert all(t.error is None for t in result.turn_timings)
    assert result.ttfb_ms is not None and result.e2e_latency_ms is not None
    assert result.ttfb_ms <= result.e2e_latency_ms
    assert not result.failed


def test_run_cascaded_failed_turn_recorded_not_raised(monkeypatch):
    monkeypatch.setattr(
        runner.httpx, "Client", _mock_client_factory(_cascade_handler(fail_turn_paths={1}))
    )
    result = runner.run_cascaded("http://target", SCENARIO)
    errors = [t for t in result.turn_timings if t.error]
    assert len(errors) == 1 and "502" in errors[0].error
    assert len(result.ttfb_samples) == 1  # the other turn still measured
    assert not result.failed


def test_run_cascaded_unreachable_backend_fails_cleanly(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(runner.httpx, "Client", _mock_client_factory(handler))
    result = runner.run_cascaded("http://nowhere", SCENARIO)
    assert result.failed
    assert result.wer is None and result.wer_error
    assert all(t.error for t in result.turn_timings)


# ── runner: concierge ──────────────────────────────────────────────────


def test_run_concierge_times_text_turns(monkeypatch):
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/web_call/query"
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"response": "on it"})

    monkeypatch.setattr(runner.httpx, "Client", _mock_client_factory(handler))
    result = runner.run_concierge("http://target", SCENARIO)
    assert result.architecture == "concierge"
    assert result.wer is None
    assert len(result.turn_timings) == 2 and not result.failed
    # All turns share one generated session_name.
    assert len({payload["session_name"] for payload in seen}) == 1


# ── runner: MOS leg & git sha ──────────────────────────────────────────


def test_eval_vb_session_flat_notebook_shape(monkeypatch):
    payload = {"score": 8, "suggestions": ["tighten the greeting"]}
    monkeypatch.setattr(runner, "run_vb", lambda *a, **k: (True, payload, None))
    mos, summary = runner.eval_vb_session("sess-1", "objective")
    assert mos == pytest.approx(4.2)
    assert "tighten the greeting" in summary


def test_eval_vb_session_nested_result_shape(monkeypatch):
    # The live CLI shape (observed 2026-07-09): scoring nested under `result`.
    payload = {
        "session_id": "sess-1",
        "objective": "objective",
        "result": {
            "score": 2,
            "verdict": "fail",
            "summary": "ignored the objective",
            "suggested_prompt_improvements": "prioritize the purpose block",
        },
    }
    monkeypatch.setattr(runner, "run_vb", lambda *a, **k: (True, payload, None))
    mos, summary = runner.eval_vb_session("sess-1", "objective")
    assert mos == pytest.approx(1.8)
    parsed = json.loads(summary)
    assert parsed["verdict"] == "fail"
    assert parsed["suggestions"] == "prioritize the purpose block"


def test_eval_vb_session_cli_missing(monkeypatch):
    monkeypatch.setattr(runner, "run_vb", lambda *a, **k: (False, None, "vb CLI not found on PATH"))
    mos, reason = runner.eval_vb_session("sess-1", "objective")
    assert mos is None and "vb CLI not found" in reason


def test_eval_vb_session_non_numeric_score(monkeypatch):
    monkeypatch.setattr(runner, "run_vb", lambda *a, **k: (True, {"score": "great"}, None))
    mos, reason = runner.eval_vb_session("sess-1", "objective")
    assert mos is None and "no numeric score" in reason


def test_resolve_git_sha_env_wins(monkeypatch):
    monkeypatch.setenv("GIT_SHA", "abc1234")
    assert runner.resolve_git_sha() == "abc1234"


def test_resolve_git_sha_no_git_no_crash(monkeypatch):
    monkeypatch.delenv("GIT_SHA", raising=False)
    def no_git(*a, **k):
        raise OSError("git not found")
    monkeypatch.setattr(runner.subprocess, "run", no_git)
    assert runner.resolve_git_sha() is None


# ── CLI (__main__) ─────────────────────────────────────────────────────


def _fake_result(architecture, scenario):
    return ArchitectureResult(
        architecture=architecture,
        scenario=scenario.name,
        turn_timings=[TurnTiming(0, 100.0, 150.0)],
        wer=0.1 if architecture == "cascaded" else None,
    )


def _patch_runners(monkeypatch, factory=_fake_result):
    for arch in list(harness_main.RUNNERS):
        monkeypatch.setitem(
            harness_main.RUNNERS, arch,
            lambda base_url, scenario, _a=arch: factory(_a, scenario),
        )
    monkeypatch.setattr(harness_main, "resolve_git_sha", lambda: "abc1234")


def test_cli_dry_run_never_writes(monkeypatch, capsys):
    _patch_runners(monkeypatch)
    create_run = MagicMock()
    monkeypatch.setattr(harness_main.eval_runs_repo, "create_run", create_run)
    exit_code = harness_main.main(["--dry-run"])
    assert exit_code == 0
    create_run.assert_not_called()
    assert "dry run" in capsys.readouterr().out


def test_cli_writes_one_row_per_architecture_x_scenario(monkeypatch):
    _patch_runners(monkeypatch)
    create_run = MagicMock(return_value=(True, None, None))
    monkeypatch.setattr(harness_main.eval_runs_repo, "create_run", create_run)
    exit_code = harness_main.main([])
    assert exit_code == 0
    fixture_names = {s.name for s in load_scenarios()}
    written = [call.args[0] for call in create_run.call_args_list]
    assert len(written) == len(fixture_names) * len(harness_main.RUNNERS)
    for row in written:
        assert row.architecture in ("cascaded", "concierge")  # enum-valid
        assert row.scenario in fixture_names
        assert row.git_sha == "abc1234"
        json.loads(row.notes)  # notes are valid compact JSON


def test_cli_unknown_scenario_lists_available(monkeypatch, capsys):
    _patch_runners(monkeypatch)
    exit_code = harness_main.main(["--scenario", "does-not-exist", "--dry-run"])
    assert exit_code == 2
    err = capsys.readouterr().err
    assert "does-not-exist" in err and "flight-cancel-readback" in err


def test_cli_all_runs_failed_exits_nonzero(monkeypatch, capsys):
    def failed_result(architecture, scenario):
        return ArchitectureResult(architecture=architecture, scenario=scenario.name)

    _patch_runners(monkeypatch, factory=failed_result)
    create_run = MagicMock()
    monkeypatch.setattr(harness_main.eval_runs_repo, "create_run", create_run)
    exit_code = harness_main.main([])
    assert exit_code == 1
    create_run.assert_not_called()  # no partial garbage rows


def test_cli_vb_session_attaches_mos(monkeypatch):
    _patch_runners(monkeypatch)
    monkeypatch.setattr(
        harness_main, "eval_vb_session", lambda sid, obj: (4.2, '{"score": 8}')
    )
    create_run = MagicMock(return_value=(True, None, None))
    monkeypatch.setattr(harness_main.eval_runs_repo, "create_run", create_run)
    exit_code = harness_main.main(["--vb-session", "sess-1", "--scenario", "repair-status-query"])
    assert exit_code == 0
    for call in create_run.call_args_list:
        row = call.args[0]
        assert row.mos_estimate == 4.2
        assert "mos" in json.loads(row.notes)


def test_cli_base_url_flag_reaches_runner(monkeypatch):
    seen = {}

    def capture(architecture, scenario):
        return _fake_result(architecture, scenario)

    for arch in list(harness_main.RUNNERS):
        def make(a):
            def run(base_url, scenario):
                seen[a] = base_url
                return _fake_result(a, scenario)
            return run
        monkeypatch.setitem(harness_main.RUNNERS, arch, make(arch))
    monkeypatch.setattr(harness_main, "resolve_git_sha", lambda: None)
    exit_code = harness_main.main(
        ["--base-url", "http://localhost:8080", "--dry-run", "--scenario", "flight-cancel-readback"]
    )
    assert exit_code == 0
    assert set(seen.values()) == {"http://localhost:8080"}


def test_package_imports_credential_free():
    # Reaching this point means the imports at module top succeeded with no
    # env/credentials; assert the public surface exists.
    assert callable(runner.run_cascaded)
    assert callable(harness_main.main)
