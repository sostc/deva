"""macOS 登录启动项管理器

通过创建 LaunchAgent plist 实现登录时自动启动 Naja
"""

import logging
import os
import plistlib
import subprocess
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

LAUNCH_AGENT_NAME = "com.naja.autostart"
LAUNCH_AGENT_LABEL = f"com.naja.autostart"
PLIST_FILENAME = f"{LAUNCH_AGENT_LABEL}.plist"


def _get_launch_agent_path() -> Path:
    """获取 LaunchAgent plist 文件路径"""
    return Path.home() / "Library" / "LaunchAgents" / PLIST_FILENAME


def _get_launch_agent_dir() -> Path:
    """获取 LaunchAgents 目录"""
    return Path.home() / "Library" / "LaunchAgents"


def _build_launch_agent_plist() -> dict:
    """构建 LaunchAgent plist 内容。

    注意：不再配置 StandardOutPath/StandardErrorPath，避免 launchd 写入的
    autostart.log 无限累积。Naja 和 tray 进程内部已有自己的轮转日志。
    """
    python_executable = sys.executable

    working_dir = str(Path(__file__).parent.parent.parent.parent.parent)

    return {
        "Label": LAUNCH_AGENT_LABEL,
        "ProgramArguments": [
            python_executable,
            "-m",
            "deva.naja",
            "-s",
            "start",
        ],
        "RunAtLoad": True,
        "KeepAlive": False,
        "WorkingDirectory": working_dir,
        "EnvironmentVariables": {
            "NAJA_AUTOSTART": "1",
        },
    }


def _load_plist(path: Path) -> Optional[dict]:
    """加载 plist 文件"""
    try:
        if path.exists():
            with open(path, "rb") as f:
                return plistlib.load(f)
    except Exception as e:
        logger.error(f"加载 plist 失败: {e}")
    return None


def is_login_item_enabled() -> bool:
    """检查登录启动项是否启用"""
    plist_path = _get_launch_agent_path()
    plist_data = _load_plist(plist_path)
    
    if plist_data is None:
        return False
    
    return plist_data.get("RunAtLoad", False) and plist_data.get("Label") == LAUNCH_AGENT_LABEL


def enable_login_item() -> bool:
    """启用登录启动项"""
    try:
        launch_dir = _get_launch_agent_dir()
        launch_dir.mkdir(parents=True, exist_ok=True)
        
        naja_logs_dir = Path.home() / ".naja" / "logs"
        naja_logs_dir.mkdir(parents=True, exist_ok=True)
        
        plist_path = _get_launch_agent_path()
        plist_data = _build_launch_agent_plist()
        
        with open(plist_path, "wb") as f:
            plistlib.dump(plist_data, f)
        
        logger.info(f"已创建登录启动项 plist: {plist_path}")
        
        try:
            subprocess.run(
                ["launchctl", "load", str(plist_path)],
                capture_output=True,
                timeout=5,
            )
            logger.info("已加载 LaunchAgent")
        except Exception as e:
            logger.warning(f"加载 LaunchAgent 失败 (可能需要重启后生效): {e}")
        
        return True
        
    except Exception as e:
        logger.error(f"启用登录启动项失败: {e}")
        return False


def disable_login_item() -> bool:
    """禁用登录启动项"""
    try:
        plist_path = _get_launch_agent_path()
        
        if not plist_path.exists():
            logger.info("登录启动项 plist 不存在，视为已禁用")
            return True
        
        try:
            subprocess.run(
                ["launchctl", "unload", str(plist_path)],
                capture_output=True,
                timeout=5,
            )
            logger.info("已卸载 LaunchAgent")
        except Exception as e:
            logger.warning(f"卸载 LaunchAgent 失败: {e}")
        
        plist_path.unlink(missing_ok=True)
        logger.info(f"已删除登录启动项 plist: {plist_path}")
        
        return True
        
    except Exception as e:
        logger.error(f"禁用登录启动项失败: {e}")
        return False


def toggle_login_item() -> bool:
    """切换登录启动项状态"""
    if is_login_item_enabled():
        return disable_login_item()
    else:
        return enable_login_item()
