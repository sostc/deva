"""
聪明资金流向检测策略

检测机构资金、大单资金的流向，识别"聪明钱"的操作
"""

import time
import numpy as np
from typing import Dict, List, Optional, Any
from collections import deque

from .base import HotspotStrategyBase, Signal


class SmartMoneyFlowDetector(HotspotStrategyBase):
    """
    聪明资金流向检测策略
    
    核心逻辑：
    1. 分析大单 vs 小单的流向差异
    2. 检测主动买入 vs 主动卖出的不平衡
    3. 识别机构资金的建仓/出货行为
    4. 结合注意力权重，优先分析高关注股票的资金流向
    
    只在市场活跃时段（高注意力）执行深度分析
    """
    
    def __init__(
        self,
        large_order_threshold: float = 1000000,  # 大单阈值（金额）
        smart_money_imbalance_threshold: float = 0.6,  # 资金流向不平衡阈值
        accumulation_threshold: float = 0.7,     # 建仓信号阈值
        distribution_threshold: float = -0.7,    # 出货信号阈值
        min_symbol_weight: float = 2.5,          # 最低个股权重
        cooldown_period: float = 240.0           # 4分钟冷却期
    ):
        super().__init__(
            strategy_id="smart_money_flow_detector",
            name="Smart Money Flow Detector",
            scope='symbol',
            min_global_hotspot=0.35,
            min_symbol_weight=min_symbol_weight,
            max_positions=15,
            cooldown_period=cooldown_period
        )
        
        self.large_order_threshold = large_order_threshold
        self.smart_money_imbalance_threshold = smart_money_imbalance_threshold
        self.accumulation_threshold = accumulation_threshold
        self.distribution_threshold = distribution_threshold
        
        # 资金流向历史
        self.money_flow_history: Dict[str, deque] = {}
        self.imbalance_history: Dict[str, deque] = {}
        
        # 检测到的资金流向模式
        self.detected_patterns: Dict[str, str] = {}  # 'accumulation' | 'distribution' | 'neutral'
        
        # 统计
        self.total_analyzed = 0
        self.smart_money_detected = 0
        
    def _on_signal(self, signal: Signal):
        """处理信号"""
        emoji = "💰" if signal.signal_type == 'buy' else "🏃" if signal.signal_type == 'sell' else "👁️"
        print(f"{emoji} [{signal.strategy_name}] {signal.signal_type.upper()} | "
              f"股票: {signal.symbol} | 置信度: {signal.confidence:.2f} | "
              f"原因: {signal.reason}")
    
    def _analyze_tick_data(self, symbol: str, row: Any) -> Dict[str, float]:
        """
        分析逐笔数据，计算资金流向
        
        从 tick 数据中提取：
        - 大单买入金额
        - 大单卖出金额
        - 小单买入金额
        - 小单卖出金额
        """
        # 从 row 中提取数据
        price = row.get('close', row.get('price', 0))
        volume = row.get('volume', 0)
        
        # 如果有逐笔数据
        buy_volume = row.get('buy_volume', volume * 0.5)  # 默认一半
        sell_volume = row.get('sell_volume', volume * 0.5)
        
        # 估算大单（假设大单占总成交量的20%）
        large_buy_volume = buy_volume * 0.2
        large_sell_volume = sell_volume * 0.2
        small_buy_volume = buy_volume * 0.8
        small_sell_volume = sell_volume * 0.8
        
        # 计算金额
        large_buy_amount = large_buy_volume * price
        large_sell_amount = large_sell_volume * price
        small_buy_amount = small_buy_volume * price
        small_sell_amount = small_sell_volume * price
        
        return {
            'large_buy': large_buy_amount,
            'large_sell': large_sell_amount,
            'small_buy': small_buy_amount,
            'small_sell': small_sell_amount,
            'total_amount': (large_buy_amount + large_sell_amount + 
                           small_buy_amount + small_sell_amount)
        }
    
    def _calculate_money_flow_imbalance(self, flow_data: Dict[str, float]) -> float:
        """
        计算资金流向不平衡度
        
        Returns:
            -1.0 到 1.0 的值，正值表示资金流入，负值表示流出
        """
        large_buy = flow_data['large_buy']
        large_sell = flow_data['large_sell']
        small_buy = flow_data['small_buy']
        small_sell = flow_data['small_sell']
        
        total_large = large_buy + large_sell
        total_small = small_buy + small_sell
        
        if total_large == 0 or total_small == 0:
            return 0.0
        
        # 大单不平衡度（权重60%）
        large_imbalance = (large_buy - large_sell) / total_large
        
        # 小单不平衡度（权重40%）
        small_imbalance = (small_buy - small_sell) / total_small
        
        # 综合不平衡度
        combined = large_imbalance * 0.6 + small_imbalance * 0.4
        
        return combined
    
    def _update_flow_history(self, symbol: str, imbalance: float, flow_data: Dict[str, float]):
        """更新资金流向历史"""
        current_time = self._get_market_time()
        
        if symbol not in self.money_flow_history:
            self.money_flow_history[symbol] = deque(maxlen=30)
            self.imbalance_history[symbol] = deque(maxlen=30)
        
        self.money_flow_history[symbol].append({
            'time': current_time,
            'flow': flow_data,
            'imbalance': imbalance
        })
        self.imbalance_history[symbol].append(imbalance)
    
    def _detect_accumulation_pattern(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        检测建仓模式
        
        特征：
        - 持续的大单买入
        - 价格稳定或小幅上涨
        - 小单卖出（散户恐慌）
        """
        if symbol not in self.money_flow_history:
            return None
        
        history = list(self.money_flow_history[symbol])
        if len(history) < 5:
            return None
        
        # 计算近期平均不平衡度
        recent_imbalances = [h['imbalance'] for h in history[-5:]]
        avg_imbalance = np.mean(recent_imbalances)
        
        # 计算大单买入持续性
        large_buy_trend = []
        for h in history[-5:]:
            flow = h['flow']
            total_large = flow['large_buy'] + flow['large_sell']
            if total_large > 0:
                large_buy_ratio = flow['large_buy'] / total_large
                large_buy_trend.append(large_buy_ratio)
        
        if not large_buy_trend:
            return None
        
        avg_large_buy_ratio = np.mean(large_buy_trend)
        
        # 建仓模式判断
        if (avg_imbalance > self.accumulation_threshold * 0.5 and 
            avg_large_buy_ratio > 0.6):
            return {
                'detected': True,
                'pattern': 'accumulation',
                'confidence': min(avg_imbalance + avg_large_buy_ratio - 0.5, 0.95),
                'avg_imbalance': avg_imbalance,
                'avg_large_buy_ratio': avg_large_buy_ratio
            }
        
        return None
    
    def _detect_distribution_pattern(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        检测出货模式
        
        特征：
        - 持续的大单卖出
        - 价格滞涨或下跌
        - 小单买入（散户接盘）
        """
        if symbol not in self.money_flow_history:
            return None
        
        history = list(self.money_flow_history[symbol])
        if len(history) < 5:
            return None
        
        # 计算近期平均不平衡度
        recent_imbalances = [h['imbalance'] for h in history[-5:]]
        avg_imbalance = np.mean(recent_imbalances)
        
        # 计算大单卖出持续性
        large_sell_trend = []
        for h in history[-5:]:
            flow = h['flow']
            total_large = flow['large_buy'] + flow['large_sell']
            if total_large > 0:
                large_sell_ratio = flow['large_sell'] / total_large
                large_sell_trend.append(large_sell_ratio)
        
        if not large_sell_trend:
            return None
        
        avg_large_sell_ratio = np.mean(large_sell_trend)
        
        # 出货模式判断
        if (avg_imbalance < self.distribution_threshold * 0.5 and 
            avg_large_sell_ratio > 0.6):
            return {
                'detected': True,
                'pattern': 'distribution',
                'confidence': min(abs(avg_imbalance) + avg_large_sell_ratio - 0.5, 0.95),
                'avg_imbalance': avg_imbalance,
                'avg_large_sell_ratio': avg_large_sell_ratio
            }
        
        return None
    
    def _analyze_symbol(self, symbol: str, row: Any, context: Dict[str, Any]) -> Optional[Signal]:
        """分析单个股票的资金流向"""
        current_time = self._get_market_time()
        
        # 分析 tick 数据
        flow_data = self._analyze_tick_data(symbol, row)
        
        if flow_data['total_amount'] < self.large_order_threshold:
            return None
        
        # 计算不平衡度
        imbalance = self._calculate_money_flow_imbalance(flow_data)
        
        # 更新历史
        self._update_flow_history(symbol, imbalance, flow_data)
        
        self.total_analyzed += 1
        
        # 检测建仓模式
        accumulation = self._detect_accumulation_pattern(symbol)
        if accumulation and accumulation['detected']:
            self.smart_money_detected += 1
            
            if not self.can_emit_signal(symbol):
                return None
            
            signal = Signal(
                strategy_name=self.name,
                symbol=symbol,
                signal_type='buy',
                confidence=accumulation['confidence'],
                score=imbalance,
                reason=f"聪明钱建仓 | 大单买入占比: {accumulation['avg_large_buy_ratio']:.1%}, 资金不平衡度: {imbalance:.2f}",
                timestamp=current_time,
                metadata={
                    'pattern': 'accumulation',
                    'avg_imbalance': accumulation['avg_imbalance'],
                    'avg_large_buy_ratio': accumulation['avg_large_buy_ratio'],
                    'current_imbalance': imbalance
                }
            )
            
            self.emit_signal(signal)
            self.detected_patterns[symbol] = 'accumulation'
            return signal
        
        # 检测出货模式
        distribution = self._detect_distribution_pattern(symbol)
        if distribution and distribution['detected']:
            self.smart_money_detected += 1
            
            if not self.can_emit_signal(f"{symbol}_sell"):
                return None
            
            signal = Signal(
                strategy_name=self.name,
                symbol=symbol,
                signal_type='sell',
                confidence=distribution['confidence'],
                score=imbalance,
                reason=f"聪明钱出货 | 大单卖出占比: {distribution['avg_large_sell_ratio']:.1%}, 资金不平衡度: {imbalance:.2f}",
                timestamp=current_time,
                metadata={
                    'pattern': 'distribution',
                    'avg_imbalance': distribution['avg_imbalance'],
                    'avg_large_sell_ratio': distribution['avg_large_sell_ratio'],
                    'current_imbalance': imbalance
                }
            )
            
            self.emit_signal(signal)
            self.detected_patterns[symbol] = 'distribution'
            return signal
        
        self.detected_patterns[symbol] = 'neutral'
        return None
    
    def analyze(self, data, context: Dict[str, Any]) -> List[Signal]:
        """
        分析数据
        
        Args:
            data: DataFrame with tick data
            context: 上下文
        """
        signals = []
        
        if data is None or data.empty:
            return signals
        
        # 遍历数据
        for idx, row in data.iterrows():
            symbol = row.get('code', idx)
            
            signal = self._analyze_symbol(symbol, row, context)
            if signal:
                signals.append(signal)
        
        return signals
    
    def get_flow_summary(self) -> Dict[str, Any]:
        """获取资金流向摘要"""
        accumulation_count = sum(1 for p in self.detected_patterns.values() if p == 'accumulation')
        distribution_count = sum(1 for p in self.detected_patterns.values() if p == 'distribution')
        
        return {
            'total_analyzed': self.total_analyzed,
            'smart_money_detected': self.smart_money_detected,
            'accumulation_signals': accumulation_count,
            'distribution_signals': distribution_count,
            'detection_rate': self.smart_money_detected / max(self.total_analyzed, 1),
            'monitored_symbols': len(self.money_flow_history)
        }
    
    def get_top_accumulation_candidates(self, top_n: int = 10) -> List[Dict[str, Any]]:
        """获取建仓候选股票"""
        candidates = []
        
        for symbol, pattern in self.detected_patterns.items():
            if pattern == 'accumulation' and symbol in self.money_flow_history:
                history = list(self.money_flow_history[symbol])
                if history:
                    latest = history[-1]
                    candidates.append({
                        'symbol': symbol,
                        'imbalance': latest['imbalance'],
                        'history_length': len(history)
                    })
        
        candidates.sort(key=lambda x: x['imbalance'], reverse=True)
        return candidates[:top_n]
