#!/usr/bin/env python3
"""Naja 菜单栏托盘进程"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from AppKit import NSApplication, NSApplicationActivationPolicyAccessory
app = NSApplication.sharedApplication()
app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)

from deva.naja.infra.ui.menu_bar_tray import start_tray

if __name__ == "__main__":
    start_tray()
