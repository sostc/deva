from typing import Dict, Any


def setup_admin_runtime(state: Dict[str, Any], *, enable_webviews=True, enable_timer=True, enable_scheduler=True):
    """Initialize admin runtime with injected dependencies.

    state keys required:
    - initialized: bool
    - logtimer, log, browser, concat, NS, scheduler
    """
    if state.get('initialized'):
        return

    # 标记 admin 正在启动，后续创建的 NS 都会自动执行 webview
    from deva.core.namespace import set_admin_starting
    set_admin_starting()

    logtimer = state['logtimer']
    log = state['log']
    browser = state['browser']
    concat = state['concat']
    NS = state['NS']
    scheduler = state['scheduler']

    if enable_timer:
        logtimer.start()
        logtimer >> log

    browser.log >> log

    log.start_cache(200, cache_max_age_seconds=60 * 60 * 24 * 30)
    access_log_stream = NS('访问日志', cache_max_len=1, cache_max_age_seconds=60 * 60 * 24 * 30, description='访问日志流，用于记录系统访问日志和用户操作')
    log.map(lambda x: log.recent(10) >> concat('<br>')) >> access_log_stream
    access_log_stream.webview(f'/{hash(access_log_stream)}')

    if state.get("enable_strategy", True) and not state.get("strategy_initialized", False):
        try:
            from deva.admin_ui.strategy.runtime import initialize_strategy_monitor_streams

            initialize_strategy_monitor_streams(attach_webviews=True)
            state["strategy_initialized"] = True
            {"level": "INFO", "source": "deva.admin", "message": "strategy runtime initialized"} >> log
        except Exception as e:
            {"level": "WARNING", "source": "deva.admin",
                "message": "strategy runtime init failed", "error": str(e)} >> log

    if enable_scheduler and not scheduler.running:
        scheduler.start()

    state['initialized'] = True
