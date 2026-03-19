"""
注意力策略管理器

统一管理所有基于注意力的策略
协调策略与注意力系统的交互
"""

import time
import asyncio
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

from .base import AttentionStrategyBase, Signal

# 性能监控支持
try:
    from deva.naja.performance import record_component_execution, ComponentType
    _PERFORMANCE_MONITORING_AVAILABLE = True
except ImportError:
    _PERFORMANCE_MONITORING_AVAILABLE = False


@dataclass
class StrategyConfig:
    """策略配置"""
    strategy_id: str
    enabled: bool = True
    priority: int = 5  # 1-10, 越高越优先
    custom_params: Dict[str, Any] = field(default_factory=dict)


class AttentionStrategyManager:
    """
    注意力策略管理器
    
    职责：
    1. 管理所有注意力策略的生命周期
    2. 协调策略与注意力系统的交互
    3. 收集和汇总所有策略的信号
    4. 提供统一的策略状态监控
    5. 根据注意力水平动态调整策略执行
    """
    
    def __init__(self):
        self.strategies: Dict[str, AttentionStrategyBase] = {}
        self.configs: Dict[str, StrategyConfig] = {}
        self.all_signals: List[Signal] = []
        self.is_running: bool = False
        
        # 统计
        self.total_signals_generated: int = 0
        self.start_time: Optional[float] = None
        
        # 注意力系统引用
        self._attention_integration = None
        self._orchestrator = None
        
        # 实验模式状态
        self._experiment_mode: bool = False
        self._experiment_datasource_id: Optional[str] = None
        self._experiment_snapshot: Dict[str, Any] = {}
        
    def _get_attention_integration(self):
        """获取注意力系统集成"""
        if self._attention_integration is None:
            try:
                from deva.naja.attention_integration import get_attention_integration
                self._attention_integration = get_attention_integration()
            except Exception as e:
                print(f"⚠️ 无法获取注意力系统集成: {e}")
        return self._attention_integration
    
    def _get_orchestrator(self):
        """获取调度中心"""
        if self._orchestrator is None:
            try:
                from deva.naja.attention_orchestrator import get_orchestrator
                self._orchestrator = get_orchestrator()
            except Exception as e:
                print(f"⚠️ 无法获取调度中心: {e}")
        return self._orchestrator
    
    def register_strategy(
        self,
        strategy: AttentionStrategyBase,
        config: Optional[StrategyConfig] = None
    ) -> bool:
        """
        注册策略
        
        Args:
            strategy: 策略实例
            config: 策略配置
        
        Returns:
            是否注册成功
        """
        if strategy.strategy_id in self.strategies:
            print(f"⚠️ 策略 {strategy.strategy_id} 已存在，跳过注册")
            return False
        
        self.strategies[strategy.strategy_id] = strategy
        
        if config is None:
            config = StrategyConfig(strategy_id=strategy.strategy_id)
        
        self.configs[strategy.strategy_id] = config
        
        print(f"✅ 策略已注册: {strategy.name} (ID: {strategy.strategy_id})")
        return True
    
    def unregister_strategy(self, strategy_id: str) -> bool:
        """注销策略"""
        if strategy_id not in self.strategies:
            return False
        
        strategy = self.strategies[strategy_id]
        strategy.deactivate()
        
        del self.strategies[strategy_id]
        del self.configs[strategy_id]
        
        print(f"🗑️ 策略已注销: {strategy_id}")
        return True
    
    def enable_strategy(self, strategy_id: str) -> bool:
        """启用策略"""
        if strategy_id not in self.configs:
            return False
        
        self.configs[strategy_id].enabled = True
        
        if strategy_id in self.strategies:
            self.strategies[strategy_id].activate()
        
        print(f"▶️ 策略已启用: {strategy_id}")
        return True
    
    def disable_strategy(self, strategy_id: str) -> bool:
        """禁用策略"""
        if strategy_id not in self.configs:
            return False
        
        self.configs[strategy_id].enabled = False
        
        if strategy_id in self.strategies:
            self.strategies[strategy_id].deactivate()
        
        print(f"⏸️ 策略已禁用: {strategy_id}")
        return True
    
    def initialize_default_strategies(self):
        """初始化默认策略集"""
        from .global_sentinel import GlobalMarketSentinel
        from .sector_hunter import SectorRotationHunter
        from .momentum_tracker import MomentumSurgeTracker
        from .anomaly_sniper import AnomalyPatternSniper
        from .smart_money_detector import SmartMoneyFlowDetector
        
        # 全局市场状态监控（始终启用）
        global_sentinel = GlobalMarketSentinel()
        self.register_strategy(global_sentinel, StrategyConfig(
            strategy_id=global_sentinel.strategy_id,
            enabled=True,
            priority=10  # 最高优先级
        ))
        
        # 板块轮动捕捉
        sector_hunter = SectorRotationHunter()
        self.register_strategy(sector_hunter, StrategyConfig(
            strategy_id=sector_hunter.strategy_id,
            enabled=True,
            priority=8
        ))
        
        # 动量突破追踪
        momentum_tracker = MomentumSurgeTracker()
        self.register_strategy(momentum_tracker, StrategyConfig(
            strategy_id=momentum_tracker.strategy_id,
            enabled=True,
            priority=7
        ))
        
        # 异常模式狙击
        anomaly_sniper = AnomalyPatternSniper()
        self.register_strategy(anomaly_sniper, StrategyConfig(
            strategy_id=anomaly_sniper.strategy_id,
            enabled=True,
            priority=6
        ))
        
        # 聪明资金流向检测
        smart_money = SmartMoneyFlowDetector()
        self.register_strategy(smart_money, StrategyConfig(
            strategy_id=smart_money.strategy_id,
            enabled=True,
            priority=7
        ))
        
        print(f"\n✅ 已初始化 {len(self.strategies)} 个默认策略")
    
    def process_data(
        self,
        data: Any,
        context: Optional[Dict[str, Any]] = None
    ) -> List[Signal]:
        """
        处理数据并收集所有策略的信号

        Args:
            data: 市场数据
            context: 注意力上下文

        Returns:
            所有策略生成的信号
        """
        if not self.is_running:
            return []

        start_time = time.time()
        all_signals = []

        # 获取注意力上下文
        if context is None:
            context = self._build_attention_context()

        # 按优先级排序策略
        sorted_strategies = sorted(
            self.strategies.items(),
            key=lambda x: self.configs[x[0]].priority,
            reverse=True
        )

        # 执行每个启用的策略
        for strategy_id, strategy in sorted_strategies:
            config = self.configs.get(strategy_id)
            if not config or not config.enabled:
                continue

            strategy_start = time.time()
            try:
                signals = strategy.process(data, context)
                all_signals.extend(signals)

                # 记录单个策略性能
                if _PERFORMANCE_MONITORING_AVAILABLE:
                    strategy_latency = (time.time() - strategy_start) * 1000
                    record_component_execution(
                        component_id=f"attention_strategy_{strategy_id}",
                        component_name=f"注意力策略: {strategy.name}",
                        component_type=ComponentType.STRATEGY,
                        execution_time_ms=strategy_latency,
                        success=True
                    )
            except Exception as e:
                print(f"❌ 策略 {strategy_id} 执行失败: {e}")
                if _PERFORMANCE_MONITORING_AVAILABLE:
                    strategy_latency = (time.time() - strategy_start) * 1000
                    record_component_execution(
                        component_id=f"attention_strategy_{strategy_id}",
                        component_name=f"注意力策略: {strategy.name}",
                        component_type=ComponentType.STRATEGY,
                        execution_time_ms=strategy_latency,
                        success=False,
                        error=str(e)
                    )

        # 保存信号
        self.all_signals.extend(all_signals)
        self.total_signals_generated += len(all_signals)

        # 记录策略管理器整体性能
        if _PERFORMANCE_MONITORING_AVAILABLE:
            total_latency = (time.time() - start_time) * 1000
            record_component_execution(
                component_id="attention_strategy_manager",
                component_name="注意力策略管理器",
                component_type=ComponentType.STRATEGY,
                execution_time_ms=total_latency,
                success=True
            )

        return all_signals
    
    def _build_attention_context(self) -> Dict[str, Any]:
        """构建注意力上下文"""
        integration = self._get_attention_integration()
        
        context = {
            'timestamp': time.time(),
            'global_attention': 0.5,
            'sector_weights': {},
            'symbol_weights': {}
        }
        
        if integration and integration.attention_system:
            attention_system = integration.attention_system
            
            # 全局注意力
            context['global_attention'] = attention_system._last_global_attention
            
            # 板块权重
            context['sector_weights'] = attention_system.sector_attention.get_all_weights()
            
            # 个股权重
            context['symbol_weights'] = attention_system.weight_pool.get_all_weights()
        
        return context
    
    def start(self):
        """启动策略管理器"""
        if self.is_running:
            print("⚠️ 策略管理器已在运行")
            return
        
        self.is_running = True
        self.start_time = time.time()
        
        # 激活所有启用的策略
        for strategy_id, strategy in self.strategies.items():
            config = self.configs.get(strategy_id)
            if config and config.enabled:
                strategy.activate()
        
        print("\n🚀 注意力策略管理器已启动")
        print(f"   活跃策略数: {sum(1 for c in self.configs.values() if c.enabled)}")
    
    def stop(self):
        """停止策略管理器"""
        if not self.is_running:
            return
        
        self.is_running = False
        
        # 停用所有策略
        for strategy in self.strategies.values():
            strategy.deactivate()
        
        print("\n⏹️ 注意力策略管理器已停止")
    
    def get_all_stats(self) -> Dict[str, Any]:
        """获取所有策略的统计信息"""
        strategy_stats = {}
        
        for strategy_id, strategy in self.strategies.items():
            config = self.configs.get(strategy_id)
            stats = strategy.get_stats()
            stats['enabled'] = config.enabled if config else False
            stats['priority'] = config.priority if config else 5
            strategy_stats[strategy_id] = stats
        
        runtime = time.time() - self.start_time if self.start_time else 0
        
        return {
            'is_running': self.is_running,
            'runtime_seconds': runtime,
            'total_strategies': len(self.strategies),
            'active_strategies': sum(1 for c in self.configs.values() if c.enabled),
            'total_signals_generated': self.total_signals_generated,
            'recent_signals': len(self.all_signals),
            'strategy_stats': strategy_stats
        }
    
    def get_recent_signals(self, n: int = 50) -> List[Signal]:
        """获取最近的信号"""
        return list(self.all_signals)[-n:]
    
    def get_signals_by_strategy(self, strategy_id: str) -> List[Signal]:
        """获取特定策略的信号"""
        return [s for s in self.all_signals if s.strategy_name == strategy_id]
    
    def get_signals_by_symbol(self, symbol: str) -> List[Signal]:
        """获取特定股票的信号"""
        return [s for s in self.all_signals if s.symbol == symbol]
    
    def clear_signals(self):
        """清空信号历史"""
        self.all_signals.clear()
        print("🗑️ 信号历史已清空")
    
    def reset_all_strategies(self):
        """重置所有策略"""
        for strategy in self.strategies.values():
            strategy.reset()
        
        self.all_signals.clear()
        self.total_signals_generated = 0
        
        print("🔄 所有策略已重置")
    
    # ==================== 实验模式支持 ====================
    
    def start_experiment(self, datasource_id: str) -> dict:
        """
        启动实验模式
        
        将注意力策略切换到指定的实验数据源（如历史行情回放）
        
        Args:
            datasource_id: 实验数据源ID
            
        Returns:
            启动结果
        """
        if self._experiment_mode:
            return {"success": False, "error": "实验模式已启动，请先关闭"}
        
        if not datasource_id:
            return {"success": False, "error": "请指定实验数据源"}
        
        # 检查数据源是否存在
        try:
            from deva.naja.datasource import get_datasource_manager
            ds_mgr = get_datasource_manager()
            ds_entry = ds_mgr.get(datasource_id)
            if ds_entry is None:
                return {"success": False, "error": f"数据源 {datasource_id} 不存在"}
        except Exception as e:
            return {"success": False, "error": f"检查数据源失败: {e}"}
        
        # 确保策略已初始化（如果还没有初始化）
        if not self.strategies:
            print("🔄 初始化注意力策略...")
            self.initialize_default_strategies()
        
        # 确保管理器已启动
        if not self.is_running:
            self.start()
        
        # 保存当前状态快照
        self._experiment_snapshot = {
            'pre_experiment_mode': self._experiment_mode,
            'pre_experiment_datasource_id': self._experiment_datasource_id,
            'pre_is_running': self.is_running,
            'strategy_snapshots': {}
        }
        
        # 保存每个策略的状态
        for strategy_id, strategy in self.strategies.items():
            self._experiment_snapshot['strategy_snapshots'][strategy_id] = {
                'was_active': strategy.is_active,
            }
        
        # 切换到实验模式
        self._experiment_mode = True
        self._experiment_datasource_id = datasource_id
        
        # 确保注意力系统的调度中心也切换到实验数据源
        try:
            orchestrator = self._get_orchestrator()
            if orchestrator:
                # 注册实验数据源到调度中心
                orchestrator.register_datasource(datasource_id)
        except Exception as e:
            print(f"⚠️ 注册实验数据源到调度中心失败: {e}")
        
        print(f"\n🧪 注意力策略实验模式已启动")
        print(f"   实验数据源: {datasource_id}")
        print(f"   策略数: {len(self.strategies)}")
        
        return {
            "success": True,
            "datasource_id": datasource_id,
            "strategy_count": len(self.strategies),
            "experiment_mode": True
        }
    
    def stop_experiment(self) -> dict:
        """
        停止实验模式
        
        恢复注意力策略到实验前的状态
        
        Returns:
            停止结果
        """
        if not self._experiment_mode:
            return {"success": False, "error": "实验模式未启动"}
        
        snapshot = self._experiment_snapshot
        
        # 恢复实验前的状态
        self._experiment_mode = snapshot.get('pre_experiment_mode', False)
        self._experiment_datasource_id = snapshot.get('pre_experiment_datasource_id')
        
        # 恢复策略状态
        for strategy_id, strategy in self.strategies.items():
            strategy_snap = snapshot.get('strategy_snapshots', {}).get(strategy_id)
            if strategy_snap:
                was_active = strategy_snap.get('was_active', False)
                if was_active and not strategy.is_active:
                    strategy.activate()
                elif not was_active and strategy.is_active:
                    strategy.deactivate()
        
        # 从调度中心注销实验数据源
        try:
            orchestrator = self._get_orchestrator()
            if orchestrator and self._experiment_datasource_id:
                orchestrator.unregister_datasource(self._experiment_datasource_id)
        except Exception as e:
            print(f"⚠️ 从调度中心注销实验数据源失败: {e}")
        
        # 清理实验状态
        self._experiment_snapshot = {}
        self._experiment_mode = False
        self._experiment_datasource_id = None
        
        print("\n🛑 注意力策略实验模式已停止")
        
        return {
            "success": True,
            "experiment_mode": False
        }
    
    def get_experiment_info(self) -> dict:
        """获取实验模式信息"""
        return {
            "active": self._experiment_mode,
            "datasource_id": self._experiment_datasource_id,
            "strategy_count": len(self.strategies) if self._experiment_mode else 0
        }
    
    def is_experiment_mode(self) -> bool:
        """是否处于实验模式"""
        return self._experiment_mode


# 全局管理器实例
_manager_instance: Optional[AttentionStrategyManager] = None


def get_strategy_manager() -> AttentionStrategyManager:
    """获取全局策略管理器实例"""
    global _manager_instance
    
    if _manager_instance is None:
        _manager_instance = AttentionStrategyManager()
    
    return _manager_instance


def initialize_attention_strategies():
    """
    初始化注意力策略系统
    
    在 naja 启动时调用
    """
    manager = get_strategy_manager()
    
    # 初始化默认策略
    manager.initialize_default_strategies()
    
    # 启动管理器
    manager.start()
    
    # 注册到注意力系统
    try:
        from deva.naja.attention_integration import register_strategy_manager
        register_strategy_manager(manager)
    except Exception as e:
        print(f"⚠️ 注册到注意力系统失败: {e}")
    
    print("\n" + "="*50)
    print("🎯 注意力策略系统初始化完成")
    print("="*50)
    
    return manager
