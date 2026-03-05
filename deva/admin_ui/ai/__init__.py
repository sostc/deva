"""AI module - AI 功能中心."""


from .llm_service import (
    get_gpt_response,
)

__all__ = [
    # AI Center (aliased as admin_ai_center for admin.py compatibility)
    # AI Center functions

    # LLM Service
    'get_gpt_response',
]
