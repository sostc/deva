"""Radar Engine - 感知层：MarketScanner

只负责发现行情异常信号，不做调度与结论
叙事追踪已移至 cognition 层
新闻获取已移至 news_fetcher.py
"""

from __future__ import annotations

import threading
import time
import uuid
import math
import os
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional

from deva import NB

from ..config import get_radar_config

try:
    from river import drift
    _RIVER_AVAILABLE = True
except Exception:
    drift = None
    _RIVER_AVAILABLE = False

from .news_fetcher import RadarNewsFetcher, RadarNewsProcessor


def _radar_debug_log(msg: str):
    """雷达调试日志"""
    if os.environ.get("NAJA_RADAR_DEBUG") == "true":
        import logging
        logging.getLogger(__name__).info(f"[Radar-Debug] {msg}")


def _clamp_event_score(score: Any) -> float:
    try:
        value = abs(float(score))
    except Exception:
        return 0.5
    if value <= 1.0:
        return value
    if value <= 100.0:
        return min(1.0, value / 100.0)
    return min(1.0, value / 5.0)


RADAR_EVENTS_TABLE = "naja_radar_events"


@dataclass
class RadarEvent:
    id: str
    ts: float
    event_type: str
    score: float
    strategy_id: str
    strategy_name: str
    signal_type: str = ""
    message: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    source: str = "market"

    def to_dict(self) -> dict:
        return {
            "event_id": self.id,
            "timestamp": self.ts,
            "event_type": self.event_type,
            "score": self.score,
            "strategy_id": self.strategy_id,
            "strategy_name": self.strategy_name,
            "signal_type": self.signal_type,
            "message": self.message,
            "payload": self.payload,
            "source": self.source,
        }

    def to_insight_signal(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "signal_type": f"{self.event_type}",
            "score": _clamp_event_score(self.score),
            "content": self.message,
            "raw_data": self.payload,
            "timestamp": self.ts,
            "metadata": {
                "strategy_id": self.strategy_id,
                "strategy_name": self.strategy_name,
                "signal_type": self.signal_type,
            },
        }


class MarketScanner:
    """
    市场扫描器 - 感知行情数据中的异常

    职责：
    - Pattern：同一信号模式重复出现
    - Drift：概念漂移检测
    - Anomaly：统计异常检测
    - SectorAnomaly：板块联动异常
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        cfg = config or {}
        self._pattern_window_seconds = float(cfg.get("pattern_window_seconds", 300))
        self._pattern_min_count = int(cfg.get("pattern_min_count", 3))
        self._pattern_cooldown_seconds = float(cfg.get("pattern_cooldown_seconds", 120))

        self._pattern_hits: Dict[str, Deque[float]] = defaultdict(deque)
        self._pattern_last_emit: Dict[str, float] = {}

        self._drift_detectors: Dict[str, Any] = {}
        self._anomaly_stats: Dict[str, Dict[str, float]] = {}

    def scan_pattern(self, strategy_id: str, signal_type: str, timestamp: float) -> Optional[Dict]:
        """检测信号模式重复"""
        key = f"{strategy_id}:{signal_type}"
        window = self._pattern_hits[key]
        window.append(timestamp)

        cutoff = timestamp - self._pattern_window_seconds
        while window and window[0] < cutoff:
            window.popleft()

        if len(window) < self._pattern_min_count:
            return None

        last_emit = self._pattern_last_emit.get(key, 0)
        if timestamp - last_emit < self._pattern_cooldown_seconds:
            return None

        self._pattern_last_emit[key] = timestamp
        return {
            "source": "radar",
            "signal_type": "radar_pattern",
            "score": min(1.0, len(window) / 10.0),
            "content": f"{signal_type}模式在短时间内重复 {len(window)} 次",
            "raw_data": {"count": len(window), "window_seconds": self._pattern_window_seconds},
            "timestamp": timestamp,
            "metadata": {"strategy_id": strategy_id, "signal_type": signal_type},
        }

    def scan_drift(self, strategy_id: str, score: float, timestamp: float) -> Optional[Dict]:
        """检测感知数据分布漂移 (Radar 感知层职责)"""
        if not _RIVER_AVAILABLE:
            return None

        detector = self._drift_detectors.get(strategy_id)
        if detector is None:
            detector = drift.ADWIN()
            self._drift_detectors[strategy_id] = detector

        detector.update(score)
        if detector.drift_detected:
            return {
                "source": "radar",
                "signal_type": "radar_data_distribution_shift",
                "score": abs(score),
                "content": "Radar感知层检测到数据分布漂移",
                "raw_data": {"value": score},
                "timestamp": timestamp,
                "metadata": {"strategy_id": strategy_id},
            }
        return None

    def scan_anomaly(self, strategy_id: str, signal_type: str, score: float, timestamp: float) -> Optional[Dict]:
        """检测统计异常"""
        key = f"{strategy_id}:{signal_type}"
        stats = self._anomaly_stats.get(key)
        if stats is None:
            stats = {"count": 0.0, "mean": 0.0, "m2": 0.0}
            self._anomaly_stats[key] = stats

        stats["count"] += 1.0
        delta = score - stats["mean"]
        stats["mean"] += delta / stats["count"]
        delta2 = score - stats["mean"]
        stats["m2"] += delta * delta2

        if stats["count"] < 30:
            return None

        variance = stats["m2"] / max(1.0, stats["count"] - 1.0)
        if variance <= 0:
            return None

        z = (score - stats["mean"]) / (variance ** 0.5)
        if abs(z) < 3.0:
            return None

        return {
            "source": "radar",
            "signal_type": "radar_anomaly",
            "score": min(1.0, abs(z) / 5.0),
            "content": f"Radar检测到统计异常 (z={z:.2f})",
            "raw_data": {"z_score": z, "value": score, "mean": stats["mean"]},
            "timestamp": timestamp,
            "metadata": {"strategy_id": strategy_id, "signal_type": signal_type},
        }

    def scan_sector_anomaly(
        self,
        sector_id: str,
        symbols: List[str],
        returns: List[float],
        timestamp: float
    ) -> Optional[Dict]:
        """检测板块联动异常 - 齐涨齐跌"""
        if len(symbols) < 3:
            return None

        up_count = sum(1 for r in returns if r > 0.5)
        down_count = sum(1 for r in returns if r < -0.5)
        total = len(returns)

        up_ratio = up_count / total
        down_ratio = down_count / total

        if up_ratio > 0.7 or down_ratio > 0.7:
            direction = "上涨" if up_ratio > 0.7 else "下跌"
            return {
                "source": "radar",
                "signal_type": "radar_sector_anomaly",
                "score": max(up_ratio, down_ratio),
                "content": f"板块{sector_id}出现齐涨齐跌异常：{direction}家数占比{max(up_ratio, down_ratio):.1%}",
                "raw_data": {
                    "sector_id": sector_id,
                    "symbols": symbols,
                    "returns": returns,
                    "up_ratio": up_ratio,
                    "down_ratio": down_ratio,
                },
                "timestamp": timestamp,
                "metadata": {"sector_id": sector_id},
            }
        return None


class RadarEngine:
    """
    雷达引擎 - 感知层

    职责：
    - NarrativeScanner：扫描新闻/文本叙事
    - MarketScanner：扫描行情异常
    - 统一信号输出到 InsightEngine

    这是感知器，不是思考器
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return

        # 确保交易时钟启动
        from .trading_clock import get_trading_clock
        get_trading_clock()

        self._db = NB(RADAR_EVENTS_TABLE)
        self._state_lock = threading.RLock()

        cfg = get_radar_config()
        self._retention_days = float(cfg.get("event_retention_days", 7))
        self._cleanup_interval_seconds = float(cfg.get("cleanup_interval_seconds", 600))
        self._macro_only = bool(cfg.get("macro_only", True))
        self._cleanup_thread = None
        self._stop_cleanup = threading.Event()

        self.market_scanner = MarketScanner(cfg)

        self._news_fetcher: Optional[RadarNewsFetcher] = None
        self._news_processor: Optional[RadarNewsProcessor] = None

        self._auto_start_news_fetcher = cfg.get("auto_start_news_fetcher", True)
        if self._auto_start_news_fetcher:
            _radar_debug_log("自动启动新闻获取器...")
            self.start_news_fetcher(cfg)

        if self._retention_days > 0 and self._cleanup_interval_seconds > 0:
            self._start_cleanup_thread()

        self._initialized = True

        _radar_debug_log("RadarEngine 初始化完成")

    def ingest_result(self, result: Any) -> List[RadarEvent]:
        """处理策略结果（行情相关）"""
        payload = self._extract_payload(result)
        if payload is None:
            return []

        _radar_debug_log(f"ingest_result: strategy={getattr(result, 'strategy_id', 'unknown')}, payload_keys={list(payload.keys()) if payload else []}")

        events: List[RadarEvent] = []
        with self._state_lock:
            pattern_sig = self.market_scanner.scan_pattern(
                strategy_id=str(getattr(result, "strategy_id", "")),
                signal_type=payload.get("signal_type", ""),
                timestamp=time.time()
            )
            if pattern_sig:
                _radar_debug_log(f"  检测到模式信号: {pattern_sig.get('content', '')[:50]}")
                events.append(self._signal_to_event(pattern_sig))

            drift_sig = self.market_scanner.scan_drift(
                strategy_id=str(getattr(result, "strategy_id", "")),
                score=payload.get("score", 0),
                timestamp=time.time()
            )
            if drift_sig:
                _radar_debug_log(f"  检测到漂移信号: score={drift_sig.get('score', 0):.3f}")
                events.append(self._signal_to_event(drift_sig))

            anomaly_sig = self.market_scanner.scan_anomaly(
                strategy_id=str(getattr(result, "strategy_id", "")),
                signal_type=payload.get("signal_type", ""),
                score=payload.get("score", 0),
                timestamp=time.time()
            )
            if anomaly_sig:
                _radar_debug_log(f"  检测到异常信号: {anomaly_sig.get('content', '')[:50]}")
                events.append(self._signal_to_event(anomaly_sig))

        stored_events: List[RadarEvent] = []
        for event in events:
            self._apply_user_attention(event)
            if self._macro_only and not self._is_macro_event(event):
                _radar_debug_log(f"  事件被过滤(macro_only): {event.event_type}")
                continue
            self._store_event(event)
            stored_events.append(event)
            _radar_debug_log(f"  事件已存储: {event.event_type}, score={event.score:.3f}, message={event.message[:30]}")

        if stored_events:
            _radar_debug_log(f"ingest_result 完成: 产生 {len(stored_events)} 个事件")

        self._emit_to_insight_pool(stored_events)
        return stored_events

    def ingest_sector_data(
        self,
        sector_id: str,
        symbols: List[str],
        returns: List[float],
        timestamp: Optional[float] = None
    ) -> Optional[Dict]:
        """
        处理板块数据，检测板块联动异常

        Args:
            sector_id: 板块ID
            symbols: 股票代码列表
            returns: 涨跌幅列表
            timestamp: 时间戳

        Returns:
            检测到的异常信号
        """
        ts = timestamp or time.time()
        signal = self.market_scanner.scan_sector_anomaly(sector_id, symbols, returns, ts)

        if signal:
            event = self._signal_to_event(signal)
            self._store_event(event)
            self._emit_to_insight([event])
            return signal

        return None

    def ingest_attention_event(
        self,
        *,
        event_type: str,
        score: float,
        message: str,
        payload: Optional[Dict[str, Any]] = None,
        signal_type: str = "attention",
        strategy_id: str = "attention_system",
        strategy_name: str = "Attention System",
        ts: Optional[float] = None,
    ) -> RadarEvent:
        """接收注意力系统的直接注入"""
        event = self._build_event_from_fields(
            event_type=event_type,
            score=score,
            signal_type=signal_type,
            message=message,
            payload=payload or {},
            strategy_id=strategy_id,
            strategy_name=strategy_name,
            ts=ts,
        )
        self._apply_user_attention(event)
        if self._macro_only and not self._is_macro_event(event):
            return event
        self._store_event(event)
        self._emit_to_insight_pool([event])
        return event

    def start_news_fetcher(self, config: Optional[Dict[str, Any]] = None) -> bool:
        """
        启动雷达内置新闻获取器

        雷达完全独立获取和处理新闻，不依赖数据源系统

        Args:
            config: 雷达配置（从中提取新闻获取器配置）

        Returns:
            是否启动成功
        """
        try:
            if self._news_fetcher is not None and self._news_fetcher._running:
                _radar_debug_log("新闻获取器已在运行中")
                return True

            cfg = config or {}

            news_config = {
                "fetch_interval": cfg.get("news_fetch_interval", 60),
                "attention_threshold": cfg.get("news_attention_threshold", 0.6),
                "force_trading_mode": cfg.get("news_force_trading", False),
            }

            self._news_processor = RadarNewsProcessor(news_config)

            self._news_fetcher = RadarNewsFetcher(
                processor=self._news_processor,
                config=news_config,
            )

            self._news_fetcher.set_signal_callback(self._on_news_signal)

            self._news_fetcher.start()

            _radar_debug_log(f"新闻获取器启动成功, 间隔: {news_config['fetch_interval']}s")
            return True

        except Exception as e:
            _radar_debug_log(f"新闻获取器启动失败: {e}")
            return False

    def stop_news_fetcher(self):
        """停止雷达内置新闻获取器"""
        if self._news_fetcher:
            self._news_fetcher.stop()
            self._news_fetcher = None
            _radar_debug_log("新闻获取器已停止")

    def _on_news_signal(self, signal: Dict[str, Any]):
        """处理新闻信号"""
        _radar_debug_log(f"收到新闻信号: {signal.get('content', '')[:50]}")

        event = RadarEvent(
            id=signal.get("id", uuid.uuid4().hex[:16]),
            ts=signal.get("timestamp", time.time()),
            event_type="news_topic",
            score=signal.get("score", 0.5),
            strategy_id="radar_news",
            strategy_name="Radar News Fetcher",
            signal_type=signal.get("signal_type", "news_topic"),
            message=signal.get("content", ""),
            payload=signal.get("raw_data", {}),
            source="radar_news",
        )

        self._store_event(event)
        self._emit_to_insight_pool([event])

    def get_news_fetcher_stats(self) -> Optional[Dict[str, Any]]:
        """获取新闻获取器统计"""
        if self._news_fetcher is None:
            return None
        return self._news_fetcher.get_stats()

    def _signal_to_event(self, signal: Dict[str, Any]) -> RadarEvent:
        """将扫描信号转换为雷达事件"""
        return RadarEvent(
            id=f"radar_{uuid.uuid4().hex[:12]}",
            ts=signal.get("timestamp", time.time()),
            event_type=signal.get("signal_type", "unknown"),
            score=signal.get("score", 0.5),
            strategy_id=signal.get("metadata", {}).get("strategy_id", ""),
            strategy_name=signal.get("metadata", {}).get("strategy_name", "market_scanner"),
            signal_type=signal.get("signal_type", ""),
            message=signal.get("content", ""),
            payload=signal.get("raw_data", {}),
            source=signal.get("source", "market"),
        )

    def _apply_user_attention(self, event: RadarEvent) -> None:
        """为雷达事件打用户注意力分"""
        system_attention = _clamp_event_score(event.score)
        confidence = 0.5
        actionability = 0.4
        novelty = 0.5

        payload = event.payload or {}
        signal_type = str(payload.get("signal_type", event.signal_type)).upper()
        if signal_type in {"BUY", "SELL"}:
            actionability = 0.9
            confidence = max(confidence, 0.7)
        elif signal_type:
            actionability = 0.5

        if "confidence" in payload:
            try:
                confidence = max(confidence, float(payload.get("confidence")))
            except Exception:
                pass

        user_score = (
            0.4 * system_attention
            + 0.2 * confidence
            + 0.2 * actionability
            + 0.2 * novelty
        )

        payload["user_score"] = round(user_score, 3)
        payload["system_attention"] = round(system_attention, 3)
        payload["scope"] = self._infer_scope(payload)
        event.payload = payload

    def _infer_scope(self, payload: Dict[str, Any]) -> str:
        """判断事件作用域（macro / symbol）"""
        for key in ("stock_code", "symbol", "code", "ticker", "stock_name"):
            if payload.get(key):
                return "symbol"
        symbols = payload.get("symbols")
        if isinstance(symbols, list) and len(symbols) == 1:
            return "symbol"
        return "macro"

    def _is_macro_event(self, event: RadarEvent) -> bool:
        """宏观事件过滤"""
        if event.event_type == "symbol_attention_change":
            return False
        payload = event.payload or {}
        scope = payload.get("scope")
        if scope == "symbol":
            return False
        return True

    def get_recent_events(self, limit: int = 20) -> List[dict]:
        try:
            keys = list(self._db.keys())
            keys.sort(reverse=True)
            items = []
            for key in keys[:limit]:
                data = self._db.get(key)
                if isinstance(data, dict):
                    items.append(data)
            return items
        except Exception:
            return []

    def summarize(self, window_seconds: int = 600) -> dict:
        now = time.time()
        cutoff = now - max(60, int(window_seconds))
        events = []
        try:
            for _, data in list(self._db.items()):
                if not isinstance(data, dict):
                    continue
                if float(data.get("timestamp", 0)) >= cutoff:
                    events.append(data)
        except Exception:
            pass

        counts = defaultdict(int)
        for e in events:
            counts[str(e.get("event_type", "unknown"))] += 1

        return {
            "window_seconds": window_seconds,
            "event_count": len(events),
            "event_type_counts": dict(counts),
            "events": events[:50],
        }

    def prune_events(self, *, retention_days: Optional[float] = None) -> dict:
        days = self._retention_days if retention_days is None else float(retention_days)
        if days <= 0:
            return {"success": False, "error": "retention disabled"}

        cutoff = time.time() - days * 86400
        removed = 0

        with self._state_lock:
            try:
                keys = list(self._db.keys())
                for key in keys:
                    ts = None
                    if isinstance(key, str) and "_" in key:
                        prefix = key.split("_", 1)[0]
                        try:
                            ts = int(prefix) / 1000.0
                        except Exception:
                            ts = None

                    if ts is None:
                        data = self._db.get(key)
                        try:
                            ts = float(data.get("timestamp", 0))
                        except Exception:
                            ts = None

                    if ts is not None and ts < cutoff:
                        try:
                            del self._db[key]
                            removed += 1
                        except Exception:
                            pass
            except Exception as e:
                return {"success": False, "error": str(e)}

        return {"success": True, "removed": removed, "cutoff": cutoff}

    def _extract_payload(self, result: Any) -> Optional[Dict[str, Any]]:
        output = getattr(result, "output_full", None)
        if output is None:
            return None

        if isinstance(output, dict):
            signal_type = str(output.get("signal_type") or output.get("signal") or "")
            score = output.get("score", output.get("confidence"))
            return {
                "signal_type": signal_type,
                "score": score,
                "output": output,
            }
        return None

    def _build_event_from_fields(
        self,
        *,
        event_type: str,
        score: float,
        signal_type: str,
        message: str,
        payload: Dict[str, Any],
        strategy_id: str,
        strategy_name: str,
        ts: Optional[float] = None,
    ) -> RadarEvent:
        return RadarEvent(
            id=f"radar_{uuid.uuid4().hex[:12]}",
            ts=time.time() if ts is None else float(ts),
            event_type=event_type,
            score=score,
            strategy_id=strategy_id,
            strategy_name=strategy_name,
            signal_type=str(signal_type or ""),
            message=message,
            payload=payload or {},
        )

    def _store_event(self, event: RadarEvent) -> None:
        try:
            key = f"{int(event.ts * 1000)}_{event.id}"
            self._db[key] = event.to_dict()
        except Exception:
            return

    def _emit_to_insight_pool(self, events: List[RadarEvent]) -> None:
        """将雷达事件发送到 InsightPool 和 CrossSignalAnalyzer"""
        if not events:
            return

        try:
            from ..cognition.insight import get_insight_pool
        except Exception:
            pass
        else:
            try:
                pool = get_insight_pool()
                for event in events:
                    signal = event.to_insight_signal()
                    try:
                        pool.ingest_attention_event(signal)
                    except Exception:
                        continue
            except Exception:
                pass

        try:
            from ..cognition.cross_signal_analyzer import get_cross_signal_analyzer
        except Exception:
            return

        try:
            analyzer = get_cross_signal_analyzer()
            for event in events:
                try:
                    analyzer.ingest_news_from_event(event)
                except Exception:
                    continue
        except Exception:
            pass

    def _start_cleanup_thread(self) -> None:
        if self._cleanup_thread is not None and self._cleanup_thread.is_alive():
            return
        self._stop_cleanup.clear()
        self._cleanup_thread = threading.Thread(
            target=self._cleanup_loop,
            daemon=True,
            name="radar_cleanup",
        )
        self._cleanup_thread.start()

    def _cleanup_loop(self) -> None:
        while not self._stop_cleanup.is_set():
            self._stop_cleanup.wait(self._cleanup_interval_seconds)
            if self._stop_cleanup.is_set():
                break
            try:
                self.prune_events()
            except Exception:
                pass


_radar_engine: Optional[RadarEngine] = None
_radar_engine_lock = threading.Lock()


def get_radar_engine() -> RadarEngine:
    global _radar_engine
    if _radar_engine is None:
        with _radar_engine_lock:
            if _radar_engine is None:
                _radar_engine = RadarEngine()
    return _radar_engine
