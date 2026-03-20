"""
动量突破追踪策略

追踪高注意力股票的动量突破，结合价格动量和成交量动量
"""

import time
import numpy as np
from typing import Dict, List, Optional, Any
from collections import deque

from .base import AttentionStrategyBase, Signal


class MomentumSurgeTracker(AttentionStrategyBase):
    """
    动量突破追踪策略
    
    核心逻辑：
    1. 只处理高注意力权重的股票（节省计算资源）
    2. 计算价格动量（价格变化率）
    3. 计算成交量动量（成交量放大倍数）
    4. 当价格和成交量同时突破阈值时，生成买入信号
    5. 当动量衰竭时，生成卖出信号
    
    只在市场注意力高时执行，避免无效计算
    """
    
    def __init__(
        self,
        price_momentum_window: int = 10,      # 价格动量计算窗口
        volume_momentum_window: int = 5,       # 成交量动量计算窗口
        price_threshold: float = 0.03,         # 价格突破阈值 (3%)
        volume_threshold: float = 2.0,         # 成交量放大阈值 (2倍)
        combined_threshold: float = 0.7,       # 综合得分阈值
        profit_target: float = 0.05,           # 止盈目标 (5%)
        stop_loss: float = -0.03,              # 止损线 (-3%)
        min_symbol_weight: float = 2.0,        # 最低个股权重
        cooldown_period: float = 180.0         # 3分钟冷却期
    ):
        super().__init__(
            strategy_id="momentum_surge_tracker",
            name="Momentum Surge Tracker",
            scope='symbol',
            min_global_attention=0.4,  # 需要较高全局注意力
            min_symbol_weight=min_symbol_weight,
            max_positions=20,
            cooldown_period=cooldown_period
        )
        
        self.price_momentum_window = price_momentum_window
        self.volume_momentum_window = volume_momentum_window
        self.price_threshold = price_threshold
        self.volume_threshold = volume_threshold
        self.combined_threshold = combined_threshold
        self.profit_target = profit_target
        self.stop_loss = stop_loss
        
        # 股票历史数据缓存
        self.price_history: Dict[str, deque] = {}
        self.volume_history: Dict[str, deque] = {}
        self.entry_prices: Dict[str, float] = {}
        self.momentum_scores: Dict[str, float] = {}
        
        # 跟踪状态
        self.watching: set = set()  # 正在观察的股票
        self.breakout_candidates: Dict[str, Dict] = {}  # 突破候选
        
    def _on_signal(self, signal: Signal):
        """处理信号"""
        emoji = "🚀" if signal.signal_type == 'buy' else "💨" if signal.signal_type == 'sell' else "👀"
        print(f"{emoji} [{signal.strategy_name}] {signal.signal_type.upper()} | "
              f"股票: {signal.symbol} | 置信度: {signal.confidence:.2f} | "
              f"得分: {signal.score:.3f} | 原因: {signal.reason}")
    
    def _update_history(self, symbol: str, price: float, volume: float):
        """更新历史数据"""
        if symbol not in self.price_history:
            self.price_history[symbol] = deque(maxlen=self.price_momentum_window + 5)
            self.volume_history[symbol] = deque(maxlen=self.volume_momentum_window + 5)
        
        self.price_history[symbol].append(price)
        self.volume_history[symbol].append(volume)
    
    def _calculate_price_momentum(self, symbol: str) -> float:
        """计算价格动量（变化率）"""
        if symbol not in self.price_history:
            return 0.0
        
        prices = list(self.price_history[symbol])
        if len(prices) < self.price_momentum_window:
            return 0.0
        
        # 计算N日价格变化率
        current = prices[-1]
        past = prices[-self.price_momentum_window]
        
        if past == 0:
            return 0.0
        
        return (current - past) / past
    
    def _calculate_volume_momentum(self, symbol: str) -> float:
        """计算成交量动量（相对平均值）"""
        if symbol not in self.volume_history:
            return 1.0
        
        volumes = list(self.volume_history[symbol])
        if len(volumes) < self.volume_momentum_window:
            return 1.0
        
        current_volume = volumes[-1]
        avg_volume = np.mean(volumes[-self.volume_momentum_window:])
        
        if avg_volume == 0:
            return 1.0
        
        return current_volume / avg_volume
    
    def _calculate_momentum_score(self, price_momentum: float, volume_momentum: float) -> float:
        """计算综合动量得分"""
        # 价格动量标准化 (0-1)
        price_score = min(abs(price_momentum) / self.price_threshold, 1.0)
        
        # 成交量动量标准化 (0-1)
        # volume_momentum 2.0 -> score 1.0
        volume_score = min((volume_momentum - 1.0) / (self.volume_threshold - 1.0), 1.0)
        
        # 综合得分（价格占60%，成交量占40%）
        combined = price_score * 0.6 + volume_score * 0.4
        
        return combined
    
    def _check_exit_conditions(self, symbol: str, current_price: float) -> Optional[str]:
        """检查退出条件"""
        if symbol not in self.entry_prices:
            return None
        
        entry_price = self.entry_prices[symbol]
        pnl = (current_price - entry_price) / entry_price
        
        if pnl >= self.profit_target:
            return f"止盈触发，收益: {pnl*100:.2f}%"
        elif pnl <= self.stop_loss:
            return f"止损触发，亏损: {pnl*100:.2f}%"
        
        return None
    
    def _analyze_symbol(self, symbol: str, row: Any, context: Dict[str, Any]) -> Optional[Signal]:
        """分析单个股票"""
        current_time = time.time()
        
        # 提取数据
        price = row.get('close', row.get('price', 0))
        volume = row.get('volume', 0)
        
        if price <= 0 or volume <= 0:
            return None
        
        # 更新历史
        self._update_history(symbol, price, volume)
        
        # 获取权重
        symbol_weight = self.get_symbol_weight(symbol)
        
        # 检查退出条件（如果已持仓）
        exit_reason = self._check_exit_conditions(symbol, price)
        if exit_reason and self.can_emit_signal(symbol):
            signal = Signal(
                strategy_name=self.name,
                symbol=symbol,
                signal_type='sell',
                confidence=0.8,
                score=0.0,
                reason=exit_reason,
                timestamp=current_time,
                metadata={
                    'exit_type': 'stop',
                    'pnl': (price - self.entry_prices.get(symbol, price)) / self.entry_prices.get(symbol, price) if symbol in self.entry_prices else 0
                }
            )
            self.emit_signal(signal)
            
            # 清理持仓
            if symbol in self.entry_prices:
                del self.entry_prices[symbol]
            if symbol in self.positions:
                del self.positions[symbol]
            
            return signal
        
        # 计算动量
        price_momentum = self._calculate_price_momentum(symbol)
        volume_momentum = self._calculate_volume_momentum(symbol)
        
        # 存储动量分数
        momentum_score = self._calculate_momentum_score(price_momentum, volume_momentum)
        self.momentum_scores[symbol] = momentum_score
        
        # 检查突破条件
        if (price_momentum > self.price_threshold and 
            volume_momentum > self.volume_threshold and
            momentum_score > self.combined_threshold):
            
            # 检查冷却期
            if not self.can_emit_signal(symbol):
                return None
            
            # 检查持仓限制
            if len(self.positions) >= self.max_positions:
                return None
            
            # 生成买入信号
            confidence = min(momentum_score, 1.0)
            
            signal = Signal(
                strategy_name=self.name,
                symbol=symbol,
                signal_type='buy',
                confidence=confidence,
                score=momentum_score,
                reason=f"动量突破 | 价格动量: {price_momentum:.2%}, 成交量: {volume_momentum:.1f}x, 权重: {symbol_weight:.1f}",
                timestamp=current_time,
                metadata={
                    'price_momentum': price_momentum,
                    'volume_momentum': volume_momentum,
                    'momentum_score': momentum_score,
                    'symbol_weight': symbol_weight,
                    'entry_price': price
                }
            )
            
            self.emit_signal(signal)
            
            # 记录持仓
            self.positions[symbol] = {
                'entry_price': price,
                'entry_time': current_time,
                'momentum_score': momentum_score
            }
            self.entry_prices[symbol] = price
            
            return signal
        
        return None
    
    def analyze(self, data, context: Dict[str, Any]) -> List[Signal]:
        """
        分析数据
        
        Args:
            data: DataFrame with columns: code, close/price, volume
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
    
    def get_momentum_ranking(self, top_n: int = 20) -> List[Dict[str, Any]]:
        """获取动量排名"""
        rankings = []
        
        for symbol, score in self.momentum_scores.items():
            if symbol in self.price_history and len(self.price_history[symbol]) > 0:
                current_price = self.price_history[symbol][-1]
                
                rankings.append({
                    'symbol': symbol,
                    'momentum_score': score,
                    'price_momentum': self._calculate_price_momentum(symbol),
                    'volume_momentum': self._calculate_volume_momentum(symbol),
                    'current_price': current_price,
                    'in_position': symbol in self.positions
                })
        
        # 按动量得分排序
        rankings.sort(key=lambda x: x['momentum_score'], reverse=True)
        
        return rankings[:top_n]
