"""Naja market copilot service.

Application-layer service that gathers existing market, cognition, knowledge,
and strategy state into a digest suitable for the awakening page, API answers,
and optional notifications.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class StrategyAdjustmentProposal:
    target: str
    suggestion: str
    reason: str
    confidence: float = 0.5
    status: str = "observing"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MarketCopilotDigest:
    timestamp: float
    datetime: str
    tianshi: str
    dili: str
    renhe: str
    summary: str
    narratives: List[Dict[str, Any]] = field(default_factory=list)
    hot_blocks: List[Dict[str, Any]] = field(default_factory=list)
    hot_symbols: List[Dict[str, Any]] = field(default_factory=list)
    knowledge_stats: Dict[str, Any] = field(default_factory=dict)
    strategy_proposals: List[StrategyAdjustmentProposal] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["strategy_proposals"] = [p.to_dict() for p in self.strategy_proposals]
        return data


class MarketCopilot:
    """Coordinates digest, natural-language answers, and notifications."""

    def __init__(self):
        self._last_digest: Optional[MarketCopilotDigest] = None

    def build_digest(self) -> MarketCopilotDigest:
        warnings: List[str] = []
        hotspot = self._safe_market_hotspot()
        narratives = self._safe_narratives(warnings)
        knowledge_stats = self._safe_knowledge_stats(warnings)

        hot_blocks = self._top_items(hotspot, "hot_blocks")
        hot_symbols = self._top_items(hotspot, "hot_stocks")
        market_state = hotspot.get("market_state", {}) if isinstance(hotspot, dict) else {}

        tianshi = self._describe_tianshi(hotspot, narratives, market_state)
        dili = self._describe_dili(hot_blocks, hot_symbols)
        renhe = self._describe_renhe(narratives, knowledge_stats)
        proposals = self._build_strategy_proposals(hot_blocks, narratives, knowledge_stats)
        summary = self._compose_summary(tianshi, dili, renhe, proposals)

        digest = MarketCopilotDigest(
            timestamp=time.time(),
            datetime=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            tianshi=tianshi,
            dili=dili,
            renhe=renhe,
            summary=summary,
            narratives=narratives[:8],
            hot_blocks=hot_blocks[:8],
            hot_symbols=hot_symbols[:8],
            knowledge_stats=knowledge_stats,
            strategy_proposals=proposals,
            warnings=warnings,
        )
        self._last_digest = digest
        return digest

    def answer(self, question: str) -> Dict[str, Any]:
        question = (question or "").strip()
        digest = self.build_digest()
        q_lower = question.lower()

        if any(word in q_lower for word in ["策略", "strategy", "调参", "买", "卖"]):
            focus = "策略层面：先用观察/验证池承接新叙事，不直接改实盘规则。"
            details = [p.to_dict() for p in digest.strategy_proposals]
        elif any(word in q_lower for word in ["新闻", "叙事", "热点", "narrative"]):
            focus = "叙事层面：重点看外部新闻热度和市场热点是否同向。"
            details = digest.narratives or digest.hot_blocks
        elif any(word in q_lower for word in ["天时", "地利", "人和"]):
            focus = "三才判断：天时看节奏，地利看落点，人和看拥挤和信心。"
            details = {"天时": digest.tianshi, "地利": digest.dili, "人和": digest.renhe}
        else:
            focus = "综合判断：先看市场温度，再看叙事落到哪些板块，最后看策略是否需要进入验证。"
            details = {
                "天时": digest.tianshi,
                "地利": digest.dili,
                "人和": digest.renhe,
                "策略建议": [p.to_dict() for p in digest.strategy_proposals],
            }

        answer = f"{focus}\n\n{digest.summary}"
        if question:
            answer = f"你问：{question}\n\n{answer}"

        return {
            "question": question,
            "answer": answer,
            "digest": digest.to_dict(),
            "details": details,
        }

    def send_digest(self, channels: Optional[List[str]] = None, force: bool = False) -> Dict[str, Any]:
        digest = self.build_digest()
        from deva.naja.infra.notification import get_multi_channel_notifier

        title = "Naja 市场学习汇报"
        message = self.format_digest_markdown(digest)
        return get_multi_channel_notifier().send(title, message, channels=channels, force=force)

    def format_digest_markdown(self, digest: Optional[MarketCopilotDigest] = None) -> str:
        digest = digest or self.build_digest()
        proposals = "\n".join(
            f"- {p.target}: {p.suggestion} ({p.reason})" for p in digest.strategy_proposals
        ) or "- 暂无策略调整建议"
        narratives = "\n".join(
            f"- {n.get('narrative') or n.get('name')}: {n.get('stage', '')} {n.get('attention_score', '')}"
            for n in digest.narratives[:5]
        ) or "- 暂无叙事数据"
        return (
            f"## Naja 市场学习汇报\n\n"
            f"时间: {digest.datetime}\n\n"
            f"### 天时\n{digest.tianshi}\n\n"
            f"### 地利\n{digest.dili}\n\n"
            f"### 人和\n{digest.renhe}\n\n"
            f"### 叙事\n{narratives}\n\n"
            f"### 策略影响\n{proposals}"
        )

    def _safe_market_hotspot(self) -> Dict[str, Any]:
        try:
            from deva.naja.market_hotspot.integration import get_market_hotspot_integration

            integration = get_market_hotspot_integration()
            if not integration or not getattr(integration, "hotspot_system", None):
                return {}

            hotspot = integration.hotspot_system
            report = integration.get_hotspot_report() or {}
            cn_blocks = self._collect_weights(
                getattr(getattr(hotspot, "_cn_context", None), "block_engine", None),
                "block",
                "CN",
            )
            cn_stocks = self._collect_weights(
                getattr(getattr(hotspot, "_cn_context", None), "weight_pool", None),
                "symbol",
                "CN",
            )
            us_state = {}
            try:
                us_state = hotspot.get_us_hotspot_state() or {}
            except Exception:
                us_state = {}
            us_blocks = [
                {"block_id": str(k), "name": str(k), "weight": self._to_float(v)}
                for k, v in sorted((us_state.get("block_hotspot") or {}).items(), key=lambda item: item[1], reverse=True)[:10]
            ]
            us_stocks = [
                {"symbol": str(k), "name": str(k), "weight": self._to_float(v)}
                for k, v in sorted((us_state.get("symbol_weights") or {}).items(), key=lambda item: item[1], reverse=True)[:20]
            ]
            return {
                "cn": {
                    "hot_blocks": cn_blocks,
                    "hot_stocks": cn_stocks,
                    "market_hotspot": self._to_float(report.get("cn_global", report.get("global_hotspot", 0))),
                    "market_activity": self._to_float(report.get("activity", 0)),
                },
                "us": {
                    "hot_blocks": us_blocks,
                    "hot_stocks": us_stocks,
                    "market_hotspot": self._to_float(us_state.get("global_hotspot", 0)),
                    "market_activity": self._to_float(us_state.get("activity", 0)),
                },
                "market_state": {"description": report.get("hotspot_level", "等待数据...")},
            }
        except Exception:
            return {}

    def _collect_weights(self, source: Any, item_type: str, market: str) -> List[Dict[str, Any]]:
        if source is None or not hasattr(source, "get_all_weights"):
            return []
        try:
            weights = source.get_all_weights(filter_noise=True)
        except TypeError:
            weights = source.get_all_weights()
        except Exception:
            return []
        result: List[Dict[str, Any]] = []
        for key, value in sorted((weights or {}).items(), key=lambda item: item[1], reverse=True)[:20]:
            item_id = str(key)
            item = {"name": item_id, "weight": self._to_float(value)}
            if item_type == "block":
                item["block_id"] = item_id
            else:
                item["symbol"] = item_id
                item["name"] = self._symbol_name(item_id)
            result.append(item)
        return result

    def _symbol_name(self, symbol: str) -> str:
        try:
            from deva.naja.dictionary.blocks import get_stock_name

            return get_stock_name(symbol)
        except Exception:
            return symbol

    def _safe_narratives(self, warnings: List[str]) -> List[Dict[str, Any]]:
        try:
            from deva.naja.cognition.narrative import get_narrative_tracker

            tracker = get_narrative_tracker()
            if tracker and hasattr(tracker, "get_summary"):
                return tracker.get_summary(limit=12)
        except Exception as exc:
            warnings.append(f"叙事读取失败: {exc}")
        return []

    def _safe_knowledge_stats(self, warnings: List[str]) -> Dict[str, Any]:
        try:
            from deva.naja.knowledge import get_knowledge_store

            return get_knowledge_store().get_stats()
        except Exception as exc:
            warnings.append(f"知识库读取失败: {exc}")
            return {}

    def _top_items(self, hotspot: Dict[str, Any], key: str) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        for market in ("cn", "us"):
            market_data = hotspot.get(market, {}) if isinstance(hotspot, dict) else {}
            for item in market_data.get(key, []) or []:
                copied = dict(item)
                copied["market"] = market.upper()
                items.append(copied)
        return sorted(items, key=lambda x: float(x.get("weight", 0) or 0), reverse=True)

    def _describe_tianshi(
        self,
        hotspot: Dict[str, Any],
        narratives: List[Dict[str, Any]],
        market_state: Dict[str, Any],
    ) -> str:
        state_desc = market_state.get("description") or market_state.get("state") or "等待更多实时数据"
        cn_hot = self._to_float(((hotspot.get("cn") or {}).get("market_hotspot") or 0) if hotspot else 0)
        us_hot = self._to_float(((hotspot.get("us") or {}).get("market_hotspot") or 0) if hotspot else 0)
        active = len([n for n in narratives if (n.get("attention_score") or 0) >= 0.3])
        temp = "升温" if max(cn_hot, us_hot) >= 0.45 or active >= 3 else "观察"
        return f"市场温度{temp}；CN热点 {cn_hot:.2f}，US热点 {us_hot:.2f}；状态：{state_desc}。"

    def _to_float(self, value: Any) -> float:
        try:
            return float(value)
        except Exception:
            return 0.0

    def _describe_dili(self, hot_blocks: List[Dict[str, Any]], hot_symbols: List[Dict[str, Any]]) -> str:
        blocks = "、".join(str(x.get("name") or x.get("block_id")) for x in hot_blocks[:5]) or "暂无集中板块"
        symbols = "、".join(str(x.get("name") or x.get("symbol")) for x in hot_symbols[:5]) or "暂无集中个股"
        return f"板块落点：{blocks}；个股落点：{symbols}。"

    def _describe_renhe(self, narratives: List[Dict[str, Any]], knowledge_stats: Dict[str, Any]) -> str:
        qualified = knowledge_stats.get("qualified_count", 0)
        validating = (knowledge_stats.get("by_state") or {}).get("validating", 0)
        top = narratives[0].get("narrative") if narratives else None
        top = top or narratives[0].get("name") if narratives else None
        top = top or "暂无主导叙事"
        return f"主导叙事：{top}；正式知识 {qualified} 条，验证中 {validating} 条。"

    def _build_strategy_proposals(
        self,
        hot_blocks: List[Dict[str, Any]],
        narratives: List[Dict[str, Any]],
        knowledge_stats: Dict[str, Any],
    ) -> List[StrategyAdjustmentProposal]:
        proposals: List[StrategyAdjustmentProposal] = []
        for item in hot_blocks[:3]:
            weight = float(item.get("weight", 0) or 0)
            if weight >= 0.3:
                name = str(item.get("name") or item.get("block_id"))
                proposals.append(StrategyAdjustmentProposal(
                    target=name,
                    suggestion="提高观察权重，进入策略验证池",
                    reason=f"热点权重 {weight:.2f}，需要验证是否有持续性",
                    confidence=min(0.8, 0.4 + weight),
                ))
        for narrative in narratives[:2]:
            score = float(narrative.get("attention_score", 0) or 0)
            if score >= 0.35:
                name = str(narrative.get("narrative") or narrative.get("name"))
                proposals.append(StrategyAdjustmentProposal(
                    target=name,
                    suggestion="绑定相关板块和新闻过滤词",
                    reason=f"叙事关注度 {score:.2f}，适合增强雷达监听",
                    confidence=min(0.85, 0.45 + score),
                ))
        if not proposals and knowledge_stats.get("total", 0):
            proposals.append(StrategyAdjustmentProposal(
                target="知识验证池",
                suggestion="保持现有策略，等待更多证据",
                reason="当前热点或叙事强度不足，不宜主动调参",
                confidence=0.55,
            ))
        return proposals[:5]

    def _compose_summary(
        self,
        tianshi: str,
        dili: str,
        renhe: str,
        proposals: List[StrategyAdjustmentProposal],
    ) -> str:
        if proposals:
            action = "建议把强热点先放入验证池，由数据确认后再影响策略权重。"
        else:
            action = "当前更适合继续观察，避免为了叙事噪音频繁调参。"
        return f"天时：{tianshi}\n地利：{dili}\n人和：{renhe}\n判断：{action}"


_copilot: Optional[MarketCopilot] = None


def get_market_copilot() -> MarketCopilot:
    global _copilot
    if _copilot is None:
        _copilot = MarketCopilot()
    return _copilot
