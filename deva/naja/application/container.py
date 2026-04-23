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
        
        # Bandit 模块组件
        self._bandit_optimizer = None
        self._portfolio_manager = None
        self._market_observer = None
        self._signal_listener = None
        self._bandit_runner = None
        self._adaptive_cycle = None
        
        # Radar 模块组件
        self._radar_engine = None
        
        # 初始化标记
        self._components_assembled = False

    def boot(self):
        """Complete bootstrap: registers everything, assembles components, and records boot report."""
        start = time.time()
        set_app_container(self)

        self._register_singletons()
        self._assemble_core_components()
        self.restore_runtime_state()

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

    def _register_singletons(self):
        """注册所有单例（来自旧的 Bootstrap 路径）"""
        from ..register import register_all_singletons
        register_all_singletons()

    def _assemble_core_components(self) -> None:
        """装配核心组件（显式依赖注入）"""
        if self._components_assembled:
            return

        try:
            # 0. 加载持久化数据管理器（原本在 Bootstrap._load_persistent_data 中）
            self._load_persistent_managers()

            # 1. 获取基础组件（从已注册的单例）
            self._trading_clock = SR('trading_clock')
            self._virtual_portfolio = SR('virtual_portfolio')
            self._value_system = SR('value_system')

            # 2. 获取 AttentionOS（需要先于 ManasManager，因为 NarrativeTracker 依赖它）
            self._attention_os = SR('attention_os')

            # 3. 获取 kernel 层组件（从已注册的单例）
            self._query_state = SR('query_state')
            self._query_state_updater = SR('query_state_updater')
            self._manas_manager = SR('manas_manager')
            # ManasEngine 在 ManasManager 内部创建，通过 get_manas_engine() 获取
            self._manas_engine = self._manas_manager._manas_engine

            # 4. 获取认知层组件（从已注册的单例）
            self._insight_pool = SR('insight_pool')
            self._insight_engine = SR('insight_engine')
            self._cognition_engine = SR('cognition_engine')

            # 5. 获取 Bandit 模块组件（从已注册的单例）
            self._bandit_optimizer = SR('bandit_optimizer')
            self._portfolio_manager = SR('portfolio_manager')
            self._bandit_tracker = SR('bandit_tracker')
            self._market_observer = SR('market_observer')
            self._signal_listener = SR('signal_listener')
            self._bandit_runner = SR('bandit_runner')
            self._adaptive_cycle = SR('adaptive_cycle')

            # 6. 获取 TradingCenter（从已注册的单例）
            self._trading_center = SR('trading_center')

            # 7. 获取 Radar 模块组件（从已注册的单例）
            self._radar_engine = SR('radar_engine')

            # 8. 初始化 SignalStream（对应 Bootstrap._register_components）
            try:
                from ..signal.stream import get_signal_stream
                get_signal_stream()
                log.info("[AppContainer] SignalStream 初始化完成")
            except Exception as e:
                log.warning(f"[AppContainer] SignalStream 初始化失败: {e}")

            # 初始化 MerrillClock（对应 Bootstrap._init_core_components）
            try:
                from ..cognition.merrill_clock import initialize_merrill_clock
                initialize_merrill_clock()
                log.info("[AppContainer] MerrillClock 初始化完成")
            except Exception as e:
                log.warning(f"[AppContainer] MerrillClock 初始化失败: {e}")

            # 9. 事件订阅装配
            self._event_registrar = self._create_event_registrar()
            self._event_registrar.register_all()
            
            # 9. 启动调度器（包含 Supervisor、心跳、美林时钟等）
            self._start_schedulers()
            
            self._components_assembled = True
            log.info("[AppContainer] 核心组件装配完成")
            
        except Exception as e:
            log.error(f"[AppContainer] 组件装配失败: {e}", exc_info=True)


    def _load_persistent_managers(self):
        """加载持久化数据管理器"""
        from ..datasource import get_datasource_manager
        from ..strategy import get_strategy_manager

        dict_mgr = SR('dictionary_manager')
        dict_mgr._ensure_initialized()
        ds_mgr = get_datasource_manager()
        ds_mgr._ensure_initialized()
        task_mgr = SR('task_manager')
        task_mgr._ensure_initialized()
        strategy_mgr = get_strategy_manager()
        strategy_mgr._ensure_initialized()

        counts = {}
        errors = {}

        for name, mgr, attr in [
            ("dictionary", dict_mgr, "字典"),
            ("datasource", ds_mgr, "datasource"),
            ("task", task_mgr, "task"),
            ("strategy", strategy_mgr, "strategy"),
        ]:
            try:
                if hasattr(mgr, 'load_prefer_files'):
                    counts[name] = mgr.load_prefer_files()
                else:
                    counts[name] = mgr.load_from_db()
            except Exception as e:
                errors[name] = str(e)

        self._load_counts = counts
        self._load_errors = errors

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
    
    def _register_ai_daily_report_task(self):
        """注册 AI 技术简报定时任务"""
        try:
            task_mgr = SR('task_manager')
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
            task_mgr = SR('task_manager')
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
            task_mgr = SR('task_manager')
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
            task_mgr = SR('task_manager')
            
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
            task_mgr = SR('task_manager')

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

            state_mgr = SR('system_state_manager')
            state_mgr.record_wake()

            orchestrator = get_wake_orchestrator()
            result = orchestrator.wake()

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
        
        # 显式依赖注入
        attention_os = AttentionOS(insight_pool=self._insight_pool)
        
        return attention_os

    def _create_trading_center(self):
        """创建 TradingCenter（显式依赖注入）"""
        from ..attention.orchestration.trading_center import TradingCenter
        
        # 显式传递 AttentionOS 实例
        trading_center = TradingCenter(attention_os=self._attention_os)
        
        return trading_center

    def _create_manas_engine(self):
        """创建 ManasEngine（显式依赖注入）"""
        from ..attention.kernel.manas_engine import ManasEngine
        
        manas_engine = ManasEngine(
            session_manager=self._trading_clock,
            portfolio=self._virtual_portfolio,
            bandit_tracker=self._bandit_tracker
        )
        
        return manas_engine
    
    def _create_manas_manager(self):
        """创建 ManasManager（显式依赖注入）"""
        from ..attention.kernel.manas_manager import ManasManager
        
        manas_manager = ManasManager(
            trading_clock=self._trading_clock,
            virtual_portfolio=self._virtual_portfolio,
            bandit_tracker=self._bandit_tracker
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
            insight_pool=self._insight_pool
        )
        
        return insight_engine
    
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
            trading_center=self._trading_center,
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
            bandit_optimizer=self._bandit_optimizer
        )
        
        return tracker
    
    def _create_market_observer(self):
        """创建 MarketDataObserver"""
        from ..bandit.market_observer import MarketDataObserver
        
        observer = MarketDataObserver()
        
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
            signal_listener=self._signal_listener,
            portfolio=self._virtual_portfolio,
            market_observer=self._market_observer,
            optimizer=self._bandit_optimizer,
            tracker=self._bandit_tracker,
            runner=self._bandit_runner
        )
        
        return cycle

    @property
    def attention_os(self):
        """获取 AttentionOS"""
        return self._attention_os

    @property
    def trading_center(self):
        """获取 TradingCenter"""
        return self._trading_center

    @property
    def insight_pool(self):
        """获取 InsightPool"""
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
        """获取 BanditTracker"""
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
    def insight_pool(self):
        """获取 InsightPool"""
        return self._insight_pool

    @property
    def insight_engine(self):
        """获取 InsightEngine"""
        return self._insight_engine

    @property
    def cognition_engine(self):
        """获取 CognitionEngine"""
        return self._cognition_engine

    @property
    def bandit_optimizer(self):
        """获取 BanditOptimizer"""
        return self._bandit_optimizer

    @property
    def portfolio_manager(self):
        """获取 PortfolioManager"""
        return self._portfolio_manager

    @property
    def radar_engine(self):
        """获取 RadarEngine"""
        return self._radar_engine

    @property
    def bandit_tracker(self):
        """获取 BanditPositionTracker"""
        return self._bandit_tracker

    @property
    def market_observer(self):
        """获取 MarketDataObserver"""
        return self._market_observer
    
    @property
    def signal_listener(self):
        """获取 SignalListener"""
        if self._signal_listener is None:
            self._assemble_core_components()
        return self._signal_listener
    
    @property
    def bandit_runner(self):
        """获取 BanditAutoRunner"""
        if self._bandit_runner is None:
            self._assemble_core_components()
        return self._bandit_runner
    
    @property
    def adaptive_cycle(self):
        """获取 AdaptiveCycle"""
        if self._adaptive_cycle is None:
            self._assemble_core_components()
        return self._adaptive_cycle

    def restore_runtime_state(self) -> None:
        print("🎯 恢复 Bandit 自适应循环...")
        try:
            from deva.naja.bandit import restore_bandit_state

            restore_bandit_state()
            print("✓ Bandit 自适应循环状态已恢复")
        except Exception as e:
            print(f"⚠️ Bandit 自适应循环恢复失败: {e}")

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
