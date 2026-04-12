"""
热点策略基类

所有基于热点的策略都继承此类
"""

import sys
import time
import numpy as np
import logging
from typing import Dict, List, Optional, Any, Callable
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from collections import deque
from deva.naja.register import SR

try:
    import pandas as pd
except Exception:
    pd = None

try:
    from deva.naja.infra.observability.performance_monitor import record_component_execution, ComponentType
    _PERFORMANCE_MONITORING_AVAILABLE = True
except ImportError:
    _PERFORMANCE_MONITORING_AVAILABLE = False

log = logging.getLogger(__name__)


@dataclass
class Signal:
    """交易信号"""
    strategy_name: str
    symbol: str
    signal_type: str  # 'buy' | 'sell' | 'hold' | 'watch'
    confidence: float  # 0.0 - 1.0
    score: float
    reason: str
    timestamp: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'strategy': self.strategy_name,
            'symbol': self.symbol,
            'type': self.signal_type,
            'confidence': self.confidence,
            'score': self.score,
            'reason': self.reason,
            'timestamp': self.timestamp,
            'metadata': self.metadata
        }


class HotspotStrategyBase(ABC):
    """
    热点策略基类
    
    核心特性：
    1. 自动接入热点系统
    2. 根据热点动态调整执行频率
    3. 只在值得计算的时候计算
    """
    
    def __init__(
        self,
        strategy_id: str,
        name: str,
        scope: str = 'symbol',  # 'global' | 'block' | 'symbol'
        market_scope: str = 'CN',  # 'CN' | 'US' | 'ALL'
        min_global_hotspot: float = 0.0,
        min_symbol_weight: float = 1.0,
        max_positions: int = 10,
        cooldown_period: float = 60.0  # 信号冷却期（秒）
    ):
        self.strategy_id = strategy_id
        self.name = name
        self.scope = scope
        self.market_scope = market_scope
        
        # 热点阈值
        self.min_global_hotspot = min_global_hotspot
        self.min_symbol_weight = min_symbol_weight
        
        # 执行控制
        self.max_positions = max_positions
        self.cooldown_period = cooldown_period
        
        # 状态
        self.is_active = False
        self.last_execution_time = 0.0
        self.execution_count = 0
        self.skip_count = 0
        
        # 持仓和信号
        self.positions: Dict[str, Dict] = {}
        self.signals: deque = deque(maxlen=100)
        self.last_signal_time: Dict[str, float] = {}
        
        # 性能统计
        self.total_processing_time = 0.0
        self.total_stocks_processed = 0
        
        # 缓存热点系统引用
        self._hotspot_integration = None
        self._orchestrator = None

    def _get_market_time(self) -> float:
        """获取当前市场时间（回放模式返回市场时间，否则返回系统时间）"""
        try:
            return SR('market_time_service').get_market_time()
        except Exception:
            return time.time()

    def _get_hotspot_integration(self):
        """获取热点系统集成器"""
        if self._hotspot_integration is None:
            try:
                from deva.naja.market_hotspot.integration import get_market_hotspot_integration
                self._hotspot_integration = get_market_hotspot_integration()
            except Exception:
                pass
        return self._hotspot_integration

    def _get_orchestrator(self):
        """获取调度中心（兼容旧接口）"""
        if self._orchestrator is None:
            try:
                from deva.naja.attention.orchestration.trading_center import get_trading_center
                self._orchestrator = get_trading_center()
            except Exception:
                pass
        return self._orchestrator
    
    def should_execute(
        self,
        global_hotspot: Optional[float] = None,
        activity: Optional[float] = None,
        market_timestamp: Optional[float] = None
    ) -> bool:
        """
        判断是否应该执行策略

        分离"热点"和"活跃度"：
        - 热点: 用于展示市场焦点在哪
        - 活跃度: 用于决定是否交易（活跃度低就不交易）

        Args:
            global_hotspot: 全局热点分数（用于展示）
            activity: 市场活跃度分数（用于交易门槛）
            market_timestamp: 市场时间戳（用于历史回放时正确计算冷却间隔）
        """
        # 使用市场时间（如果有），否则用真实时间
        current_time = market_timestamp if market_timestamp is not None else time.time()

        # 获取热点（始终从系统获取）
        if global_hotspot is None:
            integration = self._get_hotspot_integration()
            if integration and integration.hotspot_system:
                global_hotspot = integration.hotspot_system._last_global_hotspot
            else:
                global_hotspot = 0.5

        # 获取活跃度
        if activity is None:
            integration = self._get_hotspot_integration()
            if integration and integration.hotspot_system:
                activity = getattr(integration.hotspot_system, '_last_activity', 0.5)
            else:
                activity = 0.5

        # 热点展示总是进行（只是记录）
        # 活跃度低于阈值 -> 不交易
        if activity < 0.15:
            self.skip_count += 1
            return False

        # 检查冷却期（使用市场时间计算）
        if current_time - self.last_execution_time < self._get_dynamic_interval(global_hotspot):
            log.debug(f"[{self.name}] skip: cooling down, last_exec={self.last_execution_time}, interval={self._get_dynamic_interval(global_hotspot)}, global_hotspot={global_hotspot}")
            return False

        return True
    
    def _get_dynamic_interval(self, global_hotspot: float) -> float:
        """
        根据全局热点动态调整执行间隔
        
        热点高 -> 间隔短（更频繁）
        热点低 -> 间隔长（更稀疏）
        """
        # 基础间隔
        base_interval = 5.0  # 5秒
        
        # 根据热点调整
        # global_hotspot 0.0 -> 5倍间隔（25秒）
        # global_hotspot 1.0 -> 0.2倍间隔（1秒）
        factor = 5.0 - global_hotspot * 4.8
        
        return base_interval * factor
    
    def filter_by_hotspot(self, df: pd.DataFrame, min_weight: Optional[float] = None) -> pd.DataFrame:
        """
        根据热点权重筛选股票
        
        这是核心方法，只保留高热点的股票
        """
        if pd is None or df is None or df.empty:
            return df
        
        min_weight = min_weight or self.min_symbol_weight
        
        integration = self._get_hotspot_integration()
        if not integration or not integration.hotspot_system:
            return df
        
        # 获取高热点股票
        high_hotspot = integration.get_high_hotspot_symbols(threshold=min_weight)

        if not high_hotspot:
            return df

        # 筛选
        code_column = 'code' if 'code' in df.columns else df.index.name
        if code_column == 'code':
            return df[df['code'].isin(high_hotspot)]
        else:
            return df[df.index.isin(high_hotspot)]
    
    def get_symbol_weight(self, symbol: str) -> float:
        """获取个股权重"""
        integration = self._get_hotspot_integration()
        if not integration or not integration.hotspot_system:
            return 1.0
        
        return integration.hotspot_system.weight_pool.get_symbol_weight(symbol)
    
    def get_global_hotspot(self) -> float:
        """获取全局热点"""
        integration = self._get_hotspot_integration()
        if not integration or not integration.hotspot_system:
            return 0.5
        
        return integration.hotspot_system._last_global_hotspot
    
    def get_active_blocks(self, threshold: float = 0.3) -> List[str]:
        """获取活跃题材"""
        integration = self._get_hotspot_integration()
        if not integration:
            return []

        return integration.get_active_blocks(threshold)
    
    def can_emit_signal(self, symbol: str) -> bool:
        """检查是否可以发送信号（冷却期检查）"""
        current_time = time.time()
        last_time = self.last_signal_time.get(symbol, 0)
        
        return current_time - last_time >= self.cooldown_period
    
    def emit_signal(self, signal: Signal):
        """发送信号"""
        self.signals.append(signal)
        self.last_signal_time[signal.symbol] = signal.timestamp
        
        # 输出信号
        self._on_signal(signal)
        
        # 对接到 Bandit 系统和信号流
        self._forward_signal_to_bandit(signal)
        self._forward_signal_to_stream(signal)
    
    def _forward_signal_to_bandit(self, signal: Signal):
        """
        将信号转发到 Bandit 系统
        
        Bandit 会监听这些信号并创建虚拟持仓
        
        同时启动 HotspotTracker 跟踪:
        - 只要热点系统识别到内容，就开始跟踪价格变化
        - 不需要实际成交
        - 形成持续的学习反馈
        """
        try:
            # 只转发 buy/sell 信号
            if signal.signal_type not in ('buy', 'sell'):
                return
            
            # 获取信号流
            from deva.naja.signal.stream import get_signal_stream
            from deva.naja.strategy.result_store import StrategyResult
            
            stream = get_signal_stream()
            
            # 创建 StrategyResult 对象
            result = StrategyResult(
                id=f"{self.strategy_id}_{signal.symbol}_{int(signal.timestamp*1000)}",
                strategy_id=self.strategy_id,
                strategy_name=self.name,
                ts=signal.timestamp,
                success=True,
                input_preview=f"{signal.symbol}: {signal.signal_type}",
                output_preview=f"置信度: {signal.confidence:.2f}, 得分: {signal.score:.3f}",
                output_full={
                    'symbol': signal.symbol,
                    'signal_type': signal.signal_type,
                    'confidence': signal.confidence,
                    'score': signal.score,
                    'reason': signal.reason,
                    'metadata': signal.metadata
                },
                process_time_ms=0,
                error="",
                metadata={
                    'source': 'hotspot_strategy',
                    'scope': self.scope,
                    'signal_type': signal.signal_type,
                    'confidence': signal.confidence
                }
            )
            
            # 发送到信号流
            stream.update(result)

            # 记录信号到 SignalTuner
            try:
                tuner = SR('signal_tuner')
                if tuner:
                    price = 0.0
                    if signal.metadata:
                        price = float(signal.metadata.get('price', signal.metadata.get('current', 0)))
                    tuner.record_signal(
                        symbol=signal.symbol,
                        strategy_id=self.strategy_id,
                        signal_type=signal.signal_type,
                        confidence=signal.confidence,
                        score=signal.score,
                        price=price,
                        params_snapshot={self.strategy_id: {
                            'price_threshold': getattr(self, 'price_threshold', 0.03),
                            'volume_threshold': getattr(self, 'volume_threshold', 2.0),
                            'combined_threshold': getattr(self, 'combined_threshold', 0.5),
                        }}
                    )
                    log.info(f"[SignalTuner] 📡 记录信号: {signal.signal_type} {signal.symbol} @{price:.2f} 置信度={signal.confidence:.2f}")
            except Exception as te:
                log.debug(f"[SignalTuner] 信号记录失败: {te}")

            # 启动 HotspotTracker 跟踪
            # 这是用户新思路的核心: 不需要成交，只要热点选中就开始跟踪
            self._track_hotspot_signal(signal)
            
        except Exception as e:
            # 转发失败不影响策略执行
            pass
    
    def _track_hotspot_signal(self, signal: Signal):
        """
        启动 HotspotTracker 跟踪热点信号

        实现用户思路:
        - 只要热点系统识别到内容，就去关注它的价格变化
        - 形成持续的反馈学习
        - 回放模式下也会创建跟踪，由 PositionMonitor 后续更新价格
        """
        try:

            tracker = SR('hotspot_signal_tracker')

            price = 0.0
            if signal.metadata:
                price = float(signal.metadata.get('price', signal.metadata.get('current', 0)))

            block_id = signal.metadata.get('block_id', '') if signal.metadata else ''

            # 如果价格为空，先尝试从实时行情获取
            if price <= 0:
                try:
                    from deva import NB
                    db = NB("naja_realtime_quotes")
                    quote = db.get(signal.symbol)
                    if isinstance(quote, dict):
                        price = float(quote.get('price', quote.get('now', quote.get('current', 0))))
                except Exception:
                    pass

            # 即使价格为空也创建跟踪，让 PositionMonitor 后续更新
            # 回放模式下 PositionMonitor 会收到 tick 数据并更新价格
            tracker.track_hotspot(
                symbol=signal.symbol,
                block_id=block_id,
                strategy_id=self.strategy_id,
                strategy_name=self.name,
                hotspot_score=signal.score,
                prediction_score=signal.confidence,
                action=signal.signal_type.upper(),
                entry_price=price,
                market_state=signal.metadata.get('market_state', 'unknown') if signal.metadata else 'unknown',
            )

        except Exception as e:
            # 跟踪失败不影响策略执行
            pass
    
    def _forward_signal_to_stream(self, signal: Signal):
        """
        将信号转发到信号流系统
        
        这样可以在 Web UI 的信号流页面查看
        """
        try:
            from deva.naja.signal.stream import get_signal_stream
            from deva.naja.strategy.result_store import StrategyResult
            
            stream = get_signal_stream()
            
            # 创建 StrategyResult
            result = StrategyResult(
                id=f"hotspot_{self.strategy_id}_{int(time.time()*1000)}",
                strategy_id=self.strategy_id,
                strategy_name=f"[热点] {self.name}",
                ts=signal.timestamp,
                success=True,
                input_preview=f"股票: {signal.symbol}",
                output_preview=f"{signal.signal_type.upper()} | 置信度: {signal.confidence:.2f}",
                output_full=signal.to_dict(),
                process_time_ms=0,
                error="",
                metadata={
                    'hotspot_signal': True,
                    'scope': self.scope,
                    'symbol': signal.symbol,
                    'signal_type': signal.signal_type
                }
            )
            
            # 更新信号流
            stream.update(result)
            
        except Exception as e:
            # 转发失败不影响策略执行
            pass
    
    @abstractmethod
    def _on_signal(self, signal: Signal):
        """子类实现信号处理"""
        pass
    
    @abstractmethod
    def analyze(self, data: pd.DataFrame, context: Dict[str, Any]) -> List[Signal]:
        """
        分析数据并生成信号
        
        Args:
            data: 市场数据
            context: 热点上下文
            
        Returns:
            信号列表
        """
        pass
    
    def process(self, data: pd.DataFrame, context: Optional[Dict[str, Any]] = None) -> List[Signal]:
        """
        处理数据的主入口

        包含执行控制、性能统计等
        """
        start_time = time.time()

        # 获取上下文
        if context is None:
            context = {
                'global_hotspot': self.get_global_hotspot(),
                'timestamp': start_time
            }

        global_hotspot = context.get('global_hotspot', 0.5)
        activity = context.get('activity', 0.5)
        market_timestamp = context.get('timestamp', start_time)

        # 检查是否应该执行（使用市场时间计算冷却间隔）
        # 活跃度低于阈值就不交易，但热点始终展示
        if not self.should_execute(global_hotspot, activity, market_timestamp):
            return []

        # 使用市场时间更新执行时间（确保历史回放时冷却计算正确）
        self.last_execution_time = market_timestamp
        self.execution_count += 1

        # 根据策略类型过滤数据
        if self.scope == 'symbol':
            # 个股策略：只处理高热点股票
            data = self.filter_by_hotspot(data)
        elif self.scope == 'block':
            # 题材策略：数据已经由调度中心过滤
            pass
        # global策略：处理全量数据

        if data is None or data.empty:
            return []

        # 执行分析
        analyze_start = time.time()
        signals = self.analyze(data, context)
        analyze_elapsed = (time.time() - analyze_start) * 1000  # ms

        # 更新统计
        elapsed = time.time() - start_time
        self.total_processing_time += elapsed
        self.total_stocks_processed += len(data)

        # 记录性能监控
        if _PERFORMANCE_MONITORING_AVAILABLE:
            record_component_execution(
                component_id=f"hotspot_strategy_analyze_{self.strategy_id}",
                component_name=f"策略分析: {self.name}",
                component_type=ComponentType.STRATEGY,
                execution_time_ms=analyze_elapsed,
                success=True,
                expected_interval_ms=self._get_dynamic_interval(global_hotspot) * 1000,
            )

        return signals
    
    def get_stats(self) -> Dict[str, Any]:
        """获取策略统计"""
        avg_time = self.total_processing_time / max(self.execution_count, 1)
        
        return {
            'strategy_id': self.strategy_id,
            'name': self.name,
            'scope': self.scope,
            'execution_count': self.execution_count,
            'skip_count': self.skip_count,
            'signal_count': len(self.signals),
            'avg_processing_time_ms': avg_time * 1000,
            'total_stocks_processed': self.total_stocks_processed,
            'is_active': self.is_active
        }
    
    def activate(self):
        """激活策略"""
        self.is_active = True
        log.info(f"✅ 策略 {self.name} 已激活")

    def deactivate(self):
        """停用策略"""
        self.is_active = False
        log.info(f"⏸️ 策略 {self.name} 已停用")
    
    def reset(self):
        """重置策略状态"""
        self.positions.clear()
        self.signals.clear()
        self.last_signal_time.clear()
        self.execution_count = 0
        self.skip_count = 0
        self.total_processing_time = 0.0
        self.total_stocks_processed = 0
