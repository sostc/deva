"""SystemBootstrap - 系统启动引导器"""

import atexit
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, Any, List, Callable, Optional
from enum import Enum

from deva.naja.register import SR


logger = logging.getLogger(__name__)


def _record_system_sleep():
    """系统退出时记录休眠时间"""
    try:
        from deva.naja.register import SR
        state_mgr = SR('system_state_manager')
        state_mgr.record_sleep()
        logger.info("[SystemBootstrap] 已记录系统休眠时间")
    except Exception as e:
        logger.warning(f"[SystemBootstrap] 记录休眠时间失败: {e}")


class BootStage(Enum):
    """启动阶段"""
    INIT = "init"
    REGISTER_SINGLETONS = "register_singletons"
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
        self._force_realtime = False
        self._lab_mode = False

        atexit.register(_record_system_sleep)

    def set_attention_config(self, force_realtime: bool = False, lab_mode: bool = False):
        """设置注意力系统配置"""
        self._force_realtime = force_realtime
        self._lab_mode = lab_mode
        logger.info(f"[SystemBootstrap] 设置注意力配置: force_realtime={force_realtime}, lab_mode={lab_mode}")

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

            self._boot_stage = BootStage.REGISTER_SINGLETONS
            self._merge_details(self._register_singletons())

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

    def _register_singletons(self) -> BootResult:
        """注册所有单例"""
        start = time.time()
        logger.info("[1/8] 注册所有单例...")

        try:
            from deva.naja.register import register_all_singletons

            register_all_singletons()

            duration_ms = (time.time() - start) * 1000
            # 应用猴子补丁兼容模式 - 让旧代码无需修改即可使用新单例注册表
            from deva.naja.common.singleton_registry import apply_compatibility_patches
            apply_compatibility_patches()

            logger.info(f"  单例注册完成，耗时 {duration_ms:.1f}ms")

            return BootResult(
                success=True,
                stage=BootStage.REGISTER_SINGLETONS,
                message="单例注册完成",
                duration_ms=duration_ms,
            )

        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            logger.error(f"  单例注册失败: {e}")
            raise

    def _load_persistent_data(self) -> BootResult:
        """加载持久化数据"""
        start = time.time()
        logger.info("[2/8] 加载持久化数据...")

        try:
            from deva.naja.datasource import get_datasource_manager
            from deva.naja.strategy import get_strategy_manager
            from deva.naja.register import SR

            dict_mgr = SR('dictionary_manager')
            dict_mgr._ensure_initialized()
            ds_mgr = get_datasource_manager()
            ds_mgr._ensure_initialized()
            task_mgr = SR('task_manager')
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

            # 可选健康检查：字典题材
            if "dictionary" in counts and counts["dictionary"] > 0:
                try:
                    entry = dict_mgr.get_by_name("通达信概念题材")
                    if entry:
                        payload = entry.get_payload()
                        if payload is not None:
                            logger.info(f"  题材字典数据: {payload.shape}")
                        else:
                            logger.warning("  题材字典数据为空")
                    else:
                        logger.warning("  未找到通达信概念题材字典")
                except Exception as e:
                    logger.warning(f"  题材字典健康检查失败: {e}")

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
        logger.info("[3/8] 初始化核心组件...")

        details = {}

        try:
            from deva.naja.attention import get_trading_center

            trading_center = get_trading_center()
            logger.info("  TradingCenter 初始化完成")
            details["trading_center"] = "ok"
        except Exception as e:
            logger.warning(f"  TradingCenter 初始化失败: {e}")

        # 初始化美林时钟引擎
        try:
            from deva.naja.cognition.merrill_clock import initialize_merrill_clock

            clock_engine = initialize_merrill_clock()
            logger.info("  MerrillClockEngine 初始化完成")
            details["merrill_clock"] = "ok"
        except Exception as e:
            logger.warning(f"  MerrillClockEngine 初始化失败: {e}")
            details["merrill_clock_error"] = str(e)

        duration_ms = (time.time() - start) * 1000

        return BootResult(
            success=True,
            stage=BootStage.INIT_CORE,
            message="核心组件初始化完成",
            duration_ms=duration_ms,
            details=details,
        )

    def _register_components(self) -> BootResult:
        """注册组件"""
        start = time.time()
        logger.info("[4/8] 注册组件...")

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
        logger.info("[5/8] 恢复运行状态...")

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
        logger.info("[6/8] 验证数据流...")

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
        logger.info("[7/8] 启动调度器...")

        details: Dict[str, Any] = {}
        try:
            from deva.naja.supervisor import start_supervisor
            start_supervisor(force_realtime=self._force_realtime, lab_mode=self._lab_mode)
            details["supervisor"] = "started"
            logger.info("  Supervisor 已启动")
        except Exception as e:
            details["supervisor_error"] = str(e)
            logger.warning(f"  Supervisor 启动失败: {e}")

        try:
            from deva.naja.strategy.daily_review_scheduler import get_daily_review_scheduler
            scheduler = get_daily_review_scheduler()
            scheduler.start()
            details["daily_review_scheduler"] = "started"
            logger.info("  DailyReviewScheduler 已启动")
        except Exception as e:
            details["daily_review_scheduler_error"] = str(e)
            logger.warning(f"  DailyReviewScheduler 启动失败: {e}")

        # 启动美林时钟经济数据定时更新
        try:
            task_mgr = SR('task_manager')
            
            # 检查是否已有美林时钟任务
            existing = task_mgr.get_by_name("merrill_clock_update")
            if not existing:
                # 创建日频经济数据更新任务（每天凌晨 4:30 执行，获取最新数据）
                import hashlib
                task_id = hashlib.md5("merrill_clock_update_2026".encode()).hexdigest()[:12]
                
                func_code = '''
import logging
import asyncio
import nest_asyncio
log = logging.getLogger(__name__)

def execute() -> dict:
    """获取经济数据并更新美林时钟"""
    log.info("[MerrillClockTask] 开始获取经济数据...")
    
    try:
        from deva.naja.cognition.economic_data_fetcher import EconomicDataFetcher
        from deva.naja.cognition.merrill_clock import get_merrill_clock_engine
        
        fred_api_key = "f48d2328888b60cb2d188c148da31f63"
        fetcher = EconomicDataFetcher(fred_api_key=fred_api_key, use_mock=False)
        
        nest_asyncio.apply()
        
        async def _fetch():
            data = await fetcher.fetch_latest_data()
            await fetcher.close()
            return data
        
        data = asyncio.run(_fetch())
        log.info(f"[MerrillClockTask] 获取经济数据成功")
        
        clock_engine = get_merrill_clock_engine()
        signal = clock_engine.on_economic_data(data)
        
        if signal:
            log.info(f"[MerrillClockTask] 周期阶段：{signal.phase.value}, 置信度：{signal.confidence:.0%}")
            return {
                "success": True,
                "phase": signal.phase.value,
                "confidence": round(signal.confidence, 3),
                "growth_score": round(signal.growth_score, 3),
                "inflation_score": round(signal.inflation_score, 3),
            }
        else:
            return {"success": False, "message": "数据不足"}
            
    except Exception as e:
        log.error(f"[MerrillClockTask] 执行失败：{e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "message": str(e)}
'''
                
                result = task_mgr.create(
                    name="merrill_clock_update",
                    description="美林时钟经济数据定时更新（每日凌晨执行）",
                    func_code=func_code,
                    task_type="scheduler",
                    scheduler_trigger="cron",
                    cron_expr="30 4 * * *",  # 每天凌晨 4:30
                    tags=["merrill_clock", "economic", "daily"],
                )
                
                if result.get("success"):
                    entry_id = result.get("id")
                    task_mgr.start(entry_id)
                    details["merrill_clock_task"] = f"created_and_started({entry_id})"
                    logger.info(f"  美林时钟定时任务已创建并启动: {entry_id}")
                else:
                    details["merrill_clock_task_error"] = result.get("error")
                    logger.warning(f"  美林时钟定时任务创建失败: {result.get('error')}")
            else:
                # 已存在，直接启动
                if not existing.is_running:
                    task_mgr.start(existing.id)
                details["merrill_clock_task"] = f"already_exists({existing.id}), started={existing.is_running}"
                logger.info(f"  美林时钟定时任务已存在，直接启动")
                
        except Exception as e:
            details["merrill_clock_task_error"] = str(e)
            logger.warning(f"  美林时钟定时任务启动失败: {e}")

        # 心跳机制：定期更新系统活跃时间
        try:
            task_mgr = SR('task_manager')

            heartbeat_code = '''
import logging
from deva.naja.register import SR
log = logging.getLogger(__name__)

def execute() -> dict:
    """心跳：更新系统活跃时间"""
    try:
        state_mgr = SR('system_state_manager')
        state_mgr.record_active()
        log.info("[Heartbeat] 系统活跃时间已更新")
        return {"success": True}
    except Exception as e:
        log.warning(f"[Heartbeat] 更新活跃时间失败: {e}")
        return {"success": False, "error": str(e)}
'''
            existing_heartbeat = task_mgr.get_by_name("system_heartbeat")
            if not existing_heartbeat:
                import hashlib
                task_id = hashlib.md5("system_heartbeat_2026".encode()).hexdigest()[:12]

                result = task_mgr.create(
                    name="system_heartbeat",
                    description="系统心跳（定期更新活跃时间）",
                    func_code=heartbeat_code,
                    task_type="scheduler",
                    scheduler_trigger="interval",
                    interval_seconds=300,
                    tags=["system", "heartbeat"],
                )

                if result.get("success"):
                    entry_id = result.get("id")
                    task_mgr.start(entry_id)
                    details["heartbeat_task"] = f"created_and_started({entry_id})"
                    logger.info(f"  系统心跳任务已创建并启动: {entry_id}")
            else:
                if not existing_heartbeat.is_running:
                    task_mgr.start(existing_heartbeat.id)
                details["heartbeat_task"] = f"already_exists({existing_heartbeat.id})"
                logger.info(f"  系统心跳任务已存在")

        except Exception as e:
            details["heartbeat_task_error"] = str(e)
            logger.warning(f"  系统心跳任务启动失败: {e}")

        # 统一唤醒同步检查
        try:

            state_mgr = SR('system_state_manager')
            state_mgr.record_wake()

            state_summary = state_mgr.get_state_summary()
            logger.info(f"  [WakeSync] 系统状态: 休眠 {state_summary['sleep_duration_hours']} 小时")

            if state_summary['sleep_duration_hours'] < 1:
                logger.info(f"  [WakeSync] 休眠不足1小时，跳过同步")
            else:
                wake_sync_mgr = SR('wake_sync_manager')
                registered = wake_sync_mgr.get_registered_components()
                logger.info(f"  [WakeSync] 已注册 {len(registered)} 个同步组件: {registered}")

                last_active = state_mgr.get_last_active_time()
                if last_active:
                    wake_sync_result = wake_sync_mgr.perform_wake_sync(last_active)
                    details["wake_sync_summary"] = wake_sync_result
                    logger.info(f"  [WakeSync] 同步结果: {wake_sync_result.get('message', '未知')}")

        except Exception as e:
            details["wake_sync_error"] = str(e)
            logger.warning(f"  统一唤醒同步检查失败: {e}")

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
