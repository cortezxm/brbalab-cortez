"""
Processing Module

This package provides core classes and utilities for data processing in sports analytics,
including rating calculations, standings formatting, and team abbreviation mappings
for various sports leagues (e.g., EPL, FIFA).

Exports:
    - LeagueParameters: Stores and manages league-specific rating parameters.
    - RatingProcessor: General processor for team ratings and simulations.
    - BaseFormat: Base class for formatting game and standings data for export.
    - team_abbr_EPL: Dictionary mapping English Premier League team names to their abbreviations.
"""

from .rating import LeagueParameters, RatingProcessor
from .format import BaseFormat
from .team_dicts import team_abbr_EPL

__all__ = ['LeagueParameters', 'RatingProcessor', 'BaseFormat', 'team_abbr_EPL']