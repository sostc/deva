"""路由注册"""

from pywebio.platform.tornado import webio_handler

from .pages import (
    main, dsadmin, signaladmin, taskadmin, strategyadmin,
    radaradmin, insightadmin, cognition_page, memory_page,
    llmadmin, banditadmin, bandit_attribution, market,
    awakening_page, dictadmin, tableadmin, runtimestateadmin,
    souladmin, configadmin, tuningadmin, system_page,
    narrative_page, narrative_lifecycle_page, merrill_clock_page,
    learningadmin, learning_list_page, learning_history_page,
    learning_detail_page, supplychain_page,
    KnowledgeActionHandler,
    _get_log_stream_page, _get_loop_audit_page,
)
from deva.naja.cognition.ui import cognition_glossary_page


def create_handlers(cdn: str = None):
    """创建路由处理器"""
    cdn_url = cdn or 'https://fastly.jsdelivr.net/gh/wang0618/PyWebIO-assets@v1.8.3/'

    return [
        (r'/', webio_handler(main, cdn=cdn_url)),
        (r'/cognition', webio_handler(cognition_page, cdn=cdn_url)),
        (r'/cognition_glossary', webio_handler(cognition_glossary_page, cdn=cdn_url)),
        (r'/memory', webio_handler(memory_page, cdn=cdn_url)),
        (r'/insight', webio_handler(insightadmin, cdn=cdn_url)),
        (r'/system', webio_handler(system_page, cdn=cdn_url)),
        (r'/performance', webio_handler(system_page, cdn=cdn_url)),
        (r'/signaladmin', webio_handler(signaladmin, cdn=cdn_url)),
        (r'/dsadmin', webio_handler(dsadmin, cdn=cdn_url)),
        (r'/taskadmin', webio_handler(taskadmin, cdn=cdn_url)),
        (r'/strategyadmin', webio_handler(strategyadmin, cdn=cdn_url)),
        (r'/radaradmin', webio_handler(radaradmin, cdn=cdn_url)),
        (r'/llmadmin', webio_handler(llmadmin, cdn=cdn_url)),
        (r'/banditadmin', webio_handler(banditadmin, cdn=cdn_url)),
        (r'/bandit_attribution', webio_handler(bandit_attribution, cdn=cdn_url)),
        (r'/market', webio_handler(market, cdn=cdn_url)),
        (r'/awakening', webio_handler(awakening_page, cdn=cdn_url)),
        (r'/dictadmin', webio_handler(dictadmin, cdn=cdn_url)),
        (r'/tableadmin', webio_handler(tableadmin, cdn=cdn_url)),
        (r'/runtime_state', webio_handler(runtimestateadmin, cdn=cdn_url)),
        (r'/configadmin', webio_handler(configadmin, cdn=cdn_url)),
        (r'/souladmin', webio_handler(souladmin, cdn=cdn_url)),
        (r'/logstream', webio_handler(lambda: _get_log_stream_page()(), cdn=cdn_url)),
        (r'/tuningadmin', webio_handler(tuningadmin, cdn=cdn_url)),
        (r'/supplychain', webio_handler(supplychain_page, cdn=cdn_url)),
        (r'/narrative', webio_handler(narrative_page, cdn=cdn_url)),
        (r'/narrative_lifecycle', webio_handler(narrative_lifecycle_page, cdn=cdn_url)),
        (r'/merrill_clock', webio_handler(merrill_clock_page, cdn=cdn_url)),
        (r'/loop_audit', webio_handler(lambda: _get_loop_audit_page()(), cdn=cdn_url)),
        (r'/learning', webio_handler(learningadmin, cdn=cdn_url)),
        (r'/learning/list', webio_handler(learning_list_page, cdn=cdn_url)),
        (r'/learning/history', webio_handler(learning_history_page, cdn=cdn_url)),
        (r'/learning/detail/(\w+)', webio_handler(learning_detail_page, cdn=cdn_url)),
        (r'/api/knowledge/action', KnowledgeActionHandler),
    ]

