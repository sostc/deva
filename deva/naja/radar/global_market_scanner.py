"""
GlobalMarketScanner - 感知系统/全球市场/市场扫描

别名/关键词: 全球市场、市场扫描、异常检测、global market scanner、market anomaly、market scanner

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

from deva.naja.market_hotspot.data.global_market_futures import (
    GlobalMarketAPI,
    MarketData,
    MARKET_ID_TO_CODE,
)
from deva.naja.register import SR

try:
    from .global_market_config import (
        MarketSessionManager,
        MarketStatus,
        MarketType,
        get_all_market_ids,
    )
except ImportError:
    from deva.naja.radar.global_market_config import (
        MarketSessionManager,
        MarketStatus,
        MarketType,
        get_all_market_ids,
    )

log = logging.getLogger(__name__)

_loop_audit_log_stage = None

def _get_audit():
    global _loop_audit_log_stage
    if _loop_audit_log_stage is None:
        try:
            from ..infra.observability.loop_audit import LoopAudit
            _loop_audit_log_stage = lambda **kw: LoopAudit(**kw)
        except ImportError:
            _loop_audit_log_stage = lambda **kw: _DummyAudit()
    return _loop_audit_log_stage

class _DummyAudit:
    def __init__(self, **kwargs): pass
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def record_data_out(self, *args, **kwargs): pass


def _global_market_log(msg: str):
    """全球市场扫描日志"""
    if os.environ.get("NAJA_RADAR_DEBUG") == "true":
        log.info(f"[Radar-GlobalMarket] {msg}")


# ─── 流动性预测数据类（已迁移到 cognition/liquidity/liquidity_predictor.py）───
# 保留向后兼容导入
from deva.naja.cognition.liquidity.liquidity_predictor import (
    LiquiditySignalType,
    LiquidityPrediction,
    LiquidityVerification,
    LiquidityPredictor,
    get_liquidity_predictor,
)


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


class MarketBreadthTracker:
    """
    市场广度追踪器

    追踪上涨/下跌家数比例、涨停/跌停家数，计算市场广度指标和恐惧指标
    """

    def __init__(
        self,
        extreme_fear_threshold: float = 0.1,
        high_fear_threshold: float = 0.2,
        extreme_greed_threshold: float = 5.0,
        high_greed_threshold: float = 3.0,
    ):
        self.extreme_fear_threshold = extreme_fear_threshold
        self.high_fear_threshold = high_fear_threshold
        self.extreme_greed_threshold = extreme_greed_threshold
        self.high_greed_threshold = high_greed_threshold
        self._history: Deque[Dict[str, Any]] = deque(maxlen=20)

    def update(self, market_data_list: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        更新市场广度数据

        Args:
            market_data_list: 市场数据列表，每项包含:
                - change_pct: 涨跌幅
                - is_limit_up: 是否涨停（可选）
                - is_limit_down: 是否跌停（可选）

        Returns:
            Dict: 包含广度指标和恐惧评分
        """
        limit_up = 0
        limit_down = 0
        advancing = 0
        declining = 0

        for stock in market_data_list:
            change_pct = stock.get("change_pct", 0)
            is_limit_up = stock.get("is_limit_up", False)
            is_limit_down = stock.get("is_limit_down", False)

            if is_limit_up or change_pct >= 9.5:
                limit_up += 1
            elif is_limit_down or change_pct <= -9.5:
                limit_down += 1

            if change_pct > 0:
                advancing += 1
            elif change_pct < 0:
                declining += 1

        total = len(market_data_list) if market_data_list else 1
        breadth_ratio = (advancing - declining) / total if total > 0 else 0
        fear_indicator = self._calculate_fear_indicator(limit_up, limit_down, advancing, declining)
        fear_level = self._classify_fear_level(fear_indicator)
        fear_score = self._calculate_fear_score(fear_indicator)

        result = {
            "limit_up_count": limit_up,
            "limit_down_count": limit_down,
            "advancing_count": advancing,
            "declining_count": declining,
            "total_count": total,
            "breadth_ratio": breadth_ratio,
            "fear_indicator": fear_indicator,
            "fear_level": fear_level,
            "fear_score": fear_score,
            "timestamp": time.time(),
        }

        self._history.append(result)
        return result

    def update_from_market_data(self, market_data: Dict[str, MarketData]) -> Dict[str, Any]:
        """
        从 GlobalMarketScanner 的市场数据更新广度

        由于 GlobalMarketScanner 主要追踪的是指数/期货而非个股，
        这里通过涨跌幅分布来估算市场广度
        """
        if not market_data:
            return {}

        changes = [md.change_pct for md in market_data.values() if md.change_pct != 0]

        if not changes:
            return {}

        market_data_list = [{"change_pct": c} for c in changes]
        return self.update(market_data_list)

    def _calculate_fear_indicator(self, limit_up: int, limit_down: int, advancing: int, declining: int) -> float:
        """
        计算恐惧指标

        公式: fear = (limit_down / max(limit_up, 1)) * (declining / max(advancing, 1)) * 10
        """
        if limit_up == 0 and advancing == 0:
            return 10.0

        limit_ratio = limit_down / max(limit_up, 1)
        decline_ratio = declining / max(advancing, 1)
        fear = limit_ratio * decline_ratio * 10

        return min(10.0, max(0.0, fear))

    def _classify_fear_level(self, fear_indicator: float) -> str:
        """分类恐惧等级"""
        if fear_indicator >= self.extreme_fear_threshold * 5:
            return "extreme_fear"
        elif fear_indicator >= self.extreme_fear_threshold:
            return "high_fear"
        elif fear_indicator >= self.high_fear_threshold:
            return "moderate_fear"
        elif fear_indicator >= 1.0:
            return "neutral"
        elif fear_indicator <= self.extreme_greed_threshold / 10:
            return "extreme_greed"
        elif fear_indicator <= self.high_greed_threshold / 10:
            return "high_greed"
        return "neutral"

    def _calculate_fear_score(self, fear_indicator: float) -> float:
        """
        获取恐惧评分（0-100）

        0 = 极度贪婪, 100 = 极度恐慌
        """
        if fear_indicator >= 5:
            return 90.0
        elif fear_indicator >= 2:
            return 70.0 + (fear_indicator - 2) * 6.7
        elif fear_indicator >= 1:
            return 50.0 + (fear_indicator - 1) * 20
        elif fear_indicator >= 0.5:
            return 30.0 + (fear_indicator - 0.5) * 40
        else:
            return fear_indicator * 60

    def get_latest_breadth(self) -> Dict[str, Any]:
        """获取最新的广度数据"""
        return self._history[-1] if self._history else {}

    def get_breadth_summary(self) -> Dict[str, Any]:
        """获取广度摘要"""
        if not self._history:
            return {"status": "no_data"}

        latest = self._history[-1]
        avg_breadth = sum(h["breadth_ratio"] for h in self._history) / len(self._history)
        avg_fear = sum(h["fear_score"] for h in self._history) / len(self._history)

        return {
            "latest": latest,
            "avg_breadth_ratio": avg_breadth,
            "avg_fear_score": avg_fear,
            "history_size": len(self._history),
        }


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
        self._breadth_tracker = MarketBreadthTracker()
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
            self._session_manager = MarketSessionManager()
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
            from deva.naja.infra.observability.auto_tuner import get_auto_tuner, TuneCondition

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
            from deva.naja.infra.observability.auto_tuner import get_auto_tuner, trigger_business_adjustment

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
                await asyncio.wait_for(asyncio.shield(self._task), timeout=2.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
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
        with _get_audit()(loop_type="global_market", stage="scan_fetch", metadata={"phase": self._stats.get("us_trading_phase", "unknown")}) as audit:
            try:
                data = await self.api.fetch_all()
                fetch_latency = (time.time() - start_time) * 1000
                self._stats["fetch_latency_ms"] = fetch_latency

                if not data:
                    _global_market_log("未获取到市场数据")
                    self._stats["error_count"] += 1
                    audit.record_data_out({"status": "no_data", "error_count": self._stats["error_count"]})
                    return

                self._stats["success_count"] += 1
                self._last_market_data = data

                self._sync_to_propagation_engine(data)

                # 更新QueryState
                try:
                    from deva.naja.register import SR
                    
                    # 提取市场数据
                    symbols = []
                    returns = []
                    volumes = []
                    prices = []
                    
                    for code, md in data.items():
                        symbols.append(code)
                        returns.append(md.change_pct)
                        volumes.append(md.volume)
                        prices.append(md.current)
                    
                    # 发布全局市场数据事件
                    try:
                        from deva.naja.events import get_event_bus, GlobalMarketDataEvent
                        event_bus = get_event_bus()
                        event = GlobalMarketDataEvent(
                            symbols=symbols,
                            returns=returns,
                            volumes=volumes,
                            prices=prices,
                            timestamp=time.time(),
                            market='US',
                            source='global_market_scanner'
                        )
                        event_bus.publish(event)
                        log.info(f"[GlobalMarketScanner] 已发布GlobalMarketDataEvent: {len(symbols)}个股票")
                    except Exception as e:
                        log.error(f"[GlobalMarketScanner] 发布事件失败: {e}")
                except Exception as e:
                    log.error(f"[GlobalMarketScanner] 更新QueryState失败: {e}", exc_info=True)

                breadth_result = self._breadth_tracker.update_from_market_data(data)
                if breadth_result:
                    _global_market_log(f"市场广度: 涨跌比={breadth_result.get('breadth_ratio', 0):+.2f}, 恐惧={breadth_result.get('fear_score', 0):.0f}")

            except Exception as e:
                log.error(f"[GlobalMarketScanner] 获取数据异常: {e}")
                self._stats["error_count"] += 1
                audit.record_data_out({"status": "failed", "error": str(e)})
                return

            status_map = self._get_market_status_map()
            alerts = self._detect_alerts(data, status_map, breadth_result)

            if alerts:
                _global_market_log(f"检测到 {len(alerts)} 个告警")
                for alert in alerts:
                    self._alert_history.append(alert)
                    self._stats["alert_count"] += 1
                    self._stats["last_alert_time"] = time.time()
                    await self._emit_alert(alert)

            self._report_to_autotuner()
            audit.record_data_out({
                "status": "completed",
                "data_count": len(data) if data else 0,
                "alert_count": len(alerts) if alerts else 0,
                "success_count": self._stats["success_count"]
            })

    def _detect_alerts(self, data: Dict[str, MarketData], status_map: Dict[str, str], breadth: Dict[str, Any] = None) -> List[MarketAlert]:
        """检测告警"""
        alerts = []
        breadth_fear = 0.0
        if breadth and "latest" in breadth:
            breadth_fear = breadth["latest"].get("fear_score", 0.0)

        for code, md in data.items():
            market_status = status_map.get(md.market_id, "unknown")
            change_pct = md.change_pct
            abs_change = abs(change_pct)

            if abs_change < self.config.alert_threshold_single:
                continue

            is_abnormal = self._volatility_tracker.is_abnormal(
                md.market_id, change_pct, self.config.alert_threshold_volatility
            )

            base_severity = min(1.0, abs_change / 5.0)
            if breadth_fear >= 70:
                severity = min(1.0, base_severity * 1.5)
            elif breadth_fear >= 50:
                severity = min(1.0, base_severity * 1.2)
            else:
                severity = base_severity

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
                    "breadth_fear": breadth_fear,
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
        log.info(f"[GlobalMarketScanner] 开始获取市场数据...")
        data = await self.api.fetch_all()
        log.info(f"[GlobalMarketScanner] 成功获取 {len(data)} 个市场数据")
        self._last_market_data = data
        self._sync_to_propagation_engine(data)
        
        # 更新QueryState
        try:
            log.info(f"[GlobalMarketScanner] 开始更新QueryState...")
            from deva.naja.register import SR
            
            # 提取市场数据
            symbols = []
            returns = []
            volumes = []
            prices = []
            
            for code, md in data.items():
                symbols.append(code)
                returns.append(md.change_pct)
                volumes.append(md.volume)
                prices.append(md.current)
            
            log.info(f"[GlobalMarketScanner] 提取到 {len(symbols)} 个符号")
            
            # 从注册中心获取QueryState实例
            from deva.naja.application import get_app_container
            container = get_app_container()
            qs = container.query_state if container else None
            log.info(f"[GlobalMarketScanner] 从注册中心获取QueryState实例成功")
            
            qs.update_from_market(
                symbols=symbols,
                returns=returns,
                volumes=volumes,
                prices=prices
            )
            
            summary = qs.get_summary()
            log.info(f"[GlobalMarketScanner] QueryState更新成功: 市场状态={summary['market_regime']}, 关注焦点={summary['top_attention']}")
            
            # 更新UI的全局缓存
            try:
                log.info(f"[GlobalMarketScanner] 尝试更新UI的全局缓存...")
                import deva.naja.attention.ui.awakening
                deva.naja.attention.ui.awakening._query_state_instance = qs
                log.info(f"[GlobalMarketScanner] 成功更新UI的QueryState实例")
            except Exception as e:
                log.error(f"[GlobalMarketScanner] 更新UI QueryState实例失败: {e}", exc_info=True)
                
        except Exception as e:
            log.error(f"[GlobalMarketScanner] 更新QueryState失败: {e}", exc_info=True)
        
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

        breadth = self._breadth_tracker.get_breadth_summary()
        return {
            "us_trading_phase": self.session_manager.get_us_trading_phase(),
            "total_markets": len(status_map),
            "open_count": len(open_markets),
            "closed_count": len(closed_markets),
            "open_markets": open_markets,
            "status_map": status_map,
            "current_interval": self._stats["current_interval"],
            "breadth": breadth,
        }

    def get_breadth_status(self) -> Dict[str, Any]:
        """获取市场广度状态"""
        return self._breadth_tracker.get_breadth_summary()


    # ─── 流动性预测系统（已迁移到 cognition/liquidity/liquidity_predictor.py）───
    # 以下方法委托给 LiquidityPredictor，保持向后兼容

    @property
    def _liquidity_predictor(self) -> LiquidityPredictor:
        """获取流动性预测器（延迟初始化）"""
        if not hasattr(self, '_lp_instance'):
            self._lp_instance = get_liquidity_predictor(session_manager=self.session_manager)
        return self._lp_instance

    def _init_liquidity_system(self):
        """初始化流动性预测系统（委托给 LiquidityPredictor）"""
        _ = self._liquidity_predictor
        self._liquidity_initialized = True

    def predict_liquidity(self, source_market, signals, breadth_fear=None):
        """基于信号来源市场，预测对各目标市场的流动性影响（委托）"""
        self._liquidity_predictor.update_market_data_from_scanner(self._last_market_data)
        return self._liquidity_predictor.predict_liquidity(source_market, signals, breadth_fear)

    def verify_liquidity(self, target_market, actual_data):
        """验证对某个市场的预测是否正确（委托）"""
        return self._liquidity_predictor.verify_liquidity(target_market, actual_data)

    def get_liquidity_adjustment(self, target_market, actual_data=None):
        """获取对某个目标市场的调整指令（委托）"""
        return self._liquidity_predictor.get_liquidity_adjustment(target_market, actual_data)

    def get_all_market_adjustments(self):
        """获取所有市场的调整指令（委托）"""
        return self._liquidity_predictor.get_all_market_adjustments()

    def auto_verify_all_predictions(self, market_data_map):
        """自动验证所有有预测的市场（委托）"""
        return self._liquidity_predictor.auto_verify_all_predictions(market_data_map)

    def predict_and_auto_verify(self, source_market, signals, market_data_map=None, breadth_fear=None):
        """预测并自动验证（委托）"""
        self._liquidity_predictor.update_market_data_from_scanner(self._last_market_data)
        return self._liquidity_predictor.predict_and_auto_verify(source_market, signals, market_data_map, breadth_fear)

    def get_liquidity_status(self):
        """获取流动性系统状态（委托）"""
        return self._liquidity_predictor.get_liquidity_status()

    def set_narrative_signal(self, signal):
        """设置舆论信号（委托）"""
        return self._liquidity_predictor.set_narrative_signal(signal)

    def detect_resonance(self, market_signal, narrative_signal=None, breadth_fear=None):
        """检测信号共振（委托）"""
        return self._liquidity_predictor.detect_resonance(market_signal, narrative_signal, breadth_fear)

    def update_topic_heat(self, topic, change_pct, volume_ratio=1.0):
        """更新主题热度（委托）"""
        return self._liquidity_predictor.update_topic_heat(topic, change_pct, volume_ratio)

    def predict_topic_spread(self, topic, us_block_change):
        """预测主题扩散（委托）"""
        return self._liquidity_predictor.predict_topic_spread(topic, us_block_change)

    def get_topic_adjustment_for_block(self, block):
        """获取题材的主题调整指令（委托）"""
        return self._liquidity_predictor.get_topic_adjustment_for_block(block)

    def get_a_share_liquidity_prediction(self):
        """获取 A 股流动性预测（委托）"""
        return self._liquidity_predictor.get_a_share_liquidity_prediction()


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
