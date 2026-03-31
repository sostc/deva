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
    RESTORE_RUNTIME = "restore_runtime"
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
        self._boot_details: Dict[str, Any] = {}

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
            self._merge_details(self._load_persistent_data())

            self._boot_stage = BootStage.INIT_CORE
            self._merge_details(self._init_core_components())

            self._boot_stage = BootStage.REGISTER_COMPONENTS
            self._merge_details(self._register_components())

            self._boot_stage = BootStage.RESTORE_RUNTIME
            self._merge_details(self._restore_runtime_states())

            self._boot_stage = BootStage.VALIDATE
            self._merge_details(self._validate_pipeline())

            self._boot_stage = BootStage.START_SCHEDULERS
            self._merge_details(self._start_schedulers())

            self._boot_stage = BootStage.READY
            self._initialized = True

            duration_ms = (time.time() - start_time) * 1000
            logger.info(f"系统启动完成，耗时 {duration_ms:.1f}ms")

            result = BootResult(
                success=True,
                stage=BootStage.READY,
                message="系统启动成功",
                duration_ms=duration_ms,
                details=dict(self._boot_details),
            )
            _set_last_boot_report(result)
            return result

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.exception(f"系统启动失败: {e}")

            result = BootResult(
                success=False,
                stage=self._boot_stage,
                message=f"启动失败: {e}",
                duration_ms=duration_ms,
                error=str(e),
                details=dict(self._boot_details),
            )
            _set_last_boot_report(result)
            return result

    def _load_persistent_data(self) -> BootResult:
        """加载持久化数据"""
        start = time.time()
        logger.info("[1/6] 加载持久化数据...")

        try:
            from deva.naja.dictionary import get_dictionary_manager
            from deva.naja.datasource import get_datasource_manager
            from deva.naja.tasks import get_task_manager
            from deva.naja.strategy import get_strategy_manager

            dict_mgr = get_dictionary_manager()
            dict_mgr._ensure_initialized()
            ds_mgr = get_datasource_manager()
            ds_mgr._ensure_initialized()
            task_mgr = get_task_manager()
            task_mgr._ensure_initialized()
            strategy_mgr = get_strategy_manager()
            strategy_mgr._ensure_initialized()

            counts: Dict[str, int] = {}
            errors: Dict[str, str] = {}

            # 先加载字典（可能被策略/数据源引用）
            # 优先从文件加载，NB 数据作为兜底
            try:
                counts["dictionary"] = dict_mgr.load_prefer_files()
                logger.info(f"  加载了 {counts['dictionary']} 个字典（优先文件）")
            except Exception as e:
                errors["dictionary"] = str(e)
                logger.warning(f"  字典加载失败: {e}")

            # 依赖字典之后再加载其他组件
            # 优先从文件加载，NB 数据作为兜底
            for name, mgr in (
                ("datasource", ds_mgr),
                ("task", task_mgr),
                ("strategy", strategy_mgr),
            ):
                try:
                    if hasattr(mgr, 'load_prefer_files'):
                        counts[name] = mgr.load_prefer_files()
                        logger.info(f"  加载了 {counts[name]} 个{name}（优先文件）")
                    else:
                        counts[name] = mgr.load_from_db()
                        logger.info(f"  加载了 {counts[name]} 个{name}")
                except Exception as e:
                    errors[name] = str(e)
                    logger.warning(f"  {name} 加载失败: {e}")

            # 可选健康检查：字典板块
            if "dictionary" in counts and counts["dictionary"] > 0:
                try:
                    entry = dict_mgr.get_by_name("通达信概念板块")
                    if entry:
                        payload = entry.get_payload()
                        if payload is not None:
                            logger.info(f"  板块字典数据: {payload.shape}")
                        else:
                            logger.warning("  板块字典数据为空")
                    else:
                        logger.warning("  未找到通达信概念板块字典")
                except Exception as e:
                    logger.warning(f"  板块字典健康检查失败: {e}")

            duration_ms = (time.time() - start) * 1000

            return BootResult(
                success=True,
                stage=BootStage.LOAD_PERSISTENT,
                message="持久化加载完成",
                duration_ms=duration_ms,
                details={
                    "load_counts": counts,
                    "load_errors": errors,
                },
            )

        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            logger.error(f"  加载持久化数据失败: {e}")
            raise

    def _init_core_components(self) -> BootResult:
        """初始化核心组件"""
        start = time.time()
        logger.info("[2/6] 初始化核心组件...")

        try:
            from deva.naja.attention import AttentionCenter, initialize_orchestrator

            orchestrator = initialize_orchestrator()
            logger.info("  AttentionCenter 初始化完成")

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
        logger.info("[3/6] 注册组件...")

        try:
            from deva.naja.signal.stream import get_signal_stream
            get_signal_stream()
            logger.info("  SignalStream 初始化完成")
        except Exception as e:
            logger.warning(f"  SignalStream 初始化失败: {e}")

        duration_ms = (time.time() - start) * 1000

        return BootResult(
            success=True,
            stage=BootStage.REGISTER_COMPONENTS,
            message="组件注册完成",
            duration_ms=duration_ms,
        )

    def _restore_runtime_states(self) -> BootResult:
        """恢复运行时状态"""
        start = time.time()
        logger.info("[4/6] 恢复运行状态...")

        try:
            from deva.naja.runtime_state import register_all_adapters, load_all_state

            register_all_adapters()
            result = load_all_state()

            duration_ms = (time.time() - start) * 1000

            return BootResult(
                success=True,
                stage=BootStage.RESTORE_RUNTIME,
                message=f"运行状态恢复完成: {result['success']}/{result['total']} 成功",
                duration_ms=duration_ms,
                details={
                    "total": result.get("total", 0),
                    "success": result.get("success", 0),
                    "failed": result.get("failed", 0),
                },
            )
        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            logger.warning(f"  恢复运行状态失败（非致命）: {e}")
            return BootResult(
                success=True,
                stage=BootStage.RESTORE_RUNTIME,
                message=f"运行状态恢复失败: {e}",
                duration_ms=duration_ms,
                details={"warning": True},
            )

    def _validate_pipeline(self) -> BootResult:
        """验证数据流"""
        start = time.time()
        logger.info("[5/6] 验证数据流...")

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
        logger.info("[6/6] 启动调度器...")

        details: Dict[str, Any] = {}
        try:
            from deva.naja.supervisor import start_supervisor
            start_supervisor()
            details["supervisor"] = "started"
            logger.info("  Supervisor 已启动")
        except Exception as e:
            details["supervisor_error"] = str(e)
            logger.warning(f"  Supervisor 启动失败: {e}")

        try:
            from deva.naja.strategy.market_replay_scheduler import get_replay_scheduler
            scheduler = get_replay_scheduler()
            scheduler.start()
            details["market_replay_scheduler"] = "started"
            logger.info("  MarketReplayScheduler 已启动")
        except Exception as e:
            details["market_replay_scheduler_error"] = str(e)
            logger.warning(f"  MarketReplayScheduler 启动失败: {e}")

        duration_ms = (time.time() - start) * 1000

        return BootResult(
            success=True,
            stage=BootStage.START_SCHEDULERS,
            message="调度器启动完成",
            duration_ms=duration_ms,
            details=details,
        )

    def _log(self, level: str, message: str):
        """日志辅助"""
        getattr(logger, level.lower())(message)

    def _merge_details(self, result: BootResult):
        """合并阶段详情"""
        if result and result.details:
            self._boot_details.update(result.details)


_last_boot_report: Optional[BootResult] = None
_last_boot_report_ts: float = 0.0


def _set_last_boot_report(result: BootResult):
    global _last_boot_report, _last_boot_report_ts
    _last_boot_report = result
    _last_boot_report_ts = time.time()


def get_last_boot_report() -> Dict[str, Any]:
    """获取最近一次启动报告"""
    if _last_boot_report is None:
        return {}
    return {
        "success": _last_boot_report.success,
        "stage": _last_boot_report.stage.value,
        "message": _last_boot_report.message,
        "duration_ms": _last_boot_report.duration_ms,
        "error": _last_boot_report.error,
        "details": _last_boot_report.details,
        "ts": _last_boot_report_ts,
    }

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
