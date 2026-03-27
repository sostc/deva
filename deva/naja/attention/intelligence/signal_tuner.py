"""
Signal Tuner - 信号自适应调参系统

监控策略信号产生和盈亏反馈，自动调整参数以实现目标：
1. 每天产生足够的买入信号（目标10只股票）
2. 尽量让买入的股票盈利
3. 形成正向反馈循环

工作流程：
1. 监控信号产生频率
2. 跟踪买入盈亏
3. 分析哪些参数组合效果好
4. 自动调低阈值增加信号，或调高阈值提高质量
"""

import time
import threading
import logging
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from collections import defaultdict, deque
from datetime import datetime, timedelta
import json
import pickle
from pathlib import Path

try:
    from deva import NB
except ImportError:
    NB = None

log = logging.getLogger(__name__)


@dataclass
class SignalRecord:
    """信号记录"""
    symbol: str
    strategy_id: str
    signal_type: str
    confidence: float
    score: float
    timestamp: float
    price: float
    params_snapshot: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TradeRecord:
    """交易记录（跟踪买入后的盈亏）"""
    symbol: str
    strategy_id: str
    entry_price: float
    entry_time: float
    exit_price: float = 0.0
    exit_time: float = 0.0
    return_pct: float = 0.0
    holding_seconds: float = 0.0
    max_favorable_move: float = 0.0
    max_adverse_move: float = 0.0
    reason: str = ""
    params_snapshot: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ParamAdjustment:
    """参数调整记录"""
    param_name: str
    old_value: Any
    new_value: Any
    reason: str
    timestamp: float
    effective: bool = False


class SignalTuner:
    """
    信号调参器

    根据信号产生频率和交易盈亏反馈，自动调整策略参数
    """

    TARGET_DAILY_SIGNALS = 10
    TARGET_WIN_RATE = 0.6
    MIN_SIGNALS_PER_HOUR = 3

    def __init__(
        self,
        target_daily_signals: int = 10,
        check_interval: float = 60.0,
        adjustment_cooldown: float = 300.0,
        store_path: Optional[str] = None
    ):
        self.target_daily_signals = target_daily_signals
        self.check_interval = check_interval
        self.adjustment_cooldown = adjustment_cooldown

        self._store_path = store_path or Path.home() / ".naja" / "signal_tuner.pkl"
        self._db = NB("naja_signal_tuner") if NB else None

        self._lock = threading.RLock()

        self._signal_records: deque = deque(maxlen=10000)
        self._trade_records: List[TradeRecord] = []
        self._param_adjustments: deque = deque(maxlen=500)

        self._last_adjustment_time: Dict[str, float] = {}

        self._current_params: Dict[str, Dict[str, float]] = {}
        self._param_weights: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))

        self._enabled_strategies: Dict[str, bool] = {}
        self._running = False
        self._monitor_thread: Optional[threading.Thread] = None

        self._callbacks: List[Callable[[Dict], None]] = []
        self._tuning_rules: Dict[str, Dict[str, Any]] = self._default_tuning_rules()

        self._daily_stats: Dict[str, Any] = {
            'date': datetime.now().strftime('%Y-%m-%d'),
            'signals': 0,
            'buy_signals': 0,
            'trades': 0,
            'winning_trades': 0,
            'total_return': 0.0,
            'avg_return': 0.0
        }

        self._load_state()

    def _default_tuning_rules(self) -> Dict[str, Dict[str, Any]]:
        """默认调参规则"""
        return {
            'momentum_surge_tracker': {
                'price_threshold': {
                    'min': 0.01,
                    'max': 0.05,
                    'default': 0.03,
                    'step': 0.005,
                    'description': '价格突破阈值，越低越容易触发'
                },
                'volume_threshold': {
                    'min': 1.2,
                    'max': 3.0,
                    'default': 2.0,
                    'step': 0.2,
                    'description': '成交量放大阈值，越低越容易触发'
                },
                'combined_threshold': {
                    'min': 0.3,
                    'max': 0.8,
                    'default': 0.5,
                    'step': 0.05,
                    'description': '综合得分阈值，越低越容易触发'
                }
            },
            'smart_money_flow_detector': {
                'accumulation_threshold': {
                    'min': 0.4,
                    'max': 0.9,
                    'default': 0.7,
                    'step': 0.05,
                    'description': '建仓信号阈值，越低越容易触发'
                },
                'min_symbol_weight': {
                    'min': 1.5,
                    'max': 4.0,
                    'default': 2.5,
                    'step': 0.3,
                    'description': '最低个股权重，越低越容易选入'
                }
            },
            'anomaly_pattern_sniper': {
                'zscore_threshold': {
                    'min': 1.5,
                    'max': 4.0,
                    'default': 2.5,
                    'step': 0.3,
                    'description': 'Z分数阈值，越低越容易触发'
                }
            }
        }

    def _load_state(self):
        """加载状态"""
        if self._db:
            try:
                data = self._db.get('tuner_state', {})
                if data:
                    self._current_params = data.get('params', {})
                    self._param_weights = defaultdict(lambda: defaultdict(float), data.get('weights', {}))
                    log.info("[SignalTuner] 已加载调参状态")
            except Exception as e:
                log.debug(f"[SignalTuner] 加载状态失败: {e}")

    def _save_state(self):
        """保存状态"""
        if self._db:
            try:
                self._db['tuner_state'] = {
                    'params': dict(self._current_params),
                    'weights': {k: dict(v) for k, v in self._param_weights.items()},
                    'last_update': time.time()
                }
            except Exception as e:
                log.debug(f"[SignalTuner] 保存状态失败: {e}")

    def record_signal(
        self,
        symbol: str,
        strategy_id: str,
        signal_type: str,
        confidence: float,
        score: float,
        price: float,
        params_snapshot: Optional[Dict[str, Any]] = None
    ):
        """记录产生的信号"""
        with self._lock:
            record = SignalRecord(
                symbol=symbol,
                strategy_id=strategy_id,
                signal_type=signal_type,
                confidence=confidence,
                score=score,
                timestamp=time.time(),
                price=price,
                params_snapshot=params_snapshot or {}
            )
            self._signal_records.append(record)
            self._update_daily_stats('signals')
            if signal_type == 'buy':
                self._update_daily_stats('buy_signals')

            log.debug(f"[SignalTuner] 记录信号: {signal_type} {symbol} @{price:.2f}")

    def record_trade(
        self,
        symbol: str,
        strategy_id: str,
        entry_price: float,
        entry_time: float,
        params_snapshot: Optional[Dict[str, Any]] = None
    ):
        """记录买入交易"""
        with self._lock:
            trade = TradeRecord(
                symbol=symbol,
                strategy_id=strategy_id,
                entry_price=entry_price,
                entry_time=entry_time,
                params_snapshot=params_snapshot or {}
            )
            self._trade_records.append(trade)
            self._update_daily_stats('trades')
            log.debug(f"[SignalTuner] 记录买入: {symbol} @{entry_price:.2f}")

    def update_trade_result(
        self,
        symbol: str,
        exit_price: float,
        exit_time: float,
        max_favorable_move: float = 0.0,
        max_adverse_move: float = 0.0,
        reason: str = ""
    ):
        """更新交易结果"""
        with self._lock:
            for trade in reversed(self._trade_records):
                if trade.symbol == symbol and trade.exit_price == 0.0:
                    trade.exit_price = exit_price
                    trade.exit_time = exit_time
                    trade.holding_seconds = exit_time - trade.entry_time
                    trade.return_pct = (exit_price - trade.entry_price) / trade.entry_price * 100
                    trade.max_favorable_move = max_favorable_move
                    trade.max_adverse_move = max_adverse_move
                    trade.reason = reason

                    self._update_daily_stats('total_return', trade.return_pct)
                    if trade.return_pct > 0:
                        self._update_daily_stats('winning_trades')

                    log.info(f"[SignalTuner] 交易完成: {symbol} 收益={trade.return_pct:+.2f}% 原因={reason}")
                    self._learn_from_trade(trade)
                    break

    def _update_daily_stats(self, key: str, value: float = 1.0):
        """更新每日统计"""
        today = datetime.now().strftime('%Y-%m-%d')
        if self._daily_stats['date'] != today:
            self._daily_stats = {
                'date': today,
                'signals': 0,
                'buy_signals': 0,
                'trades': 0,
                'winning_trades': 0,
                'total_return': 0.0,
                'avg_return': 0.0
            }

        if key == 'total_return':
            self._daily_stats['total_return'] += value
            if self._daily_stats['trades'] > 0:
                self._daily_stats['avg_return'] = self._daily_stats['total_return'] / self._daily_stats['trades']
        else:
            self._daily_stats[key] += value

    def _learn_from_trade(self, trade: TradeRecord):
        """从交易结果学习，调整参数权重"""
        if not trade.params_snapshot:
            return

        is_profitable = trade.return_pct > 0
        reward = trade.return_pct / 10.0

        for strategy_id, params in trade.params_snapshot.items():
            for param_name, value in params.items():
                key = f"{strategy_id}.{param_name}"
                if is_profitable:
                    self._param_weights[strategy_id][param_name] += reward * 0.1
                else:
                    self._param_weights[strategy_id][param_name] -= reward * 0.05

                self._param_weights[strategy_id][param_name] = max(-1.0, min(1.0, self._param_weights[strategy_id][param_name]))

    def _should_adjust(self, strategy_id: str, param_name: str) -> bool:
        """检查是否可以调整参数"""
        key = f"{strategy_id}.{param_name}"
        last_time = self._last_adjustment_time.get(key, 0)
        return time.time() - last_time >= self.adjustment_cooldown

    def _record_adjustment(
        self,
        strategy_id: str,
        param_name: str,
        old_value: Any,
        new_value: Any,
        reason: str,
        effective: bool = False
    ):
        """记录参数调整"""
        adjustment = ParamAdjustment(
            param_name=f"{strategy_id}.{param_name}",
            old_value=old_value,
            new_value=new_value,
            reason=reason,
            timestamp=time.time(),
            effective=effective
        )
        self._param_adjustments.append(adjustment)
        self._last_adjustment_time[f"{strategy_id}.{param_name}"] = time.time()
        self._save_state()

    def get_current_params(self, strategy_id: str) -> Dict[str, float]:
        """获取策略当前参数"""
        with self._lock:
            if strategy_id not in self._current_params:
                self._current_params[strategy_id] = self._get_default_params(strategy_id)
            return self._current_params[strategy_id].copy()

    def _get_default_params(self, strategy_id: str) -> Dict[str, float]:
        """获取策略默认参数"""
        defaults = {
            'momentum_surge_tracker': {
                'price_threshold': 0.03,
                'volume_threshold': 2.0,
                'combined_threshold': 0.5
            },
            'smart_money_flow_detector': {
                'accumulation_threshold': 0.7,
                'min_symbol_weight': 2.5
            },
            'anomaly_pattern_sniper': {
                'zscore_threshold': 2.5
            }
        }
        return defaults.get(strategy_id, {})

    def register_callback(self, callback: Callable[[Dict], None]):
        """注册参数调整回调"""
        self._callbacks.append(callback)

    def emit_param_adjustment(self, strategy_id: str, param_name: str, new_value: float, reason: str):
        """发出参数调整通知"""
        adjustment = {
            'strategy_id': strategy_id,
            'param_name': param_name,
            'new_value': new_value,
            'reason': reason,
            'timestamp': time.time()
        }

        for callback in self._callbacks:
            try:
                callback(adjustment)
            except Exception as e:
                log.error(f"[SignalTuner] 参数调整回调失败: {e}")

        self._record_adjustment(strategy_id, param_name,
                                 self._current_params.get(strategy_id, {}).get(param_name, 0),
                                 new_value, reason)

    def analyze_and_adjust(self) -> List[Dict]:
        """分析信号和交易数据，进行参数调整"""
        with self._lock:
            now = time.time()
            today = datetime.now().strftime('%Y-%m-%d')
            adjustments_made = []

            today_signals = [s for s in self._signal_records
                           if datetime.fromtimestamp(s.timestamp).strftime('%Y-%m-%d') == today]
            today_buy_signals = [s for s in today_signals if s.signal_type == 'buy']

            hour_signals = [s for s in self._signal_records
                          if now - s.timestamp < 3600]
            hour_buy_signals = [s for s in hour_signals if s.signal_type == 'buy']

            completed_trades = [t for t in self._trade_records
                              if t.exit_price > 0 and t.return_pct != 0]
            recent_trades = [t for t in completed_trades
                           if datetime.fromtimestamp(t.exit_time).strftime('%Y-%m-%d') == today]

            win_rate = 0.0
            avg_return = 0.0
            if recent_trades:
                winning = sum(1 for t in recent_trades if t.return_pct > 0)
                win_rate = winning / len(recent_trades)
                avg_return = sum(t.return_pct for t in recent_trades) / len(recent_trades)

            log.info(f"[SignalTuner] 分析: 今日信号={len(today_buy_signals)}/{self.target_daily_signals}, "
                    f"胜率={win_rate:.1%}, 平均收益={avg_return:+.2f}%")

            if len(today_buy_signals) < self.target_daily_signals * 0.5:
                log.info(f"[SignalTuner] 信号不足，需要降低阈值增加触发")
                adjustments = self._decrease_thresholds(len(today_buy_signals))
                adjustments_made.extend(adjustments)

            elif len(today_buy_signals) >= self.target_daily_signals * 0.8:
                if win_rate > 0.7 and avg_return > 1.0:
                    log.info(f"[SignalTuner] 表现良好，可适当提高阈值提升质量")
                    adjustments = self._increase_thresholds_for_quality()
                    adjustments_made.extend(adjustments)

            if recent_trades and win_rate < 0.4:
                log.warning(f"[SignalTuner] 胜率过低 ({win_rate:.1%})，需要调整参数")
                adjustments = self._adjust_based_on_winning_trades()
                adjustments_made.extend(adjustments)

            if recent_trades and avg_return < -2.0:
                log.warning(f"[SignalTuner] 平均亏损过大 ({avg_return:.2f}%)，收紧止损参数")
                adjustments = self._tighten_loss_parameters()
                adjustments_made.extend(adjustments)

            return adjustments_made

    def _decrease_thresholds(self, current_signals: int) -> List[Dict]:
        """降低阈值增加信号产生"""
        adjustments = []
        shortage_ratio = (self.target_daily_signals - current_signals) / max(current_signals, 1)

        strategies_to_adjust = ['momentum_surge_tracker', 'smart_money_flow_detector']

        for strategy_id in strategies_to_adjust:
            if strategy_id not in self._tuning_rules:
                continue

            rules = self._tuning_rules[strategy_id]
            current = self.get_current_params(strategy_id)

            for param_name, rule in rules.items():
                if not self._should_adjust(strategy_id, param_name):
                    continue

                current_value = current.get(param_name, rule['default'])
                min_val = rule['min']
                step = rule['step']

                decrease_amount = step * (1 + shortage_ratio)
                new_value = max(min_val, current_value - decrease_amount)

                if new_value < current_value:
                    self._current_params[strategy_id][param_name] = new_value
                    reason = f"信号不足(当前{current_signals})，降低{param_name} {current_value:.4f}->{new_value:.4f}"
                    self.emit_param_adjustment(strategy_id, param_name, new_value, reason)
                    adjustments.append({
                        'strategy_id': strategy_id,
                        'param_name': param_name,
                        'old_value': current_value,
                        'new_value': new_value,
                        'reason': reason
                    })
                    log.info(f"[SignalTuner] 调整: {strategy_id}.{param_name} = {new_value:.4f} ({reason})")
                    break

        return adjustments

    def _increase_thresholds_for_quality(self) -> List[Dict]:
        """提高阈值提升信号质量"""
        adjustments = []

        for strategy_id in ['momentum_surge_tracker']:
            if strategy_id not in self._tuning_rules:
                continue

            rules = self._tuning_rules[strategy_id]
            current = self.get_current_params(strategy_id)

            for param_name, rule in rules.items():
                if not self._should_adjust(strategy_id, param_name):
                    continue

                current_value = current.get(param_name, rule['default'])
                max_val = rule['max']
                step = rule['step']

                new_value = min(max_val, current_value + step * 0.5)

                if new_value > current_value:
                    self._current_params[strategy_id][param_name] = new_value
                    reason = f"表现良好，提高{param_name}提升质量"
                    self.emit_param_adjustment(strategy_id, param_name, new_value, reason)
                    adjustments.append({
                        'strategy_id': strategy_id,
                        'param_name': param_name,
                        'old_value': current_value,
                        'new_value': new_value,
                        'reason': reason
                    })
                    log.info(f"[SignalTuner] 调整: {strategy_id}.{param_name} = {new_value:.4f} ({reason})")
                    break

        return adjustments

    def _adjust_based_on_winning_trades(self) -> List[Dict]:
        """根据盈利交易调整参数"""
        adjustments = []

        completed_trades = [t for t in self._trade_records if t.exit_price > 0]
        if not completed_trades:
            return adjustments

        winning_trades = [t for t in completed_trades if t.return_pct > 0]
        losing_trades = [t for t in completed_trades if t.return_pct <= 0]

        if losing_trades:
            avg_loss = sum(t.return_pct for t in losing_trades) / len(losing_trades)

            if avg_loss < -5.0:
                reason = f"平均亏损{avg_loss:.2f}%，收紧止损"
                log.info(f"[SignalTuner] {reason}")

        return adjustments

    def _tighten_loss_parameters(self) -> List[Dict]:
        """收紧亏损参数"""
        adjustments = []
        log.info("[SignalTuner] 收紧亏损参数...")
        return adjustments

    def start(self):
        """启动调参器"""
        if self._running:
            return

        self._running = True
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
        log.info("[SignalTuner] 调参器已启动")

    def stop(self):
        """停止调参器"""
        self._running = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
        self._save_state()
        log.info("[SignalTuner] 调参器已停止")

    def _monitor_loop(self):
        """监控循环"""
        while self._running:
            try:
                adjustments = self.analyze_and_adjust()
                if adjustments:
                    log.info(f"[SignalTuner] 本次调整: {len(adjustments)} 项")

                time.sleep(self.check_interval)
            except Exception as e:
                log.error(f"[SignalTuner] 监控循环错误: {e}")
                time.sleep(self.check_interval)

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            today = datetime.now().strftime('%Y-%m-%d')
            today_signals = [s for s in self._signal_records
                           if datetime.fromtimestamp(s.timestamp).strftime('%Y-%m-%d') == today]
            today_buy_signals = [s for s in today_signals if s.signal_type == 'buy']

            completed_trades = [t for t in self._trade_records if t.exit_price > 0]
            today_trades = [t for t in completed_trades
                          if datetime.fromtimestamp(t.exit_time).strftime('%Y-%m-%d') == today]

            return {
                'running': self._running,
                'daily_stats': self._daily_stats.copy(),
                'today_buy_signals': len(today_buy_signals),
                'target_daily_signals': self.target_daily_signals,
                'today_trades': len(today_trades),
                'total_trades': len(self._trade_records),
                'completed_trades': len(completed_trades),
                'recent_adjustments': len(self._param_adjustments),
                'current_params': {k: v.copy() for k, v in self._current_params.items()}
            }

    def get_suggested_params(self, strategy_id: str) -> Dict[str, float]:
        """获取建议的参数（用于应用）"""
        return self.get_current_params(strategy_id)


_signal_tuner: Optional[SignalTuner] = None
_tuner_lock = threading.Lock()


def get_signal_tuner(
    target_daily_signals: int = 10,
    check_interval: float = 60.0
) -> SignalTuner:
    """获取 SignalTuner 单例"""
    global _signal_tuner
    if _signal_tuner is None:
        with _tuner_lock:
            if _signal_tuner is None:
                _signal_tuner = SignalTuner(
                    target_daily_signals=target_daily_signals,
                    check_interval=check_interval
                )
    return _signal_tuner


def start_signal_tuner():
    """启动信号调参器"""
    tuner = get_signal_tuner()
    tuner.start()
    return tuner


def stop_signal_tuner():
    """停止信号调参器"""
    global _signal_tuner
    if _signal_tuner:
        _signal_tuner.stop()
        _signal_tuner = None
