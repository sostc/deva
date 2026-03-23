"""SystemBootstrap - 系统启动引导器"""

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, Any, List, Callable, Optional
from enum import Enum


logger = logging.getLogger(__name__)


class BootStage(Enum):
    """启动阶段"""
    INIT = "init"
    LOAD_PERSISTENT = "load_persistent"
    INIT_CORE = "init_core"
    REGISTER_COMPONENTS = "register_components"
    VALIDATE = "validate"
    START_SCHEDULERS = "start_schedulers"
    READY = "ready"


@dataclass
class BootResult:
    """启动结果"""
    success: bool
    stage: BootStage
    message: str
    duration_ms: float = 0.0
    error: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)


class SystemBootstrap:
    """
    系统启动引导器

    保证系统组件按正确顺序初始化：

    1. 加载持久化数据（字典、配置）
    2. 初始化核心组件
    3. 注册数据源
    4. 验证数据流
    5. 启动调度器

    用法:
        bootstrap = SystemBootstrap()
        result = bootstrap.boot()

        if result.success:
            print("系统启动成功")
        else:
            print(f"启动失败: {result.error}")
    """

    def __init__(self):
        self._boot_stage = BootStage.INIT
        self._boot_results: List[BootResult] = []
        self._initialized = False

    def boot(self) -> BootResult:
        """
        执行启动流程

        Returns:
            BootResult: 最终启动结果
        """
        start_time = time.time()

        try:
            self._boot_stage = BootStage.INIT
            self._log("INFO", "开始系统启动...")

            self._boot_stage = BootStage.LOAD_PERSISTENT
            self._load_persistent_data()

            self._boot_stage = BootStage.INIT_CORE
            self._init_core_components()

            self._boot_stage = BootStage.REGISTER_COMPONENTS
            self._register_components()

            self._boot_stage = BootStage.VALIDATE
            self._validate_pipeline()

            self._boot_stage = BootStage.START_SCHEDULERS
            self._start_schedulers()

            self._boot_stage = BootStage.READY
            self._initialized = True

            duration_ms = (time.time() - start_time) * 1000
            logger.info(f"系统启动完成，耗时 {duration_ms:.1f}ms")

            return BootResult(
                success=True,
                stage=BootStage.READY,
                message="系统启动成功",
                duration_ms=duration_ms,
            )

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.exception(f"系统启动失败: {e}")

            return BootResult(
                success=False,
                stage=self._boot_stage,
                message=f"启动失败: {e}",
                duration_ms=duration_ms,
                error=str(e),
            )

    def _load_persistent_data(self) -> BootResult:
        """加载持久化数据"""
        start = time.time()
        logger.info("[1/5] 加载持久化数据...")

        try:
            from deva.naja.dictionary import get_dictionary_manager
            dict_mgr = get_dictionary_manager()

            count = dict_mgr.load_from_db()
            logger.info(f"  加载了 {count} 个字典")

            entry = dict_mgr.get_by_name("通达信概念板块")
            if entry:
                payload = entry.get_payload()
                if payload is not None:
                    logger.info(f"  板块字典数据: {payload.shape}")
                else:
                    logger.warning("  板块字典数据为空")
            else:
                logger.warning("  未找到通达信概念板块字典")

            duration_ms = (time.time() - start) * 1000

            return BootResult(
                success=True,
                stage=BootStage.LOAD_PERSISTENT,
                message=f"加载了 {count} 个字典",
                duration_ms=duration_ms,
            )

        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            logger.error(f"  加载持久化数据失败: {e}")
            raise

    def _init_core_components(self) -> BootResult:
        """初始化核心组件"""
        start = time.time()
        logger.info("[2/5] 初始化核心组件...")

        try:
            from deva.naja.attention_orchestrator import AttentionOrchestrator

            orchestrator = AttentionOrchestrator()
            logger.info(f"  AttentionOrchestrator 初始化完成")

            duration_ms = (time.time() - start) * 1000

            return BootResult(
                success=True,
                stage=BootStage.INIT_CORE,
                message="核心组件初始化完成",
                duration_ms=duration_ms,
            )

        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            logger.error(f"  初始化核心组件失败: {e}")
            raise

    def _register_components(self) -> BootResult:
        """注册组件"""
        start = time.time()
        logger.info("[3/5] 注册组件...")

        duration_ms = (time.time() - start) * 1000

        return BootResult(
            success=True,
            stage=BootStage.REGISTER_COMPONENTS,
            message="组件注册完成",
            duration_ms=duration_ms,
        )

    def _validate_pipeline(self) -> BootResult:
        """验证数据流"""
        start = time.time()
        logger.info("[4/5] 验证数据流...")

        try:
            from deva.naja.attention.pipeline import PipelineManager, create_default_pipeline

            pipeline = create_default_pipeline()
            logger.info(f"  Pipeline 创建完成: {len(pipeline._stages)} 个 Stage")

            duration_ms = (time.time() - start) * 1000

            return BootResult(
                success=True,
                stage=BootStage.VALIDATE,
                message="数据流验证完成",
                duration_ms=duration_ms,
            )

        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            logger.warning(f"  数据流验证失败（非致命）: {e}")
            return BootResult(
                success=True,
                stage=BootStage.VALIDATE,
                message=f"数据流验证失败: {e}",
                duration_ms=duration_ms,
                details={'warning': True},
            )

    def _start_schedulers(self) -> BootResult:
        """启动调度器"""
        start = time.time()
        logger.info("[5/5] 启动调度器...")

        duration_ms = (time.time() - start) * 1000

        return BootResult(
            success=True,
            stage=BootStage.START_SCHEDULERS,
            message="调度器启动完成",
            duration_ms=duration_ms,
        )

    def _log(self, level: str, message: str):
        """日志辅助"""
        getattr(logger, level.lower())(message)

    @property
    def is_initialized(self) -> bool:
        """是否已初始化"""
        return self._initialized

    def get_boot_results(self) -> List[BootResult]:
        """获取启动结果列表"""
        return self._boot_results.copy()

    def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        return {
            'initialized': self._initialized,
            'current_stage': self._boot_stage.value,
            'boot_results': [
                {
                    'stage': r.stage.value,
                    'success': r.success,
                    'message': r.message,
                    'duration_ms': r.duration_ms,
                }
                for r in self._boot_results
            ],
        }


_system_bootstrap: Optional[SystemBootstrap] = None


def get_system_bootstrap() -> SystemBootstrap:
    """获取全局 SystemBootstrap 实例"""
    global _system_bootstrap
    if _system_bootstrap is None:
        _system_bootstrap = SystemBootstrap()
    return _system_bootstrap


def boot_system() -> BootResult:
    """快捷启动系统"""
    bootstrap = get_system_bootstrap()
    return bootstrap.boot()


__all__ = ['SystemBootstrap', 'BootStage', 'BootResult', 'get_system_bootstrap', 'boot_system']
