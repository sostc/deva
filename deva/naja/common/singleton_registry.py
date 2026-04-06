"""单例注册表 - 借鉴 deva namespace 思想

提供统一的单例管理机制，解决以下问题：
1. 初始化时机不明确 - 统一入口，显式初始化
2. 静默失败 - 异常会传播，可追踪失败原因
3. 难以调试 - 提供 list_status() 查看所有单例状态
4. 依赖关系模糊 - 支持声明依赖，自动按顺序初始化

使用方式：

    from deva.naja.common.singleton_registry import SR, register_singleton

    # 注册单例（带依赖声明）
    register_singleton('attention_integration',
        factory=lambda: NajaAttentionIntegration(),
        deps=['mode_manager', 'stock_registry']
    )

    # 获取单例 - 自动处理依赖初始化
    integration = SR('attention_integration')

    # 调试：查看所有单例状态
    from deva.naja.common.singleton_registry import get_registry_status
    print(get_registry_status())
"""

from __future__ import annotations

import threading
import logging
from typing import Optional, Callable, Any, Dict, List

logger = logging.getLogger(__name__)


class SingletonInfo:
    """单例信息"""
    def __init__(self, name: str, factory: Callable, deps: List[str] = None):
        self.name = name
        self.factory = factory
        self.deps = deps or []
        self._instance: Optional[Any] = None
        self._status: str = 'registered'  # registered -> initializing -> ready -> failed
        self._error: Optional[Exception] = None
        self._init_lock = threading.RLock()

    @property
    def instance(self) -> Optional[Any]:
        return self._instance

    @instance.setter
    def instance(self, value):
        self._instance = value

    @property
    def status(self) -> str:
        return self._status

    @property
    def error(self) -> Optional[Exception]:
        return self._error

    def mark_initializing(self):
        self._status = 'initializing'

    def mark_ready(self):
        self._status = 'ready'

    def mark_failed(self, error: Exception):
        self._status = 'failed'
        self._error = error

    def is_ready(self) -> bool:
        return self._status == 'ready'


class SingletonRegistry:
    """单例注册表

    核心思想借鉴 deva.core.namespace.Namespace：
    - 用字符串名称标识对象，全局唯一
    - 支持延迟创建，按需初始化
    - 线程安全
    """

    def __init__(self):
        self._singletons: Dict[str, SingletonInfo] = {}
        self._lock = threading.RLock()
        self._initializing_stack: List[str] = []  # 用于检测循环依赖

    def register(self, name: str, factory: Callable, deps: List[str] = None) -> None:
        """注册单例工厂

        Args:
            name: 单例名称，全局唯一
            factory: 工厂函数，调用后返回单例实例
            deps: 依赖的其他单例名称列表，会自动先初始化
        """
        with self._lock:
            if name in self._singletons:
                logger.warning(f"[SingletonRegistry] 单例 {name} 已注册，将被覆盖")
            self._singletons[name] = SingletonInfo(name, factory, deps)
            logger.debug(f"[SingletonRegistry] 注册单例: {name}, deps={deps}")

    def get(self, name: str) -> Any:
        """获取单例，自动处理依赖

        Args:
            name: 单例名称

        Returns:
            单例实例

        Raises:
            KeyError: 单例未注册
            RuntimeError: 循环依赖检测到
        """
        with self._lock:
            info = self._singletons.get(name)
            if info is None:
                raise KeyError(f"[SingletonRegistry] 单例 '{name}' 未注册，请先调用 register_singleton('{name}', ...)")

            # 已创建且就绪，直接返回
            if info.is_ready():
                return info.instance

            # 防止循环依赖
            if name in self._initializing_stack:
                cycle = ' -> '.join(self._initializing_stack + [name])
                raise RuntimeError(f"[SingletonRegistry] 检测到循环依赖: {cycle}")

            # 标记开始初始化
            info.mark_initializing()
            self._initializing_stack.append(name)

            try:
                # 先初始化依赖
                for dep_name in info.deps:
                    if dep_name not in self._singletons:
                        raise RuntimeError(f"[SingletonRegistry] 单例 {name} 依赖 {dep_name}，但该单例未注册")
                    dep_info = self._singletons[dep_name]
                    if not dep_info.is_ready():
                        # 递归初始化依赖
                        self.get(dep_name)

                # 创建实例
                logger.debug(f"[SingletonRegistry] 初始化单例: {name}")
                instance = info.factory()

                # 特殊处理：如果返回的是单例对象，确保是同一个实例
                if hasattr(instance, '_instance') and instance._instance is not None:
                    instance = instance._instance

                info.instance = instance
                info.mark_ready()
                logger.info(f"[SingletonRegistry] 单例就绪: {name}")
                return instance

            except Exception as e:
                info.mark_failed(e)
                logger.error(f"[SingletonRegistry] 单例 {name} 初始化失败: {e}", exc_info=True)
                raise

            finally:
                self._initializing_stack.remove(name)

    def exists(self, name: str) -> bool:
        """检查单例是否已注册"""
        with self._lock:
            return name in self._singletons

    def is_ready(self, name: str) -> bool:
        """检查单例是否已就绪"""
        with self._lock:
            info = self._singletons.get(name)
            return info.is_ready() if info else False

    def get_status(self, name: str) -> Optional[str]:
        """获取单例状态"""
        with self._lock:
            info = self._singletons.get(name)
            return info.status if info else None

    def list_status(self) -> Dict[str, dict]:
        """列出所有单例状态（调试用）"""
        with self._lock:
            result = {}
            for name, info in sorted(self._singletons.items()):
                result[name] = {
                    'status': info.status,
                    'has_instance': info.instance is not None,
                    'deps': info.deps,
                    'error': str(info.error) if info.error else None
                }
            return result

    def clear(self) -> None:
        """清空所有单例（主要用于测试）"""
        with self._lock:
            self._singletons.clear()
            self._initializing_stack.clear()


# 全局注册表实例
_global_registry = SingletonRegistry()


def SR(name: str) -> Any:
    """便捷访问函数 - 获取注册的单例

    Args:
        name: 单例名称

    Returns:
        单例实例
    """
    return _global_registry.get(name)


def register_singleton(name: str, factory: Callable, deps: List[str] = None) -> None:
    """注册单例的便捷函数

    Args:
        name: 单例名称
        factory: 工厂函数
        deps: 依赖列表
    """
    _global_registry.register(name, factory, deps)


def get_registry_status() -> Dict[str, dict]:
    """获取注册表状态（调试用）"""
    return _global_registry.list_status()


def is_singleton_ready(name: str) -> bool:
    """检查单例是否就绪"""
    return _global_registry.is_ready(name)


# ============================================================================
# 猴子补丁兼容模式 - 让旧代码无需修改即可使用新单例注册表
# ============================================================================

_compat_patches_applied = False
_original_functions = {}  # 保存原始函数


def apply_compatibility_patches():
    """应用猴子补丁，让所有旧的 get_xxx() 函数自动使用 SR()

    在 bootstrap 启动时调用一次，即可让所有旧代码透明地使用新的单例注册表。

    原理：
    1. 保存所有原始的 get_xxx() 函数
    2. 将模块中的 get_xxx() 替换为指向 SR() 的补丁函数
    3. 这样旧代码调用 get_xxx() 时，实际会调用 SR('xxx')
    4. 但工厂函数中可以直接调用类名（如 AttentionOS()）创建实例，
       因为这些调用没有被补丁
    """
    global _compat_patches_applied
    if _compat_patches_applied:
        logger.warning("[SingletonRegistry] 猴子补丁已应用，跳过")
        return

    logger.info("[SingletonRegistry] 应用猴子补丁兼容模式...")

    # 需要被替换的函数映射表：(模块名, 原始函数名, SR名称)
    PATCHES = [
        # attention 系统核心
        ('deva.naja.attention.integration.extended', 'get_attention_integration', 'attention_integration'),
        ('deva.naja.attention.attention_os', 'get_attention_os', 'attention_os'),
        ('deva.naja.attention.trading_center', 'get_trading_center', 'trading_center'),
        ('deva.naja.attention.integration.extended', 'get_mode_manager', 'mode_manager'),
        ('deva.naja.attention.signal_executor', 'get_signal_executor', 'signal_executor'),
        ('deva.naja.attention.data_processor', 'get_data_processor', 'data_processor'),

        # 应用层
        ('deva.naja.attention.attention_fusion', 'get_attention_fusion', 'attention_fusion'),
        ('deva.naja.attention.portfolio', 'get_portfolio', 'portfolio'),
        ('deva.naja.attention.focus_manager', 'get_attention_focus_manager', 'focus_manager'),
        ('deva.naja.attention.conviction_validator', 'get_conviction_validator', 'conviction_validator'),
        ('deva.naja.attention.blind_spot_investigator', 'get_blind_spot_investigator', 'blind_spot_investigator'),
        ('deva.naja.snapshot_manager', 'get_snapshot_manager', 'snapshot_manager'),

        # bandit 模块
        ('deva.naja.bandit.market_data_bus', 'get_market_data_bus', 'market_data_bus'),
        ('deva.naja.bandit.market_observer', 'get_market_observer', 'market_observer'),
        ('deva.naja.bandit.stock_sector_map', 'get_stock_sector_map', 'stock_sector_map'),

        # 认知模块（cognition_bus 已有内部单例机制，不需要猴子补丁）
        ('deva.naja.cognition.history_tracker', 'get_history_tracker', 'history_tracker'),
        ('deva.naja.cognition.text_processing_pipeline', 'get_text_pipeline', 'text_pipeline'),
        ('deva.naja.cognition.attention_text_router', 'get_attention_router', 'attention_router'),
        ('deva.naja.cognition.cross_signal_analyzer', 'get_cross_signal_analyzer', 'cross_signal_analyzer'),
        ('deva.naja.attention.narrative_block_linker', 'get_narrative_block_linker', 'narrative_block_linker'),
        ('deva.naja.cognition.insight.llm_reflection', 'get_llm_reflection_engine', 'llm_reflection_engine'),

        # 处理模块
        ('deva.naja.attention.processing.noise_manager', 'get_noise_manager', 'noise_manager'),
        ('deva.naja.attention.processing.block_noise_detector', 'get_block_noise_detector', 'block_noise_detector'),
        ('deva.naja.attention.state_querier', 'get_state_querier', 'state_querier'),
        ('deva.naja.attention.block_registry', 'get_block_registry', 'block_registry'),

        # 策略模块
        ('deva.naja.attention.strategies.strategy_manager', 'get_strategy_manager', 'strategy_manager'),

        # 其他
        ('deva.naja.attention.realtime_data_fetcher', 'get_data_fetcher', 'realtime_data_fetcher'),
        ('deva.naja.attention.kernel.manas_manager', 'get_manas_manager', 'manas_manager'),
        ('deva.naja.common.auto_tuner', 'get_auto_tuner', 'auto_tuner'),
        ('deva.naja.attention.liquidity_manager', 'get_liquidity_manager', 'liquidity_manager'),
        ('deva.naja.strategy.market_replay_scheduler', 'get_replay_scheduler', 'market_replay_scheduler'),
        ('deva.naja.attention.cognition_orchestrator', 'get_cognition_orchestrator', 'cognition_orchestrator'),

        # 基础层
        ('deva.naja.common.stock_registry', 'get_stock_registry', 'stock_registry'),
        ('deva.naja.datasource', 'get_datasource_manager', 'datasource_manager'),
    ]

    for module_name, original_func, sr_name in PATCHES:
        try:
            import importlib
            module = importlib.import_module(module_name)

            if hasattr(module, original_func):
                # 保存原始函数，以便工厂函数可以使用
                key = f"{module_name}.{original_func}"
                _original_functions[key] = getattr(module, original_func)

                def make_patch_func(name: str):
                    def patched(*args, **kwargs):
                        logger.debug(f"[SingletonRegistry] 猴子补丁: {name} → SR('{name}')")
                        return SR(name)
                    return patched

                patched_func = make_patch_func(sr_name)
                setattr(module, original_func, patched_func)
                logger.debug(f"  ✓ 补丁: {module_name}.{original_func} → SR('{sr_name}')")
        except Exception as e:
            logger.warning(f"  ✗ 补丁失败: {module_name}.{original_func} - {e}")

    _compat_patches_applied = True
    logger.info(f"[SingletonRegistry] 猴子补丁应用完成！")


def get_original_function(module_name: str, func_name: str):
    """获取原始函数（未补丁的版本）

    工厂函数内部可以使用此函数获取原始的 get_xxx() 函数，
    避免被猴子补丁拦截。
    """
    key = f"{module_name}.{func_name}"
    return _original_functions.get(key)
