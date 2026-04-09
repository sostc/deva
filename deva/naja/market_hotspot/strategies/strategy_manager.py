"""
热点策略管理器

统一管理所有基于热点的策略
协调策略与热点系统的交互
"""

import logging
import time
import asyncio
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

from .base import HotspotStrategyBase, Signal

log = logging.getLogger(__name__)

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


class HotspotStrategyManager:
    """
    热点策略管理器
    
    职责：
    1. 管理所有热点策略的生命周期
    2. 协调策略与热点系统的交互
    3. 收集和汇总所有策略的信号
    4. 提供统一的策略状态监控
    5. 根据热点水平动态调整策略执行
    """
    
    def __init__(self):
        self.strategies: Dict[str, HotspotStrategyBase] = {}
        self.configs: Dict[str, StrategyConfig] = {}
        self.all_signals: List[Signal] = []
        self.is_running: bool = False
        
        # 统计
        self.total_signals_generated: int = 0
        self.start_time: Optional[float] = None
        
        # 热点系统引用
        self._attention_integration = None
        self._orchestrator = None

        # 实验模式状态
        self._experiment_mode: bool = False
        self._experiment_datasource_id: Optional[str] = None
        self._experiment_snapshot: Dict[str, Any] = {}

    def _get_market_hotspot_integration(self):
        """获取热点系统集成"""
        if self._attention_integration is None:
            try:
                from deva.naja.market_hotspot.integration import get_market_hotspot_integration
                self._attention_integration = get_market_hotspot_integration()
            except Exception:
                pass
        return self._attention_integration

    def _get_orchestrator(self):
        """获取调度中心（兼容旧接口）"""
        if self._orchestrator is None:
            try:
                from deva.naja.attention.trading_center import get_trading_center
                self._orchestrator = get_trading_center()
            except Exception:
                pass
        return self._orchestrator
    
    def register_strategy(
        self,
        strategy: HotspotStrategyBase,
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
            return False

        self.strategies[strategy.strategy_id] = strategy

        if config is None:
            config = StrategyConfig(strategy_id=strategy.strategy_id)

        self.configs[strategy.strategy_id] = config

        return True
    
    def unregister_strategy(self, strategy_id: str) -> bool:
        """注销策略"""
        if strategy_id not in self.strategies:
            return False

        strategy = self.strategies[strategy_id]
        strategy.deactivate()

        del self.strategies[strategy_id]
        del self.configs[strategy_id]

        return True

    def enable_strategy(self, strategy_id: str) -> bool:
        """启用策略"""
        if strategy_id not in self.configs:
            return False

        self.configs[strategy_id].enabled = True

        if strategy_id in self.strategies:
            self.strategies[strategy_id].activate()

        return True

    def disable_strategy(self, strategy_id: str) -> bool:
        """禁用策略"""
        if strategy_id not in self.configs:
            return False

        self.configs[strategy_id].enabled = False

        if strategy_id in self.strategies:
            self.strategies[strategy_id].deactivate()

        return True
    
    def initialize_default_strategies(self):
        """初始化默认策略集"""
        from .global_sentinel import GlobalMarketSentinel
        from .block_hunter import BlockRotationHunter
        from .momentum_tracker import MomentumSurgeTracker
        from .anomaly_sniper import AnomalyPatternSniper
        from .smart_money_detector import SmartMoneyFlowDetector
        from .us_strategies import (
            USGlobalMarketSentinel,
            USBlockRotationHunter,
            USMomentumSurgeTracker,
            USAnomalyPatternSniper,
            USSmartMoneyFlowDetector,
        )

        global_sentinel = GlobalMarketSentinel()
        self.register_strategy(global_sentinel, StrategyConfig(
            strategy_id=global_sentinel.strategy_id,
            enabled=True,
            priority=10
        ))

        block_hunter = BlockRotationHunter()
        self.register_strategy(block_hunter, StrategyConfig(
            strategy_id=block_hunter.strategy_id,
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

        # === 美股策略集（默认启用） ===
        us_global = USGlobalMarketSentinel()
        self.register_strategy(us_global, StrategyConfig(
            strategy_id=us_global.strategy_id,
            enabled=True,
            priority=6
        ))

        us_block = USBlockRotationHunter()
        self.register_strategy(us_block, StrategyConfig(
            strategy_id=us_block.strategy_id,
            enabled=True,
            priority=5
        ))

        us_momentum = USMomentumSurgeTracker()
        self.register_strategy(us_momentum, StrategyConfig(
            strategy_id=us_momentum.strategy_id,
            enabled=True,
            priority=5
        ))

        us_anomaly = USAnomalyPatternSniper()
        self.register_strategy(us_anomaly, StrategyConfig(
            strategy_id=us_anomaly.strategy_id,
            enabled=True,
            priority=4
        ))

        us_smart_money = USSmartMoneyFlowDetector()
        self.register_strategy(us_smart_money, StrategyConfig(
            strategy_id=us_smart_money.strategy_id,
            enabled=True,
            priority=5
        ))

        self._enable_bandit_output()

    def _enable_bandit_output(self):
        """启用策略的 Bandit 输出，使信号能够创建虚拟持仓"""
        try:
            from deva.naja.strategy.output_controller import get_output_controller
            controller = get_output_controller()

            hotspot_strategies = [
                'block_rotation_hunter',
                'momentum_surge_tracker',
                'anomaly_pattern_sniper',
                'smart_money_flow_detector',
                'us_block_rotation_hunter',
                'us_momentum_surge_tracker',
                'us_anomaly_pattern_sniper',
                'us_smart_money_flow_detector',
            ]

            for strategy_id in hotspot_strategies:
                controller.update_targets(strategy_id, bandit=True, signal=True, radar=True, memory=True)
                log.info(f"[StrategyManager] 已启用 {strategy_id} 的 Bandit 输出")
        except Exception as e:
            log.warning(f"[StrategyManager] 启用 Bandit 输出失败: {e}")

    def process_data(
        self,
        data: Any,
        context: Optional[Dict[str, Any]] = None
    ) -> List[Signal]:
        """
        处理数据并收集所有策略的信号

        Args:
            data: 市场数据
            context: 热点上下文

        Returns:
            所有策略生成的信号
        """
        log.debug(f"[StrategyManager] process_data called: data rows={len(data) if data is not None else 'None'}, context keys={list(context.keys()) if context else 'None'}")
        if not self.is_running:
            return []

        start_time = time.time()
        all_signals = []

        # 获取热点上下文
        if context is None:
            context = self._build_attention_context()

        # 识别当前市场（用于策略门控）
        market = context.get('market')
        if not market and hasattr(data, 'columns') and 'market' in data.columns:
            try:
                markets = set(str(m).upper() for m in data['market'].dropna().unique())
                if len(markets) == 1:
                    market = markets.pop()
                elif len(markets) > 1:
                    market = "ALL"
            except Exception:
                market = None
        if not market:
            market = "CN"

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
                strategy_market = getattr(strategy, 'market_scope', 'ALL')
                if market != "ALL" and strategy_market not in ("ALL", market):
                    continue
                signals = strategy.process(data, context)
                all_signals.extend(signals)

                # 记录单个策略性能
                if _PERFORMANCE_MONITORING_AVAILABLE:
                    strategy_latency = (time.time() - strategy_start) * 1000
                    record_component_execution(
                        component_id=f"attention_strategy_{strategy_id}",
                        component_name=f"热点策略: {strategy.name}",
                        component_type=ComponentType.STRATEGY,
                        execution_time_ms=strategy_latency,
                        success=True
                    )
            except Exception as e:
                pass
                if _PERFORMANCE_MONITORING_AVAILABLE:
                    strategy_latency = (time.time() - strategy_start) * 1000
                    record_component_execution(
                        component_id=f"attention_strategy_{strategy_id}",
                        component_name=f"热点策略: {strategy.name}",
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
                component_name="热点策略管理器",
                component_type=ComponentType.STRATEGY,
                execution_time_ms=total_latency,
                success=True
            )

        return all_signals
    
    def _build_attention_context(self) -> Dict[str, Any]:
        """构建热点上下文"""
        integration = self._get_market_hotspot_integration()
        
        context = {
            'timestamp': time.time(),
            'global_hotspot': 0.5,
            'block_weights': {},
            'symbol_weights': {}
        }
        
        if integration and integration.hotspot_system:
            attention_system = integration.hotspot_system
            
            # 全局热点
            context['global_hotspot'] = attention_system._last_global_hotspot
            
            # 题材权重（过滤噪音题材）
            context['block_weights'] = attention_system.block_hotspot.get_all_weights(filter_noise=True)
            
            # 个股权重
            context['symbol_weights'] = attention_system.weight_pool.get_all_weights()
        
        return context
    
    def start(self):
        """启动策略管理器"""
        if self.is_running:
            return

        self.is_running = True
        self.start_time = time.time()

        # 激活所有启用的策略
        for strategy_id, strategy in self.strategies.items():
            config = self.configs.get(strategy_id)
            if config and config.enabled:
                strategy.activate()
    
    def stop(self):
        """停止策略管理器"""
        if not self.is_running:
            return
        
        self.is_running = False

        # 停用所有策略
        for strategy in self.strategies.values():
            strategy.deactivate()
    
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

    def reset_all_strategies(self):
        """重置所有策略"""
        for strategy in self.strategies.values():
            strategy.reset()

        self.all_signals.clear()
        self.total_signals_generated = 0
    
    # ==================== 实验模式支持 ====================
    
    def start_experiment(self, datasource_id: str) -> dict:
        """
        启动实验模式
        
        将热点策略切换到指定的实验数据源（如历史行情回放）
        
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

        # 启动反馈报告收集
        try:
            from deva.naja.market_hotspot.intelligence.feedback_report import get_feedback_report_generator
            reporter = get_feedback_report_generator()
            experiment_id = reporter.start_collection(datasource_id=datasource_id)
            log.info(f"反馈报告收集已启动: {experiment_id}")
        except Exception as e:
            log.warning(f"启动反馈报告收集失败: {e}")

        # 确保热点系统的调度中心也切换到实验数据源
        try:
            orchestrator = self._get_orchestrator()
            if orchestrator:
                orchestrator.register_datasource(datasource_id)
        except Exception:
            pass
        
        return {
            "success": True,
            "datasource_id": datasource_id,
            "strategy_count": len(self.strategies),
            "experiment_mode": True
        }
    
    def stop_experiment(self) -> dict:
        """
        停止实验模式
        
        恢复热点策略到实验前的状态
        
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
        except Exception:
            pass

        # 停止实验数据源（如果是 replay 类型）
        experiment_datasource_id = self._experiment_datasource_id
        if experiment_datasource_id:
            try:
                from deva.naja.datasource import get_datasource_manager
                ds_mgr = get_datasource_manager()
                ds_entry = ds_mgr.get(experiment_datasource_id)
                if ds_entry and ds_entry.is_running:
                    ds_mgr.stop(experiment_datasource_id)
                    log.info(f"实验数据源已停止: {experiment_datasource_id}")
            except Exception as e:
                log.warning(f"停止实验数据源失败: {e}")

        # 清理实验状态
        self._experiment_snapshot = {}
        self._experiment_mode = False
        self._experiment_datasource_id = None

        # 停止反馈报告收集并生成报告
        report_path = None
        insights_pushed = 0
        try:
            from deva.naja.market_hotspot.intelligence.feedback_report import get_feedback_report_generator
            reporter = get_feedback_report_generator()
            reporter.stop_collection()

            # 推送到认知系统的 InsightPool，供 LLM Reflection 生成洞察
            insights_pushed = reporter._emit_to_insight()

            if reporter.get_summary()['signals_count'] > 0:
                report_path = reporter.save_report()
                log.info(f"反馈报告已保存: {report_path}")
            else:
                log.info("本次实验无信号，跳过报告生成")
            reporter.clear()
        except Exception as e:
            log.warning(f"生成反馈报告失败: {e}")

        result = {
            "success": True,
            "experiment_mode": False
        }
        if report_path:
            result["report_path"] = report_path
        if insights_pushed > 0:
            result["insights_pushed"] = insights_pushed
        return result
    
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

    def create_strategy_entry(self, strategy_id: str):
        """
        创建策略条目包装器（实现 StrategyEntry 接口）

        Args:
            strategy_id: 热点策略ID

        Returns:
            HotspotStrategyWrapper 或 None（如果策略不存在）
        """
        if strategy_id not in self.strategies:
            return None

        try:
            from .wrapper import wrap_hotspot_strategy
            strategy = self.strategies[strategy_id]
            wrapper = wrap_hotspot_strategy(strategy, self)

            config = self.configs.get(strategy_id)
            if config:
                from ...common.recoverable import UnitStatus
                wrapper._state.status = UnitStatus.RUNNING.value if config.enabled else UnitStatus.STOPPED.value

            return wrapper
        except Exception:
            return None

    def create_all_strategy_entries(self):
        """
        创建所有热点策略的策略条目包装器列表

        Returns:
            List[HotspotStrategyWrapper]
        """
        wrappers = []
        for strategy_id in self.strategies:
            wrapper = self.create_strategy_entry(strategy_id)
            if wrapper:
                wrappers.append(wrapper)
        return wrappers


# 全局管理器实例
_manager_instance: Optional[HotspotStrategyManager] = None


def get_hotspot_manager() -> HotspotStrategyManager:
    """获取全局策略管理器实例"""
    global _manager_instance

    if _manager_instance is None:
        _manager_instance = HotspotStrategyManager()
        _manager_instance.initialize_default_strategies()
        _manager_instance.start()

    return _manager_instance


def get_strategy_manager() -> HotspotStrategyManager:
    """获取全局策略管理器实例（别名，自动初始化）"""
    return get_hotspot_manager()


def initialize_hotspot_strategies():
    """
    初始化热点策略系统

    在 naja 启动时调用
    """
    manager = get_hotspot_manager()

    # 初始化默认策略
    manager.initialize_default_strategies()

    # 启动管理器
    manager.start()

    # 注册到热点系统
    try:
        from deva.naja.market_hotspot.integration import register_strategy_manager
        register_strategy_manager(manager)
    except Exception:
        pass

    # 自动注册到策略管理系统（用于UI展示）
    _auto_register_to_strategy_manager(manager)

    return manager


def _auto_register_to_strategy_manager(manager: HotspotStrategyManager):
    """
    自动将热点策略注册到策略管理系统

    这样在策略管理UI中可以统一看到所有策略
    """
    try:
        from deva.naja.strategy import get_hotspot_manager as get_sm
        strategy_mgr = get_sm()

        for strategy_id in manager.strategies:
            existing = strategy_mgr.get(strategy_id)
            if existing is not None:
                continue

            wrapper = manager.create_strategy_entry(strategy_id)
            if wrapper:
                strategy_mgr._items[strategy_id] = wrapper
    except Exception:
        pass

    return manager
