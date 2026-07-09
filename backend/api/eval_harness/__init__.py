"""Evaluation harness — the L5 course port (Phase 11).

On-demand CLI that measures the shipped voice architectures over HTTP
(TTFB/e2e latency, WER via a TTS→STT round trip, MOS-style quality via
`vb eval`) and persists one `eval_runs` row per architecture × scenario,
stamped with git SHA. Run as `python -m api.eval_harness` (or `make eval`).

Importing this package needs no credentials, no network, no `vb` binary —
everything external is read per call, the standing repo rule.
"""
