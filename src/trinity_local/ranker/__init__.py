"""Routing policy layer: unified interface for provider recommendations."""
from __future__ import annotations

from .base import Ranker
from .types import RoutingContext, RoutingDecision

__all__ = ["Ranker", "RoutingContext", "RoutingDecision", "build_default_ranker"]


def build_default_ranker() -> Ranker:
    """Factory for the default ranker.

    Currently returns a FallbackRanker (heuristic + k-NN with graceful fallback).
    Will be the integration point for watcher migration (step 5).

    Raises:
        NotImplementedError: Until backends are implemented (step 2–4).
    """
    raise NotImplementedError("Ranker backends not yet implemented. See step 2–4.")
