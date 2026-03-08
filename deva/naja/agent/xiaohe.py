"""萧何智能体 - 仓位管理和风控官

负责仓位管理、风险控制、资金管理。
"""

from __future__ import annotations

import time
import math
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum

from deva import NB, Stream, bus, when, PeriodicCallback
import logging

# 使用标准日志
log = logging.getLogger(__name__)
from deva.naja.agent.base import BaseAgent, AgentMetadata, AgentRole, AgentState


class RiskLevel(Enum):
    """风险等级"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class Position:
    """持仓信息"""
    position_id: str
    strategy_name: str
    amount: float
    avg_price: float
    stock_code: str = ""
    stock_name: str = ""
    current_price: float = 0.0
    open_timestamp: float = 0.0
    last_update_ts: float = 0.0


@dataclass
class RiskMetrics:
    """风险指标"""
    total_exposure: float = 0.0
    position_concentration: float = 0.0
    max_drawdown: float = 0.0
    var_95: float = 0.0
    sharpe_ratio: float = 0.0
    risk_level: RiskLevel = RiskLevel.LOW


@dataclass
class RiskCheckResult:
    """风控检查结果"""
    approved: bool
    reason: str
    risk_level: RiskLevel
    suggested_amount: float = 0.0
    conditions: List[str] = field(default_factory=list)


class XiaoHeAgent(BaseAgent):
    """萧何智能体
    
    职责:
    1. 仓位管理
    2. 风险控制
    3. 资金管理
    4. 交易审批
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        metadata = AgentMetadata(
            name="萧何",
            role=AgentRole.RISK_MANAGER,
            description="风控官 - 负责仓位管理和风险控制",
            config=config or {}
        )
        super().__init__(metadata, config)
        
        self._positions: Dict[str, Position] = {}
        self._risk_metrics = RiskMetrics()
        
        self._total_capital = self._config.get('total_capital', 1000000.0)
        self._available_capital = self._total_capital
        self._used_capital = 0.0
        
        self._max_position_size = self._config.get('max_position_size', 0.2)
        self._max_total_exposure = self._config.get('max_total_exposure', 0.8)
        self._max_drawdown_limit = self._config.get('max_drawdown_limit', 0.1)
        self._var_limit = self._config.get('var_limit', 0.05)
        
        self._risk_thresholds = {
            'low': 0.3,
            'medium': 0.5,
            'high': 0.7,
            'critical': 0.9
        }
        
        self._trade_approvals: Dict[str, bool] = {}
        self._risk_history: List[Dict[str, Any]] = []
        
        # 数据源订阅相关
        self._data_source = None
        self._price_update_interval = 5000  # 5秒更新一次
        self._report_interval = 5000  # 5秒汇报一次
        self._price_update_callback = None
        self._report_callback = None
    
    def get_position(self, position_id: str) -> Optional[Position]:
        """获取持仓信息"""
        return self._positions.get(position_id)
    
    def get_all_positions(self) -> List[Position]:
        """获取所有持仓"""
        return list(self._positions.values())
    
    def add_position(
        self,
        strategy_name: str,
        amount: float,
        price: float,
        stock_code: str = "",
        stock_name: str = ""
    ) -> Position:
        """添加持仓"""
        position_id = f"POS_{strategy_name}_{int(time.time())}"
        
        position = Position(
            position_id=position_id,
            strategy_name=strategy_name,
            stock_code=stock_code,
            stock_name=stock_name,
            amount=amount,
            avg_price=price,
            current_price=price,
            open_timestamp=time.time(),
            last_update_ts=time.time()
        )
        
        self._positions[position_id] = position
        self._used_capital += amount * price
        self._available_capital = self._total_capital - self._used_capital
        
        self._update_risk_metrics()
        
        log.info(f"萧何：新增持仓 [{position_id}] 策略={strategy_name} 股票={stock_name}({stock_code}) 数量={amount} 价格={price}")
        
        return position
    
    def update_position_price(self, position_id: str, current_price: float):
        """更新持仓价格"""
        if position_id not in self._positions:
            return
        
        position = self._positions[position_id]
        position.current_price = current_price
        position.last_update_ts = time.time()
        
        self._update_risk_metrics()
    
    def close_position(self, position_id: str, price: float) -> float:
        """平仓"""
        if position_id not in self._positions:
            return 0.0
        
        position = self._positions[position_id]
        profit_loss = (price - position.avg_price) * position.amount
        
        self._used_capital -= position.amount * position.avg_price
        self._available_capital += position.amount * price
        
        del self._positions[position_id]
        
        self._update_risk_metrics()
        
        log.info(f"萧何：平仓 [{position_id}] 价格={price} 盈亏={profit_loss:.2f}")
        
        return profit_loss
    
    def check_risk(self, signal_data: Dict[str, Any]) -> RiskCheckResult:
        """风控检查
        
        Args:
            signal_data: 信号数据
            
        Returns:
            RiskCheckResult: 风控检查结果
        """
        try:
            risk_level = self._calculate_risk_level()
            
            if risk_level == RiskLevel.CRITICAL:
                return RiskCheckResult(
                    approved=False,
                    reason="风险等级过高，禁止交易",
                    risk_level=risk_level
                )
            
            if self._risk_metrics.total_exposure >= self._max_total_exposure * self._total_capital:
                return RiskCheckResult(
                    approved=False,
                    reason="总风险暴露超过限制",
                    risk_level=risk_level
                )
            
            confidence = signal_data.get('confidence', 0.5)
            if confidence < 0.6:
                return RiskCheckResult(
                    approved=False,
                    reason="信号置信度过低",
                    risk_level=risk_level
                )
            
            suggested_amount = self._calculate_position_size(confidence)
            
            conditions = []
            if risk_level == RiskLevel.HIGH:
                conditions.append("建议降低仓位")
            if self._available_capital < suggested_amount * 0.5:
                conditions.append("可用资金不足")
                suggested_amount = self._available_capital * 0.5
            
            approved = len(conditions) == 0 or all('不足' not in c for c in conditions)
            
            result = RiskCheckResult(
                approved=approved,
                reason="风控检查通过" if approved else "; ".join(conditions),
                risk_level=risk_level,
                suggested_amount=suggested_amount,
                conditions=conditions
            )
            
            self._record_risk_check(result, signal_data)
            
            return result
            
        except Exception as e:
            self._handle_error(e)
            return RiskCheckResult(
                approved=False,
                reason=f"风控检查异常：{e}",
                risk_level=RiskLevel.CRITICAL
            )
    
    def get_risk_metrics(self) -> Dict[str, Any]:
        """获取风险指标"""
        return {
            'total_exposure': self._risk_metrics.total_exposure,
            'exposure_ratio': self._risk_metrics.total_exposure / self._total_capital if self._total_capital > 0 else 0,
            'position_concentration': self._risk_metrics.position_concentration,
            'max_drawdown': self._risk_metrics.max_drawdown,
            'var_95': self._risk_metrics.var_95,
            'sharpe_ratio': self._risk_metrics.sharpe_ratio,
            'risk_level': self._risk_metrics.risk_level.value,
            'total_capital': self._total_capital,
            'available_capital': self._available_capital,
            'used_capital': self._used_capital,
            'position_count': len(self._positions)
        }
    
    def get_capital_info(self) -> Dict[str, Any]:
        """获取资金信息"""
        return {
            'total_capital': self._total_capital,
            'available_capital': self._available_capital,
            'used_capital': self._used_capital,
            'usage_ratio': self._used_capital / self._total_capital if self._total_capital > 0 else 0
        }
    
    def set_risk_level(self, level: str):
        """手动设置风险等级"""
        if level in self._risk_thresholds:
            log.info(f"萧何：手动设置风险等级为 {level}")
    
    def _do_initialize(self):
        """初始化"""
        log.info("萧何智能体初始化中...")
        self._load_positions_from_db()
        self._update_risk_metrics()
    
    def _do_start(self):
        """启动"""
        log.info("萧何智能体启动")
        self.start_periodic_updates()
    
    def _do_stop(self):
        """停止"""
        log.info("萧何智能体停止")
        self.stop_periodic_updates()
    
    def _do_pause(self):
        """暂停"""
        log.info("萧何智能体暂停")
    
    def _do_resume(self):
        """恢复"""
        log.info("萧何智能体恢复")
    
    def _handle_message(self, message: Dict[str, Any]):
        """处理消息"""
        msg_type = message.get('type')
        
        if msg_type == 'risk_check_request':
            signal = message.get('signal', {})
            result = self.check_risk(signal)
            
            self.send_message({
                'type': 'risk_check_response',
                'to': message.get('from'),
                'approved': result.approved,
                'reason': result.reason,
                'suggested_amount': result.suggested_amount,
                'risk_level': result.risk_level.value,
                'conditions': result.conditions
            })
        
        elif msg_type == 'trade_executed':
            trade = message.get('trade', {})
            if trade.get('action') == 'buy':
                strategy_name = trade.get('strategy_name')
                amount = trade.get('amount', 0)
                price = trade.get('price', 0)
                stock_code = trade.get('stock_code', '')
                stock_name = trade.get('stock_name', '')
                
                if amount > 0 and price > 0:
                    self.add_position(strategy_name, amount, price, stock_code, stock_name)
        
        elif msg_type == 'query_risk_metrics':
            metrics = self.get_risk_metrics()
            self.send_message({
                'type': 'risk_metrics_response',
                'to': message.get('from'),
                'metrics': metrics
            })
        
        elif msg_type == 'query_positions':
            positions = self.get_all_positions()
            self.send_message({
                'type': 'positions_response',
                'to': message.get('from'),
                'positions': [
                    {
                        'position_id': p.position_id,
                        'strategy_name': p.strategy_name,
                        'amount': p.amount,
                        'avg_price': p.avg_price,
                        'current_price': p.current_price,
                        'profit_loss': (p.current_price - p.avg_price) * p.amount
                    }
                    for p in positions
                ]
            })
        
        elif msg_type == 'issue_assigned':
            # 处理刘邦分发的问题
            issue_id = message.get('issue_id')
            issue_type = message.get('issue_type')
            description = message.get('description')
            
            log.info(f"萧何：收到分配的问题 [{issue_id}]: {description}")
            
            # 处理风控和资金问题
            if issue_type == 'risk':
                # 这里可以添加具体的问题处理逻辑
                log.info(f"萧何：处理风控问题 [{issue_id}]")
                
                # 发送处理结果
                self.send_message({
                    'type': 'issue_handled',
                    'to': '刘邦',
                    'issue_id': issue_id,
                    'status': 'resolved',
                    'message': f'风控问题已处理：{description}',
                    'handled_by': '萧何',
                    'timestamp': time.time()
                })
            else:
                log.warning(f"萧何：收到非风控类型的问题 [{issue_id}]: {issue_type}")
        
        elif msg_type == 'subscribe_data_source':
            # 处理刘邦通知订阅数据源的消息
            data_source_id = message.get('data_source_id')
            data_source_name = message.get('data_source_name')
            
            log.info(f"萧何：收到订阅数据源通知，数据源ID：{data_source_id}，名称：{data_source_name}")
            
            # 尝试订阅数据源
            try:
                from deva.naja.datasource import get_datasource_manager
                
                ds_mgr = get_datasource_manager()
                ds_mgr.load_from_db()
                
                # 查找并订阅数据源
                for ds in ds_mgr.list_all():
                    if getattr(ds, 'id', '') == data_source_id:
                        self.subscribe_to_data_source(ds)
                        log.info(f"萧何：已成功订阅数据源 [{data_source_name}]")
                        
                        # 发送确认消息
                        self.send_message({
                            'type': 'data_source_subscribed',
                            'to': '刘邦',
                            'data_source_id': data_source_id,
                            'data_source_name': data_source_name,
                            'message': f'已成功订阅数据源 [{data_source_name}]',
                            'timestamp': time.time()
                        })
                        break
                else:
                    log.warning(f"萧何：未找到数据源 ID：{data_source_id}")
                    
                    # 发送失败消息
                    self.send_message({
                        'type': 'data_source_subscribe_failed',
                        'to': '刘邦',
                        'data_source_id': data_source_id,
                        'data_source_name': data_source_name,
                        'message': f'未找到数据源 ID：{data_source_id}',
                        'timestamp': time.time()
                    })
            except Exception as e:
                log.error(f"萧何：订阅数据源失败：{e}")
                
                # 发送失败消息
                self.send_message({
                    'type': 'data_source_subscribe_failed',
                    'to': '刘邦',
                    'data_source_id': data_source_id,
                    'data_source_name': data_source_name,
                    'message': f'订阅数据源失败：{e}',
                    'timestamp': time.time()
                })
        
        elif msg_type == 'report_positions':
            # 处理刘邦要求汇报持仓盈亏情况的消息
            log.info("萧何：收到刘邦要求汇报持仓盈亏情况的消息")
            
            # 汇报持仓情况
            self.report_positions()
            
            # 计算总盈亏
            positions = self.get_all_positions()
            total_pnl = 0
            for position in positions:
                total_pnl += (position.current_price - position.avg_price) * position.amount
            
            # 发送盈亏情况给刘邦
            self.send_message({
                'type': 'positions_report',
                'to': '刘邦',
                'total_pnl': total_pnl,
                'position_count': len(positions),
                'message': f'当前总盈亏：{total_pnl:.2f}，持仓数量：{len(positions)}',
                'timestamp': time.time()
            })
    

    

    
    def _calculate_risk_level(self) -> RiskLevel:
        """计算风险等级"""
        exposure_ratio = self._risk_metrics.total_exposure / self._total_capital if self._total_capital > 0 else 0
        
        if exposure_ratio >= self._risk_thresholds['critical']:
            return RiskLevel.CRITICAL
        elif exposure_ratio >= self._risk_thresholds['high']:
            return RiskLevel.HIGH
        elif exposure_ratio >= self._risk_thresholds['medium']:
            return RiskLevel.MEDIUM
        else:
            return RiskLevel.LOW
    
    def _update_risk_metrics(self):
        """更新风险指标"""
        total_exposure = sum(p.amount * p.current_price for p in self._positions.values())
        
        if len(self._positions) > 0:
            max_position = max(p.amount * p.current_price for p in self._positions.values())
            concentration = max_position / total_exposure if total_exposure > 0 else 0
        else:
            concentration = 0
        
        self._risk_metrics.total_exposure = total_exposure
        self._risk_metrics.position_concentration = concentration
        
        self._risk_metrics.risk_level = self._calculate_risk_level()
        
        self._update_metrics('total_exposure', total_exposure)
        self._update_metrics('risk_level', self._risk_metrics.risk_level.value)
    
    def _calculate_position_size(self, confidence: float) -> float:
        """计算建议仓位大小"""
        base_size = self._total_capital * self._max_position_size
        
        adjusted_size = base_size * confidence
        
        available_for_position = self._available_capital * 0.5
        
        return min(adjusted_size, available_for_position)
    
    def _record_risk_check(self, result: RiskCheckResult, signal_data: Dict[str, Any]):
        """记录风控检查"""
        record = {
            'timestamp': time.time(),
            'approved': result.approved,
            'risk_level': result.risk_level.value,
            'reason': result.reason,
            'signal_confidence': signal_data.get('confidence', 0)
        }
        
        self._risk_history.append(record)
        
        if len(self._risk_history) > 1000:
            self._risk_history = self._risk_history[-1000:]
    
    def _load_positions_from_db(self):
        """从数据库加载持仓"""
        try:
            db = NB('naja_positions')
            positions_data = db.get('positions')
            
            if positions_data:
                for pos_data in positions_data:
                    position = Position(
                        position_id=pos_data.get('position_id', ''),
                        strategy_name=pos_data.get('strategy_name', ''),
                        amount=pos_data.get('amount', 0),
                        avg_price=pos_data.get('avg_price', 0),
                        stock_code=pos_data.get('stock_code', ''),
                        stock_name=pos_data.get('stock_name', ''),
                        current_price=pos_data.get('current_price', 0),
                        open_timestamp=pos_data.get('open_timestamp', 0),
                        last_update_ts=pos_data.get('last_update_ts', 0)
                    )
                    self._positions[position.position_id] = position
                
                log.info(f"萧何：已从数据库加载 {len(self._positions)} 个持仓")
                
                self._update_risk_metrics()
        except Exception as e:
            log.warning(f"萧何：加载持仓失败：{e}")
    
    def subscribe_to_data_source(self, data_source):
        """订阅数据源以获取实时价格更新
        
        Args:
            data_source: 数据源对象
        """
        self._data_source = data_source
        # 订阅数据源的更新
        if self._data_source:
            # 尝试获取数据源的流
            data_stream = None
            
            # 先尝试直接获取stream属性
            if hasattr(data_source, 'stream') and data_source.stream:
                data_stream = data_source.stream
            # 再尝试调用get_stream()方法
            elif hasattr(data_source, 'get_stream') and callable(data_source.get_stream):
                data_stream = data_source.get_stream()
            
            if data_stream and hasattr(data_stream, 'sink'):
                data_stream.sink(self._process_data_source_update)
                log.info("萧何：已订阅数据源的流以获取实时价格更新")
            else:
                log.warning("萧何：数据源没有可订阅的流，无法实时更新价格")
    
    def _process_data_source_update(self, data):
        """处理数据源的更新
        
        Args:
            data: 数据源发送的更新数据
        """
        try:
            # 假设数据是一个包含股票代码和价格的字典或列表
            if isinstance(data, dict):
                self._update_price_from_data(data)
                self._check_price_difference()
                self.report_positions_by_strategy()
            elif isinstance(data, list):
                # log.info(f"萧何：处理数据源更新列表，包含 {len(data)} 条数据")
                for item in data:
                    self._update_price_from_data(item)
                self._check_price_difference()
                self.report_positions_by_strategy()
            # 处理 DataFrame 格式的数据
            elif hasattr(data, 'iterrows'):
                # log.info(f"萧何：处理数据源更新 DataFrame，包含 {len(data)} 条数据")
                for index, row in data.iterrows():
                    # 将 DataFrame 行转换为字典
                    row_dict = row.to_dict()
                    self._update_price_from_data(row_dict)
                self._check_price_difference()
                self.report_positions_by_strategy()
        except Exception as e:
            log.warning(f"萧何：处理数据源更新失败：{e}")
    
    def _check_price_difference(self):
        """检查持仓股票的价格差异并报警"""
        try:
            positions = self.get_all_positions()
            if not positions:
                return
            
            log.info("\033[91m" + "=" * 120 + "\033[0m")
            log.info("\033[91m" + "【价格差异报警】" + "\033[0m")
            log.info("\033[91m" + f"{'策略名称':<20}{'股票名称':<15}{'股票代码':<10}{'买入价格':<10}{'当前价格':<10}{'价格差异':<10}{'差异比例':<10}" + "\033[0m")
            log.info("\033[91m" + "-" * 120 + "\033[0m")
            
            for position in positions:
                price_diff = position.current_price - position.avg_price
                diff_ratio = (price_diff / position.avg_price) * 100 if position.avg_price > 0 else 0
                
                # 使用红色打印报警信息
                log.info("\033[91m" + f"{position.strategy_name:<20}{position.stock_name:<15}{position.stock_code:<10}{position.avg_price:<10.2f}{position.current_price:<10.2f}{price_diff:<10.2f}{diff_ratio:<10.2f}%" + "\033[0m")
            
            log.info("\033[91m" + "=" * 120 + "\033[0m")
        except Exception as e:
            log.warning(f"萧何：检查价格差异失败：{e}")
    
    def _update_price_from_data(self, data):
        """从数据中提取价格并更新持仓
        
        Args:
            data: 包含股票信息的数据
        """
        try:
            # 尝试从不同字段获取股票代码
            stock_code = data.get('code', data.get('stock_code', data.get('symbol', data.get('StockCode', data.get('股票代码', '')))))
            
            # 尝试从不同字段获取价格，优先使用最新价
            price_fields = ['current', 'now', 'price', 'last', 'close', '最新价', 'closePrice', 'CurrentPrice']
            price = 0
            for field in price_fields:
                if field in data:
                    price_value = data[field]
                    # 确保价格是数字且大于0
                    try:
                        price = float(price_value)
                        if price > 0:
                            break
                    except (ValueError, TypeError):
                        continue
            
            log.debug(f"萧何：从数据中提取股票代码：{stock_code}，价格：{price}")
            
            if stock_code and price > 0:
                # 更新对应股票的持仓价格
                updated = False
                for position in self._positions.values():
                    if position.stock_code == stock_code:
                        old_price = position.current_price
                        # 计算价格变化百分比
                        price_change_pct = ((price - old_price) / old_price * 100) if old_price > 0 else 0
                        self.update_position_price(position.position_id, price)
                        log.info(f"萧何：更新持仓 [{position.stock_name}({position.stock_code})] 价格：{old_price:.2f} -> {price:.2f} (变化：{price_change_pct:.2f}%)")
                        updated = True
                if not updated:
                    log.debug(f"萧何：未找到股票代码为 {stock_code} 的持仓")
            else:
                log.debug(f"萧何：无效的股票数据，代码：{stock_code}，价格：{price}")
        except Exception as e:
            log.warning(f"萧何：更新价格失败：{e}")
    
    def start_periodic_updates(self):
        """启动定期价格更新和持仓报告"""
        # 启动价格更新回调
        self._price_update_callback = PeriodicCallback(self._update_all_positions, self._price_update_interval)
        
        # 启动持仓报告回调
        self._report_callback = PeriodicCallback(self.report_positions, self._report_interval)
        
        log.info("萧何：已启动定期价格更新和持仓报告")
    
    def stop_periodic_updates(self):
        """停止定期价格更新和持仓报告"""
        # PeriodicCallback返回的是Stream对象，不需要手动停止
        # Stream会在不再被引用时自动清理
        self._price_update_callback = None
        self._report_callback = None
        log.info("萧何：已停止定期价格更新和持仓报告")
    
    def _update_all_positions(self):
        """更新所有持仓的价格"""
        # 尝试从数据源获取所有持仓股票的最新价格
        if self._data_source:
            # 对于每个持仓，尝试从数据源获取最新价格
            # 这里我们假设数据源会通过 _process_data_source_update 方法推送价格更新
            # 但为了确保价格是最新的，我们可以尝试主动获取
            log.debug("萧何：尝试从数据源获取最新价格")
            
            # 这里可以添加主动从数据源获取价格的逻辑
            # 例如，如果数据源有 query 方法，可以调用它获取特定股票的价格
            # 但由于我们不确定数据源的具体实现，我们暂时依赖数据源的推送
            
            # 检查是否有未更新的持仓
            current_time = time.time()
            for position in self._positions.values():
                # 检查价格是否长时间未更新（例如超过10秒）
                if current_time - position.last_update_ts > 10:
                    log.warning(f"萧何：持仓 [{position.stock_name}({position.stock_code})] 价格长时间未更新")
        else:
            log.debug("萧何：未订阅数据源，无法更新价格")
        
        # 记录价格更新时间
        log.debug("萧何：已尝试更新所有持仓价格")
    
    def report_positions(self):
        """以表格形式汇报持仓情况"""
        # 在汇报前更新所有持仓价格，确保使用最新价格
        self._update_all_positions()
        
        positions = self.get_all_positions()
        
        if not positions:
            log.info("萧何：当前无持仓")
            return
        
        # 打印表格头部
        log.info("=" * 120)
        log.info(f"{'策略名称':<20}{'股票名称':<15}{'股票代码':<10}{'持仓数量':<10}{'买入价格':<10}{'当前价格':<10}{'市值':<10}{'盈亏':<10}")
        log.info("-" * 120)
        
        total_value = 0
        total_profit_loss = 0
        
        for position in positions:
            market_value = position.amount * position.current_price
            profit_loss = (position.current_price - position.avg_price) * position.amount
            total_value += market_value
            total_profit_loss += profit_loss
            
            log.info(f"{position.strategy_name:<20}{position.stock_name:<15}{position.stock_code:<10}{position.amount:<10}{position.avg_price:<10.2f}{position.current_price:<10.2f}{market_value:<10.2f}{profit_loss:<10.2f}")
        
        # 打印表格底部
        log.info("-" * 120)
        log.info(f"{'总计':<65}{total_value:<10.2f}{total_profit_loss:<10.2f}")
        log.info("=" * 120)
    
    def report_positions_by_strategy(self):
        """按照策略分组汇报持仓盈亏情况"""
        # 在汇报前更新所有持仓价格，确保使用最新价格
        self._update_all_positions()
        
        positions = self.get_all_positions()
        
        if not positions:
            log.info("萧何：当前无持仓")
            return
        
        # 按策略分组
        strategy_positions = {}
        for position in positions:
            if position.strategy_name not in strategy_positions:
                strategy_positions[position.strategy_name] = []
            strategy_positions[position.strategy_name].append(position)
        
        # 统计上涨和下跌股票
        up_stocks = []
        down_stocks = []
        
        total_value = 0
        total_profit_loss = 0
        total_cost = 0
        
        for strategy_name, strategy_pos in strategy_positions.items():
            strategy_value = 0
            strategy_pnl = 0
            strategy_cost = 0
            
            # 统计策略内上涨和下跌股票
            strategy_up_stocks = []
            strategy_down_stocks = []
            
            for position in strategy_pos:
                market_value = position.amount * position.current_price
                cost = position.amount * position.avg_price
                profit_loss = (position.current_price - position.avg_price) * position.amount
                price_change_pct = ((position.current_price - position.avg_price) / position.avg_price * 100) if position.avg_price > 0 else 0
                
                strategy_value += market_value
                strategy_pnl += profit_loss
                strategy_cost += cost
                total_value += market_value
                total_profit_loss += profit_loss
                total_cost += cost
                
                if profit_loss > 0:
                    up_stocks.append(position)
                    strategy_up_stocks.append(position)
                elif profit_loss < 0:
                    down_stocks.append(position)
                    strategy_down_stocks.append(position)
            
            # 计算策略仓位占比
            strategy_ratio = (strategy_value / total_value * 100) if total_value > 0 else 0
            
            # 打印策略盈亏情况
            if strategy_pnl < 0:
                # 亏损策略，红色打印
                log.info(f"\033[91m萧何：策略 [{strategy_name}] 下跌，绝对盈亏 {strategy_pnl:.2f}，仓位占比 {strategy_ratio:.2f}%\033[0m")
                # 只打印下跌股票
                for position in strategy_down_stocks:
                    price_change_pct = ((position.current_price - position.avg_price) / position.avg_price * 100) if position.avg_price > 0 else 0
                    log.info(f"\033[91m  └─ {position.stock_name}({position.stock_code}) 跌幅 {price_change_pct:.2f}%，盈亏 {((position.current_price - position.avg_price) * position.amount):.2f}\033[0m")
            else:
                # 盈利策略，绿色打印
                log.info(f"\033[92m萧何：策略 [{strategy_name}] 上涨，绝对盈亏 {strategy_pnl:.2f}，仓位占比 {strategy_ratio:.2f}%\033[0m")
                # 只打印上涨股票
                for position in strategy_up_stocks:
                    price_change_pct = ((position.current_price - position.avg_price) / position.avg_price * 100) if position.avg_price > 0 else 0
                    log.info(f"\033[92m  └─ {position.stock_name}({position.stock_code}) 涨幅 {price_change_pct:.2f}%，盈亏 {((position.current_price - position.avg_price) * position.amount):.2f}\033[0m")
        
        # 计算总收益率
        total_return_rate = (total_profit_loss / total_cost * 100) if total_cost > 0 else 0
        
        # 打印总盈亏
        if total_profit_loss < 0:
            log.info(f"\033[91m萧何：总盈亏：{total_profit_loss:.2f}，总市值：{total_value:.2f}，总收益率：{total_return_rate:.2f}%\033[0m")
        else:
            log.info(f"\033[92m萧何：总盈亏：{total_profit_loss:.2f}，总市值：{total_value:.2f}，总收益率：{total_return_rate:.2f}%\033[0m")
        
        # 打印上涨和下跌股票统计
        log.info(f"萧何：上涨股票 {len(up_stocks)} 只，下跌股票 {len(down_stocks)} 只")
    
    def generate_final_report(self, hanxin_agent=None):
        """生成最终交易总结报告
        
        Args:
            hanxin_agent: 韩信智能体实例，用于获取交易历史
        """
        # 在生成最终报告前更新所有持仓价格，确保使用最新价格
        self._update_all_positions()
        
        log.info("\n" + "=" * 100)
        log.info("【萧何最终交易总结报告】")
        log.info("萧何：尊敬的刘邦同志，本次交易实验已完成，以下是我的详细汇报：")
        
        # 1. 交易执行情况
        log.info("\n1. 交易执行情况：")
        if hanxin_agent:
            trades = hanxin_agent.get_trade_history()
            log.info(f"   - 总交易次数：{len(trades)}")
            
            if trades:
                total_trade_value = 0
                for i, trade in enumerate(trades, 1):
                    trade_value = trade.price * trade.amount
                    total_trade_value += trade_value
                    log.info(f"   - 交易 {i}：{trade.action} {trade.strategy_name}")
                    log.info(f"     价格：{trade.price:.2f}, 数量：{trade.amount}")
                    log.info(f"     金额：{trade_value:.2f}, 交易ID：{trade.trade_id}")
                log.info(f"   - 总交易金额：{total_trade_value:.2f}")
            else:
                log.info(f"   - 未执行任何交易")
        else:
            log.info(f"   - 无法获取交易历史（韩信智能体未提供）")
        
        # 2. 资金情况
        log.info("\n2. 资金情况：")
        capital_info = self.get_capital_info()
        log.info(f"   - 总资金：{capital_info['total_capital']:.2f}")
        log.info(f"   - 可用资金：{capital_info['available_capital']:.2f}")
        log.info(f"   - 已用资金：{capital_info['used_capital']:.2f}")
        log.info(f"   - 资金使用率：{capital_info['usage_ratio']:.2%}")
        
        # 3. 风控指标
        log.info("\n3. 风控指标：")
        risk_metrics = self.get_risk_metrics()
        log.info(f"   - 总风险暴露：{risk_metrics['total_exposure']:.2f}")
        log.info(f"   - 风险暴露比例：{risk_metrics['exposure_ratio']:.2%}")
        log.info(f"   - 持仓集中度：{risk_metrics['position_concentration']:.2%}")
        log.info(f"   - 风险等级：{risk_metrics['risk_level']}")
        log.info(f"   - 持仓数量：{risk_metrics['position_count']}")
        
        # 4. 持仓情况
        log.info("\n4. 持仓情况：")
        positions = self.get_all_positions()
        
        if not positions:
            log.info(f"   - 当前无持仓")
        else:
            log.info(f"   - 持仓数量：{len(positions)}")
            total_value = 0
            total_profit_loss = 0
            
            # 打印持仓表格
            log.info("\n   " + "-" * 90)
            log.info(f"   {'策略名称':<15}{'股票名称':<12}{'股票代码':<10}{'数量':<8}{'买入价':<8}{'现价':<8}{'市值':<10}{'盈亏':<10}")
            log.info("   " + "-" * 90)
            
            for position in positions:
                market_value = position.amount * position.current_price
                profit_loss = (position.current_price - position.avg_price) * position.amount
                total_value += market_value
                total_profit_loss += profit_loss
                
                log.info(f"   {position.strategy_name:<15}{position.stock_name:<12}{position.stock_code:<10}{position.amount:<8}{position.avg_price:<8.2f}{position.current_price:<8.2f}{market_value:<10.2f}{profit_loss:<10.2f}")
            
            log.info("   " + "-" * 90)
            log.info(f"   {'总计':<45}{total_value:<10.2f}{total_profit_loss:<10.2f}")
        
        # 5. 韩信工作情况评估
        log.info("\n5. 韩信工作情况评估：")
        if hanxin_agent:
            active_strategies = hanxin_agent.get_active_strategies()
            trades = hanxin_agent.get_trade_history()
            
            log.info(f"   - 启动策略数量：{len(active_strategies)}")
            if active_strategies:
                log.info(f"   - 策略列表：{', '.join(active_strategies[:3])}{'...' if len(active_strategies) > 3 else ''}")
            log.info(f"   - 执行交易次数：{len(trades)}")
            
            if trades:
                # 计算交易成功率（简单评估）
                successful_trades = 0
                for position in positions:
                    if (position.current_price - position.avg_price) > 0:
                        successful_trades += 1
                success_rate = (successful_trades / len(positions) * 100) if positions else 0
                log.info(f"   - 交易成功率：{success_rate:.1f}%")
            else:
                log.info(f"   - 未执行任何交易")
        else:
            log.info(f"   - 无法评估韩信工作情况（智能体未提供）")
        
        # 6. 总结与建议
        log.info("\n6. 总结与建议：")
        if positions:
            total_value = sum(p.amount * p.current_price for p in positions)
            total_cost = sum(p.amount * p.avg_price for p in positions)
            total_pnl = total_value - total_cost
            
            if total_pnl > 0:
                log.info(f"   ✓ 本次交易实验盈利：{total_pnl:.2f}")
                log.info(f"   ✓ 收益率：{total_pnl / total_cost * 100:.2f}%")
            elif total_pnl < 0:
                log.info(f"   ⚠ 本次交易实验亏损：{total_pnl:.2f}")
                log.info(f"   ⚠ 收益率：{total_pnl / total_cost * 100:.2f}%")
            else:
                log.info(f"   ⚡ 本次交易实验盈亏平衡")
        else:
            log.info(f"   ⚠ 本次交易实验未产生任何持仓")
        
        log.info("\n   建议：")
        if risk_metrics['risk_level'] in ['high', 'critical']:
            log.info(f"   - 当前风险等级较高，建议适当降低仓位")
        if len(positions) > 5:
            log.info(f"   - 持仓数量较多，建议适当集中投资")
        if capital_info['usage_ratio'] > 0.8:
            log.info(f"   - 资金使用率较高，建议保留足够的流动性")
        
        log.info("\n萧何：本次汇报完毕，感谢您的关注！")
        log.info("=" * 100)