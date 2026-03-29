"""
板块轮动捕捉策略

利用注意力系统的板块注意力权重，捕捉资金在板块间的轮动
"""

import time
import numpy as np
from typing import Dict, List, Optional, Any
from collections import deque

from .base import AttentionStrategyBase, Signal


def _get_noise_detector():
    """延迟导入避免循环依赖"""
    try:
        from deva.naja.attention.processing.sector_noise_detector import get_sector_noise_detector
        return get_sector_noise_detector()
    except ImportError:
        return None


class SectorRotationHunter(AttentionStrategyBase):
    """
    板块轮动捕捉策略
    
    核心逻辑：
    1. 监控板块注意力权重的变化
    2. 当某个板块权重快速上升时，标记为"资金流入"
    3. 当板块权重下降时，标记为"资金流出"
    4. 捕捉板块轮动的转折点
    
    只在板块注意力活跃的时段执行
    """
    
    def __init__(
        self,
        momentum_threshold: float = 0.15,  # 动量阈值
        rotation_threshold: float = 0.3,   # 轮动阈值
        min_sector_attention: float = 0.4,  # 最低板块注意力
        history_window: int = 20,          # 历史窗口
        cooldown_period: float = 300.0     # 5分钟冷却期
    ):
        super().__init__(
            strategy_id="sector_rotation_hunter",
            name="Sector Rotation Hunter",
            scope='sector',
            min_global_attention=0.3,  # 需要一定全局注意力
            cooldown_period=cooldown_period
        )
        
        self.momentum_threshold = momentum_threshold
        self.rotation_threshold = rotation_threshold
        self.min_sector_attention = min_sector_attention
        self.history_window = history_window
        
        # 板块历史数据
        self.sector_history: Dict[str, deque] = {}
        self.sector_momentum: Dict[str, float] = {}
        self.sector_signals: Dict[str, str] = {}  # 'watching_inflow' | 'watching_outflow' | 'stable'
        
        # 轮动状态
        self.current_hot_sectors: List[str] = []
        self.last_rotation_time: float = 0.0
        
    def _on_signal(self, signal: Signal):
        """处理信号"""
        print(f"📊 [{signal.strategy_name}] {signal.signal_type.upper()} | "
              f"板块: {signal.symbol} | 置信度: {signal.confidence:.2f} | "
              f"原因: {signal.reason}")
    
    def _update_sector_history(self, sector_weights: Dict[str, float]):
        """更新板块历史数据"""
        current_time = self._get_market_time()
        
        for sector, weight in sector_weights.items():
            if sector not in self.sector_history:
                self.sector_history[sector] = deque(maxlen=self.history_window)
            
            self.sector_history[sector].append({
                'time': current_time,
                'weight': weight
            })
    
    def _calculate_sector_momentum(self, sector: str) -> float:
        """计算板块动量"""
        if sector not in self.sector_history:
            return 0.0
        
        history = list(self.sector_history[sector])
        if len(history) < 5:
            return 0.0
        
        # 计算权重变化率
        recent = np.mean([h['weight'] for h in history[-3:]])
        previous = np.mean([h['weight'] for h in history[:min(5, len(history))]])
        
        if previous == 0:
            return 0.0
        
        momentum = (recent - previous) / previous
        return momentum
    
    def _detect_rotation(self, sector_weights: Dict[str, float]) -> List[Signal]:
        """检测板块轮动"""
        signals = []
        current_time = self._get_market_time()
        noise_detector = _get_noise_detector()

        for sector, weight in sector_weights.items():
            if noise_detector and noise_detector.is_noise(sector):
                continue

            if weight < self.min_sector_attention:
                continue

            momentum = self._calculate_sector_momentum(sector)
            self.sector_momentum[sector] = momentum

            if momentum > self.momentum_threshold:
                if self._is_rotation_source(sector, sector_weights):
                    if self.can_emit_signal(sector):
                        signal = Signal(
                            strategy_name=self.name,
                            symbol=sector,
                            signal_type='watch',
                            confidence=min(abs(momentum) * 2, 1.0),
                            score=momentum,
                            reason=f"板块轮动资金流入，动量: {momentum:.3f}, 权重: {weight:.3f}",
                            timestamp=current_time,
                            metadata={
                                'momentum': momentum,
                                'weight': weight,
                                'rotation_type': 'inflow'
                            }
                        )
                        self.emit_signal(signal)
                        signals.append(signal)
                        self.sector_signals[sector] = 'watching_inflow'

            elif momentum < -self.momentum_threshold:
                if self.can_emit_signal(f"{sector}_out"):
                    signal = Signal(
                        strategy_name=self.name,
                        symbol=sector,
                        signal_type='watch',
                        confidence=min(abs(momentum) * 2, 1.0),
                        score=momentum,
                        reason=f"板块轮动资金流出，动量: {momentum:.3f}, 权重: {weight:.3f}",
                        timestamp=current_time,
                        metadata={
                            'momentum': momentum,
                            'weight': weight,
                            'rotation_type': 'outflow'
                        }
                    )
                    self.emit_signal(signal)
                    signals.append(signal)
                    self.sector_signals[sector] = 'watching_outflow'
        
        return signals
    
    def _is_rotation_source(self, target_sector: str, sector_weights: Dict[str, float]) -> bool:
        """判断是否是轮动目标（有资金从其他板块流出）"""
        # 检查是否有其他板块在流出
        outflow_sectors = [
            sector for sector, momentum in self.sector_momentum.items()
            if momentum < -self.momentum_threshold * 0.5 and sector != target_sector
        ]
        
        return len(outflow_sectors) > 0
    
    def _identify_hot_sectors(self, sector_weights: Dict[str, float]) -> List[str]:
        """识别热点板块"""
        hot_sectors = []
        noise_detector = _get_noise_detector()

        for sector, weight in sector_weights.items():
            if noise_detector and noise_detector.is_noise(sector):
                continue

            momentum = self.sector_momentum.get(sector, 0.0)

            if weight > self.min_sector_attention and momentum > 0:
                hot_sectors.append({
                    'sector': sector,
                    'weight': weight,
                    'momentum': momentum,
                    'score': weight * (1 + momentum)
                })

        hot_sectors.sort(key=lambda x: x['score'], reverse=True)

        return [h['sector'] for h in hot_sectors[:5]]
    
    def analyze(self, data, context: Dict[str, Any]) -> List[Signal]:
        """
        分析板块数据
        
        Args:
            data: 板块数据（包含各板块的股票）
            context: 上下文，包含板块注意力权重
        """
        signals = []
        current_time = self._get_market_time()
        
        # 从上下文获取板块权重
        sector_weights = context.get('sector_weights', {})
        
        if not sector_weights:
            # 从注意力系统获取
            integration = self._get_attention_system()
            if integration and integration.attention_system:
                sector_weights = integration.attention_system.sector_attention.get_all_weights()
        
        if not sector_weights:
            return signals
        
        # 更新历史
        self._update_sector_history(sector_weights)
        
        # 检测轮动
        rotation_signals = self._detect_rotation(sector_weights)
        signals.extend(rotation_signals)
        
        # 更新热点板块
        self.current_hot_sectors = self._identify_hot_sectors(sector_weights)
        
        # 如果检测到轮动，记录时间
        if rotation_signals:
            self.last_rotation_time = current_time
        
        return signals
    
    def get_sector_analysis(self) -> Dict[str, Any]:
        """获取板块分析结果"""
        return {
            'hot_sectors': self.current_hot_sectors,
            'sector_momentum': self.sector_momentum.copy(),
            'sector_signals': self.sector_signals.copy(),
            'last_rotation_time': self.last_rotation_time,
            'history_length': {s: len(h) for s, h in self.sector_history.items()}
        }
