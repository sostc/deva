"""流动性分析器"""

import time
from typing import Dict, List, Any
import logging

log = logging.getLogger(__name__)


class LiquidityAnalyzer:
    """流动性分析器，提供流动性风险评估"""
    
    def __init__(self):
        """初始化流动性分析器"""
        self._last_update = 0.0
        self._update_interval = 60.0  # 60秒更新一次
        self._liquidity_state = {
            "liquidity_risk": 0.5,
            "market_liquidity": 0.5,
            "block_liquidity": {},
            "timestamp": time.time()
        }
        self._propagation_engine = None
    
    def get_state(self) -> Dict[str, Any]:
        """获取流动性状态
        
        Returns:
            Dict[str, Any]: 流动性状态信息
        """
        current_time = time.time()
        if current_time - self._last_update > self._update_interval:
            self._update_liquidity_state()
        return self._liquidity_state
    
    def _update_liquidity_state(self):
        """更新流动性状态"""
        try:
            # 初始化传播引擎
            if self._propagation_engine is None:
                from .propagation import PropagationEngine
                self._propagation_engine = PropagationEngine()
                self._propagation_engine.initialize()
            
            # 获取流动性结构
            liquidity_structure = self._propagation_engine.get_liquidity_structure()
            
            # 计算流动性风险
            market_liquidity = self._calculate_market_liquidity(liquidity_structure)
            liquidity_risk = 1.0 - market_liquidity
            
            # 计算板块流动性
            block_liquidity = self._calculate_block_liquidity(liquidity_structure)
            
            # 更新状态
            self._liquidity_state = {
                "liquidity_risk": liquidity_risk,
                "market_liquidity": market_liquidity,
                "block_liquidity": block_liquidity,
                "timestamp": time.time()
            }
            
            self._last_update = time.time()
        except Exception as e:
            log.warning(f"[LiquidityAnalyzer] 更新流动性状态失败: {e}")
    
    def _calculate_market_liquidity(self, liquidity_structure: Dict[str, Any]) -> float:
        """计算市场整体流动性
        
        Args:
            liquidity_structure: 流动性结构
            
        Returns:
            float: 市场流动性评分 (0-1)
        """
        try:
            # 从流动性结构中提取市场流动性指标
            # 这里使用简化的计算方法，实际应用中可以根据具体数据结构进行调整
            total_liquidity = 0.0
            count = 0
            
            if "markets" in liquidity_structure:
                for market in liquidity_structure["markets"]:
                    if "liquidity_score" in market:
                        total_liquidity += market["liquidity_score"]
                        count += 1
            
            if count > 0:
                return min(1.0, max(0.0, total_liquidity / count))
            else:
                return 0.5
        except Exception as e:
            log.warning(f"[LiquidityAnalyzer] 计算市场流动性失败: {e}")
            return 0.5
    
    def _calculate_block_liquidity(self, liquidity_structure: Dict[str, Any]) -> Dict[str, float]:
        """计算板块流动性
        
        Args:
            liquidity_structure: 流动性结构
            
        Returns:
            Dict[str, float]: 板块流动性评分
        """
        try:
            block_liquidity = {}
            
            if "blocks" in liquidity_structure:
                for block in liquidity_structure["blocks"]:
                    if "name" in block and "liquidity_score" in block:
                        block_liquidity[block["name"]] = block["liquidity_score"]
            
            return block_liquidity
        except Exception as e:
            log.warning(f"[LiquidityAnalyzer] 计算板块流动性失败: {e}")
            return {}
    
    def update_market(self, market_id: str, price: float, volume: float = 0, narrative_score: float = 0.0):
        """更新市场状态
        
        Args:
            market_id: 市场ID
            price: 价格
            volume: 成交量
            narrative_score: 叙事评分
        """
        try:
            if self._propagation_engine is None:
                from .propagation import PropagationEngine
                self._propagation_engine = PropagationEngine()
                self._propagation_engine.initialize()
            
            self._propagation_engine.update_market(
                market_id=market_id,
                price=price,
                volume=volume,
                narrative_score=narrative_score
            )
            
            # 强制更新流动性状态
            self._update_liquidity_state()
        except Exception as e:
            log.warning(f"[LiquidityAnalyzer] 更新市场状态失败: {e}")
    
    def update_narrative(self, narrative: str, attention_score: float):
        """更新叙事状态
        
        Args:
            narrative: 叙事
            attention_score: 注意力评分
        """
        try:
            if self._propagation_engine is None:
                from .propagation import PropagationEngine
                self._propagation_engine = PropagationEngine()
                self._propagation_engine.initialize()
            
            self._propagation_engine.update_narrative_state(narrative, attention_score)
            
            # 强制更新流动性状态
            self._update_liquidity_state()
        except Exception as e:
            log.warning(f"[LiquidityAnalyzer] 更新叙事状态失败: {e}")
