"""Data dictionary admin module."""

from .dictionary_service import get_dictionary_manager
from .dictionary_panel import render_dictionary_admin

__all__ = [
    "get_dictionary_manager",
    "render_dictionary_admin",
]
