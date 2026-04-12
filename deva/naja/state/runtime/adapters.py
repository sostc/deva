"""运行时状态组件适配器

将现有组件适配到 StatefulComponent 接口。
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List

from .manager import StatefulComponent
from deva.naja.register import SR

logger = logging.getLogger(__name__)


class DataSourceManagerAdapter(StatefulComponent):
    """DataSourceManager 适配器"""

    def __init__(self, manager):
        self._manager = manager

    @property
    def persistence_id(self) -> str:
        return "datasource_manager"

    @property
    def persistence_table(self) -> str:
        return "naja_datasources"

    @property
    def persistence_priority(self) -> int:
        return 10

    @property
    def persistence_type(self) -> str:
        return "DataSourceManager"

    @property
    def persistence_name(self) -> str:
        return "数据源管理器"

    def load_state(self) -> bool:
        try:
            self._manager.load_prefer_files()
            return True
        except Exception as e:
            logger.error(f"[DataSourceManagerAdapter] 加载失败: {e}")
            return False

    def save_state(self) -> bool:
        try:
            from deva import NB
            db = NB(self.persistence_table)

            with self._manager._items_lock:
                entries = list(self._manager._items.values())

            for entry in entries:
                if entry.is_running:
                    entry.save()

            return True
        except Exception as e:
            logger.error(f"[DataSourceManagerAdapter] 保存失败: {e}")
            return False

    def verify_state(self) -> bool:
        with self._manager._items_lock:
            return len(self._manager._items) >= 0


class TaskManagerAdapter(StatefulComponent):
    """TaskManager 适配器"""

    def __init__(self, manager):
        self._manager = manager

    @property
    def persistence_id(self) -> str:
        return "task_manager"

    @property
    def persistence_table(self) -> str:
        return "naja_tasks"

    @property
    def persistence_priority(self) -> int:
        return 20

    @property
    def persistence_type(self) -> str:
        return "TaskManager"

    @property
    def persistence_name(self) -> str:
        return "任务管理器"

    def load_state(self) -> bool:
        try:
            self._manager.load_prefer_files()
            return True
        except Exception as e:
            logger.error(f"[TaskManagerAdapter] 加载失败: {e}")
            return False

    def save_state(self) -> bool:
        try:
            from deva import NB
            db = NB(self.persistence_table)

            with self._manager._items_lock:
                entries = list(self._manager._items.values())

            saved_count = 0
            for entry in entries:
                if entry.is_running:
                    entry._was_running = True
                    entry.save()
                    saved_count += 1

            logger.info(f"[TaskManagerAdapter] 已保存 {saved_count} 个运行中的任务状态")
            return True
        except Exception as e:
            logger.error(f"[TaskManagerAdapter] 保存失败: {e}")
            return False

    def verify_state(self) -> bool:
        return True


class StrategyManagerAdapter(StatefulComponent):
    """StrategyManager 适配器"""

    def __init__(self, manager):
        self._manager = manager

    @property
    def persistence_id(self) -> str:
        return "strategy_manager"

    @property
    def persistence_table(self) -> str:
        return "naja_strategies"

    @property
    def persistence_priority(self) -> int:
        return 30

    @property
    def persistence_type(self) -> str:
        return "StrategyManager"

    @property
    def persistence_name(self) -> str:
        return "策略管理器"

    def load_state(self) -> bool:
        try:
            self._manager.load_prefer_files()
            return True
        except Exception as e:
            logger.error(f"[StrategyManagerAdapter] 加载失败: {e}")
            return False

    def save_state(self) -> bool:
        try:
            from deva import NB
            db = NB(self.persistence_table)

            with self._manager._items_lock:
                entries = list(self._manager._items.values())

            saved_count = 0
            for entry in entries:
                if entry.is_running:
                    entry._was_running = True
                    entry.save()
                    saved_count += 1

            logger.info(f"[StrategyManagerAdapter] 已保存 {saved_count} 个运行中的策略状态")
            return True
        except Exception as e:
            logger.error(f"[StrategyManagerAdapter] 保存失败: {e}")
            return False

    def verify_state(self) -> bool:
        return True


class AttentionCenterAdapter(StatefulComponent):
    """AttentionCenter 适配器"""

    def __init__(self, center):
        self._center = center

    @property
    def persistence_id(self) -> str:
        return "attention_center"

    @property
    def persistence_table(self) -> str:
        return "naja_attention_tracker"

    @property
    def persistence_priority(self) -> int:
        return 40

    @property
    def persistence_type(self) -> str:
        return "AttentionCenter"

    @property
    def persistence_name(self) -> str:
        return "注意力中心"

    def load_state(self) -> bool:
        try:
            if hasattr(self._center, 'load_state'):
                self._center.load_state(self._center.get_state() if hasattr(self._center, 'get_state') else {})
            return True
        except Exception as e:
            logger.error(f"[AttentionCenterAdapter] 加载失败: {e}")
            return False

    def save_state(self) -> bool:
        try:
            if hasattr(self._center, 'persist_state'):
                self._center.persist_state()
            return True
        except Exception as e:
            logger.error(f"[AttentionCenterAdapter] 保存失败: {e}")
            return False

    def verify_state(self) -> bool:
        return True


class BanditRunnerAdapter(StatefulComponent):
    """BanditRunner 适配器"""

    def __init__(self, runner):
        self._runner = runner

    @property
    def persistence_id(self) -> str:
        return "bandit_runner"

    @property
    def persistence_table(self) -> str:
        return "naja_bandit_config"

    @property
    def persistence_priority(self) -> int:
        return 50

    @property
    def persistence_type(self) -> str:
        return "BanditRunner"

    @property
    def persistence_name(self) -> str:
        return "Bandit 策略选择器"

    def load_state(self) -> bool:
        try:
            return True
        except Exception as e:
            logger.error(f"[BanditRunnerAdapter] 加载失败: {e}")
            return False

    def save_state(self) -> bool:
        try:
            if hasattr(self._runner, 'save_state'):
                self._runner.save_state()
            return True
        except Exception as e:
            logger.error(f"[BanditRunnerAdapter] 保存失败: {e}")
            return False

    def verify_state(self) -> bool:
        return True


class RadarEngineAdapter(StatefulComponent):
    """RadarEngine 适配器"""

    def __init__(self, radar):
        self._radar = radar

    @property
    def persistence_id(self) -> str:
        return "radar_engine"

    @property
    def persistence_table(self) -> str:
        return "naja_radar_events"

    @property
    def persistence_priority(self) -> int:
        return 60

    @property
    def persistence_type(self) -> str:
        return "RadarEngine"

    @property
    def persistence_name(self) -> str:
        return "新闻雷达"

    def load_state(self) -> bool:
        try:
            if hasattr(self._radar, 'load_state'):
                self._radar.load_state()
            return True
        except Exception as e:
            logger.error(f"[RadarEngineAdapter] 加载失败: {e}")
            return False

    def save_state(self) -> bool:
        try:
            if hasattr(self._radar, 'save_state'):
                self._radar.save_state()
            return True
        except Exception as e:
            logger.error(f"[RadarEngineAdapter] 保存失败: {e}")
            return False

    def verify_state(self) -> bool:
        return True


class SignalTunerAdapter(StatefulComponent):
    """SignalTuner 信号调谐器适配器"""

    def __init__(self, tuner):
        self._tuner = tuner

    @property
    def persistence_id(self) -> str:
        return "signal_tuner"

    @property
    def persistence_table(self) -> str:
        return "naja_signal_tuner"

    @property
    def persistence_priority(self) -> int:
        return 35

    @property
    def persistence_type(self) -> str:
        return "SignalTuner"

    @property
    def persistence_name(self) -> str:
        return "信号调谐器"

    def load_state(self) -> bool:
        try:
            self._tuner._load_state()
            return True
        except Exception as e:
            logger.error(f"[SignalTunerAdapter] 加载失败: {e}")
            return False

    def save_state(self) -> bool:
        try:
            self._tuner._save_state()
            return True
        except Exception as e:
            logger.error(f"[SignalTunerAdapter] 保存失败: {e}")
            return False

    def verify_state(self) -> bool:
        return True


def register_all_adapters():
    """注册所有适配器到 RuntimeStateManager

    在系统启动时调用此函数注册所有组件。
    """
    from .manager import get_runtime_state_manager

    mgr = get_runtime_state_manager()

    # 数据源管理器
    try:
        from deva.naja.datasource import get_datasource_manager
        ds_mgr = get_datasource_manager()
        mgr.register(DataSourceManagerAdapter(ds_mgr))
        logger.info("[RuntimeStateManager] 已注册 DataSourceManager")
    except Exception as e:
        logger.warning(f"[RuntimeStateManager] DataSourceManager 注册失败: {e}")

    # 任务管理器
    try:
        task_mgr = SR('task_manager')
        mgr.register(TaskManagerAdapter(task_mgr))
        logger.info("[RuntimeStateManager] 已注册 TaskManager")
    except Exception as e:
        logger.warning(f"[RuntimeStateManager] TaskManager 注册失败: {e}")

    # 策略管理器
    try:
        from deva.naja.strategy import get_strategy_manager
        strategy_mgr = get_strategy_manager()
        mgr.register(StrategyManagerAdapter(strategy_mgr))
        logger.info("[RuntimeStateManager] 已注册 StrategyManager")
    except Exception as e:
        logger.warning(f"[RuntimeStateManager] StrategyManager 注册失败: {e}")

    # 注意力中心
    try:
        attention = SR('hotspot_system')
        if attention:
            mgr.register(AttentionCenterAdapter(attention))
            logger.info("[RuntimeStateManager] 已注册 AttentionCenter")
    except Exception as e:
        logger.warning(f"[RuntimeStateManager] AttentionCenter 注册失败: {e}")

    # Bandit Runner
    try:
        bandit = SR('bandit_runner')
        mgr.register(BanditRunnerAdapter(bandit))
        logger.info("[RuntimeStateManager] 已注册 BanditRunner")
    except Exception as e:
        logger.warning(f"[RuntimeStateManager] BanditRunner 注册失败: {e}")

    # 雷达引擎
    try:
        from deva.naja.radar import get_radar_engine
        radar = get_radar_engine()
        mgr.register(RadarEngineAdapter(radar))
        logger.info("[RuntimeStateManager] 已注册 RadarEngine")
    except Exception as e:
        logger.warning(f"[RuntimeStateManager] RadarEngine 注册失败: {e}")

    # SignalTuner 信号调谐器
    try:
        tuner = SR('signal_tuner')
        if tuner:
            mgr.register(SignalTunerAdapter(tuner))
            logger.info("[RuntimeStateManager] 已注册 SignalTuner")
    except Exception as e:
        logger.warning(f"[RuntimeStateManager] SignalTuner 注册失败: {e}")

    logger.info(f"[RuntimeStateManager] 共注册 {len(mgr.list_all())} 个组件")