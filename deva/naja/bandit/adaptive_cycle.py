"""自适应循环控制器

将信号监听、虚拟持仓、市场观察和 Bandit 调节串联起来。
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional

from deva import NB

from .signal_listener import SignalListener, DetectedSignal, get_signal_listener
from .virtual_portfolio import VirtualPortfolio, VirtualPosition, get_virtual_portfolio
from .market_observer import MarketDataObserver, get_market_observer
from .optimizer import get_bandit_optimizer
from .tracker import get_bandit_tracker
from .runner import get_bandit_runner

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
    
    def __init__(self):
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
        self._db = NB(ADAPTIVE_CONFIG_TABLE)
        
        self._signal_listener = get_signal_listener()
        self._portfolio = get_virtual_portfolio()
        self._market_observer = get_market_observer()
        self._optimizer = get_bandit_optimizer()
        self._tracker = get_bandit_tracker()
        self._runner = get_bandit_runner()
        
        self._auto_start = True
        self._auto_buy_enabled = True
        self._auto_adjust_enabled = True
        
        self._load_config()
        self._setup_callbacks()
        
        if self._running:
            self._restore_running_state()
    
    def _restore_running_state(self):
        """恢复运行状态，重新追踪已持仓的股票"""
        try:
            # 恢复持仓追踪
            positions = self._portfolio.get_all_positions(status="OPEN")
            for pos in positions:
                self._market_observer.track_stock(pos.stock_code)

            # 启动各组件（如果之前是运行状态）
            if self._signal_listener._running:
                self._signal_listener.start()
            if self._market_observer._running:
                self._market_observer.start()
            if self._runner._running:
                self._runner.start()

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

        log.info(f"[AdaptiveCycle] 准备创建持仓: {signal.stock_code} @ {signal.price}")

        position = self._portfolio.open_position(
            strategy_id=signal.strategy_id,
            strategy_name=signal.strategy_name,
            stock_code=signal.stock_code,
            stock_name=signal.stock_name,
            price=signal.price,
            amount=10000,
            stop_loss_pct=-5.0,
            take_profit_pct=10.0,
            market_time=signal.market_time
        )
        
        if position:
            log.info(f"[AdaptiveCycle] 🎉 持仓创建成功! ID={position.position_id} {signal.stock_name}({signal.stock_code}) @ {signal.price}")
            self._market_observer.track_stock(signal.stock_code)
            
            self._optimizer.select_strategy(
                available_strategies=[signal.strategy_id],
                context={"stock_code": signal.stock_code, "price": signal.price}
            )
            
            log.info(f"[AdaptiveCycle] ✅ 自适应循环: 创建虚拟持仓 {signal.stock_name}({signal.stock_code}) @ {signal.price}")
        else:
            log.error(f"[AdaptiveCycle] ❌ 持仓创建失败: {signal.stock_code}")
    
    def _on_price_update(self, stock_code: str, price: float):
        """处理价格更新"""
        log.info(f"[AdaptiveCycle] 📈 收到价格更新: {stock_code} @ {price}")
        
        closed = self._portfolio.update_price(stock_code, price)
        log.info(f"[AdaptiveCycle] 📊 止盈止损检查完成，平仓数量: {len(closed)}")
        
        for close_info in closed:
            log.info(f"[AdaptiveCycle] 💰 触发止盈止损平仓 {stock_code} @ {price}")
    
    def _on_position_closed(self, position_id: str, position: VirtualPosition, reason: str):
        """处理持仓平仓"""
        result = self._tracker.on_position_closed(
            strategy_id=position.strategy_id,
            position_id=position_id,
            entry_price=position.entry_price,
            exit_price=position.current_price,
            open_timestamp=position.entry_time,
            trigger_adjust=self._auto_adjust_enabled
        )
        
        log.info(f"自适应循环: 平仓 {position.stock_name} 收益={position.return_pct:.2f}% "
                f"原因={reason} Bandit奖励={result.get('reward', 0):.2f}")
        
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


_cycle: Optional[AdaptiveCycle] = None
_cycle_lock = threading.Lock()


def get_adaptive_cycle() -> AdaptiveCycle:
    global _cycle
    if _cycle is None:
        with _cycle_lock:
            if _cycle is None:
                _cycle = AdaptiveCycle()
    return _cycle
