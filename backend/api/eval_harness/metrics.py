"""Metrics core for the eval harness (L5 port) — pure functions, no I/O.

WER is the standard word-level Levenshtein distance over the reference length,
implemented with the stdlib so the harness adds no dependency. The MOS mapping
takes the 0–10 score `vb eval`'s LLM judge returns and projects it onto the
1–5 MOS-style scale the `eval_runs.mos_estimate` column expects.
"""
from __future__ import annotations

import re
from statistics import mean, median
from typing import Dict, List, Optional


_WORD_RE = re.compile(r"[a-z0-9']+")


def _words(text: str) -> List[str]:
    """Normalize to comparable words: lowercase, punctuation-insensitive."""
    return _WORD_RE.findall(text.lower())


def wer(reference: str, hypothesis: str) -> float:
    """Word error rate: (substitutions + insertions + deletions) / reference
    words. 0.0 for a perfect match; can exceed 1.0 when the hypothesis is
    longer and entirely wrong."""
    ref = _words(reference)
    hyp = _words(hypothesis)
    if not ref:
        return 0.0 if not hyp else 1.0

    # Two-row Levenshtein over words.
    previous = list(range(len(hyp) + 1))
    for i, ref_word in enumerate(ref, start=1):
        current = [i] + [0] * len(hyp)
        for j, hyp_word in enumerate(hyp, start=1):
            cost = 0 if ref_word == hyp_word else 1
            current[j] = min(
                previous[j] + 1,        # deletion
                current[j - 1] + 1,     # insertion
                previous[j - 1] + cost, # substitution / match
            )
        previous = current
    return previous[-1] / len(ref)


def mos_from_vb_score(score: float) -> float:
    """Map a `vb eval` 0–10 judge score onto the 1–5 MOS-style scale.
    Out-of-range scores clamp rather than extrapolate."""
    clamped = max(0.0, min(10.0, float(score)))
    return 1.0 + (clamped / 10.0) * 4.0


def summarize_latencies(samples_ms: List[float]) -> Dict[str, Optional[float]]:
    """Mean/p50/max/count over latency samples. The mean feeds the eval_runs
    row; the rest ride along in notes."""
    if not samples_ms:
        return {"count": 0, "mean_ms": None, "p50_ms": None, "max_ms": None}
    return {
        "count": len(samples_ms),
        "mean_ms": round(mean(samples_ms), 1),
        "p50_ms": round(median(samples_ms), 1),
        "max_ms": round(max(samples_ms), 1),
    }
