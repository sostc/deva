"""全球流动性传播引擎"""

import time
from typing import Dict, List, Any
import logging

log = logging.getLogger(__name__)


class PropagationEngine:
    """全球流动性传播引擎"""
    
    def __init__(self):
        """初始化传播引擎"""
        self._markets = {}
        self._narratives = {}
        self._sectors = {}
        self._initialized = False
    
    def initialize(self):
        """初始化传播引擎"""
        try:
            # 初始化市场数据
            self._initialize_markets()
            # 初始化行业数据
            self._initialize_sectors()
            self._initialized = True
            log.info("[PropagationEngine] 初始化完成")
        except Exception as e:
            log.warning(f"[PropagationEngine] 初始化失败: {e}")
    
    def _initialize_markets(self):
        """初始化市场数据"""
        # 这里可以从数据源加载市场数据
        # 现在使用默认数据
        default_markets = [
            {"id": "china_a", "name": "中国A股", "liquidity_score": 0.7},
            {"id": "us_stocks", "name": "美国股市", "liquidity_score": 0.9},
            {"id": "hk_stocks", "name": "香港股市", "liquidity_score": 0.8},
            {"id": "crypto", "name": "加密货币", "liquidity_score": 0.6},
        ]
        
        for market in default_markets:
            self._markets[market["id"]] = market
    
    def _initialize_sectors(self):
        """初始化行业数据"""
        # 这里可以从数据源加载行业数据
        # 现在使用默认数据
        default_sectors = [
            {"id": "tech", "name": "科技", "liquidity_score": 0.8},
            {"id": "finance", "name": "金融", "liquidity_score": 0.7},
            {"id": "healthcare", "name": "医疗", "liquidity_score": 0.6},
            {"id": "energy", "name": "能源", "liquidity_score": 0.5},
            {"id": "consumer", "name": "消费", "liquidity_score": 0.7},
        ]
        
        for sector in default_sectors:
            self._sectors[sector["id"]] = sector
    
    def update_market(self, market_id: str, price: float, volume: float = 0, narrative_score: float = 0.0):
        """更新市场状态
        
        Args:
            market_id: 市场ID
            price: 价格
            volume: 成交量
            narrative_score: 叙事评分
        """
        try:
            if market_id not in self._markets:
                self._markets[market_id] = {
                    "id": market_id,
                    "name": market_id,
                    "liquidity_score": 0.5,
                    "price": price,
                    "volume": volume,
                    "narrative_score": narrative_score,
                    "last_update": time.time()
                }
            else:
                market = self._markets[market_id]
                market["price"] = price
                market["volume"] = volume
                market["narrative_score"] = narrative_score
                market["last_update"] = time.time()
                
                # 根据成交量和价格变化更新流动性评分
                # 这里使用简化的计算方法
                liquidity_score = min(1.0, max(0.1, 0.5 + narrative_score * 0.3))
                market["liquidity_score"] = liquidity_score
        except Exception as e:
            log.warning(f"[PropagationEngine] 更新市场状态失败: {e}")
    
    def update_narrative_state(self, narrative: str, attention_score: float):
        """更新叙事状态
        
        Args:
            narrative: 叙事
            attention_score: 注意力评分
        """
        try:
            if narrative not in self._narratives:
                self._narratives[narrative] = {
                    "name": narrative,
                    "attention_score": attention_score,
                    "last_update": time.time()
                }
            else:
                self._narratives[narrative]["attention_score"] = attention_score
                self._narratives[narrative]["last_update"] = time.time()
            
            # 叙事注意力变化会影响市场流动性
            self._propagate_narrative_impact(narrative, attention_score)
        except Exception as e:
            log.warning(f"[PropagationEngine] 更新叙事状态失败: {e}")
    
    def _propagate_narrative_impact(self, narrative: str, attention_score: float):
        """传播叙事影响到市场
        
        Args:
            narrative: 叙事
            attention_score: 注意力评分
        """
        try:
            # 简化的传播模型
            # 叙事注意力会影响相关市场的流动性
            for market_id, market in self._markets.items():
                # 这里使用简化的相关性计算
                # 实际应用中可以根据叙事与市场的相关性进行调整
                correlation = 0.3  # 默认相关性
                impact = attention_score * correlation
                market["liquidity_score"] = min(1.0, max(0.1, market["liquidity_score"] + impact * 0.1))
        except Exception as e:
            log.warning(f"[PropagationEngine] 传播叙事影响失败: {e}")
    
    def get_liquidity_structure(self) -> Dict[str, Any]:
        """获取流动性结构
        
        Returns:
            Dict[str, Any]: 流动性结构
        """
        try:
            return {
                "markets": list(self._markets.values()),
                "sectors": list(self._sectors.values()),
                "narratives": list(self._narratives.values()),
                "timestamp": time.time()
            }
        except Exception as e:
            log.warning(f"[PropagationEngine] 获取流动性结构失败: {e}")
            return {
                "markets": [],
                "sectors": [],
                "narratives": [],
                "timestamp": time.time()
            }
    
    def decay_all_attention(self):
        """衰减所有注意力"""
        try:
            current_time = time.time()
            for narrative, data in self._narratives.items():
                # 注意力随时间衰减
                time_diff = current_time - data["last_update"]
                decay_factor = max(0.1, 1.0 - time_diff / 3600.0 * 0.1)  # 每小时衰减10%
                data["attention_score"] *= decay_factor
                if data["attention_score"] < 0.1:
                    del self._narratives[narrative]
        except Exception as e:
            log.warning(f"[PropagationEngine] 衰减注意力失败: {e}")
