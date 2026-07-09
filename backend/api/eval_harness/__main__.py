"""CLI entrypoint: `python -m api.eval_harness` (or `make eval ARGS=…`).

One eval_runs row per architecture × scenario. Defaults target the deployed
Cloud Run service so the numbers reflect what judges will experience; point
--base-url at http://localhost:8080 (in-container) or http://localhost:1019
(host) for the local stack. --dry-run prints the rows and writes nothing.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional

from api.eval_harness.metrics import summarize_latencies
from api.eval_harness.runner import (
    RUNNERS,
    ArchitectureResult,
    eval_vb_session,
    resolve_git_sha,
)
from api.eval_harness.scenario_loader import Scenario, ScenarioError, load_scenarios
from api.repositories import eval_runs as eval_runs_repo
from api.repositories.models import EvalRun

# The dev service from README.md — override with --base-url / EVAL_BASE_URL.
DEFAULT_BASE_URL = "https://vocal-bridge-be-dev-24105435206.us-west1.run.app"


def _build_row(
    result: ArchitectureResult,
    git_sha: Optional[str],
    base_url: str,
    mos: Optional[float],
    mos_note: Optional[str],
) -> EvalRun:
    notes = {
        "base_url": base_url,
        "ttfb": summarize_latencies(result.ttfb_samples),
        "e2e": summarize_latencies(result.e2e_samples),
        "turns": [
            {"i": t.turn_index, "ttfb_ms": t.ttfb_ms, "e2e_ms": t.e2e_ms, "error": t.error}
            for t in result.turn_timings
        ],
        **result.notes_extra,
    }
    if result.stt_transcript is not None:
        notes["stt_transcript"] = result.stt_transcript
    if result.wer_error:
        notes["wer_error"] = result.wer_error
    if mos_note:
        notes["mos"] = mos_note
    return EvalRun(
        architecture=result.architecture,
        git_sha=git_sha,
        scenario=result.scenario,
        ttfb_ms=result.ttfb_ms,
        e2e_latency_ms=result.e2e_latency_ms,
        wer=result.wer,
        mos_estimate=mos,
        notes=json.dumps(notes, separators=(",", ":")),
    )


def _print_table(rows: List[EvalRun], failures: List[str]) -> None:
    header = f"{'architecture':<12} {'scenario':<26} {'ttfb_ms':>8} {'e2e_ms':>8} {'wer':>6} {'mos':>5}"
    print(header)
    print("-" * len(header))
    for row in rows:
        print(
            f"{row.architecture:<12} {row.scenario:<26} "
            f"{row.ttfb_ms if row.ttfb_ms is not None else '-':>8} "
            f"{row.e2e_latency_ms if row.e2e_latency_ms is not None else '-':>8} "
            f"{row.wer if row.wer is not None else '-':>6} "
            f"{row.mos_estimate if row.mos_estimate is not None else '-':>5}"
        )
    for line in failures:
        print(f"FAILED: {line}")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m api.eval_harness",
        description="L5 eval harness: measure the shipped architectures and persist eval_runs rows.",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help=f"target backend (default: $EVAL_BASE_URL or {DEFAULT_BASE_URL})",
    )
    parser.add_argument(
        "--architecture",
        choices=[*RUNNERS, "all"],
        default="all",
        help="architecture to evaluate (default: all)",
    )
    parser.add_argument(
        "--scenario",
        default=None,
        help="scenario fixture name (default: every fixture in scenarios/)",
    )
    parser.add_argument(
        "--vb-session",
        default=None,
        help="completed Vocal Bridge session id — enables the vb eval MOS leg",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print results without writing to BigQuery",
    )
    args = parser.parse_args(argv)

    # Env is read here, not at import — the module must import credential-free.
    import os

    base_url = args.base_url or os.environ.get("EVAL_BASE_URL", "").strip() or DEFAULT_BASE_URL

    try:
        scenarios = load_scenarios()
    except ScenarioError as exc:
        print(f"scenario fixture error: {exc}", file=sys.stderr)
        return 2
    if args.scenario is not None:
        available = [s.name for s in scenarios]
        scenarios = [s for s in scenarios if s.name == args.scenario]
        if not scenarios:
            print(
                f"unknown scenario '{args.scenario}'; available: {', '.join(available)}",
                file=sys.stderr,
            )
            return 2

    architectures = list(RUNNERS) if args.architecture == "all" else [args.architecture]
    git_sha = resolve_git_sha()

    rows: List[EvalRun] = []
    failures: List[str] = []
    for scenario in scenarios:
        # One MOS verdict per scenario (vb eval judges a whole completed
        # call); it rides on every row this invocation writes, with the
        # session id in notes so the provenance is unambiguous.
        mos: Optional[float] = None
        mos_note: Optional[str] = None
        if args.vb_session:
            mos, mos_note = eval_vb_session(args.vb_session, scenario.objective)

        for architecture in architectures:
            print(f"running {architecture} × {scenario.name} against {base_url} …")
            result = RUNNERS[architecture](base_url, scenario)
            if result.failed:
                failures.append(f"{architecture} × {scenario.name}: no successful measurements")
                continue
            rows.append(_build_row(result, git_sha, base_url, mos, mos_note))

    _print_table(rows, failures)

    if not rows:
        print("every run failed; nothing to persist", file=sys.stderr)
        return 1

    if args.dry_run:
        print(f"dry run: {len(rows)} row(s) not written")
        return 0

    write_failures = 0
    for row in rows:
        ok, _, error = eval_runs_repo.create_run(row)
        if not ok:
            write_failures += 1
            print(f"eval_runs insert failed ({row.architecture} × {row.scenario}): {error}", file=sys.stderr)
    written = len(rows) - write_failures
    print(f"persisted {written}/{len(rows)} row(s) to eval_runs (git_sha={git_sha or 'none'})")
    return 1 if written == 0 else 0


if __name__ == "__main__":
    sys.exit(main())
