"""
ReplayScheduler - 回放调度器

基于性能反馈的智能调度器，用于数据回放场景：
- 从数据库按时间顺序拉取历史数据
- 按档位过滤（HIGH/MEDIUM/LOW）
- 发送数据给下游，等待处理完成
- 集成 AutoTuner，根据处理性能动态调整间隔

核心流程：
1. ReplayScheduler 处理一批数据
2. 处理完成，记录 execution_time_ms 到 PerformanceMonitor
3. AutoTuner 每60秒检查一次性能指标
4. 发现处理时间过长/过短，调用 trigger_business_adjustment()
5. ReplayScheduler 收到反馈，调整 current_interval
6. 下一批数据按新间隔处理
"""

import threading
import time
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

from deva import NB, log
from deva.naja.register import SR

log = logging.getLogger(__name__)


@dataclass
class ReplayConfig:
    """回放配置"""
    db_table: str = "quant_snapshot_5min_window"
    base_interval: float = 1.0
    min_interval: float = 0.1
    max_interval: float = 10.0
    time_window_seconds: float = 5.0
    playback_speed: float = 1.0

    start_time: Optional[str] = None
    end_time: Optional[str] = None

    enable_level_filter: bool = True
    medium_sample_rate: float = 0.5
    skip_low_level: bool = True


class ReplayScheduler:
    """
    回放调度器 - 基于性能反馈的智能调度

    行为：
    - 从 DB 按时间顺序拉取数据
    - 按档位过滤（HIGH/MEDIUM/LOW）
    - 发送数据给下游，等待完成信号
    - 集成 AutoTuner，根据处理性能动态调整间隔
    """

    _instance: Optional['ReplayScheduler'] = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self, config: Optional[ReplayConfig] = None):
        if getattr(self, '_initialized', False):
            return

        self.config = config or ReplayConfig()

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        self._current_interval = self.config.base_interval
        self._target_interval = self.config.base_interval

        self._fetch_count = 0
        self._error_count = 0
        self._last_fetch_time = 0.0
        self._last_processing_time = 0.0

        self._current_replay_time: Optional[datetime] = None
        self._end_replay_time: Optional[datetime] = None
        self._has_more_data = True

        self._downstream_callback: Optional[Callable] = None
        self._completion_event = threading.Event()
        self._latest_sent_data: Optional[Any] = None
        self._finished_callbacks: List[Callable] = []

        self._db: Optional[Any] = None
        self._data_keys: List[Any] = []
        self._key_index = 0

        self._perf_adjustments = deque(maxlen=100)

        self._register_auto_tuner_callback()

        self._initialized = True
        log.info(f"[ReplayScheduler] 回放调度器初始化完成，配置: {self.config}")

    def _register_auto_tuner_callback(self):
        """注册 AutoTuner 回调"""
        try:
            from deva.naja.common.auto_tuner import get_auto_tuner, trigger_business_adjustment, TuneCondition
            tuner = get_auto_tuner()

            tuner.add_condition('replay_processing', TuneCondition(
                cooldown=30,
                threshold=500,
                action='adjust_replay_interval'
            ))

            self._trigger_adjustment = trigger_business_adjustment
            log.info("[ReplayScheduler] 已注册 AutoTuner 回调")
        except Exception as e:
            log.warning(f"[ReplayScheduler] 无法注册 AutoTuner 回调: {e}")
            self._trigger_adjustment = None

    def set_downstream_callback(self, callback: Callable):
        """设置下游处理完成回调"""
        self._downstream_callback = callback

    def register_finished_callback(self, callback: Callable):
        """注册回放完成回调"""
        self._finished_callbacks.append(callback)

    def on_processing_complete(self, processing_time_ms: float):
        """下游处理完成回调 - 通知性能监控"""
        self._last_processing_time = processing_time_ms

        try:
            from deva.naja.performance import record_component_execution, ComponentType
            record_component_execution(
                component_id="replay_scheduler",
                component_name="ReplayScheduler",
                component_type=ComponentType.DATASOURCE,
                execution_time_ms=processing_time_ms,
                success=True,
            )
        except Exception as e:
            log.debug(f"[ReplayScheduler] 记录性能指标失败: {e}")

        self._completion_event.set()

    def start(self):
        """启动回放调度器"""
        if self._running:
            log.warning("[ReplayScheduler] 已在运行中")
            return

        self._running = True
        self._stop_event.clear()

        self._init_db()
        self._init_replay_time()

        self._enable_market_time_service()

        self._thread = threading.Thread(target=self._fetch_loop, daemon=True)
        self._thread.start()

        log.info(f"[ReplayScheduler] 回放调度器已启动，DB表: {self.config.db_table}")

    def stop(self):
        """停止回放调度器"""
        if not self._running:
            return

        self._running = False
        self._stop_event.set()

        self._disable_market_time_service()

        if self._thread:
            self._thread.join(timeout=5.0)

        log.info("[ReplayScheduler] 回放调度器已停止")

    def _init_db(self):
        """初始化数据库连接"""
        try:
            self._db = NB(self.config.db_table, key_mode='time')
            self._data_keys = list(self._db.keys())

            if self.config.start_time:
                start_dt = datetime.fromisoformat(self.config.start_time)
                start_ts = start_dt.timestamp()
                self._data_keys = [k for k in self._data_keys if float(k) >= start_ts if self._is_numeric_key(k)]

            if self.config.end_time:
                end_dt = datetime.fromisoformat(self.config.end_time)
                end_ts = end_dt.timestamp()
                self._data_keys = [k for k in self._data_keys if float(k) <= end_ts if self._is_numeric_key(k)]

            self._data_keys.sort()
            self._key_index = 0

            log.info(f"[ReplayScheduler] 加载 {len(self._data_keys)} 条数据")
        except Exception as e:
            log.error(f"[ReplayScheduler] 初始化DB失败: {e}")
            self._data_keys = []
            self._has_more_data = False

    def _is_numeric_key(self, key) -> bool:
        """判断key是否为数字类型"""
        try:
            float(key)
            return True
        except (ValueError, TypeError):
            return False

    def _init_replay_time(self):
        """初始化回放时间"""
        if self._data_keys:
            try:
                first_key = self._data_keys[0]
                self._current_replay_time = self._parse_timestamp(first_key)
                if self.config.end_time:
                    self._end_replay_time = datetime.fromisoformat(self.config.end_time)
                else:
                    last_key = self._data_keys[-1]
                    self._end_replay_time = self._parse_timestamp(last_key)
            except Exception as e:
                log.error(f"[ReplayScheduler] 解析回放时间失败: {e}, key={self._data_keys[0]}")
                self._current_replay_time = datetime.now()
                self._end_replay_time = self._current_replay_time + timedelta(hours=1)
        else:
            self._current_replay_time = datetime.now()
            self._end_replay_time = self._current_replay_time + timedelta(hours=1)

    def _parse_timestamp(self, key) -> datetime:
        """解析时间戳或ISO格式"""
        if isinstance(key, (int, float)):
            return datetime.fromtimestamp(key)
        try:
            return datetime.fromisoformat(str(key))
        except Exception:
            return datetime.fromtimestamp(float(key))

    def _fetch_loop(self):
        """主循环"""
        log.info("[ReplayScheduler] 回放循环开始")

        while self._running and not self._stop_event.is_set() and self._has_more_data:
            try:
                self._fetch_and_send()
                self._wait_for_completion()
                self._adjust_interval()
                self._wait_interval()

            except Exception as e:
                self._error_count += 1
                log.error(f"[ReplayScheduler] 回放循环异常: {e}")
                time.sleep(1)

        log.info(f"[ReplayScheduler] 回放循环结束 (fetched={self._fetch_count}, errors={self._error_count})")
        self._running = False

    def _fetch_and_send(self):
        """获取并发送数据"""
        while self._key_index < len(self._data_keys):
            key = self._data_keys[self._key_index]

            if not self._is_numeric_key(key):
                log.debug(f"[ReplayScheduler] 跳过无效key: {key}")
                self._key_index += 1
                continue

            data = self._db.get(key)

            if data is None:
                self._key_index += 1
                continue

            self._last_fetch_time = time.time()
            self._current_replay_time = self._parse_timestamp(key)
            self._fetch_count += 1

            self._update_market_time()

            filtered_data = self._filter_by_level(data)
            self._latest_sent_data = filtered_data  # 存储最后发送的数据

            if self._downstream_callback:
                start_time = time.time()
                self._downstream_callback(filtered_data)
                processing_time = (time.time() - start_time) * 1000
                self.on_processing_complete(processing_time)
            else:
                self._completion_event.set()

            if self._key_index % 10 == 0:
                log.info(f"[ReplayScheduler] 已处理 {self._key_index}/{len(self._data_keys)} 条，"
                        f"当前间隔: {self._current_interval:.2f}s")

            self._key_index += 1
            return

        self._has_more_data = False
        self._emit_finished()

    def _filter_by_level(self, data):
        """按档位过滤数据"""
        if not self.config.enable_level_filter:
            return data

        try:
            from deva.naja.market_hotspot.intelligence.frequency_scheduler import get_frequency_scheduler
            fs = get_frequency_scheduler()

            if fs is None:
                return data

            import pandas as pd
            if isinstance(data, pd.DataFrame):
                if 'code' not in data.columns:
                    return data

                filtered_rows = []
                for _, row in data.iterrows():
                    symbol = row.get('code', '')
                    if not symbol:
                        continue

                    try:
                        level = fs.get_symbol_level(symbol)
                        level_val = level.value if hasattr(level, 'value') else level

                        if level_val == 2:
                            filtered_rows.append(row)
                        elif level_val == 1 and self.config.medium_sample_rate > 0:
                            import random
                            if random.random() < self.config.medium_sample_rate:
                                filtered_rows.append(row)
                        elif level_val == 0 and not self.config.skip_low_level:
                            filtered_rows.append(row)

                    except Exception:
                        filtered_rows.append(row)

                if filtered_rows:
                    return pd.DataFrame(filtered_rows)
                return data

        except Exception as e:
            log.debug(f"[ReplayScheduler] 档位过滤失败: {e}")

        return data

    def _wait_for_completion(self):
        """等待下游处理完成"""
        timeout = max(1.0, self._current_interval * 2)
        self._completion_event.wait(timeout=timeout)
        self._completion_event.clear()

    def _adjust_interval(self):
        """根据 AutoTuner 反馈调整间隔"""
        pass

    def _emit_finished(self):
        """触发回放完成回调"""
        for callback in self._finished_callbacks:
            try:
                callback()
            except Exception as e:
                log.error(f"[ReplayScheduler] 执行完成回调失败: {e}")

    def _wait_interval(self):
        """等待当前间隔"""
        time.sleep(self._current_interval)

    def adjust_interval(self, new_interval: float, reason: str = ""):
        """手动调整间隔（供 AutoTuner 调用）"""
        old_interval = self._current_interval
        self._current_interval = max(
            self.config.min_interval,
            min(new_interval, self.config.max_interval)
        )

        if abs(old_interval - self._current_interval) > 0.01:
            self._perf_adjustments.append({
                'timestamp': time.time(),
                'old': old_interval,
                'new': self._current_interval,
                'reason': reason,
            })
            log.info(f"[ReplayScheduler] 间隔调整: {old_interval:.3f}s -> {self._current_interval:.3f}s ({reason})")

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            'running': self._running,
            'fetch_count': self._fetch_count,
            'error_count': self._error_count,
            'current_interval': self._current_interval,
            'target_interval': self._target_interval,
            'current_replay_time': str(self._current_replay_time) if self._current_replay_time else None,
            'end_replay_time': str(self._end_replay_time) if self._end_replay_time else None,
            'has_more_data': self._has_more_data,
            'progress': f"{self._key_index}/{len(self._data_keys)}" if self._data_keys else "0/0",
            'last_processing_time_ms': self._last_processing_time,
        }

    def _enable_market_time_service(self):
        """启用市场时间服务（回放模式）"""
        try:
            mts = SR('market_time_service')
            mts.set_replay_mode(True)
            log.info("[ReplayScheduler] 已启用市场时间服务（回放模式）")
        except Exception as e:
            log.warning(f"[ReplayScheduler] 无法启用市场时间服务: {e}")

    def _update_market_time(self):
        """更新市场时间服务的时间"""
        if self._current_replay_time is None:
            return
        try:
            mts = SR('market_time_service')
            replay_ts = self._current_replay_time.timestamp()
            mts.set_market_time(replay_ts)
            log.debug(f"[ReplayScheduler] 更新市场时间: {self._current_replay_time}")
        except Exception as e:
            log.debug(f"[ReplayScheduler] 更新市场时间失败: {e}")

    def _disable_market_time_service(self):
        """关闭市场时间服务（回放结束时）"""
        try:
            mts = SR('market_time_service')
            mts.set_replay_mode(False)
            log.info("[ReplayScheduler] 已关闭市场时间服务（退出回放模式）")
        except Exception as e:
            log.warning(f"[ReplayScheduler] 无法关闭市场时间服务: {e}")

    def set_interval(self, interval: float):
        """设置目标间隔（供外部调用）"""
        self._target_interval = max(
            self.config.min_interval,
            min(interval, self.config.max_interval)
        )


def create_replay_scheduler(config: ReplayConfig) -> ReplayScheduler:
    """创建回放调度器（单例模式，直接委托给 ReplayScheduler.__new__）"""
    return ReplayScheduler(config)


def get_replay_scheduler() -> Optional[ReplayScheduler]:
    """获取当前回放调度器实例（如果已创建）"""
    return ReplayScheduler._instance
