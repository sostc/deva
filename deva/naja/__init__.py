"""Naja - 统一可恢复单元管理平台

基于 RecoverableUnit 抽象的统一管理平台。
"""

import importlib

__version__ = "2.0.0"


# ---------------------------------------------------------------------------
# 包级重导出 → 按需加载（PEP 562）
# ---------------------------------------------------------------------------
# 这些名字原先在包导入时就 eager 引入 .signal / .radar / .tasks / .strategy /
# .dictionary / .supervisor，而这些子模块会传递性拉入
# pywebio / pandas / bokeh / requests_html 等重库（实测约 1.1s）。
# 托盘与 CLI 启动根本用不到它们，却要为每次 `import deva.naja.*` 买单。
#
# 因此改为惰性：第一次访问 deva.naja.<Name> 时才导入对应子模块，并缓存结果。
# `from deva.naja import <Name>` 同样可用（Python 会回调模块级 __getattr__）。
_LAZY_EXPORTS = {
    # infra.runtime.recoverable
    "RecoverableUnit": ".infra.runtime.recoverable",
    "UnitMetadata": ".infra.runtime.recoverable",
    "UnitState": ".infra.runtime.recoverable",
    "UnitStatus": ".infra.runtime.recoverable",
    "RecoveryManager": ".infra.runtime.recoverable",
    "recovery_manager": ".infra.runtime.recoverable",
    # tasks
    "TaskEntry": ".tasks",
    "TaskManager": ".tasks",
    # strategy
    "StrategyEntry": ".strategy",
    "StrategyManager": ".strategy",
    "get_strategy_manager": ".strategy",
    # dictionary
    "DictionaryEntry": ".dictionary",
    "DictionaryManager": ".dictionary",
    # signal
    "render_signal_page": ".signal",
    # radar
    "RadarEngine": ".radar",
    "get_radar_engine": ".radar",
    # supervisor
    "NajaSupervisor": ".supervisor",
    "get_naja_supervisor": ".supervisor",
    "stop_supervisor": ".supervisor",
}


__all__ = [
    # Base
    "RecoverableUnit",
    "UnitMetadata",
    "UnitState",
    "UnitStatus",
    "RecoveryManager",
    "recovery_manager",
    # Task
    "TaskEntry",
    "TaskManager",
    # Strategy
    "StrategyEntry",
    "StrategyManager",
    "get_strategy_manager",
    # Dictionary
    "DictionaryEntry",
    "DictionaryManager",
    # Signal
    "render_signal_page",
    # Radar
    "RadarEngine",
    "get_radar_engine",
    # Supervisor
    "NajaSupervisor",
    "get_naja_supervisor",
    "stop_supervisor",
]


def __getattr__(name):
    """PEP 562：惰性解析被重导出的名字。"""
    module_path = _LAZY_EXPORTS.get(name)
    if module_path is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module = importlib.import_module(module_path, __name__)
    value = getattr(module, name)
    globals()[name] = value  # 缓存，后续访问不再进入 __getattr__
    return value


def __dir__():
    return sorted(set(globals()) | set(_LAZY_EXPORTS))
