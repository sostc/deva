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
        from .attention.integration.extended import AttentionModeManager
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
        from .attention.integration.extended import NajaAttentionIntegration
        return NajaAttentionIntegration()
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

    logger.info("[NajaRegister] 注意力系统单例注册完成")


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
        from .attention.portfolio import PortfolioManager
        return PortfolioManager()
    register_singleton('portfolio', _create_portfolio,
                      deps=['attention_integration'])
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

    def _create_stock_sector_map():
        from .bandit.stock_sector_map import StockSectorMap
        return StockSectorMap()
    register_singleton('stock_sector_map', _create_stock_sector_map,
                      deps=['stock_registry'])
    logger.info("  ✓ stock_sector_map")

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
        from .cognition.history_tracker import AttentionHistoryTracker
        return AttentionHistoryTracker()
    register_singleton('history_tracker', _create_history_tracker,
                      deps=[])
    logger.info("  ✓ history_tracker")

    def _create_text_pipeline():
        from .cognition.text_processing_pipeline import TextProcessingPipeline
        return TextProcessingPipeline()
    register_singleton('text_pipeline', _create_text_pipeline,
                      deps=['cognition_bus'])
    logger.info("  ✓ text_pipeline")

    def _create_attention_router():
        from .cognition.attention_text_router import AttentionTextRouter
        return AttentionTextRouter()
    register_singleton('attention_router', _create_attention_router,
                      deps=['attention_integration'])
    logger.info("  ✓ attention_router")

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

    logger.info("[NajaRegister] 认知模块单例注册完成")


def _register_processing_singletons():
    """注册处理模块单例"""
    logger.info("[NajaRegister] 注册处理模块单例...")

    def _create_noise_manager():
        from .attention.processing.noise_manager import NoiseManager
        return NoiseManager()
    register_singleton('noise_manager', _create_noise_manager,
                      deps=[])
    logger.info("  ✓ noise_manager")

    def _create_block_noise_detector():
        from .attention.processing.block_noise_detector import BlockNoiseDetector
        return BlockNoiseDetector()
    register_singleton('block_noise_detector', _create_block_noise_detector,
                      deps=[])
    logger.info("  ✓ block_noise_detector")

    def _create_state_querier():
        from .attention.state_querier import StateQuerier
        return StateQuerier()
    register_singleton('state_querier', _create_state_querier,
                      deps=['mode_manager'])
    logger.info("  ✓ state_querier")

    def _create_block_registry():
        from .attention.block_registry import BlockRegistry
        return BlockRegistry()
    register_singleton('block_registry', _create_block_registry,
                      deps=['attention_integration'])
    logger.info("  ✓ block_registry")

    logger.info("[NajaRegister] 处理模块单例注册完成")


def _register_strategy_singletons():
    """注册策略模块单例"""
    logger.info("[NajaRegister] 注册策略模块单例...")

    def _create_strategy_manager():
        from .attention.strategies.strategy_manager import AttentionStrategyManager
        return AttentionStrategyManager()
    register_singleton('strategy_manager', _create_strategy_manager,
                      deps=['attention_integration'])
    logger.info("  ✓ strategy_manager")

    logger.info("[NajaRegister] 策略模块单例注册完成")


def _register_other_singletons():
    """注册其他单例"""
    logger.info("[NajaRegister] 注册其他单例...")

    def _create_realtime_data_fetcher():
        from .attention.realtime_data_fetcher import RealtimeDataFetcher
        integration = SR('attention_integration')
        return RealtimeDataFetcher(attention_system=integration)
    register_singleton('realtime_data_fetcher', _create_realtime_data_fetcher,
                      deps=['mode_manager', 'attention_integration'])
    logger.info("  ✓ realtime_data_fetcher")

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

    def _create_market_replay_scheduler():
        from .strategy.market_replay_scheduler import MarketReplayScheduler
        return MarketReplayScheduler()
    register_singleton('market_replay_scheduler', _create_market_replay_scheduler,
                      deps=['datasource_manager'])
    logger.info("  ✓ market_replay_scheduler")

    def _create_cognition_orchestrator():
        from .attention.cognition_orchestrator import CognitionOrchestrator
        return CognitionOrchestrator()
    register_singleton('cognition_orchestrator', _create_cognition_orchestrator,
                      deps=['attention_os'])
    logger.info("  ✓ cognition_orchestrator")

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
    'get_registry_status',
    'print_registry_status',
]
