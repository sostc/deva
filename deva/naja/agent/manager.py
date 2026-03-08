"""智能体管理器模块

提供智能体的统一管理、初始化和协调功能。
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Type

from deva import NB, log as deva_log
import logging

# 使用标准日志
log = logging.getLogger(__name__)
from deva.naja.agent.base import BaseAgent, AgentMetadata, AgentRole
from deva.naja.agent.zhangliang import ZhangLiangAgent
from deva.naja.agent.hanxin import HanXinAgent
from deva.naja.agent.xiaohe import XiaoHeAgent
from deva.naja.agent.liubang import LiuBangAgent


class AgentManager:
    """智能体管理器
    
    负责:
    1. 创建和注册智能体
    2. 管理智能体生命周期
    3. 协调整体系统运行
    4. 提供系统级监控
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if getattr(self, '_initialized', False):
            return
        
        self._agents: Dict[str, BaseAgent] = {}
        self._config: Dict[str, Any] = {}
        self._initialized = True
        
        log.info("智能体管理器初始化完成")
    
    def create_agent(
        self,
        agent_type: str,
        name: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None
    ) -> BaseAgent:
        """创建智能体
        
        Args:
            agent_type: 智能体类型 (zhangliang, chenping, xiaohe, liubang)
            name: 智能体名称 (可选，默认使用内置名称)
            config: 配置参数
            
        Returns:
            BaseAgent: 创建的智能体实例
        """
        agent_classes = {
            'zhangliang': ZhangLiangAgent,
            '张良': ZhangLiangAgent,
            'hanxin': HanXinAgent,
            '韩信': HanXinAgent,
            'xiaohe': XiaoHeAgent,
            '萧何': XiaoHeAgent,
            'liubang': LiuBangAgent,
            '刘邦': LiuBangAgent,
        }
        
        if agent_type not in agent_classes:
            raise ValueError(f"未知的智能体类型：{agent_type}")
        
        agent_class = agent_classes[agent_type]
        agent = agent_class(config=config)
        
        if name:
            agent._metadata.name = name
        
        self.register_agent(agent)
        
        return agent
    
    def register_agent(self, agent: BaseAgent):
        """注册智能体"""
        self._agents[agent.name] = agent
        log.info(f"已注册智能体 [{agent.name}] 角色={agent.role.value}")
        
        if '刘邦' in self._agents:
            liubang = self._agents['刘邦']
            if isinstance(liubang, LiuBangAgent):
                liubang.register_agent(agent)
    
    def get_agent(self, name: str) -> Optional[BaseAgent]:
        """获取智能体"""
        return self._agents.get(name)
    
    def get_all_agents(self) -> Dict[str, BaseAgent]:
        """获取所有智能体"""
        return self._agents.copy()
    
    def start_agent(self, name: str) -> bool:
        """启动智能体"""
        agent = self.get_agent(name)
        if not agent:
            log.error(f"智能体 [{name}] 不存在")
            return False
        
        try:
            agent.start()
            return True
        except Exception as e:
            log.error(f"启动智能体 [{name}] 失败：{e}")
            return False
    
    def stop_agent(self, name: str) -> bool:
        """停止智能体"""
        agent = self.get_agent(name)
        if not agent:
            log.error(f"智能体 [{name}] 不存在")
            return False
        
        try:
            agent.stop()
            return True
        except Exception as e:
            log.error(f"停止智能体 [{name}] 失败：{e}")
            return False
    
    def start_all_agents(self):
        """启动所有智能体"""
        log.info("启动所有智能体")
        
        for name, agent in self._agents.items():
            try:
                agent.start()
                log.info(f"智能体 [{name}] 已启动")
            except Exception as e:
                log.error(f"启动智能体 [{name}] 失败：{e}")
    
    def stop_all_agents(self):
        """停止所有智能体"""
        log.info("停止所有智能体")
        
        for name, agent in self._agents.items():
            try:
                agent.stop()
                log.info(f"智能体 [{name}] 已停止")
            except Exception as e:
                log.error(f"停止智能体 [{name}] 失败：{e}")
    
    def initialize_four_agents(
        self,
        config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, BaseAgent]:
        """初始化四个智能体（张良、陈平、萧何、刘邦）
        
        Args:
            config: 全局配置
            
        Returns:
            Dict[str, BaseAgent]: 四个智能体实例
        """
        config = config or {}
        
        log.info("初始化四个智能体...")
        
        zhangliang = self.create_agent('zhangliang', config=config.get('zhangliang', {}))
        log.info("✓ 张良智能体已创建")
        
        hanxin = self.create_agent('hanxin', config=config.get('hanxin', {}))
        log.info("✓ 韩信智能体已创建")
        
        xiaohe = self.create_agent('xiaohe', config=config.get('xiaohe', {}))
        log.info("✓ 萧何智能体已创建")
        
        liubang = self.create_agent('liubang', config=config.get('liubang', {}))
        log.info("✓ 刘邦智能体已创建")
        
        liubang.register_agent(zhangliang)
        liubang.register_agent(hanxin)
        liubang.register_agent(xiaohe)
        
        # 设置智能体之间的协调关系
        zhangliang.set_hanxin_agent('韩信')
        hanxin.set_zhangliang_agent('张良')
        hanxin.set_xiaohe_agent('萧何')
        
        log.info("✓ 智能体协调关系已建立")
        
        return {
            '张良': zhangliang,
            '韩信': hanxin,
            '萧何': xiaohe,
            '刘邦': liubang
        }
    
    def get_system_status(self) -> Dict[str, Any]:
        """获取系统状态"""
        status = {
            'timestamp': time.time(),
            'agent_count': len(self._agents),
            'agents': {}
        }
        
        for name, agent in self._agents.items():
            status['agents'][name] = {
                'role': agent.role.value,
                'state': agent.state.state.value,
                'errors': agent.state.error_count,
                'last_action': agent.state.last_action_ts
            }
        
        if '刘邦' in self._agents:
            liubang = self._agents['刘邦']
            if isinstance(liubang, LiuBangAgent):
                status['system_metrics'] = liubang.get_system_metrics().__dict__
        
        return status
    
    def export_config(self) -> Dict[str, Any]:
        """导出配置"""
        return {
            'agents': {
                name: {
                    'role': agent.role.value,
                    'config': agent._config
                }
                for name, agent in self._agents.items()
            }
        }
    
    def import_config(self, config: Dict[str, Any]):
        """导入配置"""
        self._config = config


_agent_manager: Optional[AgentManager] = None


def get_agent_manager() -> AgentManager:
    """获取智能体管理器单例"""
    global _agent_manager
    if _agent_manager is None:
        _agent_manager = AgentManager()
    return _agent_manager


def create_four_agents(config: Optional[Dict[str, Any]] = None) -> Dict[str, BaseAgent]:
    """便捷函数：创建四个智能体"""
    manager = get_agent_manager()
    return manager.initialize_four_agents(config)
