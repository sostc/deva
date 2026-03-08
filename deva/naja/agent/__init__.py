"""Naja 智能体模块

提供基于 deva 框架的智能体系统，包括:
- 张良：策略创建师
- 陈平：交易员
- 萧何：风控官
- 刘邦：监督者
"""

from .base import (
    BaseAgent,
    AgentMetadata,
    AgentState,
    AgentRole,
    AgentState as AgentStateEnum,
)

from .zhangliang import ZhangLiangAgent
from .hanxin import HanXinAgent
from .xiaohe import XiaoHeAgent
from .liubang import LiuBangAgent

from .manager import (
    AgentManager,
    get_agent_manager,
    create_four_agents,
)

__all__ = [
    # Base classes
    "BaseAgent",
    "AgentMetadata",
    "AgentState",
    "AgentRole",
    "AgentStateEnum",
    
    # Agent implementations
    "ZhangLiangAgent",
    "HanXinAgent",
    "XiaoHeAgent",
    "LiuBangAgent",
    
    # Manager
    "AgentManager",
    "get_agent_manager",
    "create_four_agents",
]
