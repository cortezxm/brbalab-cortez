"""
Export module
This module provides functionality to export processed data, such as game results
and standings, to external systems like Google Sheets.
"""
from .export import exporter

__all__ = ['exporter']