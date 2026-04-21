"""自适应循环控制器

将信号监听、虚拟持仓、市场观察和 Bandit 调节串联起来。
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional

from deva import NB

from .signal_listener import SignalListener, DetectedSignal
from .virtual_portfolio import VirtualPortfolio, VirtualPosition
from .market_observer import MarketDataObserver, get_market_observer
from .optimizer import get_bandit_optimizer
from deva.naja.register import SR

log = logging.getLogger(__name__)

ADAPTIVE_CONFIG_TABLE = "naja_bandit_adaptive_config"


class AdaptiveCycle:
    """自适应循环控制器
    
    串联所有组件形成完整的交易循环：
    
    信号流 → SignalListener → 识别股票
                              ↓
                          虚拟持仓 (VirtualPortfolio)
                              ↓
                    MarketDataObserver 更新价格
                              ↓
                          检查止盈止损
                              ↓
                         平仓 → Bandit 更新
                              ↓
                    BanditOptimizer 调整策略参数
    """
    
    def __init__(self, signal_listener=None, portfolio=None, market_observer=None, optimizer=None, tracker=None, runner=None):
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
        self._db = NB(ADAPTIVE_CONFIG_TABLE)
        
        # 使用依赖注入，如果没有提供则使用 SR()
        from deva.naja.register import SR
        from .market_observer import get_market_observer
        from .optimizer import get_bandit_optimizer
        
        self._signal_listener = signal_listener or SR('signal_listener')
        self._portfolio = portfolio or SR('virtual_portfolio')
        self._market_observer = market_observer or get_market_observer()
        self._optimizer = optimizer or get_bandit_optimizer()
        self._tracker = tracker or SR('bandit_tracker')
        self._runner = runner or SR('bandit_runner')
        
        self._auto_start = True
        self._auto_buy_enabled = True
        self._auto_adjust_enabled = True

        self._manas_context_cache: Optional[Dict[str, Any]] = None
        self._last_manas_update = 0.0
        self._manas_update_interval = 60.0

        self._state_restored = False

        self._load_config()
        self._setup_callbacks()

        if self._running:
            self._restore_running_state()
    
    def _restore_running_state(self):
        """恢复运行状态，重新追踪已持仓的股票"""
        if self._state_restored:
            log.debug("状态已恢复，跳过")
            return

        try:
            positions = self._portfolio.get_all_positions(status="OPEN")
            stock_codes = [pos.stock_code for pos in positions]
            if stock_codes:
                self._market_observer.track_stocks_batch(stock_codes)

            if self._signal_listener._running and not self._signal_listener._thread:
                self._signal_listener.start()
            if self._market_observer._running and not getattr(self._market_observer, '_thread', None):
                self._market_observer.start()
            if self._runner._running and not self._runner._thread:
                self._runner.start()

            self._state_restored = True
            log.info(f"✓ Bandit 恢复完成: 持仓({len(positions)})")
        except Exception as e:
            log.error(f"恢复运行状态失败: {e}")
    
    def _load_config(self):
        """加载配置"""
        try:
            config = self._db.get("adaptive_config")
            if config:
                self._auto_start = config.get("auto_start", True)
                self._auto_buy_enabled = config.get("auto_buy_enabled", True)
                self._auto_adjust_enabled = config.get("auto_adjust_enabled", True)
                
                if config.get("was_running", False) and self._auto_start:
                    self._running = True
                    log.debug("检测到上次运行状态为运行中，将自动启动")
        except Exception:
            pass
    
    def _save_config(self):
        """保存配置"""
        try:
            self._db["adaptive_config"] = {
                "auto_start": self._auto_start,
                "auto_buy_enabled": self._auto_buy_enabled,
                "auto_adjust_enabled": self._auto_adjust_enabled,
                "was_running": self._running
            }
        except Exception:
            pass

    def _get_manas_risk_context(self) -> Dict[str, Any]:
        """
        获取 Manas 的风险上下文，用于调整止盈止损

        Returns:
            {
                "risk_temperature": float,
                "timing_score": float,
                "regime_score": float,
                "harmony_strength": float,
            }
        """
        current_time = time.time()

        if (current_time - self._last_manas_update < self._manas_update_interval
                and self._manas_context_cache is not None):
            return self._manas_context_cache

        try:
            from deva.naja.attention.orchestration.trading_center import get_trading_center
            tc = get_trading_center()
            manas_engine = tc.get_attention_os().kernel.get_manas_engine()

            portfolio_state = {"position_pct": 0.0, "total_value": 100000, "cash": 30000}
            manas_output = manas_engine.compute(
                session_manager=None,
                portfolio=portfolio_state,
                scanner=None,
                bandit_tracker=None,
                macro_signal=0.5,
                narratives=[]
            )

            self._manas_context_cache = {
                "risk_temperature": manas_output.risk_temperature,
                "timing_score": manas_output.timing_score,
                "regime_score": manas_output.regime_score,
                "harmony_strength": manas_output.harmony_strength,
            }
            self._last_manas_update = current_time

            return self._manas_context_cache
        except Exception as e:
            log.debug(f"[AdaptiveCycle] 获取 Manas 上下文失败: {e}")
            return {
                "risk_temperature": 1.0,
                "timing_score": 0.5,
                "regime_score": 0.0,
                "harmony_strength": 0.5,
            }

    def _get_adaptive_stop_loss(self, base_return_pct: float = 0.0) -> tuple:
        """
        根据 Manas 风险上下文获取自适应止盈止损

        Args:
            base_return_pct: 持仓当前收益率

        Returns:
            (stop_loss_pct, take_profit_pct)
        """
        manas_context = self._get_manas_risk_context()
        risk_t = manas_context["risk_temperature"]
        timing = manas_context["timing_score"]

        base_stop_loss = -8.0
        base_take_profit = 15.0

        if risk_t > 1.3:
            stop_loss = base_stop_loss * 0.6
            take_profit = base_take_profit * 0.8
            log.info(f"[AdaptiveCycle] 高风险环境: stop_loss={stop_loss}%, take_profit={take_profit}%")
        elif risk_t > 1.5:
            stop_loss = base_stop_loss * 0.4
            take_profit = base_take_profit * 0.6
            log.warning(f"[AdaptiveCycle] 极高风险环境: stop_loss={stop_loss}%, take_profit={take_profit}%")
        elif timing < 0.4:
            stop_loss = base_stop_loss * 1.5
            take_profit = base_take_profit * 0.7
            log.info(f"[AdaptiveCycle] 时机不佳: stop_loss={stop_loss}%, take_profit={take_profit}%")
        else:
            stop_loss = base_stop_loss
            take_profit = base_take_profit

        if base_return_pct > 5.0:
            stop_loss = max(stop_loss, -10.0)

        return stop_loss, take_profit

    def _request_trading_center_approval(self, signal: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        请求 TradingCenter 对信号进行决策

        Args:
            signal: 信号字典

        Returns:
            决策结果，包含 approved, final_confidence, reasoning 等
            如果请求失败返回 None
        """
        try:
            from deva.naja.attention.orchestration.trading_center import get_trading_center
            tc = get_trading_center()
            if tc is None:
                log.warning("[AdaptiveCycle] TradingCenter 不可用")
                return None

            if not hasattr(tc, 'process_strategy_signal'):
                log.warning("[AdaptiveCycle] TradingCenter 不支持 process_strategy_signal 方法")
                return None

            decision = tc.process_strategy_signal(signal)
            return decision

        except Exception as e:
            log.warning(f"[AdaptiveCycle] 请求 TradingCenter 决策失败: {e}")
            return None

    def _setup_callbacks(self):
        """设置回调"""

        # 使用实例属性存储回调函数，避免重复注册
        if not hasattr(self, '_callbacks_registered'):
            self._callbacks_registered = False

        if self._callbacks_registered:
            log.debug("[AdaptiveCycle] 回调已注册，跳过")
            return

        def on_signal(signal: DetectedSignal):
            if self._auto_buy_enabled:
                self._on_new_signal(signal)

        self._signal_listener.register_callback(on_signal)

        def on_price_update(stock_code: str, price: float):
            log.debug(f"[AdaptiveCycle] 收到价格更新: {stock_code} @ {price}")
            self._on_price_update(stock_code, price)

        self._market_observer.register_price_callback(on_price_update)

        def on_position_close(position_id: str, position: VirtualPosition, reason: str):
            self._on_position_closed(position_id, position, reason)

        self._portfolio.register_close_callback(on_position_close)

        self._callbacks_registered = True
        log.debug("[AdaptiveCycle] 回调注册完成")
    
    def _on_new_signal(self, signal: DetectedSignal):
        """处理新信号"""
        log.debug(f"[AdaptiveCycle] 收到信号: {signal.stock_code} {signal.stock_name} 价格={signal.price} 置信度={signal.confidence}")

        signal_type_upper = signal.signal_type.upper()
        is_buy_signal = "BUY" in signal_type_upper or "买入" in signal_type_upper

        if not is_buy_signal:
            log.debug(f"[AdaptiveCycle] 信号类型不支持: {signal.signal_type}")
            return

        if signal.price <= 0:
            log.warning(f"[AdaptiveCycle] 信号价格无效: {signal.stock_code}")
            return

        positions = self._portfolio.get_positions_by_stock(signal.stock_code)
        if positions:
            log.debug(f"[AdaptiveCycle] 股票已有持仓，跳过: {signal.stock_code}")
            return

        signal_dict = {
            'strategy_id': signal.strategy_id,
            'strategy_name': signal.strategy_name,
            'stock_code': signal.stock_code,
            'stock_name': signal.stock_name,
            'signal_type': signal.signal_type,
            'price': signal.price,
            'confidence': signal.confidence,
            'timestamp': signal.timestamp,
            'raw_data': signal.raw_data,
        }

        decision = self._request_trading_center_approval(signal_dict)
        if not decision:
            log.debug(f"[AdaptiveCycle] TradingCenter 决策请求失败，使用原始信号")
            decision = {'approved': True, 'final_confidence': signal.confidence}

        if not decision.get('approved'):
            approved_confidence = decision.get('final_confidence', 0)
            reasoning = decision.get('reasoning', [])
            log.info(f"[AdaptiveCycle] ❌ TradingCenter 否决信号: {signal.stock_code} "
                    f"(confidence={approved_confidence:.3f})")
            for r in reasoning[-3:]:
                log.info(f"[AdaptiveCycle]   决策理由: {r}")
            return

        approved_confidence = decision.get('final_confidence', 0)
        harmony = decision.get('harmony_strength', 0.5)
        manas_score = decision.get('manas_score', 0.5)
        awakening = decision.get('awakening_level', 'dormant')
        log.info(f"[AdaptiveCycle] ✅ TradingCenter 批准信号: {signal.stock_code} "
                f"(confidence={approved_confidence:.3f}, harmony={harmony:.3f}, "
                f"manas={manas_score:.3f}, awakening={awakening})")

        log.info(f"[AdaptiveCycle] 准备创建持仓: {signal.stock_code} @ {signal.price}")

        stop_loss_pct, take_profit_pct = self._get_adaptive_stop_loss()
        log.info(f"[AdaptiveCycle] 自适应止盈止损: stop_loss={stop_loss_pct}%, take_profit={take_profit_pct}%")

        position = self._portfolio.open_position(
            strategy_id=signal.strategy_id,
            strategy_name=signal.strategy_name,
            stock_code=signal.stock_code,
            stock_name=signal.stock_name,
            price=signal.price,
            amount=10000,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
            market_time=signal.market_time,
            signal_confidence=signal.confidence,
        )
        
        if position:
            log.info(f"[AdaptiveCycle] 🎉 持仓创建成功! ID={position.position_id} {signal.stock_name}({signal.stock_code}) @ {signal.price}")
            self._market_observer.track_stock(signal.stock_code)

            try:
                from deva.naja.bandit.notifier import get_bandit_notifier
                notifier = get_bandit_notifier()
                notifier.notify_position_opened(
                    position_id=position.position_id,
                    stock_code=signal.stock_code,
                    stock_name=signal.stock_name,
                    price=signal.price,
                    amount=10000,
                )
                notifier.notify_buy_signal(
                    stock_code=signal.stock_code,
                    stock_name=signal.stock_name,
                    price=signal.price,
                    confidence=signal.confidence,
                    strategy_name=signal.strategy_name,
                    reason=f"信号触发: {signal.signal_type}",
                )
            except Exception as e:
                log.warning(f"[AdaptiveCycle] 发送交易通知失败: {e}")

            try:
                from deva.naja.state.snapshot import record_bandit_decision
                record_bandit_decision(
                    action="BUY",
                    symbol=signal.stock_code,
                    price=signal.price,
                    confidence=signal.confidence,
                    quantity=10000,
                    reason=f"信号触发: {signal.signal_type} from {signal.strategy_name}"
                )
            except Exception as e:
                log.debug(f"记录Bandit决策快照失败: {e}")

            self._optimizer.select_strategy(
                available_strategies=[signal.strategy_id],
                context={"stock_code": signal.stock_code, "price": signal.price}
            )

            log.info(f"[AdaptiveCycle] ✅ 自适应循环: 创建虚拟持仓 {signal.stock_name}({signal.stock_code}) @ {signal.price}")
        else:
            log.error(f"[AdaptiveCycle] ❌ 持仓创建失败: {signal.stock_code}")
    
    def _on_price_update(self, stock_code: str, price: float):
        """处理价格更新"""
        log.debug(f"[AdaptiveCycle] 📈 收到价格更新: {stock_code} @ {price}")
        
        closed = self._portfolio.update_price(stock_code, price)
        log.debug(f"[AdaptiveCycle] 📊 止盈止损检查完成，平仓数量: {len(closed)}")
        
        for close_info in closed:
            log.debug(f"[AdaptiveCycle] 💰 触发止盈止损平仓 {stock_code} @ {price}")
    
    def _on_position_closed(self, position_id: str, position: VirtualPosition, reason: str):
        """处理持仓平仓"""
        result = self._tracker.on_position_closed(
            strategy_id=position.strategy_id,
            position_id=position_id,
            entry_price=position.entry_price,
            exit_price=position.current_price,
            open_timestamp=position.entry_time,
            trigger_adjust=self._auto_adjust_enabled,
            stock_code=position.stock_code,
            stock_name=position.stock_name,
            close_reason=reason,
            signal_confidence=getattr(position, 'signal_confidence', 0.5),
        )
        
        log.info(f"自适应循环: 平仓 {position.stock_name} 收益={position.return_pct:.2f}% "
                f"原因={reason} Bandit奖励={result.get('reward', 0):.2f}")

        try:
            from deva.naja.bandit.notifier import get_bandit_notifier
            notifier = get_bandit_notifier()
            notifier.notify_position_closed(
                position_id=position_id,
                stock_code=position.stock_code,
                stock_name=position.stock_name,
                open_price=position.entry_price,
                close_price=position.current_price,
                profit_pct=position.return_pct,
                reason=reason,
            )
        except Exception as e:
            log.warning(f"[AdaptiveCycle] 发送平仓通知失败: {e}")

        try:
            from deva.naja.state.snapshot import record_bandit_decision
            record_bandit_decision(
                action="SELL",
                symbol=position.stock_code,
                price=position.current_price,
                confidence=getattr(position, 'signal_confidence', 0.5),
                quantity=position.quantity,
                reason=f"平仓: {reason}, 收益率={position.return_pct:.2f}%"
            )
        except Exception as e:
            log.debug(f"记录Bandit决策快照失败: {e}")

        self._optimizer.update_reward(position.strategy_id, result.get('reward', position.return_pct))
    
    def start(self):
        """启动自适应循环"""
        if self._running:
            log.warning("AdaptiveCycle 已在运行")
            return

        self._running = True
        self._save_config()  # 保存运行状态

        # 重新设置回调（确保 MarketObserver 的回调已注册）
        self._setup_callbacks()

        self._signal_listener.start()
        self._market_observer.start()

        log.info("自适应循环已启动")
    
    def stop(self):
        """停止自适应循环"""
        if not self._running:
            return
        
        self._running = False
        self._save_config()  # 保存运行状态
        
        self._signal_listener.stop()
        self._market_observer.stop()
        
        log.info("自适应循环已停止")
    
    def run_once(self) -> dict:
        """手动运行一次"""
        results = {
            "signals": [],
            "prices": [],
            "bandit": {}
        }
        
        results["signals"] = self._signal_listener.get_status()
        results["prices"] = self._market_observer.get_status()
        
        try:
            results["bandit"] = self._optimizer.review_and_adjust()
        except Exception as e:
            results["bandit"] = {"error": str(e)}
        
        return results
    
    def get_status(self) -> dict:
        """获取状态"""
        return {
            "running": self._running,
            "auto_buy_enabled": self._auto_buy_enabled,
            "auto_adjust_enabled": self._auto_adjust_enabled,
            "signal_listener": self._signal_listener.get_status(),
            "market_observer": self._market_observer.get_status(),
            "portfolio": self._portfolio.get_summary(),
        }
    
    def get_positions(self) -> List[dict]:
        """获取当前持仓"""
        positions = self._portfolio.get_all_positions(status="OPEN")
        return [
            {
                "position_id": p.position_id,
                "strategy_name": p.strategy_name,
                "stock_code": p.stock_code,
                "stock_name": p.stock_name,
                "entry_price": p.entry_price,
                "current_price": p.current_price,
                "quantity": p.quantity,
                "return_pct": p.return_pct,
                "profit_loss": p.profit_loss,
                "holding_seconds": p.holding_seconds,
                "stop_loss": p.stop_loss,
                "take_profit": p.take_profit,
                "market_time": p.market_time,
                "entry_time": p.entry_time
            }
            for p in positions
        ]
    
    def get_history(self, limit: int = 50) -> List[dict]:
        """获取历史持仓"""
        positions = self._portfolio.get_all_positions(status="CLOSED")
        positions.sort(key=lambda x: x.exit_time or x.last_update_time, reverse=True)
        return [
            {
                "position_id": p.position_id,
                "strategy_name": p.strategy_name,
                "stock_code": p.stock_code,
                "stock_name": p.stock_name,
                "entry_price": p.entry_price,
                "exit_price": p.exit_price,
                "current_price": p.current_price,
                "quantity": p.quantity,
                "return_pct": p.return_pct,
                "profit_loss": p.profit_loss,
                "holding_seconds": p.holding_seconds,
                "entry_time": p.entry_time,
                "exit_time": p.exit_time,
                "last_update_time": p.last_update_time,
                "close_reason": p.close_reason,  # 平仓原因
                "market_time": p.market_time
            }
            for p in positions[:limit]
        ]
    
    def set_auto_buy(self, enabled: bool):
        """设置自动买入"""
        self._auto_buy_enabled = enabled
        self._save_config()
    
    def set_auto_adjust(self, enabled: bool):
        """设置自动调节"""
        self._auto_adjust_enabled = enabled
        self._save_config()
    
    def close_position(self, position_id: str, reason: str = "MANUAL") -> bool:
        """手动平仓"""
        position = self._portfolio.get_position(position_id)
        if not position:
            return False
        
        return self._portfolio.close_position(position_id, position.current_price, reason) is not None

