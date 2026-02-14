#!/usr/bin/env python3
"""Log watchdog demo for deva.

Reads a growing text log file and emits alerts when ERROR/WARNING frequency
exceeds configured thresholds within a rolling time window.
"""

import argparse
import re
import time
from collections import deque

from deva import Deva, from_textfile, log, warn


LEVEL_PATTERN = re.compile(r"\b(ERROR|WARN|WARNING|CRITICAL)\b", re.IGNORECASE)


class AlertPolicy:
    """Rolling-window alert policy with cooldown to avoid alert storms."""

    def __init__(self, window_seconds=60, error_threshold=3, warning_threshold=8, cooldown_seconds=30):
        self.window_seconds = window_seconds
        self.error_threshold = error_threshold
        self.warning_threshold = warning_threshold
        self.cooldown_seconds = cooldown_seconds

        self.error_hits = deque()
        self.warning_hits = deque()
        self.last_alert_at = 0.0

    def handle(self, event):
        now = event["ts"]
        level = event["level"]

        if level in {"ERROR", "CRITICAL"}:
            self.error_hits.append(now)
        elif level == "WARNING":
            self.warning_hits.append(now)

        self._trim_old(now)
        self._maybe_alert(now, event)

    def _trim_old(self, now):
        cutoff = now - self.window_seconds
        while self.error_hits and self.error_hits[0] < cutoff:
            self.error_hits.popleft()
        while self.warning_hits and self.warning_hits[0] < cutoff:
            self.warning_hits.popleft()

    def _maybe_alert(self, now, event):
        if now - self.last_alert_at < self.cooldown_seconds:
            return

        error_count = len(self.error_hits)
        warning_count = len(self.warning_hits)

        if error_count >= self.error_threshold:
            self.last_alert_at = now
            (
                f"ALERT: ERROR spike. {error_count} errors in last "
                f"{self.window_seconds}s. Last line: {event['line']}"
            ) >> warn
        elif warning_count >= self.warning_threshold:
            self.last_alert_at = now
            (
                f"ALERT: WARNING spike. {warning_count} warnings in last "
                f"{self.window_seconds}s. Last line: {event['line']}"
            ) >> warn


def parse_line(line):
    text = line.strip()
    if not text:
        return None

    match = LEVEL_PATTERN.search(text)
    if not match:
        return None

    normalized = match.group(1).upper()
    if normalized == "WARN":
        normalized = "WARNING"

    return {
        "ts": time.time(),
        "level": normalized,
        "line": text,
    }


def main():
    parser = argparse.ArgumentParser(description="Real-time log watchdog using deva")
    parser.add_argument("--file", default="./app.log", help="log file path to watch")
    parser.add_argument("--poll", type=float, default=0.2, help="poll interval in seconds")
    parser.add_argument("--window", type=int, default=60, help="rolling window size (seconds)")
    parser.add_argument("--error-threshold", type=int, default=3, help="error count threshold")
    parser.add_argument("--warning-threshold", type=int, default=8, help="warning count threshold")
    parser.add_argument("--cooldown", type=int, default=30, help="alert cooldown in seconds")
    args = parser.parse_args()

    policy = AlertPolicy(
        window_seconds=args.window,
        error_threshold=args.error_threshold,
        warning_threshold=args.warning_threshold,
        cooldown_seconds=args.cooldown,
    )

    source = from_textfile(args.file, poll_interval=args.poll, start=True)
    events = source.map(parse_line).filter(lambda e: e is not None)

    events.map(lambda e: f"[{e['level']}] {e['line']}") >> log
    events.sink(policy.handle)

    f"watchdog started, file={args.file}" >> log
    Deva.run()


if __name__ == "__main__":
    main()
