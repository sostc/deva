"""
异常模式狙击策略

结合 River 的在线异常检测和 PyTorch 的模式识别
只在高热点时段激活 PyTorch 引擎进行深度分析
"""

import time
import numpy as np
from typing import Dict, List, Optional, Any
from collections import deque

from .base import HotspotStrategyBase, Signal


class AnomalyPatternSniper(HotspotStrategyBase):
    """
    异常模式狙击策略
    
    核心逻辑（双引擎架构）：
    1. River Engine（轻量级，始终运行）：
       - 实时计算统计异常值（Z-score, IQR）
       - 检测价格/成交量的统计异常
       - 计算基础特征（波动率、换手率等）
    
    2. PyTorch Engine（重量级，按需激活）：
       - 当全局热点 > 0.6 时激活
       - 使用深度学习模型识别复杂模式
       - 识别"假突破"、"洗盘"等复杂形态
    
    3. 信号生成：
       - River 检测到异常 + PyTorch 确认模式 = 高置信度信号
       - 只在高热点时段全力运行
    """
    
    def __init__(
        self,
        zscore_threshold: float = 2.5,         # Z-score异常阈值
        volume_spike_threshold: float = 3.0,   # 成交量突增阈值
        pattern_confidence_threshold: float = 0.75,  # 模式识别置信度阈值
        pytorch_activation_threshold: float = 0.6,   # PyTorch激活阈值
        min_symbol_weight: float = 3.0,        # 最低个股权重
        cooldown_period: float = 300.0         # 5分钟冷却期
    ):
        super().__init__(
            strategy_id="anomaly_pattern_sniper",
            name="Anomaly Pattern Sniper",
            scope='symbol',
            min_global_hotspot=0.3,  # 需要一定全局热点
            min_symbol_weight=min_symbol_weight,
            max_positions=10,
            cooldown_period=cooldown_period
        )
        
        self.zscore_threshold = zscore_threshold
        self.volume_spike_threshold = volume_spike_threshold
        self.pattern_confidence_threshold = pattern_confidence_threshold
        self.pytorch_activation_threshold = pytorch_activation_threshold
        
        # River Engine 状态
        self.price_stats: Dict[str, Dict] = {}  # 价格统计
        self.volume_stats: Dict[str, Dict] = {}  # 成交量统计
        self.anomaly_history: Dict[str, deque] = {}  # 异常历史
        
        # PyTorch Engine 状态
        self.pytorch_active: bool = False
        self.pattern_cache: Dict[str, Any] = {}  # 模式缓存
        
        # 检测到的异常
        self.detected_anomalies: List[Dict] = []
        
    def _on_signal(self, signal: Signal):
        """处理信号"""
        emoji = "🎯" if signal.signal_type == 'buy' else "⚠️"
        print(f"{emoji} [{signal.strategy_name}] {signal.signal_type.upper()} | "
              f"股票: {signal.symbol} | 置信度: {signal.confidence:.2f} | "
              f"原因: {signal.reason}")
    
    def _update_river_stats(self, symbol: str, price: float, volume: float):
        """更新 River 统计（在线学习）"""
        current_time = self._get_market_time()
        
        # 初始化或更新价格统计
        if symbol not in self.price_stats:
            self.price_stats[symbol] = {
                'count': 0,
                'mean': price,
                'm2': 0.0,  # 用于计算方差
                'history': deque(maxlen=50)
            }
        
        stats = self.price_stats[symbol]
        stats['count'] += 1
        stats['history'].append(price)
        
        # Welford 在线均值和方差算法
        delta = price - stats['mean']
        stats['mean'] += delta / stats['count']
        delta2 = price - stats['mean']
        stats['m2'] += delta * delta2
        
        # 初始化或更新成交量统计
        if symbol not in self.volume_stats:
            self.volume_stats[symbol] = {
                'count': 0,
                'mean': volume,
                'm2': 0.0,
                'history': deque(maxlen=30)
            }
        
        vol_stats = self.volume_stats[symbol]
        vol_stats['count'] += 1
        vol_stats['history'].append(volume)
        
        delta = volume - vol_stats['mean']
        vol_stats['mean'] += delta / vol_stats['count']
        delta2 = volume - vol_stats['mean']
        vol_stats['m2'] += delta * delta2
    
    def _calculate_zscore(self, symbol: str, price: float) -> float:
        """计算价格 Z-score"""
        if symbol not in self.price_stats:
            return 0.0
        
        stats = self.price_stats[symbol]
        if stats['count'] < 10:
            return 0.0
        
        variance = stats['m2'] / stats['count']
        std = np.sqrt(variance) if variance > 0 else 1.0
        
        return (price - stats['mean']) / std if std > 0 else 0.0
    
    def _detect_volume_spike(self, symbol: str, volume: float) -> float:
        """检测成交量突增"""
        if symbol not in self.volume_stats:
            return 1.0
        
        stats = self.volume_stats[symbol]
        if stats['count'] < 10:
            return 1.0
        
        mean_volume = stats['mean']
        if mean_volume == 0:
            return 1.0
        
        return volume / mean_volume
    
    def _river_anomaly_detection(self, symbol: str, price: float, volume: float) -> Dict[str, Any]:
        """
        River Engine: 轻量级异常检测
        
        Returns:
            异常检测结果
        """
        # 更新统计
        self._update_river_stats(symbol, price, volume)
        
        # 计算 Z-score
        price_zscore = self._calculate_zscore(symbol, price)
        
        # 检测成交量突增
        volume_ratio = self._detect_volume_spike(symbol, volume)
        
        # 判断异常
        is_price_anomaly = abs(price_zscore) > self.zscore_threshold
        is_volume_spike = volume_ratio > self.volume_spike_threshold
        
        # 综合异常得分
        anomaly_score = 0.0
        if is_price_anomaly:
            anomaly_score += 0.5
        if is_volume_spike:
            anomaly_score += 0.5
        
        return {
            'is_anomaly': anomaly_score > 0.5,
            'anomaly_score': anomaly_score,
            'price_zscore': price_zscore,
            'volume_ratio': volume_ratio,
            'is_price_anomaly': is_price_anomaly,
            'is_volume_spike': is_volume_spike
        }
    
    def _pytorch_pattern_recognition(self, symbol: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        PyTorch Engine: 深度模式识别
        
        只在全局热点高时激活
        """
        global_hotspot = context.get('global_hotspot', 0.5)
        
        # 检查是否激活 PyTorch
        if global_hotspot < self.pytorch_activation_threshold:
            return {
                'activated': False,
                'pattern_detected': False,
                'confidence': 0.0,
                'pattern_type': 'none'
            }
        
        # 获取历史数据
        if symbol not in self.price_stats:
            return {
                'activated': True,
                'pattern_detected': False,
                'confidence': 0.0,
                'pattern_type': 'insufficient_data'
            }
        
        prices = list(self.price_stats[symbol]['history'])
        if len(prices) < 20:
            return {
                'activated': True,
                'pattern_detected': False,
                'confidence': 0.0,
                'pattern_type': 'insufficient_data'
            }
        
        # 模拟 PyTorch 模式识别（实际使用时加载训练好的模型）
        # 这里使用简化的启发式规则模拟深度学习模型
        pattern_result = self._simulate_pattern_model(prices)
        
        return {
            'activated': True,
            'pattern_detected': pattern_result['detected'],
            'confidence': pattern_result['confidence'],
            'pattern_type': pattern_result['type']
        }
    
    def _simulate_pattern_model(self, prices: List[float]) -> Dict[str, Any]:
        """
        模拟 PyTorch 模式识别模型
        
        实际使用时替换为真实的深度学习模型推理
        """
        if len(prices) < 10:
            return {'detected': False, 'confidence': 0.0, 'type': 'none'}
        
        # 计算价格特征
        returns = np.diff(prices) / prices[:-1]
        
        # 特征1: 波动率
        volatility = np.std(returns) if len(returns) > 0 else 0
        
        # 特征2: 趋势强度
        trend = (prices[-1] - prices[0]) / prices[0] if prices[0] != 0 else 0
        
        # 特征3: 最近5日动量
        recent_momentum = (prices[-1] - prices[-5]) / prices[-5] if len(prices) >= 5 and prices[-5] != 0 else 0
        
        # 模拟模式识别
        # 突破模式: 高波动 + 强趋势 + 正向动量
        if volatility > 0.02 and trend > 0.03 and recent_momentum > 0.02:
            confidence = min(0.5 + volatility * 10 + trend * 5, 0.95)
            return {
                'detected': True,
                'confidence': confidence,
                'type': 'breakout_confirmed'
            }
        
        # 假突破模式: 高波动 + 趋势反转
        if volatility > 0.025 and trend > 0.02 and recent_momentum < -0.01:
            confidence = min(0.5 + volatility * 8, 0.9)
            return {
                'detected': True,
                'confidence': confidence,
                'type': 'false_breakout'
            }
        
        # 洗盘模式: 极高波动 + 价格回归
        if volatility > 0.04 and abs(trend) < 0.01:
            confidence = min(0.4 + volatility * 10, 0.85)
            return {
                'detected': True,
                'confidence': confidence,
                'type': 'shakeout'
            }
        
        return {
            'detected': False,
            'confidence': 0.0,
            'type': 'no_pattern'
        }
    
    def _analyze_symbol(self, symbol: str, row: Any, context: Dict[str, Any]) -> Optional[Signal]:
        """分析单个股票"""
        current_time = self._get_market_time()
        
        # 提取数据
        price = row.get('close', row.get('price', 0))
        volume = row.get('volume', 0)
        
        if price <= 0 or volume <= 0:
            return None
        
        # Step 1: River Engine 异常检测
        river_result = self._river_anomaly_detection(symbol, price, volume)
        
        # 如果不是异常，跳过
        if not river_result['is_anomaly']:
            return None
        
        # Step 2: PyTorch Engine 模式识别（高热点时）
        pytorch_result = self._pytorch_pattern_recognition(symbol, context)
        
        # 记录异常
        anomaly_record = {
            'time': current_time,
            'symbol': symbol,
            'price': price,
            'volume': volume,
            'river_result': river_result,
            'pytorch_result': pytorch_result
        }
        self.detected_anomalies.append(anomaly_record)
        
        # Step 3: 综合决策
        combined_confidence = river_result['anomaly_score'] * 0.4
        
        if pytorch_result['activated'] and pytorch_result['pattern_detected']:
            combined_confidence += pytorch_result['confidence'] * 0.6
        
        # 生成信号
        if combined_confidence >= self.pattern_confidence_threshold:
            if not self.can_emit_signal(symbol):
                return None
            
            # 根据模式类型决定信号
            pattern_type = pytorch_result.get('pattern_type', 'unknown')
            
            if pattern_type == 'breakout_confirmed':
                signal_type = 'buy'
                reason = f"确认突破 | Z-score: {river_result['price_zscore']:.2f}, 成交量: {river_result['volume_ratio']:.1f}x"
            elif pattern_type == 'false_breakout':
                signal_type = 'sell'
                reason = f"假突破警告 | Z-score: {river_result['price_zscore']:.2f}"
            elif pattern_type == 'shakeout':
                signal_type = 'buy'
                reason = f"洗盘结束信号 | 波动率极高，价格回归"
            else:
                signal_type = 'watch'
                reason = f"异常检测 | Z-score: {river_result['price_zscore']:.2f}"
            
            signal = Signal(
                strategy_name=self.name,
                symbol=symbol,
                signal_type=signal_type,
                confidence=combined_confidence,
                score=river_result['anomaly_score'],
                reason=reason,
                timestamp=current_time,
                metadata={
                    'river_result': river_result,
                    'pytorch_result': pytorch_result,
                    'combined_confidence': combined_confidence,
                    'price': price,
                    'volume': volume
                }
            )
            
            self.emit_signal(signal)
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
        
        # 更新 PyTorch 激活状态
        global_hotspot = context.get('global_hotspot', 0.5)
        self.pytorch_active = global_hotspot >= self.pytorch_activation_threshold
        
        # 遍历数据
        for idx, row in data.iterrows():
            symbol = row.get('code', idx)
            
            signal = self._analyze_symbol(symbol, row, context)
            if signal:
                signals.append(signal)
        
        return signals
    
    def get_anomaly_summary(self) -> Dict[str, Any]:
        """获取异常检测摘要"""
        recent_anomalies = [
            a for a in self.detected_anomalies[-50:]
        ]
        
        return {
            'total_anomalies_detected': len(self.detected_anomalies),
            'recent_anomalies': len(recent_anomalies),
            'pytorch_active': self.pytorch_active,
            'monitored_symbols': len(self.price_stats),
            'last_anomaly': self.detected_anomalies[-1] if self.detected_anomalies else None
        }
