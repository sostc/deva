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

import hashlib
import logging
import time
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from collections import deque
from datetime import datetime

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
#  去重 / 限流常量
#
#  背景：Radar 每 60 秒扫描一次全球市场，同一条传播边在一段单边行情里会被
#  反复触发，产生大量"内容完全一致"的预测与验证结果。通知层若不做去重，
#  钉钉会收到几十条一字不差的消息。下列常量是最后一道兜底闸门。
# ---------------------------------------------------------------------------
DEFAULT_DEDUPE_WINDOW = 1800.0   # 同内容指纹在该窗口内只发送一次（秒）
DEFAULT_MIN_INTERVAL = 45.0      # 任意两条通知之间的最小间隔（秒），挡秒级风暴
DEFAULT_BURST_LIMIT = 4          # 同一 notification_type 在 burst 窗口内最多发送条数
DEFAULT_BURST_WINDOW = 600.0     # 突发窗口（秒）

# 不参与指纹计算的可变字段（时间戳类、倒计时类），否则同内容会因微小差异穿透去重
_FINGERPRINT_EXCLUDE = frozenset({"verify_minutes"})

# 市场显示名：静态表优先，回退到 global_market_config 的中文名，
# 避免像 "nasdaq" 这类未在表中的 market_id 直接以英文 id 出现在钉钉文案里。
_STATIC_MARKET_NAMES = {
    "a_share": "A 股",
    "hk_equity": "港股",
    "us_equity": "美股",
    "us_futures": "美股期货",
    "cn_futures": "国内期货",
}


def market_display_name(market_id: str) -> str:
    """把 market_id 转成人能读的名字"""
    if not market_id:
        return market_id
    name = _STATIC_MARKET_NAMES.get(market_id)
    if name:
        return name
    try:
        from deva.naja.cognition.liquidity.global_market_config import get_market_config

        config = get_market_config(market_id)
        if config is not None and getattr(config, "name", None):
            return config.name
    except Exception:
        pass
    return market_id


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
    suppressed: bool = False
    suppress_reason: Optional[str] = None

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
            "suppressed": self.suppressed,
            "suppress_reason": self.suppress_reason,
        }


class LiquidityNotifier:
    """
    流动性预测通知器

    职责：
    1. 发送钉钉通知（重大变化时）
    2. 维护最近的通知历史（默认保存 20 条）
    3. 提供通知状态查询
    """

    def __init__(
        self,
        max_history: int = 20,
        dedupe_window: float = DEFAULT_DEDUPE_WINDOW,
        min_interval: float = DEFAULT_MIN_INTERVAL,
        burst_limit: int = DEFAULT_BURST_LIMIT,
        burst_window: float = DEFAULT_BURST_WINDOW,
    ):
        self._notifications: deque = deque(maxlen=max_history)
        self._enabled = True
        self._stats = {
            "total_sent": 0,
            "total_failed": 0,
            "total_suppressed": 0,
            "suppressed_duplicate": 0,
            "suppressed_burst": 0,
            "suppressed_interval": 0,
            "by_type": {},
        }

        # 去重/限流状态
        self._dedupe_window = max(0.0, dedupe_window)
        self._min_interval = max(0.0, min_interval)
        self._burst_limit = max(1, burst_limit)
        self._burst_window = max(0.0, burst_window)
        self._fingerprints: Dict[str, float] = {}      # fingerprint -> 上次发送时间
        self._type_sends: Dict[str, deque] = {}        # type -> 最近发送时间队列
        self._last_send_time: float = 0.0

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
        from_name = market_display_name(from_market)
        to_name = market_display_name(to_market)

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
        from_name = market_display_name(from_market)
        to_name = market_display_name(to_market)
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
        from_name = market_display_name(from_market)
        to_name = market_display_name(to_market)

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

        market_names = [market_display_name(m) for m in markets]

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

        market_name = market_display_name(market)

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

    def _fingerprint(self, notification: "LiquidityNotification") -> str:
        """
        计算通知内容指纹

        只用"语义内容"计算：类型 + 参与决定的字段。时间戳、倒计时这类字段
        被排除，否则同一件事会因秒级差异生成不同指纹，去重形同虚设。
        """
        parts = [notification.notification_type]
        for key in sorted(notification.data):
            if key in _FINGERPRINT_EXCLUDE:
                continue
            value = notification.data[key]
            if isinstance(value, float):
                value = round(value, 3)
            elif isinstance(value, (list, tuple)):
                value = ",".join(str(v) for v in value)
            parts.append(f"{key}={value}")
        raw = "|".join(parts)
        return hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]

    def _check_send_allowed(self, notification: "LiquidityNotification") -> Tuple[bool, str]:
        """
        判断这条通知是否允许发送

        Returns:
            (是否允许, 原因)：允许时原因为空串
        """
        now = time.time()

        # 1) 同内容去重：窗口内已经发过一模一样的，直接抑制
        fingerprint = self._fingerprint(notification)
        last_sent_at = self._fingerprints.get(fingerprint)
        if last_sent_at is not None and (now - last_sent_at) < self._dedupe_window:
            return False, f"duplicate:{fingerprint}"

        # 2) 同类型突发限制：避免某一类事件在短时间内灌满钉钉
        bucket = self._type_sends.setdefault(
            notification.notification_type, deque()
        )
        while bucket and (now - bucket[0]) > self._burst_window:
            bucket.popleft()
        if len(bucket) >= self._burst_limit:
            return False, f"burst:{notification.notification_type}"

        # 3) 全局最小间隔：挡住秒级连续轰炸
        if self._last_send_time and (now - self._last_send_time) < self._min_interval:
            return False, "interval"

        return True, ""

    def _mark_sent(self, notification: "LiquidityNotification"):
        """记录发送痕迹，供后续去重/限流判定"""
        now = time.time()
        self._fingerprints[self._fingerprint(notification)] = now
        bucket = self._type_sends.setdefault(notification.notification_type, deque())
        bucket.append(now)
        self._last_send_time = now

        # 顺手清理过期的指纹记录，避免长时间运行后字典无限增长
        expired = [fp for fp, ts in self._fingerprints.items()
                   if (now - ts) > max(self._dedupe_window, 1.0)]
        for fp in expired:
            self._fingerprints.pop(fp, None)

    def _add_notification(self, notification: LiquidityNotification):
        """添加通知到历史记录"""
        self._notifications.appendleft(notification)

        # 更新统计
        n_type = notification.notification_type
        self._stats["by_type"][n_type] = self._stats["by_type"].get(n_type, 0) + 1

        log.info(f"[LiquidityNotifier] 添加通知：{notification.title}")

    def _send_to_dtalk(self, notification: LiquidityNotification):
        """发送到钉钉（带去重 + 限流）"""
        if not self._enabled:
            log.debug(f"[LiquidityNotifier] 通知已禁用，跳过发送")
            notification.sent = False
            return

        allowed, reason = self._check_send_allowed(notification)
        if not allowed:
            notification.sent = False
            notification.suppressed = True
            notification.suppress_reason = reason
            self._stats["total_suppressed"] += 1
            if reason.startswith("duplicate"):
                self._stats["suppressed_duplicate"] += 1
            elif reason.startswith("burst"):
                self._stats["suppressed_burst"] += 1
            else:
                self._stats["suppressed_interval"] += 1
            log.info(
                f"[LiquidityNotifier] 抑制重复/过密通知（{reason}）：{notification.title}"
            )
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
            self._mark_sent(notification)

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
            "limits": {
                "dedupe_window": self._dedupe_window,
                "min_interval": self._min_interval,
                "burst_limit": self._burst_limit,
                "burst_window": self._burst_window,
            },
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
