"""Routing policy layer: unified interface for provider recommendations."""
from __future__ import annotations

from .base import Ranker
from .fallback import FallbackRanker
from .types import RoutingContext, RoutingDecision

__all__ = ["Ranker", "RoutingContext", "RoutingDecision", "build_default_ranker"]


def build_default_ranker() -> Ranker:
    """Factory for the default ranker.

    Returns FallbackRanker: tries k-NN advisory (heuristic + embeddings),
    falls back to pure heuristic if k-NN unavailable.

    This is the main backend for watcher routing (step 5+).
    """
    return FallbackRanker()
