"""Compatibility wrapper for monitor route handlers."""

from __future__ import annotations

from .monitor.shared_routes import build_monitor_route_handlers


def monitor_route_handlers(ctx):
    return build_monitor_route_handlers(ctx, module_file=__file__)


__all__ = ["monitor_route_handlers"]
