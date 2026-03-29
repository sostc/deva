"""PropagationEngine - 流动性传播引擎

核心功能：
1. 管理所有市场节点 (MarketNode)
2. 管理所有影响边 (InfluenceEdge)
3. 执行传播逻辑
4. 验证传播结果
5. 动态调整边权重
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import time
import logging

from .global_market_config import (
    MARKET_CONFIGS,
    MARKET_TRADING_ORDER,
    INFLUENCE_PATHS,
    get_market_config,
    get_next_markets,
)
from .market_node import MarketNode, MarketState
from .influence_edge import InfluenceEdge, PropagationEvent

log = logging.getLogger(__name__)

MARKET_ID_MAP = {
    "nasdaq100": "nasdaq",
    "sp500": "sp500",
    "dowjones": "dow_jones",
    "gold": "gold",
    "silver": "silver",
    "crude_oil": "crude_oil",
    "natural_gas": "natural_gas",
    "nvda": "us_equity",
    "aapl": "us_equity",
    "tsla": "us_equity",
    "msft": "us_equity",
    "googl": "us_equity",
    "amzn": "us_equity",
    "meta": "us_equity",
}


@dataclass
class PropagationSignal:
    """传播信号"""
    from_market: str
    to_market: str
    timestamp: float
    change: float
    propagation_probability: float
    status: str

    narrative_triggered: Optional[str] = None


class PropagationEngine:
    """流动性传播引擎

    管理全球市场的传播网络：
    - 节点：各个市场
    - 边：市场间的影响关系
    """

    def __init__(self):
        self._nodes: Dict[str, MarketNode] = {}
        self._edges: Dict[str, InfluenceEdge] = {}

        self._propagation_history: List[PropagationSignal] = []
        self._max_history = 500

        self._narrative_states: Dict[str, float] = {}

        self._initialized = False

    def initialize(self):
        """初始化引擎，创建所有节点和边"""
        for market_id, config in MARKET_CONFIGS.items():
            self._nodes[market_id] = MarketNode(
                market_id=market_id,
                name=config.name,
                market_type=config.market_type,
            )

        for path in INFLUENCE_PATHS:
            edge_key = f"{path['from']}->{path['to']}"
            self._edges[edge_key] = InfluenceEdge(
                from_market=path["from"],
                to_market=path["to"],
                base_strength=path.get("strength", 0.7),
                delay_hours=path.get("delay_hours", 0),
            )

        self._initialized = True
        log.info(f"[PropagationEngine] 初始化完成: {len(self._nodes)} 个节点, {len(self._edges)} 条边")

    def update_market(
        self,
        market_id: str,
        price: float,
        volume: float = 0,
        timestamp: float = None,
        narrative_score: float = 0.0,
    ) -> Optional[MarketState]:
        """更新市场状态并触发传播"""
        if not self._initialized:
            self.initialize()

        if timestamp is None:
            timestamp = time.time()

        node = self._nodes.get(market_id)
        if not node:
            config = get_market_config(market_id)
            if config:
                node = MarketNode(
                    market_id=market_id,
                    name=config.name,
                    market_type=config.market_type,
                )
                self._nodes[market_id] = node

        if narrative_score > 0:
            node.update_narrative_score(narrative_score)

        state = node.update(price, volume, timestamp, narrative_score)

        if state and node._change_count > 0:
            self._propagate_change(market_id, state, timestamp)

        return state

    def _propagate_change(
        self,
        from_market: str,
        state: MarketState,
        timestamp: float,
    ):
        """将市场变化传播到相关市场"""
        paths = get_next_markets(from_market)

        for path in paths:
            to_market = path["to"]
            edge_key = f"{from_market}->{to_market}"

            edge = self._edges.get(edge_key)
            if not edge:
                continue

            probability = edge.propagate(
                source_change=state.price_change,
                timestamp=timestamp,
            )

            signal = PropagationSignal(
                from_market=from_market,
                to_market=to_market,
                timestamp=timestamp,
                change=state.price_change,
                propagation_probability=probability.predicted_strength,
                status="propagated",
            )
            self._add_to_history(signal)
            self._emit_liquidity_insight(signal, state)

    def _emit_liquidity_insight(self, signal: PropagationSignal, state: MarketState) -> None:
        """发送流动性传播信号到洞察池"""
        try:
            from deva.naja.cognition.insight import emit_to_insight_pool

            insight_data = {
                "source": "liquidity_propagation",
                "signal_type": "liquidity_propagation",
                "from_market": signal.from_market,
                "to_market": signal.to_market,
                "change": signal.change,
                "propagation_probability": signal.propagation_probability,
                "status": signal.status,
                "narrative_triggered": signal.narrative_triggered,
                "score": signal.propagation_probability,
                "message": f"{signal.from_market} → {signal.to_market}: {signal.status}",
                "timestamp": signal.timestamp,
            }
            emit_to_insight_pool(insight_data)
        except ImportError:
            pass
        except Exception:
            pass

    def verify_propagation(
        self,
        to_market: str,
        actual_change: float,
        timestamp: float = None,
    ) -> Optional[PropagationEvent]:
        """验证传播是否成功"""
        if timestamp is None:
            timestamp = time.time()

        target_node = self._nodes.get(to_market)
        if not target_node:
            return None

        best_edge = None
        best_event = None

        for edge_key, edge in self._edges.items():
            if edge.to_market != to_market:
                continue

            pending = edge.get_pending_events()
            if pending:
                event = edge.verify(actual_change, timestamp)
                if event:
                    best_edge = edge
                    best_event = event

                    signal = PropagationSignal(
                        from_market=event.from_market,
                        to_market=to_market,
                        timestamp=event.verification_timestamp,
                        change=actual_change,
                        propagation_probability=edge.get_propagation_probability(),
                        status="verified" if event.verified else "failed",
                    )
                    self._add_to_history(signal)

                    break

        return best_event

    def update_narrative_state(
        self,
        narrative: str,
        attention_score: float,
        timestamp: float = None,
    ):
        """更新叙事状态（来自 NarrativeTracker）"""
        if timestamp is None:
            timestamp = time.time()

        self._narrative_states[narrative] = attention_score

        for market_id, node in self._nodes.items():
            config = get_market_config(market_id)
            if config and narrative in config.related_narratives:
                node.update_narrative_score(attention_score)

    def get_market_attention(self, market_id: str) -> float:
        """获取市场的注意力分数"""
        node = self._nodes.get(market_id)
        if node:
            return node.get_attention_level()
        return "unknown"

    def get_active_markets(self, threshold: float = 0.3) -> List[str]:
        """获取活跃的市场列表"""
        active = []
        for market_id, node in self._nodes.items():
            if node.is_active(threshold):
                active.append(market_id)
        return active

    def get_propagation_chains(self, from_market: str) -> List[List[str]]:
        """获取从某个市场出发的传播链"""
        chains = []
        visited = set()
        current_chain = [from_market]

        def dfs(market: str, chain: List[str]):
            visited.add(market)
            next_markets = get_next_markets(market)
            if not next_markets:
                chains.append(chain.copy())
            else:
                for next_m in next_markets:
                    if next_m not in visited:
                        dfs(next_m, chain + [next_m])

        dfs(from_market, current_chain)
        return chains

    def decay_all_attention(self, rate: float = 0.95):
        """衰减所有市场的注意力分数"""
        for node in self._nodes.values():
            node.decay_attention(rate)

        for edge in self._edges.values():
            edge.natural_decay(rate)

    def get_liquidity_structure(self) -> Dict[str, Any]:
        """获取当前流动性结构"""
        markets = {}
        for market_id, node in self._nodes.items():
            info = node.get_info()
            markets[market_id] = {
                "name": info["name"],
                "attention_level": info["attention_level"],
                "attention_score": info["attention_score"],
                "change_count": info["change_count"],
                "is_active": info["is_active"],
            }

        edges = {}
        for edge_key, edge in self._edges.items():
            info = edge.get_info()
            if info["total_propagations"] > 0:
                edges[edge_key] = info

        return {
            "timestamp": time.time(),
            "markets": markets,
            "edges": edges,
            "narrative_states": self._narrative_states.copy(),
            "active_markets": self.get_active_markets(),
        }

    def get_resonance_signals(self) -> List[Dict[str, Any]]:
        """获取共振信号"""
        signals = []

        for market_id, node in self._nodes.items():
            if node.is_active(0.5):
                state = node.get_state()
                if state:
                    signals.append({
                        "market_id": market_id,
                        "name": node.name,
                        "change": state.price_change,
                        "volatility": state.volatility,
                        "attention_score": state.attention_score,
                        "narrative_match": state.narrative_match_score,
                        "propagation_targets": [p["to"] for p in get_next_markets(market_id)],
                    })

        return signals

    def _add_to_history(self, signal: PropagationSignal):
        """添加传播信号到历史"""
        self._propagation_history.append(signal)
        if len(self._propagation_history) > self._max_history:
            self._propagation_history.pop(0)

    def get_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取传播历史"""
        return [
            {
                "from": s.from_market,
                "to": s.to_market,
                "timestamp": s.timestamp,
                "change": s.change,
                "probability": s.propagation_probability,
                "status": s.status,
            }
            for s in self._propagation_history[-limit:]
        ]

    def get_info(self) -> Dict[str, Any]:
        """获取引擎信息"""
        return {
            "initialized": self._initialized,
            "nodes_count": len(self._nodes),
            "edges_count": len(self._edges),
            "active_markets": len(self.get_active_markets()),
            "history_size": len(self._propagation_history),
            "narrative_states": list(self._narrative_states.keys()),
        }

    def sync_from_global_market_api(self, market_data: Dict[str, Any]) -> int:
        """
        从 GlobalMarketAPI 同步市场数据

        Args:
            market_data: GlobalMarketAPI.fetch_all() 返回的 Dict[str, MarketData]

        Returns:
            更新了多少个市场节点
        """
        count = 0
        for code, md in market_data.items():
            market_id = MARKET_ID_MAP.get(md.market_id, md.market_id)

            if market_id in self._nodes:
                price = md.current
                volume = md.volume if hasattr(md, 'volume') else 0
                self.update_market(market_id, price, volume)
                count += 1
            else:
                log.debug(f"[PropagationEngine] 忽略未知市场: {market_id} (code: {code})")

        if count > 0:
            log.info(f"[PropagationEngine] 从 GlobalMarketAPI 同步了 {count} 个市场")

        return count

    async def fetch_and_sync_from_global_market_api(self) -> int:
        """
        直接从 GlobalMarketAPI 获取并同步数据

        Returns:
            更新了多少个市场节点
        """
        try:
            from deva.naja.attention.data.global_market_futures import GlobalMarketAPI

            api = GlobalMarketAPI()
            data = await api.fetch_all()
            return self.sync_from_global_market_api(data)
        except Exception as e:
            log.error(f"[PropagationEngine] 从 GlobalMarketAPI 获取数据失败: {e}")
            return 0
