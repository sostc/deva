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

    if enable_scheduler and not scheduler.running:
        scheduler.start()

    state['initialized'] = True
