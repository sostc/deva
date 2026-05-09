"""Multi-channel notification adapter.

This module is an infra boundary: it talks to external channels, while callers
decide what is worth sending.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

log = logging.getLogger(__name__)


@dataclass
class NotifyResult:
    channel: str
    success: bool
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class MultiChannelNotifier:
    """Send Naja summaries to DingTalk and phone/iMessage."""

    def __init__(self, min_interval_seconds: int = 60):
        self.min_interval_seconds = min_interval_seconds
        self._last_sent_at: Dict[str, float] = {}
        self._history: List[Dict[str, Any]] = []

    def send(
        self,
        title: str,
        message: str,
        channels: Optional[Iterable[str]] = None,
        force: bool = False,
    ) -> Dict[str, Any]:
        channels = list(channels or ["dingtalk", "phone"])
        results: List[NotifyResult] = []

        for channel in channels:
            normalized = str(channel).strip().lower()
            if not normalized:
                continue
            if not force and self._is_rate_limited(normalized):
                results.append(NotifyResult(normalized, False, "rate_limited"))
                continue
            if normalized in {"dingtalk", "dtalk", "ding"}:
                result = self._send_dingtalk(title, message)
            elif normalized in {"phone", "imessage", "sms", "mobile"}:
                result = self._send_phone(message)
            else:
                result = NotifyResult(normalized, False, "unsupported_channel")
            if result.success:
                self._last_sent_at[normalized] = time.time()
            results.append(result)

        record = {
            "timestamp": time.time(),
            "datetime": datetime.now().isoformat(timespec="seconds"),
            "title": title,
            "channels": channels,
            "results": [r.to_dict() for r in results],
        }
        self._history.append(record)
        self._history = self._history[-100:]
        return record

    def _is_rate_limited(self, channel: str) -> bool:
        last = self._last_sent_at.get(channel, 0)
        return bool(last and time.time() - last < self.min_interval_seconds)

    def _send_dingtalk(self, title: str, message: str) -> NotifyResult:
        try:
            from deva.endpoints import Dtalk

            md_message = f"@md@{title}|{message}"
            md_message >> Dtalk()
            return NotifyResult("dingtalk", True)
        except Exception as exc:
            log.warning("[MultiChannelNotifier] DingTalk send failed: %s", exc)
            return NotifyResult("dingtalk", False, str(exc))

    def _send_phone(self, message: str) -> NotifyResult:
        try:
            from deva.naja.strategy.daily_review import _IMESSAGE_PHONE, send_imessage

            ok = send_imessage(_IMESSAGE_PHONE, message)
            return NotifyResult("phone", bool(ok), "" if ok else "send_imessage_failed")
        except Exception as exc:
            log.warning("[MultiChannelNotifier] phone send failed: %s", exc)
            return NotifyResult("phone", False, str(exc))

    def get_recent(self, limit: int = 20) -> List[Dict[str, Any]]:
        return self._history[-limit:]


_notifier: Optional[MultiChannelNotifier] = None


def get_multi_channel_notifier() -> MultiChannelNotifier:
    global _notifier
    if _notifier is None:
        _notifier = MultiChannelNotifier()
    return _notifier
