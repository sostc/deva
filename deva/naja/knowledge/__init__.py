"""Knowledge Layer - 学习层

职责：
- 外部知识采集：文章学习、AI日报、实时监听
- 知识状态管理：观察期 → 验证期 → 正式知识
- 因果知识注入：将学习到的因果关系注入认知系统

存储位置：deva/naja/knowledge/（方便 AI Agent 大模型读取）
"""

from .knowledge_store import KnowledgeStore, KnowledgeEntry, KnowledgeState, get_knowledge_store
from .state_manager import KnowledgeStateManager, KnowledgeState as State, get_state_manager
from .cognition_interface import CognitionInterface, get_cognition_interface
from .knowledge_exporter import KnowledgeExporter, get_knowledge_exporter
from .learning_ui import LearningUI, get_learning_ui
from .web_ui import (
    render_learning_page,
    render_knowledge_list_page,
    render_knowledge_history_page,
    render_knowledge_detail_page,
    handle_knowledge_action,
    render_knowledge_stats,
)

__all__ = [
    "KnowledgeStore",
    "KnowledgeEntry",
    "KnowledgeState",
    "get_knowledge_store",
    "KnowledgeStateManager",
    "State",
    "get_state_manager",
    "CognitionInterface",
    "get_cognition_interface",
    "KnowledgeExporter",
    "get_knowledge_exporter",
    "LearningUI",
    "get_learning_ui",
    "render_learning_page",
    "render_knowledge_list_page",
    "render_knowledge_history_page",
    "render_knowledge_detail_page",
    "handle_knowledge_action",
    "render_knowledge_stats",
]