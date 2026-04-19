from __future__ import annotations

import logging
from typing import Any, Optional

from .runtime_config import AppRuntimeConfig
from .runtime_modes import RuntimeModeInitializer

log = logging.getLogger(__name__)


class AppContainer:
    """Composition root for Naja runtime assembly."""

    def __init__(self, config: AppRuntimeConfig):
        self.config = config
        self._boot_result = None
        
        # 核心组件（懒加载）
        self._attention_os = None
        self._trading_center = None
        self._decision_orchestrator = None
        self._event_registrar = None
        
        # 内核组件（kernel 层）
        self._query_state = None
        self._query_state_updater = None
        self._value_system = None
        self._trading_clock = None
        self._virtual_portfolio = None
        self._bandit_tracker = None
        self._manas_engine = None
        self._manas_manager = None
        
        # 认知层组件
        self._insight_pool = None
        self._insight_engine = None
        
        # Bandit 模块组件
        self._bandit_optimizer = None
        self._portfolio_manager = None
        self._market_observer = None
        self._signal_listener = None
        self._bandit_runner = None
        self._adaptive_cycle = None
        
        # Radar 模块组件
        self._radar_engine = None
        
        # 初始化标记
        self._components_assembled = False

    @property
    def boot_result(self):
        return self._boot_result

    def boot(self):
        from ..infra.lifecycle.bootstrap import SystemBootstrap

        bootstrap = SystemBootstrap()
        self._boot_result = bootstrap.boot()
        
        # 启动后装配核心组件
        self._assemble_core_components()
        
        return self._boot_result

    def _assemble_core_components(self) -> None:
        """装配核心组件（显式依赖注入）"""
        if self._components_assembled:
            return
            
        log.info("[AppContainer] 开始装配核心组件...")
        
        try:
            # 1. 创建基础组件
            self._trading_clock = self._create_trading_clock()
            self._virtual_portfolio = self._create_virtual_portfolio()
            self._value_system = self._create_value_system()
            
            # 2. 创建 kernel 层组件
            self._query_state = self._create_query_state()
            self._query_state_updater = self._create_query_state_updater()
            self._manas_engine = self._create_manas_engine()
            self._manas_manager = self._create_manas_manager()
            
            # 3. 创建认知层组件
            self._insight_pool = self._create_insight_pool()
            self._insight_engine = self._create_insight_engine()
            
            # 4. 创建 Bandit 模块组件
            self._bandit_optimizer = self._create_bandit_optimizer()
            self._portfolio_manager = self._create_portfolio_manager()
            self._bandit_tracker = self._create_bandit_tracker()
            self._market_observer = self._create_market_observer()
            self._signal_listener = self._create_signal_listener()
            self._bandit_runner = self._create_bandit_runner()
            self._adaptive_cycle = self._create_adaptive_cycle()
            
            # 5. 装配 AttentionOS（显式依赖）
            self._attention_os = self._create_attention_os()
            
            # 4. 装配 TradingCenter（显式依赖注入）
            self._trading_center = self._create_trading_center()
            
            # 5. DecisionOrchestrator 由 TradingCenter 内部创建
            
            # 6. 创建 Radar 模块组件
            self._radar_engine = self._create_radar_engine()
            
            # 7. 事件订阅装配
            self._event_registrar = self._create_event_registrar()
            self._event_registrar.register_all()
            
            self._components_assembled = True
            log.info("[AppContainer] 核心组件装配完成")
            
        except Exception as e:
            log.error(f"[AppContainer] 组件装配失败: {e}", exc_info=True)



    def _create_trading_clock(self):
        """创建 TradingClock"""
        from ..radar.trading_clock import TradingClock
        tc = TradingClock()
        tc.start()
        return tc

    def _create_virtual_portfolio(self):
        """创建 VirtualPortfolio"""
        from ..bandit.virtual_portfolio import VirtualPortfolio
        return VirtualPortfolio()

    def _create_value_system(self):
        """创建 ValueSystem"""
        from ..attention.values.system import ValueSystem
        return ValueSystem()

    def _create_query_state(self):
        """创建 QueryState（内核组件）"""
        from ..attention.kernel.state import QueryState
        
        qs = QueryState()
        
        # 显式注入依赖
        if self._value_system:
            qs.set_value_system(self._value_system)
            
        return qs

    def _create_query_state_updater(self):
        """创建 QueryStateUpdater（内核组件）"""
        from ..attention.kernel.state_updater import QueryStateUpdater
        
        updater = QueryStateUpdater(query_state=self._query_state)
        
        return updater

    def _create_attention_os(self):
        """创建 AttentionOS（显式依赖）"""
        from ..attention.os.attention_os import AttentionOS
        
        # 显式依赖注入
        attention_os = AttentionOS(insight_pool=self._insight_pool)
        
        return attention_os

    def _create_trading_center(self):
        """创建 TradingCenter（显式依赖注入）"""
        from ..attention.orchestration.trading_center import TradingCenter
        
        # 显式传递 AttentionOS 实例
        trading_center = TradingCenter(attention_os=self._attention_os)
        
        return trading_center

    def _create_manas_engine(self):
        """创建 ManasEngine（显式依赖注入）"""
        from ..attention.kernel.manas_engine import ManasEngine
        
        manas_engine = ManasEngine(
            session_manager=self._trading_clock,
            portfolio=self._virtual_portfolio,
            bandit_tracker=self._bandit_tracker
        )
        
        return manas_engine
    
    def _create_manas_manager(self):
        """创建 ManasManager（显式依赖注入）"""
        from ..attention.kernel.manas_manager import ManasManager
        
        manas_manager = ManasManager(
            trading_clock=self._trading_clock,
            virtual_portfolio=self._virtual_portfolio,
            bandit_tracker=self._bandit_tracker
        )
        
        return manas_manager
    
    def _create_insight_pool(self):
        """创建 InsightPool"""
        from ..cognition.insight.engine import InsightPool
        return InsightPool()
    
    def _create_insight_engine(self):
        """创建 InsightEngine（显式依赖注入）"""
        from ..cognition.insight.engine import InsightEngine
        
        insight_engine = InsightEngine(
            insight_pool=self._insight_pool
        )
        
        return insight_engine
    
    def _create_radar_engine(self):
        """创建 RadarEngine"""
        from ..radar.engine import RadarEngine
        
        radar_engine = RadarEngine(trading_clock=self._trading_clock)
        
        return radar_engine
    
    def _create_event_registrar(self):
        """创建事件订阅装配器"""
        from .event_registrar import EventSubscriberRegistrar
        return EventSubscriberRegistrar(
            attention_os=self._attention_os,
            trading_center=self._trading_center,
        )
    
    def _create_bandit_optimizer(self):
        """创建 Bandit 优化器（显式依赖注入）"""
        from ..bandit.optimizer import BanditOptimizer
        
        bandit_optimizer = BanditOptimizer(
            attention_os=self._attention_os
        )
        
        return bandit_optimizer
    
    def _create_portfolio_manager(self):
        """创建持仓管理器（显式依赖注入）"""
        from ..bandit.portfolio_manager import PortfolioManager
        
        portfolio_manager = PortfolioManager(
            virtual_portfolio=self._virtual_portfolio
        )
        
        return portfolio_manager
    
    def _create_bandit_tracker(self):
        """创建 BanditPositionTracker"""
        from ..bandit.tracker import BanditPositionTracker
        
        tracker = BanditPositionTracker(
            market_time_service=self._trading_clock,
            bandit_optimizer=self._bandit_optimizer
        )
        
        return tracker
    
    def _create_market_observer(self):
        """创建 MarketDataObserver"""
        from ..bandit.market_observer import MarketDataObserver
        
        observer = MarketDataObserver()
        
        return observer
    
    def _create_signal_listener(self):
        """创建 SignalListener"""
        from ..bandit.signal_listener import SignalListener
        
        listener = SignalListener()
        
        return listener
    
    def _create_bandit_runner(self):
        """创建 BanditAutoRunner"""
        from ..bandit.runner import BanditAutoRunner
        
        runner = BanditAutoRunner()
        
        return runner
    
    def _create_adaptive_cycle(self):
        """创建 AdaptiveCycle"""
        from ..bandit.adaptive_cycle import AdaptiveCycle
        
        cycle = AdaptiveCycle(
            signal_listener=self._signal_listener,
            portfolio=self._virtual_portfolio,
            market_observer=self._market_observer,
            optimizer=self._bandit_optimizer,
            tracker=self._bandit_tracker,
            runner=self._bandit_runner
        )
        
        return cycle

    @property
    def attention_os(self):
        """获取 AttentionOS"""
        if self._attention_os is None:
            self._assemble_core_components()
        return self._attention_os

    @property
    def trading_center(self):
        """获取 TradingCenter"""
        if self._trading_center is None:
            self._assemble_core_components()
        return self._trading_center

    @property
    def insight_pool(self):
        """获取 InsightPool"""
        if self._insight_pool is None:
            self._insight_pool = self._get_compat_singleton('insight_pool')
        return self._insight_pool

    @property
    def query_state(self):
        """获取 QueryState"""
        if self._query_state is None:
            self._assemble_core_components()
        return self._query_state

    @property
    def query_state_updater(self):
        """获取 QueryStateUpdater"""
        if self._query_state_updater is None:
            self._assemble_core_components()
        return self._query_state_updater

    @property
    def value_system(self):
        """获取 ValueSystem"""
        if self._value_system is None:
            self._assemble_core_components()
        return self._value_system

    @property
    def trading_clock(self):
        """获取 TradingClock"""
        if self._trading_clock is None:
            self._assemble_core_components()
        return self._trading_clock

    @property
    def virtual_portfolio(self):
        """获取 VirtualPortfolio"""
        if self._virtual_portfolio is None:
            self._assemble_core_components()
        return self._virtual_portfolio

    @property
    def bandit_tracker(self):
        """获取 BanditTracker"""
        if self._bandit_tracker is None:
            self._assemble_core_components()
        return self._bandit_tracker
    
    @property
    def manas_engine(self):
        """获取 ManasEngine"""
        if self._manas_engine is None:
            self._assemble_core_components()
        return self._manas_engine
    
    @property
    def manas_manager(self):
        """获取 ManasManager"""
        if self._manas_manager is None:
            self._assemble_core_components()
        return self._manas_manager
    
    @property
    def insight_pool(self):
        """获取 InsightPool"""
        if self._insight_pool is None:
            self._assemble_core_components()
        return self._insight_pool
    
    @property
    def insight_engine(self):
        """获取 InsightEngine"""
        if self._insight_engine is None:
            self._assemble_core_components()
        return self._insight_engine
    
    @property
    def bandit_optimizer(self):
        """获取 BanditOptimizer"""
        if self._bandit_optimizer is None:
            self._assemble_core_components()
        return self._bandit_optimizer
    
    @property
    def portfolio_manager(self):
        """获取 PortfolioManager"""
        if self._portfolio_manager is None:
            self._assemble_core_components()
        return self._portfolio_manager

    @property
    def radar_engine(self):
        """获取 RadarEngine"""
        if self._radar_engine is None:
            self._assemble_core_components()
        return self._radar_engine
    
    @property
    def bandit_tracker(self):
        """获取 BanditPositionTracker"""
        if self._bandit_tracker is None:
            self._assemble_core_components()
        return self._bandit_tracker
    
    @property
    def market_observer(self):
        """获取 MarketDataObserver"""
        if self._market_observer is None:
            self._assemble_core_components()
        return self._market_observer
    
    @property
    def signal_listener(self):
        """获取 SignalListener"""
        if self._signal_listener is None:
            self._assemble_core_components()
        return self._signal_listener
    
    @property
    def bandit_runner(self):
        """获取 BanditAutoRunner"""
        if self._bandit_runner is None:
            self._assemble_core_components()
        return self._bandit_runner
    
    @property
    def adaptive_cycle(self):
        """获取 AdaptiveCycle"""
        if self._adaptive_cycle is None:
            self._assemble_core_components()
        return self._adaptive_cycle

    def restore_runtime_state(self) -> None:
        print("🎯 恢复 Bandit 自适应循环...")
        try:
            from deva.naja.bandit import restore_bandit_state

            restore_bandit_state()
            print("✓ Bandit 自适应循环状态已恢复")
        except Exception as e:
            print(f"⚠️ Bandit 自适应循环恢复失败: {e}")

    def initialize_runtime_modes(self) -> None:
        RuntimeModeInitializer(self.config).initialize()

    def create_handlers(self):
        from ..web_ui.routes import create_handlers

        return create_handlers()

    def attention_config_summary(self) -> str:
        from ..market_hotspot.integration.market_hotspot_config import load_config
        import os

        attention_config = load_config()
        config_source = "env"
        if os.path.exists(os.path.expanduser("~/.naja/attention_config.yaml")):
            config_source = "file+env"
        return (
            "🧭 注意力配置摘要: enabled="
            f"{attention_config.enabled}, intervals="
            f"{attention_config.high_interval}/{attention_config.medium_interval}/{attention_config.low_interval}s, "
            f"monitoring={attention_config.enable_monitoring}, source={config_source}"
        )

    def startup_report(self) -> dict[str, Any]:
        details = self._boot_result.details if self._boot_result and self._boot_result.details else {}
        return {
            "load_counts": details.get("load_counts", {}),
            "load_errors": details.get("load_errors", {}),
            "restore_results": details.get("restore_results", {}),
            "restore_errors": details.get("restore_errors", {}),
            "components_assembled": self._components_assembled,
        }


# 全局容器实例（保持兼容性）
_app_container: Optional[AppContainer] = None


def set_app_container(container: AppContainer) -> None:
    """设置全局 AppContainer 实例"""
    global _app_container
    _app_container = container


def get_app_container() -> Optional[AppContainer]:
    """获取全局 AppContainer 实例"""
    return _app_container
