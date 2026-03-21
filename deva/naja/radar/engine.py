"""Radar Engine - 感知层：NarrativeScanner + MarketScanner"""

from __future__ import annotations

import threading
import time
import uuid
import math
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


NARRATIVE_KEYWORDS: Dict[str, List[str]] = {
    "AI": [
        "AI", "AIGC", "人工智能", "大模型", "多模态", "生成式", "GPT", "ChatGPT", "Sora",
        "算力", "智能体", "机器人", "自动驾驶", "NLP", "语音", "视觉",
    ],
    "芯片": [
        "芯片", "半导体", "集成电路", "晶圆", "光刻", "EDA", "封测", "制程", "GPU", "CPU",
        "HBM", "DRAM", "NAND", "SoC", "ASIC", "FPGA", "存储",
    ],
    "新能源": [
        "新能源", "光伏", "风电", "储能", "锂电", "电池", "充电桩", "氢能", "碳中和", "碳达峰",
        "新能源车", "电动车", "逆变器",
    ],
    "医药": [
        "医药", "生物医药", "创新药", "疫苗", "医疗", "医疗器械", "临床", "试验", "基因",
        "细胞治疗", "CXO", "医院", "药品", "药企",
    ],
}


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


class NarrativeScanner:
    """
    叙事扫描器 - 感知新闻/文本数据中的叙事

    职责：
    - 检测叙事出现、扩散、高潮、消退
    - 追踪叙事之间的关系
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        cfg = config or {}
        self._recent_window = float(cfg.get("narrative_recent_window_seconds", 6 * 3600))
        self._prev_window = float(cfg.get("narrative_prev_window_seconds", 6 * 3600))
        self._peak_count = int(cfg.get("narrative_peak_count", 8))
        self._spread_count = int(cfg.get("narrative_spread_count", 4))
        self._peak_score = float(cfg.get("narrative_peak_score", 0.8))
        self._spread_score = float(cfg.get("narrative_spread_score", 0.55))
        self._emit_cooldown = float(cfg.get("narrative_emit_cooldown_seconds", 120))

        self._narrative_states: Dict[str, Dict[str, Any]] = defaultdict(self._make_narrative_state)
        self._last_emit: Dict[str, float] = {}

    def _make_narrative_state(self) -> Dict[str, Any]:
        return {
            "hits": [],
            "stage": "萌芽",
            "last_stage_change": 0.0,
            "attention_score": 0.0,
        }

    def scan(self, content: str, timestamp: float, metadata: Optional[Dict] = None) -> List[Dict]:
        """
        扫描文本内容，检测叙事信号

        Returns:
            List of detected narratives with their signals
        """
        if not content:
            return []

        results = []
        content_lower = content.lower()

        for narrative, keywords in NARRATIVE_KEYWORDS.items():
            hit_keywords = []
            for kw in keywords:
                if kw.lower() in content_lower or kw in content:
                    hit_keywords.append(kw)

            if not hit_keywords:
                continue

            state = self._narrative_states[narrative]
            old_hits_count = len(state["hits"])
            state["hits"].append((timestamp, hit_keywords))

            self._prune_hits(state, timestamp)
            metrics = self._compute_metrics(state, timestamp)
            new_stage = self._determine_stage(metrics, state)

            old_stage = state.get("_last_emitted_stage")
            stage_changed = new_stage != old_stage
            state["stage"] = new_stage

            first_emit = old_hits_count == 0 or old_stage is None
            is_stage_change = stage_changed and old_stage is not None

            if first_emit and self._should_emit(narrative, timestamp):
                state["_last_emitted_stage"] = new_stage
                results.append({
                    "source": "narrative",
                    "narrative": narrative,
                    "stage": new_stage,
                    "score": metrics["attention_score"],
                    "content": f"{narrative}叙事进入{new_stage}阶段",
                    "keywords": hit_keywords,
                    "timestamp": timestamp,
                    "metadata": metadata or {},
                })
            elif is_stage_change:
                state["_last_emitted_stage"] = new_stage
                results.append({
                    "source": "narrative",
                    "narrative": narrative,
                    "stage": new_stage,
                    "score": metrics["attention_score"],
                    "content": f"{narrative}叙事进入{new_stage}阶段",
                    "keywords": hit_keywords,
                    "timestamp": timestamp,
                    "metadata": metadata or {},
                })

        return results

    def _prune_hits(self, state: Dict, now_ts: float) -> None:
        cutoff = now_ts - self._recent_window * 12
        state["hits"] = [(ts, kws) for ts, kws in state["hits"] if ts >= cutoff]

    def _compute_metrics(self, state: Dict, now_ts: float) -> Dict[str, float]:
        recent_cutoff = now_ts - self._recent_window
        prev_cutoff = recent_cutoff - self._prev_window

        recent_hits = [(ts, kws) for ts, kws in state["hits"] if ts >= recent_cutoff]
        prev_hits = [(ts, kws) for ts, kws in state["hits"] if prev_cutoff <= ts < recent_cutoff]

        recent_count = len(recent_hits)
        prev_count = len(prev_hits)

        count_score = 1.0 - math.exp(-recent_count / max(1, 8.0))
        attention_score = 0.6 * count_score + 0.4 * min(1.0, recent_count / 10.0)
        trend = (recent_count - prev_count) / max(prev_count, 1)

        return {
            "recent_count": recent_count,
            "prev_count": prev_count,
            "attention_score": attention_score,
            "trend": trend,
        }

    def _determine_stage(self, metrics: Dict, state: Dict) -> str:
        recent_count = metrics["recent_count"]
        attention_score = metrics["attention_score"]

        # 首次出现 = 萌芽
        if recent_count == 1:
            return "萌芽"
        # 持续减少 = 消退
        if recent_count <= 1 and attention_score <= 0.25:
            return "消退"
        # 高频率或高分 = 高潮
        if recent_count >= self._peak_count or attention_score >= self._peak_score:
            return "高潮"
        # 有增长或中等水平 = 扩散
        if recent_count >= self._spread_count or metrics["trend"] >= 0.3 or attention_score >= self._spread_score:
            return "扩散"
        return "萌芽"

    def _should_emit(self, narrative: str, now_ts: float) -> bool:
        last_ts = self._last_emit.get(narrative, 0.0)
        if now_ts - last_ts < self._emit_cooldown:
            return False
        self._last_emit[narrative] = now_ts
        return True


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
            "source": "market",
            "signal_type": "pattern",
            "score": min(1.0, len(window) / 10.0),
            "content": f"{signal_type}模式在短时间内重复 {len(window)} 次",
            "raw_data": {"count": len(window), "window_seconds": self._pattern_window_seconds},
            "timestamp": timestamp,
            "metadata": {"strategy_id": strategy_id, "signal_type": signal_type},
        }

    def scan_drift(self, strategy_id: str, score: float, timestamp: float) -> Optional[Dict]:
        """检测概念漂移"""
        if not _RIVER_AVAILABLE:
            return None

        detector = self._drift_detectors.get(strategy_id)
        if detector is None:
            detector = drift.ADWIN()
            self._drift_detectors[strategy_id] = detector

        detector.update(score)
        if detector.change_detected:
            return {
                "source": "market",
                "signal_type": "drift",
                "score": abs(score),
                "content": "检测到概念漂移",
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
            "source": "market",
            "signal_type": "anomaly",
            "score": min(1.0, abs(z) / 5.0),
            "content": f"异常波动 (z={z:.2f})",
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
                "source": "market",
                "signal_type": "sector_anomaly",
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

        self._db = NB(RADAR_EVENTS_TABLE)
        self._state_lock = threading.RLock()

        cfg = get_radar_config()
        self._retention_days = float(cfg.get("event_retention_days", 7))
        self._cleanup_interval_seconds = float(cfg.get("cleanup_interval_seconds", 600))
        self._macro_only = bool(cfg.get("macro_only", True))
        self._cleanup_thread = None
        self._stop_cleanup = threading.Event()

        self.narrative_scanner = NarrativeScanner(cfg)
        self.market_scanner = MarketScanner(cfg)

        if self._retention_days > 0 and self._cleanup_interval_seconds > 0:
            self._start_cleanup_thread()

        self._initialized = True

    def ingest_result(self, result: Any) -> List[RadarEvent]:
        """处理策略结果（行情相关）"""
        payload = self._extract_payload(result)
        if payload is None:
            return []

        events: List[RadarEvent] = []
        with self._state_lock:
            pattern_sig = self.market_scanner.scan_pattern(
                strategy_id=str(getattr(result, "strategy_id", "")),
                signal_type=payload.get("signal_type", ""),
                timestamp=time.time()
            )
            if pattern_sig:
                events.append(self._signal_to_event(pattern_sig))

            drift_sig = self.market_scanner.scan_drift(
                strategy_id=str(getattr(result, "strategy_id", "")),
                score=payload.get("score", 0),
                timestamp=time.time()
            )
            if drift_sig:
                events.append(self._signal_to_event(drift_sig))

            anomaly_sig = self.market_scanner.scan_anomaly(
                strategy_id=str(getattr(result, "strategy_id", "")),
                signal_type=payload.get("signal_type", ""),
                score=payload.get("score", 0),
                timestamp=time.time()
            )
            if anomaly_sig:
                events.append(self._signal_to_event(anomaly_sig))

        stored_events: List[RadarEvent] = []
        for event in events:
            self._apply_user_attention(event)
            if self._macro_only and not self._is_macro_event(event):
                continue
            self._store_event(event)
            stored_events.append(event)

        self._emit_to_insight(stored_events)
        return stored_events

    def ingest_narrative(self, content: str, metadata: Optional[Dict] = None) -> List[Dict]:
        """
        处理叙事内容（新闻/文本）

        Args:
            content: 文本内容
            metadata: 附加元数据

        Returns:
            检测到的叙事信号列表
        """
        timestamp = time.time()
        signals = self.narrative_scanner.scan(content, timestamp, metadata)

        events = []
        for sig in signals:
            event = RadarEvent(
                id=f"narrative_{uuid.uuid4().hex[:12]}",
                ts=timestamp,
                event_type=f"narrative_{sig.get('stage', 'unknown')}",
                score=sig.get("score", 0.5),
                strategy_id="narrative_scanner",
                strategy_name="NarrativeScanner",
                signal_type="narrative",
                message=sig.get("content", ""),
                payload=sig.get("raw_data", {}),
                source="narrative",
            )
            self._store_event(event)
            events.append(event)

        self._emit_to_insight(events)
        return signals

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
        self._emit_to_insight([event])
        return event

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

    def _emit_to_insight(self, events: List[RadarEvent]) -> None:
        """将雷达事件发送到 InsightEngine"""
        if not events:
            return

        try:
            from ..insight import get_insight_engine
        except Exception:
            return

        try:
            insight = get_insight_engine()
        except Exception:
            return

        for event in events:
            signal = event.to_insight_signal()
            try:
                insight.ingest_signal(signal)
            except Exception:
                continue

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
