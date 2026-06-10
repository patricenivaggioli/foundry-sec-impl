"""Configuration models — aligned with spec §12 and the demo CLI."""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field


class SubstrateConfig(BaseModel):
    dsn: str


class LLMConfig(BaseModel):
    provider: Literal["mistral", "mock"] = "mistral"
    strong_model: str = "mistral-large-latest"
    bulk_model: str = "mistral-small-latest"
    region: Literal["eu", "us"] = "eu"


class TargetConfig(BaseModel):
    path: str
    revision: str = "HEAD"
    include: list[str] = Field(default_factory=lambda: ["**/*.py"])
    exclude: list[str] = Field(default_factory=lambda: ["**/test_*.py", "**/.venv/**"])


class BudgetConfig(BaseModel):
    tokens: int = 200_000
    wallclock_seconds: int = 600
    spend_cap_cents: int = 1000
    yield_threshold: float = 0.0


class ConcurrencyConfig(BaseModel):
    detector: int = 2
    triager: int = 2
    validator: int = 1


class GoalsConfig(BaseModel):
    attack_goals: list[str] = Field(default_factory=list)
    scope_backlog: list[str] = Field(default_factory=list)


class TestbedConfig(BaseModel):
    description: str = "docker-mock"
    endpoints: list[str] = Field(default_factory=list)


class EvaluationConfig(BaseModel):
    name: str
    substrate: SubstrateConfig
    llm: LLMConfig = Field(default_factory=LLMConfig)
    target: TargetConfig
    budget: BudgetConfig = Field(default_factory=BudgetConfig)
    concurrency: ConcurrencyConfig = Field(default_factory=ConcurrencyConfig)
    goals: GoalsConfig = Field(default_factory=GoalsConfig)
    testbed: TestbedConfig = Field(default_factory=TestbedConfig)

    @classmethod
    def load(cls, path: str | Path) -> "EvaluationConfig":
        text = Path(path).read_text()
        text = _resolve_env(text)
        data = yaml.safe_load(text)
        return cls.model_validate(data)


def _resolve_env(text: str) -> str:
    def sub(m: re.Match[str]) -> str:
        name = m.group(1)
        val = os.environ.get(name)
        if val is None:
            raise ValueError(f"Config references env var ${{{name}}} but it is not set")
        return val

    return re.sub(r"\$\{env:([A-Z0-9_]+)\}", sub, text)
