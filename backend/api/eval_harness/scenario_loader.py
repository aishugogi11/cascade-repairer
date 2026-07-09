"""Scenario fixtures for the eval harness.

Scenarios are reviewable YAML checked into `scenarios/` — no audio binaries.
`ground_truth` feeds the TTS→STT WER round trip; `objective` is what makes
the `vb eval` MOS leg meaningful (L5: without one, the LLM is grading vibes).
Loader errors always name the offending file.
"""
from __future__ import annotations

from pathlib import Path
from typing import List

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator

SCENARIOS_DIR = Path(__file__).parent / "scenarios"


class ScenarioError(ValueError):
    """A fixture file is missing, unparseable, or fails validation."""


class Scenario(BaseModel):
    name: str
    description: str
    turns: List[str] = Field(..., min_length=1)
    ground_truth: str
    objective: str

    @field_validator("name", "description", "ground_truth", "objective")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must not be blank")
        return v.strip()

    @field_validator("turns")
    @classmethod
    def _turns_not_blank(cls, v: List[str]) -> List[str]:
        cleaned = [turn.strip() for turn in v]
        if any(not turn for turn in cleaned):
            raise ValueError("turns must not contain blank entries")
        return cleaned


def load_scenario(path: Path) -> Scenario:
    """Load and validate one fixture; raises ScenarioError naming the file."""
    try:
        raw = yaml.safe_load(path.read_text())
    except OSError as exc:
        raise ScenarioError(f"{path.name}: unreadable: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ScenarioError(f"{path.name}: invalid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise ScenarioError(f"{path.name}: expected a YAML mapping")
    try:
        return Scenario(**raw)
    except ValidationError as exc:
        raise ScenarioError(f"{path.name}: {exc}") from exc


def load_scenarios(directory: Path = SCENARIOS_DIR) -> List[Scenario]:
    """All fixtures in the directory, sorted by filename for stable output."""
    return [load_scenario(path) for path in sorted(directory.glob("*.yaml"))]
