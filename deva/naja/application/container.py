from __future__ import annotations

import logging
from typing import Any, Optional

from .runtime_config import AppRuntimeConfig
from .runtime_modes import RuntimeModeInitializer
from ..infra.lifecycle.bootstrap import BootResult, BootStage
from ..register import SR

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
        self._cognition_engine = None
        
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
        log.info("[AppContainer] 开始初始化...")

        set_app_container(self)

        self._register_singletons()

        self._assemble_core_components()

        self._boot_result = BootResult(
            success=True,
            stage=BootStage.READY,
            message="AppContainer 初始化完成",
            duration_ms=0.0,
        )

        return self._boot_result

    def _register_singletons(self):
        """注册所有单例（来自旧的 Bootstrap 路径）"""
        from ..register import register_all_singletons
        register_all_singletons()

    def _assemble_core_components(self) -> None:
        """装配核心组件（显式依赖注入）"""
        if self._components_assembled:
            return

        log.info("[AppContainer] 开始装配核心组件...")

        try:
            # 0. 加载持久化数据管理器（原本在 Bootstrap._load_persistent_data 中）
            self._load_persistent_managers()

            # 1. 获取基础组件（从已注册的单例）
            self._trading_clock = SR('trading_clock')
            self._virtual_portfolio = SR('virtual_portfolio')
            self._value_system = SR('value_system')

            # 2. 获取 AttentionOS（需要先于 ManasManager，因为 NarrativeTracker 依赖它）
            self._attention_os = SR('attention_os')

            # 3. 获取 kernel 层组件（从已注册的单例）
            self._query_state = SR('query_state')
            self._query_state_updater = SR('query_state_updater')
            self._manas_manager = SR('manas_manager')
            # ManasEngine 在 ManasManager 内部创建，通过 get_manas_engine() 获取
            self._manas_engine = self._manas_manager._manas_engine

            # 4. 获取认知层组件（从已注册的单例）
            self._insight_pool = SR('insight_pool')
            self._insight_engine = SR('insight_engine')
            self._cognition_engine = SR('cognition_engine')

            # 5. 获取 Bandit 模块组件（从已注册的单例）
            self._bandit_optimizer = SR('bandit_optimizer')
            self._portfolio_manager = SR('portfolio_manager')
            self._bandit_tracker = SR('bandit_tracker')
            self._market_observer = SR('market_observer')
            self._signal_listener = SR('signal_listener')
            self._bandit_runner = SR('bandit_runner')
            self._adaptive_cycle = SR('adaptive_cycle')

            # 6. 获取 TradingCenter（从已注册的单例）
            self._trading_center = SR('trading_center')

            # 7. 获取 Radar 模块组件（从已注册的单例）
            self._radar_engine = SR('radar_engine')

            # 8. 事件订阅装配
            self._event_registrar = self._create_event_registrar()
            self._event_registrar.register_all()
            
            # 9. 启动 Supervisor（包含热点系统初始化）
            self._start_supervisor()
            
            self._components_assembled = True
            log.info("[AppContainer] 核心组件装配完成")
            
        except Exception as e:
            log.error(f"[AppContainer] 组件装配失败: {e}", exc_info=True)


    def _load_persistent_managers(self):
        """加载持久化数据管理器（原本在 Bootstrap._load_persistent_data 中）"""
        log.info("[AppContainer] 加载持久化数据管理器...")

        from ..datasource import get_datasource_manager
        from ..strategy import get_strategy_manager

        dict_mgr = SR('dictionary_manager')
        dict_mgr._ensure_initialized()
        ds_mgr = get_datasource_manager()
        ds_mgr._ensure_initialized()
        task_mgr = SR('task_manager')
        task_mgr._ensure_initialized()
        strategy_mgr = get_strategy_manager()
        strategy_mgr._ensure_initialized()

        counts = {}
        errors = {}

        try:
            counts["dictionary"] = dict_mgr.load_prefer_files()
            log.info(f"  加载了 {counts['dictionary']} 个字典（优先文件）")
        except Exception as e:
            errors["dictionary"] = str(e)
            log.warning(f"  字典加载失败: {e}")

        for name, mgr in (
            ("datasource", ds_mgr),
            ("task", task_mgr),
            ("strategy", strategy_mgr),
        ):
            try:
                if hasattr(mgr, 'load_prefer_files'):
                    counts[name] = mgr.load_prefer_files()
                    log.info(f"  加载了 {counts[name]} 个{name}（优先文件）")
                else:
                    counts[name] = mgr.load_from_db()
                    log.info(f"  加载了 {counts[name]} 个{name}")
            except Exception as e:
                errors[name] = str(e)
                log.warning(f"  {name} 加载失败: {e}")

        self._load_counts = counts
        self._load_errors = errors

    def _start_supervisor(self):
        """启动 Supervisor（包含热点系统初始化和数据获取器启动）"""
        try:
            from ..supervisor import start_supervisor
            from ..supervisor.monitoring import MonitoringMixin
            
            log.info("[AppContainer] 启动 Supervisor...")
            supervisor = start_supervisor()
            
            # 配置并启动注意力系统
            if isinstance(supervisor, MonitoringMixin):
                supervisor._force_realtime = False
                supervisor._lab_mode = None
                supervisor.configure_attention(force_realtime=False, lab_mode=None)
                log.info("[AppContainer] Supervisor 注意力系统配置完成")
            
            log.info("[AppContainer] Supervisor 已启动")
        except Exception as e:
            log.warning(f"[AppContainer] Supervisor 启动失败: {e}", exc_info=True)

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
    
    def _create_cognition_engine(self):
        """创建 CognitionEngine"""
        from ..cognition.engine import CognitionEngine
        return CognitionEngine()
    
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
        return self._attention_os

    @property
    def trading_center(self):
        """获取 TradingCenter"""
        return self._trading_center

    @property
    def insight_pool(self):
        """获取 InsightPool"""
        return self._insight_pool

    @property
    def query_state(self):
        """获取 QueryState"""
        return self._query_state

    @property
    def query_state_updater(self):
        """获取 QueryStateUpdater"""
        return self._query_state_updater

    @property
    def value_system(self):
        """获取 ValueSystem"""
        return self._value_system

    @property
    def trading_clock(self):
        """获取 TradingClock"""
        return self._trading_clock

    @property
    def virtual_portfolio(self):
        """获取 VirtualPortfolio"""
        return self._virtual_portfolio

    @property
    def bandit_tracker(self):
        """获取 BanditTracker"""
        return self._bandit_tracker

    @property
    def manas_engine(self):
        """获取 ManasEngine"""
        return self._manas_engine

    @property
    def manas_manager(self):
        """获取 ManasManager"""
        return self._manas_manager

    @property
    def insight_pool(self):
        """获取 InsightPool"""
        return self._insight_pool

    @property
    def insight_engine(self):
        """获取 InsightEngine"""
        return self._insight_engine

    @property
    def cognition_engine(self):
        """获取 CognitionEngine"""
        return self._cognition_engine

    @property
    def bandit_optimizer(self):
        """获取 BanditOptimizer"""
        return self._bandit_optimizer

    @property
    def portfolio_manager(self):
        """获取 PortfolioManager"""
        return self._portfolio_manager

    @property
    def radar_engine(self):
        """获取 RadarEngine"""
        return self._radar_engine

    @property
    def bandit_tracker(self):
        """获取 BanditPositionTracker"""
        return self._bandit_tracker

    @property
    def market_observer(self):
        """获取 MarketDataObserver"""
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
        return {
            "load_counts": {},
            "load_errors": {},
            "restore_results": {},
            "restore_errors": {},
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
