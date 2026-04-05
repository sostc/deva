"""
Backward-compatibility wrapper for sector_narrative → narrative_tracker

This module is DEPRECATED. All new code should import from narrative_tracker.
"""

from deva.naja.cognition.narrative_tracker import (
    NarrativeTracker,
    TIANDAO_KEYWORDS,
    MINXIN_KEYWORDS,
    get_narrative_tracker,
)

SectorNarrative = NarrativeTracker

__all__ = [
    "NarrativeTracker",
    "SectorNarrative",
    "TIANDAO_KEYWORDS",
    "MINXIN_KEYWORDS",
    "get_narrative_tracker",
]
