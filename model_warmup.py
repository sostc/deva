#!/usr/bin/env python
"""
模型预热模块 - 智能选股策略系统 v2.0
解决 River 模型初始预测得分偏低的问题
"""

import time
from typing import Dict, Any
from dataclasses import dataclass


@dataclass
class WarmUpConfig:
    """预热配置"""
    warm_up_periods: int = 50          # 预热期长度（帧数）
    initial_threshold: float = 0.45     # 初始买入阈值（很低）
    normal_threshold: float = 0.55      # 正常期阈值
    initial_learning_rate: float = 0.05 # 预热期高学习率
    normal_learning_rate: float = 0.01  # 正常期学习率


class ModelWarmUpStrategy:
    """
    模型预热策略
    
    解决 River 模型初始阶段预测得分偏低的问题：
    1. 预热期使用很低的买入阈值（0.45），确保产生交易
    2. 预热期使用高学习率（0.05），快速学习
    3. 随着时间推移，逐步提高阈值和学习率
    4. 预热期结束后，使用正常参数
    """
    
    def __init__(self, config: WarmUpConfig = None):
        self.config = config or WarmUpConfig()
        self.current_period = 0
        self.is_warm_up_complete = False
        
        # 预热期交易统计
        self.warm_up_trades = []
        self.warm_up_profits = []
    
    def get_buy_threshold(self) -> float:
        """
        动态获取买入阈值
        
        预热期：从 0.45 线性增加到 0.55
        正常期：固定 0.55
        """
        if self.current_period < self.config.warm_up_periods:
            # 预热期：线性增加阈值
            ratio = self.current_period / self.config.warm_up_periods
            threshold = self.config.initial_threshold + \
                       (self.config.normal_threshold - self.config.initial_threshold) * ratio
            return threshold
        
        return self.config.normal_threshold
    
    def get_learning_rate(self) -> float:
        """
        动态获取学习率
        
        预热期：高学习率 0.05
        正常期：正常学习率 0.01
        """
        if self.current_period < self.config.warm_up_periods:
            return self.config.initial_learning_rate
        return self.config.normal_learning_rate
    
    def update(self, trade_profit: float = None):
        """
        更新预热状态
        
        Args:
            trade_profit: 本次交易收益（如果有）
        """
        self.current_period += 1
        
        if trade_profit is not None:
            self.warm_up_trades.append({
                'period': self.current_period,
                'profit': trade_profit
            })
            self.warm_up_profits.append(trade_profit)
        
        # 检查是否完成预热
        if self.current_period >= self.config.warm_up_periods and not self.is_warm_up_complete:
            self.is_warm_up_complete = True
            self._print_warm_up_summary()
    
    def _print_warm_up_summary(self):
        """打印预热期总结"""
        print("\n" + "="*70)
        print("🔥 模型预热完成")
        print("="*70)
        print(f"  预热期长度: {self.config.warm_up_periods} 帧")
        print(f"  交易次数: {len(self.warm_up_trades)}")
        
        if self.warm_up_profits:
            total_profit = sum(self.warm_up_profits)
            win_count = sum(1 for p in self.warm_up_profits if p > 0)
            win_rate = win_count / len(self.warm_up_profits) * 100
            
            print(f"  总收益: {total_profit:+.2f}")
            print(f"  胜率: {win_rate:.1f}% ({win_count}/{len(self.warm_up_profits)})")
        
        print(f"  当前买入阈值: {self.get_buy_threshold():.3f}")
        print(f"  当前学习率: {self.get_learning_rate():.3f}")
        print("="*70 + "\n")
    
    def get_status(self) -> Dict[str, Any]:
        """获取当前状态"""
        return {
            'current_period': self.current_period,
            'warm_up_periods': self.config.warm_up_periods,
            'progress': min(self.current_period / self.config.warm_up_periods * 100, 100),
            'is_warm_up_complete': self.is_warm_up_complete,
            'current_threshold': self.get_buy_threshold(),
            'current_learning_rate': self.get_learning_rate(),
            'trade_count': len(self.warm_up_trades),
        }


class AdaptiveThresholdManager:
    """
    自适应阈值管理器
    
    根据模型表现动态调整买入阈值
    """
    
    def __init__(self, 
                 base_threshold: float = 0.50,
                 min_threshold: float = 0.45,
                 max_threshold: float = 0.65,
                 adjustment_step: float = 0.01):
        self.base_threshold = base_threshold
        self.current_threshold = base_threshold
        self.min_threshold = min_threshold
        self.max_threshold = max_threshold
        self.adjustment_step = adjustment_step
        
        # 历史表现
        self.recent_predictions = []
        self.recent_accuracies = []
    
    def update_threshold(self, prediction: float, actual_result: bool):
        """
        根据预测结果更新阈值
        
        Args:
            prediction: 模型预测得分
            actual_result: 实际结果（True=盈利, False=亏损）
        """
        self.recent_predictions.append({
            'prediction': prediction,
            'actual': actual_result,
            'timestamp': time.time()
        })
        
        # 只保留最近50次预测
        if len(self.recent_predictions) > 50:
            self.recent_predictions = self.recent_predictions[-50:]
        
        # 计算最近胜率
        if len(self.recent_predictions) >= 10:
            recent = self.recent_predictions[-10:]
            win_rate = sum(1 for p in recent if p['actual']) / len(recent)
            
            # 根据胜率调整阈值
            if win_rate > 0.6:
                # 胜率高，可以提高阈值（更严格）
                self.current_threshold = min(
                    self.current_threshold + self.adjustment_step,
                    self.max_threshold
                )
            elif win_rate < 0.4:
                # 胜率低，降低阈值（更宽松）
                self.current_threshold = max(
                    self.current_threshold - self.adjustment_step,
                    self.min_threshold
                )
    
    def get_threshold(self) -> float:
        """获取当前阈值"""
        return self.current_threshold
    
    def reset(self):
        """重置阈值"""
        self.current_threshold = self.base_threshold
        self.recent_predictions.clear()


# 测试代码
if __name__ == "__main__":
    print("="*70)
    print("模型预热模块测试")
    print("="*70)
    
    # 测试预热策略
    config = WarmUpConfig(warm_up_periods=20)
    warm_up = ModelWarmUpStrategy(config)
    
    print("\n模拟预热过程:")
    for i in range(25):
        threshold = warm_up.get_buy_threshold()
        lr = warm_up.get_learning_rate()
        
        # 模拟交易
        profit = 1.0 if i % 3 == 0 else -0.5
        warm_up.update(profit)
        
        if i % 5 == 0:
            print(f"  帧{i:2d}: 阈值={threshold:.3f}, 学习率={lr:.3f}, "
                  f"{'预热中' if not warm_up.is_warm_up_complete else '已完成'}")
    
    print("\n" + "="*70)
    print("测试完成!")
    print("="*70)
