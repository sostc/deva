#!/usr/bin/env python3
"""Naja 菜单栏托盘启动器"""
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from AppKit import NSApplication, NSApplicationActivationPolicyAccessory
app = NSApplication.sharedApplication()
app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)

from deva.naja.infra.ui.menu_bar_tray import start_tray

if __name__ == "__main__":
    start_tray()
