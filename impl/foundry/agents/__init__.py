"""The eight core agent roles."""
from foundry.agents.indexer import IndexerAgent
from foundry.agents.cartographer import CartographerAgent
from foundry.agents.detector import DetectorAgent
from foundry.agents.triager import TriagerAgent
from foundry.agents.validator import ValidatorAgent
from foundry.agents.coverage_guide import CoverageGuideAgent
from foundry.agents.reporter_agent import ReporterAgent

__all__ = [
    "IndexerAgent",
    "CartographerAgent",
    "DetectorAgent",
    "TriagerAgent",
    "ValidatorAgent",
    "CoverageGuideAgent",
    "ReporterAgent",
]
