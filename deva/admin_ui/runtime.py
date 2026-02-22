from typing import Dict, Any

ADMIN_STREAM_NAMES = (
    '访问日志',
    '实时新闻',
    '涨跌停',
    '领涨领跌板块',
    '1分钟板块异动',
    '30秒板块异动',
)


def build_admin_streams(NS):
    return [NS(name) for name in ADMIN_STREAM_NAMES]


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
        >> NS('访问日志', cache_max_len=1, cache_max_age_seconds=60 * 60 * 24 * 30)

    if enable_webviews:
        for s in build_admin_streams(NS):
            s.webview(f'/{hash(s)}')

    if state.get("enable_stock", True) and not state.get("stock_initialized", False):
        try:
            from deva.admin_ui.stock.runtime import setup_stock_streams

            # Admin 统一管理 webview 挂载，股票管道这里仅负责产出流数据。
            setup_stock_streams(attach_webviews=False)
            state["stock_initialized"] = True
            {"level": "INFO", "source": "deva.admin", "message": "stock runtime initialized"} >> log
        except Exception as e:
            # 股票依赖是可选能力，失败不影响 admin 基础功能。
            {"level": "WARNING", "source": "deva.admin", "message": "stock runtime init failed", "error": str(e)} >> log

    if enable_scheduler and not scheduler.running:
        scheduler.start()

    state['initialized'] = True
