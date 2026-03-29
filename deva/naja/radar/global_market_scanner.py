"""
GlobalMarketScanner - 全球市场感知器 (增强版)

功能:
1. 定期获取全球市场数据（期货 + 美股）
2. 基于交易时间的分层扫描策略
3. 检测异常波动并产生告警事件
4. 发现市场异动时主动发送给认知系统
5. 追踪市场状态变化

扫描策略:
- 24小时市场（期货）: 持续监控，标准间隔
- 美股交易时段: 高频率扫描（美股开盘时）
- 美股盘前盘后: 低频率扫描
- 收盘时段: 最小频率扫描

感知的市场:
- 股指期货: 纳指(NQ)、标普500(ES)、道琼斯(YM)
- 商品期货: 黄金(GC)、白银(SI)、原油(CL)、天然气(NG)
- 美股个股: NVDA、AAPL、TSLA、MSFT、GOOG 等
"""

import asyncio
import hashlib
import logging
import os
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Deque, Dict, List, Optional

from deva.naja.attention.data.global_market_futures import (
    GlobalMarketAPI,
    MarketData,
    MARKET_ID_TO_CODE,
)

try:
    from .global_market_config import (
        MarketSessionManager,
        MarketStatus,
        MarketType,
        get_market_session_manager,
        get_all_market_ids,
    )
except ImportError:
    from deva.naja.radar.global_market_config import (
        MarketSessionManager,
        MarketStatus,
        MarketType,
        get_market_session_manager,
        get_all_market_ids,
    )

log = logging.getLogger(__name__)


def _global_market_log(msg: str):
    """全球市场扫描日志"""
    if os.environ.get("NAJA_RADAR_DEBUG") == "true":
        log.info(f"[Radar-GlobalMarket] {msg}")


@dataclass
class MarketAlert:
    """市场告警"""
    id: str
    timestamp: datetime
    market_id: str
    alert_type: str
    severity: float
    current: float
    change_pct: float
    message: str
    market_status: str = "unknown"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "market_id": self.market_id,
            "alert_type": self.alert_type,
            "severity": self.severity,
            "current": self.current,
            "change_pct": self.change_pct,
            "message": self.message,
            "market_status": self.market_status,
            "metadata": self.metadata,
        }


class MarketVolatilityTracker:
    """市场波动追踪器"""

    def __init__(self, window_size: int = 10):
        self._window_size = window_size
        self._history: Dict[str, Deque[float]] = {}

    def update(self, market_id: str, change_pct: float) -> Dict[str, float]:
        """更新历史并计算统计"""
        if market_id not in self._history:
            self._history[market_id] = deque(maxlen=self._window_size)

        self._history[market_id].append(change_pct)

        values = list(self._history[market_id])
        if len(values) < 2:
            return {"mean": 0, "std": 0, "volatility": 0}

        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        std = variance ** 0.5

        return {
            "mean": mean,
            "std": std,
            "volatility": std,
            "recent_max": max(abs(v) for v in values[-3:]),
        }

    def is_abnormal(self, market_id: str, change_pct: float, threshold: float = 2.0) -> bool:
        """判断是否异常"""
        stats = self.update(market_id, change_pct)
        if stats["std"] == 0:
            return abs(change_pct) > threshold
        return abs(change_pct) > stats["mean"] + 3 * stats["std"]


@dataclass
class ScanConfig:
    """扫描配置"""
    interval_trading: float = 15       # 交易时段间隔（秒）
    interval_extended: float = 60       # 盘前盘后间隔（秒）
    interval_closed: float = 300       # 收盘时段间隔（秒）
    interval_24h: float = 60           # 24小时市场间隔（秒）
    alert_threshold_volatility: float = 2.0
    alert_threshold_single: float = 3.0


class GlobalMarketScanner:
    """
    全球市场感知器 (增强版)

    根据市场交易时间动态调整扫描频率：
    - 美股交易时段 (21:30-04:00 北京时间): 每15秒扫描
    - 美股盘前盘后: 每60秒扫描
    - 24小时期货市场: 每60秒扫描
    - 收盘时段: 每5分钟扫描

    性能监控：
    - 自动注册到 AutoTuner
    - 监控获取延迟、错误率等指标
    - 支持自动调优扫描间隔
    """

    DEFAULT_CONFIG = ScanConfig()
    COMPONENT_NAME = "GlobalMarketScanner"

    def __init__(self, config: Optional[ScanConfig] = None):
        self.config = config or self.DEFAULT_CONFIG

        self._api: Optional[GlobalMarketAPI] = None
        self._session_manager: Optional[MarketSessionManager] = None
        self._running = False
        self._task: Optional[asyncio.Task] = None

        self._volatility_tracker = MarketVolatilityTracker(window_size=10)
        self._last_market_data: Dict[str, MarketData] = {}
        self._alert_history: Deque[MarketAlert] = deque(maxlen=100)

        self._callbacks: List[callable] = []

        self._stats = {
            "fetch_count": 0,
            "alert_count": 0,
            "last_fetch_time": 0,
            "last_alert_time": 0,
            "current_interval": 0,
            "us_trading_phase": "unknown",
            "fetch_latency_ms": 0.0,
            "error_count": 0,
            "success_count": 0,
        }

        self._auto_tuner_registered = False
        self._propagation_engine = None
        self._sync_to_propagation = False

    @property
    def api(self) -> GlobalMarketAPI:
        if self._api is None:
            self._api = GlobalMarketAPI()
        return self._api

    @property
    def session_manager(self) -> MarketSessionManager:
        if self._session_manager is None:
            self._session_manager = get_market_session_manager()
        return self._session_manager

    def register_callback(self, callback: callable):
        """注册回调函数，接收市场告警"""
        self._callbacks.append(callback)

    def enable_propagation_engine_sync(self, propagation_engine):
        """
        启用 PropagationEngine 同步

        每次扫描到新数据后，自动同步到 PropagationEngine
        """
        self._propagation_engine = propagation_engine
        self._sync_to_propagation = True
        _global_market_log("已启用 PropagationEngine 同步")

    def disable_propagation_engine_sync(self):
        """禁用 PropagationEngine 同步"""
        self._sync_to_propagation = False
        self._propagation_engine = None
        _global_market_log("已禁用 PropagationEngine 同步")

    def _sync_to_propagation_engine(self, data: Dict[str, MarketData]):
        """同步数据到 PropagationEngine"""
        if not self._sync_to_propagation or not self._propagation_engine:
            return

        try:
            count = self._propagation_engine.sync_from_global_market_api(data)
            if count > 0:
                _global_market_log(f"同步 {count} 个市场数据到 PropagationEngine")
        except Exception as e:
            _global_market_log(f"同步到 PropagationEngine 失败: {e}")

    def _register_to_autotuner(self):
        """注册到自动调优器"""
        if self._auto_tuner_registered:
            return

        try:
            from deva.naja.common.auto_tuner import get_auto_tuner, TuneCondition

            tuner = get_auto_tuner()

            tuner.add_condition("global_market_fetch_error_rate", TuneCondition(
                threshold=0.1,
                action="reduce_interval",
                cooldown=300,
            ))

            self._auto_tuner_registered = True
            _global_market_log("已注册到 AutoTuner")
        except Exception as e:
            _global_market_log(f"注册到 AutoTuner 失败: {e}")

    def _report_to_autotuner(self):
        """报告性能指标到自动调优器"""
        if not self._auto_tuner_registered:
            return

        try:
            from deva.naja.common.auto_tuner import get_auto_tuner, trigger_business_adjustment

            total = self._stats["success_count"] + self._stats["error_count"]
            if total == 0:
                return

            error_rate = self._stats["error_count"] / total

            if error_rate > 0.1:
                current_interval = self._stats.get("current_interval", 60)
                new_interval = min(current_interval * 1.5, 300)
                trigger_business_adjustment(
                    param_name="global_scanner_interval",
                    new_value=new_interval,
                    reason=f"错误率过高 ({error_rate:.1%})，自动增加扫描间隔"
                )
                _global_market_log(f"错误率过高，自动调整间隔: {current_interval}s -> {new_interval}s")

        except ImportError:
            pass
        except Exception as e:
            _global_market_log(f"报告到 AutoTuner 失败: {e}")

    def _calculate_interval(self) -> float:
        """根据市场状态计算扫描间隔"""
        phase = self.session_manager.get_us_trading_phase()
        self._stats["us_trading_phase"] = phase

        if phase == "trading":
            return self.config.interval_trading
        elif phase in ("pre_market", "post_market"):
            return self.config.interval_extended
        else:
            return self.config.interval_closed

    def _get_market_status_map(self) -> Dict[str, str]:
        """获取所有市场的当前状态"""
        return self.session_manager.get_all_status()

    async def start(self):
        """启动扫描"""
        if self._running:
            log.warning("[GlobalMarketScanner] 已在运行中")
            return

        _global_market_log("启动全球市场扫描器 (增强版)...")
        self._running = True
        self._task = asyncio.create_task(self._scan_loop())

        self._register_to_autotuner()

        log.info("[GlobalMarketScanner] 已启动")

    async def stop(self):
        """停止扫描"""
        if not self._running:
            return

        _global_market_log("停止全球市场扫描器...")
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        log.info("[GlobalMarketScanner] 已停止")

    async def _scan_loop(self):
        """扫描循环 - 动态调整间隔"""
        while self._running:
            try:
                interval = self._calculate_interval()
                self._stats["current_interval"] = interval

                await self._fetch_and_analyze()
                self._stats["fetch_count"] += 1
                self._stats["last_fetch_time"] = time.time()

            except Exception as e:
                log.error(f"[GlobalMarketScanner] 扫描异常: {e}")

            interval = self._stats["current_interval"]
            _global_market_log(f"扫描完成，下次间隔: {interval}秒 (阶段: {self._stats['us_trading_phase']})")
            await asyncio.sleep(interval)

    async def _fetch_and_analyze(self):
        """获取并分析数据"""
        start_time = time.time()
        try:
            data = await self.api.fetch_all()
            fetch_latency = (time.time() - start_time) * 1000
            self._stats["fetch_latency_ms"] = fetch_latency

            if not data:
                _global_market_log("未获取到市场数据")
                self._stats["error_count"] += 1
                return

            self._stats["success_count"] += 1
            self._last_market_data = data

            self._sync_to_propagation_engine(data)
        except Exception as e:
            log.error(f"[GlobalMarketScanner] 获取数据异常: {e}")
            self._stats["error_count"] += 1
            return

        status_map = self._get_market_status_map()

        alerts = self._detect_alerts(data, status_map)

        if alerts:
            _global_market_log(f"检测到 {len(alerts)} 个告警")
            for alert in alerts:
                self._alert_history.append(alert)
                self._stats["alert_count"] += 1
                self._stats["last_alert_time"] = time.time()
                await self._emit_alert(alert)

        self._report_to_autotuner()

    def _detect_alerts(self, data: Dict[str, MarketData], status_map: Dict[str, str]) -> List[MarketAlert]:
        """检测告警"""
        alerts = []

        for code, md in data.items():
            market_status = status_map.get(md.market_id, "unknown")
            change_pct = md.change_pct
            abs_change = abs(change_pct)

            if abs_change < self.alert_threshold_single:
                continue

            is_abnormal = self._volatility_tracker.is_abnormal(
                md.market_id, change_pct, self.alert_threshold_volatility
            )

            severity = min(1.0, abs_change / 5.0)

            if is_abnormal:
                alert_type = "abnormal_volatility"
                message = f"{md.name} 异常波动: {change_pct:+.2f}%"
            elif abs_change > 5.0:
                alert_type = "extreme_move"
                message = f"{md.name} 极端波动: {change_pct:+.2f}%"
            elif change_pct > 0:
                alert_type = "significant_up"
                message = f"{md.name} 大幅上涨: {change_pct:+.2f}%"
            else:
                alert_type = "significant_down"
                message = f"{md.name} 大幅下跌: {change_pct:+.2f}%"

            alert = MarketAlert(
                id=self._generate_alert_id(md.market_id, alert_type),
                timestamp=datetime.now(),
                market_id=md.market_id,
                alert_type=alert_type,
                severity=severity,
                current=md.current,
                change_pct=change_pct,
                message=message,
                market_status=market_status,
                metadata={
                    "code": md.code,
                    "name": md.name,
                    "open": md.open,
                    "high": md.high,
                    "low": md.low,
                    "prev_close": md.prev_close,
                    "volume": md.volume,
                    "is_abnormal": is_abnormal,
                    "update_time": md.update_time,
                },
            )
            alerts.append(alert)

        return alerts

    def _generate_alert_id(self, market_id: str, alert_type: str) -> str:
        """生成告警ID"""
        content = f"{market_id}_{alert_type}_{time.time()}"
        return hashlib.md5(content.encode()).hexdigest()[:12]

    async def _emit_alert(self, alert: MarketAlert):
        """发送告警到回调"""
        _global_market_log(f"告警: {alert.message} [状态: {alert.market_status}]")
        for callback in self._callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(alert)
                else:
                    callback(alert)
            except Exception as e:
                log.error(f"[GlobalMarketScanner] 回调异常: {e}")

    async def fetch_once(self) -> Dict[str, MarketData]:
        """手动获取一次数据"""
        data = await self.api.fetch_all()
        self._last_market_data = data
        self._sync_to_propagation_engine(data)
        return data

    def get_last_data(self) -> Dict[str, MarketData]:
        """获取最近一次数据"""
        return self._last_market_data

    def get_alerts(self, limit: int = 20) -> List[MarketAlert]:
        """获取最近告警"""
        return list(self._alert_history)[-limit:]

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        total = self._stats["success_count"] + self._stats["error_count"]
        success_rate = self._stats["success_count"] / total if total > 0 else 0
        error_rate = self._stats["error_count"] / total if total > 0 else 0

        return {
            **self._stats,
            "running": self._running,
            "alert_history_size": len(self._alert_history),
            "tracked_markets": list(self._last_market_data.keys()),
            "success_rate": success_rate,
            "error_rate": error_rate,
            "total_requests": total,
        }

    def get_market_summary(self) -> Dict[str, Any]:
        """获取市场状态摘要"""
        status_map = self._get_market_status_map()
        open_markets = [k for k, v in status_map.items() if v == MarketStatus.OPEN.value]
        closed_markets = [k for k, v in status_map.items() if v == MarketStatus.CLOSED.value]

        return {
            "us_trading_phase": self.session_manager.get_us_trading_phase(),
            "total_markets": len(status_map),
            "open_count": len(open_markets),
            "closed_count": len(closed_markets),
            "open_markets": open_markets,
            "status_map": status_map,
            "current_interval": self._stats["current_interval"],
        }


_scanner_instance: Optional[GlobalMarketScanner] = None


def get_global_market_scanner() -> GlobalMarketScanner:
    """获取全局扫描器实例"""
    global _scanner_instance
    if _scanner_instance is None:
        _scanner_instance = GlobalMarketScanner()
    return _scanner_instance


if __name__ == "__main__":
    async def test():
        scanner = GlobalMarketScanner()

        async def on_alert(alert: MarketAlert):
            print(f"🔔 告警: {alert.message} [状态: {alert.market_status}]")

        scanner.register_callback(on_alert)

        print("=== 全球市场感知器 (增强版) ===")
        print(f"当前市场状态: {scanner.session_manager.get_us_trading_phase()}")
        print()

        summary = scanner.get_market_summary()
        print(f"美股阶段: {summary['us_trading_phase']}")
        print(f"当前扫描间隔: {summary['current_interval']}秒")
        print(f"开放市场数: {summary['open_count']}")
        print(f"关闭市场数: {summary['closed_count']}")
        print()

        print("获取市场数据...")
        data = await scanner.fetch_once()
        print(f"获取到 {len(data)} 个市场数据")
        for code, md in list(data.items())[:7]:
            pct = md.change_pct
            sign = "+" if pct >= 0 else ""
            print(f"  {md.name}: {md.current} ({sign}{pct:.2f}%)")

        print("\n测试完成")

    asyncio.run(test())
