"""
BanditNotifier - 交易信号通知器

核心功能：
1. 在产生交易信号时发送钉钉通知
2. 在持仓发生变化时发送通知
3. 维护通知历史记录

通知场景：
- 买入信号触发
- 卖出信号触发（止盈/止损/手动）
- 持仓发生变化
- 重要状态变化
"""

import logging
import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from collections import deque
from datetime import datetime

log = logging.getLogger(__name__)


@dataclass
class TradeNotification:
    """交易通知记录"""
    id: str
    timestamp: float
    notification_type: str  # "buy_signal", "sell_signal", "position_opened", "position_closed"
    title: str
    message: str
    data: Dict[str, Any] = field(default_factory=dict)
    sent: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "time_str": datetime.fromtimestamp(self.timestamp).strftime("%Y-%m-%d %H:%M:%S"),
            "type": self.notification_type,
            "title": self.title,
            "message": self.message,
            "data": self.data,
            "sent": self.sent,
        }


class BanditNotifier:
    """
    交易信号通知器

    职责：
    1. 发送钉钉通知（交易信号时）
    2. 维护最近的通知历史（默认保存 50 条）
    3. 提供通知状态查询
    """

    _instance: Optional['BanditNotifier'] = None
    _lock = None

    def __new__(cls):
        if cls._instance is None:
            import threading
            cls._lock = threading.Lock()
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, '_initialized', False):
            return
        self._notifications: deque = deque(maxlen=50)
        self._enabled = True
        self._stats = {
            "total_sent": 0,
            "total_failed": 0,
            "by_type": {},
        }
        self._last_send_time = 0
        self._min_send_interval = 60
        self._initialized = True
        log.info("[BanditNotifier] 交易通知器已初始化")

    def notify_buy_signal(
        self,
        stock_code: str,
        stock_name: str,
        price: float,
        confidence: float,
        strategy_name: str,
        reason: str = "",
    ):
        """发送买入信号通知"""
        notification = TradeNotification(
            id=f"buy_{int(time.time())}_{stock_code}",
            timestamp=time.time(),
            notification_type="buy_signal",
            title=f"📈 买入信号 | {stock_name}({stock_code})",
            message=f"""**{stock_name}** ({stock_code})

💰 价格: {price:.2f}
🎯 置信度: {confidence:.2%}
📊 策略: {strategy_name}
📝 原因: {reason or '信号触发'}
⏰ 时间: {datetime.now().strftime('%H:%M:%S')}""",
            data={
                "stock_code": stock_code,
                "stock_name": stock_name,
                "price": price,
                "confidence": confidence,
                "strategy_name": strategy_name,
                "reason": reason,
            }
        )
        self._add_and_send(notification)

    def notify_sell_signal(
        self,
        stock_code: str,
        stock_name: str,
        price: float,
        profit_pct: float,
        reason: str,
    ):
        """发送卖出信号通知"""
        emoji = "🎉" if profit_pct > 0 else "😔"
        notification = TradeNotification(
            id=f"sell_{int(time.time())}_{stock_code}",
            timestamp=time.time(),
            notification_type="sell_signal",
            title=f"{emoji} 卖出信号 | {stock_name}({stock_code})",
            message=f"""**{stock_name}** ({stock_code})

💰 卖出价格: {price:.2f}
{'📈' if profit_pct > 0 else '📉'} 收益: {profit_pct:+.2f}%
📝 原因: {reason}
⏰ 时间: {datetime.now().strftime('%H:%M:%S')}""",
            data={
                "stock_code": stock_code,
                "stock_name": stock_name,
                "price": price,
                "profit_pct": profit_pct,
                "reason": reason,
            }
        )
        self._add_and_send(notification)

    def notify_position_opened(
        self,
        position_id: str,
        stock_code: str,
        stock_name: str,
        price: float,
        amount: float,
    ):
        """发送持仓开启通知"""
        notification = TradeNotification(
            id=f"open_{position_id}",
            timestamp=time.time(),
            notification_type="position_opened",
            title=f"✅ 持仓开启 | {stock_name}",
            message=f"""**{stock_name}** ({stock_code})

💰 买入价格: {price:.2f}
💵 买入金额: {amount:,.2f}
🆔 持仓ID: {position_id}
⏰ 时间: {datetime.now().strftime('%H:%M:%S')}""",
            data={
                "position_id": position_id,
                "stock_code": stock_code,
                "stock_name": stock_name,
                "price": price,
                "amount": amount,
            }
        )
        self._add_and_send(notification)

    def notify_position_closed(
        self,
        position_id: str,
        stock_code: str,
        stock_name: str,
        open_price: float,
        close_price: float,
        profit_pct: float,
        reason: str,
    ):
        """发送持仓关闭通知"""
        emoji = "🎉" if profit_pct > 0 else "😔"
        notification = TradeNotification(
            id=f"close_{position_id}",
            timestamp=time.time(),
            notification_type="position_closed",
            title=f"{emoji} 持仓关闭 | {stock_name}",
            message=f"""**{stock_name}** ({stock_code})

📈 开仓价格: {open_price:.2f}
💰 平仓价格: {close_price:.2f}
{'📈' if profit_pct > 0 else '📉'} 收益率: {profit_pct:+.2f}
📝 平仓原因: {reason}
🆔 持仓ID: {position_id}
⏰ 时间: {datetime.now().strftime('%H:%M:%S')}""",
            data={
                "position_id": position_id,
                "stock_code": stock_code,
                "stock_name": stock_name,
                "open_price": open_price,
                "close_price": close_price,
                "profit_pct": profit_pct,
                "reason": reason,
            }
        )
        self._add_and_send(notification)

    def _add_and_send(self, notification: TradeNotification):
        """添加并发送通知"""
        self._notifications.append(notification)
        self._send_to_dtalk(notification)

    def _send_to_dtalk(self, notification: TradeNotification):
        """发送到钉钉"""
        if not self._enabled:
            log.debug(f"[BanditNotifier] 通知已禁用，跳过发送")
            notification.sent = False
            return

        current_time = time.time()
        if current_time - self._last_send_time < self._min_send_interval:
            log.debug(f"[BanditNotifier] 发送间隔太短，跳过")
            notification.sent = False
            return

        try:
            from deva.endpoints import Dtalk

            md_message = f"@md@{notification.title}|{notification.message}"

            dtalk = Dtalk()
            md_message >> dtalk

            notification.sent = True
            self._stats["total_sent"] += 1
            self._last_send_time = current_time

            type_count = self._stats["by_type"].get(notification.notification_type, 0)
            self._stats["by_type"][notification.notification_type] = type_count + 1

            log.info(f"[BanditNotifier] 通知已发送：{notification.title}")

        except Exception as e:
            log.error(f"[BanditNotifier] 发送通知失败：{e}")
            notification.sent = False
            self._stats["total_failed"] += 1

    def get_recent_notifications(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取最近的通知"""
        notifications = list(self._notifications)[-limit:]
        return [n.to_dict() for n in notifications]

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "total_sent": self._stats["total_sent"],
            "total_failed": self._stats["total_failed"],
            "by_type": dict(self._stats["by_type"]),
            "last_send_time": datetime.fromtimestamp(self._last_send_time).strftime("%H:%M:%S") if self._last_send_time else None,
        }

    def set_enabled(self, enabled: bool):
        """设置是否启用"""
        self._enabled = enabled
        log.info(f"[BanditNotifier] 通知{'启用' if enabled else '禁用'}")


def get_bandit_notifier() -> BanditNotifier:
    """获取 BanditNotifier 单例"""
    return BanditNotifier()