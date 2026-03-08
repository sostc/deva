"""刘邦智能体 - 总体监督和协调者

负责监督其他智能体，总把控项目运行。
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum

from deva import NB, Stream, bus, when, timer
import logging

# 使用标准日志
log = logging.getLogger(__name__)
from deva.naja.agent.base import BaseAgent, AgentMetadata, AgentRole, AgentState
from deva.naja.agent.zhangliang import ZhangLiangAgent
from deva.naja.agent.hanxin import HanXinAgent
from deva.naja.agent.xiaohe import XiaoHeAgent


class SystemHealth(Enum):
    """系统健康状态"""
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class AgentStatus:
    """智能体状态"""
    name: str
    role: str
    state: str
    last_action_ts: float
    action_count: int
    error_count: int
    health: SystemHealth


@dataclass
class SystemMetrics:
    """系统指标"""
    total_strategies: int = 0
    active_strategies: int = 0
    total_trades: int = 0
    total_positions: int = 0
    total_capital: float = 0.0
    available_capital: float = 0.0
    system_health: SystemHealth = SystemHealth.HEALTHY
    last_update_ts: float = 0.0


class LiuBangAgent(BaseAgent):
    """刘邦智能体
    
    职责:
    1. 监督其他智能体运行状态
    2. 协调整体系统运行
    3. 系统健康监控
    4. 异常处理和告警
    5. 性能优化建议
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        metadata = AgentMetadata(
            name="刘邦",
            role=AgentRole.SUPERVISOR,
            description="监督者 - 负责总把控项目和协调其他智能体",
            config=config or {}
        )
        super().__init__(metadata, config)
        
        self._agents: Dict[str, BaseAgent] = {}
        self._system_metrics = SystemMetrics()
        self._health_history: List[Dict[str, Any]] = []
        
        self._health_check_interval = self._config.get('health_check_interval', 30)
        self._alert_thresholds = self._config.get('alert_thresholds', {
            'error_count': 5,
            'max_drawdown': 0.1,
            'min_capital_ratio': 0.2
        })
        
        self._alerts: List[Dict[str, Any]] = []
        self._performance_log: List[Dict[str, Any]] = []
        self._issue_history: List[Dict[str, Any]] = []
    
    def register_agent(self, agent: BaseAgent):
        """注册智能体"""
        self._agents[agent.name] = agent
        log.info(f"刘邦：已注册智能体 [{agent.name}] 角色={agent.role.value}")
    
    def unregister_agent(self, agent_name: str):
        """注销智能体"""
        if agent_name in self._agents:
            del self._agents[agent_name]
            log.info(f"刘邦：已注销智能体 [{agent_name}]")
    
    def get_agent_status(self, agent_name: str) -> Optional[AgentStatus]:
        """获取智能体状态"""
        if agent_name not in self._agents:
            return None
        
        agent = self._agents[agent_name]
        
        health = SystemHealth.HEALTHY
        if agent.state.error_count >= self._alert_thresholds.get('error_count', 5):
            health = SystemHealth.CRITICAL
        elif agent.state.error_count >= 2:
            health = SystemHealth.WARNING
        
        return AgentStatus(
            name=agent.name,
            role=agent.role.value,
            state=agent.state.state.value,
            last_action_ts=agent.state.last_action_ts,
            action_count=agent.state.action_count,
            error_count=agent.state.error_count,
            health=health
        )
    
    def get_all_agent_statuses(self) -> List[AgentStatus]:
        """获取所有智能体状态"""
        return [self.get_agent_status(name) for name in self._agents.keys()]
    
    def get_system_metrics(self) -> SystemMetrics:
        """获取系统指标"""
        self._update_system_metrics()
        return self._system_metrics
    
    def check_system_health(self) -> SystemHealth:
        """检查系统健康状态"""
        critical_count = 0
        warning_count = 0
        
        for agent_name in self._agents:
            status = self.get_agent_status(agent_name)
            if status:
                if status.health == SystemHealth.CRITICAL:
                    critical_count += 1
                elif status.health == SystemHealth.WARNING:
                    warning_count += 1
        
        if critical_count > 0:
            return SystemHealth.CRITICAL
        elif warning_count >= 2:
            return SystemHealth.WARNING
        else:
            return SystemHealth.HEALTHY
    
    def start_all_agents(self):
        """启动所有智能体"""
        log.info("刘邦：启动所有智能体")
        
        for agent_name, agent in self._agents.items():
            try:
                agent.start()
                log.info(f"刘邦：智能体 [{agent_name}] 已启动")
            except Exception as e:
                log.error(f"刘邦：启动智能体 [{agent_name}] 失败：{e}")
                self._create_alert('error', f'启动智能体 {agent_name} 失败', str(e))
    
    def stop_all_agents(self):
        """停止所有智能体"""
        log.info("刘邦：停止所有智能体")
        
        for agent_name, agent in self._agents.items():
            try:
                agent.stop()
                log.info(f"刘邦：智能体 [{agent_name}] 已停止")
            except Exception as e:
                log.error(f"刘邦：停止智能体 [{agent_name}] 失败：{e}")
    
    def pause_all_agents(self):
        """暂停所有智能体"""
        log.info("刘邦：暂停所有智能体")
        
        for agent_name, agent in self._agents.items():
            try:
                agent.pause()
            except Exception as e:
                log.error(f"刘邦：暂停智能体 [{agent_name}] 失败：{e}")
    
    def resume_all_agents(self):
        """恢复所有智能体"""
        log.info("刘邦：恢复所有智能体")
        
        for agent_name, agent in self._agents.items():
            try:
                agent.resume()
            except Exception as e:
                log.error(f"刘邦：恢复智能体 [{agent_name}] 失败：{e}")
    
    def get_alerts(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取告警列表"""
        return self._alerts[-limit:]
    
    def get_performance_report(self) -> Dict[str, Any]:
        """获取性能报告"""
        self._update_system_metrics()
        
        return {
            'timestamp': time.time(),
            'system_health': self._system_metrics.system_health.value,
            'agents': {
                name: {
                    'state': status.state,
                    'health': status.health.value,
                    'errors': status.error_count
                }
                for name, status in [(n, self.get_agent_status(n)) for n in self._agents.keys()]
                if status
            },
            'strategies': {
                'total': self._system_metrics.total_strategies,
                'active': self._system_metrics.active_strategies
            },
            'trades': {
                'total': self._system_metrics.total_trades
            },
            'capital': {
                'total': self._system_metrics.total_capital,
                'available': self._system_metrics.available_capital,
                'usage_ratio': (self._system_metrics.total_capital - self._system_metrics.available_capital) / self._system_metrics.total_capital if self._system_metrics.total_capital > 0 else 0
            }
        }
    
    def optimize_system(self) -> List[str]:
        """系统优化建议"""
        suggestions = []
        
        for agent_name, agent in self._agents.items():
            if agent.state.error_count >= 3:
                suggestions.append(f"检查智能体 {agent_name} 的错误日志")
            
            if agent.state.state == AgentState.ERROR:
                suggestions.append(f"智能体 {agent_name} 处于错误状态，需要重启")
        
        if self._system_metrics.system_health == SystemHealth.WARNING:
            suggestions.append("系统处于警告状态，建议检查各智能体运行情况")
        elif self._system_metrics.system_health == SystemHealth.CRITICAL:
            suggestions.append("系统处于严重状态，建议立即干预")
        
        return suggestions
    
    
    
    def _do_initialize(self):
        """初始化"""
        log.info("刘邦智能体初始化中...")
        self._setup_agent_coordination()
    
    def get_replay_datasource(self):
        """获取行情回放数据源
        
        Returns:
            成功返回数据源对象，失败返回None
        """
        try:
            from deva.naja.datasource import get_datasource_manager
            
            ds_mgr = get_datasource_manager()
            
            # 确保数据源已从数据库加载
            ds_mgr.load_from_db()
            
            # 查找行情回放数据源
            replay_ds = None
            for ds in ds_mgr.list_all():
                ds_name = getattr(ds, "name", "")
                if "回放" in ds_name or "replay" in ds_name.lower():
                    replay_ds = ds
                    break
            
            if not replay_ds:
                log.warning(f"刘邦：未找到行情回放数据源")
                return None
            
            return replay_ds
        except Exception as e:
            log.error(f"刘邦：获取行情回放数据源失败：{e}")
            return None

    def start_replay_datasource(self, interval: float = 1.0):
        """启动行情回放数据源
        
        Args:
            interval: 回放间隔（秒）
            
        Returns:
            成功返回数据源对象，失败返回None
        """
        try:
            # 获取行情回放数据源
            replay_ds = self.get_replay_datasource()
            
            if not replay_ds:
                return None
            
            # 设置回放间隔
            if hasattr(replay_ds, '_metadata') and hasattr(replay_ds._metadata, 'config'):
                if not replay_ds._metadata.config:
                    replay_ds._metadata.config = {}
                replay_ds._metadata.config['interval'] = interval
                log.info(f"刘邦：已设置数据源 [{replay_ds.name}] 回放间隔为 {interval} 秒")
            
            # 启动数据源
            log.info(f"刘邦：正在启动数据源 [{replay_ds.name}]...")
            start_result = replay_ds.start()
            
            if start_result.get('success'):
                log.info(f"刘邦：数据源 [{replay_ds.name}] 启动成功")
                
                # 发送消息通知萧何订阅数据源
                self.send_message({
                    'type': 'subscribe_data_source',
                    'to': '萧何',
                    'data_source_id': replay_ds.id,
                    'data_source_name': replay_ds.name,
                    'message': f'请订阅行情回放数据源 [{replay_ds.name}]'
                })
                log.info(f"刘邦：已通知萧何订阅行情回放数据源 [{replay_ds.name}]")
                
                # 保存数据源引用
                self.replay_ds = replay_ds
                return replay_ds
            else:
                log.error(f"刘邦：数据源 [{replay_ds.name}] 启动失败：{start_result.get('error', '')}")
                return None
        except Exception as e:
            log.error(f"刘邦：启动行情回放数据源失败：{e}")
            return None

    def _do_start(self):
        """启动实现"""
        log.info("刘邦智能体启动")
        
        # 启动其他三个智能体：萧何、韩信、张良
        self._start_agent('萧何')
        self._start_agent('张良')
        self._start_agent('韩信')
        
        # 启动行情回放数据源
        log.info("刘邦：启动行情回放数据源")
        # 默认间隔为 1 秒，可通过参数修改
        replay_ds = self.start_replay_datasource()
        
        # 通知张良启动river策略
        log.info("刘邦：通知张良启动river策略")
        message = {
            'type': 'start_river_strategies',
            'to': '张良',
            'message': '请启动所有river策略'
        }
        
        # 如果找到数据源，添加数据源ID
        if replay_ds:
            message['data_source_id'] = replay_ds.id
            message['data_source_name'] = replay_ds.name
            log.info(f"刘邦：传递数据源ID [{replay_ds.id}] 给张良")
        
        self.send_message(message)
        
        # 等待一段时间，确保张良有足够时间处理消息
        import time
        time.sleep(2)
        
        @timer(interval=self._health_check_interval, start=True)
        def health_check():
            if self._state.state == AgentState.RUNNING:
                self._perform_health_check()
    
    def _do_stop(self):
        """停止"""
        log.info("刘邦智能体停止")
    
    def _do_pause(self):
        """暂停"""
        log.info("刘邦智能体暂停")
    
    def _do_resume(self):
        """恢复"""
        log.info("刘邦智能体恢复")
    
    def _handle_message(self, message: Dict[str, Any]):
        """处理消息"""
        msg_type = message.get('type')
        
        if msg_type == 'agent_registered':
            agent_name = message.get('agent_name')
            log.info(f"刘邦：收到智能体注册通知 [{agent_name}]")
        
        elif msg_type == 'error_report':
            agent_name = message.get('agent_name')
            error = message.get('error')
            self._create_alert('error', f'智能体 {agent_name} 错误', error)
        
        elif msg_type == 'query_system_status':
            report = self.get_performance_report()
            self.send_message({
                'type': 'system_status_response',
                'to': message.get('from'),
                'report': report
            })
        
        elif msg_type == 'query_alerts':
            alerts = self.get_alerts()
            self.send_message({
                'type': 'alerts_response',
                'to': message.get('from'),
                'alerts': alerts
            })
        
        elif msg_type == 'data_source_subscribed':
            # 处理萧何订阅数据源成功的消息
            data_source_id = message.get('data_source_id')
            data_source_name = message.get('data_source_name')
            
            log.info(f"刘邦：收到萧何订阅数据源成功的消息，数据源：{data_source_name} (ID: {data_source_id})")
        
        elif msg_type == 'data_source_subscribe_failed':
            # 处理萧何订阅数据源失败的消息
            data_source_id = message.get('data_source_id')
            data_source_name = message.get('data_source_name')
            error_message = message.get('message')
            
            log.error(f"刘邦：收到萧何订阅数据源失败的消息，数据源：{data_source_name} (ID: {data_source_id})，原因：{error_message}")
            self._create_alert('error', '数据源订阅失败', f'萧何无法订阅数据源 {data_source_name}：{error_message}')
        
        elif msg_type == 'trade_failed':
            # 处理韩信无法交易的消息
            reason = message.get('reason')
            stock_name = message.get('stock_name')
            stock_code = message.get('stock_code')
            strategy_name = message.get('strategy_name')
            
            log.error(f"刘邦：收到韩信无法交易的消息，股票：{stock_name}({stock_code})，策略：{strategy_name}，原因：{reason}")
            self._create_alert('error', '交易失败', f'韩信无法执行交易：{reason}')
            
            # 停止数据源
            self._stop_replay_datasource()
            
            # 通知萧何汇报持仓盈亏情况
            self.send_message({
                'type': 'report_positions',
                'to': '萧何',
                'message': '请汇报当前持仓盈亏情况'
            })
        
        elif msg_type == 'positions_report':
            # 处理萧何的持仓报告
            total_pnl = message.get('total_pnl', 0)
            position_count = message.get('position_count', 0)
            report_message = message.get('message', '')
            
            log.info(f"刘邦：收到萧何的持仓报告：{report_message}")
            
            # 检查是否亏损
            if total_pnl < 0:
                log.error(f"刘邦：交易亏损 {total_pnl:.2f}，责骂张良！")
                
                # 通知张良
                self.send_message({
                    'type': 'scold',
                    'to': '张良',
                    'message': f'张良，你制定的策略导致亏损 {total_pnl:.2f}，必须改进！'
                })
                
                # 退出程序
                log.error("刘邦：交易亏损，程序退出")
                import sys
                sys.exit(1)
            else:
                log.info("刘邦：交易盈利，继续运行")
    

    

    
    def _setup_agent_coordination(self):
        """设置智能体协调"""
        zhangliang = None
        hanxin = None
        xiaohe = None
        
        for name, agent in self._agents.items():
            if isinstance(agent, ZhangLiangAgent):
                zhangliang = agent
            elif isinstance(agent, HanXinAgent):
                hanxin = agent
            elif isinstance(agent, XiaoHeAgent):
                xiaohe = agent
        
        if zhangliang and hanxin:
            zhangliang.set_hanxin_agent(hanxin.name)
            log.info("刘邦：已建立 张良 -> 韩信 协调关系")
        
        if hanxin and xiaohe:
            hanxin.set_xiaohe_agent(xiaohe.name)
            log.info("刘邦：已建立 韩信 -> 萧何 协调关系")
    
    def _perform_health_check(self):
        """执行健康检查"""
        health = self.check_system_health()
        
        self._system_metrics.system_health = health
        self._system_metrics.last_update_ts = time.time()
        
        health_record = {
            'timestamp': time.time(),
            'health': health.value,
            'agent_count': len(self._agents),
            'active_agents': sum(1 for s in self.get_all_agent_statuses() if s.state == AgentState.RUNNING.value)
        }
        
        self._health_history.append(health_record)
        if len(self._health_history) > 1000:
            self._health_history = self._health_history[-1000:]
        
        if health == SystemHealth.CRITICAL:
            self._create_alert('critical', '系统健康状态严重', f'发现 {health.value} 状态')
        elif health == SystemHealth.WARNING:
            log.warning(f"刘邦：系统健康状态警告 [{health.value}]")
    
    def _update_system_metrics(self):
        """更新系统指标"""
        try:
            from deva.naja.strategy import get_strategy_manager
            strategy_mgr = get_strategy_manager()
            # 使用list_all()方法获取策略列表
            all_strategies = strategy_mgr.list_all()
            self._system_metrics.total_strategies = len(all_strategies)
            # 计算活跃策略数量
            active_count = 0
            for strategy in all_strategies:
                if hasattr(strategy, '_state') and strategy._state == 'running':
                    active_count += 1
            self._system_metrics.active_strategies = active_count
            
            if '韩信' in self._agents:
                hanxin = self._agents['韩信']
                if hasattr(hanxin, 'get_trade_history'):
                    self._system_metrics.total_trades = len(hanxin.get_trade_history())
            
            if '萧何' in self._agents:
                xiaohe = self._agents['萧何']
                if hasattr(xiaohe, 'get_capital_info'):
                    capital_info = xiaohe.get_capital_info()
                    self._system_metrics.total_capital = capital_info.get('total_capital', 0)
                    self._system_metrics.available_capital = capital_info.get('available_capital', 0)
            
            self._system_metrics.last_update_ts = time.time()
            
        except Exception as e:
            log.error(f"刘邦：更新系统指标失败：{e}")
    
    def get_replay_datasource(self, interval: float = 1.0):
        """获取行情回放数据源
        
        Args:
            interval: 回放间隔（秒）
            
        Returns:
            成功返回数据源对象，失败返回None
        """
        try:
            from deva.naja.datasource import get_datasource_manager
            
            ds_mgr = get_datasource_manager()
            
            # 确保数据源已从数据库加载
            ds_mgr.load_from_db()
            
            # 查找行情回放数据源
            replay_ds = None
            for ds in ds_mgr.list_all():
                ds_name = getattr(ds, "name", "")
                if "回放" in ds_name or "replay" in ds_name.lower():
                    replay_ds = ds
                    break
            
            if not replay_ds:
                log.warning(f"刘邦：未找到行情回放数据源")
                return None
            
            # 发送消息通知萧何订阅数据源
            self.send_message({
                'type': 'subscribe_data_source',
                'to': '萧何',
                'data_source_id': replay_ds.id,
                'data_source_name': replay_ds.name,
                'message': f'请订阅行情回放数据源 [{replay_ds.name}]'
            })
            log.info(f"刘邦：已通知萧何订阅行情回放数据源 [{replay_ds.name}]")
            
            # 设置回放间隔
            if hasattr(replay_ds, '_metadata') and hasattr(replay_ds._metadata, 'config'):
                if not replay_ds._metadata.config:
                    replay_ds._metadata.config = {}
                replay_ds._metadata.config['interval'] = interval
                log.info(f"刘邦：已设置数据源 [{replay_ds.name}] 回放间隔为 {interval} 秒")
            
            log.info(f"刘邦：正在启动数据源 [{replay_ds.name}]...")
            start_result = replay_ds.start()
            
            if start_result.get('success'):
                log.info(f"刘邦：数据源 [{replay_ds.name}] 启动成功")
                
                self.replay_ds = replay_ds
                return replay_ds
            else:
                log.error(f"刘邦：数据源 [{replay_ds.name}] 启动失败：{start_result.get('error', '')}")
                return None
        except Exception as e:
            log.error(f"刘邦：启动行情回放数据源失败：{e}")
            return None
    
    
    
    
    
    def _stop_replay_datasource(self):
        """停止行情回放数据源"""
        if hasattr(self, 'replay_ds') and self.replay_ds:
            stop_result = self.replay_ds.stop()
            if stop_result.get('success'):
                log.info(f"刘邦：数据源 [{self.replay_ds.name}] 停止成功")
            else:
                log.error(f"刘邦：数据源 [{self.replay_ds.name}] 停止失败：{stop_result.get('error', '')}")
        else:
            log.warning("刘邦：未找到行情回放数据源，无法停止")
    
    
    def _check_pnl_and_scold_zhangliang(self):
        """检查盈亏情况，如果亏损就责骂张良并退出程序"""
        try:
            # 检查萧何的持仓情况
            xiaohe = None
            if '萧何' in self._agents:
                xiaohe = self._agents['萧何']
            else:
                # 尝试从agent manager获取萧何
                try:
                    from deva.naja.agent.manager import get_agent_manager
                    manager = get_agent_manager()
                    xiaohe = manager.get_agent('萧何')
                except Exception as e:
                    log.error(f"刘邦：获取萧何智能体失败：{e}")
            
            if xiaohe:
                # 计算总盈亏
                positions = xiaohe.get_all_positions()
                total_pnl = 0
                for position in positions:
                    total_pnl += (position.current_price - position.avg_price) * position.amount
                
                log.info(f"刘邦：当前总盈亏：{total_pnl:.2f}")
                
                # 如果亏损，责骂张良并退出程序
                if total_pnl < 0:
                    log.error(f"刘邦：交易亏损 {total_pnl:.2f}，责骂张良！")
                    
                    # 通知张良
                    self.send_message({
                        'type': 'scold',
                        'to': '张良',
                        'message': f'张良，你制定的策略导致亏损 {total_pnl:.2f}，必须改进！'
                    })
                    
                    # 退出程序
                    log.error("刘邦：交易亏损，程序退出")
                    import sys
                    sys.exit(1)
                else:
                    log.info("刘邦：交易盈利，继续运行")
            else:
                log.error("刘邦：未找到萧何智能体，无法检查盈亏情况")
        except Exception as e:
            log.error(f"刘邦：检查盈亏情况失败：{e}")
    
    def _handle_agent_message(self, message: Dict[str, Any]):
        """处理智能体消息"""
        msg_type = message.get('type')
        
        if msg_type == 'error':
            agent_name = message.get('from')
            error = message.get('error')
            self._create_alert('error', f'智能体 {agent_name} 错误', error)
    
    def _start_agent(self, agent_name):
        """启动指定智能体"""
        try:
            from deva.naja.agent.manager import get_agent_manager
            from deva.naja.agent.hanxin import HanXinAgent
            from deva.naja.agent.xiaohe import XiaoHeAgent
            from deva.naja.agent.zhangliang import ZhangLiangAgent
            
            manager = get_agent_manager()
            agent = manager.get_agent(agent_name)
            
            if agent:
                if agent.state.state != AgentState.RUNNING:
                    agent.start()
                    log.info(f"刘邦：已启动 {agent_name} 智能体")
                else:
                    log.info(f"刘邦：{agent_name} 智能体已在运行中")
            else:
                # 自动创建和注册智能体
                log.info(f"刘邦：未找到 {agent_name} 智能体，正在自动创建...")
                if agent_name == '韩信':
                    agent = HanXinAgent()
                elif agent_name == '萧何':
                    agent = XiaoHeAgent()
                elif agent_name == '张良':
                    agent = ZhangLiangAgent()
                else:
                    log.warning(f"刘邦：不支持的智能体名称：{agent_name}")
                    return
                
                # 注册智能体
                manager.register_agent(agent)
                log.info(f"刘邦：已创建并注册 {agent_name} 智能体")
                
                # 启动智能体
                agent.start()
                log.info(f"刘邦：已启动 {agent_name} 智能体")
                
        except Exception as e:
            log.error(f"刘邦：启动 {agent_name} 智能体失败：{e}")

    

    def _create_alert(self, level: str, title: str, message: str):
        """创建告警"""
        alert = {
            'level': level,
            'title': title,
            'message': message,
            'timestamp': time.time(),
            'acknowledged': False
        }
        
        self._alerts.append(alert)
        
        if len(self._alerts) > 100:
            self._alerts = self._alerts[-100:]
        
        log.warning(f"刘邦：告警 [{level}] {title}: {message}")
