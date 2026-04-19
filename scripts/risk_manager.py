#!/usr/bin/env python
"""
风险管理模块 - 智能选股策略系统 v2.0
包含仓位管理、止盈止损、回撤控制等功能
"""

import numpy as np
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from collections import defaultdict


@dataclass
class Position:
    """持仓信息"""
    code: str
    name: str
    buy_price: float
    volume: int
    current_price: float = 0.0
    highest_price: float = 0.0
    buy_time: float = 0.0
    
    @property
    def profit_pct(self) -> float:
        if self.buy_price == 0:
            return 0.0
        return (self.current_price - self.buy_price) / self.buy_price * 100
    
    @property
    def profit_amount(self) -> float:
        return (self.current_price - self.buy_price) * self.volume
    
    @property
    def market_value(self) -> float:
        return self.current_price * self.volume


class PositionSizer:
    """
    仓位管理器 - 使用Kelly公式
    """
    
    def __init__(self, max_position_pct: float = 0.15, min_position_pct: float = 0.05):
        self.max_position_pct = max_position_pct
        self.min_position_pct = min_position_pct
        
        # 历史交易统计
        self.trade_history: Dict[str, List[Dict]] = defaultdict(list)
    
    def record_trade(self, stock_code: str, profit: float, is_win: bool):
        """记录交易结果"""
        self.trade_history[stock_code].append({
            'profit': profit,
            'is_win': is_win,
        })
        
        # 限制历史长度
        if len(self.trade_history[stock_code]) > 50:
            self.trade_history[stock_code] = self.trade_history[stock_code][-50:]
    
    def calculate_position_size(self, stock_code: str, confidence: float, 
                               total_capital: float) -> int:
        """
        使用Kelly公式计算仓位大小
        
        Kelly公式: f* = (bp - q) / b
        - b: 赔率 (平均盈利/平均亏损)
        - p: 胜率
        - q: 败率 = 1 - p
        
        Returns:
            建议买入股数
        """
        history = self.trade_history.get(stock_code, [])
        
        if len(history) < 5:
            # 历史数据不足，使用默认仓位
            position_value = total_capital * self.min_position_pct * confidence
            return int(position_value / 100) * 100  # 整手
        
        # 计算胜率
        wins = [t for t in history if t['is_win']]
        losses = [t for t in history if not t['is_win']]
        
        win_rate = len(wins) / len(history)
        loss_rate = 1 - win_rate
        
        # 计算赔率
        avg_win = np.mean([t['profit'] for t in wins]) if wins else 0.01
        avg_loss = abs(np.mean([t['profit'] for t in losses])) if losses else 0.01
        
        odds = avg_win / avg_loss if avg_loss > 0 else 1.0
        
        # Kelly公式
        kelly_fraction = (odds * win_rate - loss_rate) / odds if odds > 0 else 0
        
        # 半Kelly（更保守）
        half_kelly = kelly_fraction * 0.5
        
        # 结合模型置信度
        adjusted_fraction = half_kelly * confidence
        
        # 限制在合理范围内
        final_fraction = max(self.min_position_pct, 
                            min(adjusted_fraction, self.max_position_pct))
        
        # 计算股数
        position_value = total_capital * final_fraction
        shares = int(position_value / 100) * 100  # 整手
        
        return max(shares, 100)  # 最少100股


class StopLossManager:
    """
    止损管理器 - 支持固定止损和跟踪止损
    """
    
    def __init__(self, 
                 initial_stop: float = -0.08,
                 trailing_stop: float = 0.05,
                 use_trailing: bool = True):
        self.initial_stop = initial_stop
        self.trailing_stop = trailing_stop
        self.use_trailing = use_trailing
        
        # 跟踪最高价
        self.highest_prices: Dict[str, float] = {}
    
    def update_price(self, stock_code: str, current_price: float):
        """更新最高价"""
        if stock_code not in self.highest_prices:
            self.highest_prices[stock_code] = current_price
        else:
            self.highest_prices[stock_code] = max(
                self.highest_prices[stock_code], 
                current_price
            )
    
    def check_stop_loss(self, position: Position) -> Optional[Dict]:
        """
        检查是否触发止损
        
        Returns:
            如果触发止损，返回卖出信号；否则返回None
        """
        # 更新最高价
        self.update_price(position.code, position.current_price)
        
        # 计算当前亏损
        current_loss_pct = (position.current_price - position.buy_price) / position.buy_price
        
        # 初始止损检查
        if current_loss_pct <= self.initial_stop:
            return {
                'action': 'SELL',
                'reason': f'初始止损触发，亏损 {current_loss_pct*100:.2f}%',
                'type': 'stop_loss'
            }
        
        # 跟踪止损检查
        if self.use_trailing:
            highest = self.highest_prices.get(position.code, position.buy_price)
            trailing_stop_price = highest * (1 - self.trailing_stop)
            
            if position.current_price <= trailing_stop_price:
                return {
                    'action': 'SELL',
                    'reason': f'跟踪止损触发，从最高点 {highest:.2f} 回撤 {self.trailing_stop*100:.1f}%',
                    'type': 'trailing_stop'
                }
        
        return None
    
    def reset(self, stock_code: str):
        """重置某只股票的跟踪数据"""
        if stock_code in self.highest_prices:
            del self.highest_prices[stock_code]


class TakeProfitManager:
    """
    止盈管理器 - 分级止盈
    """
    
    def __init__(self):
        # 止盈层级: (盈利比例, 止盈仓位比例)
        self.take_profit_levels = [
            (0.05, 0.30),   # 盈利5%，止盈30%仓位
            (0.10, 0.30),   # 盈利10%，再止盈30%仓位
            (0.15, 0.20),   # 盈利15%，再止盈20%仓位
            (0.20, 0.20),   # 盈利20%，清仓剩余20%
        ]
        
        # 记录已触发的层级
        self.triggered_levels: Dict[str, set] = defaultdict(set)
    
    def check_take_profit(self, position: Position) -> List[Dict]:
        """
        检查是否触发止盈
        
        Returns:
            止盈信号列表
        """
        signals = []
        profit_pct = position.profit_pct / 100  # 转换为小数
        stock_code = position.code
        
        for level, ratio in self.take_profit_levels:
            if profit_pct >= level and level not in self.triggered_levels[stock_code]:
                signals.append({
                    'action': 'PARTIAL_SELL',
                    'ratio': ratio,
                    'reason': f'盈利达到 {level*100:.0f}%，止盈 {ratio*100:.0f}% 仓位',
                    'level': level,
                })
                self.triggered_levels[stock_code].add(level)
        
        return signals
    
    def reset(self, stock_code: str):
        """重置某只股票的止盈状态"""
        if stock_code in self.triggered_levels:
            del self.triggered_levels[stock_code]


class DrawdownController:
    """
    回撤控制器
    """
    
    def __init__(self, max_drawdown: float = 0.15):
        self.max_drawdown = max_drawdown
        self.peak_value = 0.0
        self.current_drawdown = 0.0
    
    def update(self, current_value: float) -> Optional[Dict]:
        """
        更新回撤状态
        
        Returns:
            如果触发回撤限制，返回控制信号
        """
        # 更新峰值
        if current_value > self.peak_value:
            self.peak_value = current_value
            self.current_drawdown = 0.0
        else:
            # 计算回撤
            self.current_drawdown = (self.peak_value - current_value) / self.peak_value
        
        # 检查是否超过最大回撤
        if self.current_drawdown >= self.max_drawdown:
            return {
                'action': 'EMERGENCY',
                'reason': f'最大回撤限制触发，当前回撤 {self.current_drawdown*100:.2f}%',
                'suggestion': '暂停新开仓，逐步减仓',
            }
        
        # 回撤警告
        if self.current_drawdown >= self.max_drawdown * 0.7:
            return {
                'action': 'WARNING',
                'reason': f'回撤警告，当前回撤 {self.current_drawdown*100:.2f}%',
                'suggestion': '谨慎开仓，加强风控',
            }
        
        return None
    
    def get_status(self) -> Dict[str, float]:
        """获取回撤状态"""
        return {
            'peak_value': self.peak_value,
            'current_drawdown': self.current_drawdown,
            'max_drawdown_limit': self.max_drawdown,
        }


class RiskManager:
    """
    风险管理主类 - 整合所有风控组件
    """
    
    def __init__(self, 
                 max_position_pct: float = 0.15,
                 initial_stop: float = -0.08,
                 trailing_stop: float = 0.05,
                 max_drawdown: float = 0.15):
        
        self.position_sizer = PositionSizer(max_position_pct)
        self.stop_loss_manager = StopLossManager(initial_stop, trailing_stop)
        self.take_profit_manager = TakeProfitManager()
        self.drawdown_controller = DrawdownController(max_drawdown)
        
        # 风险统计
        self.risk_stats = {
            'total_stop_loss': 0,
            'total_take_profit': 0,
            'max_drawdown_hit': 0,
        }
    
    def calculate_position(self, stock_code: str, confidence: float, 
                          total_capital: float) -> int:
        """计算建议仓位"""
        return self.position_sizer.calculate_position_size(
            stock_code, confidence, total_capital
        )
    
    def check_risk(self, position: Position, current_value: float) -> List[Dict]:
        """
        全面风险检查
        
        Returns:
            风险信号列表
        """
        signals = []
        
        # 1. 检查止损
        stop_signal = self.stop_loss_manager.check_stop_loss(position)
        if stop_signal:
            signals.append(stop_signal)
            self.risk_stats['total_stop_loss'] += 1
        
        # 2. 检查止盈
        take_profit_signals = self.take_profit_manager.check_take_profit(position)
        signals.extend(take_profit_signals)
        self.risk_stats['total_take_profit'] += len(take_profit_signals)
        
        # 3. 检查回撤
        drawdown_signal = self.drawdown_controller.update(current_value)
        if drawdown_signal and drawdown_signal['action'] == 'EMERGENCY':
            signals.append(drawdown_signal)
            self.risk_stats['max_drawdown_hit'] += 1
        
        return signals
    
    def record_trade_result(self, stock_code: str, profit: float, is_win: bool):
        """记录交易结果"""
        self.position_sizer.record_trade(stock_code, profit, is_win)
    
    def reset_stock(self, stock_code: str):
        """重置某只股票的风险状态"""
        self.stop_loss_manager.reset(stock_code)
        self.take_profit_manager.reset(stock_code)
    
    def get_risk_report(self) -> Dict[str, Any]:
        """获取风险报告"""
        drawdown_status = self.drawdown_controller.get_status()
        
        return {
            'drawdown': drawdown_status,
            'stats': self.risk_stats.copy(),
            'stop_loss_count': self.risk_stats['total_stop_loss'],
            'take_profit_count': self.risk_stats['total_take_profit'],
        }


# 测试代码
if __name__ == "__main__":
    print("="*70)
    print("风险管理模块测试")
    print("="*70)
    
    # 创建风险管理器
    risk_mgr = RiskManager()
    
    # 测试仓位计算
    print("\n测试仓位计算:")
    for i in range(5):
        # 模拟历史交易
        profit = np.random.randn() * 5
        is_win = profit > 0
        risk_mgr.record_trade_result('000001', profit, is_win)
    
    shares = risk_mgr.calculate_position('000001', 0.7, 100000)
    print(f"  建议仓位: {shares} 股")
    
    # 测试止损止盈
    print("\n测试止损止盈:")
    position = Position(
        code='000001',
        name='测试股票',
        buy_price=10.0,
        volume=1000,
        current_price=12.0,  # 盈利20%
    )
    
    # 更新最高价
    risk_mgr.stop_loss_manager.update_price('000001', 13.0)
    
    # 检查风险
    signals = risk_mgr.check_risk(position, 120000)
    print(f"  风险信号数量: {len(signals)}")
    for sig in signals:
        print(f"    - {sig['action']}: {sig['reason']}")
    
    # 测试回撤
    print("\n测试回撤控制:")
    for value in [100000, 95000, 90000, 85000]:
        signal = risk_mgr.drawdown_controller.update(value)
        status = risk_mgr.drawdown_controller.get_status()
        print(f"  资产 {value}: 回撤 {status['current_drawdown']*100:.1f}%")
    
    print("\n" + "="*70)
    print("测试完成!")
    print("="*70)
