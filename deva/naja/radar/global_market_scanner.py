"""
GlobalMarketScanner - 全球市场感知器 (增强版)

功能:
1. 定期获取全球市场数据（期货 + 美股）
2. 基于交易时间的分层扫描策略
3. 检测异常波动并产生告警事件
4. 发现市场异动时主动发送给认知系统
5. 追踪市场状态变化
6. 多市场流动性预测与验证（新增）

扫描策略:
- 24小时市场（期货）: 持续监控，标准间隔
- 美股交易时段: 高频率扫描（美股开盘时）
- 美股盘前盘后: 低频率扫描
- 收盘时段: 最小频率扫描

感知的市场:
- 股指期货: 纳指(NQ)、标普500(ES)、道琼斯(YM)
- 商品期货: 黄金(GC)、白银(SI)、原油(CL)、天然气(NG)
- 美股个股: NVDA、AAPL、TSLA、MSFT、GOOG 等

多市场流动性预测:
- 基于全球市场信号，预测对各目标市场的流动性影响
- 支持 A股、港股、美股等多个市场的预测
- 验证预测是否正确，动态调整/解除限制
"""

import asyncio
import hashlib
import logging
import os
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Deque, Dict, List, Optional

import numpy as np

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


class LiquiditySignalType(Enum):
    """
    流动性信号类型枚举

    用于标识不同市场的流动性预测目标
    注意：这里定义的是 Attention 系统内部使用的市场标识
    与 MarketType（交易时间配置）不同
    """
    CHINA_A = "china_a"       # A股
    HONG_KONG = "hk"          # 港股
    US = "us"                 # 美股
    FUTURES = "futures"       # 期货
    CRYPTO = "crypto"         # 加密货币


@dataclass
class LiquidityPrediction:
    """
    流动性预测

    表示基于某些信号，对某个目标市场的流动性预测

    属性:
        target_market: 预测目标市场
        source_signals: 信号来源描述
        signal: 预测值 0-1 (< 0.4 紧张, > 0.6 宽松)
        confidence: 置信度 0-1
        timestamp: 预测时间
        valid_until: 预测有效期（秒）
        adjustment: 调整指令
    """
    target_market: LiquiditySignalType
    source_signals: List[str]
    signal: float
    confidence: float
    timestamp: float
    valid_until: float
    is_priced: bool = False
    priced_reason: str = ""
    priced_at_open: bool = False
    adjustment: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LiquidityVerification:
    """
    流动性验证

    用于验证预测是否正确

    属性:
        target_market: 目标市场
        actual_signals: 实际信号列表
        expected_signal: 预期信号
        verification_count: 验证次数
        verified: 是否已验证
        should_relax: 是否应该解除限制
    """
    target_market: LiquiditySignalType
    actual_signals: List[float] = field(default_factory=list)
    expected_signal: float = 0.5
    verification_count: int = 0
    verified: bool = False
    should_relax: bool = False


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

            if abs_change < self.config.alert_threshold_single:
                continue

            is_abnormal = self._volatility_tracker.is_abnormal(
                md.market_id, change_pct, self.config.alert_threshold_volatility
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

    def get_stats(self, wait_for_running: bool = False, timeout: float = 5.0) -> Dict[str, Any]:
        """获取统计信息

        Args:
            wait_for_running: 是否等待扫描器真正启动
            timeout: 等待超时时间（秒）
        """
        import time

        if wait_for_running and not self._running:
            start_time = time.time()
            while not self._running and (time.time() - start_time) < timeout:
                time.sleep(0.1)

        total = self._stats["success_count"] + self._stats["error_count"]
        success_rate = self._stats["success_count"] / total if total > 0 else 0
        error_rate = self._stats["error_count"] / total if total > 0 else 0

        return {
            **self._stats,
            "running": self._running,
            "is_running": self._running,
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

    def _init_liquidity_system(self):
        """初始化流动性预测系统"""
        self._liquidity_predictions: Dict[LiquiditySignalType, LiquidityPrediction] = {}
        self._latest_data: Dict[str, Any] = {}
        self._liquidity_verifications: Dict[LiquiditySignalType, LiquidityVerification] = {}
        self._liquidity_history: Dict[LiquiditySignalType, deque] = {
            lt: deque(maxlen=20) for lt in LiquiditySignalType
        }
        self._market_influences = {
            LiquiditySignalType.CHINA_A: [LiquiditySignalType.HONG_KONG, LiquiditySignalType.US],
            LiquiditySignalType.HONG_KONG: [LiquiditySignalType.CHINA_A, LiquiditySignalType.US],
            LiquiditySignalType.US: [LiquiditySignalType.CHINA_A, LiquiditySignalType.HONG_KONG],
            LiquiditySignalType.FUTURES: [LiquiditySignalType.CHINA_A, LiquiditySignalType.US],
        }
        self._transmission_probabilities = {
            (LiquiditySignalType.CHINA_A, LiquiditySignalType.HONG_KONG): 0.7,
            (LiquiditySignalType.CHINA_A, LiquiditySignalType.US): 0.3,
            (LiquiditySignalType.US, LiquiditySignalType.CHINA_A): 0.5,
            (LiquiditySignalType.US, LiquiditySignalType.HONG_KONG): 0.8,
            (LiquiditySignalType.HONG_KONG, LiquiditySignalType.CHINA_A): 0.6,
            (LiquiditySignalType.HONG_KONG, LiquiditySignalType.US): 0.4,
            (LiquiditySignalType.FUTURES, LiquiditySignalType.CHINA_A): 0.6,
            (LiquiditySignalType.FUTURES, LiquiditySignalType.US): 0.5,
        }
        self._liquidity_initialized = True

    def _get_dynamic_valid_until(self, target: LiquiditySignalType) -> float:
        """
        动态计算预测有效期
        - 市场交易中：有效期 = 当前交易时段结束时间
        - 市场未开盘：有效期 = 下一个交易时段结束时间
        - 市场已收盘：有效期 = 明天交易时段结束时间
        """
        market_id_map = {
            LiquiditySignalType.CHINA_A: "china_a",
            LiquiditySignalType.HONG_KONG: "hk",
            LiquiditySignalType.US: "us_equity",
            LiquiditySignalType.FUTURES: "nasdaq100",
            LiquiditySignalType.CRYPTO: None,
        }
        market_id = market_id_map.get(target)
        if not market_id:
            return time.time() + 3600

        market_status = self.session_manager.get_market_status(market_id)

        if market_status == MarketStatus.OPEN:
            remaining = self.session_manager.get_session_remaining_seconds(market_id)
            if remaining is not None and remaining > 0:
                return time.time() + remaining
        elif market_status in (MarketStatus.PRE_MARKET, MarketStatus.POST_MARKET, MarketStatus.BREAK):
            remaining = self.session_manager.get_session_remaining_seconds(market_id)
            if remaining is not None and remaining > 0:
                duration = self.session_manager.get_market_trading_duration_seconds(market_id) or 0
                return time.time() + remaining + duration

        duration = self.session_manager.get_market_trading_duration_seconds(market_id) or 14400
        return time.time() + duration

    def _check_if_priced(self, target: LiquiditySignalType, source_signal: float, source_market: LiquiditySignalType) -> tuple:
        """
        检测目标市场是否已经对源市场信号完成"定价"

        定价检测逻辑：
        - 目标市场开盘变动方向与源市场信号方向一致 → 已定价（无效干预）
        - 目标市场开盘变动方向与源市场信号方向相反 → 未定价（值得干预）
        - 信号太弱或数据不足 → 无法判断（不干预）

        Args:
            target: 目标市场
            source_signal: 源市场信号（原始，未经过传染率折扣）
            source_market: 源市场

        Returns:
            (is_priced, reason, priced_at_open)
        """
        market_id_map = {
            LiquiditySignalType.CHINA_A: "china_a",
            LiquiditySignalType.HONG_KONG: "hk",
            LiquiditySignalType.US: "us_equity",
            LiquiditySignalType.FUTURES: "nasdaq100",
            LiquiditySignalType.CRYPTO: None,
        }
        market_id = market_id_map.get(target)
        if not market_id:
            return (False, "", False)

        if self.session_manager.get_market_status(market_id) == MarketStatus.CLOSED:
            return (False, "市场已收盘，等待下一交易日", False)

        recent_data = self._get_latest_market_data(market_id)
        if not recent_data:
            return (False, "无市场数据，无法判断定价状态", False)

        open_change = recent_data.get('change_pct', 0)

        if abs(open_change) < 0.1:
            return (False, f"开盘变化微小({open_change:.2f}%),未定价", False)

        signal_threshold = 0.15
        if abs(source_signal - 0.5) <= signal_threshold:
            return (False, "信号不够强，无法判断定价", False)

        source_dir = 1 if source_signal > 0.5 else -1
        open_dir = 1 if open_change > 0 else -1

        if source_dir == open_dir:
            return (True,
                    f"已定价: 源信号方向={source_dir}, 开盘变动={open_change:.2f}%, 方向一致",
                    True)
        else:
            return (False,
                    f"未定价: 源信号方向={source_dir}, 开盘变动={open_change:.2f}%, 方向相反",
                    False)

    def _get_latest_market_data(self, market_id: str) -> Optional[Dict[str, Any]]:
        """获取最近的市场数据"""
        md = self._last_market_data.get(market_id)
        if md:
            return {'change_pct': md.change_pct, 'current': md.current}
        return None

    def predict_liquidity(self, source_market: LiquiditySignalType, signals: Dict[str, Any]) -> List[LiquidityPrediction]:
        """
        基于信号来源市场，预测对各目标市场的流动性影响

        Args:
            source_market: 信号来源市场
            signals: 信号数据（涨跌、成交量、波动率等）

        Returns:
            List[LiquidityPrediction]: 对各目标市场的预测列表
        """
        if not getattr(self, '_liquidity_initialized', False):
            self._init_liquidity_system()

        predictions = []
        source_signal = self._calc_liquidity_signal(signals)

        target_markets = self._market_influences.get(source_market, [])
        for target in target_markets:
            transmission_prob = self._get_transmission_probability(source_market, target)
            predicted_signal = source_signal * transmission_prob

            is_priced, priced_reason, priced_at_open = self._check_if_priced(target, source_signal, source_market)

            adjustment = self._generate_adjustment(target, predicted_signal, is_priced)

            prediction = LiquidityPrediction(
                target_market=target,
                source_signals=[f"{source_market.value}: {source_signal:.2f}"],
                signal=predicted_signal,
                confidence=transmission_prob,
                timestamp=time.time(),
                valid_until=self._get_dynamic_valid_until(target),
                is_priced=is_priced,
                priced_reason=priced_reason,
                priced_at_open=priced_at_open,
                adjustment=adjustment
            )

            predictions.append(prediction)
            self._liquidity_predictions[target] = prediction

        return predictions

    def _calc_liquidity_signal(self, signals: Dict[str, Any]) -> float:
        """
        计算流动性信号，范围 [0, 1]
        - 暴涨(+5%↑) = 流动性宽松 = signal接近1.0
        - 暴跌(-5%↓) = 流动性紧张 = signal接近0.0
        - 不变(0%) = signal = 0.5
        """
        change = signals.get('change_pct', 0)
        volume_ratio = signals.get('volume_ratio', 1.0)

        change_score = 0.5 + (change / 10.0)
        change_score = float(np.clip(change_score, 0.0, 1.0))

        if volume_ratio < 0.7:
            volume_score = 0.3
        elif volume_ratio < 0.9:
            volume_score = 0.4
        elif volume_ratio > 1.5:
            volume_score = 0.3
        elif volume_ratio > 1.3:
            volume_score = 0.4
        else:
            volume_score = 0.5

        signal = change_score * 0.7 + volume_score * 0.3
        return float(np.clip(signal, 0.0, 1.0))

    def _get_transmission_probability(self, source: LiquiditySignalType, target: LiquiditySignalType) -> float:
        """获取市场间传染概率"""
        return self._transmission_probabilities.get((source, target), 0.3)

    def _generate_adjustment(self, target: LiquiditySignalType, signal: float, is_priced: bool = False) -> Dict[str, Any]:
        """生成调整指令"""
        if is_priced:
            return {
                "sector_attention_factor": 1.0,
                "strategy_budget": {},
                "frequency_factor": 1.0,
                "position_size_multiplier": 1.0,
                "holding_time_factor": 1.0,
                "is_priced": True,
            }
        if signal < 0.4:
            return {
                "sector_attention_factor": 0.8,
                "strategy_budget": {
                    "AnomalySniper": 0.2,
                    "MomentumTracker": -0.2,
                },
                "frequency_factor": 1.3,
                "position_size_multiplier": 0.6,
                "holding_time_factor": 0.7,
                "warning": "流动性紧张信号",
            }
        elif signal > 0.7:
            return {
                "sector_attention_factor": 1.1,
                "strategy_budget": {
                    "AnomalySniper": -0.1,
                    "MomentumTracker": 0.1,
                },
                "frequency_factor": 0.9,
                "position_size_multiplier": 1.1,
                "holding_time_factor": 1.0,
            }
        else:
            return {
                "sector_attention_factor": 1.0,
                "strategy_budget": {},
                "frequency_factor": 1.0,
                "position_size_multiplier": 1.0,
                "holding_time_factor": 1.0,
            }

    def verify_liquidity(self, target_market: LiquiditySignalType, actual_data: Dict[str, Any]):
        """
        验证对某个市场的预测是否正确

        Args:
            target_market: 目标市场
            actual_data: 实际市场数据（涨跌幅、成交量等）
        """
        if not getattr(self, '_liquidity_initialized', False):
            self._init_liquidity_system()

        if target_market not in self._liquidity_verifications:
            expected = 0.5
            if target_market in self._liquidity_predictions:
                expected = self._liquidity_predictions[target_market].signal
            self._liquidity_verifications[target_market] = LiquidityVerification(
                target_market=target_market,
                expected_signal=expected
            )

        ver = self._liquidity_verifications[target_market]
        actual_signal = self._calc_liquidity_signal(actual_data)
        ver.actual_signals.append(actual_signal)
        ver.verification_count += 1

        if ver.verification_count < 5:
            return

        recent = ver.actual_signals[-10:]
        avg_actual = sum(recent) / len(recent)

        diff = abs(avg_actual - ver.expected_signal)
        if diff > 0.25:
            ver.verified = False
            ver.should_relax = True
            log.info(f"[Liquidity] {target_market.value} 预判错误: 预期={ver.expected_signal:.2f}, 实际={avg_actual:.2f}, 解除限制")
        else:
            ver.verified = True
            ver.should_relax = False

    def get_liquidity_adjustment(self, target_market: LiquiditySignalType, actual_data: Dict[str, Any] = None) -> Optional[Dict[str, Any]]:
        """
        获取对某个目标市场的调整指令

        Args:
            target_market: 目标市场
            actual_data: 可选的实际数据，用于验证

        Returns:
            dict: 调整指令，如果没有预测则返回 None
        """
        if not getattr(self, '_liquidity_initialized', False):
            return None

        prediction = self._liquidity_predictions.get(target_market)
        if not prediction:
            return None

        if actual_data:
            self.verify_liquidity(target_market, actual_data)

        if time.time() > prediction.valid_until:
            log.info(f"[Liquidity] {target_market.value} 预测过期，解除限制")
            return self._generate_relaxation_adjustment()

        ver = self._liquidity_verifications.get(target_market)
        if ver and ver.should_relax:
            log.info(f"[Liquidity] {target_market.value} 验证失败，解除限制")
            return self._generate_relaxation_adjustment()

        return prediction.adjustment

    def get_all_market_adjustments(self) -> Dict[LiquiditySignalType, Optional[Dict[str, Any]]]:
        """
        获取所有市场的调整指令（用于全局更新）

        Returns:
            Dict[market, adjustment]: 各市场的调整指令
        """
        if not getattr(self, '_liquidity_initialized', False):
            return {}

        adjustments = {}
        for market in self._liquidity_predictions.keys():
            adjustments[market] = self.get_liquidity_adjustment(market)
        return adjustments

    def auto_verify_all_predictions(self, market_data_map: Dict[LiquiditySignalType, Dict[str, Any]]):
        """
        自动验证所有有预测的市场

        Args:
            market_data_map: 各市场的实际数据 {
                LiquiditySignalType.CHINA_A: {'change_pct': -1.5, 'volume_ratio': 0.8},
                LiquiditySignalType.US: {'change_pct': 2.0, 'volume_ratio': 1.2},
                ...
            }
        """
        for market, data in market_data_map.items():
            if market in self._liquidity_predictions:
                self.verify_liquidity(market, data)

    def predict_and_auto_verify(self, source_market: LiquiditySignalType, signals: Dict[str, Any], market_data_map: Dict[LiquiditySignalType, Dict[str, Any]] = None) -> List[LiquidityPrediction]:
        """
        预测并自动验证（形成闭环）

        Args:
            source_market: 信号来源市场
            signals: 信号数据
            market_data_map: 各目标市场的实际数据（用于验证）

        Returns:
            List[LiquidityPrediction]: 预测列表
        """
        predictions = self.predict_liquidity(source_market, signals)

        if market_data_map:
            self.auto_verify_all_predictions(market_data_map)

        return predictions

    def _generate_relaxation_adjustment(self) -> Dict[str, Any]:
        """生成解除限制的调整"""
        return {
            "sector_attention_factor": 1.2,
            "strategy_budget": {
                "AnomalySniper": -0.2,
                "MomentumTracker": 0.2,
            },
            "frequency_factor": 0.9,
            "is_relaxation": True,
        }

    def get_liquidity_status(self) -> Dict[str, Any]:
        """获取流动性系统状态"""
        if not getattr(self, '_liquidity_initialized', False):
            self._init_liquidity_system()

        predictions = {}
        for market, pred in self._liquidity_predictions.items():
            predictions[market.value] = {
                "signal": pred.signal,
                "confidence": pred.confidence,
                "source_signals": pred.source_signals,
                "is_valid": time.time() <= pred.valid_until,
            }

        verifications = {}
        for market, ver in self._liquidity_verifications.items():
            verifications[market.value] = {
                "expected": ver.expected_signal,
                "verification_count": ver.verification_count,
                "verified": ver.verified,
                "should_relax": ver.should_relax,
            }

        resonance = getattr(self, '_last_resonance', None)
        resonance_info = None
        if resonance:
            resonance_info = {
                "level": resonance["resonance_level"],
                "confidence": resonance["confidence"],
                "alignment": resonance["alignment"],
                "weight": resonance.get("weight", 0),
                "market_signal": resonance["market_signal"],
                "narrative_signal": resonance["narrative_signal"],
            }

        topic_predictions = getattr(self, '_topic_predictions', {})
        topic_info = {}
        for topic, pred in topic_predictions.items():
            topic_info[topic] = {
                "target_sectors": pred.get("target_sectors", []),
                "spread_probability": pred.get("spread_probability", 0),
                "expected_change": pred.get("expected_change", 0),
                "heat_score": pred.get("heat_score", 0),
            }

        return {
            "predictions": predictions,
            "verifications": verifications,
            "resonance": resonance_info,
            "topic_predictions": topic_info,
        }

    def set_narrative_signal(self, signal: float):
        """
        设置舆论信号（供 NarrativeTracker 调用）

        Args:
            signal: 舆论信号 (-1 to 1, 负=利空，正=利多)
        """
        if not getattr(self, '_liquidity_initialized', False):
            self._init_liquidity_system()

        self._narrative_signal = float(np.clip(signal, -1.0, 1.0))

    def detect_resonance(self, market_signal: float, narrative_signal: float = None) -> Dict[str, Any]:
        """
        检测信号共振

        Args:
            market_signal: 行情信号 (-1 to 1)
            narrative_signal: 舆论信号 (-1 to 1)，如果为 None 则使用内部存储的舆论信号

        Returns:
            {
                "resonance_level": "high"/"medium"/"low"/"divergent"/"none",
                "confidence": 0.0-1.0,
                "final_signal": float,
                "alignment": float,
                "weight": float,
            }
        """
        if narrative_signal is None:
            narrative_signal = getattr(self, '_narrative_signal', 0.0)

        if abs(market_signal) < 0.1 and abs(narrative_signal) < 0.1:
            resonance_level = "none"
            confidence = 0.0
        elif abs(market_signal) < 0.2 or abs(narrative_signal) < 0.2:
            if market_signal * narrative_signal > 0:
                resonance_level = "low"
                confidence = 0.4
            elif market_signal * narrative_signal < 0:
                resonance_level = "divergent"
                confidence = 0.3
            else:
                resonance_level = "low"
                confidence = 0.3
        elif market_signal * narrative_signal > 0:
            alignment = 1 - abs(market_signal - narrative_signal) / 2
            if alignment > 0.7:
                resonance_level = "high"
                confidence = 0.9
            else:
                resonance_level = "medium"
                confidence = 0.7
        elif market_signal * narrative_signal < 0:
            resonance_level = "divergent"
            confidence = 0.5
        else:
            resonance_level = "low"
            confidence = 0.4

        resonance_weights = {
            "high": 1.0,
            "medium": 0.7,
            "low": 0.5,
            "divergent": 0.3,
            "none": 0.0,
        }
        weight = resonance_weights[resonance_level]
        final_signal = market_signal * weight

        self._last_resonance = {
            "resonance_level": resonance_level,
            "confidence": confidence,
            "final_signal": final_signal,
            "alignment": 1 - abs(market_signal - narrative_signal) / 2 if resonance_level != "none" else 0,
            "weight": weight,
            "market_signal": market_signal,
            "narrative_signal": narrative_signal,
        }

        return self._last_resonance

    TOPIC_SECTOR_MAPPING = {
        "芯片": {"a_share_sectors": ["半导体", "集成电路"], "us_sector": "SOX"},
        "AI": {"a_share_sectors": ["人工智能", "软件服务"], "us_sector": "AI"},
        "新能源": {"a_share_sectors": ["锂电池", "光伏"], "us_sector": "XLE"},
        "电动车": {"a_share_sectors": ["新能源汽车"], "us_sector": "TSLA"},
        "云计算": {"a_share_sectors": ["云计算", "数据中心"], "us_sector": "CLOUD"},
    }

    CROSS_MARKET_PROB = {
        "芯片": 0.7,
        "AI": 0.6,
        "新能源": 0.5,
        "电动车": 0.4,
        "云计算": 0.5,
    }

    def update_topic_heat(self, topic: str, change_pct: float, volume_ratio: float = 1.0):
        """
        更新主题热度

        Args:
            topic: 主题名称
            change_pct: 涨跌幅
            volume_ratio: 成交量比
        """
        if not hasattr(self, '_topic_heat'):
            self._topic_heat = {}

        if topic not in self._topic_heat:
            self._topic_heat[topic] = deque(maxlen=10)

        heat_score = abs(change_pct) * volume_ratio
        self._topic_heat[topic].append(heat_score)

    def predict_topic_spread(self, topic: str, us_sector_change: float) -> Dict[str, Any]:
        """
        预测主题扩散

        Args:
            topic: 主题名称
            us_sector_change: 美股该板块的涨跌幅

        Returns:
            {
                "target_sectors": List[str],
                "spread_probability": float,
                "expected_change": float,
                "heat_score": float,
                "confidence": float,
            }
        """
        mapping = self.TOPIC_SECTOR_MAPPING.get(topic, {})
        target_sectors = mapping.get("a_share_sectors", [])

        heat_history = self._topic_heat.get(topic, [])
        heat_score = float(np.mean(list(heat_history))) if heat_history else 0

        base_prob = self.CROSS_MARKET_PROB.get(topic, 0.3)

        heat_factor = min(heat_score / 5.0, 1.5)
        spread_prob = base_prob * heat_factor

        expected_change = us_sector_change * spread_prob

        result = {
            "target_sectors": target_sectors,
            "spread_probability": min(spread_prob, 0.95),
            "expected_change": expected_change,
            "heat_score": heat_score,
            "confidence": base_prob * 0.8,
        }

        if not hasattr(self, '_topic_predictions'):
            self._topic_predictions = {}
        self._topic_predictions[topic] = result

        return result

    def get_topic_adjustment_for_sector(self, sector: str) -> Optional[Dict[str, Any]]:
        """
        获取板块的主题调整指令

        Args:
            sector: 板块名称

        Returns:
            {
                "attention_weight_factor": float,
                "hot_topic_score": float,
                "spread_confidence": float,
                "topics": List[str],
            }
        """
        relevant_topics = []
        for topic, mapping in self.TOPIC_SECTOR_MAPPING.items():
            if sector in mapping["a_share_sectors"]:
                relevant_topics.append(topic)

        if not relevant_topics:
            return None

        total_heat = 0
        total_prob = 0
        for topic in relevant_topics:
            heat = float(np.mean(list(self._topic_heat.get(topic, [])))) if self._topic_heat.get(topic) else 0
            prob = self.CROSS_MARKET_PROB.get(topic, 0.3)
            total_heat += heat * prob
            total_prob += prob

        avg_heat = total_heat / len(relevant_topics) if relevant_topics else 0
        avg_prob = total_prob / len(relevant_topics) if relevant_topics else 0

        if avg_heat > 3:
            attention_factor = 1.2 + (avg_heat - 3) * 0.05
        else:
            attention_factor = 1.0

        return {
            "attention_weight_factor": min(attention_factor, 1.5),
            "hot_topic_score": avg_heat,
            "spread_confidence": avg_prob,
            "topics": relevant_topics,
        }

    def get_a_share_liquidity_prediction(self) -> Optional[LiquidityPrediction]:
        """获取 A 股流动性预测（便捷方法）"""
        return self._liquidity_predictions.get(LiquiditySignalType.CHINA_A)


_scanner_instance: Optional[GlobalMarketScanner] = None
_scanner_lock = threading.Lock()


def get_global_market_scanner() -> GlobalMarketScanner:
    """获取全局扫描器实例（线程安全单例）"""
    global _scanner_instance
    if _scanner_instance is None:
        with _scanner_lock:
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
