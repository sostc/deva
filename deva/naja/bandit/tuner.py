"""BanditTuner - Bandit系统/策略调优/超参

别名/关键词: 策略调优、超参、bandit tuner、参数调优

Bandit 参数调优器 - 持续循环优化版

调参模式核心逻辑：
1. 数据播放 → 信号来时用 VirtualPortfolio 开仓
2. 价格更新时调用 VirtualPortfolio.update_price 检查止盈/止损
3. 数据播放完后从 VirtualPortfolio 获取真实交易结果评估
4. 自动调整参数（放宽或收紧）
5. 持续循环直到找到最优

使用 VirtualPortfolio 管理真实持仓和盈亏计算。
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

log = logging.getLogger(__name__)


@dataclass
class ParameterSpace:
    """参数空间定义"""
    min_confidence: List[float] = None
    stop_loss_pct: List[float] = None
    take_profit_pct: List[float] = None
    position_size_pct: List[float] = None

    def __post_init__(self):
        if self.min_confidence is None:
            self.min_confidence = [0.6, 0.5, 0.4, 0.3, 0.2]
        if self.stop_loss_pct is None:
            self.stop_loss_pct = [-3, -5, -7, -10]
        if self.take_profit_pct is None:
            self.take_profit_pct = [5, 8, 10, 15, 20]
        if self.position_size_pct is None:
            self.position_size_pct = [10, 15, 20, 25]


@dataclass
class TuningResult:
    """单次调参结果"""
    params: Dict[str, Any]
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    profit_factor: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    signal_count: int
    timestamp: float

    def get_score(self) -> float:
        weights = {
            'total_return': 0.4,
            'sharpe_ratio': 0.3,
            'win_rate': 0.2,
            'max_drawdown': 0.1,
        }
        return (
            weights['total_return'] * max(0, self.total_return / 100) +
            weights['sharpe_ratio'] * max(0, self.sharpe_ratio) +
            weights['win_rate'] * max(0, self.win_rate / 100) +
            weights['max_drawdown'] * max(0, (20 - self.max_drawdown) / 20)
        )

    def to_dict(self) -> dict:
        return {
            "params": self.params,
            "total_return": self.total_return,
            "sharpe_ratio": self.sharpe_ratio,
            "max_drawdown": self.max_drawdown,
            "win_rate": self.win_rate,
            "profit_factor": self.profit_factor,
            "total_trades": self.total_trades,
            "signal_count": self.signal_count,
            "timestamp": self.timestamp,
        }


class BanditTuner:
    """Bandit 参数调优器 - 使用 VirtualPortfolio 真实持仓

    核心逻辑：
    1. 监听 AttentionCenter 的信号
    2. 使用 VirtualPortfolio 管理真实持仓和盈亏
    3. 数据播放时更新持仓价格，VirtualPortfolio 自动检查止盈/止损
    4. 数据播放完后评估当前参数效果
    5. 自动调整参数（放宽或收紧）
    6. 持续循环直到找到最优
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return

        self._parameter_space = ParameterSpace()
        self._best_params: Optional[Dict[str, Any]] = None
        self._best_result: Optional[TuningResult] = None
        self._tuning_history: List[TuningResult] = []

        self._current_params = {
            'min_confidence': 0.3,
            'stop_loss_pct': -5.0,
            'take_profit_pct': 12.0,
            'position_size_pct': 20.0,
        }

        self._phase = 'waiting'
        self._data_replay_finished = False

        self._adjustment_strategy = 'relax'
        self._relax_count = 0
        self._tighten_count = 0

        self._callbacks: List[Callable[[str, Any], None]] = []

        self._running = False
        self._stop_event = threading.Event()

        self._portfolio = None
        self._tracker = None

        self._realtime_taste = None
        self._init_realtime_taste()

        self._initialized = True

    def _init_realtime_taste(self):
        """初始化实时舌识"""
        try:
            from deva.naja.senses.realtime_taste import RealtimeTaste
            self._realtime_taste = RealtimeTaste()
            log.info(f"[BanditTuner] RealtimeTaste 初始化完成")
        except Exception as e:
            log.warning(f"[BanditTuner] RealtimeTaste 初始化失败: {e}")
            self._realtime_taste = None

    def register_callback(self, callback: Callable[[str, Any], None]):
        self._callbacks.append(callback)

    def _emit(self, event: str, data: Any):
        for cb in self._callbacks:
            try:
                cb(event, data)
            except Exception as e:
                log.warning(f"[BanditTuner] 回调失败: {e}")

    def start(self):
        """启动调参器"""
        self._running = True
        self._stop_event.clear()
        self._init_portfolio()
        log.info(f"[BanditTuner] 启动，当前参数: {self._current_params}")
        self._emit('started', self._current_params)

    def _init_portfolio(self):
        """初始化虚拟持仓组合"""
        try:
            self._portfolio = SR('virtual_portfolio')
            self._tracker = SR('bandit_tracker')

            def on_tuner_position_closed(position_id: str, position, reason: str):
                if self._tracker and self._running:
                    self._tracker.on_position_closed(
                        strategy_id=position.strategy_id,
                        position_id=position_id,
                        entry_price=position.entry_price,
                        exit_price=position.exit_price,
                        open_timestamp=position.entry_time,
                        stock_code=position.stock_code,
                        stock_name=position.stock_name,
                        close_reason=reason,
                        signal_confidence=position.signal_confidence,
                    )
                self._sync_close_to_taste(position.stock_code)

            self._portfolio.register_close_callback(on_tuner_position_closed)
            log.info(f"[BanditTuner] VirtualPortfolio 初始化完成，close_callback 已注册")
        except Exception as e:
            log.error(f"[BanditTuner] VirtualPortfolio 初始化失败: {e}")

    def _get_portfolio(self):
        """获取或初始化 Portfolio"""
        if self._portfolio is None:
            self._init_portfolio()
        return self._portfolio

    def stop(self):
        """停止调参器"""
        self._running = False
        self._stop_event.set()
        log.info(f"[BanditTuner] 停止")
        self._emit('stopped', self._best_result)

    def set_initial_params(self, params: Dict[str, float]):
        """设置初始参数"""
        self._current_params = params.copy()
        self._apply_params_to_systems()
        log.info(f"[BanditTuner] 设置初始参数: {params}")

    def _apply_params_to_systems(self):
        """应用当前参数到各个系统"""
        try:
            self._apply_confidence_threshold(self._current_params['min_confidence'])
        except Exception as e:
            log.warning(f"[BanditTuner] 应用 min_confidence 失败: {e}")

    def _apply_confidence_threshold(self, threshold: float):
        """应用置信度阈值到信号监听器"""
        try:
            listener = SR('signal_listener')
            if listener:
                listener._min_confidence = threshold
                log.info(f"[BanditTuner] 调整 min_confidence -> {threshold}")
        except Exception as e:
            log.warning(f"[BanditTuner] 无法调整置信度阈值: {e}")

    def on_signal(self, result: Any):
        """收到信号时调用 - 使用 VirtualPortfolio 真实开仓"""
        if not self._running:
            return

        stock_code = ""
        price = 0
        strategy_name = ""

        if hasattr(result, 'output_full') and result.output_full:
            output = result.output_full
            stock_code = output.get('stock_code', output.get('code', ''))
            price = output.get('price', 0)
            strategy_name = output.get('strategy_name', 'unknown')
        elif hasattr(result, 'strategy_id'):
            stock_code = result.strategy_id

        if not stock_code or price <= 0:
            return

        portfolio = self._get_portfolio()
        if not portfolio:
            log.warning(f"[BanditTuner] Portfolio 未初始化")
            return

        for pos in portfolio.get_all_positions():
            if pos.stock_code == stock_code and pos.status == "OPEN":
                log.debug(f"[BanditTuner] 已有持仓，跳过: {stock_code}")
                return

        stop_loss_pct = self._current_params['stop_loss_pct']
        take_profit_pct = self._current_params['take_profit_pct']
        position_size_pct = self._current_params['position_size_pct']

        position_value = portfolio._total_capital * (position_size_pct / 100.0)

        position = portfolio.open_position(
            strategy_id=result.strategy_id if hasattr(result, 'strategy_id') else 'tuner',
            strategy_name=strategy_name,
            stock_code=stock_code,
            stock_name=stock_code,
            price=price,
            quantity=0,
            amount=position_value,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
        )

        if position:
            log.info(f"[BanditTuner] 🎯 开仓: {stock_code} @ {price}, 数量={position.quantity:.2f}, 止损={stop_loss_pct}%, 止盈={take_profit_pct}%")
            self._sync_position_to_taste(position)
        else:
            log.debug(f"[BanditTuner] 开仓失败或资金不足: {stock_code}")

        self._emit('signal_collected', {'stock_code': stock_code, 'price': price})

    def on_price_update(self, stock_code: str, current_price: float):
        """收到价格更新时调用 - 更新 VirtualPortfolio 持仓"""
        if not self._running:
            return

        portfolio = self._get_portfolio()
        if not portfolio:
            log.warning(f"[BanditTuner] Portfolio 未初始化")
            return

        with portfolio._lock:
            matching_positions = [(pos_id, pos) for pos_id, pos in portfolio._positions.items()
                                  if pos.stock_code == stock_code and pos.status == "OPEN"]

            if matching_positions:
                log.info(f"[BanditTuner] 📈 价格更新: {stock_code} {matching_positions[0][1].current_price} -> {current_price}, 止损={matching_positions[0][1].stop_loss:.2f}, 止盈={matching_positions[0][1].take_profit:.2f}")

        closed_positions = portfolio.update_price(stock_code, current_price)

        if self._realtime_taste:
            taste_signal = self._realtime_taste.taste_position(stock_code, current_price)
            if taste_signal and taste_signal.should_adjust:
                log.info(f"[BanditTuner] 🍈 舌识建议调整: {taste_signal.adjust_reason}, floating_pnl={taste_signal.floating_pnl:.2%}, freshness={taste_signal.freshness:.2%}")

        for closed in closed_positions:
            pnl = closed.profit_loss
            return_pct = closed.return_pct
            close_reason = closed.close_reason
            log.info(f"[BanditTuner] 📤 平仓: {closed.stock_code} @ {closed.exit_price:.2f}, 原因={close_reason}, 盈亏={pnl:.2f} ({return_pct:.2f}%)")

    def on_data_replay_finished(self):
        """数据回放结束时调用"""
        if not self._running:
            return

        portfolio = self._get_portfolio()
        if portfolio:
            positions = portfolio.get_all_positions(status="OPEN")
            if positions:
                log.info(f"[BanditTuner] 数据回放结束，还有 {len(positions)} 个持仓未平")
                for pos in positions:
                    portfolio.close_position(pos.position_id, pos.current_price, "TIME_UP")
                    log.info(f"[BanditTuner] 强制平仓: {pos.stock_code} @ {pos.current_price:.2f}")

        self._data_replay_finished = True
        self._evaluate_and_adjust()

    def _evaluate_and_adjust(self):
        """评估当前参数效果 - 基于 VirtualPortfolio 真实交易结果"""
        portfolio = self._get_portfolio()
        if not portfolio:
            log.warning("[BanditTuner] Portfolio 未初始化，无法评估")
            self._decide_adjustment_direction(None)
            return

        closed_trades = []
        all_positions = portfolio.get_all_positions()
        for pos in all_positions:
            if pos.status == "CLOSED" and pos.exit_price > 0:
                closed_trades.append(pos)

        if not closed_trades:
            log.info(f"[BanditTuner] 无平仓记录，继续等待...")
            self._decide_adjustment_direction(None)
            return

        total_pnl = sum(t.profit_loss for t in closed_trades)
        total_return_pct = total_pnl / 1000000.0 * 100

        winning_trades = [t for t in closed_trades if t.profit_loss > 0]
        losing_trades = [t for t in closed_trades if t.profit_loss <= 0]

        win_rate = len(winning_trades) / len(closed_trades) * 100 if closed_trades else 0

        avg_win = sum(t.profit_loss for t in winning_trades) / len(winning_trades) if winning_trades else 0
        avg_loss = abs(sum(t.profit_loss for t in losing_trades) / len(losing_trades)) if losing_trades else 1
        profit_factor = (avg_win * len(winning_trades)) / (avg_loss * len(losing_trades)) if losing_trades and avg_loss > 0 else 0

        result = TuningResult(
            params=self._current_params.copy(),
            total_return=total_return_pct,
            sharpe_ratio=total_return_pct / 10,
            max_drawdown=0.0,
            win_rate=win_rate,
            profit_factor=profit_factor,
            total_trades=len(closed_trades),
            winning_trades=len(winning_trades),
            losing_trades=len(losing_trades),
            signal_count=len(closed_trades),
            timestamp=time.time(),
        )

        self._tuning_history.append(result)

        log.info(f"[BanditTuner] 评估结果: 收益={total_return_pct:.2f}%, 交易数={len(closed_trades)}, 胜率={win_rate:.1f}%, 盈亏比={profit_factor:.2f}")

        if self._best_result is None or result.get_score() > self._best_result.get_score():
            self._best_result = result
            self._best_params = self._current_params.copy()
            log.info(f"[BanditTuner] 🏆 新最优! 得分={result.get_score():.4f}")
            self._emit('new_best', result)
        else:
            log.info(f"[BanditTuner] 当前得分={result.get_score():.4f}, 最优={self._best_result.get_score():.4f}")

        self._decide_adjustment_direction(result)

    def _decide_adjustment_direction(self, result: TuningResult):
        """根据评估结果决定调整方向"""
        if result is None or result.total_return <= 0:
            log.info(f"[BanditTuner] 收益为负或无交易，放宽参数...")
            self._relax_params()
        else:
            log.info(f"[BanditTuner] 收益为正，尝试收紧参数看能否更好...")
            self._tighten_params()

        self._emit('adjustment_decided', {
            'direction': 'tighten' if result and result.total_return > 0 else 'relax',
            'result': result.to_dict() if result else {}
        })

    def _sync_position_to_taste(self, position):
        """同步持仓到 RealtimeTaste"""
        if self._realtime_taste and position:
            try:
                self._realtime_taste.register_position(
                    symbol=position.stock_code,
                    entry_price=position.entry_price,
                    quantity=int(position.quantity),
                    entry_time=position.entry_time
                )
                log.debug(f"[BanditTuner] 同步持仓到 RealtimeTaste: {position.stock_code}")
            except Exception as e:
                log.warning(f"[BanditTuner] 同步持仓到 RealtimeTaste 失败: {e}")

    def _sync_close_to_taste(self, stock_code: str):
        """同步平仓到 RealtimeTaste"""
        if self._realtime_taste:
            try:
                self._realtime_taste.close_position(stock_code)
                log.debug(f"[BanditTuner] 同步平仓到 RealtimeTaste: {stock_code}")
            except Exception as e:
                log.warning(f"[BanditTuner] 同步平仓到 RealtimeTaste 失败: {e}")

    def _tighten_params(self):
        """收紧参数"""
        self._tighten_count += 1
        current_conf = self._current_params['min_confidence']

        new_conf = min(0.6, current_conf + 0.05)
        self._current_params['min_confidence'] = new_conf
        log.info(f"[BanditTuner] 收紧参数: min_confidence -> {new_conf}")
        self._apply_params_to_systems()

    def _relax_params(self):
        """放宽参数"""
        self._relax_count += 1
        current_conf = self._current_params['min_confidence']

        new_conf = max(0.1, current_conf - 0.05)
        self._current_params['min_confidence'] = new_conf
        log.info(f"[BanditTuner] 放宽参数: min_confidence -> {new_conf}")
        self._apply_params_to_systems()

    def get_best_params(self) -> Optional[Dict[str, Any]]:
        return self._best_params

    def get_best_result(self) -> Optional[TuningResult]:
        return self._best_result

    def get_current_params(self) -> Dict[str, Any]:
        return self._current_params.copy()

    def get_status(self) -> dict:
        portfolio = self._get_portfolio()
        open_positions = 0
        if portfolio:
            open_positions = len(portfolio.get_all_positions(status="OPEN"))
        return {
            "running": self._running,
            "phase": self._phase,
            "current_params": self._current_params,
            "best_params": self._best_params,
            "open_positions": open_positions,
            "tuning_history_size": len(self._tuning_history),
            "relax_count": self._relax_count,
            "tighten_count": self._tighten_count,
            "realtime_taste_enabled": self._realtime_taste is not None,
        }


_tuner: Optional[BanditTuner] = None
_tuner_lock = threading.Lock()


def get_bandit_tuner() -> BanditTuner:
    from deva.naja.register import SR
    return SR('bandit_tuner')
