"""Menu configuration and management for Deva Admin UI.

This module centralizes all menu-related configuration and rendering logic.
"""

from .config import (
    MenuItem,
    MAIN_MENU_ITEMS,
    SIDEBAR_CONFIG,
    get_menu_items,
    get_menu_paths,
    get_menu_item_by_path,
    add_menu_item,
    remove_menu_item,
)
from .renderer import create_nav_menu, create_sidebar, init_floating_menu_manager

__all__ = [
    # Configuration
    'MenuItem',
    'MAIN_MENU_ITEMS',
    'SIDEBAR_CONFIG',
    # Rendering functions
    'create_nav_menu',
    'create_sidebar',
    'init_floating_menu_manager',
    # Helper functions
    'get_menu_items',
    'get_menu_paths',
    'get_menu_item_by_path',
    'add_menu_item',
    'remove_menu_item',
]
