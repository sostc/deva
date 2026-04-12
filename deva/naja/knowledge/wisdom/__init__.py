"""
Wisdom - 知识库检索模块

从爸爸的知识库中检索相关文章，用于：
1. 在合适的时机分享给爸爸
2. 校准 Naja 自身的价值观
"""

from .wisdom_retriever import (
    WisdomRetriever,
    WisdomSpeaker,
    WisdomSnippet,
    TriggerContext,
    retrieve_wisdom,
    format_wisdom_for_speech,
)

__all__ = [
    "WisdomRetriever",
    "WisdomSpeaker",
    "WisdomSnippet",
    "TriggerContext",
    "retrieve_wisdom",
    "format_wisdom_for_speech",
]
