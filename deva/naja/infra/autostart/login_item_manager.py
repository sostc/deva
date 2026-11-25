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


#: 交易模式的**部署默认值**（本机开关的唯一权威处）。
#:
#: ❗为什么放在这里：``NAJA_EXEC_BACKEND`` 决定 Bandit 往哪儿报单。代码里的
#: 默认值仍是 ``virtual``（装上代码不会自动开始报单），但**本机要跑模拟交易**
#: 就必须显式写进 LaunchAgent 的环境变量，否则每次重启都静默回到虚拟仓——
#: 「以为在跑模拟盘，其实一笔都没成交」。
#:
#: ❗真实交易在这套系统里**没有实现**：``execution.BACKENDS`` 只有
#: ``virtual`` / ``futu_sim``，``place_order`` 的唯一调用点硬编码
#: ``TrdEnv.SIMULATE``。所以这里的 ``futu_sim`` 就是「模拟交易开」，
#: 而「真实交易关」不是靠某个 0/1 开关，是**没有这条代码路径**。
#: 守卫 ``verify_trade_mode_sim_only.py`` 钉住这两件事。
TRADE_ENV_DEFAULTS = {
    # 模拟交易：开（报价 / 报单都路由到富途模拟账户）
    "NAJA_EXEC_BACKEND": "futu_sim",
    # 做 T 走富途模拟账户（三个市场各一份模拟仓）
    "NAJA_T_ROTATION_ON_SIM": "1",
    # 守望台执行腿：关。它会把「批准」直接变成报单，属另一层授权，
    # 要开必须单独置 1，不跟着模拟交易一起被打开。
    "NAJA_WATCH_EXEC_ENABLED": "0",
}


def _merge_env(existing: Optional[dict]) -> dict:
    """合并环境变量：**已有的显式设置优先**，默认值只补缺失项。

    ❗原实现每次都用一份写死的 ``{"NAJA_AUTOSTART": "1"}`` 重建 plist，
    把手工加进去的 ``NAJA_T_ROTATION_SYMBOLS`` / ``NAJA_T_ROTATION_ON_SIM``
    全抹掉 —— 用户在托盘里点一下「登录时自动启动」，做 T 就静默退回虚拟盘。
    这类「配置被静默重置」比报错危险得多，故必须合并而不是覆盖。
    """
    env: dict = {}
    for key, value in (existing or {}).items():
        if isinstance(value, (str, int, float, bool)):
            env[str(key)] = str(value)
    for key, value in TRADE_ENV_DEFAULTS.items():
        env.setdefault(key, value)
    env["NAJA_AUTOSTART"] = "1"
    return env


def _build_launch_agent_plist(existing_env: Optional[dict] = None) -> dict:
    """构建 LaunchAgent plist 内容。

    注意：不再配置 StandardOutPath/StandardErrorPath，避免 launchd 写入的
    autostart.log 无限累积。Naja 和 tray 进程内部已有自己的轮转日志。

    Args:
        existing_env: 现有 plist 的 ``EnvironmentVariables``。传入则**合并**
            （已有优先），不传则只写默认值——两者都会保证交易模式默认值在场。
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
        "EnvironmentVariables": _merge_env(existing_env),
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
        # 先读现有 plist 的环境变量再合并 —— 否则会把手工配置的
        # NAJA_T_ROTATION_SYMBOLS / NAJA_EXEC_BACKEND 一起抹掉。
        current = _load_plist(plist_path) or {}
        plist_data = _build_launch_agent_plist(
            existing_env=current.get("EnvironmentVariables")
        )
        
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
