"""VirtualPortfolio - Bandit系统/虚拟持仓/持仓同步

别名/关键词: 虚拟持仓、持仓同步、virtual portfolio

管理虚拟股票的买入、卖出和持仓。
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from deva import NB
from deva.naja.common.market_time import get_market_time_service

log = logging.getLogger(__name__)

VIRTUAL_PORTFOLIO_TABLE = "naja_bandit_virtual_portfolio"
UNIFIED_POSITIONS_TABLE = "naja_bandit_positions"


@dataclass
class VirtualPosition:
    """虚拟持仓"""
    position_id: str
    strategy_id: str
    strategy_name: str
    stock_code: str
    stock_name: str
    entry_price: float
    current_price: float
    quantity: float
    entry_time: float
    last_update_time: float
    status: str = "OPEN"
    stop_loss: float = 0.0
    take_profit: float = 0.0
    exit_price: float = 0.0
    exit_time: float = 0.0
    close_reason: str = ""  # 平仓原因: STOP_LOSS, TAKE_PROFIT, MANUAL, FORCE
    market_time: float = 0.0  # 行情数据时间（买入时的行情时间）
    signal_confidence: float = 0.5  # 开仓时信号的信心度

    @property
    def return_pct(self) -> float:
        if self.entry_price <= 0:
            return 0.0
        return (self.current_price - self.entry_price) / self.entry_price * 100
    
    @property
    def profit_loss(self) -> float:
        return (self.current_price - self.entry_price) * self.quantity
    
    @property
    def market_value(self) -> float:
        return self.current_price * self.quantity
    
    @property
    def holding_seconds(self) -> float:
        market_time = get_market_time_service().get_market_time()
        return market_time - self.entry_time


class VirtualPortfolio:
    """虚拟持仓组合

    管理虚拟股票的买入和卖出：
    1. 创建虚拟买入持仓
    2. 更新持仓价格
    3. 检查止盈止损
    4. 平仓处理
    - 使用统一持仓表 naja_bandit_positions
    """

    def __init__(self, account_name: str = "虚拟测试"):
        self.account_name = account_name
        self._positions: Dict[str, VirtualPosition] = {}
        self._lock = threading.RLock()

        self._db = NB(UNIFIED_POSITIONS_TABLE)

        self._total_capital = 1000000.0
        self._used_capital = 0.0
        self._max_position_pct = 0.2
        self._max_total_pct = 0.8

        self._position_callbacks: List[Callable[[str, VirtualPosition], None]] = []
        self._close_callbacks: List[Callable[[str, VirtualPosition, str], None]] = []

        self._load_positions()

    def _load_positions(self):
        """从统一数据库加载持仓"""
        try:
            from dataclasses import fields as dc_fields
            valid_fields = {f.name for f in dc_fields(VirtualPosition)}

            accounts_data = self._db.get("accounts", {})
            account_data = accounts_data.get(self.account_name, {})
            positions_data = account_data.get("positions", {})

            for pos_id, pos_data in positions_data.items():
                if isinstance(pos_data, dict):
                    filtered_data = {k: v for k, v in pos_data.items() if k in valid_fields}
                    self._positions[pos_id] = VirtualPosition(**filtered_data)

            self._used_capital = sum(
                pos.entry_price * pos.quantity
                for pos in self._positions.values()
                if pos.status == "OPEN"
            )
            self._total_capital = account_data.get("total_capital", 1000000.0)
            log.info(f"已加载 {len(self._positions)} 个虚拟持仓，已用资金: {self._used_capital:.2f}")
        except Exception as e:
            log.error(f"加载持仓失败: {e}")

    def _save_positions(self):
        """保存持仓到统一数据库"""
        try:
            accounts_data = self._db.get("accounts", {})
            if self.account_name not in accounts_data:
                accounts_data[self.account_name] = {"account_type": "virtual"}

            positions_data = {pos_id: vars(pos) for pos_id, pos in self._positions.items()}
            accounts_data[self.account_name]["positions"] = positions_data
            accounts_data[self.account_name]["total_capital"] = self._total_capital
            accounts_data[self.account_name]["used_capital"] = self._used_capital
            self._db["accounts"] = accounts_data
        except Exception as e:
            log.error(f"保存持仓失败: {e}")
    
    def register_position_callback(self, callback: Callable[[str, VirtualPosition], None]):
        """注册持仓更新回调"""
        self._position_callbacks.append(callback)
    
    def register_close_callback(self, callback: Callable[[str, VirtualPosition, str], None]):
        """注册平仓回调"""
        self._close_callbacks.append(callback)
    
    def clear_all_positions(self) -> int:
        """清空所有持仓（平仓）"""
        with self._lock:
            open_positions = [p for p in self._positions.values() if p.status == "OPEN"]
            count = 0
            for pos in open_positions:
                self.close_position(pos.position_id, reason="手动清空")
                count += 1
            log.info(f"已手动清空 {count} 个持仓")
            return count
    
    def clear_history(self) -> int:
        """清空历史持仓记录"""
        with self._lock:
            count = len(self._positions)
            self._positions.clear()
            self._used_capital = 0.0
            self._save_positions()
            log.info(f"已清空 {count} 个历史持仓记录")
            return count
    
    def open_position(
        self,
        strategy_id: str,
        strategy_name: str,
        stock_code: str,
        stock_name: str,
        price: float,
        quantity: float = 0.0,
        amount: float = 0.0,
        stop_loss_pct: float = -5.0,
        take_profit_pct: float = 10.0,
        market_time: float = 0.0,
        signal_confidence: float = 0.5,
    ) -> Optional[VirtualPosition]:
        """开仓（虚拟买入）
        
        Args:
            strategy_id: 策略 ID
            strategy_name: 策略名称
            stock_code: 股票代码
            stock_name: 股票名称
            price: 买入价格
            quantity: 买入数量
            amount: 买入金额（如果 quantity=0，则使用 amount 计算）
            stop_loss_pct: 止损百分比
            take_profit_pct: 止盈百分比
            
        Returns:
            VirtualPosition: 持仓对象
        """
        with self._lock:
            if price <= 0:
                log.warning(f"开仓价格无效: {price}")
                return None
            
            if quantity <= 0 and amount <= 0:
                log.warning("数量和金额都无效")
                return None
            
            if quantity <= 0:
                quantity = amount / price
            
            position_value = quantity * price
            used = self._used_capital + position_value
            
            if used > self._total_capital * self._max_total_pct:
                log.warning(f"总持仓超限: {used} > {self._total_capital * self._max_total_pct}")
                return None
            
            if position_value > self._total_capital * self._max_position_pct:
                log.warning(f"单笔持仓超限: {position_value} > {self._total_capital * self._max_position_pct}")
                return None
            
            position_id = f"VP_{stock_code}_{int(time.time() * 1000)}"

            mts = get_market_time_service()
            entry_time = mts.get_market_time()
            current_market_time = mts.get_market_time()

            position = VirtualPosition(
                position_id=position_id,
                strategy_id=strategy_id,
                strategy_name=strategy_name,
                stock_code=stock_code,
                stock_name=stock_name,
                entry_price=price,
                current_price=price,
                quantity=quantity,
                entry_time=entry_time,
                last_update_time=entry_time,
                status="OPEN",
                stop_loss=price * (1 + stop_loss_pct / 100),
                take_profit=price * (1 + take_profit_pct / 100),
                market_time=market_time if market_time > 0 else current_market_time,
                signal_confidence=signal_confidence,
            )
            
            self._positions[position_id] = position
            self._used_capital += position_value
            
            self._save_positions()
            
            log.info(f"虚拟开仓: {stock_name}({stock_code}) 数量={quantity:.2f} 价格={price:.2f}")
            
            return position
    
    def update_price(self, stock_code: str, current_price: float) -> List[dict]:
        """更新持仓价格

        Args:
            stock_code: 股票代码
            current_price: 当前价格

        Returns:
            List[dict]: 触发止盈止损的平仓列表
        """
        log.debug(f"[VirtualPortfolio] 📈 update_price 被调用: {stock_code} @ {current_price}")

        with self._lock:
            closed = []
            matching_positions = [(pos_id, pos) for pos_id, pos in self._positions.items()
                                  if pos.stock_code == stock_code and pos.status == "OPEN"]

            log.debug(f"[VirtualPortfolio] 🔍 找到 {len(matching_positions)} 个匹配的持仓")

            for pos_id, position in matching_positions:
                old_price = position.current_price
                position.current_price = current_price
                position.last_update_time = get_market_time_service().get_market_time()

                log.debug(f"[VirtualPortfolio] 💰 更新持仓 {pos_id}: {stock_code} {old_price} -> {current_price}")
                
                for callback in self._position_callbacks:
                    try:
                        callback(pos_id, position)
                    except Exception as e:
                        log.error(f"持仓更新回调失败: {e}")
                
                close_reason = None
                if position.stop_loss > 0 and current_price <= position.stop_loss:
                    close_reason = "STOP_LOSS"
                elif position.take_profit > 0 and current_price >= position.take_profit:
                    close_reason = "TAKE_PROFIT"
                
                if close_reason:
                    closed_pos = self.close_position(pos_id, current_price, close_reason)
                    if closed_pos:
                        closed.append(closed_pos)
            
            self._save_positions()
            return closed
    
    def close_position(
        self,
        position_id: str,
        exit_price: float,
        reason: str = "MANUAL",
    ) -> Optional[VirtualPosition]:
        """平仓

        Args:
            position_id: 持仓 ID
            exit_price: 平仓价格
            reason: 平仓原因

        Returns:
            VirtualPosition: 平仓的持仓对象
        """
        with self._lock:
            position = self._positions.get(position_id)
            if not position or position.status != "OPEN":
                return None

            position.exit_price = exit_price
            position.current_price = exit_price
            position.status = "CLOSED"

            exit_time = get_market_time_service().get_market_time()
            if exit_time < position.entry_time:
                log.warning(f"[VirtualPortfolio] 平仓时间倒置检测: exit_time({exit_time:.0f}) < entry_time({position.entry_time:.0f})，使用 entry_time + 1")
                exit_time = position.entry_time + 1
            position.exit_time = exit_time

            position.close_reason = reason

            actual_pnl = (exit_price - position.entry_price) * position.quantity

            self._used_capital -= position.entry_price * position.quantity

            for callback in self._close_callbacks:
                try:
                    callback(position_id, position, reason)
                except Exception as e:
                    log.error(f"平仓回调失败: {e}")

            log.info(f"虚拟平仓: {position.stock_name}({position.stock_code}) "
                    f"收益率={position.return_pct:.2f}% 原因={reason}")

            self._save_positions()
            return position
    
    def close_all(self, reason: str = "FORCE") -> int:
        """平所有持仓"""
        with self._lock:
            count = 0
            for pos_id in list(self._positions.keys()):
                position = self._positions.get(pos_id)
                if position and position.status == "OPEN":
                    if self.close_position(pos_id, position.current_price, reason):
                        count += 1
            return count
    
    def get_position(self, position_id: str) -> Optional[VirtualPosition]:
        """获取持仓"""
        return self._positions.get(position_id)
    
    def get_positions_by_stock(self, stock_code: str) -> List[VirtualPosition]:
        """获取股票的持仓"""
        return [p for p in self._positions.values() 
                if p.stock_code == stock_code and p.status == "OPEN"]
    
    def get_positions_by_strategy(self, strategy_id: str) -> List[VirtualPosition]:
        """获取策略的持仓"""
        return [p for p in self._positions.values() 
                if p.strategy_id == strategy_id and p.status == "OPEN"]
    
    def get_all_positions(self, status: Optional[str] = None) -> List[VirtualPosition]:
        """获取所有持仓"""
        if status is None:
            return list(self._positions.values())
        return [p for p in self._positions.values() if p.status == status]
    
    def get_summary(self) -> dict:
        """获取组合摘要"""
        positions = self.get_all_positions(status="OPEN")
        
        if not positions:
            return {
                "total_value": 0.0,
                "used_capital": 0.0,
                "available_capital": self._total_capital,
                "position_count": 0,
                "total_return": 0.0,
                "total_profit_loss": 0.0
            }
        
        total_value = sum(p.market_value for p in positions)
        total_cost = sum(p.entry_price * p.quantity for p in positions)
        total_profit_loss = sum(p.profit_loss for p in positions)
        
        return {
            "total_value": total_value,
            "used_capital": self._used_capital,
            "available_capital": self._total_capital - self._used_capital,
            "position_count": len(positions),
            "total_return": (total_value - total_cost) / total_cost * 100 if total_cost > 0 else 0,
            "total_profit_loss": total_profit_loss
        }
    
    def set_capital(self, capital: float):
        """设置总资金"""
        self._total_capital = capital
    
    def set_max_position_pct(self, pct: float):
        """设置单笔持仓比例"""
        self._max_position_pct = max(0.01, min(1.0, pct))
    
    def set_max_total_pct(self, pct: float):
        """设置总持仓比例"""
        self._max_total_pct = max(0.01, min(1.0, pct))


_portfolio: Optional[VirtualPortfolio] = None
_portfolio_lock = threading.Lock()


def get_virtual_portfolio() -> VirtualPortfolio:
    global _portfolio
    if _portfolio is None:
        with _portfolio_lock:
            if _portfolio is None:
                _portfolio = VirtualPortfolio()
    return _portfolio
