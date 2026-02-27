"""AI module - AI 功能中心."""

from .ai_center import (
    render_ai_tab_ui as admin_ai_center,
    show_ai_chat,
    show_ai_code_generator,
    show_python_code_gen,
    show_deva_strategy_gen,
    show_deva_datasource_gen,
    show_deva_task_gen,
    show_ai_text_processor,
    show_text_summary,
    show_translation,
    show_text_polish,
    show_text_analysis,
)

from .ai_code_creator import (
    show_ai_code_creator,
)

from .ai_studio import (
    show_ai_studio,
)

from .ai_code_generator import (
    AICodeGenerator,
    StrategyAIGenerator,
    DataSourceAIGenerator,
    TaskAIGenerator,
)

from .ai_strategy_generator import (
    analyze_data_schema,
    generate_strategy_code,
    validate_strategy_code,
    test_strategy_code,
    generate_strategy_documentation,
)

from .llm_service import (
    get_gpt_response,
)

__all__ = [
    # AI Center (aliased as admin_ai_center for admin.py compatibility)
    'admin_ai_center',
    # AI Center functions
    'show_ai_chat',
    'show_ai_code_generator',
    'show_python_code_gen',
    'show_deva_strategy_gen',
    'show_deva_datasource_gen',
    'show_deva_task_gen',
    'show_ai_text_processor',
    'show_text_summary',
    'show_translation',
    'show_text_polish',
    'show_text_analysis',
    # AI Code Creator
    'show_ai_code_creator',
    # AI Studio
    'show_ai_studio',
    # AI Code Generators
    'AICodeGenerator',
    'StrategyAIGenerator',
    'DataSourceAIGenerator',
    'TaskAIGenerator',
    # AI Strategy Generator
    'analyze_data_schema',
    'generate_strategy_code',
    'validate_strategy_code',
    'test_strategy_code',
    'generate_strategy_documentation',
    # LLM Service
    'get_gpt_response',
]
