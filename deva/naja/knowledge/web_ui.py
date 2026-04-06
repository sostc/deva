"""
Learning Layer Web UI - 学习层网页界面

提供知识管理的网页界面
"""

import json
from typing import Dict, Any

from deva.naja.knowledge import (
    get_learning_ui,
    get_knowledge_store,
    get_state_manager,
    get_knowledge_exporter,
    KnowledgeState,
)
from deva.naja.attention.blind_spot_investigator import CAUSAL_KNOWLEDGE


def render_learning_page(ctx: dict = None) -> str:
    """渲染学习层主页面"""
    learning_ui = get_learning_ui()
    return learning_ui.render_dashboard()


def render_knowledge_list_page(ctx: dict = None) -> str:
    """渲染知识列表页面"""
    learning_ui = get_learning_ui()

    status_filter = None
    if ctx and isinstance(ctx, dict):
        params = ctx.get("params", {})
        status_filter = params.get("status")

    return learning_ui.render_knowledge_list(status_filter=status_filter)


def render_knowledge_history_page(ctx: dict = None) -> str:
    """渲染状态转换历史页面"""
    learning_ui = get_learning_ui()
    return learning_ui.render_transition_history()


async def handle_knowledge_action(ctx: dict) -> Dict[str, Any]:
    """处理知识操作

    Args:
        ctx: 请求上下文，包含 action, entry_id, note 等参数

    Returns:
        操作结果
    """
    learning_ui = get_learning_ui()

    action = ctx.get("action", "")
    entry_id = ctx.get("entry_id", "")
    note = ctx.get("note", "")

    result = learning_ui.handle_action(action, entry_id, note)

    return result


def render_knowledge_stats(ctx: dict = None) -> Dict[str, Any]:
    """获取知识统计信息"""
    store = get_knowledge_store()
    state_manager = get_state_manager()
    exporter = get_knowledge_exporter()

    exporter.load_predefined(CAUSAL_KNOWLEDGE)

    return {
        "store_stats": store.get_stats(),
        "summary": exporter.get_summary(),
        "cooldown_info": {},
    }


def render_knowledge_detail_page(ctx: dict = None, entry_id: str = None) -> str:
    """渲染知识详情页面"""
    learning_ui = get_learning_ui()
    return learning_ui.render_knowledge_detail(entry_id)


__all__ = [
    "render_learning_page",
    "render_knowledge_list_page",
    "render_knowledge_history_page",
    "render_knowledge_detail_page",
    "handle_knowledge_action",
    "render_knowledge_stats",
]