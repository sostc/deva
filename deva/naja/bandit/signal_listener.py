"""信号监听器

架构核心原则：
- Bandit 是决策中心（TradingCenter）的执行器，隐藏在决策中心背后
- 唯一入口：订阅 NajaEventBus 的 TradeDecisionEvent
- 所有策略信号必须先经过 TradingCenter 审批，审批通过后才发布 TradeDecisionEvent
- 旧版直连 SignalStream 的轮询路径已永久禁用

信号流向：
  策略信号 → TradingCenter（决策审批）
             ├─ 通过 → TradeDecisionEvent → SignalListener → Bandit 执行
             └─ 否决 → 仅记录，不执行
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from deva import NB

from ..signal.stream import get_signal_stream
from ..strategy.result_store import StrategyResult
from ..radar.trading_clock import TRADING_CLOCK_STREAM
from deva.naja.register import SR

# 新架构：Bandit 订阅交易总线
try:
    from deva.naja.events import get_trading_bus, TradeDecisionEvent
    _EVENT_BUS_AVAILABLE = True
    _USE_TRADING_BUS = True
except ImportError:
    log.warning("[SignalListener] 交易总线不可用，Bandit 将无法接收交易决策事件")
    _EVENT_BUS_AVAILABLE = False
    _USE_TRADING_BUS = False

log = logging.getLogger(__name__)

SIGNAL_CONFIG_TABLE = "naja_bandit_signal_config"


@dataclass
class DetectedSignal:
    """检测到的信号"""
    signal_id: str
    strategy_id: str
    strategy_name: str
    stock_code: str
    stock_name: str
    signal_type: str
    price: float
    confidence: float
    timestamp: float
    raw_data: Dict[str, Any] = field(default_factory=dict)
    market_time: float = 0.0  # 行情数据时间


class SignalListener:
    """信号监听器

    监听信号流：
    1. 实时获取信号流中的新信号（流式订阅模式）
    2. 识别信号中的股票信息
    3. 过滤和转换信号格式
    4. 触发虚拟持仓创建回调

    架构演进：
    - 旧版：轮询模式（每2秒轮询一次，实验模式下有60秒延迟问题）
    - 新版：流式订阅模式（信号实时推送，无延迟）
    """

    def __init__(self):
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        self._signal_stream = get_signal_stream()
        self._last_processed_ts = 0.0

        self._callbacks: List[Callable[[DetectedSignal], None]] = []

        self._poll_interval = 2.0
        self._min_confidence = 0.6
        self._force_mode = False

        self._processed_signals: Dict[str, float] = {}
        self._max_processed = 1000

        self._current_phase: str = 'closed'

        self._low_power_mode = False
        self._normal_poll_interval = 2.0
        self._low_power_poll_interval = 60.0

        self._stream_mode = False
        self._stream_sink_registered = False

        self._errors = {"config_load": 0, "config_save": 0, "experiment_check": 0, "parse": 0}

        self._load_config()
        self._subscribe_to_trade_decisions()

    def _subscribe_to_trade_decisions(self):
        """订阅 TradeDecisionEvent 事件（唯一交易信号入口）"""
        if not _EVENT_BUS_AVAILABLE:
            log.warning("[SignalListener] 交易总线不可用，Bandit 无法接收交易决策事件")
            return
        
        try:
            # 使用交易总线订阅
            from deva.naja.events import get_trading_bus
            bus = get_trading_bus()
            bus.subscribe('TradeDecisionEvent', self._on_trade_decision_event)
            log.debug(f"[SignalListener] ✅ 已订阅 TradeBus 的 TradeDecisionEvent（事件驱动模式）")
        except Exception as e:
            log.warning(f"[SignalListener] 订阅 TradeDecisionEvent 失败: {e}")
    
    def _load_config(self):
        """加载配置"""
        try:
            db = NB(SIGNAL_CONFIG_TABLE)
            config = db.get("listener_config")
            if config:
                self._poll_interval = config.get("poll_interval", 2.0)
                self._min_confidence = config.get("min_confidence", 0.6)
                was_running = config.get("was_running", False)
                if was_running:
                    self._running = True
                    log.debug("SignalListener 上次运行中，将自动恢复")
        except Exception as e:
            self._errors["config_load"] += 1
            log.warning(f"[SignalListener] 配置加载失败 (累计{self._errors['config_load']}次): {e}")

    def _save_config(self):
        """保存配置"""
        try:
            db = NB(SIGNAL_CONFIG_TABLE)
            db["listener_config"] = {
                "poll_interval": self._poll_interval,
                "min_confidence": self._min_confidence,
                "was_running": self._running
            }
        except Exception as e:
            self._errors["config_save"] += 1
            log.warning(f"[SignalListener] 配置保存失败 (累计{self._errors['config_save']}次): {e}")
    
    def register_callback(self, callback: Callable[[DetectedSignal], None]):
        """注册信号处理回调"""
        self._callbacks.append(callback)
        log.debug(f"已注册信号回调: {callback.__name__}")
    
    def unregister_callback(self, callback: Callable[[DetectedSignal], None]):
        """注销信号处理回调"""
        if callback in self._callbacks:
            self._callbacks.remove(callback)
    
    def start(self):
        """启动监听

        ═══════════════════════════════════════════════════════
        Bandit 唯一入口：NajaEventBus TradeDecisionEvent
        ═══════════════════════════════════════════════════════

        Bandit 是决策中心的执行器，不直接接收策略信号。
        所有信号必须先经过 TradingCenter 审批，审批通过后才到 Bandit。
        """
        if self._running and self._thread and self._thread.is_alive():
            log.warning("SignalListener 已在运行")
            return

        self._running = True
        self._stop_event.clear()

        TRADING_CLOCK_STREAM.sink(self._on_trading_clock_signal)
        log.debug("SignalListener 已订阅交易时钟信号")

        # 旧版轮询线程已禁用：不再直连 SignalStream
        # 所有信号必须经过 TradingCenter 审批

        self._save_config()

        if _EVENT_BUS_AVAILABLE:
            log.info("SignalListener 已启动 → 等待 TradingCenter 审批后的交易决策")
        else:
            log.warning("SignalListener 已启动 → ⚠️ 交易总线不可用，Bandit 将无法接收交易决策")

    def _on_trading_clock_signal(self, signal: Dict[str, Any]):
        """处理交易时钟信号"""
        signal_type = signal.get('type')
        phase = signal.get('phase')

        if signal_type == 'current_state':
            self._current_phase = phase
        elif signal_type == 'phase_change':
            self._current_phase = phase
            if phase in ('trading', 'pre_market', 'call_auction'):
                log.debug(f"[SignalListener] 进入交易时段")
            else:
                log.debug(f"[SignalListener] 退出交易时段")

    def _enable_stream_mode(self):
        """[已废弃] 旧版流式订阅 SignalStream 直连模式

        新架构通过 NajaEventBus 订阅 TradeDecisionEvent，此方法不再使用。
        保留仅作兼容，避免外部调用报错。
        """
        log.warning("[SignalListener] _enable_stream_mode 已废弃，请使用 NajaEventBus 事件驱动模式")

    def _on_signal_stream_update(self, result: StrategyResult):
        """[已废弃] 处理信号流中的新信号（旧版流式回调）

        新架构使用 _on_trade_decision_event。此方法保留仅作兼容。
        """
        log.debug("[SignalListener] _on_signal_stream_update 已废弃，新架构使用 TradeDecisionEvent")

    def _on_trade_decision_event(self, event):
        """处理 TradeDecisionEvent（新架构唯一交易信号入口）

        TradingCenter 审批通过后发布此事件，Bandit 负责执行。
        event 字段说明（TradeDecisionEvent dataclass）：
          - event.is_approved: 是否批准
          - event.decision: DecisionResult 枚举
          - event.signal_event: 原始 StrategySignalEvent
          - event.approved_symbol: 批准的股票代码（可能与原始不同）
          - event.approved_direction: 批准的方向（SignalDirection 枚举）
          - event.approval_score: 综合审批分数
          - event.position_size: 批准持仓比例
          - event.reason: 决策理由
        """
        if not self._running:
            return

        try:
            # 只处理审批通过的决策
            if not getattr(event, 'is_approved', False):
                decision_val = getattr(event, 'decision', None)
                log.debug(f"[Bandit] TradeDecisionEvent 未通过审批: decision={decision_val}")
                return

            # 提取核心字段
            signal_event = getattr(event, 'signal_event', None)
            symbol = getattr(event, 'approved_symbol', None)
            if not symbol and signal_event:
                symbol = getattr(signal_event, 'symbol', '')
            if not symbol:
                log.debug("[Bandit] TradeDecisionEvent 缺少 symbol，跳过")
                return

            approved_direction = getattr(event, 'approved_direction', None)
            if approved_direction is None and signal_event:
                approved_direction = getattr(signal_event, 'direction', None)

            action_type = 'hold'
            if approved_direction is not None:
                direction_val = getattr(approved_direction, 'value', str(approved_direction))
                action_type = direction_val  # 'buy' / 'sell' / 'neutral'

            if action_type in ('hold', 'neutral'):
                return

            approval_score = getattr(event, 'approval_score', 0.7)
            entry_price = getattr(event, 'entry_price', 0.0) or 0.0

            # 从原始信号补充价格
            if entry_price == 0.0 and signal_event:
                entry_price = getattr(signal_event, 'current_price', 0.0) or 0.0

            strategy_name = 'TradingCenter'
            strategy_id = 'trading_center'
            if signal_event:
                strategy_name = getattr(signal_event, 'strategy_name', strategy_name)
                strategy_id = signal_event.metadata.get('strategy_id', strategy_id) if signal_event.metadata else strategy_id

            # 构建 DetectedSignal（保持与回调接口兼容）
            signal = DetectedSignal(
                signal_id=f"tde_{symbol}_{int(getattr(event, 'timestamp', time.time()) * 1000)}",
                strategy_id=strategy_id,
                strategy_name=strategy_name,
                stock_code=symbol,
                stock_name=getattr(signal_event, 'symbol', symbol) if signal_event else symbol,
                signal_type=action_type.upper(),
                price=entry_price,
                confidence=approval_score,
                timestamp=getattr(event, 'timestamp', time.time()),
                raw_data=event.to_dict() if hasattr(event, 'to_dict') else {}
            )

            # 置信度过滤
            if signal.confidence < self._min_confidence:
                log.debug(f"[Bandit] TradeDecisionEvent 置信度不足: {signal.confidence:.3f} < {self._min_confidence:.3f}")
                return

            log.info(f"[Bandit] 📥 收到 TradeDecisionEvent: {signal.signal_type} {symbol} approval_score={approval_score:.2f}")

            for callback in self._callbacks:
                try:
                    callback(signal)
                except Exception as e:
                    log.error(f"[Bandit] 信号回调执行失败: {e}")

        except Exception as e:
            log.error(f"[Bandit] _on_trade_decision_event 处理失败: {e}")

    def _is_experiment_mode(self) -> bool:
        """检查是否处于实验模式"""
        try:
            from deva.naja.strategy import get_strategy_manager
            mgr = get_strategy_manager()
            experiment_info = mgr.get_experiment_info()
            return experiment_info.get("active", False)
        except Exception as e:
            self._errors["experiment_check"] += 1
            log.debug(f"[SignalListener] 实验模式检查失败 (累计{self._errors['experiment_check']}次): {e}")
            return False

    def _is_allowed_to_run(self) -> bool:
        """检查是否允许运行"""
        import os
        if self._force_mode:
            return True
        if self._is_experiment_mode():
            return True
        # Lab 模式下强制运行
        if os.environ.get('NAJA_LAB_MODE') or os.environ.get('LAB_MODE'):
            return True
        if self._current_phase in ('trading', 'pre_market', 'call_auction', 'closed'):
            return True
        if not hasattr(self, '_last_allowed_log') or time.time() - self._last_allowed_log > 5:
            log.debug(f"[SignalListener] _is_allowed_to_run=False: force={self._force_mode}, experiment={self._is_experiment_mode()}, phase={self._current_phase}")
            self._last_allowed_log = time.time()
        return False
    
    def stop(self):
        """停止监听"""
        if not self._running:
            return
        
        self._running = False
        self._stop_event.set()
        
        if self._thread:
            self._thread.join(timeout=5)
        
        self._save_config()  # 保存运行状态
        
        log.debug("SignalListener 已停止")
    
    def _run_loop(self):
        """主循环（轮询模式后备）"""
        log.debug(f"[SignalListener] _run_loop started: force={self._force_mode}, phase={self._current_phase}")
        while self._running and not self._stop_event.is_set():
            if self._stream_mode:
                self._stop_event.wait(1)
                continue
            try:
                if self._is_allowed_to_run():
                    self._process_signals()
            except Exception as e:
                log.error(f"SignalListener 处理错误: {e}")

            self._stop_event.wait(self._poll_interval)

    def _process_signals(self):
        """处理信号流中的新信号（轮询模式）

        包含自动阈值调整：如果长时间没有信号通过阈值，自动降低阈值以产生交易。
        包含低功耗模式：当上游（策略）不活跃时，自动增大轮询间隔。
        """
        try:
            active_count = 0
            from ..strategy import get_strategy_manager
            mgr = get_strategy_manager()
            for entry in mgr.list_all():
                if entry.is_processing_data(timeout=300):
                    active_count += 1

            if active_count == 0:
                if not self._low_power_mode:
                    self._low_power_mode = True
                    self._poll_interval = self._low_power_poll_interval
                    log.warning(f"[SignalListener] 没有策略在处理数据，进入低频模式，间隔: {self._poll_interval}s")
                return

            recent = self._signal_stream.get_recent(limit=50)
            log.debug(f"[Bandit] 获取到 {len(recent)} 个信号")

            if self._low_power_mode:
                self._low_power_mode = False
                self._poll_interval = self._normal_poll_interval
                log.warning(f"[SignalListener] 上游恢复，退出低频模式，间隔恢复: {self._poll_interval}s")
        except Exception as e:
            log.error(f"获取信号流失败: {e}")
            return

        now = time.time()
        if not hasattr(self, '_last_signal_time'):
            self._last_signal_time = now
        if not hasattr(self, '_consecutive_rejections'):
            self._consecutive_rejections = 0

        for result in recent:
            if result.ts <= self._last_processed_ts:
                continue

            if self._is_processed(result.id):
                continue

            signal = self._parse_signal(result)
            if signal is None:
                continue

            log.debug(f"[Bandit] 收到信号: {signal.stock_code} {signal.stock_name} 置信度={signal.confidence} 类型={signal.signal_type}")

            if signal.confidence < self._min_confidence:
                self._consecutive_rejections += 1
                log.warning(f"[Bandit] 置信度低于阈值: {signal.confidence:.3f} < {self._min_confidence:.3f} (连续拒绝: {self._consecutive_rejections})")

                if self._consecutive_rejections >= 10 and self._min_confidence > 0.05:
                    old_threshold = self._min_confidence
                    self._min_confidence = max(0.05, self._min_confidence - 0.1)
                    self._consecutive_rejections = 0
                    log.warning(f"[Bandit] ⚠️ 自动降低置信度阈值: {old_threshold:.3f} -> {self._min_confidence:.3f}")
                    self._save_config()
                continue

            self._consecutive_rejections = 0
            self._mark_processed(result.id, result.ts)

            if result.ts > self._last_processed_ts:
                self._last_processed_ts = result.ts

            for callback in self._callbacks:
                try:
                    callback(signal)
                except Exception as e:
                    log.error(f"信号回调执行失败: {e}")
    
    def _parse_signal(self, result: StrategyResult) -> Optional[DetectedSignal]:
        """解析信号

        支持两种格式：
        1. 直接格式: {signal_type: "BUY", stock_code: "xxx", price: xxx}
        2. River picks 格式: {signal: "xxx", picks: [{code, name, price, up_probability}]}
        """
        try:
            output = result.output_full
            if not output:
                output = result.output_preview
                if not output:
                    log.warning(f"[Bandit] 解析信号失败: output_full 和 output_preview 都为空, result_id={result.id}")
                    return None

            if isinstance(output, dict):
                signal_data = output
            elif hasattr(output, 'to_dict'):
                signal_data = output.to_dict()
            else:
                log.warning(f"[Bandit] 解析信号失败: output 类型不支持, type={type(output)}")
                return None

            log.debug(f"[Bandit] 解析信号: id={result.id[:20] if result.id else 'N/A'}..., keys={list(signal_data.keys())}")
            
            stock_code = ""
            stock_name = ""
            price = 0.0
            confidence = 0.7
            signal_type = "BUY"
            market_time = 0.0
            
            if 'picks' in signal_data and isinstance(signal_data['picks'], list) and signal_data['picks']:
                picks = signal_data['picks']
                top_pick = picks[0]
                
                stock_code = str(top_pick.get('code', '') or top_pick.get('stock_code', ''))
                stock_name = top_pick.get('name', '') or top_pick.get('stock_name', '')
                price = float(top_pick.get('price', 0) or top_pick.get('close', 0) or top_pick.get('current', 0))
                
                signal_type = "BUY"
                
                prob_fields = ['up_probability', 'order_flow_up_probability', 'anomaly_score', 'probability']
                for pf in prob_fields:
                    if pf in top_pick:
                        confidence = float(top_pick[pf])
                        if pf == 'anomaly_score':
                            confidence = min(1.0, confidence / 10.0)
                        break
                
                if signal_data.get('signal'):
                    signal_type = f"BUY ({signal_data['signal']})"
            else:
                stock_code = self._extract_stock_code(signal_data)
                stock_name = signal_data.get('name', '') or signal_data.get('stock_name', '')
                price = self._extract_price(signal_data)
                confidence = float(signal_data.get('confidence', 0.7))
                signal_type = signal_data.get('signal_type', signal_data.get('type', 'BUY'))
            
            if not stock_code:
                return None
            
            # 提取行情时间
            market_time = self._extract_market_time(signal_data, result.ts)

            # 优先从 metadata 获取 signal_confidence
            metadata = getattr(result, 'metadata', {}) or {}
            if isinstance(metadata, dict):
                signal_confidence = metadata.get('signal_confidence', confidence)
            else:
                signal_confidence = confidence

            return DetectedSignal(
                signal_id=result.id,
                strategy_id=result.strategy_id,
                strategy_name=result.strategy_name,
                stock_code=stock_code,
                stock_name=stock_name,
                signal_type=signal_type,
                price=price,
                confidence=signal_confidence,
                timestamp=result.ts,
                raw_data=signal_data,
                market_time=market_time
            )
            
        except Exception as e:
            self._errors["parse"] += 1
            log.warning(f"[SignalListener] 解析信号失败 (累计{self._errors['parse']}次): {e}")
            return None
    
    def _extract_market_time(self, data: Dict[str, Any], default_ts: float) -> float:
        """提取行情数据时间
        
        尝试从多个可能的字段中提取行情时间：
        - data_time: 行情数据时间
        - datetime: 日期时间
        - timestamp: 时间戳
        - market_time: 市场时间
        """
        try:
            # 尝试直接获取时间戳字段
            for key in ['data_time', 'timestamp', 'market_time', 'ts']:
                if key in data:
                    value = data[key]
                    if isinstance(value, (int, float)) and value > 1000000000:
                        return float(value)
            
            # 尝试解析 datetime 字符串
            for key in ['datetime', 'time', 'date']:
                if key in data:
                    value = data[key]
                    if isinstance(value, str):
                        try:
                            from datetime import datetime
                            # 尝试多种格式
                            for fmt in ['%Y-%m-%d %H:%M:%S', '%Y%m%d%H%M%S', '%H:%M:%S']:
                                try:
                                    dt = datetime.strptime(value, fmt)
                                    # 如果是只有时间格式，使用当前日期
                                    if fmt == '%H:%M:%S':
                                        from datetime import datetime as dt2
                                        now = dt2.now()
                                        dt = dt.replace(year=now.year, month=now.month, day=now.day)
                                    return dt.timestamp()
                                except ValueError:
                                    continue
                        except Exception:
                            pass
            
            # 如果从 picks 中获取，尝试第一个 pick 的时间字段
            if 'picks' in data and isinstance(data['picks'], list) and data['picks']:
                top_pick = data['picks'][0]
                for key in ['data_time', 'timestamp', 'market_time', 'ts']:
                    if key in top_pick:
                        value = top_pick[key]
                        if isinstance(value, (int, float)) and value > 1000000000:
                            return float(value)
            
            # 如果都没有找到，使用默认时间戳
            return default_ts
            
        except Exception as e:
            log.debug(f"提取行情时间失败: {e}")
            return default_ts
    
    def _extract_stock_code(self, data: Dict[str, Any]) -> str:
        """提取股票代码"""
        for key in ['code', 'stock_code', 'symbol', 'Code', 'Symbol']:
            if key in data:
                return str(data[key])
        return ''
    
    def _extract_price(self, data: Dict[str, Any]) -> float:
        """提取价格"""
        for key in ['price', 'close', 'current', 'last', ' Price']:
            if key in data:
                try:
                    return float(data[key])
                except (ValueError, TypeError):
                    continue
        return 0.0
    
    def _is_processed(self, signal_id: str) -> bool:
        """检查信号是否已处理"""
        return signal_id in self._processed_signals
    
    def _mark_processed(self, signal_id: str, timestamp: float):
        """标记信号已处理"""
        self._processed_signals[signal_id] = timestamp
        
        if len(self._processed_signals) > self._max_processed:
            sorted_items = sorted(self._processed_signals.items(), key=lambda x: x[1])
            self._processed_signals = dict(sorted_items[-self._max_processed//2:])
    
    def set_poll_interval(self, seconds: float):
        """设置轮询间隔

        Args:
            seconds: 新的轮询间隔秒数
        """
        old_interval = self._poll_interval
        new_interval = max(0.5, seconds)

        if self._low_power_mode and new_interval > self._normal_poll_interval:
            self._low_power_poll_interval = new_interval
        else:
            if not self._low_power_mode:
                self._normal_poll_interval = new_interval
            self._poll_interval = new_interval

        if old_interval != self._poll_interval:
            log.debug(f"[SignalListener] 轮询间隔调整: {old_interval}s → {self._poll_interval}s")
        self._save_config()
    
    def set_min_confidence(self, confidence: float):
        """设置最小置信度"""
        self._min_confidence = max(0.0, min(1.0, confidence))
        self._save_config()
    
    def get_status(self) -> dict:
        """获取状态"""
        return {
            "running": self._running,
            "stream_mode": self._stream_mode,
            "poll_interval": self._poll_interval,
            "min_confidence": self._min_confidence,
            "last_processed_ts": self._last_processed_ts,
            "processed_count": len(self._processed_signals),
            "callbacks_count": len(self._callbacks),
            "errors": dict(self._errors),
        }

    def get_errors(self) -> dict:
        """获取错误统计"""
        return dict(self._errors)

