"""Data dictionary admin module."""

from .dictionary_service import get_dictionary_manager
from .dictionary_panel import render_dictionary_admin
from .dictionary_v2 import (
    get_dictionary_manager as get_dictionary_manager_v2,
    DictionaryManager,
    DictionaryEntry,
)
from .dictionary_v2_panel import render_dictionary_v2_admin

__all__ = [
    "get_dictionary_manager",
    "render_dictionary_admin",
    "get_dictionary_manager_v2",
    "DictionaryManager",
    "DictionaryEntry",
    "render_dictionary_v2_admin",
]
