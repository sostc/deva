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
            "market_time_service": self._trading_clock,  # 别名：旧代码可能用这个名
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

    def _assemble_core_components(self) -> None:
        """装配核心组件（显式依赖注入）"""
        if self._components_assembled:
            return

        from ..infra.observability.startup_timer import StartupTimer

        try:
            StartupTimer.start("加载持久化管理器")
            self._load_persistent_managers()
            StartupTimer.end("加载持久化管理器")

            StartupTimer.start("创建基础组件")
            self._trading_clock = self._create_trading_clock()
            self._virtual_portfolio = self._create_virtual_portfolio()
            self._virtual_portfolio.set_market_time_service(self._trading_clock)
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
        """启动调度器"""
        from ..supervisor import start_supervisor
        from ..supervisor.monitoring import MonitoringMixin

        try:
            supervisor = start_supervisor()
            if isinstance(supervisor, MonitoringMixin):
                supervisor._force_realtime = False
                supervisor._lab_mode = None
                supervisor.configure_attention(force_realtime=False, lab_mode=None)
        except Exception as e:
            log.warning(f"[AppContainer] Supervisor 启动失败: {e}", exc_info=True)

        try:
            from ..strategy.daily_review_scheduler import get_daily_review_scheduler
            scheduler = get_daily_review_scheduler()
            scheduler.start()
        except Exception as e:
            log.warning(f"[AppContainer] DailyReviewScheduler 启动失败: {e}", exc_info=True)
        
        # 注册所有 TaskManager 管理的定时任务
        self._register_ai_daily_report_task()
        self._register_knowledge_injector_task()
        self._register_openrouter_monitor_task()
        
        # 启动美林时钟经济数据定时更新
        self._start_merrill_clock_task()
        
        # 心跳机制：定期更新系统活跃时间
        self._start_heartbeat_task()
        
        # 统一唤醒同步检查
        self._perform_wake_sync()
        
        log.info("[AppContainer] 调度器启动完成")
    
    def _start_background_initialization(self):
        """启动后台初始化线程，异步加载非关键组件（并行版本）"""
        import threading
        import concurrent.futures
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

            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                futures = [
                    executor.submit(init_attention_integration),
                    executor.submit(init_signal_stream),
                    executor.submit(init_merrill_clock),
                    executor.submit(init_schedulers),
                ]
                concurrent.futures.wait(futures)

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
            
            existing = task_mgr.get_by_name("merrill_clock_update")
            if not existing:
                import hashlib
                task_id = hashlib.md5("merrill_clock_update_2026".encode()).hexdigest()[:12]
                
                func_code = '''
import logging
import asyncio
import os
import nest_asyncio
log = logging.getLogger(__name__)

def execute() -> dict:
    """获取经济数据并更新美林时钟"""
    log.info("[MerrillClockTask] 开始获取经济数据...")
    
    try:
        from deva.naja.cognition.merrill_clock.economic_data_fetcher import EconomicDataFetcher
        from deva.naja.cognition.merrill_clock import get_merrill_clock_engine
        
        fred_api_key = os.environ.get("FRED_API_KEY", "")
        if not fred_api_key:
            log.warning("[MerrillClockTask] FRED_API_KEY 环境变量未设置，使用 mock 模式")
        fetcher = EconomicDataFetcher(fred_api_key=fred_api_key, use_mock=not bool(fred_api_key))
        
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

    def _create_trading_center(self):
        """创建 TradingCenter（显式依赖注入）"""
        from ..attention.orchestration.trading_center import TradingCenter
        
        # 显式传递 AttentionOS 实例
        trading_center = TradingCenter(attention_os=self._attention_os)
        
        return trading_center

    def _create_manas_engine(self):
        """创建 ManasEngine（显式依赖注入）

        注意：使用 self._bandit_tracker 而不是 self.bandit_tracker property，
        防止在 _assemble_core_components() 调用栈中递归。
        """
        from ..attention.kernel.manas_engine import ManasEngine

        if self._bandit_tracker is None:
            was_assembled = self._components_assembled
            self._components_assembled = True
            try:
                if self._bandit_optimizer is None:
                    self._bandit_optimizer = self._create_bandit_optimizer()
                self._bandit_tracker = self._create_bandit_tracker()
            finally:
                self._components_assembled = was_assembled or self._components_assembled

        manas_engine = ManasEngine(
            session_manager=self._trading_clock,
            portfolio=self._virtual_portfolio,
            bandit_tracker=self._bandit_tracker,
        )

        return manas_engine
    
    def _create_manas_manager(self):
        """创建 ManasManager（显式依赖注入）

        注意：此处必须用 self._bandit_tracker 直接属性访问，不能用
        self.bandit_tracker property —— 因为 property 会触发
        _assemble_core_components()，而当前可能正处于它的调用栈中，
        会导致递归初始化。
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

        manas_manager = ManasManager(
            trading_clock=self._trading_clock,
            virtual_portfolio=self._virtual_portfolio,
            bandit_tracker=self._bandit_tracker,
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
            insight_pool=self.insight_pool
        )
        
        return insight_engine

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
            market_time_service=self._trading_clock,
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
