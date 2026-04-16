"""Naja 单例注册表 - 统一管理所有单例

借鉴 deva namespace 思想，为 naja 所有核心单例提供统一的注册和访问机制。

设计原则：
1. 声明式配置 - 用数据表描述单例，自动生成工厂函数
2. 显式声明依赖 - 每个单例声明其依赖项
3. 自动初始化顺序 - 根据依赖关系自动排序初始化
4. 调试友好 - 可查看所有单例状态
5. 向后兼容 - 不影响现有的 get_xxx() 函数

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
import importlib
from typing import List, Tuple

from .infra.registry.singleton_registry import (
    register_singleton, SR, get_registry_status,
)

logger = logging.getLogger(__name__)


# ============================================================
#  声明式单例配置表
#
#  格式: (sr_name, module_path, class_name, deps)
#    - sr_name: SR() 访问名
#    - module_path: 相对于 deva.naja 的模块路径（用 . 分隔）
#    - class_name: 要实例化的类名
#    - deps: 依赖的其他单例名列表
#
#  所有列在这里的单例都是「简单实例化」：import + Class()
# ============================================================

SIMPLE_SINGLETONS: List[Tuple[str, str, str, List[str]]] = [
    # ── 基础层 ──
    ("mode_manager",      ".market_hotspot.integration.market_hotspot_integration", "HotspotModeManager", []),

    # ── 注意力系统 ──
    ("signal_executor",          ".attention.orchestration.signal_executor",    "SignalExecutor",           ["attention_integration"]),
    ("trading_center",           ".attention.orchestration.trading_center",     "TradingCenter",            ["attention_os", "attention_integration"]),
    ("hotspot_signal_tracker",   ".attention.tracking.hotspot_signal_tracker",  "HotspotSignalTracker",     ["attention_integration"]),
    ("position_monitor",         ".attention.tracking.position_monitor",        "PositionMonitor",          ["attention_integration"]),
    ("report_generator",         ".attention.tracking.report_generator",        "AttentionReportGenerator", ["attention_integration"]),
    ("signal_tuner",             ".market_hotspot.intelligence.signal_tuner",   "SignalTuner",              ["attention_integration"]),
    ("value_system",             ".attention.values.system",                    "ValueSystem",              []),

    # ── 应用层 ──
    ("attention_fusion",         ".attention.attention_fusion",       "AttentionFusion",          ["attention_os"]),
    ("portfolio",                ".attention.portfolio",              "Portfolio",                []),
    ("focus_manager",            ".attention.focus_manager",          "AttentionFocusManager",    ["attention_integration"]),
    ("conviction_validator",     ".attention.discovery",              "ConvictionValidator",      ["attention_integration"]),
    ("blind_spot_investigator",  ".attention.discovery",              "BlindSpotInvestigator",    ["attention_integration"]),
    ("snapshot_manager",         ".state.snapshot",                   "SnapshotManager",          []),

    # ── Bandit ──
    ("market_data_bus",    ".bandit.market_data_bus",       "MarketDataBus",           ["mode_manager"]),
    ("market_observer",    ".bandit.market_observer",       "MarketDataObserver",      []),
    ("stock_block_map",    ".bandit.stock_block_map",       "StockBlockMap",           ["stock_registry"]),
    ("adaptive_cycle",     ".bandit.adaptive_cycle",        "AdaptiveCycle",           ["market_data_bus"]),
    ("bandit_runner",      ".bandit.runner",                "BanditAutoRunner",        ["market_data_bus"]),
    ("signal_listener",    ".bandit.signal_listener",       "SignalListener",          []),
    ("bandit_tracker",     ".bandit.tracker",               "BanditPositionTracker",   []),

    # ── 认知 ──
    ("cross_signal_analyzer",  ".cognition.analysis.cross_signal_analyzer",  "CrossSignalAnalyzer",  ["attention_integration"]),
    ("narrative_block_linker", ".attention.discovery",              "NarrativeBlockLinker", ["attention_integration"]),
    ("llm_reflection_engine",  ".cognition.insight.llm_reflection", "LLMReflectionEngine", ["attention_integration"]),
    ("cognition_engine",       ".cognition.engine",                 "CognitionEngine",     []),
    ("insight_pool",           ".cognition.insight.engine",         "InsightPool",         []),
    ("insight_engine",         ".cognition.insight.engine",         "InsightEngine",       ["insight_pool"]),
    ("awakened_alaya",         ".knowledge.alaya",                  "AwakenedAlaya",       []),
    ("strategy_result_store",  ".strategy.result_store",            "ResultStore",         []),
    ("signal_dispatcher",      ".signal.dispatcher",                "SignalDispatcher",    []),
    ("llm_controller",         ".llm_controller.controller",        "LLMController",      []),
    ("bandit_optimizer",       ".bandit.optimizer",                 "BanditOptimizer",     ["market_data_bus"]),
    ("bandit_tuner",           ".bandit.tuner",                     "BanditTuner",         ["market_data_bus"]),
    ("bandit_attribution",     ".bandit.attribution",               "BanditAttribution",   ["strategy_result_store"]),
    ("virtual_portfolio",      ".bandit.virtual_portfolio",         "VirtualPortfolio",    []),

    # ── 基础设施 ──
    ("thread_pool",            ".infra.runtime.thread_pool",        "ThreadPoolManager",        []),
    ("log_stream",             ".infra.log.log_stream",             "NajaLogStream",            []),
    ("output_controller",      ".strategy.output_controller",       "OutputController",         []),
    ("recoverable",            ".infra.runtime.recoverable",        "Recoverable",              []),
    ("performance_monitor",    ".infra.observability.performance_monitor", "NajaPerformanceMonitor", []),
    ("scheduler_manager",      ".scheduler.common",                 "SchedulerManager",         []),
    ("radar_engine",           ".radar.engine",                     "RadarEngine",              ["trading_clock"]),
    ("system_state_manager",   ".state.system.system_state",        "SystemStateManager",       []),
    ("market_time_service",    ".infra.runtime.market_time",        "MarketTimeService",        []),
    ("market_session_manager", ".radar.global_market_config",       "MarketSessionManager",     []),
    ("replay_scheduler",       ".replay.replay_scheduler",          "ReplayScheduler",          []),
    ("system_monitor",         ".infra.observability.system_monitor", "SystemMonitor",          []),
    ("auto_tuner",             ".infra.observability.auto_tuner",   "AutoTuner",                []),
    ("liquidity_manager",      ".attention.orchestration.liquidity_manager", "LiquidityManager", ["attention_integration"]),
    ("daily_review_scheduler", ".strategy.daily_review_scheduler",  "DailyReviewScheduler",     ["datasource_manager"]),
    ("cognition_orchestrator", ".attention.orchestration.cognition_orchestrator", "CognitionOrchestrator", ["attention_os"]),
    ("task_manager",           ".tasks",                            "TaskManager",              []),
    ("dictionary_manager",     ".dictionary",                       "DictionaryManager",        []),
]


def _auto_register(entries: List[Tuple[str, str, str, List[str]]]):
    """根据声明式配置表自动注册简单单例"""
    for sr_name, module_path, class_name, deps in entries:
        def _make_factory(mod_path: str, cls_name: str):
            def factory():
                mod = importlib.import_module(mod_path, package="deva.naja")
                cls = getattr(mod, cls_name)
                return cls()
            return factory

        register_singleton(sr_name, _make_factory(module_path, class_name), deps=deps)
        logger.info(f"  ✓ {sr_name}")


# ============================================================
#  需要特殊初始化逻辑的单例（保留显式工厂函数）
# ============================================================

def _register_custom_singletons():
    """注册需要特殊初始化逻辑的单例"""

    # --- stock_registry: 调用工厂函数而非类构造器 ---
    def _create_stock_registry():
        from .dictionary.blocks import get_block_dictionary
        return get_block_dictionary()
    register_singleton('stock_registry', _create_stock_registry, deps=[])
    logger.info("  ✓ stock_registry")

    # --- datasource_manager: 需要 _ensure_initialized() ---
    def _create_datasource_manager():
        from .datasource import DataSourceManager
        mgr = DataSourceManager()
        mgr._ensure_initialized()
        return mgr
    register_singleton('datasource_manager', _create_datasource_manager, deps=[])
    logger.info("  ✓ datasource_manager")

    # --- portfolio_manager: 创建后自动加载持仓配置 ---
    def _create_portfolio_manager():
        from .bandit.portfolio_manager import PortfolioManager
        pm = PortfolioManager()
        return pm
    register_singleton('portfolio_manager', _create_portfolio_manager, deps=['virtual_portfolio'])
    logger.info("  ✓ portfolio_manager")

    # --- attention_integration: 需要 load_config + initialize ---
    def _create_attention_integration():
        from .market_hotspot.integration.market_hotspot_integration import MarketHotspotIntegration
        from .market_hotspot.integration.market_hotspot_config import load_config
        integration = MarketHotspotIntegration()
        config = load_config()
        if config.enabled:
            system_config = config.to_hotspot_system_config()
            integration.initialize(system_config)
        return integration
    register_singleton('attention_integration', _create_attention_integration,
                      deps=['mode_manager', 'stock_registry'])
    logger.info("  ✓ attention_integration")

    # --- attention_os: 需要 initialize() ---
    def _create_attention_os():
        from .attention.os.attention_os import AttentionOS
        os_inst = AttentionOS()
        if not getattr(os_inst, '_initialized', False):
            os_inst.initialize()
        return os_inst
    register_singleton('attention_os', _create_attention_os,
                      deps=['attention_integration'])
    logger.info("  ✓ attention_os")

    # --- manas_manager: 注入 attention_os 的 kernel ---
    def _create_manas_manager():
        from .attention.kernel.manas_manager import ManasManager
        try:
            attention_os = SR('attention_os')
            kernel = attention_os.get_kernel()
        except Exception:
            kernel = None
        manager = ManasManager(kernel=kernel)
        manager.set_enabled(True)
        return manager
    register_singleton('manas_manager', _create_manas_manager,
                      deps=['attention_os'])
    logger.info("  ✓ manas_manager")

    # --- hotspot_system: 从 attention_integration 取属性 ---
    def _create_hotspot_system():
        integration = SR('attention_integration')
        return integration.hotspot_system
    register_singleton('hotspot_system', _create_hotspot_system,
                      deps=['attention_integration'])
    logger.info("  ✓ hotspot_system")

    # --- cognition_bus: 调用 get_event_bus() 单例获取器 ---
    def _create_cognitive_signal_bus():
        from .events import get_event_bus
        return get_event_bus()
    register_singleton('cognition_bus', _create_cognitive_signal_bus, deps=[])
    logger.info("  ✓ cognition_bus (→ NajaEventBus)")

    # --- history_tracker: 需要 load_latest_state + start_auto_save ---
    def _create_history_tracker():
        from .market_hotspot.tracking.history_tracker import MarketHotspotHistoryTracker
        tracker = MarketHotspotHistoryTracker()
        tracker.load_latest_state()
        tracker.start_auto_save(interval_seconds=300)
        return tracker
    register_singleton('history_tracker', _create_history_tracker, deps=[])
    logger.info("  ✓ history_tracker")

    # --- trading_clock: 统一交易时钟（支持 A股 + 美股），需要 start() ---
    def _create_trading_clock():
        from .radar.trading_clock import TradingClock
        tc = TradingClock()
        tc.start()
        return tc
    register_singleton('trading_clock', _create_trading_clock, deps=[])
    logger.info("  ✓ trading_clock (统一，支持 A股 + 美股)")

    # --- realtime_data_fetcher: 需要 SR() + start() ---
    def _create_realtime_data_fetcher():
        from .market_hotspot.data.realtime_fetcher import RealtimeDataFetcher
        integration = SR('attention_integration')
        fetcher = RealtimeDataFetcher(hotspot_system=integration)
        fetcher.start()
        return fetcher
    register_singleton('realtime_data_fetcher', _create_realtime_data_fetcher,
                      deps=['mode_manager', 'attention_integration'])
    logger.info("  ✓ realtime_data_fetcher")

    # --- wake_sync_manager: 需要注册多个组件 ---
    def _create_wake_sync_manager():
        from .state.system.wake_sync_manager import WakeSyncManager
        from .state.system.wake_sync_handlers import (
            AIDailyReportWakeSync,
            NewsFetcherWakeSync,
            GlobalMarketScannerWakeSync,
            DailyReviewWakeSync,
            PortfolioPriceWakeSync,
        )
        mgr = WakeSyncManager()
        mgr.register(PortfolioPriceWakeSync())
        mgr.register(NewsFetcherWakeSync())
        mgr.register(GlobalMarketScannerWakeSync())
        mgr.register(DailyReviewWakeSync())
        mgr.register(AIDailyReportWakeSync())
        return mgr
    register_singleton('wake_sync_manager', _create_wake_sync_manager, deps=[])
    logger.info("  ✓ wake_sync_manager")


def ensure_trading_clocks():
    """确保交易时钟相关单例已注册并初始化

    防御性函数：正常流程下 register_all_singletons() 已完成注册，
    此函数仅处理 bootstrap 之前被调用的边缘情况。
    """
    for sr_name, factory_info in [
        ('trading_clock', ('.radar.trading_clock', 'TradingClock', True)),
        ('market_session_manager', ('.radar.global_market_config', 'MarketSessionManager', False)),
    ]:
        try:
            SR(sr_name)
        except KeyError:
            mod_path, cls_name, needs_start = factory_info

            def _make_factory(mp, cn, ns):
                def factory():
                    mod = importlib.import_module(mp, package="deva.naja")
                    inst = getattr(mod, cn)()
                    if ns:
                        inst.start()
                    return inst
                return factory

            register_singleton(sr_name, _make_factory(mod_path, cls_name, needs_start), deps=[])

    try:
        SR('trading_clock')
    except Exception as e:
        logger.warning(f"[NajaRegister] 交易时钟初始化失败: {e}")


def register_all_singletons():
    """注册所有 naja 单例

    应在 naja 启动时调用一次（在 bootstrap 过程中）
    """
    logger.info("=" * 60)
    logger.info("[NajaRegister] 开始注册所有单例...")
    logger.info("=" * 60)

    # 1. 特殊初始化逻辑的单例（顺序敏感）
    _register_custom_singletons()

    # 2. 简单实例化的单例（声明式批量注册）
    _auto_register(SIMPLE_SINGLETONS)

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
