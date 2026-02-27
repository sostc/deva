from typing import Dict, Any

ADMIN_STREAM_NAMES = (
    '访问日志',
    '实时新闻',
    '涨跌停',
    '领涨领跌板块',
    '1分钟板块异动',
    '30秒板块异动',
)

ADMIN_STREAM_DESCRIPTIONS = {
    '访问日志': '访问日志流，用于记录系统访问日志和用户操作',
    '实时新闻': '实时新闻流，用于展示最新的财经新闻资讯',
    '涨跌停': '涨跌停流，用于监控股票涨跌停情况',
    '领涨领跌板块': '领涨领跌板块流，用于分析板块涨跌排名',
    '1分钟板块异动': '1分钟板块异动流，用于监控板块的1分钟级别异动',
    '30秒板块异动': '30秒板块异动流，用于监控板块的30秒级别异动',
}


def build_admin_streams(NS):
    return [NS(name, description=ADMIN_STREAM_DESCRIPTIONS.get(name)) for name in ADMIN_STREAM_NAMES]


def setup_admin_runtime(state: Dict[str, Any], *, enable_webviews=True, enable_timer=True, enable_scheduler=True):
    """Initialize admin runtime with injected dependencies.

    state keys required:
    - initialized: bool
    - logtimer, log, browser, concat, NS, scheduler
    """
    if state.get('initialized'):
        return

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
    log.map(lambda x: log.recent(10) >> concat('<br>')) \
        >> NS('访问日志', cache_max_len=1, cache_max_age_seconds=60 * 60 * 24 * 30, description='访问日志流，用于记录系统访问日志和用户操作')

    if enable_webviews:
        for s in build_admin_streams(NS):
            s.webview(f'/{hash(s)}')

    if state.get("enable_strategy", True) and not state.get("strategy_initialized", False):
        try:
            from deva.admin_ui.strategy.runtime import setup_strategy_streams

            setup_strategy_streams(attach_webviews=False)
            state["strategy_initialized"] = True
            {"level": "INFO", "source": "deva.admin", "message": "strategy runtime initialized"} >> log
        except Exception as e:
            {"level": "WARNING", "source": "deva.admin", "message": "strategy runtime init failed", "error": str(e)} >> log

    if enable_scheduler and not scheduler.running:
        scheduler.start()

    state['initialized'] = True
