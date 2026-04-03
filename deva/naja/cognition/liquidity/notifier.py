"""
LiquidityNotifier - 流动性预测通知器

核心功能：
1. 在关键节点发送钉钉通知
2. 维护最近的通知历史记录
3. 提供通知状态查询接口

通知场景：
- 创建高置信度预测（>0.7）
- 预测验证成功（置信度>0.8）
- 预测验证失败（预判错误）
- 检测到跨市场共振
- 流动性信号急剧变化
"""

import logging
import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from collections import deque
from datetime import datetime

log = logging.getLogger(__name__)


@dataclass
class LiquidityNotification:
    """流动性通知记录"""
    id: str
    timestamp: float
    notification_type: str  # "prediction_created", "prediction_confirmed", "prediction_denied", "resonance_detected", "signal_change"
    severity: str  # "high", "medium", "low"
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
            "severity": self.severity,
            "title": self.title,
            "message": self.message,
            "data": self.data,
            "sent": self.sent,
        }


class LiquidityNotifier:
    """
    流动性预测通知器

    职责：
    1. 发送钉钉通知（重大变化时）
    2. 维护最近的通知历史（默认保存 20 条）
    3. 提供通知状态查询
    """

    def __init__(self, max_history: int = 20):
        self._notifications: deque = deque(maxlen=max_history)
        self._enabled = True
        self._stats = {
            "total_sent": 0,
            "total_failed": 0,
            "by_type": {},
        }

    def send_prediction_created(
        self,
        from_market: str,
        to_market: str,
        direction: str,
        probability: float,
        source_change: float,
        verify_minutes: float,
    ):
        """
        发送预测创建通知

        Args:
            from_market: 源市场
            to_market: 目标市场
            direction: "up" 或 "down"
            probability: 置信度
            source_change: 源市场变化幅度
            verify_minutes: 验证时间（分钟）
        """
        # 只在高置信度时发送
        if probability < 0.7:
            return

        severity = "high" if probability > 0.85 else "medium"
        direction_icon = "📈" if direction == "up" else "📉"
        market_map = {
            "a_share": "A 股",
            "hk_equity": "港股",
            "us_equity": "美股",
            "us_futures": "美股期货",
            "cn_futures": "国内期货",
        }

        from_name = market_map.get(from_market, from_market)
        to_name = market_map.get(to_market, to_market)

        title = f"🔔 流动性预测 | {from_name} → {to_name}"
        message = f"""
{direction_icon} **预测方向**: {direction.upper()}
📊 **置信度**: {probability:.1%}
💹 **源市场变化**: {source_change:+.2f}%
⏰ **验证时间**: {verify_minutes:.0f}分钟后

> 系统已自动跟踪该预测，将在到期时验证
"""

        notification = LiquidityNotification(
            id=f"liq_notify_{int(time.time())}",
            timestamp=time.time(),
            notification_type="prediction_created",
            severity=severity,
            title=title,
            message=message,
            data={
                "from_market": from_market,
                "to_market": to_market,
                "direction": direction,
                "probability": probability,
                "source_change": source_change,
                "verify_minutes": verify_minutes,
            },
        )

        self._add_notification(notification)
        self._send_to_dtalk(notification)

    def send_prediction_confirmed(
        self,
        from_market: str,
        to_market: str,
        direction: str,
        probability: float,
        actual_change: float,
    ):
        """
        发送预测验证成功通知

        Args:
            from_market: 源市场
            to_market: 目标市场
            direction: 预测方向
            probability: 原预测置信度
            actual_change: 实际变化幅度
        """
        market_map = {
            "a_share": "A 股",
            "hk_equity": "港股",
            "us_equity": "美股",
        }

        from_name = market_map.get(from_market, from_market)
        to_name = market_map.get(to_market, to_market)
        direction_icon = "📈" if direction == "up" else "📉"

        title = f"✅ 预测验证成功 | {from_name} → {to_name}"
        message = f"""
{direction_icon} **预测方向**: {direction.upper()} ✓
📊 **原置信度**: {probability:.1%}
💹 **实际变化**: {actual_change:+.2f}%
🎯 **预判准确**: 市场走势符合预期

> 流动性传导模型验证有效
"""

        notification = LiquidityNotification(
            id=f"liq_notify_{int(time.time())}",
            timestamp=time.time(),
            notification_type="prediction_confirmed",
            severity="high",
            title=title,
            message=message,
            data={
                "from_market": from_market,
                "to_market": to_market,
                "direction": direction,
                "probability": probability,
                "actual_change": actual_change,
            },
        )

        self._add_notification(notification)
        self._send_to_dtalk(notification)

    def send_prediction_denied(
        self,
        from_market: str,
        to_market: str,
        direction: str,
        probability: float,
        actual_change: float,
        reason: str = "timeout",
    ):
        """
        发送预测验证失败通知

        Args:
            from_market: 源市场
            to_market: 目标市场
            direction: 预测方向
            probability: 原预测置信度
            actual_change: 实际变化幅度
            reason: 失败原因
        """
        market_map = {
            "a_share": "A 股",
            "hk_equity": "港股",
            "us_equity": "美股",
        }

        from_name = market_map.get(from_market, from_market)
        to_name = market_map.get(to_market, to_market)

        title = f"❌ 预测验证失败 | {from_name} → {to_name}"
        message = f"""
📊 **原预测**: {direction.upper()} (置信度 {probability:.1%})
💹 **实际变化**: {actual_change:+.2f}%
⚠️ **失败原因**: {reason}

> 系统将持续学习，优化模型参数
"""

        notification = LiquidityNotification(
            id=f"liq_notify_{int(time.time())}",
            timestamp=time.time(),
            notification_type="prediction_denied",
            severity="high",
            title=title,
            message=message,
            data={
                "from_market": from_market,
                "to_market": to_market,
                "direction": direction,
                "probability": probability,
                "actual_change": actual_change,
                "reason": reason,
            },
        )

        self._add_notification(notification)
        self._send_to_dtalk(notification)

    def send_resonance_detected(
        self,
        markets: List[str],
        resonance_level: str,
        confidence: float,
    ):
        """
        发送跨市场共振检测通知

        Args:
            markets: 共振市场列表
            resonance_level: 共振等级
            confidence: 置信度
        """
        if confidence < 0.7:
            return

        market_names = []
        for m in markets:
            if m == "a_share":
                market_names.append("A 股")
            elif m == "hk_equity":
                market_names.append("港股")
            elif m == "us_equity":
                market_names.append("美股")
            else:
                market_names.append(m)

        level_icon = {
            "high": "🚨",
            "medium": "⚠️",
            "low": "📊",
        }.get(resonance_level, "📊")

        title = f"{level_icon} 跨市场共振检测 | {confidence:.1%}"
        message = f"""
🌐 **共振市场**: {' → '.join(market_names)}
📊 **共振等级**: {resonance_level.upper()}
🎯 **置信度**: {confidence:.1%}

> 检测到显著的跨市场流动性联动
"""

        notification = LiquidityNotification(
            id=f"liq_notify_{int(time.time())}",
            timestamp=time.time(),
            notification_type="resonance_detected",
            severity="high" if confidence > 0.85 else "medium",
            title=title,
            message=message,
            data={
                "markets": markets,
                "resonance_level": resonance_level,
                "confidence": confidence,
            },
        )

        self._add_notification(notification)
        self._send_to_dtalk(notification)

    def send_signal_change(
        self,
        market: str,
        old_signal: float,
        new_signal: float,
        change_pct: float,
    ):
        """
        发送流动性信号急剧变化通知

        Args:
            market: 市场
            old_signal: 原信号值
            new_signal: 新信号值
            change_pct: 变化幅度
        """
        # 只在变化超过 30% 时发送
        if abs(change_pct) < 0.3:
            return

        market_map = {
            "a_share": "A 股",
            "hk_equity": "港股",
            "us_equity": "美股",
        }

        market_name = market_map.get(market, market)

        if new_signal < 0.4:
            status = "🔴 紧张"
            icon = "⚠️"
        elif new_signal > 0.7:
            status = "🟢 宽松"
            icon = "✅"
        else:
            status = "🟡 中性"
            icon = "📊"

        direction = "↑" if change_pct > 0 else "↓"

        title = f"{icon} 流动性信号大幅变化 | {market_name}"
        message = f"""
📊 **市场**: {market_name}
🎯 **当前状态**: {status} (信号值 {new_signal:.2f})
📈 **变化幅度**: {direction} {abs(change_pct):.1%}
📉 **原信号值**: {old_signal:.2f}

> 市场流动性状态发生显著变化
"""

        notification = LiquidityNotification(
            id=f"liq_notify_{int(time.time())}",
            timestamp=time.time(),
            notification_type="signal_change",
            severity="high" if abs(change_pct) > 0.5 else "medium",
            title=title,
            message=message,
            data={
                "market": market,
                "old_signal": old_signal,
                "new_signal": new_signal,
                "change_pct": change_pct,
            },
        )

        self._add_notification(notification)
        self._send_to_dtalk(notification)

    def _add_notification(self, notification: LiquidityNotification):
        """添加通知到历史记录"""
        self._notifications.appendleft(notification)

        # 更新统计
        n_type = notification.notification_type
        self._stats["by_type"][n_type] = self._stats["by_type"].get(n_type, 0) + 1

        log.info(f"[LiquidityNotifier] 添加通知：{notification.title}")

    def _send_to_dtalk(self, notification: LiquidityNotification):
        """发送到钉钉"""
        if not self._enabled:
            log.debug(f"[LiquidityNotifier] 通知已禁用，跳过发送")
            notification.sent = False
            return

        try:
            from deva.endpoints import Dtalk

            # 构建 markdown 消息
            md_message = f"@md@{notification.title}|{notification.message}"

            # 异步发送
            dtalk = Dtalk()
            md_message >> dtalk

            notification.sent = True
            self._stats["total_sent"] += 1

            log.info(f"[LiquidityNotifier] 通知已发送：{notification.title}")

        except Exception as e:
            log.error(f"[LiquidityNotifier] 发送通知失败：{e}")
            notification.sent = False
            self._stats["total_failed"] += 1

    def get_recent_notifications(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取最近的通知历史"""
        return [n.to_dict() for n in list(self._notifications)[:limit]]

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            **self._stats,
            "history_count": len(self._notifications),
            "enabled": self._enabled,
        }

    def enable(self):
        """启用通知"""
        self._enabled = True
        log.info("[LiquidityNotifier] 通知已启用")

    def disable(self):
        """禁用通知"""
        self._enabled = False
        log.info("[LiquidityNotifier] 通知已禁用")

    def is_enabled(self) -> bool:
        """是否启用"""
        return self._enabled


# 全局单例
_notifier: Optional[LiquidityNotifier] = None


def get_notifier() -> LiquidityNotifier:
    """获取全局通知器实例"""
    global _notifier
    if _notifier is None:
        _notifier = LiquidityNotifier()
    return _notifier
