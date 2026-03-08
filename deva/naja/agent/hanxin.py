"""韩信智能体 - 策略执行和交易员

负责启动策略实验室，分析信号流里的数据，找到买入信号并买入。
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass, field

from deva import NB, Stream, bus, when, timer
import logging

# 使用标准日志
log = logging.getLogger(__name__)
from deva.naja.agent.base import BaseAgent, AgentMetadata, AgentRole, AgentState
from deva.naja.strategy import get_strategy_manager, StrategyEntry
from deva.naja.signal.stream import SignalStream, get_signal_stream
from deva.naja.strategy.result_store import StrategyResult


@dataclass
class BuySignal:
    """买入信号"""
    strategy_name: str
    signal_time: float
    signal_data: Dict[str, Any]
    confidence: float = 0.0
    reason: str = ""


@dataclass
class Trade:
    """交易记录"""
    trade_id: str
    strategy_name: str
    action: str  # buy, sell
    timestamp: float
    price: float = 0.0
    amount: float = 0.0
    reason: str = ""


class HanXinAgent(BaseAgent):
    """韩信智能体
    
    职责:
    1. 启动策略实验室
    2. 分析信号流里的数据
    3. 找到买入信号并执行买入
    4. 管理交易执行
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        metadata = AgentMetadata(
            name="韩信",
            role=AgentRole.TRADER,
            description="交易员 - 负责启动策略实验室，分析信号并执行买入",
            config=config or {}
        )
        super().__init__(metadata, config)
        
        self._signal_stream: Optional[SignalStream] = None
        self._active_strategies: Dict[str, StrategyEntry] = {}
        self._strategy_logics: Dict[str, Dict[str, Any]] = {}
        self._pending_signals: List[BuySignal] = []
        self._trade_history: List[Trade] = []
        self._zhangliang_agent: Optional[str] = None
        self._xiaohe_agent: Optional[str] = None
        
        self._signal_analysis_interval = self._config.get('signal_analysis_interval', 5)
        self._auto_trade_enabled = self._config.get('auto_trade_enabled', True)
        
        # 行情回放数据源启动标志
        self._replay_datasource_started = False
        
        # 市场状态
        self._market_state = None
    
    def set_zhangliang_agent(self, agent_name: str):
        """设置张良智能体的名称"""
        self._zhangliang_agent = agent_name
        log.info(f"韩信 -> 已绑定张良智能体：{agent_name}")
    
    def set_xiaohe_agent(self, agent_name: str):
        """设置萧何智能体的名称"""
        self._xiaohe_agent = agent_name
        log.info(f"韩信 -> 已绑定萧何智能体：{agent_name}")

    

    
    def execute_buy(
        self,
        buy_signal: BuySignal,
        amount: float = 0.0,
        price: float = 0.0
    ) -> Optional[Trade]:
        """执行买入操作
        
        Args:
            buy_signal: 买入信号
            amount: 买入数量
            price: 买入价格
            
        Returns:
            Trade: 交易记录
        """
        try:
            if not self._xiaohe_agent:
                log.warning("韩信：未绑定萧何智能体，无法进行风控检查")
            
            # 从 river 信号中提取价格和代码
            signal_data = buy_signal.signal_data
            stock_code = signal_data.get('code', '')
            stock_name = signal_data.get('name', '')
            
            # 如果没有提供价格，尝试从信号数据中获取
            if price <= 0:
                price = signal_data.get('price', 0.0)
                # 尝试从其他可能的字段获取价格
                if price <= 0:
                    price = signal_data.get('close', 0.0) or signal_data.get('current', 0.0) or signal_data.get('last', 0.0)
            
            if self._xiaohe_agent:
                risk_check = self._request_risk_check(buy_signal)
                if not risk_check.get('approved', False):
                    log.warning(f"韩信：风控未通过，取消买入 [{buy_signal.strategy_name}] - {stock_name}({stock_code})")
                    return None
            
            trade_id = f"BUY_{int(time.time() * 1000)}"
            
            trade = Trade(
                trade_id=trade_id,
                strategy_name=buy_signal.strategy_name,
                action='buy',
                timestamp=time.time(),
                price=price,
                amount=amount,
                reason=buy_signal.reason
            )
            
            self._trade_history.append(trade)
            
            # 发送 trade_executed 消息通知萧何添加持仓
            try:
                self.send_message({
                    'type': 'trade_executed',
                    'to': '萧何',
                    'trade': {
                        'action': 'buy',
                        'strategy_name': buy_signal.strategy_name,
                        'amount': amount,
                        'price': price,
                        'stock_code': stock_code,
                        'stock_name': stock_name,
                        'timestamp': time.time()
                    }
                })
                log.info(f"韩信：已发送交易执行消息给萧何")
            except Exception as msg_error:
                log.error(f"韩信：发送交易执行消息失败：{msg_error}")
            
            self._increment_metric('trades_executed')
            
            # 实时汇报交易情况
            log.info(f"\033[94m韩信：买入 {stock_name}({stock_code})，数量 {amount}，价格 {price:.2f}，金额 {price * amount:.2f}\033[0m")
            log.info(f"\033[94m  └─ 策略：{buy_signal.strategy_name}，置信度 {buy_signal.confidence:.2f}\033[0m")
            
            # 通知其他智能体交易执行情况
            try:
                self.send_message({
                    'type': 'trade_executed',
                    'trade': {
                        'trade_id': trade_id,
                        'strategy_name': buy_signal.strategy_name,
                        'action': trade.action,
                        'price': price,
                        'amount': amount,
                        'stock_code': stock_code,
                        'stock_name': stock_name,
                        'timestamp': trade.timestamp
                    }
                })
            except Exception as msg_error:
                log.error(f"韩信：发送交易通知消息失败：{msg_error}")
            
            return trade
            
        except Exception as e:
            log.error(f"韩信：执行买入操作出错：{e}")
            # 不将错误传播，避免智能体进入错误状态
            return None
    
    def auto_trade_loop(self):
        """自动交易循环"""
        try:
            if not self._auto_trade_enabled:
                return
            
            # 检查市场状态是否已获取
            if self._market_state is None:
                return
            
            # 高波动市场：不交易
            if self._market_state == '高波动市场':
                log.info(f"\033[94m韩信：高波动市场 - 不执行交易\033[0m")
                # 清空待处理信号，避免在市场状态变化后重复处理
                self._pending_signals.clear()
                return
            
            # 处理待处理的买入信号
            if not self._pending_signals:
                return
            
            log.info(f"\033[94m韩信：开始处理 {len(self._pending_signals)} 个买入信号...\033[0m")
            
            # 处理所有待处理的信号
            for i, signal in enumerate(self._pending_signals, 1):
                # 汇报当前处理进度
                log.info(f"\033[94m韩信：处理第 {i}/{len(self._pending_signals)} 个信号...\033[0m")
                
                # 对于 river 策略的信号，设置合理的买入数量
                signal_data = signal.signal_data
                
                # 确保 signal_data 是字典
                if not isinstance(signal_data, dict):
                    log.warning(f"韩信：信号数据格式错误，不是字典类型: {type(signal_data)}")
                    continue
                    
                stock_code = signal_data.get('code', '')
                stock_name = signal_data.get('name', '')
                confidence = signal.confidence
                
                # 根据市场状态和置信度设置买入金额
                base_amount = 10000  # 基础买入金额
                
                # 根据市场状态调整买入金额
                if self._market_state == '趋势市场':
                    # 趋势市场加大交易
                    market_multiplier = 1.5
                elif self._market_state == '高波动市场':
                    # 高波动市场减少交易
                    market_multiplier = 0.5
                else:  # 震荡市场
                    # 震荡市场正常交易
                    market_multiplier = 1.0
                
                buy_amount = base_amount * confidence * market_multiplier
                
                # 从信号中获取价格，尝试多个可能的字段
                price = 0.0
                price_fields = ['price', 'current', 'now', 'last', 'close', 'open', 'high', 'low']
                for field in price_fields:
                    if field in signal_data:
                        try:
                            p = float(signal_data[field])
                            if p > 0:
                                price = p
                                break
                        except Exception:
                            pass
                
                # 如果仍然没有价格，跳过该信号
                if price <= 0:
                    log.warning(f"韩信：信号中缺少价格信息，跳过买入 - {stock_name}({stock_code})")
                    continue
                
                # 检查是否已经持有该股票
                from deva.naja.agent.manager import get_agent_manager
                manager = get_agent_manager()
                xiaohe = manager.get_agent('萧何')
                already_holding = False
                if xiaohe:
                    positions = xiaohe.get_all_positions()
                    for position in positions:
                        if position.stock_code == stock_code:
                            already_holding = True
                            log.info(f"\033[94m韩信：股票 {stock_name}({stock_code}) 已经在持仓中，跳过买入\033[0m")
                            break
                
                if not already_holding:
                    # 计算买入数量（股）
                    shares = int(buy_amount / price)
                    if shares > 0:
                        # 明确的交易日志提醒
                        if self._market_state == '震荡市场':
                            log.info(f"\033[94m韩信：震荡市场正常交易 - 检测到买入信号 - 置信度={confidence:.2f} 股票={stock_name}({stock_code}) 价格={price} 计划买入={shares}股\033[0m")
                        elif self._market_state == '趋势市场':
                            log.info(f"\033[94m韩信：趋势市场加大交易 - 检测到买入信号 - 置信度={confidence:.2f} 股票={stock_name}({stock_code}) 价格={price} 计划买入={shares}股\033[0m")
                        elif self._market_state == '高波动市场':
                            log.info(f"\033[94m韩信：高波动市场减少交易 - 检测到买入信号 - 置信度={confidence:.2f} 股票={stock_name}({stock_code}) 价格={price} 计划买入={shares}股\033[0m")
                        self.execute_buy(signal, amount=shares, price=price)
            
            # 清空待处理信号列表
            self._pending_signals.clear()
            
            log.info(f"\033[94m韩信：信号处理完成\033[0m")
        except Exception as e:
            log.error(f"韩信：自动交易循环出错：{e}")
            # 不将错误传播，避免智能体进入错误状态
    
    def get_trade_history(self, strategy_name: Optional[str] = None) -> List[Trade]:
        """获取交易历史"""
        if strategy_name:
            return [t for t in self._trade_history if t.strategy_name == strategy_name]
        return self._trade_history
    
    def get_active_strategies(self) -> List[str]:
        """获取活跃策略列表"""
        return list(self._active_strategies.keys())
    
    def _do_initialize(self):
        """初始化"""
        log.info("韩信智能体初始化中...")
        # self._signal_stream = get_signal_stream()
    
    def process_signal(self, signal):
        """处理信号流中的新信号"""
        if self._state.state != AgentState.RUNNING:
            return
        
        try:
            # 首先检查信号是否有效
            if not isinstance(signal, StrategyResult) or not signal.success:
                return
            
            # 处理市场状态信号
            if '市场' in signal.strategy_name:
                self._update_market_state(signal)
                return
            
            # 检查市场状态是否已获取
            if self._market_state is None:
                # 市场状态未获取，不解读其他信号
                return
            
            # 根据市场状态决定交易策略
            market_state = self._market_state
            
            # 分析当前信号
            buy_signal = self._extract_buy_signal(signal)
            if buy_signal:
                # 根据市场状态决定交易策略
                if market_state == '震荡市场':
                    # 震荡市场：谨慎交易，只接受高置信度信号
                    if buy_signal.confidence >= 0.7:
                        self._pending_signals.append(buy_signal)
                        log.info(f"\033[94m韩信：震荡市场谨慎交易 - 接受高置信度信号 (置信度: {buy_signal.confidence:.2f})\033[0m")
                    else:
                        log.info(f"\033[94m韩信：震荡市场谨慎交易 - 忽略低置信度信号 (置信度: {buy_signal.confidence:.2f})\033[0m")
                elif market_state == '高波动市场':
                    # 高波动市场：不交易
                    log.info(f"\033[94m韩信：高波动市场 - 不交易，忽略信号 (置信度: {buy_signal.confidence:.2f})\033[0m")
                else:  # 趋势市场
                    # 趋势市场：正常交易
                    self._pending_signals.append(buy_signal)
                    log.info(f"\033[94m韩信：趋势市场正常交易 - 接受信号 (置信度: {buy_signal.confidence:.2f})\033[0m")
                
                if market_state != '高波动市场':
                    log.info(f"\033[94m韩信：发现 1 个买入信号\033[0m")
                    self._update_metrics('pending_signals', len(self._pending_signals))
            
            # 执行自动交易循环
            self.auto_trade_loop()
        except Exception as e:
            log.error(f"韩信：处理信号时出错：{e}")
            # 不将错误传播，避免智能体进入错误状态

    def _do_start(self):
        """启动"""
        log.info("\033[91m韩信智能体启动\033[0m")
        
        # 绑定萧何智能体
        from deva.naja.agent.manager import get_agent_manager
        manager = get_agent_manager()
        xiaohe = manager.get_agent('萧何')
        if xiaohe:
            self._xiaohe_agent = xiaohe
            log.info("\033[91m韩信：已绑定萧何智能体\033[0m")
        else:
            log.warning("\033[91m韩信：未找到萧何智能体，将使用默认风控逻辑\033[0m")
        
        # 订阅信号流，使用 sink 方式处理信号
        if not self._signal_stream:
            self._signal_stream = get_signal_stream()
            log.info("\033[91m韩信：已获取信号流实例\033[0m")
        
        # 将处理函数 sink 到信号流
        self._signal_stream.sink(self.process_signal)
        log.info("\033[91m韩信：已订阅信号流，将自动分析新信号\033[0m")
        log.info("\033[91m韩信：启动完成，等待信号...\033[0m")
    
    def _do_stop(self):
        """停止"""
        log.info("韩信智能体停止")
    
    def _do_pause(self):
        """暂停"""
        log.info("韩信智能体暂停")
    
    def _do_resume(self):
        """恢复"""
        log.info("韩信智能体恢复")
    
    def _handle_message(self, message: Dict[str, Any]):
        """处理消息"""
        msg_type = message.get('type')
        
        if msg_type == 'strategy_logic_notification':
            strategy_name = message.get('strategy_name')
            logic = message.get('logic', {})
            
            self._strategy_logics[strategy_name] = logic
            log.info(f"韩信：收到策略 [{strategy_name}] 逻辑：{logic.get('description', '')}")
        
        elif msg_type == 'start_strategy_request':
            strategy_name = message.get('strategy_name')
            if strategy_name:
                # 策略启动由刘邦负责
                log.info(f"韩信：策略 [{strategy_name}] 启动请求已收到，由刘邦负责启动")
                self.send_message({
                    'type': 'strategy_started_response',
                    'to': message.get('from'),
                    'strategy_name': strategy_name,
                    'success': True
                })
        
        elif msg_type == 'query_trades':
            trades = self.get_trade_history()
            self.send_message({
                'type': 'trades_response',
                'to': message.get('from'),
                'trades': [
                    {
                        'trade_id': t.trade_id,
                        'strategy_name': t.strategy_name,
                        'action': t.action,
                        'timestamp': t.timestamp,
                        'price': t.price,
                        'amount': t.amount
                    }
                    for t in trades
                ]
            })
        
        elif msg_type == 'issue_assigned':
            # 处理刘邦分发的问题
            issue_id = message.get('issue_id')
            issue_type = message.get('issue_type')
            description = message.get('description')
            
            log.info(f"韩信：收到分配的问题 [{issue_id}]: {description}")
            
            # 处理交易执行问题
            if issue_type == 'trade':
                # 这里可以添加具体的问题处理逻辑
                log.info(f"韩信：处理交易执行问题 [{issue_id}]")
                
                # 发送处理结果
                self.send_message({
                    'type': 'issue_handled',
                    'to': '刘邦',
                    'issue_id': issue_id,
                    'status': 'resolved',
                    'message': f'交易执行问题已处理：{description}',
                    'handled_by': '韩信',
                    'timestamp': time.time()
                })
            else:
                log.warning(f"韩信：收到非交易类型的问题 [{issue_id}]: {issue_type}")
    

    

    
    def _update_market_state(self, signal: StrategyResult):
        """从市场气候聚类信号中更新市场状态"""
        if not signal.output_full:
            return
        
        output = signal.output_full
        if isinstance(output, dict):
            # 处理市场气候聚类信号
            if output.get('signal') == 'market_climate_cluster':
                dominant_cluster = output.get('dominant_cluster')
                dominant_name = output.get('dominant_name', '')
                
                # 根据聚类结果更新市场状态
                if dominant_cluster == 0:
                    new_state = '震荡市场'
                elif dominant_cluster == 1:
                    new_state = '趋势市场'
                elif dominant_cluster == 2:
                    new_state = '高波动市场'
                else:
                    new_state = None
                
                if new_state and new_state != self._market_state:
                    self._market_state = new_state
                    # 使用红色报警字体输出市场状态判断
                    log.info(f"\033[91m韩信：市场类型判断 - 市场状态更新为：{new_state}（{dominant_name}）\033[0m")
                    
                    # 使用红色报警字体输出交易结论
                    if new_state == '震荡市场':
                        log.info(f"\033[91m韩信：交易结论 - 震荡市场，谨慎交易，只接受高置信度信号\033[0m")
                    elif new_state == '高波动市场':
                        log.info(f"\033[91m韩信：交易结论 - 高波动市场，尽量不交易\033[0m")
                    elif new_state == '趋势市场':
                        log.info(f"\033[91m韩信：交易结论 - 趋势市场，正常交易\033[0m")

    def _extract_buy_signal(self, result: StrategyResult) -> Optional[BuySignal]:
        """从策略结果中提取买入信号"""
        if not result.output_full:
            return None
        
        output = result.output_full
        
        buy_signal = None
        confidence = 0.0
        reason = ""
        
        if isinstance(output, dict):
            # 处理 river 策略的信号格式
            if 'picks' in output:
                picks = output['picks']
                if picks and len(picks) > 0:
                    # 取第一个作为买入信号
                    top_pick = picks[0]
                    buy_signal = top_pick
                    
                    # 根据 river 策略的不同类型计算置信度
                    signal_type = output.get('signal', '')
                    
                    # 检测趋势分析信号并红色打印报警
                    if signal_type == 'trend_analysis':
                        log.info(f"\033[91m韩信：报警 - 检测到趋势分析信号！\033[0m")
                        
                    if 'probability' in signal_type:
                        # 概率类策略
                        confidence = top_pick.get('up_probability', 0.0) or top_pick.get('order_flow_up_probability', 0.0)
                    elif 'anomaly' in signal_type:
                        # 异常类策略
                        confidence = min(1.0, (top_pick.get('anomaly_score', 0.0) or 0.0) / 10.0)
                    elif 'behavior' in signal_type:
                        # 行为类策略
                        confidence = 0.7  # 固定置信度
                    else:
                        # 其他类型策略，尝试从 pick 中获取置信度相关字段
                        confidence = top_pick.get('up_probability', 0.0) or top_pick.get('order_flow_up_probability', 0.0) or top_pick.get('anomaly_score', 0.0) or 0.6
                    
                    reason = f"River 策略 [{signal_type}] 推荐：{top_pick.get('name', '')}({top_pick.get('code', '')})"
            
            # 处理传统信号格式
            elif 'signals' in output:
                signals = output['signals']
                if signals and len(signals) > 0:
                    # 检查是否有趋势分析信号
                    if output.get('signal_type') == 'trend_analysis' or output.get('signal') == 'trend_analysis':
                        log.info(f"\033[91m韩信：报警 - 检测到趋势分析信号！\033[0m")
                    buy_signal = signals[0]
                    confidence = self._calculate_signal_confidence(output)
                    reason = f"策略信号：{result.strategy_name}"
            
            # 处理包含 raw_picks 的信号格式
            elif 'raw_picks' in output:
                raw_picks = output['raw_picks']
                if raw_picks and len(raw_picks) > 0:
                    # 检查是否有趋势分析信号
                    if output.get('signal_type') == 'trend_analysis' or output.get('signal') == 'trend_analysis':
                        log.info(f"\033[91m韩信：报警 - 检测到趋势分析信号！\033[0m")
                    # 取第一个作为买入信号
                    top_pick = raw_picks[0]
                    buy_signal = top_pick
                    confidence = 0.6  # 默认置信度
                    reason = f"策略 [{result.strategy_name}] 推荐：{top_pick.get('name', '')}({top_pick.get('code', '')})"
            
            elif 'buy' in output or '买入' in str(output):
                # 检查是否有趋势分析信号
                if output.get('signal_type') == 'trend_analysis' or output.get('signal') == 'trend_analysis':
                    log.info(f"\033[91m韩信：报警 - 检测到趋势分析信号！\033[0m")
                buy_signal = output
                confidence = 0.7
                reason = "检测到买入关键词"
        
        if buy_signal:
            return BuySignal(
                strategy_name=result.strategy_name,
                signal_time=result.ts,
                signal_data=buy_signal,
                confidence=confidence,
                reason=reason
            )
        
        return None
    
    def _calculate_signal_confidence(self, output: Dict[str, Any]) -> float:
        """计算信号置信度"""
        confidence = 0.5
        
        if isinstance(output, dict):
            signals = output.get('signals', [])
            if len(signals) >= 3:
                confidence += 0.2
            if len(signals) >= 5:
                confidence += 0.1
            
            if output.get('market_strength', 0) > 70:
                confidence += 0.1
        
        return min(confidence, 1.0)
    
    def _request_risk_check(self, buy_signal: BuySignal) -> Dict[str, Any]:
        """向萧何请求风控检查"""
        if not self._xiaohe_agent:
            return {'approved': True}
        
        try:
            # 直接从 agent manager 获取萧何智能体并调用风控检查
            from deva.naja.agent.manager import get_agent_manager
            manager = get_agent_manager()
            xiaohe = manager.get_agent('萧何')
            
            if xiaohe:
                # 调用萧何的风控检查方法
                signal_data = buy_signal.signal_data.copy() if isinstance(buy_signal.signal_data, dict) else {}
                signal_data['confidence'] = buy_signal.confidence
                signal_data['strategy_name'] = buy_signal.strategy_name
                
                result = xiaohe.check_risk(signal_data)
                
                log.info(f"韩信：萧何风控检查 - 结果={'通过' if result.approved else '拒绝'} 原因={result.reason} 风险等级={result.risk_level.value}")
                
                # 如果风控未通过，通知刘邦
                if not result.approved:
                    # 从signal_data中获取股票信息
                    stock_name = signal_data.get('name', '')
                    stock_code = signal_data.get('code', '')
                    
                    self.send_message({
                        'type': 'trade_failed',
                        'to': '刘邦',
                        'reason': result.reason,
                        'stock_name': stock_name,
                        'stock_code': stock_code,
                        'strategy_name': buy_signal.strategy_name,
                        'message': f'无法执行交易：{result.reason}'
                    })
                
                return {
                    'approved': result.approved,
                    'reason': result.reason,
                    'risk_level': result.risk_level.value,
                    'suggested_amount': result.suggested_amount
                }
            else:
                log.warning("韩信：未找到萧何智能体，跳过风控检查")
                return {'approved': True}
        except Exception as e:
            log.error(f"韩信：风控检查失败：{e}")
            return {'approved': True}  # 风控失败时默认允许交易
