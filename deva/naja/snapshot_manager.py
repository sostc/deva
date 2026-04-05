"""SnapshotManager - 数据快照持久化管理器

职责：
1. 注意力榜单快照 - 每5分钟记录一次高注意力股票
2. 市场状态快照 - 每日收盘时记录市场整体状态
3. Bandit决策上下文快照 - 每次决策时记录上下文

用于复盘和系统进化。
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Set
from collections import deque

from deva import NB

log = logging.getLogger(__name__)

TABLE_ATTENTION_SNAPSHOTS = "naja_attention_snapshots"
TABLE_MARKET_STATE_DAILY = "naja_market_state_daily"
TABLE_BANDIT_DECISION_CONTEXT = "naja_bandit_decision_context"


@dataclass
class AttentionSnapshotRecord:
    """注意力榜单快照"""
    timestamp: float
    top_symbols: List[Dict[str, Any]]
    block_weights: Dict[str, float]
    active_blocks: List[str]
    market_context: Dict[str, Any]
    total_attention_count: int


@dataclass
class MarketStateSnapshot:
    """市场状态每日快照"""
    date: str
    timestamp: float
    market_data: Dict[str, Any]
    market_summary: Dict[str, Any]
    alerts: List[Dict[str, Any]]
    us_trading_phase: str
    narratives: List[str]
    liquidity_status: Dict[str, Any]


@dataclass
class BanditDecisionContext:
    """Bandit决策上下文"""
    decision_id: str
    timestamp: float
    action: str
    symbol: str
    price: float
    confidence: float
    quantity: float
    market_state: Dict[str, Any]
    attention_state: Dict[str, Any]
    reason: str
    portfolio_snapshot: Dict[str, Any]


class SnapshotManager:
    """数据快照管理器（单例）"""

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
        if getattr(self, '_initialized', False):
            return
        self._initialized = True

        self._attention_db = NB(TABLE_ATTENTION_SNAPSHOTS)
        self._market_db = NB(TABLE_MARKET_STATE_DAILY)
        self._decision_db = NB(TABLE_BANDIT_DECISION_CONTEXT)

        self._last_attention_snapshot = 0.0
        self._attention_snapshot_interval = 300

        self._last_market_snapshot = 0.0
        self._last_snapshot_date = ""

        log.info("SnapshotManager 初始化完成")

    def record_attention_snapshot(self, force: bool = False) -> Optional[AttentionSnapshotRecord]:
        """记录注意力榜单快照

        Args:
            force: 是否强制记录（忽略时间间隔）

        Returns:
            AttentionSnapshotRecord or None
        """
        now = time.time()

        if not force and (now - self._last_attention_snapshot) < self._attention_snapshot_interval:
            return None

        try:
            from deva.naja.attention.trading_center import get_trading_center

            tc = get_trading_center()
            os = tc.get_attention_os()
            scheduler = os.market_scheduler

            top_symbols = []
            try:
                symbol_weights = scheduler._symbol_weights
                if symbol_weights:
                    sorted_symbols = sorted(symbol_weights.items(), key=lambda x: x[1], reverse=True)[:20]
                    top_symbols = [
                        {"symbol": sym, "weight": float(wgt)}
                        for sym, wgt in sorted_symbols
                    ]
            except Exception as e:
                log.debug(f"获取top_symbols失败: {e}")

            block_weights = {}
            try:
                block_weights = scheduler._block_weights
                block_weights = {k: float(v) for k, v in block_weights.items()}
            except Exception as e:
                log.debug(f"获取block_weights失败: {e}")

            active_blocks = list(getattr(tc, '_cached_active_blocks', set()) or set())

            market_context = {}
            try:
                from deva.naja.radar.global_market_scanner import get_global_market_scanner
                scanner = get_global_market_scanner()
                scanner_data = scanner.get_last_data()
                summary = scanner.get_market_summary()
                if scanner_data:
                    market_context = {
                        "us_phase": summary.get("us_trading_phase", "unknown"),
                        "open_markets": summary.get("open_markets", []),
                        "market_count": len(scanner_data),
                    }
            except Exception as e:
                log.debug(f"获取market_context失败: {e}")

            record = AttentionSnapshotRecord(
                timestamp=now,
                top_symbols=top_symbols,
                block_weights=block_weights,
                active_blocks=active_blocks,
                market_context=market_context,
                total_attention_count=len(top_symbols)
            )

            key = f"attn_{int(now)}"
            self._attention_db[key] = asdict(record)
            self._last_attention_snapshot = now

            log.debug(f"注意力快照已记录: {len(top_symbols)} 个高注意力股票")
            return record

        except Exception as e:
            log.error(f"记录注意力快照失败: {e}")
            return None

    def record_market_state_snapshot(self, force: bool = False) -> Optional[MarketStateSnapshot]:
        """记录每日市场状态快照

        Args:
            force: 是否强制记录（忽略日期检查）

        Returns:
            MarketStateSnapshot or None
        """
        now = time.time()
        from datetime import datetime
        today = datetime.fromtimestamp(now).strftime("%Y-%m-%d")

        if not force and (self._last_snapshot_date == today and now - self._last_market_snapshot < 3600):
            return None

        try:
            from deva.naja.radar.global_market_scanner import get_global_market_scanner
            scanner = get_global_market_scanner()

            market_data = {}
            try:
                raw_data = scanner.get_last_data()
                for code, md in raw_data.items():
                    market_data[code] = {
                        "name": md.name,
                        "current": md.current,
                        "change_pct": md.change_pct,
                        "prev_close": md.prev_close,
                        "volume": md.volume,
                    }
            except Exception as e:
                log.debug(f"获取market_data失败: {e}")

            summary = {}
            try:
                summary = scanner.get_market_summary()
            except Exception as e:
                log.debug(f"获取summary失败: {e}")

            alerts = []
            try:
                raw_alerts = scanner.get_alerts(limit=10)
                alerts = [a.to_dict() if hasattr(a, 'to_dict') else a for a in raw_alerts]
            except Exception as e:
                log.debug(f"获取alerts失败: {e}")

            narratives = []
            try:
                from deva.naja.cognition.sector_narrative import get_narrative_tracker
                tracker = get_narrative_tracker()
                if tracker:
                    narratives = [n.get("name", n.get("narrative", "")) for n in tracker.get_active_narratives()[:5]]
            except Exception:
                pass

            liquidity_status = {}
            try:
                liq_pred = scanner.get_a_share_liquidity_prediction()
                if liq_pred:
                    liquidity_status = {
                        "signal": liq_pred.signal,
                        "confidence": liq_pred.confidence,
                        "valid_until": liq_pred.valid_until,
                    }
            except Exception:
                pass

            record = MarketStateSnapshot(
                date=today,
                timestamp=now,
                market_data=market_data,
                market_summary=summary,
                alerts=alerts,
                us_trading_phase=summary.get("us_trading_phase", "unknown"),
                narratives=narratives,
                liquidity_status=liquidity_status
            )

            key = f"market_{today}_{int(now)}"
            self._market_db[key] = asdict(record)
            self._last_market_snapshot = now
            self._last_snapshot_date = today

            log.info(f"市场状态快照已记录: {today}, 市场数={len(market_data)}, 叙事={len(narratives)}")
            return record

        except Exception as e:
            log.error(f"记录市场状态快照失败: {e}")
            return None

    def record_bandit_decision(
        self,
        action: str,
        symbol: str,
        price: float,
        confidence: float,
        quantity: float,
        reason: str = ""
    ) -> Optional[BanditDecisionContext]:
        """记录Bandit决策上下文

        Args:
            action: BUY/SELL/HOLD
            symbol: 股票代码
            price: 价格
            confidence: 置信度
            quantity: 数量
            reason: 决策原因

        Returns:
            BanditDecisionContext or None
        """
        now = time.time()
        decision_id = f"dec_{int(now * 1000)}"

        try:
            market_state = self._get_current_market_state()
            attention_state = self._get_current_attention_state()
            portfolio_snapshot = self._get_portfolio_snapshot()

            record = BanditDecisionContext(
                decision_id=decision_id,
                timestamp=now,
                action=action,
                symbol=symbol,
                price=price,
                confidence=confidence,
                quantity=quantity,
                market_state=market_state,
                attention_state=attention_state,
                reason=reason,
                portfolio_snapshot=portfolio_snapshot
            )

            self._decision_db[decision_id] = asdict(record)

            log.debug(f"Bandit决策已记录: {decision_id} {action} {symbol} @{price}")
            return record

        except Exception as e:
            log.error(f"记录Bandit决策失败: {e}")
            return None

    def _get_current_market_state(self) -> Dict[str, Any]:
        """获取当前市场状态"""
        state = {
            "us_phase": "unknown",
            "index_changes": {},
            "alerts_count": 0,
        }

        try:
            scanner = get_global_market_scanner()
            summary = scanner.get_market_summary()
            state["us_phase"] = summary.get("us_trading_phase", "unknown")

            data = scanner.get_last_data()
            for code, md in list(data.items())[:5]:
                state["index_changes"][code] = md.change_pct

            alerts = scanner.get_alerts(limit=20)
            state["alerts_count"] = len(alerts)
        except Exception as e:
            log.debug(f"获取market_state失败: {e}")

        return state

    def _get_current_attention_state(self) -> Dict[str, Any]:
        """获取当前注意力状态"""
        state = {
            "top_symbols": [],
            "active_blocks": [],
            "block_weights": {},
        }

        try:
            from deva.naja.attention.trading_center import get_trading_center
            tc = get_trading_center()
            os = tc.get_attention_os()
            scheduler = os.market_scheduler

            try:
                symbol_weights = scheduler._symbol_weights
                if symbol_weights:
                    sorted_symbols = sorted(symbol_weights.items(), key=lambda x: x[1], reverse=True)[:10]
                    state["top_symbols"] = [sym for sym, _ in sorted_symbols]
            except Exception:
                pass

            state["active_blocks"] = list(getattr(tc, '_cached_active_blocks', set()) or set())

            try:
                block_weights = scheduler._block_weights
                state["block_weights"] = {k: float(v) for k, v in block_weights.items()}
            except Exception:
                pass

        except Exception as e:
            log.debug(f"获取attention_state失败: {e}")

        return state

    def _get_portfolio_snapshot(self) -> Dict[str, Any]:
        """获取当前持仓快照"""
        snapshot = {
            "accounts": {},
            "total_value": 0.0,
            "total_pnl": 0.0,
        }

        try:
            from deva.naja.bandit.portfolio_manager import get_portfolio_manager
            pm = get_portfolio_manager()

            all_summaries = pm.get_all_summaries()
            for name, summary in all_summaries.items():
                snapshot["accounts"][name] = summary
                snapshot["total_value"] += summary.get("total_value", 0.0)
                snapshot["total_pnl"] += summary.get("total_profit_loss", 0.0)

        except Exception as e:
            log.debug(f"获取portfolio_snapshot失败: {e}")

        return snapshot

    def get_attention_snapshots(self, hours: int = 24, limit: int = 100) -> List[Dict[str, Any]]:
        """获取最近的注意力快照"""
        results = []
        cutoff = time.time() - (hours * 3600)

        try:
            for key in self._attention_db.keys():
                try:
                    record = self._attention_db.get(key)
                    if record and record.get("timestamp", 0) > cutoff:
                        results.append(record)
                except Exception:
                    pass

            results.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
            return results[:limit]

        except Exception as e:
            log.error(f"获取attention_snapshots失败: {e}")
            return []

    def get_market_snapshots(self, days: int = 7) -> List[Dict[str, Any]]:
        """获取最近的市场状态快照"""
        results = []
        cutoff = time.time() - (days * 86400)

        try:
            for key in self._market_db.keys():
                try:
                    record = self._market_db.get(key)
                    if record and record.get("timestamp", 0) > cutoff:
                        results.append(record)
                except Exception:
                    pass

            results.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
            return results

        except Exception as e:
            log.error(f"获取market_snapshots失败: {e}")
            return []

    def get_decision_contexts(self, hours: int = 24, limit: int = 100) -> List[Dict[str, Any]]:
        """获取最近的Bandit决策上下文"""
        results = []
        cutoff = time.time() - (hours * 3600)

        try:
            for key in self._decision_db.keys():
                try:
                    record = self._decision_db.get(key)
                    if record and record.get("timestamp", 0) > cutoff:
                        results.append(record)
                except Exception:
                    pass

            results.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
            return results[:limit]

        except Exception as e:
            log.error(f"获取decision_contexts失败: {e}")
            return []

    def start_periodic_snapshots(self):
        """启动定期快照任务"""
        import threading

        def snapshot_loop():
            while True:
                try:
                    self.record_attention_snapshot()
                    self.record_market_state_snapshot()
                except Exception as e:
                    log.error(f"定期快照失败: {e}")
                time.sleep(300)

        thread = threading.Thread(target=snapshot_loop, daemon=True)
        thread.start()
        log.info("定期快照任务已启动")


_snapshot_manager: Optional[SnapshotManager] = None


def get_snapshot_manager() -> SnapshotManager:
    """获取快照管理器单例"""
    global _snapshot_manager
    if _snapshot_manager is None:
        _snapshot_manager = SnapshotManager()
    return _snapshot_manager


def record_attention_snapshot(force: bool = False) -> Optional[AttentionSnapshotRecord]:
    """快捷函数：记录注意力快照"""
    return get_snapshot_manager().record_attention_snapshot(force)


def record_market_state_snapshot(force: bool = False) -> Optional[MarketStateSnapshot]:
    """快捷函数：记录市场状态快照"""
    return get_snapshot_manager().record_market_state_snapshot(force)


def record_bandit_decision(
    action: str,
    symbol: str,
    price: float,
    confidence: float,
    quantity: float,
    reason: str = ""
) -> Optional[BanditDecisionContext]:
    """快捷函数：记录Bandit决策"""
    return get_snapshot_manager().record_bandit_decision(
        action, symbol, price, confidence, quantity, reason
    )