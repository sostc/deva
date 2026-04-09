"""Attention 模块单例注册

集中管理 attention 模块的单例及其依赖关系，借鉴 deva namespace 思想。

依赖关系图：
    mode_manager (AttentionModeManager)
           ↓
    stock_registry (StockRegistry)
           ↓
    attention_integration (MarketHotspotIntegration)
           ↓
    attention_os (AttentionOS)

使用方式：

    # 获取已注册的单例（自动处理依赖）
    from deva.naja.attention.register import SR

    integration = SR('attention_integration')  # 自动先初始化 mode_manager 和 stock_registry
    attention_os = SR('attention_os')

    # 查看所有单例状态
    from deva.naja.attention.register import get_registry_status
    print(get_registry_status())
"""

import logging
from typing import Optional

from ..market_hotspot.integration.extended import (
    MarketHotspotIntegration,
    AttentionModeManager,
    get_market_hotspot_integration as _get_market_hotspot_integration,
    get_mode_manager as _get_mode_manager,
    initialize_hotspot_system as _initialize_attention_system,
)
from ..common.stock_registry import get_stock_registry, StockInfoRegistry
from ..common.singleton_registry import register_singleton, SR, get_registry_status

log = logging.getLogger(__name__)


def _get_stock_registry():
    """获取 StockInfoRegistry 单例"""
    return get_stock_registry()


def _get_mode_manager():
    """获取 AttentionModeManager 单例"""
    return _get_mode_manager_orig()


def _get_market_hotspot_integration_factory():
    """获取 MarketHotspotIntegration 单例工厂"""
    def factory():
        integration = _get_market_hotspot_integration()
        # 确保已初始化
        if not integration._initialized_attention_system:
            _initialize_attention_system()
        return integration
    return factory


# 延迟导入，避免循环依赖
_get_mode_manager_orig = None


def _init_mode_manager():
    """初始化 mode_manager 获取函数"""
    global _get_mode_manager_orig
    if _get_mode_manager_orig is None:
        from .integration.extended import get_mode_manager as _gm
        _get_mode_manager_orig = _gm


def _create_mode_manager():
    """创建 AttentionModeManager"""
    _init_mode_manager()
    return _get_mode_manager()


def _create_attention_integration():
    """创建 MarketHotspotIntegration（带初始化）"""
    integration = _get_market_hotspot_integration()
    if not getattr(integration, '_initialized_attention_system', False):
        log.info("[AttentionRegister] 初始化 attention_integration")
        _initialize_attention_system()
    return integration


def _create_attention_os():
    """创建 AttentionOS（带初始化）"""
    from .attention_os import AttentionOS
    os = AttentionOS()
    if not os._initialized:
        os.initialize()
    return os


def register_attention_singletons():
    """注册 attention 模块的所有单例

    应在 naja 启动时调用一次
    """
    _init_mode_manager()

    register_singleton('mode_manager', _create_mode_manager, deps=[])
    log.info("[AttentionRegister] 注册单例: mode_manager")

    register_singleton('stock_registry', _get_stock_registry, deps=[])
    log.info("[AttentionRegister] 注册单例: stock_registry")

    register_singleton('attention_integration', _create_attention_integration, deps=['mode_manager', 'stock_registry'])
    log.info("[AttentionRegister] 注册单例: attention_integration")

    register_singleton('attention_os', _create_attention_os, deps=['attention_integration'])
    log.info("[AttentionRegister] 注册单例: attention_os")

    log.info("[AttentionRegister] Attention 模块单例注册完成")


__all__ = [
    'SR',
    'register_attention_singletons',
    'get_registry_status',
]
