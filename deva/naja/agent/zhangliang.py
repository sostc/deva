"""张良智能体 - 策略创建师

负责创建策略，分析策略逻辑，并告知韩信策略的逻辑。
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass, field

from deva import NB, Stream, bus, when
import logging

# 使用标准日志
log = logging.getLogger(__name__)
from deva.naja.agent.base import BaseAgent, AgentMetadata, AgentRole, AgentState
from deva.naja.strategy import get_strategy_manager, StrategyEntry, StrategyMetadata


@dataclass
class StrategyLogic:
    """策略逻辑描述"""
    strategy_name: str
    logic_description: str
    entry_conditions: List[str] = field(default_factory=list)
    exit_conditions: List[str] = field(default_factory=list)
    risk_controls: List[str] = field(default_factory=list)
    parameters: Dict[str, Any] = field(default_factory=dict)


class ZhangLiangAgent(BaseAgent):
    """张良智能体
    
    职责:
    1. 创建新的交易策略
    2. 分析策略逻辑
    3. 将策略逻辑告知陈平智能体
    4. 管理策略生命周期
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        metadata = AgentMetadata(
            name="张良",
            role=AgentRole.STRATEGIST,
            description="策略创建师 - 负责创建策略并分析策略逻辑",
            config=config or {}
        )
        super().__init__(metadata, config)
        
        self._strategy_cache: Dict[str, StrategyLogic] = {}
        self._hanxin_agent: Optional[str] = None  # 韩信智能体引用
    
    def set_hanxin_agent(self, agent_name: str):
        """设置韩信智能体的名称"""
        self._hanxin_agent = agent_name
        log.info(f"张良 -> 已绑定韩信智能体：{agent_name}")
    
    def create_strategy(
        self,
        strategy_name: str,
        code: str,
        datasource_id: str = "",
        window_size: int = 5,
        category: str = "默认"
    ) -> StrategyEntry:
        """创建新策略
        
        Args:
            strategy_name: 策略名称
            code: 策略代码
            datasource_id: 绑定的数据源 ID
            window_size: 窗口大小
            category: 策略类别
            
        Returns:
            StrategyEntry: 策略条目
        """
        try:
            strategy_mgr = get_strategy_manager()
            
            metadata = StrategyMetadata(
                bound_datasource_id=datasource_id,
                window_size=window_size,
                category=category,
                diagram_info={"created_by": "张良智能体"}
            )
            
            strategy = StrategyEntry(metadata=metadata)
            strategy.set_code(code)
            strategy.set_name(strategy_name)
            
            strategy_mgr.add(strategy_name, strategy)
            
            log.info(f"张良：已创建策略 [{strategy_name}]")
            
            strategy_logic = self._analyze_strategy_logic(strategy_name, code)
            self._strategy_cache[strategy_name] = strategy_logic
            
            self._notify_hanxin(strategy_name, strategy_logic)
            
            self._increment_metric('strategies_created')
            
            return strategy
            
        except Exception as e:
            self._handle_error(e)
            raise
    
    def analyze_strategy(self, strategy_name: str) -> StrategyLogic:
        """分析策略逻辑
        
        Args:
            strategy_name: 策略名称
            
        Returns:
            StrategyLogic: 策略逻辑描述
        """
        if strategy_name in self._strategy_cache:
            return self._strategy_cache[strategy_name]
        
        strategy_mgr = get_strategy_manager()
        strategy = strategy_mgr.get(strategy_name)
        
        if not strategy:
            raise ValueError(f"策略 [{strategy_name}] 不存在")
        
        code = strategy.get_code()
        logic = self._analyze_strategy_logic(strategy_name, code)
        self._strategy_cache[strategy_name] = logic
        
        return logic
    
    def update_strategy_logic(
        self,
        strategy_name: str,
        logic_update: Dict[str, Any]
    ):
        """更新策略逻辑
        
        Args:
            strategy_name: 策略名称
            logic_update: 逻辑更新内容
        """
        if strategy_name not in self._strategy_cache:
            self.analyze_strategy(strategy_name)
        
        logic = self._strategy_cache[strategy_name]
        
        if 'entry_conditions' in logic_update:
            logic.entry_conditions = logic_update['entry_conditions']
        if 'exit_conditions' in logic_update:
            logic.exit_conditions = logic_update['exit_conditions']
        if 'risk_controls' in logic_update:
            logic.risk_controls = logic_update['risk_controls']
        if 'parameters' in logic_update:
            logic.parameters.update(logic_update['parameters'])
        
        self._notify_hanxin(strategy_name, logic)
        log.info(f"张良：已更新策略 [{strategy_name}] 逻辑并通知韩信")
    
    def get_all_strategies(self) -> List[Dict[str, Any]]:
        """获取所有策略信息"""
        strategy_mgr = get_strategy_manager()
        strategies = []
        
        # 使用list_all()方法获取策略列表
        entries = strategy_mgr.list_all()
        for strategy in entries:
            info = {
                'name': strategy.name,
                'state': strategy._state.value if hasattr(strategy._state, 'value') else str(strategy._state),
                'datasource': strategy._metadata.bound_datasource_id,
                'category': strategy._metadata.category,
            }
            
            if strategy.name in self._strategy_cache:
                logic = self._strategy_cache[strategy.name]
                info['logic'] = {
                    'description': logic.logic_description,
                    'entry_count': len(logic.entry_conditions),
                    'exit_count': len(logic.exit_conditions),
                }
            
            strategies.append(info)
        
        return strategies
    
    def _do_initialize(self):
        """初始化"""
        log.info("张良智能体初始化中...")
        self._load_strategies_from_db()
    
    def _do_start(self):
        """启动"""
        log.info("张良智能体启动")
        # 不自动加载策略，等待刘邦通知
    
    def start_river_strategies(self, data_source_id: Optional[str] = None) -> Dict[str, bool]:
        """启动 river 类别的所有策略
        
        Args:
            data_source_id: 数据源ID，如果不提供则自动查找
            
        Returns:
            Dict[str, bool]: 策略启动结果
        """
        try:
            from deva.naja.strategy import get_strategy_manager
            from deva.naja.datasource import get_datasource_manager
            
            strategy_mgr = get_strategy_manager()
            # 加载策略
            strategy_mgr.load_from_db()
            log.info(f"张良：已从数据库加载策略")
            
            ds_mgr = get_datasource_manager()
            ds_mgr.load_from_db()
            
            # 查找行情回放数据源
            replay_ds = None
            if data_source_id:
                # 使用指定的数据源ID
                for ds in ds_mgr.list_all():
                    if ds.id == data_source_id:
                        replay_ds = ds
                        break
                if replay_ds:
                    log.info(f"张良：使用指定的数据源 [{replay_ds.name}] (ID: {replay_ds.id})")
                else:
                    log.warning(f"张良：未找到指定的数据源 (ID: {data_source_id})")
                    # 尝试自动查找
                    for ds in ds_mgr.list_all():
                        ds_name = getattr(ds, "name", "")
                        if "回放" in ds_name or "replay" in ds_name.lower():
                            replay_ds = ds
                            break
            else:
                # 自动查找行情回放数据源
                for ds in ds_mgr.list_all():
                    ds_name = getattr(ds, "name", "")
                    if "回放" in ds_name or "replay" in ds_name.lower():
                        replay_ds = ds
                        break
            
            if not replay_ds:
                log.warning("张良：未找到行情回放数据源")
                return {}
            
            results = {}
            # 使用list_all()方法获取策略列表
            entries = strategy_mgr.list_all()
            
            # 用于跟踪已处理的策略名称，避免重复处理
            processed_strategies = set()
            
            for entry in entries:
                if entry.name.lower().startswith('river'):
                    # 检查是否已经处理过该策略名称
                    if entry.name in processed_strategies:
                        log.info(f"张良：策略 [{entry.name}] 已经处理过，跳过")
                        continue
                    
                    # 绑定数据源
                    old_datasource_id = entry._metadata.bound_datasource_id
                    entry._metadata.bound_datasource_id = replay_ds.id
                    log.info(f"张良：已将策略 [{entry.name}] 从数据源 [{old_datasource_id}] 重新绑定到 [{replay_ds.name}] ({replay_ds.id})")
                    
                    # 启动策略
                    log.info(f"张良：正在启动策略 [{entry.name}]...")
                    result = entry.start()
                    
                    if result.get('success', False):
                        log.info(f"张良：策略 [{entry.name}] 启动成功")
                        results[entry.name] = True
                    else:
                        log.error(f"张良：启动策略失败 [{entry.name}]: {result.get('error', '')}")
                        results[entry.name] = False
                    
                    # 标记该策略名称已处理
                    processed_strategies.add(entry.name)
            
            if not results:
                log.warning("张良：未找到 river 类别的策略")
            else:
                log.info(f"张良：已启动 {len(results)} 个 river 策略")
            
            return results
        except Exception as e:
            log.error(f"张良：启动 river 策略失败：{e}")
            return {}
    
    def _do_stop(self):
        """停止"""
        log.info("张良智能体停止")
    
    def _do_pause(self):
        """暂停"""
        log.info("张良智能体暂停")
    
    def _do_resume(self):
        """恢复"""
        log.info("张良智能体恢复")
    
    def _handle_message(self, message: Dict[str, Any]):
        """处理消息"""
        msg_type = message.get('type')
        
        if msg_type == 'strategy_query':
            strategy_name = message.get('strategy_name')
            if strategy_name:
                logic = self.analyze_strategy(strategy_name)
                self.send_message({
                    'type': 'strategy_logic_response',
                    'to': message.get('from'),
                    'strategy_name': strategy_name,
                    'logic': logic
                })
        
        elif msg_type == 'create_strategy_request':
            strategy_name = message.get('strategy_name')
            code = message.get('code')
            datasource_id = message.get('datasource_id')
            
            if strategy_name and code:
                strategy = self.create_strategy(
                    strategy_name=strategy_name,
                    code=code,
                    datasource_id=datasource_id or ""
                )
                self.send_message({
                    'type': 'strategy_created',
                    'to': message.get('from'),
                    'strategy_name': strategy_name,
                    'success': True
                })
        
        elif msg_type == 'start_river_strategies':
            # 处理刘邦发送的启动river策略的消息
            log.info("张良：收到启动river策略的通知")
            # 获取数据源ID
            data_source_id = message.get('data_source_id')
            if data_source_id:
                log.info(f"张良：收到刘邦传递的数据源ID [{data_source_id}]")
            results = self.start_river_strategies(data_source_id=data_source_id)
            
            # 发送启动结果给刘邦
            self.send_message({
                'type': 'river_strategies_started',
                'to': '刘邦',
                'results': results,
                'message': f'已启动 {len(results)} 个 river 策略'
            })
        
        elif msg_type == 'issue_assigned':
            # 处理刘邦分发的问题
            issue_id = message.get('issue_id')
            issue_type = message.get('issue_type')
            description = message.get('description')
            
            log.info(f"张良：收到分配的问题 [{issue_id}]: {description}")
            
            # 处理策略相关问题
            if issue_type == 'strategy':
                # 这里可以添加具体的问题处理逻辑
                log.info(f"张良：处理策略问题 [{issue_id}]")
                
                # 发送处理结果
                self.send_message({
                    'type': 'issue_handled',
                    'to': '刘邦',
                    'issue_id': issue_id,
                    'status': 'resolved',
                    'message': f'策略问题已处理：{description}',
                    'handled_by': '张良',
                    'timestamp': time.time()
                })
            else:
                log.warning(f"张良：收到非策略类型的问题 [{issue_id}]: {issue_type}")
    

    

    
    def _analyze_strategy_logic(self, strategy_name: str, code: str) -> StrategyLogic:
        """分析策略逻辑
        
        通过静态分析代码提取策略逻辑。
        """
        logic_description = ""
        entry_conditions = []
        exit_conditions = []
        risk_controls = []
        parameters = {}
        
        if 'buy' in code.lower() or '买入' in code:
            entry_conditions.append("满足买入条件时执行买入操作")
        
        if 'sell' in code.lower() or '卖出' in code:
            exit_conditions.append("满足卖出条件时执行卖出操作")
        
        if 'stop_loss' in code.lower() or '止损' in code:
            risk_controls.append("设置止损机制")
        
        if 'position' in code.lower() or '仓位' in code:
            risk_controls.append("包含仓位管理逻辑")
        
        if 'window' in code.lower() or '窗口' in code:
            logic_description = "基于时间窗口的策略"
        elif 'signal' in code.lower() or '信号' in code:
            logic_description = "基于信号驱动的策略"
        else:
            logic_description = "自定义交易策略"
        
        return StrategyLogic(
            strategy_name=strategy_name,
            logic_description=logic_description,
            entry_conditions=entry_conditions,
            exit_conditions=exit_conditions,
            risk_controls=risk_controls,
            parameters=parameters
        )
    
    def _notify_hanxin(self, strategy_name: str, logic: StrategyLogic):
        """通知韩信智能体策略逻辑"""
        if not self._hanxin_agent:
            log.warning(f"张良：未绑定韩信智能体，无法通知策略 [{strategy_name}] 逻辑")
            return
        
        message = {
            'type': 'strategy_logic_notification',
            'to': self._hanxin_agent,
            'strategy_name': strategy_name,
            'logic': {
                'description': logic.logic_description,
                'entry_conditions': logic.entry_conditions,
                'exit_conditions': logic.exit_conditions,
                'risk_controls': logic.risk_controls,
                'parameters': logic.parameters
            },
            'timestamp': time.time()
        }
        
        self.send_message(message)
        log.info(f"张良：已通知韩信策略 [{strategy_name}] 的逻辑")
    
    def _load_strategies_from_db(self):
        """从数据库加载策略"""
        # 空实现，等待刘邦通知时才加载策略
        pass
