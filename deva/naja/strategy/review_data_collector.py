"""
ReviewDataCollector - 强化版复盘数据收集器

功能：
1. 收集市场焦点（行情）
2. 收集舆情焦点（新闻）
3. 收集外部变化（市场+舆情综合）
4. 收集内部变化（交易+痛点+知识）
5. 与昨天对比，检测变化

设计原则：
- 变化驱动：有变化的才详细，无变化的只作为锚点
- 三焦点模型：市场焦点、舆情焦点、内部焦点
- 共振分析：检测三个方向的注意力是否共振
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from deva import NB

log = logging.getLogger(__name__)

REVIEW_STATE_TABLE = "naja_review_state"
NEWS_HISTORY_TABLE = "naja_news_history"


class ReviewDataCollector:
    """
    复盘数据收集器

    收集四个方向的数据：
    - market_focus: 市场焦点（行情）
    - news_focus: 舆情焦点（新闻）
    - external_changes: 外部变化
    - internal_changes: 内部变化
    """

    def __init__(self):
        self._nb = NB(REVIEW_STATE_TABLE)
        self._news_nb = NB(NEWS_HISTORY_TABLE)

    def collect_all(self) -> Dict[str, Any]:
        """收集所有数据"""
        return {
            "market_focus": self.collect_market_focus(),
            "news_focus": self.collect_news_focus(),
            "external_changes": self.collect_external_changes(),
            "internal_changes": self.collect_internal_changes(),
            "hotspot_shift": self.collect_hotspot_shift_history(),
        }

    def collect_hotspot_shift_history(self, lookback_hours: int = 24) -> Dict[str, Any]:
        """
        收集历史热点切换数据

        包含：
        - 题材切换事件时间线
        - 个股切换事件时间线
        - 热点快照历史
        """
        try:
            from deva.naja.market_hotspot.tracking.history_tracker import get_history_tracker

            tracker = get_history_tracker()
            if tracker is None:
                return {"status": "no_tracker"}

            cutoff_time = time.time() - (lookback_hours * 3600)

            block_events = []
            symbol_events = []

            for event in tracker.block_hotspot_events_medium:
                if event.timestamp < cutoff_time:
                    continue
                block_events.append({
                    'timestamp': event.timestamp,
                    'time': event.market_time,
                    'date': event.market_date,
                    'block_id': event.block_id,
                    'block_name': event.block_name,
                    'event_type': event.event_type,
                    'weight_change': event.weight_change,
                    'change_percent': event.change_percent,
                    'description': event.description,
                })

            for change in tracker.changes:
                if change.timestamp < cutoff_time:
                    continue
                if change.item_type != 'symbol':
                    continue
                symbol_events.append({
                    'timestamp': change.timestamp,
                    'time': change.market_time,
                    'symbol': change.item_id,
                    'name': change.item_name,
                    'change_type': change.change_type,
                    'old_weight': change.old_weight,
                    'new_weight': change.new_weight,
                    'change_percent': change.change_percent,
                    'price_change': change.price_change,
                    'description': change.description,
                })

            block_events.sort(key=lambda x: x['timestamp'], reverse=True)
            symbol_events.sort(key=lambda x: x['timestamp'], reverse=True)

            return {
                "status": "ok",
                "lookback_hours": lookback_hours,
                "block_event_count": len(block_events),
                "symbol_event_count": len(symbol_events),
                "block_events": block_events[:30],
                "symbol_events": symbol_events[:30],
                "recent_blocks": [e['block_name'] for e in block_events[:5]],
                "recent_symbols": [e['symbol'] for e in symbol_events[:5]],
            }

        except Exception as e:
            log.warning(f"[ReviewDataCollector] collect_hotspot_shift_history 失败: {e}")
            return {"status": "error", "error": str(e)}

    def collect_market_focus(self) -> Dict[str, Any]:
        """
        收集市场焦点（行情）

        包含：
        - 整体状态（涨跌、情绪）
        - 波动率
        - 市场广度
        - 资金流向
        - 行业热点
        """
        try:
            from deva.naja.strategy.daily_review import DailyReviewAnalyzer

            analyzer = DailyReviewAnalyzer()
            analyzer.step1_full_market()
            analyzer.step2_hot_narrative()
            mo = analyzer.market_overview

            if not mo:
                return {"status": "no_data"}

            sentiment = getattr(mo, "combined_sentiment", "未知")
            breadth = getattr(mo, "ashare_breadth", 0)

            result = {
                "status": "ok",
                "ashare": {
                    "avg_change": getattr(mo, "ashare_avg_change", 0),
                    "median_change": getattr(mo, "ashare_median_change", 0),
                    "sentiment": sentiment,
                    "breadth": breadth,
                    "advancing": getattr(mo, "ashare_advancing", 0),
                    "declining": getattr(mo, "ashare_declining", 0),
                    "effective_count": getattr(mo, "ashare_effective_count", 0),
                },
                "usstock": {
                    "avg_change": getattr(mo, "usstock_avg_change", 0),
                    "median_change": getattr(mo, "usstock_median_change", 0),
                    "sentiment": getattr(mo, "combined_sentiment", "未知"),
                    "breadth": getattr(mo, "usstock_breadth", 0),
                    "advancing": getattr(mo, "usstock_advancing", 0),
                    "declining": getattr(mo, "usstock_declining", 0),
                },
                "combined_sentiment": sentiment,
            }

            narrative_map = {}
            if analyzer.top_narratives:
                for n in analyzer.top_narratives[:5]:
                    narrative_map[n.narrative] = {
                        "avg_change": n.avg_change,
                        "gainer_ratio": n.gainer_ratio,
                        "stock_count": n.stock_count,
                    }
            result["narratives"] = narrative_map

            return result

        except Exception as e:
            log.warning(f"[ReviewDataCollector] collect_market_focus 失败: {e}")
            return {"status": "error", "error": str(e)}

    def collect_news_focus(self) -> Dict[str, Any]:
        """
        收集舆情焦点（新闻）

        包含：
        - 宏观舆情（地缘政治、宏观经济）
        - 行业舆情（按行业分类）
        - 今日新闻数量

        从持久化的每日摘要中读取（只读状态，不读实体）
        """
        try:
            from deva import NB

            nb = NB("naja_radar_news")
            daily_summary = nb.get("daily_summary", {})

            today = datetime.now().strftime('%Y-%m-%d')
            today_data = daily_summary.get(today, {})

            yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
            yesterday_data = daily_summary.get(yesterday, {})

            return {
                "status": "ok",
                "total_news": today_data.get("count", 0),
                "macro_news": [{"title": t} for t in today_data.get("macro_titles", [])],
                "macro_count": today_data.get("macro_count", 0),
                "industry_news": [{"title": t} for t in today_data.get("industry_titles", [])],
                "industry_count": today_data.get("industry_count", 0),
                "yesterday_total": yesterday_data.get("count", 0),
                "last_updated": today_data.get("last_updated", ""),
            }

        except Exception as e:
            log.warning(f"[ReviewDataCollector] collect_news_focus 失败: {e}")
            return {"status": "error", "error": str(e)}

    def collect_external_changes(self) -> Dict[str, Any]:
        """
        收集外部变化

        包含：
        - 叙事变化（排名、涨跌幅）
        - 情绪变化
        - 行业资金流向变化
        """
        try:
            today_data = self.collect_market_focus()
            yesterday_data = self._get_yesterday_state("market_focus")

            changes = {
                "narrative_changes": [],
                "sentiment_changes": [],
                "flow_changes": [],
            }

            if yesterday_data and yesterday_data.get("status") == "ok":
                today_narratives = today_data.get("narratives", {})
                yesterday_narratives = yesterday_data.get("narratives", {})

                for name, today_info in today_narratives.items():
                    yesterday_info = yesterday_narratives.get(name, {})
                    if yesterday_info:
                        change = today_info["avg_change"] - yesterday_info["avg_change"]
                        if abs(change) > 0.5:
                            changes["narrative_changes"].append({
                                "narrative": name,
                                "change": change,
                                "today": today_info["avg_change"],
                                "yesterday": yesterday_info["avg_change"],
                            })

                if today_data.get("combined_sentiment") != yesterday_data.get("combined_sentiment"):
                    changes["sentiment_changes"].append({
                        "today": today_data.get("combined_sentiment"),
                        "yesterday": yesterday_data.get("combined_sentiment"),
                    })

            self._save_today_state("market_focus", today_data)

            return {
                "status": "ok",
                "changes": changes,
                "has_changes": any(changes.values()) if changes else False,
            }

        except Exception as e:
            log.warning(f"[ReviewDataCollector] collect_external_changes 失败: {e}")
            return {"status": "error", "error": str(e)}

    def collect_internal_changes(self) -> Dict[str, Any]:
        """
        收集内部焦点变化

        包含：
        - 交易变动（买卖操作）
        - 知识学习（新知识/状态变化）
        - 痛点挖掘（新发现的产业链痛点）
        """
        try:
            changes = {
                "trade_changes": [],
                "knowledge_changes": [],
                "pain_point_changes": [],
            }

            trade_changes = self._get_trade_changes()
            if trade_changes:
                changes["trade_changes"] = trade_changes

            knowledge_changes = self._get_knowledge_changes()
            if knowledge_changes:
                changes["knowledge_changes"] = knowledge_changes

            pain_point_changes = self._get_pain_point_changes()
            if pain_point_changes:
                changes["pain_point_changes"] = pain_point_changes

            self._save_internal_changes(changes)

            return {
                "status": "ok",
                "has_changes": any(changes.values()) if changes else False,
                **changes,
            }

        except Exception as e:
            log.warning(f"[ReviewDataCollector] collect_internal_changes 失败: {e}")
            return {"status": "error", "error": str(e)}

    def _get_trade_changes(self) -> List[Dict]:
        """获取交易变动"""
        try:
            from deva.naja.bandit.portfolio_manager import get_portfolio_manager

            pm = get_portfolio_manager()
            account_names = pm.get_all_account_names()

            today_positions = {}
            for account_name in account_names:
                portfolio = pm.get_us_portfolio(account_name)
                if portfolio:
                    positions = portfolio.get_all_positions()
                    for pos in positions:
                        if hasattr(pos, 'symbol'):
                            symbol = pos.symbol
                            today_positions[symbol] = {"quantity": getattr(pos, 'quantity', 0)}

            yesterday_positions = self._get_yesterday_state("positions") or {}

            changes = []
            all_symbols = set(today_positions.keys()) | set(yesterday_positions.keys())

            for symbol in all_symbols:
                today_qty = today_positions.get(symbol, {}).get("quantity", 0)
                yesterday_qty = yesterday_positions.get(symbol, {}).get("quantity", 0)

                if today_qty != yesterday_qty:
                    action = "买入" if today_qty > yesterday_qty else "卖出"
                    change_qty = today_qty - yesterday_qty
                    changes.append({
                        "symbol": symbol,
                        "action": action,
                        "quantity": abs(change_qty),
                        "today_qty": today_qty,
                        "yesterday_qty": yesterday_qty,
                    })

            return changes

        except Exception as e:
            log.warning(f"[ReviewDataCollector] _get_trade_changes 失败: {e}")
            return []

    def _get_knowledge_changes(self) -> List[Dict]:
        """获取知识学习变化"""
        try:
            from deva.naja.knowledge.state_manager import KnowledgeStateManager, get_state_manager
            from deva.naja.knowledge.knowledge_store import get_knowledge_store

            store = get_knowledge_store()
            ksm = get_state_manager()
            all_knowledge = store.get_all()

            yesterday_knowledge = self._get_yesterday_state("knowledge") or []

            yesterday_ids = {k.entry_id if hasattr(k, 'entry_id') else str(k) for k in yesterday_knowledge}
            today_ids = {k.entry_id if hasattr(k, 'entry_id') else str(k) for k in all_knowledge}

            new_ids = today_ids - yesterday_ids
            promoted_ids = yesterday_ids - today_ids

            new_knowledge = [k for k in all_knowledge if (hasattr(k, 'entry_id') and k.entry_id in new_ids)]

            promoted_knowledge = []
            for k in yesterday_knowledge:
                k_id = k.entry_id if hasattr(k, 'entry_id') else str(k)
                if k_id in promoted_ids:
                    status = k.status if hasattr(k, 'status') else ""
                    if status == "validating":
                        promoted_knowledge.append({
                            "id": k_id,
                            "knowledge": k.cause if hasattr(k, 'cause') else str(k),
                            "from_state": "validating",
                            "to_state": "qualified",
                        })

            changes = []
            if new_knowledge:
                changes.append({
                    "type": "new",
                    "items": [{"cause": k.cause if hasattr(k, 'cause') else ""} for k in new_knowledge[:3]],
                })
            if promoted_knowledge:
                changes.append({
                    "type": "promoted",
                    "items": promoted_knowledge[:3],
                })

            self._save_today_state("knowledge", [{"entry_id": k.entry_id if hasattr(k, 'entry_id') else str(k), "status": k.status, "cause": k.cause if hasattr(k, 'cause') else ""} for k in all_knowledge])

            return changes

        except Exception as e:
            log.warning(f"[ReviewDataCollector] _get_knowledge_changes 失败: {e}")
            return []

    def _get_pain_point_changes(self) -> List[Dict]:
        """获取痛点挖掘变化"""
        try:
            from deva.naja.knowledge.knowledge_store import get_knowledge_store

            store = get_knowledge_store()
            all_knowledge = store.get_all()

            pain_points = [k for k in all_knowledge if "pain" in (k.cause + k.effect).lower()]

            yesterday_pain_points = self._get_yesterday_state("pain_points") or []
            yesterday_ids = {k.get("id", k.get("entry_id")) for k in yesterday_pain_points}

            new_pain_points = [
                {"id": k.id, "cause": k.cause, "effect": k.effect}
                for k in pain_points
                if k.id not in yesterday_ids
            ]

            self._save_today_state("pain_points", [{"id": k.id, "cause": k.cause, "effect": k.effect} for k in pain_points])

            return new_pain_points[:3] if new_pain_points else []

        except Exception as e:
            log.warning(f"[ReviewDataCollector] _get_pain_point_changes 失败: {e}")
            return []

    def _get_yesterday_state(self, key: str) -> Optional[Any]:
        """获取昨天的状态"""
        try:
            yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
            key_with_date = f"{key}_{yesterday}"
            return self._nb.get(key_with_date)
        except Exception:
            return None

    def _save_today_state(self, key: str, data: Any):
        """保存今天的状态"""
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            key_with_date = f"{key}_{today}"
            self._nb[key_with_date] = data
        except Exception as e:
            log.warning(f"[ReviewDataCollector] _save_today_state 失败: {e}")

    def _save_internal_changes(self, changes: Dict):
        """保存内部变化"""
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            self._nb[f"internal_changes_{today}"] = {
                "timestamp": datetime.now().isoformat(),
                **changes,
            }
        except Exception as e:
            log.warning(f"[ReviewDataCollector] _save_internal_changes 失败: {e}")


def get_review_data_collector() -> ReviewDataCollector:
    """获取复盘数据收集器单例"""
    global _collector_instance
    if _collector_instance is None:
        _collector_instance = ReviewDataCollector()
    return _collector_instance


_collector_instance = None