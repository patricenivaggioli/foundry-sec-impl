"""Orchestrator — two lanes (FR-010..FR-019).

* Lifecycle lane — synchronous: registers agents, plans phases, dispatches
  bulk tasks (detect_rule batches, coverage ticks, report).
* Converse lane — opportunistic: answers operator queries via the LLM
  (stubbed in this MVP; CLI surface drives it).

The orchestrator does NOT do its own analysis (Principle X).
"""
from foundry.orchestrator.lifecycle import LifecycleOrchestrator

__all__ = ["LifecycleOrchestrator"]
