#!/usr/bin/env python
"""
策略池模块 - 智能选股策略系统 v2.0
多策略动态切换和组合
"""

import numpy as np
from typing import Dict, Any, List, Optional
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass

from river import linear_model, optim, preprocessing


@dataclass
class StrategyPerformance:
    """策略表现"""
    total_return: float = 0.0
    win_rate: float = 0.0
    trade_count: int = 0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0


class BaseStrategy(ABC):
    """策略基类"""
    
    def __init__(self, name: str, params: Dict[str, Any]):
        self.name = name
        self.params = params
        self.performance = StrategyPerformance()
        self.trade_history: List[Dict] = []
    
    @abstractmethod
    def should_buy(self, features: Dict[str, float]) -> bool:
        """是否应该买入"""
        pass
    
    @abstractmethod
    def should_sell(self, position: Any, current_price: float) -> bool:
        """是否应该卖出"""
        pass
    
    def record_trade(self, trade: Dict):
        """记录交易"""
        self.trade_history.append(trade)
        self._update_performance()
    
    def _update_performance(self):
        """更新表现统计"""
        if not self.trade_history:
            return
        
        profits = [t.get('profit', 0) for t in self.trade_history]
        wins = [p for p in profits if p > 0]
        
        self.performance.total_return = sum(profits)
        self.performance.win_rate = len(wins) / len(profits) if profits else 0
        self.performance.trade_count = len(self.trade_history)


class TrendFollowingStrategy(BaseStrategy):
    """
    趋势跟踪策略
    
    特点：
    - 追涨杀跌
    - 适合牛市
    - 使用均线和MACD
    """
    
    def __init__(self, params: Dict[str, Any] = None):
        default_params = {
            'ma_short': 5,
            'ma_long': 20,
            'macd_threshold': 0,
        }
        default_params.update(params or {})
        super().__init__('TrendFollowing', default_params)
        
        self.model = linear_model.LogisticRegression(
            optimizer=optim.SGD(0.01)
        )
        self.scaler = preprocessing.StandardScaler()
    
    def should_buy(self, features: Dict[str, float]) -> bool:
        """趋势向上时买入"""
        # 均线多头排列
        ma5_ratio = features.get('ma5_ratio', 0)
        ma20_ratio = features.get('ma20_ratio', 0)
        
        # MACD向上
        macd_hist = features.get('macd_histogram', 0)
        
        # 趋势确认
        return ma5_ratio > 0 and ma20_ratio > 0 and macd_hist > 0
    
    def should_sell(self, position: Any, current_price: float) -> bool:
        """趋势反转时卖出"""
        profit_pct = (current_price - position.buy_price) / position.buy_price
        
        # 趋势破坏或达到止损
        return profit_pct < -0.08 or profit_pct > 0.20


class MeanReversionStrategy(BaseStrategy):
    """
    均值回归策略
    
    特点：
    - 高抛低吸
    - 适合震荡市
    - 使用RSI和布林带
    """
    
    def __init__(self, params: Dict[str, Any] = None):
        default_params = {
            'rsi_oversold': 30,
            'rsi_overbought': 70,
            'bb_lower_threshold': 0.2,
        }
        default_params.update(params or {})
        super().__init__('MeanReversion', default_params)
        
        self.model = linear_model.LogisticRegression(
            optimizer=optim.SGD(0.01)
        )
        self.scaler = preprocessing.StandardScaler()
    
    def should_buy(self, features: Dict[str, float]) -> bool:
        """超卖时买入"""
        rsi = features.get('rsi_14', 50)
        bb_position = features.get('bollinger_position', 0.5)
        
        # RSI超卖且接近布林带下轨
        return rsi < self.params['rsi_oversold'] and bb_position < self.params['bb_lower_threshold']
    
    def should_sell(self, position: Any, current_price: float) -> bool:
        """超买时卖出"""
        profit_pct = (current_price - position.buy_price) / position.buy_price
        
        # 达到目标收益或止损
        return profit_pct > 0.08 or profit_pct < -0.05


class MomentumStrategy(BaseStrategy):
    """
    动量策略
    
    特点：
    - 追逐强势
    - 适合热点板块
    - 使用价格动量和成交量
    """
    
    def __init__(self, params: Dict[str, Any] = None):
        default_params = {
            'momentum_threshold': 2.0,
            'volume_threshold': 1.5,
        }
        default_params.update(params or {})
        super().__init__('Momentum', default_params)
        
        self.model = linear_model.LogisticRegression(
            optimizer=optim.SGD(0.02)
        )
        self.scaler = preprocessing.StandardScaler()
    
    def should_buy(self, features: Dict[str, float]) -> bool:
        """动量强劲时买入"""
        momentum = features.get('momentum_10', 0)
        volume_ratio = features.get('volume_ratio', 1.0)
        price_change = features.get('price_change_1d', 0)
        
        # 价格动量强劲且放量
        return (momentum > self.params['momentum_threshold'] and 
                volume_ratio > self.params['volume_threshold'] and
                price_change > 1.0)
    
    def should_sell(self, position: Any, current_price: float) -> bool:
        """动量衰竭时卖出"""
        profit_pct = (current_price - position.buy_price) / position.buy_price
        
        # 动量策略需要快速止损
        return profit_pct < -0.05 or profit_pct > 0.15


class BlockRotationStrategy(BaseStrategy):
    """
    板块轮动策略
    
    特点：
    - 追逐热点板块
    - 板块动量选股
    - 适合结构性行情
    """
    
    def __init__(self, params: Dict[str, Any] = None):
        default_params = {
            'block_momentum_threshold': 1.0,
            'min_block_count': 2,
        }
        default_params.update(params or {})
        super().__init__('BlockRotation', default_params)
        
        self.model = linear_model.LogisticRegression(
            optimizer=optim.SGD(0.01)
        )
        self.scaler = preprocessing.StandardScaler()
    
    def should_buy(self, features: Dict[str, float]) -> bool:
        """板块热点时买入"""
        block_momentum = features.get('block_momentum', 0)
        block_count = features.get('block_count', 0)
        
        # 所属板块表现好且股票有板块概念
        return (block_momentum > self.params['block_momentum_threshold'] and
                block_count >= self.params['min_block_count'])
    
    def should_sell(self, position: Any, current_price: float) -> bool:
        """板块退潮时卖出"""
        profit_pct = (current_price - position.buy_price) / position.buy_price
        
        # 板块策略中等止盈止损
        return profit_pct < -0.07 or profit_pct > 0.12


class StrategyPool:
    """
    策略池 - 管理多个策略
    """
    
    def __init__(self):
        self.strategies: Dict[str, BaseStrategy] = {
            'trend_following': TrendFollowingStrategy(),
            'mean_reversion': MeanReversionStrategy(),
            'momentum': MomentumStrategy(),
            'block_rotation': BlockRotationStrategy(),
        }
        
        self.current_strategy = 'trend_following'
        self.performance_history: Dict[str, List[float]] = defaultdict(list)
    
    def select_strategy(self, market_state: str) -> BaseStrategy:
        """
        根据市场状态选择策略
        
        Args:
            market_state: 市场状态
            
        Returns:
            选中的策略
        """
        # 状态到策略的映射
        state_strategy_map = {
            'bull_volatile': 'momentum',
            'bull_stable': 'trend_following',
            'bear_volatile': 'mean_reversion',
            'bear_stable': 'mean_reversion',
            'sideways': 'mean_reversion',
            'neutral': 'block_rotation',
        }
        
        strategy_name = state_strategy_map.get(market_state, 'block_rotation')
        self.current_strategy = strategy_name
        
        return self.strategies[strategy_name]
    
    def get_current_strategy(self) -> BaseStrategy:
        """获取当前策略"""
        return self.strategies[self.current_strategy]
    
    def record_performance(self, strategy_name: str, profit: float):
        """记录策略表现"""
        self.performance_history[strategy_name].append(profit)
        
        # 限制历史长度
        if len(self.performance_history[strategy_name]) > 100:
            self.performance_history[strategy_name] = self.performance_history[strategy_name][-100:]
    
    def get_best_strategy(self) -> str:
        """获取表现最好的策略"""
        avg_returns = {}
        for name, profits in self.performance_history.items():
            if profits:
                avg_returns[name] = np.mean(profits[-20:])
            else:
                avg_returns[name] = 0
        
        return max(avg_returns, key=avg_returns.get)
    
    def get_all_performances(self) -> Dict[str, StrategyPerformance]:
        """获取所有策略的表现"""
        return {name: strategy.performance for name, strategy in self.strategies.items()}


class MarketStateDetector:
    """
    市场状态检测器
    """
    
    def __init__(self):
        self.market_history: List[Dict] = []
    
    def update(self, market_data: Dict[str, float]):
        """更新市场数据"""
        self.market_history.append(market_data)
        
        # 限制历史长度
        if len(self.market_history) > 20:
            self.market_history = self.market_history[-20:]
    
    def detect_state(self) -> str:
        """
        检测当前市场状态
        
        Returns:
            市场状态字符串
        """
        if len(self.market_history) < 5:
            return 'neutral'
        
        recent = self.market_history[-5:]
        
        # 计算市场指标
        avg_change = np.mean([d.get('avg_change', 0) for d in recent])
        volatility = np.std([d.get('avg_change', 0) for d in recent])
        up_down_ratio = np.mean([d.get('up_down_ratio', 1) for d in recent])
        
        # 判断市场状态
        if avg_change > 0.5 and volatility > 1.5:
            return 'bull_volatile'
        elif avg_change > 0.5 and volatility <= 1.5:
            return 'bull_stable'
        elif avg_change < -0.5 and volatility > 1.5:
            return 'bear_volatile'
        elif avg_change < -0.5 and volatility <= 1.5:
            return 'bear_stable'
        elif abs(avg_change) <= 0.3:
            return 'sideways'
        else:
            return 'neutral'


# 测试代码
if __name__ == "__main__":
    print("="*70)
    print("策略池模块测试")
    print("="*70)
    
    # 创建策略池
    pool = StrategyPool()
    
    # 测试策略选择
    print("\n测试策略选择:")
    states = ['bull_volatile', 'bull_stable', 'bear_volatile', 'sideways', 'neutral']
    for state in states:
        strategy = pool.select_strategy(state)
        print(f"  {state:20s} -> {strategy.name}")
    
    # 测试策略买入信号
    print("\n测试策略买入信号:")
    test_features = {
        'ma5_ratio': 0.02,
        'ma20_ratio': 0.05,
        'macd_histogram': 0.3,
        'rsi_14': 25,
        'bollinger_position': 0.1,
        'momentum_10': 3.0,
        'volume_ratio': 2.0,
        'block_momentum': 2.5,
        'block_count': 3,
    }
    
    for name, strategy in pool.strategies.items():
        should_buy = strategy.should_buy(test_features)
        print(f"  {strategy.name:20s}: {'买入' if should_buy else '观望'}")
    
    print("\n" + "="*70)
    print("测试完成!")
    print("="*70)
