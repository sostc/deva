"""Naja 单例注册表 - 统一管理所有单例

借鉴 deva namespace 思想，为 naja 所有核心单例提供统一的注册和访问机制。

设计原则：
1. 显式声明依赖 - 每个单例声明其依赖项
2. 自动初始化顺序 - 根据依赖关系自动排序初始化
3. 调试友好 - 可查看所有单例状态
4. 向后兼容 - 不影响现有的 get_xxx() 函数

使用方式：

    # 注册所有单例（在 bootstrap 中调用）
    from deva.naja.register import register_all_singletons
    register_all_singletons()

    # 获取单例
    from deva.naja.register import SR
    attention_os = SR('attention_os')

    # 调试
    from deva.naja.register import get_registry_status, print_registry_status
    print_registry_status()
"""

import logging
from typing import List, Callable

from .common.singleton_registry import (
    register_singleton, SR, get_registry_status,
    get_original_function
)

logger = logging.getLogger(__name__)


def _orig(module_name: str, func_name: str):
    """获取原始函数（未补丁版本）"""
    orig = get_original_function(module_name, func_name)
    if orig is None:
        raise RuntimeError(f"原始函数 {module_name}.{func_name} 未找到")
    return orig


def _register_base_singletons():
    """注册基础层单例（无依赖或只有简单依赖）"""
    logger.info("[NajaRegister] 注册基础层单例...")

    def _create_mode_manager():
        from .market_hotspot.integration.extended import AttentionModeManager
        return AttentionModeManager()
    register_singleton('mode_manager', _create_mode_manager, deps=[])
    logger.info("  ✓ mode_manager")

    def _create_stock_registry():
        from .common.stock_registry import StockInfoRegistry
        return StockInfoRegistry()
    register_singleton('stock_registry', _create_stock_registry, deps=[])
    logger.info("  ✓ stock_registry")

    def _create_datasource_manager():
        from .datasource import DataSourceManager
        mgr = DataSourceManager()
        mgr._ensure_initialized()
        return mgr
    register_singleton('datasource_manager', _create_datasource_manager, deps=[])
    logger.info("  ✓ datasource_manager")

    logger.info("[NajaRegister] 基础层单例注册完成")


def _register_attention_singletons():
    """注册注意力系统相关单例"""
    logger.info("[NajaRegister] 注册注意力系统单例...")

    def _create_attention_integration():
        from .market_hotspot.integration.extended import MarketHotspotIntegration
        from .attention.config import load_config, get_intelligence_config
        
        integration = MarketHotspotIntegration()
        # 立即初始化注意力系统
        config = load_config()
        intelligence_config = get_intelligence_config()
        if config.enabled:
            system_config = config.to_attention_system_config()
            integration.initialize(system_config, intelligence_config=intelligence_config)
        return integration
    register_singleton('attention_integration', _create_attention_integration,
                      deps=['mode_manager', 'stock_registry'])
    logger.info("  ✓ attention_integration")

    def _create_attention_os():
        from .attention.attention_os import AttentionOS
        os = AttentionOS()
        if not getattr(os, '_initialized', False):
            os.initialize()
        return os
    register_singleton('attention_os', _create_attention_os,
                      deps=['attention_integration'])
    logger.info("  ✓ attention_os")

    def _create_signal_executor():
        from .attention.signal_executor import SignalExecutor
        return SignalExecutor()
    register_singleton('signal_executor', _create_signal_executor,
                      deps=['attention_integration'])
    logger.info("  ✓ signal_executor")

    def _create_data_processor():
        from .attention.data_processor import DataProcessor
        return DataProcessor()
    register_singleton('data_processor', _create_data_processor,
                      deps=['attention_integration'])
    logger.info("  ✓ data_processor")

    def _create_trading_center():
        from .attention.trading_center import TradingCenter
        return TradingCenter()
    register_singleton('trading_center', _create_trading_center,
                      deps=['attention_os', 'attention_integration'])
    logger.info("  ✓ trading_center")

    def _create_attention_tracker():
        from .attention.tracker import AttentionTracker
        return AttentionTracker()
    register_singleton('attention_tracker', _create_attention_tracker,
                      deps=['attention_integration'])
    logger.info("  ✓ attention_tracker")

    def _create_price_monitor():
        from .attention.price_monitor import PriceMonitor
        return PriceMonitor()
    register_singleton('price_monitor', _create_price_monitor,
                      deps=['attention_integration'])
    logger.info("  ✓ price_monitor")

    def _create_report_generator():
        from .attention.report_generator import AttentionReportGenerator
        return AttentionReportGenerator()
    register_singleton('report_generator', _create_report_generator,
                      deps=['attention_integration'])
    logger.info("  ✓ report_generator")

    def _create_signal_tuner():
        from .market_hotspot.intelligence.signal_tuner import SignalTuner
        return SignalTuner()
    register_singleton('signal_tuner', _create_signal_tuner,
                      deps=['attention_integration'])
    logger.info("  ✓ signal_tuner")

    def _create_hotspot_system():
        integration = SR('attention_integration')
        return integration.hotspot_system
    register_singleton('hotspot_system', _create_hotspot_system,
                      deps=['attention_integration'])
    logger.info("  ✓ hotspot_system")

    def _create_value_system():
        from .attention.values.system import ValueSystem
        return ValueSystem()
    register_singleton('value_system', _create_value_system,
                      deps=[])
    logger.info("  ✓ value_system")

    logger.info("[NajaRegister] 注意力系统单例注册完成")


def ensure_trading_clocks():
    """确保交易时钟相关单例已注册并初始化"""
    try:
        SR('market_session_manager')
    except KeyError:
        def _create_market_session_manager():
            from .radar.global_market_config import MarketSessionManager
            return MarketSessionManager()
        register_singleton('market_session_manager', _create_market_session_manager, deps=[])

    try:
        SR('trading_clock')
    except KeyError:
        def _create_trading_clock():
            from .radar.trading_clock import TradingClock
            tc = TradingClock()
            tc.start()
            return tc
        register_singleton('trading_clock', _create_trading_clock, deps=[])

    try:
        SR('us_trading_clock')
    except KeyError:
        def _create_us_trading_clock():
            from .radar.trading_clock import USTradingClock
            utc = USTradingClock()
            utc.start()
            return utc
        register_singleton('us_trading_clock', _create_us_trading_clock, deps=[])

    # 触发实例化，确保线程启动
    try:
        SR('trading_clock')
        SR('us_trading_clock')
    except Exception as e:
        logger.warning(f"[NajaRegister] 交易时钟初始化失败: {e}")


def _register_application_singletons():
    """注册应用层单例"""
    logger.info("[NajaRegister] 注册应用层单例...")

    def _create_attention_fusion():
        from .attention.attention_fusion import AttentionFusion
        return AttentionFusion()
    register_singleton('attention_fusion', _create_attention_fusion,
                      deps=['attention_os'])
    logger.info("  ✓ attention_fusion")

    def _create_portfolio():
        from .attention.portfolio import Portfolio
        return Portfolio()
    register_singleton('portfolio', _create_portfolio)
    logger.info("  ✓ portfolio")

    def _create_focus_manager():
        from .attention.focus_manager import AttentionFocusManager
        return AttentionFocusManager()
    register_singleton('focus_manager', _create_focus_manager,
                      deps=['attention_integration'])
    logger.info("  ✓ focus_manager")

    def _create_conviction_validator():
        from .attention.conviction_validator import ConvictionValidator
        return ConvictionValidator()
    register_singleton('conviction_validator', _create_conviction_validator,
                      deps=['attention_integration'])
    logger.info("  ✓ conviction_validator")

    def _create_blind_spot_investigator():
        from .attention.blind_spot_investigator import BlindSpotInvestigator
        return BlindSpotInvestigator()
    register_singleton('blind_spot_investigator', _create_blind_spot_investigator,
                      deps=['attention_integration'])
    logger.info("  ✓ blind_spot_investigator")

    def _create_snapshot_manager():
        from .snapshot_manager import SnapshotManager
        return SnapshotManager()
    register_singleton('snapshot_manager', _create_snapshot_manager,
                      deps=[])
    logger.info("  ✓ snapshot_manager")

    logger.info("[NajaRegister] 应用层单例注册完成")


def _register_bandit_singletons():
    """注册 bandit 模块单例"""
    logger.info("[NajaRegister] 注册 bandit 单例...")

    def _create_market_data_bus():
        from .bandit.market_data_bus import MarketDataBus
        return MarketDataBus()
    register_singleton('market_data_bus', _create_market_data_bus,
                      deps=['mode_manager'])
    logger.info("  ✓ market_data_bus")

    def _create_market_observer():
        from .bandit.market_observer import MarketDataObserver
        return MarketDataObserver()
    register_singleton('market_observer', _create_market_observer,
                      deps=[])
    logger.info("  ✓ market_observer")

    def _create_stock_block_map():
        from .bandit.stock_block_map import StockBlockMap
        return StockBlockMap()
    register_singleton('stock_block_map', _create_stock_block_map,
                      deps=['stock_registry'])
    logger.info("  ✓ stock_block_map")

    def _create_adaptive_cycle():
        from .bandit.adaptive_cycle import AdaptiveCycle
        return AdaptiveCycle()
    register_singleton('adaptive_cycle', _create_adaptive_cycle,
                      deps=['market_data_bus'])
    logger.info("  ✓ adaptive_cycle")

    def _create_bandit_runner():
        from .bandit.runner import BanditAutoRunner
        return BanditAutoRunner()
    register_singleton('bandit_runner', _create_bandit_runner,
                      deps=['market_data_bus'])
    logger.info("  ✓ bandit_runner")

    def _create_signal_listener():
        from .bandit.signal_listener import SignalListener
        return SignalListener()
    register_singleton('signal_listener', _create_signal_listener,
                      deps=[])
    logger.info("  ✓ signal_listener")

    def _create_bandit_tracker():
        from .bandit.tracker import BanditPositionTracker
        return BanditPositionTracker()
    register_singleton('bandit_tracker', _create_bandit_tracker,
                      deps=[])
    logger.info("  ✓ bandit_tracker")

    logger.info("[NajaRegister] bandit 单例注册完成")


def _register_cognition_singletons():
    """注册认知模块单例"""
    logger.info("[NajaRegister] 注册认知模块单例...")

    def _create_cognition_bus():
        from .cognition.cognition_bus import get_cognition_bus
        return get_cognition_bus()
    register_singleton('cognition_bus', _create_cognition_bus,
                      deps=[])
    logger.info("  ✓ cognition_bus")

    def _create_history_tracker():
        from .market_hotspot.market_hotspot_history_tracker import MarketHotspotHistoryTracker
        tracker = MarketHotspotHistoryTracker()
        tracker.load_latest_state()
        tracker.start_auto_save(interval_seconds=300)
        return tracker
    register_singleton('history_tracker', _create_history_tracker,
                      deps=[])
    logger.info("  ✓ history_tracker")

    def _create_cross_signal_analyzer():
        from .cognition.cross_signal_analyzer import CrossSignalAnalyzer
        return CrossSignalAnalyzer()
    register_singleton('cross_signal_analyzer', _create_cross_signal_analyzer,
                      deps=['attention_integration'])
    logger.info("  ✓ cross_signal_analyzer")

    def _create_narrative_block_linker():
        from .attention.narrative_block_linker import NarrativeBlockLinker
        return NarrativeBlockLinker()
    register_singleton('narrative_block_linker', _create_narrative_block_linker,
                      deps=['attention_integration'])
    logger.info("  ✓ narrative_block_linker")

    def _create_llm_reflection_engine():
        from .cognition.insight.llm_reflection import LLMReflectionEngine
        return LLMReflectionEngine()
    register_singleton('llm_reflection_engine', _create_llm_reflection_engine,
                      deps=['attention_integration'])
    logger.info("  ✓ llm_reflection_engine")

    def _create_cognition_engine():
        from .cognition.engine import CognitionEngine
        return CognitionEngine()
    register_singleton('cognition_engine', _create_cognition_engine,
                      deps=[])
    logger.info("  ✓ cognition_engine")

    def _create_insight_pool():
        from .cognition.insight.engine import InsightPool
        return InsightPool()
    register_singleton('insight_pool', _create_insight_pool,
                      deps=[])
    logger.info("  ✓ insight_pool")

    def _create_insight_engine():
        from .cognition.insight.engine import InsightEngine
        return InsightEngine()
    register_singleton('insight_engine', _create_insight_engine,
                      deps=['insight_pool'])
    logger.info("  ✓ insight_engine")

    def _create_awakened_alaya():
        from .alaya import AwakenedAlaya
        return AwakenedAlaya()
    register_singleton('awakened_alaya', _create_awakened_alaya,
                      deps=[])
    logger.info("  ✓ awakened_alaya")

    logger.info("  ✓ signal_stream")

    def _create_strategy_result_store():
        from .strategy.result_store import ResultStore
        return ResultStore()
    register_singleton('strategy_result_store', _create_strategy_result_store,
                      deps=[])
    logger.info("  ✓ strategy_result_store")

    def _create_signal_dispatcher():
        from .signal.dispatcher import SignalDispatcher
        return SignalDispatcher()
    register_singleton('signal_dispatcher', _create_signal_dispatcher,
                      deps=['signal_stream'])
    logger.info("  ✓ signal_dispatcher")

    def _create_llm_controller():
        from .llm_controller.controller import LLMController
        return LLMController()
    register_singleton('llm_controller', _create_llm_controller,
                      deps=[])
    logger.info("  ✓ llm_controller")

    def _create_bandit_optimizer():
        from .bandit.optimizer import BanditOptimizer
        return BanditOptimizer()
    register_singleton('bandit_optimizer', _create_bandit_optimizer,
                      deps=['market_data_bus'])
    logger.info("  ✓ bandit_optimizer")

    def _create_bandit_tuner():
        from .bandit.tuner import BanditTuner
        return BanditTuner()
    register_singleton('bandit_tuner', _create_bandit_tuner,
                      deps=['market_data_bus'])
    logger.info("  ✓ bandit_tuner")

    def _create_bandit_attribution():
        from .bandit.attribution import BanditAttribution
        return BanditAttribution()
    register_singleton('bandit_attribution', _create_bandit_attribution,
                      deps=['strategy_result_store'])
    logger.info("  ✓ bandit_attribution")

    def _create_virtual_portfolio():
        from .bandit.virtual_portfolio import VirtualPortfolio
        return VirtualPortfolio()
    register_singleton('virtual_portfolio', _create_virtual_portfolio,
                      deps=[])
    logger.info("  ✓ virtual_portfolio")

    def _create_thread_pool():
        from .common.thread_pool import ThreadPoolManager
        return ThreadPoolManager()
    register_singleton('thread_pool', _create_thread_pool,
                      deps=[])
    logger.info("  ✓ thread_pool")

    def _create_log_stream():
        from .log_stream import NajaLogStream
        return NajaLogStream()
    register_singleton('log_stream', _create_log_stream,
                      deps=[])
    logger.info("  ✓ log_stream")

    def _create_output_controller():
        from .strategy.output_controller import OutputController
        return OutputController()
    register_singleton('output_controller', _create_output_controller,
                      deps=[])
    logger.info("  ✓ output_controller")

    def _create_recoverable():
        from .common.recoverable import Recoverable
        return Recoverable()
    register_singleton('recoverable', _create_recoverable,
                      deps=[])
    logger.info("  ✓ recoverable")

    def _create_performance_monitor():
        from .performance.performance_monitor import NajaPerformanceMonitor
        return NajaPerformanceMonitor()
    register_singleton('performance_monitor', _create_performance_monitor,
                      deps=[])
    logger.info("  ✓ performance_monitor")

    def _create_scheduler_manager():
        from .scheduler.common import SchedulerManager
        return SchedulerManager()
    register_singleton('scheduler_manager', _create_scheduler_manager,
                      deps=[])
    logger.info("  ✓ scheduler_manager")

    def _create_noise_filter():
        from .attention.processing.noise_filter import NoiseFilter
        return NoiseFilter()
    register_singleton('noise_filter', _create_noise_filter,
                      deps=[])
    logger.info("  ✓ noise_filter")

    def _create_trading_clock():
        from .radar.trading_clock import TradingClock
        tc = TradingClock()
        tc.start()
        return tc
    register_singleton('trading_clock', _create_trading_clock,
                      deps=[])
    logger.info("  ✓ trading_clock")

    def _create_us_trading_clock():
        from .radar.trading_clock import USTradingClock
        utc = USTradingClock()
        utc.start()
        return utc
    register_singleton('us_trading_clock', _create_us_trading_clock,
                      deps=[])
    logger.info("  ✓ us_trading_clock")

    def _create_radar_engine():
        from .radar.engine import RadarEngine
        return RadarEngine()
    register_singleton('radar_engine', _create_radar_engine,
                      deps=['trading_clock'])
    logger.info("  ✓ radar_engine")

    def _create_system_state_manager():
        from .system_state.system_state import SystemStateManager
        return SystemStateManager()
    register_singleton('system_state_manager', _create_system_state_manager,
                      deps=[])
    logger.info("  ✓ system_state_manager")

    def _create_market_time_service():
        from .common.market_time import MarketTimeService
        return MarketTimeService()
    register_singleton('market_time_service', _create_market_time_service,
                      deps=[])
    logger.info("  ✓ market_time_service")

    def _create_market_session_manager():
        from .radar.global_market_config import MarketSessionManager
        return MarketSessionManager()
    register_singleton('market_session_manager', _create_market_session_manager,
                      deps=[])
    logger.info("  ✓ market_session_manager")

    def _create_replay_scheduler():
        from .replay.replay_scheduler import ReplayScheduler
        return ReplayScheduler()
    register_singleton('replay_scheduler', _create_replay_scheduler,
                      deps=[])
    logger.info("  ✓ replay_scheduler")

    def _create_wake_sync_manager():
        from .system_state.wake_sync_manager import WakeSyncManager, _register_default_components
        mgr = WakeSyncManager()
        _register_default_components_for_sr(mgr)
        return mgr
    def _register_default_components_for_sr(manager):
        from .system_state.wake_sync_handlers import (
            AIDailyReportWakeSync,
            NewsFetcherWakeSync,
            GlobalMarketScannerWakeSync,
            DailyReviewWakeSync,
            PortfolioPriceWakeSync,
        )
        manager.register(PortfolioPriceWakeSync())
        manager.register(NewsFetcherWakeSync())
        manager.register(GlobalMarketScannerWakeSync())
        manager.register(DailyReviewWakeSync())
        manager.register(AIDailyReportWakeSync())
    register_singleton('wake_sync_manager', _create_wake_sync_manager,
                      deps=[])
    logger.info("  ✓ wake_sync_manager")

    def _create_system_monitor():
        from .system_monitor import SystemMonitor
        return SystemMonitor()
    register_singleton('system_monitor', _create_system_monitor,
                      deps=[])
    logger.info("  ✓ system_monitor")

    logger.info("[NajaRegister] 系统级单例注册完成")


def _register_processing_singletons():
    """注册处理层单例"""
    logger.info("[NajaRegister] 注册处理层单例...")
    # 处理层单例已合并到其他模块，无需额外注册
    logger.info("[NajaRegister] 处理层单例注册完成")


def _register_strategy_singletons():
    """注册策略层单例"""
    logger.info("[NajaRegister] 注册策略层单例...")
    # 策略层单例已合并到其他模块，无需额外注册
    logger.info("[NajaRegister] 策略层单例注册完成")


def _register_system_singletons():
    """注册系统层单例"""
    logger.info("[NajaRegister] 注册系统层单例...")
    # 系统层单例已合并到其他模块，无需额外注册
    logger.info("[NajaRegister] 系统层单例注册完成")


def _register_other_singletons():
    """注册其他单例"""
    logger.info("[NajaRegister] 注册其他单例...")

    def _create_realtime_data_fetcher():
        from .market_hotspot.realtime_data_fetcher import RealtimeDataFetcher
        integration = SR('attention_integration')
        fetcher = RealtimeDataFetcher(hotspot_system=integration)
        fetcher.start()  # 启动数据获取器
        return fetcher
    register_singleton('realtime_data_fetcher', _create_realtime_data_fetcher,
                      deps=['mode_manager', 'attention_integration'])
    logger.info("  ✓ realtime_data_fetcher")

    def _create_portfolio_manager():
        from .bandit.portfolio_manager import PortfolioManager
        return PortfolioManager()
    register_singleton('portfolio_manager', _create_portfolio_manager,
                      deps=[])
    logger.info("  ✓ portfolio_manager")

    def _create_manas_manager():
        from .attention.kernel.manas_manager import ManasManager
        return ManasManager()
    register_singleton('manas_manager', _create_manas_manager,
                      deps=[])
    logger.info("  ✓ manas_manager")

    def _create_auto_tuner():
        from .common.auto_tuner import AutoTuner
        return AutoTuner()
    register_singleton('auto_tuner', _create_auto_tuner,
                      deps=[])
    logger.info("  ✓ auto_tuner")

    def _create_liquidity_manager():
        from .attention.liquidity_manager import LiquidityManager
        return LiquidityManager()
    register_singleton('liquidity_manager', _create_liquidity_manager,
                      deps=['attention_integration'])
    logger.info("  ✓ liquidity_manager")

    def _create_daily_review_scheduler():
        from .strategy.daily_review_scheduler import DailyReviewScheduler
        return DailyReviewScheduler()
    register_singleton('daily_review_scheduler', _create_daily_review_scheduler,
                      deps=['datasource_manager'])
    logger.info("  ✓ daily_review_scheduler")

    def _create_cognition_orchestrator():
        from .attention.cognition_orchestrator import CognitionOrchestrator
        return CognitionOrchestrator()
    register_singleton('cognition_orchestrator', _create_cognition_orchestrator,
                      deps=['attention_os'])
    logger.info("  ✓ cognition_orchestrator")

    def _create_connector():
        from .manas_alaya_connector import ManasAlayaConnector
        return ManasAlayaConnector()
    register_singleton('connector', _create_connector,
                      deps=[])
    logger.info("  ✓ connector")

    def _create_task_manager():
        from .tasks import TaskManager
        return TaskManager()
    register_singleton('task_manager', _create_task_manager,
                      deps=[])
    logger.info("  ✓ task_manager")

    def _create_dictionary_manager():
        from .dictionary import DictionaryManager
        return DictionaryManager()
    register_singleton('dictionary_manager', _create_dictionary_manager,
                      deps=[])
    logger.info("  ✓ dictionary_manager")

    logger.info("[NajaRegister] 其他单例注册完成")


def register_all_singletons():
    """注册所有 naja 单例

    应在 naja 启动时调用一次（在 bootstrap 过程中）
    """
    logger.info("=" * 60)
    logger.info("[NajaRegister] 开始注册所有单例...")
    logger.info("=" * 60)

    _register_base_singletons()
    _register_attention_singletons()
    _register_application_singletons()
    _register_bandit_singletons()
    _register_cognition_singletons()
    _register_processing_singletons()
    _register_strategy_singletons()
    _register_system_singletons()
    _register_other_singletons()

    logger.info("=" * 60)
    logger.info("[NajaRegister] 所有单例注册完成!")
    logger.info("=" * 60)


def print_registry_status():
    """打印所有单例状态（调试用）"""
    status = get_registry_status()
    print("\n" + "=" * 70)
    print("NAJA 单例注册表状态")
    print("=" * 70)
    print(f"{'名称':<30} {'状态':<12} {'依赖数':<8} {'实例':<6}")
    print("-" * 70)
    for name, info in sorted(status.items()):
        deps = info.get('deps', [])
        status_str = info['status']
        has_inst = "✓" if info.get('has_instance') else "✗"
        print(f"{name:<30} {status_str:<12} {len(deps):<8} {has_inst:<6}")
    print("-" * 70)
    print(f"总计: {len(status)} 个单例")
    ready_count = sum(1 for v in status.values() if v['status'] == 'ready')
    print(f"就绪: {ready_count}")
    print("=" * 70 + "\n")


__all__ = [
    'SR',
    'register_all_singletons',
    'ensure_trading_clocks',
    'get_registry_status',
    'print_registry_status',
]
