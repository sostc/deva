from __future__ import annotations

import logging
import time
from typing import Any, Optional

from .runtime_config import AppRuntimeConfig
from .runtime_modes import RuntimeModeInitializer
from ..register import SR

log = logging.getLogger(__name__)


class BootStage:
    """启动阶段枚举"""
    INIT = "init"
    REGISTER_SINGLETONS = "register_singletons"
    LOAD_PERSISTENT = "load_persistent"
    INIT_CORE = "init_core"
    REGISTER_COMPONENTS = "register_components"
    RESTORE_RUNTIME = "restore_runtime"
    START_SCHEDULERS = "start_schedulers"
    READY = "ready"


# 全局启动报告（供 health_ui 等使用）
_last_boot_report: dict[str, Any] = {}
_last_boot_report_ts: float = 0.0


def get_last_boot_report() -> dict[str, Any]:
    """获取最近一次启动报告"""
    return _last_boot_report


def _record_boot_report(report: dict[str, Any]):
    """记录启动报告"""
    global _last_boot_report, _last_boot_report_ts
    _last_boot_report = report
    _last_boot_report_ts = time.time()


class AppContainer:
    """Composition root for Naja runtime assembly."""

    def __init__(self, config: AppRuntimeConfig):
        self.config = config
        
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
        self._market_time_service = None
        self._virtual_portfolio = None
        self._bandit_tracker = None
        self._manas_engine = None
        self._manas_manager = None
        
        # 认知层组件
        self._insight_pool = None
        self._insight_engine = None
        self._cognition_engine = None
        self._llm_reflection_engine = None
        
        # Bandit 模块组件
        self._bandit_optimizer = None
        self._portfolio_manager = None
        self._market_observer = None
        self._signal_listener = None
        self._bandit_runner = None
        self._adaptive_cycle = None
        
        # Radar 模块组件
        self._radar_engine = None

        # Structural Growth Radar 模块组件
        self._structural_growth_pool = None

        # Infra 组件（懒加载）
        self._task_manager = None
        self._system_state_manager = None
        self._dictionary_manager = None
        self._attention_integration = None

        # 初始化标记
        self._components_assembled = False

    def boot(self):
        """Complete bootstrap: registers everything, assembles components, and records boot report."""
        from ..infra.observability.startup_timer import StartupTimer

        StartupTimer.reset()
        start = time.time()
        set_app_container(self)

        StartupTimer.start("注册单例")
        self._register_singletons()
        StartupTimer.end("注册单例")

        StartupTimer.start("装配核心组件")
        self._assemble_core_components()
        StartupTimer.end("装配核心组件")

        StartupTimer.start("将容器组件注册到单例注册表")
        self._register_container_components_as_singletons()
        StartupTimer.end("将容器组件注册到单例注册表")

        StartupTimer.start("注册健康检查项")
        self._register_health_checks()
        StartupTimer.end("注册健康检查项")

        StartupTimer.start("恢复运行状态")
        self.restore_runtime_state()
        StartupTimer.end("恢复运行状态")

        duration = (time.time() - start) * 1000
        _record_boot_report({
            "success": True,
            "stage": BootStage.READY,
            "message": "AppContainer 初始化完成",
            "duration_ms": duration,
        })

        from deva.naja.infra.log.colorful_logger import StartupVisualizer
        sv = StartupVisualizer(width=60)

        with sv.section('📦 加载组件'):
            counts = self._load_counts
            if counts.get('datasource'):
                sv.item('datasource_manager', '✓', f"{counts.get('datasource', 0)} 个")
            if counts.get('task'):
                sv.item('task_manager', '✓', f"{counts.get('task', 0)} 个")
            if counts.get('strategy'):
                sv.item('strategy_manager', '✓', f"{counts.get('strategy', 0)} 个")

        sv.success(f"AppContainer 初始化完成，耗时 {duration:.0f}ms")

        log.info(StartupTimer.get_report())

    def _register_singletons(self):
        """注册声明式单例（来自 register.py 的 SIMPLE_SINGLETONS + 自定义工厂）。

        此步骤只做"工厂函数注册"，不实例化任何对象。核心组件的实例由
        AppContainer 自己创建（_assemble_core_components），之后在
        _register_container_components_as_singletons 中把 container 已经
        创建好的对象"覆盖注册"到 SingletonRegistry，从而让新旧代码都
        访问同一份实例。
        """
        from ..register import register_all_singletons
        register_all_singletons()

    def _register_container_components_as_singletons(self):
        """将 AppContainer 自己创建好的核心组件注册到 SingletonRegistry。

        这样无论调用方是用 container.xxx 还是 SR('xxx')，都是访问同一份实例。
        """
        from ..infra.registry.singleton_registry import register_singleton

        # 收集所有已实例化的核心组件（包括 property 懒加载触发后的）
        components = {
            # ── 基础组件 ──
            "trading_clock": self._trading_clock,
            # ❗不要把 market_time_service 别名到 _trading_clock。
            # 两者是两套互不相通的接口：
            #   MarketTimeService -> get_market_time / get_market_datetime / set_replay_mode
            #   TradingClock      -> cn_phase / us_phase / get_global_status
            # TradingClock **没有** get_market_time()。此处曾写成
            #   "market_time_service": self._trading_clock,  # 别名：旧代码可能用这个名
            # 导致 SR('market_time_service').get_market_time() 必然 AttributeError，
            # 直接表现为 /banditadmin 打开即 "Unhandled error in pywebio app"
            # （VirtualPosition.holding_seconds 是唯一未被 try 包住的消费点），
            # 并让 market_hotspot 的回放时间/回放模式静默降级为系统时间。
            # 该名字由 register.py 的声明式表注册为真正的 MarketTimeService，
            # 这里保持不覆盖即可。
            "virtual_portfolio": self._virtual_portfolio,
            "value_system": self._value_system,
            # ── Attention Kernel / OS ──
            "attention_os": self._attention_os,
            "query_state": self._query_state,
            "query_state_updater": self._query_state_updater,
            "manas_manager": self._manas_manager,
            # ── 持久化管理器 ──
            "dictionary_manager": self._dictionary_manager,
            "task_manager": self._task_manager,
            "system_state_manager": self._system_state_manager,
            # ── 懒加载：如果 property 已访问（非 None）则注册；否则注册为懒加载工厂
            "attention_integration": self._attention_integration,
            "trading_center": self._trading_center,
            "insight_pool": self._insight_pool,
            "insight_engine": self._insight_engine,
            "cognition_engine": self._cognition_engine,
            "llm_reflection_engine": self._llm_reflection_engine,
            "radar_engine": self._radar_engine,
            "bandit_optimizer": self._bandit_optimizer,
            "portfolio_manager": self._portfolio_manager,
            "bandit_tracker": self._bandit_tracker,
            "market_observer": self._market_observer,
            "signal_listener": self._signal_listener,
            "bandit_runner": self._bandit_runner,
            "adaptive_cycle": self._adaptive_cycle,
            # ── Structural Growth Radar ──
            "structural_growth_pool": self._structural_growth_pool,
        }

        container_ref = self
        for name, instance in components.items():
            if instance is not None:
                # 已初始化：直接返回实例（用 default 参数避免闭包变量问题）
                register_singleton(name, lambda _i=instance: _i)
            else:
                # 未初始化：用 property 做懒加载
                register_singleton(
                    name,
                    lambda _n=name, _c=container_ref: getattr(_c, _n, None),
                )

        # 把 AppContainer 自己也注册成 'app_container' 单例
        register_singleton("app_container", lambda: self)

    def _register_health_checks(self) -> None:
        """把子系统的健康检查项注册进全局 HealthCheckManager。

        HealthCheckManager 此前从来没被接通过：全仓搜 `manager.register(`
        只出现在它自己 docstring 的用法示例里，生产代码一个调用点都没有；
        配套的 create_attention_health_checks() 同样是定义了却无人使用。
        结果 check_all() 恒返回空 dict，/health 的「健康检查中心」面板永远
        显示 ❓ UNKNOWN / "No components registered" / 总组件 0 —— UI 写好了，
        注册链路没接，和 945c108 修的那类死面板同一病因。

        注册进去的是**惰性**可调用对象：真正的检查在每次渲染面板时才执行，
        拿到的是运行时真实状态，而不是启动那一刻的快照。也正因此，
        这里必须小心别在检查函数里触发重型构造。
        """
        from ..infra.observability.health import (
            create_attention_health_checks,
            get_health_check_manager,
        )

        manager = get_health_check_manager()

        # 幂等：重复 boot 时不叠加同名组件（register 是覆盖语义，这里显式
        # 先清一遍，避免把「这次没注册到」误读成「上一轮还在」）
        for name in ("attention", "core", "tasks"):
            manager.unregister(name)

        # ① 注意力子系统（已有现成的检查项工厂）
        manager.register("attention", create_attention_health_checks())

        # ② 容器核心组件是否真的装配出来了
        #    都是 boot 期间必定赋值的字段，检查只读不构造
        core_checks = {
            "attention_os": lambda: self._attention_os is not None,
            "task_manager": lambda: self._task_manager is not None,
            "trading_clock": lambda: self._trading_clock is not None,
        }
        manager.register("core", core_checks)

        # ③ 定时调度的心跳必须在跳。
        #
        # 靶子是 scheduler.common.SchedulerManager —— Naja 的定时任务统一由这个
        # 共享管理器驱动（naja/tasks/entry.py 的 _start_timer / _start_scheduler
        # 都走它）。不要去查 admin TaskManager 里那个 APScheduler：那是管理后台
        # 任务注册表的，Naja 主进程压根不启动它，查它只会得到一个恒红的假告警。
        #
        # 只读 _scheduler 而不调 get_scheduler()：后者有「不存在就创建并启动」
        # 的副作用，健康检查不该把没在跑的东西启动起来。
        #
        # 判定方式也是踩出来的：这个 scheduler 是 deva/core/when.py 里的自研
        # 流式调度器，**没有 running 属性**，用 getattr(s, "running", False)
        # 判活必然恒 False（第一版就栽在这，恒红假告警）。它表达存活的方式是
        # 内部的 asyncio 事件循环 —— loop.asyncio_loop.is_running()。
        def check_shared_scheduler():
            from deva.naja.scheduler.common import SchedulerManager

            scheduler = getattr(SchedulerManager(), "_scheduler", None)
            if scheduler is None:
                return False
            asyncio_loop = getattr(getattr(scheduler, "loop", None), "asyncio_loop", None)
            if asyncio_loop is None:
                return False
            is_running = getattr(asyncio_loop, "is_running", None)
            return bool(is_running and is_running())

        def check_jobs_registered():
            """至少有一个作业/定时器在册（两条注册路径都算）。"""
            from deva.naja.scheduler.common import SchedulerManager

            shared = SchedulerManager()
            scheduler = getattr(shared, "_scheduler", None)
            jobs = scheduler.get_jobs() if scheduler is not None and hasattr(scheduler, "get_jobs") else []
            handles = getattr(shared, "_timer_handles", None) or {}
            return len(jobs) + len(handles) > 0

        manager.register("tasks", {
            "shared_scheduler": check_shared_scheduler,
            "jobs_registered": check_jobs_registered,
        })

    def _assemble_core_components(self) -> None:
        """装配核心组件（显式依赖注入）"""
        if self._components_assembled:
            return
        if getattr(self, '_assembling_core', False):
            return
        self._assembling_core = True

        from ..infra.observability.startup_timer import StartupTimer

        try:
            StartupTimer.start("加载持久化管理器")
            self._load_persistent_managers()
            StartupTimer.end("加载持久化管理器")

            StartupTimer.start("创建基础组件")
            self._trading_clock = self._create_trading_clock()
            self._market_time_service = self._create_market_time_service()
            self._virtual_portfolio = self._create_virtual_portfolio()
            self._virtual_portfolio.set_market_time_service(self._market_time_service)
            self._value_system = self._create_value_system()
            StartupTimer.end("创建基础组件")

            StartupTimer.start("创建 AttentionOS")
            self._attention_os = self._create_attention_os()
            StartupTimer.end("创建 AttentionOS")

            StartupTimer.start("创建 Kernel 层组件")
            self._query_state = self._create_query_state()
            self._query_state_updater = self._create_query_state_updater()
            self._manas_manager = self._create_manas_manager()
            self._manas_engine = self._manas_manager.get_manas_engine()
            # 注意：只注入 provider，不在这里拉取快照——真正的拉取发生在
            # 每条新闻评分时（惰性），避免开局就触发 NB 读表。
            self._wire_news_focus_provider()
            # 按持仓推导关注主题（用户选定「自动采纳」档位）。后台线程执行，
            # 要读 NB + 供应链图谱，不该拖慢启动。
            self._bootstrap_derived_topics()
            StartupTimer.end("创建 Kernel 层组件")

            # 基础组件就绪后立即标记，防止 property 递归
            self._components_assembled = True

            # 4. 获取认知层组件（延迟加载，使用时再获取）
            # self._insight_pool = SR('insight_pool')
            # self._insight_engine = SR('insight_engine')
            # self._cognition_engine = SR('cognition_engine')

            # 5. 获取 Bandit 模块组件（延迟加载）
            # self._bandit_optimizer = SR('bandit_optimizer')
            # self._portfolio_manager = SR('portfolio_manager')
            # self._bandit_tracker = SR('bandit_tracker')
            # self._market_observer = SR('market_observer')
            # self._signal_listener = SR('signal_listener')
            # self._bandit_runner = SR('bandit_runner')
            # self._adaptive_cycle = SR('adaptive_cycle')

            # 6. 获取 TradingCenter（延迟加载）
            # self._trading_center = SR('trading_center')

            # 7. 获取 Radar 模块组件（延迟加载）
            # self._radar_engine = SR('radar_engine')

            # 8. 初始化 SignalStream（延迟加载）
            # try:
            #     from ..signal.stream import get_signal_stream
            #     get_signal_stream()
            #     log.info("[AppContainer] SignalStream 初始化完成")
            # except Exception as e:
            #     log.warning(f"[AppContainer] SignalStream 初始化失败: {e}")

            # 初始化 MerrillClock（延迟加载）
            # try:
            #     from ..cognition.merrill_clock import initialize_merrill_clock
            #     initialize_merrill_clock()
            #     log.info("[AppContainer] MerrillClock 初始化完成")
            # except Exception as e:
            #     log.warning(f"[AppContainer] MerrillClock 初始化失败: {e}")

            # 9. 事件订阅装配（必需）
            self._event_registrar = self._create_event_registrar()
            self._event_registrar.register_all()

            # 9b. 认知↔交易桥梁装配。
            # ❗此前本模块**从未被实例化**（全库无调用方，enable_bridge(True) 只存在
            # 于 docstring 示例）→ 四条转换规则永不执行。这里接上装配点，
            # 但**默认仍关闭**：开关是 NAJA_BUS_BRIDGE=1，原因是「叙事/板块 →
            # 买还是卖」的方向口径没有权威依据（见 events/bus_bridge.py 模块 docstring）。
            # 无论开关如何都会打印一行状态，避免又变成「只能靠读代码才知道」。
            try:
                from ..events.bus_bridge import enable_bridge_from_env
                enable_bridge_from_env()
            except Exception as e:
                log.warning(f"[AppContainer] BusBridge 装配失败: {e}")

            # 10. 装配 SignalExecutor 依赖
            try:
                from ..attention.orchestration.signal_executor import get_signal_executor
                executor = get_signal_executor()
                executor.set_insight_pool(self.insight_pool)
            except Exception as e:
                log.warning(f"[AppContainer] SignalExecutor 依赖注入失败: {e}")

            # 11. 装配 StateQuerier 依赖
            try:
                from ..attention.orchestration.state_querier import get_state_querier
                querier = get_state_querier()
                querier.set_trading_clock(self._trading_clock)
            except Exception as e:
                log.warning(f"[AppContainer] StateQuerier 依赖注入失败: {e}")

            # 12. 装配 CognitionIngestion 依赖
            try:
                from ..cognition.ingestion import get_cognition_ingestion
                ingestion = get_cognition_ingestion()
                ingestion.set_insight_pool(self.insight_pool)
            except Exception as e:
                log.warning(f"[AppContainer] CognitionIngestion 依赖注入失败: {e}")

            # 13. 洞察池 → 认知洞察事件（否则 QueryState.cognitive_insights 永远空）
            try:
                self._wire_insight_pool_events()
            except Exception as e:
                log.warning(f"[AppContainer] 洞察事件接线失败: {e}")
            
            # 10. 启动调度器（延迟加载，只启动核心调度器）
            # self._start_schedulers()
            
            # 11. 启动后台初始化线程
            self._start_background_initialization()
            
            log.info("[AppContainer] 核心组件装配完成（延迟加载模式）")
            
        except Exception as e:
            self._components_assembled = True
            log.error(f"[AppContainer] 组件装配失败: {e}", exc_info=True)


    def _load_persistent_managers(self):
        """加载持久化数据管理器（并行版本）"""
        from ..datasource import get_datasource_manager
        from ..strategy import get_strategy_manager
        import concurrent.futures
        from ..infra.observability.startup_timer import StartupTimer

        StartupTimer.start("持久化管理器初始化")
        import concurrent.futures

        def _init_dict():
            StartupTimer.start("字典管理器初始化")
            dict_mgr = self.dictionary_manager
            dict_mgr._ensure_initialized()
            StartupTimer.end("字典管理器初始化")
            return ("dictionary", dict_mgr)

        def _init_ds():
            StartupTimer.start("数据源管理器初始化")
            ds_mgr = get_datasource_manager()
            ds_mgr._ensure_initialized()
            StartupTimer.end("数据源管理器初始化")
            return ("datasource", ds_mgr)

        def _init_task():
            StartupTimer.start("任务管理器初始化")
            task_mgr = self.task_manager
            task_mgr._ensure_initialized()
            StartupTimer.end("任务管理器初始化")
            return ("task", task_mgr)

        def _init_strategy():
            StartupTimer.start("策略管理器初始化")
            strategy_mgr = get_strategy_manager()
            strategy_mgr._ensure_initialized()
            StartupTimer.end("策略管理器初始化")
            return ("strategy", strategy_mgr)

        counts = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = [
                executor.submit(_init_dict),
                executor.submit(_init_ds),
                executor.submit(_init_task),
                executor.submit(_init_strategy),
            ]
            for future in concurrent.futures.as_completed(futures):
                try:
                    name, mgr = future.result()
                    counts[name] = len(mgr._items)
                except Exception as e:
                    log.warning(f"[AppContainer] 初始化任务管理器失败: {e}")

        StartupTimer.end("持久化管理器初始化")
        self._load_counts = counts
        self._load_errors = {}

    def _start_schedulers(self):
        """启动调度器

        ❗**每一段都必须留「开始 / ✓结束」两行日志**。
        事故（2026-10-15 11:26 / 11:51 两代进程）：做 T 启动之后到「调度器启动
        完成」之间**一行日志都没有**，于是守望台（IntentRunner）静默未启动
        5.5 小时，事后只能靠「比对哪些日志缺行」反推卡点。留痕之后，卡在哪一段
        一眼可见：只有「→ X」而没有「✓ X」的那一段就是卡点。
        """
        from contextlib import contextmanager
        from ..supervisor import start_supervisor
        from ..supervisor.monitoring import MonitoringMixin

        @contextmanager
        def _stage(name: str):
            t0 = time.monotonic()
            log.info("[AppContainer] 调度器启动 → %s", name)
            try:
                yield
            finally:
                log.info("[AppContainer] 调度器启动 ✓ %s（%.1fs）", name, time.monotonic() - t0)

        with _stage("Supervisor"):
            try:
                supervisor = start_supervisor()
                if isinstance(supervisor, MonitoringMixin):
                    supervisor._force_realtime = False
                    supervisor._lab_mode = None
                    supervisor.configure_attention(force_realtime=False, lab_mode=None)
            except Exception as e:
                log.warning(f"[AppContainer] Supervisor 启动失败: {e}", exc_info=True)

        with _stage("DailyReviewScheduler"):
            try:
                from ..strategy.daily_review_scheduler import get_daily_review_scheduler
                scheduler = get_daily_review_scheduler()
                scheduler.start()
            except Exception as e:
                log.warning(f"[AppContainer] DailyReviewScheduler 启动失败: {e}", exc_info=True)

        with _stage("TRotationRunner"):
            # 做 T 降本：长期持有芯片指数底仓 + 日内做 T，收盘前强制买回。
            # 注册到单例表不等于会跑 —— 这里必须显式 start()，否则整套模块
            # 会变成「代码是对的、守卫是绿的、但一条行情都没流过」的摆设。
            try:
                from ..bandit.t_rotation_runner import get_t_rotation_runner
                t_runner = get_t_rotation_runner()
                t_runner.start()
            except Exception as e:
                log.warning(f"[AppContainer] TRotationRunner 启动失败: {e}", exc_info=True)

        with _stage("IntentRunner（守望台）"):
            # 守望台：「想买但不知道什么时候下手」的人工意向也常驻盯盘。
            # ❗同样必须显式 start() —— 注册进单例表不等于会跑。
            # 启动时守望台是空的（意向由 UI / 命令行登记），所以这里起的是
            # **节拍与心跳**，真正的守望随后 declare 进来即可被扫到。
            try:
                from ..bandit.intent_runner import get_intent_runner
                intent_runner = get_intent_runner()
                intent_runner.start()
            except Exception as e:
                log.warning(f"[AppContainer] IntentRunner 启动失败: {e}", exc_info=True)

        with _stage("定时任务注册"):
            # 注册所有 TaskManager 管理的定时任务
            self._register_ai_daily_report_task()
            self._register_knowledge_injector_task()
            self._register_openrouter_monitor_task()
            self._register_news_digest_task()

            # 启动美林时钟经济数据定时更新
            self._start_merrill_clock_task()

            # 心跳机制：定期更新系统活跃时间
            self._start_heartbeat_task()

        with _stage("唤醒同步"):
            # 统一唤醒同步检查
            self._perform_wake_sync()

        log.info("[AppContainer] 调度器启动完成")

    #: 后台初始化的兜底等待上限（秒）。单项卡住时**不允许**它把后面所有步骤
    #: 一起吞掉。事故（2026-10-15 11:26 / 11:51 两代进程）：调度器链在
    #: IntentRunner 启动前静默卡死，守望台 5.5 小时未启动，而进程不退、
    #: 做 T 心跳照跳、API 可用、日志零异常 —— 根因是「全部并发项一起等且无超时」。
    #: 正常启动这几项都在数秒内完成，120s 不会误伤慢启动。
    BACKGROUND_INIT_TIMEOUT = 120.0

    def _start_background_initialization(self):
        """启动后台初始化线程，异步加载非关键组件（并行版本）"""
        import threading
        from ..infra.observability.startup_timer import StartupTimer

        def background_init():
            log.info("[AppContainer] 后台初始化线程启动（并行模式）")

            def init_attention_integration():
                try:
                    StartupTimer.start("后台初始化 attention_integration")
                    log.info("[AppContainer] 后台初始化: attention_integration")
                    attention_integration = self.attention_integration
                    attention_integration.ensure_initialized()
                    StartupTimer.end("后台初始化 attention_integration")
                    log.info("[AppContainer] attention_integration 初始化完成")
                except Exception as e:
                    log.warning(f"[AppContainer] attention_integration 初始化失败: {e}")

            def init_signal_stream():
                try:
                    log.info("[AppContainer] 后台初始化: SignalStream")
                    from ..signal.stream import get_signal_stream
                    get_signal_stream()
                    log.info("[AppContainer] SignalStream 初始化完成")
                except Exception as e:
                    log.warning(f"[AppContainer] SignalStream 初始化失败: {e}")

            def init_merrill_clock():
                try:
                    log.info("[AppContainer] 后台初始化: MerrillClock")
                    from ..cognition.merrill_clock import initialize_merrill_clock
                    initialize_merrill_clock()
                    log.info("[AppContainer] MerrillClock 初始化完成")
                except Exception as e:
                    log.warning(f"[AppContainer] MerrillClock 初始化失败: {e}")

            def init_schedulers():
                try:
                    log.info("[AppContainer] 后台初始化: 调度器")
                    self._start_schedulers()
                except Exception as e:
                    log.warning(f"[AppContainer] 调度器启动失败: {e}")

            def _timed(name, fn):
                """跑一项初始化并**两侧留痕**。

                ❗「只有开始、没有结束」的那一项就是卡住的那一项。
                此前 4 项并发初始化全程只有零散日志，一个卡住就只能靠比对缺行反推。
                """
                t0 = time.monotonic()
                log.info("[AppContainer] 后台初始化开始: %s", name)
                try:
                    fn()
                except Exception as e:  # noqa: BLE001
                    log.warning(f"[AppContainer] {name} 初始化失败: {e}")
                finally:
                    log.info(
                        "[AppContainer] 后台初始化结束: %s（耗时 %.1fs）",
                        name, time.monotonic() - t0,
                    )

            tasks = {
                "attention_integration": init_attention_integration,
                "SignalStream": init_signal_stream,
                "MerrillClock": init_merrill_clock,
                "调度器": init_schedulers,
            }
            # ❗这里**刻意不用** ThreadPoolExecutor：
            # ① 它作为上下文管理器退出时会 shutdown(wait=True)，某一项卡住就把
            #    本线程一起等死 —— 正是要避免的事；
            # ② 它的工作线程不是 daemon，解释器退出时会 join，卡住的项还会连带
            #    把「关不掉的服务」一起留下。
            threads = {}
            for name, fn in tasks.items():
                th = threading.Thread(
                    target=_timed, args=(name, fn),
                    name=f"naja-init-{name}", daemon=True,
                )
                threads[name] = th
                th.start()

            deadline = time.monotonic() + self.BACKGROUND_INIT_TIMEOUT
            for th in threads.values():
                th.join(max(0.0, deadline - time.monotonic()))

            stuck = [n for n, th in threads.items() if th.is_alive()]
            if stuck:
                # ❗必须报 ERROR：这种残缺状态**外表完全健康**（进程不退、做 T 心跳
                # 照跳、Web/API 可用、日志零异常），只有这一行能说明它不完整。
                log.error(
                    "[AppContainer] 后台初始化超时 %.0fs，以下初始化项未完成：%s。"
                    "它们之后的启动步骤已被跳过，服务会以「看起来正常」的残缺状态继续运行。"
                    "定位：日志里只有「后台初始化开始: X」而没有对应的「结束」行，X 就是卡点。",
                    self.BACKGROUND_INIT_TIMEOUT, "、".join(stuck),
                )
                return

            log.info("[AppContainer] 后台初始化完成")

        thread = threading.Thread(target=background_init, daemon=True)
        thread.start()
        log.info("[AppContainer] 后台初始化线程已启动（并行模式）")

    def _register_ai_daily_report_task(self):
        """注册 AI 技术简报定时任务"""
        try:
            task_mgr = self.task_manager
            existing = task_mgr.get_by_name("ai_daily_report")
            if not existing:
                func_code = '''
import logging
log = logging.getLogger(__name__)

def execute() -> dict:
    """AI 技术简报：抓取 arXiv/HF/GitHub/新闻，生成结构化简报并推送"""
    try:
        from deva.naja.tasks.ai_daily_report import execute as run_ai_daily_report
        result = run_ai_daily_report()
        return result
    except Exception as e:
        log.error(f"[AI_Daily_Report] 执行失败: {e}")
        return {"success": False, "error": str(e)}
'''
                result = task_mgr.create(
                    name="ai_daily_report",
                    description="AI 技术简报（arXiv/HF/GitHub/新闻，生成结构化报告并推送手机）",
                    func_code=func_code,
                    task_type="scheduler",
                    scheduler_trigger="cron",
                    cron_expr="0 21 * * *",
                    tags=["ai", "daily_report", "intelligence"],
                )
                if result.get("success"):
                    task_mgr.start(result.get("id"))
                    log.info(f"[AppContainer] AI 技术简报任务已创建并启动: {result.get('id')}")
            else:
                if not existing.is_running:
                    task_mgr.start(existing.id)
                log.info("[AppContainer] AI 技术简报任务已存在")
        except Exception as e:
            log.warning(f"[AppContainer] AI 技术简报任务注册失败: {e}")

    def _register_news_digest_task(self):
        """注册「新闻消化日报」定时任务（每日 19:00）。

        产物：``~/.naja/news_digest/YYYY-MM-DD.html``（自包含，可随时翻看）。
        与 AI 晚报互补：AI 晚报是"技术圈发生了什么"，本任务是
        "按我们的持仓与关注，今天到底该看哪几条"。
        """
        try:
            task_mgr = self.task_manager
            existing = task_mgr.get_by_name("news_digest")
            if not existing:
                func_code = '''
import logging
log = logging.getLogger(__name__)

def execute() -> dict:
    """新闻消化日报：扫描已评分新闻池 → 按持仓/关注相关度精选 → 生成 HTML 日报"""
    try:
        from deva.naja.news.digest import run_daily_digest
        return run_daily_digest(push=False)
    except Exception as e:
        log.error(f"[NewsDigest] 执行失败: {e}")
        return {"success": False, "error": str(e)}
'''
                result = task_mgr.create(
                    name="news_digest",
                    description="新闻消化日报（按持仓/关注相关度精选，生成 HTML 报告）",
                    func_code=func_code,
                    task_type="scheduler",
                    scheduler_trigger="cron",
                    cron_expr="0 19 * * *",
                    tags=["news", "digest", "daily_report"],
                )
                if result.get("success"):
                    task_mgr.start(result.get("id"))
                    log.info(f"[AppContainer] 新闻消化日报任务已创建并启动: {result.get('id')}")
            else:
                if not existing.is_running:
                    task_mgr.start(existing.id)
                log.info("[AppContainer] 新闻消化日报任务已存在")
        except Exception as e:
            log.warning(f"[AppContainer] 新闻消化日报任务注册失败: {e}")

    def _register_knowledge_injector_task(self):
        """注册 AI 知识库注入与验证定时任务"""
        try:
            task_mgr = self.task_manager
            existing = task_mgr.get_by_name("knowledge_injector")
            if not existing:
                func_code = '''
import logging
log = logging.getLogger(__name__)

def execute() -> dict:
    """知识库注入与验证：从 AI 日报新闻中提取因果知识并注入"""
    try:
        from deva.naja.tasks.ai_knowledge_injector import AIKnowledgeInjector
        from deva.naja.tasks.ai_daily_report import (
            fetch_ai_news,
            fetch_ai_investment_news,
        )
        
        injector = AIKnowledgeInjector()
        
        news_list = fetch_ai_news()
        invest_news = fetch_ai_investment_news()
        
        all_news = (news_list or []) + (invest_news or [])
        if not all_news:
            return {"success": True, "message": "无新闻数据，跳过"}
        
        evaluation = injector.extract_and_evaluate_knowledge(all_news)
        counts = injector.inject_knowledge(evaluation)
        
        notification = injector.generate_notification_text(evaluation)
        if notification:
            log.info(f"[KnowledgeInjector] {notification}")
        
        return {
            "success": True,
            "new": counts.get("new", 0),
            "validating": counts.get("validating", 0),
            "qualified": counts.get("qualified", 0),
        }
    except Exception as e:
        log.error(f"[KnowledgeInjector] 执行失败: {e}")
        return {"success": False, "error": str(e)}
'''
                result = task_mgr.create(
                    name="knowledge_injector",
                    description="AI 知识库注入与验证（定期评估新闻中的因果知识，清理过期知识）",
                    func_code=func_code,
                    task_type="scheduler",
                    scheduler_trigger="cron",
                    cron_expr="0 22 * * *",
                    tags=["knowledge", "injection", "daily"],
                )
                if result.get("success"):
                    task_mgr.start(result.get("id"))
                    log.info(f"[AppContainer] 知识库注入任务已创建并启动: {result.get('id')}")
            else:
                if not existing.is_running:
                    task_mgr.start(existing.id)
                log.info("[AppContainer] 知识库注入任务已存在")
        except Exception as e:
            log.warning(f"[AppContainer] 知识库注入任务注册失败: {e}")

    def _register_openrouter_monitor_task(self):
        """注册 OpenRouter AI 算力趋势监控定时任务"""
        try:
            task_mgr = self.task_manager
            existing = task_mgr.get_by_name("openrouter_monitor")
            if not existing:
                func_code = '''
import logging
import asyncio
log = logging.getLogger(__name__)

def execute() -> dict:
    """OpenRouter AI 算力 TOKEN 消耗趋势监控（每周执行）"""
    try:
        from deva.naja.cognition.openrouter_monitor import (
            refresh_openrouter_data,
            get_ai_compute_trend,
        )
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(refresh_openrouter_data())
        finally:
            loop.close()
        
        if result:
            trend = get_ai_compute_trend()
            return {
                "success": True,
                "trend_direction": trend.get("trend_direction") if trend else "unknown",
                "alert_level": result.get("alert_level", "normal"),
                "message": result.get("message", ""),
                "data_weeks": result.get("data_weeks", 0),
            }
        else:
            return {"success": False, "message": "数据获取失败"}
    except Exception as e:
        log.error(f"[OpenRouter] 执行失败: {e}")
        return {"success": False, "error": str(e)}
'''
                result = task_mgr.create(
                    name="openrouter_monitor",
                    description="OpenRouter AI 算力 TOKEN 消耗趋势监控（每周分析全球 AI 算力需求变化）",
                    func_code=func_code,
                    task_type="scheduler",
                    scheduler_trigger="cron",
                    cron_expr="0 9 * * 1",  # 每周一 09:00
                    tags=["openrouter", "ai_compute", "weekly"],
                )
                if result.get("success"):
                    task_mgr.start(result.get("id"))
                    log.info(f"[AppContainer] OpenRouter 监控任务已创建并启动: {result.get('id')}")
            else:
                if not existing.is_running:
                    task_mgr.start(existing.id)
                log.info("[AppContainer] OpenRouter 监控任务已存在")
        except Exception as e:
            log.warning(f"[AppContainer] OpenRouter 监控任务注册失败: {e}")

    def _start_merrill_clock_task(self):
        """启动美林时钟定时任务"""
        try:
            task_mgr = self.task_manager

            # ❗任务名带版本号，不是洁癖：func_code 是**存在 NB 里**的，改源码
            # 对已存在的任务毫无影响（下面 `if not existing` 直接跳过）。
            # v1 那段用了 nest_asyncio，每次执行都抛 Event loop is closed，
            # 而且这个失败只在 console 日志的 traceback 里看得见。
            # 换名是唯一可靠的上线方式；旧任务只停不删，留作痕迹。
            TASK_NAME = "merrill_clock_update_v2"
            legacy = task_mgr.get_by_name("merrill_clock_update")
            if legacy is not None and getattr(legacy, "is_running", False):
                try:
                    task_mgr.stop(legacy.id)
                    log.info("[AppContainer] 已停用旧版美林任务 merrill_clock_update（func_code 含 nest_asyncio，必然失败）")
                except Exception as e:
                    log.warning(f"[AppContainer] 停用旧版美林任务失败: {e}")

            existing = task_mgr.get_by_name(TASK_NAME)
            if not existing:
                import hashlib
                task_id = hashlib.md5("merrill_clock_update_2026_v2".encode()).hexdigest()[:12]
                
                func_code = '''
import logging
import asyncio
import os
log = logging.getLogger(__name__)


def _run_coro(coro):
    """在**本线程新建**的 loop 上跑协程。

    ❗不要用 asyncio.run()：nest_asyncio.apply() 会把 asyncio.run 换成
    nest_asyncio.run，后者取的是**本线程的默认 loop**。调度线程里那个 loop
    早已被 close（服务启动阶段用过 asyncio.run），于是 create_task 直接抛
    RuntimeError: Event loop is closed —— 这就是经济周期停在 4 天前的根因。

    也不要再 apply() nest_asyncio：它只会把这个问题重新引进来。
    new_event_loop() 不动默认 loop，跑完就关，互不干扰。
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        raise RuntimeError("_run_coro 不能在已有 running loop 的线程里调用")
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        try:
            loop.close()
        except Exception:
            pass


def execute() -> dict:
    """获取经济数据并更新美林时钟"""
    log.info("[MerrillClockTask] 开始获取经济数据...")
    
    try:
        from deva.naja.cognition.merrill_clock.economic_data_fetcher import EconomicDataFetcher
        from deva.naja.cognition.merrill_clock import get_merrill_clock_engine
        
        fred_api_key = os.environ.get("FRED_API_KEY", "")
        use_mock = not bool(fred_api_key)
        if use_mock:
            log.warning("[MerrillClockTask] FRED_API_KEY 环境变量未设置，使用 mock 模式")
        fetcher = EconomicDataFetcher(fred_api_key=fred_api_key, use_mock=use_mock)
        
        async def _fetch():
            data = await fetcher.fetch_latest_data()
            await fetcher.close()
            return data
        
        data = _run_coro(_fetch())
        log.info("[MerrillClockTask] 获取经济数据成功")
        
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
                # ❗mock 数据算出来的周期也是「看起来像真信号」。
                # 不标出来，页面上那句「过热」就无从判断可信度。
                "mock": use_mock,
            }
        else:
            return {"success": False, "message": "数据不足"}
            
    except Exception as e:
        log.error(f"[MerrillClockTask] 执行失败：{e}", exc_info=True)
        return {"success": False, "message": str(e)}
'''
                
                result = task_mgr.create(
                    name=TASK_NAME,
                    description="美林时钟经济数据定时更新（每日凌晨执行）",
                    func_code=func_code,
                    task_type="scheduler",
                    scheduler_trigger="cron",
                    cron_expr="30 4 * * *",
                    tags=["merrill_clock", "economic", "daily"],
                )
                
                if result.get("success"):
                    entry_id = result.get("id")
                    task_mgr.start(entry_id)
                    log.info(f"[AppContainer] 美林时钟定时任务已创建并启动: {entry_id}")
                else:
                    log.warning(f"[AppContainer] 美林时钟定时任务创建失败: {result.get('error')}")
            else:
                if not existing.is_running:
                    task_mgr.start(existing.id)
                log.info(f"[AppContainer] 美林时钟定时任务已存在，直接启动")
                
        except Exception as e:
            log.warning(f"[AppContainer] 美林时钟定时任务启动失败: {e}")
    
    def _start_heartbeat_task(self):
        """启动系统心跳任务"""
        try:
            task_mgr = self.task_manager

            heartbeat_code = '''
import logging
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
                    log.info(f"[AppContainer] 系统心跳任务已创建并启动: {entry_id}")
            else:
                if not existing_heartbeat.is_running:
                    task_mgr.start(existing_heartbeat.id)
                log.info(f"[AppContainer] 系统心跳任务已存在")

        except Exception as e:
            log.warning(f"[AppContainer] 系统心跳任务启动失败: {e}")
    
    def _perform_wake_sync(self):
        """统一唤醒补作业检查

        委托给 application 层的 WakeOrchestrator 统一编排，
        内部协调组件恢复与外部数据补齐。
        """
        try:
            from .wake_orchestrator import get_wake_orchestrator

            state_mgr = self.system_state_manager

            orchestrator = get_wake_orchestrator()
            result = orchestrator.wake()

            state_mgr.record_wake()

            action = result.get('action', 'executed')
            if action == 'skipped':
                log.info(f"[AppContainer] [WakeSync] {result.get('reason', '跳过')}")
            else:
                log.info(f"[AppContainer] [WakeSync] 唤醒补作业完成: 休眠 {result.get('sleep_hours')}h, "
                         f"恢复={result.get('recovery', {})}, 同步={result.get('wake_sync', {})}")

        except Exception as e:
            log.warning(f"[AppContainer] 统一唤醒补作业失败: {e}")

    def _create_trading_clock(self):
        """创建 TradingClock"""
        from ..radar.trading_clock import TradingClock
        tc = TradingClock()
        tc.start()
        return tc

    def _create_market_time_service(self):
        """创建 MarketTimeService（显式依赖注入）

        ❗必须与 TradingClock 严格区分：TradingClock 只有 cn_phase /
        us_phase / get_global_status，没有 get_market_time()。以前这里
        直接把 _trading_clock 当 market_time_service 注入，导致
        VirtualPortfolio.open_position / BanditPositionTracker 一调用
        get_market_time() 就 AttributeError。
        MarketTimeService 本身是单例，与 SR('market_time_service') 同实例。
        """
        from ..infra.runtime.market_time import MarketTimeService
        return MarketTimeService()

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
        
        # 显式依赖注入（通过 property 懒加载依赖）
        attention_os = AttentionOS(insight_pool=self.insight_pool)
        attention_os.set_trading_clock(self._trading_clock)
        
        return attention_os

    def _wire_news_focus_provider(self) -> None:
        """把「注意力状态提供者」接到文本评分器上（修复一条静默失效的死线）。

        背景：``TextImportanceScorer.set_manas_state`` 全仓**从未被调用**，
        导致 ``_manas_state`` 恒为 None → 关注主题匹配恒空、叙事分恒为常数、
        ``TextFocusedEvent.matched_focus_topics`` 恒空，下游叙事追踪/跨信号/
        供应链联动整条链路空转（表现为"跑得好好的"）。

        这里注入 ``build_manas_focus_state``：每次评分前惰性拉取当前焦点快照
        （持仓 / 自选 / 关注叙事 / 关注主题），评分器不反向依赖 news 包——
        依赖方向仍是 application → attention / news。
        """
        attention_os = self._attention_os
        if attention_os is None:
            log.warning("[AppContainer] attention_os 未就绪，跳过焦点 provider 接线")
            return
        try:
            from ..news.focus import build_manas_focus_state

            attention_os.set_text_focus_provider(build_manas_focus_state)
            log.info("[AppContainer] 新闻焦点 provider 已接入文本评分器")
        except Exception as e:
            log.warning(f"[AppContainer] 焦点 provider 接线失败: {e}")

    def _bootstrap_derived_topics(self) -> None:
        """按持仓推导关注主题（用户 2026-10-12 选定的「自动采纳」档位）。

        推导 → 采纳为 ``source="derived"``（可在 /focusadmin 一键撤销）。
        跳过用户曾撤销过的主题，避免每次启动把刚删掉的又加回来。

        放**后台线程**且延迟数秒：要读 NB + 供应链图谱，而且不能在
        ``_assemble_core_components`` 的调用栈里跟主线程抢初始化。
        开关：``NAJA_NEWS_AUTO_DERIVE=0`` 关闭。
        """
        import os

        if str(os.environ.get("NAJA_NEWS_AUTO_DERIVE", "1")).strip().lower() in (
            "0", "false", "no", "off",
        ):
            log.info("[AppContainer] 自动推导关注主题已关闭（NAJA_NEWS_AUTO_DERIVE=0）")
            return

        def _run() -> None:
            time.sleep(5)  # 等启动流程走完，别和装配阶段抢资源
            try:
                from ..news.focus_advisor import auto_apply_derived

                result = auto_apply_derived()
            except Exception as e:
                log.warning("[AppContainer] 自动推导关注主题失败: %s", e)
                return

            if not result.get("ok"):
                log.warning(
                    "[AppContainer] 自动推导关注主题未完成: %s", result.get("reason")
                )
                return

            derived = result.get("derived") or {}
            log.info(
                "[AppContainer] 自动推导关注主题：采纳 %s；已存在 %s；跳过 %s%s",
                result.get("applied") or [],
                result.get("already") or [],
                result.get("skipped") or [],
                f"；推导降级 {derived.get('degraded')}" if derived.get("degraded") else "",
            )

        try:
            import threading as _threading
            _threading.Thread(
                target=_run, name="focus-derive-bootstrap", daemon=True
            ).start()
        except Exception as e:
            log.warning("[AppContainer] 自动推导线程启动失败: %s", e)

    def _create_trading_center(self):
        """创建 TradingCenter（显式依赖注入）"""
        from ..attention.orchestration.trading_center import TradingCenter

        # 显式传递 AttentionOS 实例
        trading_center = TradingCenter(attention_os=self._attention_os)
        
        return trading_center

    def _create_manas_manager(self):
        """创建 ManasManager（显式依赖注入）

        注入 AttentionOS 的 kernel，使 manager 与内核共用同一个 ManasEngine。
        不注入的话 manager 会自建第二个引擎，导致 _cognitive_state /
        _recent_pnl 两套状态互不可见：内核按自己那份打分，UI 读的是另一份。

        注意：此处必须用 self._bandit_tracker 直接属性访问，不能用
        self.bandit_tracker property —— 因为 property 会触发
        _assemble_core_components()，而当前可能正处于它的调用栈中，
        会导致递归初始化。self._attention_os 同理，用直接属性访问。
        """
        from ..attention.kernel.manas_manager import ManasManager

        # 若 _bandit_tracker 尚未初始化则先懒创建，但直接走 create 而不走 property
        if self._bandit_tracker is None:
            # 提前设置已装配标识，防止递归
            was_assembled = self._components_assembled
            self._components_assembled = True
            try:
                if self._bandit_optimizer is None:
                    self._bandit_optimizer = self._create_bandit_optimizer()
                self._bandit_tracker = self._create_bandit_tracker()
            finally:
                self._components_assembled = was_assembled or self._components_assembled

        # kernel 注入：attention_os 在 _assemble_core_components() 中先于本方法
        # 创建，因此这里读 self._attention_os 是安全的
        kernel = None
        attention_os = self._attention_os
        if attention_os is not None:
            get_kernel = getattr(attention_os, "get_kernel", None)
            if callable(get_kernel):
                try:
                    kernel = get_kernel()
                except Exception as e:
                    log.warning(
                        f"[AppContainer] 获取 AttentionOS kernel 失败，"
                        f"末那识将退化为独立引擎: {e}"
                    )

        manas_manager = ManasManager(
            kernel=kernel,
            trading_clock=self._trading_clock,
            virtual_portfolio=self._virtual_portfolio,
            bandit_tracker=self._bandit_tracker,
        )

        # P1 接线修复：把真实依赖注入内核侧 ManasEngine。
        # 内核的 ManasEngine 是自建且无依赖注入的，其 _get_portfolio /
        # _get_bandit_tracker 历史上直接 return None → 风险温度 T 恒 1.25、
        # confidence 恒 0.35（诊断见 docs/naja/manas_upgrade_plan.md §1）。
        # session_manager 不在此处传：内核会自行解析 scanner.session_manager
        # （MarketSessionManager），与打分路径共用同一个对象。
        # 装配点放在 application 层，符合架构基准 §6.2（核心层不新增 SR）与 §6.3。
        if kernel is not None and hasattr(kernel, "set_manas_dependencies"):
            kernel.set_manas_dependencies(
                portfolio=self._virtual_portfolio,
                bandit_tracker=self._bandit_tracker,
            )

        # D3 闭环反馈（读取端）：把 manas 的觉醒维度接到共享 AwakenedAlaya 上。
        # 之前该环节指向一个全仓不存在的 get_awakening_controller → 恒 ×1.0。
        # 这里用 lambda 延迟求值：TradingCenter 是单例，且其内部 alaya 懒创建，
        # 装配期直接取可能拿到未初始化的实例。
        if kernel is not None:
            engine = getattr(kernel, "manas_engine", None)
            if engine is None and hasattr(kernel, "get_manas_engine"):
                try:
                    engine = kernel.get_manas_engine()
                except Exception:
                    engine = None
            if engine is not None and hasattr(engine, "set_awakening_level_provider"):
                def _awakening_level_provider():
                    try:
                        from ..attention.orchestration.trading_center import get_trading_center
                        tc = get_trading_center()
                        if tc is not None:
                            return tc.get_awakening_level()
                    except Exception:
                        pass
                    return "dormant"

                engine.set_awakening_level_provider(_awakening_level_provider)
                log.info("[AppContainer] Manas 觉醒维度已接入共享 AwakenedAlaya")

        # 启动即启用：内核侧 OSAttentionKernel 是无条件计算末那识的（os_kernel.py
        # 无 _enable_manas 门闩），manager 侧必须同步启用，否则
        # container.manas_engine 恒为 None，UI 拿到的又是另一个引擎的状态
        manas_manager.set_enabled(True)

        return manas_manager
    
    def _create_insight_pool(self):
        """创建 InsightPool"""
        from ..cognition.insight.engine import InsightPool
        return InsightPool()
    
    def _create_insight_engine(self):
        """创建 InsightEngine（显式依赖注入）"""
        from ..cognition.insight.engine import InsightEngine
        
        insight_engine = InsightEngine(
            insight_pool=self.insight_pool
        )
        
        return insight_engine

    def _wire_insight_pool_events(self):
        """把「洞察池有新洞察」接到 CognitiveInsightEvent 上。

        ❗此前全仓**没有任何地方**发布 CognitiveInsightEvent，而
        QueryStateUpdater 只认事件 → 页面上「认知洞察」恒 0，且无从判断
        是「真没有洞察」还是「洞察有了但送不出去」。叙事事件是通的
        （narrative/tracker.py 里 publish_event(NarrativeStateEvent(...))），
        照同一模板补上即可。
        """
        from ..events import publish_event
        from ..events.cognitive_events import CognitiveInsightEvent

        pool = self.insight_pool
        if pool is None:
            log.warning("[AppContainer] insight_pool 未就绪，跳过洞察事件接线")
            return

        def _on_new_insight(insight):
            payload = insight.to_dict() if hasattr(insight, "to_dict") else dict(insight)
            # 只把最近若干条送出去：QueryState 是给页面读的，不需要全量历史。
            recent = [
                i.to_dict() if hasattr(i, "to_dict") else i
                for i in list(getattr(pool, "_insights", []) or [])[-20:]
            ]
            publish_event(
                CognitiveInsightEvent(
                    insights=recent or [payload],
                    confidence=float(payload.get("confidence", 0.5) or 0.5),
                    timestamp=float(payload.get("ts", time.time()) or time.time()),
                    source="insight_pool",
                )
            )

        pool.on_insight = _on_new_insight
        log.info("[AppContainer] 洞察池 → CognitiveInsightEvent 接线完成")

    def _create_llm_reflection_engine(self):
        """创建 LLMReflectionEngine（显式依赖注入）"""
        from ..cognition.insight.llm_reflection import LLMReflectionEngine
        
        engine = LLMReflectionEngine()
        engine.set_cognition_engine(self.cognition_engine)
        engine.set_insight_pool(self.insight_pool)
        
        return engine

    
    def _create_cognition_engine(self):
        """创建 CognitionEngine"""
        from ..cognition.engine import CognitionEngine
        return CognitionEngine()
    
    def _create_radar_engine(self):
        """创建 RadarEngine"""
        from ..radar.engine import RadarEngine
        
        radar_engine = RadarEngine(trading_clock=self._trading_clock)
        
        return radar_engine

    def _create_structural_growth_pool(self):
        """创建结构性增长雷达观察池，优先从持久化文件恢复"""
        from ..structural_growth import ObservationPool, IndustryState
        pool = ObservationPool()
        # 尝试从持久化文件恢复
        if pool.load_from_file() and len(pool) > 0:
            return pool
        # 首次启动：预注册全部默认行业
        default_industries = [
            ("ai_chips", "AI芯片"),
            ("ai_foundry", "晶圆代工"),
            ("semiconductor_equipment", "半导体设备"),
            ("hbm", "高带宽存储"),
            ("cloud_infra", "云计算/数据中心"),
            ("ai_software", "AI软件/应用"),
            ("ai_power", "AI电力/散热"),
            ("energy_storage", "储能"),
            ("cybersecurity", "网络安全"),
            ("robotics", "机器人/自动化"),
            ("ai_networking", "AI网络"),
        ]
        for iid, name in default_industries:
            if iid not in pool:
                pool.add(IndustryState(industry_id=iid, name=name))
        pool.save_to_file()
        return pool
    
    def _create_event_registrar(self):
        """创建事件订阅装配器"""
        from .event_registrar import EventSubscriberRegistrar
        return EventSubscriberRegistrar(
            attention_os=self._attention_os,
            trading_center=self.trading_center,
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
            market_time_service=self._market_time_service,
            bandit_optimizer=self.bandit_optimizer
        )
        
        return tracker
    
    def _create_market_observer(self):
        """创建 MarketDataObserver（显式依赖注入）"""
        from ..bandit.market_observer import MarketDataObserver
        
        observer = MarketDataObserver()
        observer.set_trading_clock(self._trading_clock)
        
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
            signal_listener=self.signal_listener,
            portfolio=self._virtual_portfolio,
            market_observer=self.market_observer,
            optimizer=self.bandit_optimizer,
            tracker=self.bandit_tracker,
            runner=self.bandit_runner
        )
        
        return cycle

    def _create_task_manager(self):
        """创建 TaskManager"""
        from ..tasks import TaskManager
        task_mgr = TaskManager()
        task_mgr._ensure_initialized()
        return task_mgr

    def _create_system_state_manager(self):
        """创建 SystemStateManager"""
        from ..state.system.system_state import SystemStateManager
        return SystemStateManager()

    def _create_dictionary_manager(self):
        """创建 DictionaryManager"""
        from ..dictionary import DictionaryManager
        dict_mgr = DictionaryManager()
        dict_mgr._ensure_initialized()
        return dict_mgr

    def _create_attention_integration(self):
        """创建 AttentionIntegration（MarketHotspotIntegration）"""
        from ..market_hotspot.integration.market_hotspot_integration import MarketHotspotIntegration
        from ..market_hotspot.integration.market_hotspot_config import load_config
        integration = MarketHotspotIntegration()
        integration._deferred_init_config = load_config()
        return integration

    @property
    def attention_os(self):
        """获取 AttentionOS"""
        return self._attention_os

    @property
    def task_manager(self):
        """获取 TaskManager（懒加载）"""
        if self._task_manager is None:
            self._task_manager = self._create_task_manager()
        return self._task_manager

    @property
    def system_state_manager(self):
        """获取 SystemStateManager（懒加载）"""
        if self._system_state_manager is None:
            self._system_state_manager = self._create_system_state_manager()
        return self._system_state_manager

    @property
    def dictionary_manager(self):
        """获取 DictionaryManager（懒加载）"""
        if self._dictionary_manager is None:
            self._dictionary_manager = self._create_dictionary_manager()
        return self._dictionary_manager

    @property
    def attention_integration(self):
        """获取 AttentionIntegration（懒加载）"""
        if self._attention_integration is None:
            self._attention_integration = self._create_attention_integration()
        return self._attention_integration

    @property
    def trading_center(self):
        """获取 TradingCenter（懒加载）"""
        if self._trading_center is None:
            self._assemble_core_components()
            self._trading_center = self._create_trading_center()
            log.info("[AppContainer] TradingCenter 懒加载完成")
        return self._trading_center

    @property
    def insight_pool(self):
        """获取 InsightPool（懒加载）"""
        if self._insight_pool is None:
            self._assemble_core_components()
            self._insight_pool = self._create_insight_pool()
            log.info("[AppContainer] InsightPool 懒加载完成")
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
        """获取 BanditTracker（懒加载）"""
        if self._bandit_tracker is None:
            self._assemble_core_components()
            _ = self.bandit_optimizer
            self._bandit_tracker = self._create_bandit_tracker()
            log.info("[AppContainer] BanditTracker 懒加载完成")
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
    def insight_engine(self):
        """获取 InsightEngine（懒加载）"""
        if self._insight_engine is None:
            self._assemble_core_components()
            _ = self.insight_pool
            self._insight_engine = self._create_insight_engine()
            log.info("[AppContainer] InsightEngine 懒加载完成")
        return self._insight_engine

    @property
    def cognition_engine(self):
        """获取 CognitionEngine（懒加载）"""
        if self._cognition_engine is None:
            self._assemble_core_components()
            self._cognition_engine = self._create_cognition_engine()
            log.info("[AppContainer] CognitionEngine 懒加载完成")
        return self._cognition_engine

    @property
    def llm_reflection_engine(self):
        """获取 LLMReflectionEngine（懒加载）"""
        if self._llm_reflection_engine is None:
            self._assemble_core_components()
            self._llm_reflection_engine = self._create_llm_reflection_engine()
            log.info("[AppContainer] LLMReflectionEngine 懒加载完成")
        return self._llm_reflection_engine

    @property
    def bandit_optimizer(self):
        """获取 BanditOptimizer（懒加载）"""
        if self._bandit_optimizer is None:
            self._assemble_core_components()
            self._bandit_optimizer = self._create_bandit_optimizer()
            log.info("[AppContainer] BanditOptimizer 懒加载完成")
        return self._bandit_optimizer

    @property
    def portfolio_manager(self):
        """获取 PortfolioManager（懒加载）"""
        if self._portfolio_manager is None:
            self._assemble_core_components()
            self._portfolio_manager = self._create_portfolio_manager()
            log.info("[AppContainer] PortfolioManager 懒加载完成")
        return self._portfolio_manager

    @property
    def radar_engine(self):
        """获取 RadarEngine（懒加载）"""
        if self._radar_engine is None:
            self._assemble_core_components()
            self._radar_engine = self._create_radar_engine()
            log.info("[AppContainer] RadarEngine 懒加载完成")
        return self._radar_engine

    @property
    def structural_growth_pool(self):
        """获取结构性增长雷达观察池（懒加载）"""
        if self._structural_growth_pool is None:
            self._assemble_core_components()
            self._structural_growth_pool = self._create_structural_growth_pool()
            log.info("[AppContainer] StructuralGrowthPool 懒加载完成")
        return self._structural_growth_pool

    @property
    def market_observer(self):
        """获取 MarketDataObserver（懒加载）"""
        if self._market_observer is None:
            self._assemble_core_components()
            self._market_observer = self._create_market_observer()
            log.info("[AppContainer] MarketDataObserver 懒加载完成")
        return self._market_observer

    @property
    def signal_listener(self):
        """获取 SignalListener（懒加载）"""
        if self._signal_listener is None:
            self._assemble_core_components()
            self._signal_listener = self._create_signal_listener()
            log.info("[AppContainer] SignalListener 懒加载完成")
        return self._signal_listener

    @property
    def bandit_runner(self):
        """获取 BanditAutoRunner（懒加载）"""
        if self._bandit_runner is None:
            self._assemble_core_components()
            self._bandit_runner = self._create_bandit_runner()
            log.info("[AppContainer] BanditAutoRunner 懒加载完成")
        return self._bandit_runner

    @property
    def adaptive_cycle(self):
        """获取 AdaptiveCycle（懒加载）"""
        if self._adaptive_cycle is None:
            self._assemble_core_components()
            _ = self.signal_listener
            _ = self.bandit_runner
            _ = self.bandit_optimizer
            _ = self.bandit_tracker
            _ = self.market_observer
            self._adaptive_cycle = self._create_adaptive_cycle()
            log.info("[AppContainer] AdaptiveCycle 懒加载完成")
        return self._adaptive_cycle

    def restore_runtime_state(self) -> None:
        print("🎯 恢复 Bandit 自适应循环...")
        try:
            from deva.naja.bandit import restore_bandit_state

            restore_bandit_state()
            print("✓ Bandit 自适应循环状态已恢复")
        except Exception as e:
            print(f"⚠️ Bandit 自适应循环恢复失败: {e}")

        # === 恢复定时任务运行状态 ===
        try:
            task_mgr = self.task_manager
            task_mgr._ensure_initialized()
            result = task_mgr.restore_running_states()
            restored = result.get("restored_count", 0)
            failed = result.get("failed_count", 0)
            if restored > 0:
                print(f"✓ 任务管理器: 已恢复 {restored} 个定时任务" + (f"（失败 {failed}）" if failed > 0 else ""))
            elif failed > 0:
                print(f"⚠️ 任务管理器恢复失败: {failed} 个")
        except Exception as e:
            print(f"⚠️ 任务管理器恢复失败: {e}")

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
