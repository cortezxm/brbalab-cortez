"""
Data Acquisition Module

This module handles scraping football league data from external sources.
"""

from .scraper import EPLScraper, BaseScraper, LeagueConfig, get_epl_season_year

__all__ = ['EPLScraper', 'BaseScraper', 'LeagueConfig', 'get_epl_season_year']