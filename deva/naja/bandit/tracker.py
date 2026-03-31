"""Bandit 持仓追踪器

在持仓平仓时计算收益并触发 Bandit 更新。
与萧何 (XiaoHe) 的持仓管理集成。
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from deva import NB
from deva.naja.common.market_time import get_market_time_service

from .optimizer import get_bandit_optimizer, StrategyReward

POSITION_REWARD_TABLE = "naja_bandit_position_rewards"


def _get_liquidity_signal() -> float:
    """获取当前市场流动性信号"""
    try:
        from deva.naja.radar.global_market_scanner import get_global_market_scanner
        scanner = get_global_market_scanner()
        if scanner:
            adj = scanner.get_liquidity_adjustment("CHINA_A")
            return adj.get("adjusted_signal", 0.5) if adj else 0.5
    except Exception:
        pass
    return 0.5


def _get_volatility_signal() -> float:
    """获取当前市场波动率信号"""
    try:
        from deva.naja.attention.data.volatility_calculator import get_recent_volatility
        vol = get_recent_volatility()
        return min(vol / 30.0, 1.0) if vol else 0.5
    except Exception:
        pass
    return 0.5


@dataclass
class PositionRewardRecord:
    """持仓收益记录"""
    position_id: str
    strategy_id: str
    entry_price: float
    exit_price: float
    return_pct: float
    holding_duration: float
    reward: float
    timestamp: float = field(default_factory=time.time)


class BanditPositionTracker:
    """持仓收益追踪器

    集成到萧何的平仓流程，在持仓平仓时：
    1. 计算收益（收益率、持仓时间）
    2. 生成奖励值
    3. 调用 BanditOptimizer 更新策略统计
    4. 可选触发策略调节
    5. 记录归因数据到 Attribution 系统
    """

    def __init__(self):
        self._optimizer = get_bandit_optimizer()
        self._db = NB(POSITION_REWARD_TABLE)
        self._reward_type = "basic"
        self._enabled = True
        self._attribution_enabled = True

    def on_position_closed(
        self,
        strategy_id: str,
        position_id: str,
        entry_price: float,
        exit_price: float,
        open_timestamp: float,
        trigger_adjust: bool = True,
        stock_code: str = "",
        stock_name: str = "",
        close_reason: str = "",
        signal_confidence: float = 0.5,
    ) -> dict:
        """持仓平仓时调用此方法

        Args:
            strategy_id: 策略 ID
            position_id: 持仓 ID
            entry_price: 入场价格
            exit_price: 出场价格
            open_timestamp: 开仓时间戳
            trigger_adjust: 是否触发策略调节
            stock_code: 股票代码
            stock_name: 股票名称
            close_reason: 平仓原因
            signal_confidence: 信号信心度

        Returns:
            dict: 完整的处理结果
        """
        if not self._enabled:
            return {"success": False, "error": "Tracker 已禁用"}

        if entry_price <= 0 or exit_price <= 0:
            return {"success": False, "error": "价格无效"}

        mts = get_market_time_service()
        current_time = mts.get_market_time()

        return_pct = (exit_price - entry_price) / entry_price * 100
        holding_seconds = current_time - open_timestamp
        if holding_seconds < 0:
            log.warning(f"[Tracker] 持仓时间为负: holding_seconds={holding_seconds:.0f}，使用0")
            holding_seconds = 0

        reward = self._calculate_reward(return_pct, holding_seconds)

        reward_record = PositionRewardRecord(
            position_id=position_id,
            strategy_id=strategy_id,
            entry_price=entry_price,
            exit_price=exit_price,
            return_pct=return_pct,
            holding_duration=holding_seconds,
            reward=reward,
            timestamp=current_time
        )

        bandit_result = self._optimizer.update_reward(strategy_id, reward)

        self._save_reward_record(reward_record)

        attribution_result = None
        if self._attribution_enabled and stock_code:
            attribution_result = self._record_attribution(
                position_id=position_id,
                strategy_id=strategy_id,
                stock_code=stock_code,
                stock_name=stock_name,
                entry_price=entry_price,
                exit_price=exit_price,
                entry_time=open_timestamp,
                exit_time=current_time,
                holding_seconds=holding_seconds,
                close_reason=close_reason,
                signal_confidence=signal_confidence,
            )

        result = {
            "success": True,
            "position_id": position_id,
            "strategy_id": strategy_id,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "return_pct": return_pct,
            "holding_seconds": holding_seconds,
            "reward": reward,
            "bandit_update": bandit_result,
            "attribution": attribution_result,
        }

        if trigger_adjust and bandit_result.get("success"):
            adjust_result = self._optimizer.review_and_adjust(
                strategy_ids=[strategy_id],
                dry_run=False
            )
            result["adjust_result"] = adjust_result

        return result

    def _record_attribution(
        self,
        position_id: str,
        strategy_id: str,
        stock_code: str,
        stock_name: str,
        entry_price: float,
        exit_price: float,
        entry_time: float,
        exit_time: float,
        holding_seconds: float,
        close_reason: str,
        signal_confidence: float,
    ) -> Optional[dict]:
        """记录归因数据"""
        try:
            from .attribution import record_trade_attribution

            liquidity = _get_liquidity_signal()
            volatility = _get_volatility_signal()

            attr = record_trade_attribution(
                position_id=position_id,
                strategy_id=strategy_id,
                stock_code=stock_code,
                stock_name=stock_name,
                entry_price=entry_price,
                exit_price=exit_price,
                entry_time=entry_time,
                exit_time=exit_time,
                holding_seconds=holding_seconds,
                close_reason=close_reason,
                signal_confidence=signal_confidence,
                market_liquidity=liquidity,
                market_volatility=volatility,
            )
            return {"success": True, "attribution_id": attr.position_id}
        except Exception as e:
            log.warning(f"记录归因失败: {e}")
            return {"success": False, "error": str(e)}
    
    def on_position_update(
        self,
        strategy_id: str,
        position_id: str,
        current_price: float,
        open_timestamp: float,
    ) -> Optional[dict]:
        """持仓价格更新时调用（可选，用于实时监控）
        
        Args:
            strategy_id: 策略 ID
            position_id: 持仓 ID
            current_price: 当前价格
            open_timestamp: 开仓时间戳
            
        Returns:
            Optional[dict]: 如果触发止盈/止损返回动作
        """
        return None
    
    def _calculate_reward(
        self,
        return_pct: float,
        holding_seconds: float,
    ) -> float:
        """计算奖励值
        
        Args:
            return_pct: 收益率 (%)
            holding_seconds: 持仓时长 (秒)
            
        Returns:
            float: 奖励值
        """
        if self._reward_type == "basic":
            return return_pct
        
        elif self._reward_type == "sharpe_like":
            if holding_seconds <= 0:
                return return_pct
            hour_factor = holding_seconds / 3600
            return return_pct / (hour_factor ** 0.5)
        
        elif self._reward_type == "time_weighted":
            hour_factor = min(holding_seconds / 3600, 24)
            return return_pct * (1 + 0.1 * hour_factor)
        
        elif self._reward_type == "risk_adjusted":
            if return_pct > 0:
                return return_pct
            else:
                return return_pct * 1.5
        
        return return_pct
    
    def _save_reward_record(self, record: PositionRewardRecord):
        """保存收益记录"""
        try:
            key = f"{record.position_id}_{int(record.timestamp * 1000)}"
            self._db[key] = {
                "position_id": record.position_id,
                "strategy_id": record.strategy_id,
                "entry_price": record.entry_price,
                "exit_price": record.exit_price,
                "return_pct": record.return_pct,
                "holding_duration": record.holding_duration,
                "reward": record.reward,
                "timestamp": record.timestamp
            }
        except Exception:
            pass
    
    def get_position_history(
        self,
        strategy_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[dict]:
        """获取持仓收益历史
        
        Args:
            strategy_id: 策略 ID (None 表示所有)
            limit: 返回数量
            
        Returns:
            List[dict]: 收益记录列表
        """
        try:
            all_data = self._db.items()
            records = []
            
            for key, value in all_data:
                if isinstance(value, dict):
                    if strategy_id is None or value.get("strategy_id") == strategy_id:
                        records.append(value)
            
            records.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
            return records[:limit]
        except Exception:
            return []
    
    def get_strategy_summary(self, strategy_id: str) -> dict:
        """获取策略收益摘要
        
        Args:
            strategy_id: 策略 ID
            
        Returns:
            dict: 摘要信息
        """
        history = self.get_position_history(strategy_id=strategy_id, limit=100)
        
        if not history:
            return {
                "strategy_id": strategy_id,
                "total_trades": 0,
                "win_rate": 0.0,
                "avg_return": 0.0,
                "total_return": 0.0,
                "avg_holding_seconds": 0.0
            }
        
        total = len(history)
        wins = sum(1 for r in history if r.get("return_pct", 0) > 0)
        
        returns = [r.get("return_pct", 0) for r in history]
        holdings = [r.get("holding_duration", 0) for r in history]
        
        return {
            "strategy_id": strategy_id,
            "total_trades": total,
            "win_rate": wins / total * 100 if total > 0 else 0,
            "avg_return": sum(returns) / total if total > 0 else 0,
            "total_return": sum(returns),
            "avg_holding_seconds": sum(holdings) / total if total > 0 else 0,
            "best_return": max(returns) if returns else 0,
            "worst_return": min(returns) if returns else 0
        }
    
    def set_reward_type(self, reward_type: str):
        """设置奖励计算类型"""
        valid_types = {"basic", "sharpe_like", "time_weighted", "risk_adjusted"}
        if reward_type not in valid_types:
            raise ValueError(f"不支持的类型: {reward_type}, 支持: {valid_types}")
        self._reward_type = reward_type
    
    def enable(self):
        """启用追踪器"""
        self._enabled = True
    
    def disable(self):
        """禁用追踪器"""
        self._enabled = False


_tracker: Optional[BanditPositionTracker] = None
_tracker_lock = threading.Lock()


def get_bandit_tracker() -> BanditPositionTracker:
    global _tracker
    if _tracker is None:
        with _tracker_lock:
            if _tracker is None:
                _tracker = BanditPositionTracker()
    return _tracker
