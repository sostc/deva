#!/usr/bin/env python3
"""Naja 菜单栏托盘启动器"""
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from AppKit import NSApplication, NSApplicationActivationPolicyAccessory
app = NSApplication.sharedApplication()
# 声明为 accessory 应用：不显示 Dock 图标、不出现在 Cmd+Tab
app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)

# rumps.App.run() 内部会调用 activateIgnoringOtherApps_(True)，
# 该调用会让 Dock 图标持续跳动以吸引用户注意。
# 托盘应用本就不该抢焦点，这里将其替换为 no-op，从根源杜绝跳动。
def _activate_noop(self, flag):
    return None
NSApplication.activateIgnoringOtherApps_ = _activate_noop

from deva.naja.infra.runtime.daemon import sanitize_proxy_env
from deva.naja.infra.ui.menu_bar_tray import start_tray

if __name__ == "__main__":
    # 托盘进程可能在「-s start」派生时继承一个已失效的本地代理，而
    # 「一键总结」是在托盘进程内直接请求大模型 → 必须确保出口可用。
    sanitize_proxy_env()
    start_tray()
