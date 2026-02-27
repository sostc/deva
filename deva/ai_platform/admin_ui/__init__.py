"""Admin modularized components."""

# Core modules
from . import runtime
from . import auth_routes
from . import contexts
from . import main_ui
from . import menus

# Feature modules
from . import tasks
from . import ai
from . import datasource
from . import document
from . import monitor
from . import tables
from . import config
from . import follow
from . import browser

# Strategy module (complex submodule)
from . import strategy

__all__ = [
    # Core
    'runtime',
    'auth_routes',
    'contexts',
    'main_ui',
    'menus',
    # Features
    'tasks',
    'ai',
    'datasource',
    'document',
    'monitor',
    'tables',
    'config',
    'follow',
    'browser',
    # Strategy
    'strategy',
]
