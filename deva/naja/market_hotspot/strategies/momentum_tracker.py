"""
动量突破追踪策略

追踪高热点股票的动量突破，结合价格动量和成交量动量
"""

import sys
import time
import numpy as np
from typing import Dict, List, Optional, Any
from collections import deque

from .base import HotspotStrategyBase, Signal


class MomentumSurgeTracker(HotspotStrategyBase):
    """
    动量突破追踪策略
    
    核心逻辑：
    1. 只处理高热点权重的股票（节省计算资源）
    2. 计算价格动量（价格变化率）
    3. 计算成交量动量（成交量放大倍数）
    4. 当价格和成交量同时突破阈值时，生成买入信号
    5. 当动量衰竭时，生成卖出信号
    
    只在市场热点高时执行，避免无效计算
    """
    
    def __init__(
        self,
        price_momentum_window: int = 10,      # 价格动量计算窗口
        volume_momentum_window: int = 5,       # 成交量动量计算窗口
        price_threshold: float = 0.01,          # 价格突破阈值 (1%)
        volume_threshold: float = 1.2,         # 成交量放大阈值 (1.2倍)
        combined_threshold: float = 0.30,     # 综合得分阈值
        profit_target: float = 0.05,          # 止盈目标 (5%)
        stop_loss: float = -0.02,             # 止损线 (-2%)
        min_symbol_weight: float = 0.0005,       # 最低个股权重
        cooldown_period: float = 60.0          # 1分钟冷却期
    ):
        super().__init__(
            strategy_id="momentum_surge_tracker",
            name="Momentum Surge Tracker",
            scope='symbol',
            min_global_hotspot=0.4,  # 需要较高全局热点
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
    
    def _calculate_momentum_score(self, price_momentum: float, volume_momentum: float, history_len: int = 0) -> float:
        """计算综合动量得分"""
        price_history_needed = self.price_momentum_window
        volume_history_needed = self.volume_momentum_window

        if history_len < price_history_needed or price_momentum == 0:
            if volume_momentum > self.volume_threshold:
                return min((volume_momentum - 1.0) / (self.volume_threshold - 1.0), 1.0) * 0.4
            return 0.0

        price_score = min(abs(price_momentum) / self.price_threshold, 1.0)

        if history_len < volume_history_needed:
            volume_score = 0.3
        else:
            volume_score = min((volume_momentum - 1.0) / (self.volume_threshold - 1.0), 1.0)

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
        current_time = self._get_market_time()
        
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
        price_history_len = len(self.price_history.get(symbol, []))
        volume_history_len = len(self.volume_history.get(symbol, []))

        history_len = min(price_history_len, volume_history_len)
        has_enough_history = history_len >= self.price_momentum_window

        momentum_score = self._calculate_momentum_score(price_momentum, volume_momentum, history_len)
        self.momentum_scores[symbol] = momentum_score

        buy_triggered = False
        if has_enough_history:
            if price_momentum > self.price_threshold and volume_momentum > self.volume_threshold and momentum_score > self.combined_threshold:
                buy_triggered = True
        else:
            if volume_momentum > self.volume_threshold * 1.5 and momentum_score > 0.15:
                buy_triggered = True

        if buy_triggered:
            
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
        import sys
        print(f"[Momentum] analyze called: data rows={len(data) if data is not None else 'None'}", flush=True)
        print(f"[Momentum] data columns: {list(data.columns) if data is not None else 'None'}", flush=True)
        if data is not None and len(data) > 0:
            p_changes = data['p_change'].values if 'p_change' in data.columns else []
            print(f"[Momentum] p_change stats: min={p_changes.min() if len(p_changes) > 0 else 'N/A'}, max={p_changes.max() if len(p_changes) > 0 else 'N/A'}", flush=True)
            print(f"[Momentum] p_change sample (first 10): {p_changes[:10] if len(p_changes) > 0 else 'N/A'}", flush=True)
        signals = []

        if data is None or data.empty:
            return signals

        import logging
        log = logging.getLogger(__name__)

        checked = 0
        passed_threshold = 0
        threshold = 0.005

        for idx, row in data.iterrows():
            symbol = row.get('code', idx)
            p_change = row.get('p_change', 0)
            checked += 1

            if abs(p_change) >= threshold:
                passed_threshold += 1
                confidence = min(abs(p_change) / 0.05, 1.0)
                signal = Signal(
                    strategy_name=self.name,
                    symbol=symbol,
                    signal_type='buy',
                    confidence=confidence,
                    score=abs(p_change),
                    reason=f"动量信号 | p_change: {p_change:.2%}",
                    timestamp=self._get_market_time(),
                    metadata={
                        'p_change': p_change,
                        'price': row.get('close', 0),
                        'volume': row.get('volume', 0)
                    }
                )
                if signal:
                    signals.append(signal)

        print(f"[Momentum] analyze loop done: checked={checked}, threshold={threshold}", flush=True)
        log.info(f"[Momentum] 检查 {checked} 个股票, p_change阈值({threshold})内 {passed_threshold} 个, 生成 {len(signals)} 个信号")

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
