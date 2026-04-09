"""
全局市场状态监控策略 (Global Market Sentinel)

功能：
1. 监控整体市场风险状态
2. 在极端行情时发出预警
3. 控制其他策略的激进程度

特点：
- 全局策略，处理全市场数据
- 只在市场异常时激活
- 输出风险等级信号
"""

import time
import numpy as np
from typing import Dict, List, Any
from collections import deque

try:
    import pandas as pd
except Exception:
    pd = None

from .base import HotspotStrategyBase, Signal


class GlobalMarketSentinel(HotspotStrategyBase):
    """
    全局市场状态监控策略
    
    类似市场的"体温计"，监测整体健康状态
    """
    
    def __init__(
        self,
        strategy_id: str = "global_sentinel",
        volatility_threshold: float = 3.0,  # 波动率阈值(%)
        panic_threshold: float = 5.0,       # 恐慌阈值(%)
        history_window: int = 20
    ):
        super().__init__(
            strategy_id=strategy_id,
            name="Global Market Sentinel",
            scope='global',
            min_global_hotspot=0.0,  # 始终运行，监控市场
            max_positions=0  # 不产生交易信号，只产生风险信号
        )
        
        self.volatility_threshold = volatility_threshold
        self.panic_threshold = panic_threshold
        self.history_window = history_window
        
        # 历史状态
        self.volatility_history = deque(maxlen=history_window)
        self.attention_history = deque(maxlen=history_window)
        
        # 风险等级
        self.current_risk_level = 0  # 0-4
        self.risk_levels = {
            0: "Normal",
            1: "Caution", 
            2: "Warning",
            3: "Danger",
            4: "Panic"
        }
        
        # 统计
        self.alert_count = 0
    
    def analyze(self, data: pd.DataFrame, context: Dict[str, Any]) -> List[Signal]:
        """
        分析全市场状态
        
        计算：
        1. 市场波动率
        2. 涨跌分布
        3. 恐慌指数
        4. 综合风险等级
        """
        if pd is None or data is None or data.empty:
            return []
        
        signals = []
        
        # 提取基础数据
        changes = self._get_changes(data)
        if len(changes) == 0:
            return signals
        
        # 计算市场指标
        volatility = np.std(changes)  # 波动率
        mean_change = np.mean(changes)  # 平均涨跌幅
        up_ratio = np.sum(changes > 0) / len(changes)  # 上涨比例
        down_ratio = np.sum(changes < 0) / len(changes)  # 下跌比例
        extreme_down = np.sum(changes < -self.panic_threshold) / len(changes)  # 极端下跌比例
        
        # 更新历史
        self.volatility_history.append(volatility)
        self.attention_history.append(context.get('global_hotspot', 0.5))
        
        # 计算趋势
        volatility_trend = self._calculate_trend(self.volatility_history)
        attention_trend = self._calculate_trend(self.attention_history)
        
        # 计算风险等级
        new_risk_level = self._calculate_risk_level(
            volatility, mean_change, up_ratio, down_ratio, 
            extreme_down, volatility_trend, attention_trend
        )
        
        # 风险等级变化时发出信号
        if new_risk_level != self.current_risk_level:
            self.current_risk_level = new_risk_level
            
            if new_risk_level >= 2:  # Warning及以上
                signal = Signal(
                    strategy_name=self.name,
                    symbol="MARKET",
                    signal_type="risk_alert",
                    confidence=min(new_risk_level / 4.0, 1.0),
                    score=new_risk_level,
                    reason=f"Risk Level {new_risk_level}: {self.risk_levels[new_risk_level]}",
                    timestamp=self._get_market_time(),
                    metadata={
                        'volatility': volatility,
                        'mean_change': mean_change,
                        'up_ratio': up_ratio,
                        'down_ratio': down_ratio,
                        'extreme_down': extreme_down,
                        'global_hotspot': context.get('global_hotspot', 0.5)
                    }
                )
                signals.append(signal)
                self.alert_count += 1
        
        # 定期输出状态报告（每10帧）
        if self.execution_count % 10 == 0:
            self._print_status_report(
                volatility, mean_change, up_ratio, down_ratio,
                extreme_down, context.get('global_hotspot', 0.5)
            )
        
        return signals
    
    def _get_changes(self, data: pd.DataFrame) -> np.ndarray:
        """获取涨跌幅数据"""
        if 'p_change' in data.columns:
            return pd.to_numeric(data['p_change'], errors='coerce').dropna().values
        elif 'now' in data.columns and 'close' in data.columns:
            now = pd.to_numeric(data['now'], errors='coerce')
            close = pd.to_numeric(data['close'], errors='coerce')
            return ((now - close) / close * 100).dropna().values
        else:
            return np.array([])
    
    def _calculate_trend(self, history: deque) -> float:
        """计算趋势（-1到1）"""
        if len(history) < 5:
            return 0.0
        
        recent = list(history)[-5:]
        if len(recent) < 2:
            return 0.0
        
        # 简单线性回归斜率
        x = np.arange(len(recent))
        y = np.array(recent)
        slope = np.polyfit(x, y, 1)[0] if len(x) > 1 else 0
        
        # 归一化到-1到1
        return np.clip(slope / (np.mean(y) + 1e-6), -1, 1)
    
    def _calculate_risk_level(
        self,
        volatility: float,
        mean_change: float,
        up_ratio: float,
        down_ratio: float,
        extreme_down: float,
        volatility_trend: float,
        attention_trend: float
    ) -> int:
        """计算风险等级 0-4"""
        risk_score = 0
        
        # 波动率评分
        if volatility > self.panic_threshold:
            risk_score += 2
        elif volatility > self.volatility_threshold:
            risk_score += 1
        
        # 极端下跌评分
        if extreme_down > 0.1:  # 超过10%股票极端下跌
            risk_score += 2
        elif extreme_down > 0.05:
            risk_score += 1
        
        # 涨跌失衡评分
        if up_ratio < 0.2 or down_ratio > 0.7:
            risk_score += 1
        
        # 趋势恶化评分
        if volatility_trend > 0.3:  # 波动率在上升
            risk_score += 1
        
        return min(risk_score, 4)
    
    def _print_status_report(
        self,
        volatility: float,
        mean_change: float,
        up_ratio: float,
        down_ratio: float,
        extreme_down: float,
        global_hotspot: float
    ):
        """打印状态报告"""
        risk_name = self.risk_levels.get(self.current_risk_level, "Unknown")
        risk_emoji = ["🟢", "🟡", "🟠", "🔴", "⚫"][self.current_risk_level]
        
        print(f"\n{'='*60}")
        print(f"{risk_emoji} 市场状态监控报告")
        print(f"{'='*60}")
        print(f"风险等级: {self.current_risk_level} ({risk_name})")
        print(f"波动率: {volatility:.2f}%")
        print(f"平均涨跌: {mean_change:+.2f}%")
        print(f"上涨比例: {up_ratio:.1%}")
        print(f"下跌比例: {down_ratio:.1%}")
        print(f"极端下跌: {extreme_down:.1%}")
        print(f"全局注意力: {global_hotspot:.2f}")
        print(f"执行次数: {self.execution_count}")
        print(f"预警次数: {self.alert_count}")
        print(f"{'='*60}\n")
    
    def _on_signal(self, signal: Signal):
        """处理信号"""
        risk_emoji = ["🟢", "🟡", "🟠", "🔴", "⚫"][int(signal.score)]
        print(f"\n{risk_emoji} [{self.name}] 风险预警")
        print(f"   等级: {signal.reason}")
        print(f"   波动率: {signal.metadata.get('volatility', 0):.2f}%")
        print(f"   极端下跌: {signal.metadata.get('extreme_down', 0):.1%}")
        print(f"   建议: {self._get_advice(int(signal.score))}")
    
    def _get_advice(self, risk_level: int) -> str:
        """获取建议"""
        advice = {
            0: "正常交易",
            1: "保持警惕，控制仓位",
            2: "减仓观望，收紧止损",
            3: "大幅减仓，以现金为主",
            4: "清仓避险，等待机会"
        }
        return advice.get(risk_level, "观望")
    
    def get_risk_level(self) -> int:
        """获取当前风险等级"""
        return self.current_risk_level
    
    def is_market_safe(self) -> bool:
        """判断市场是否安全"""
        return self.current_risk_level <= 1
