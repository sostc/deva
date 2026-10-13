"""Bandit 数据新鲜度记录（进程内登记簿）

为什么需要它
------------
Bandit 页面上的数字（A股持仓现价/收益率、美股行情）都是**异步更新**的：
行情推送一到就改，停推就冻结。以前页面只显示数字本身，用户无从判断
「这个价格是刚更新的，还是半小时前的」—— 一个"看起来很新"的旧数字
比明显报错更危险。

本模块让每条数据链路都能如实回答两个问题：
    1. 最后一次更新发生在什么时候；
    2. 那一次是成功还是失败（失败的话，数据实际停留在几点）。

设计要点
--------
* **进程内单例 + 线程锁**：行情回调跑在 observer 线程、富途同步跑在
  pywebio 请求线程、UI 读取在协程里，必须并发安全。
* **不走 SingletonRegistry**：这里只是"观测埋点"，没有跨模块装配需求。
  走注册表反而会引入「谁才是权威实例」的歧义（参见 market_time_service
  别名事故：container 覆盖注册把两个不同语义的对象指向了同一个实例）。
  因此沿用模块级缓存的 get_xxx() 惯例，与 get_market_observer 一致。
* **区分「尝试」与「成功」两个时间戳**：失败时也要能说清"最后一次尝试
  是何时失败的"，而不是只剩一个越来越旧的成功时间让人误判。
* **只记事实、不做交易时段推断**：是否"陈旧"由调用方按阈值判断，
  避免非交易时段长期误报。
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Dict, Optional

# ── 数据源标识 ──────────────────────────────────────────────
# 新增链路时在这里登记，UI 与守卫都以此为准（避免各处散落裸字符串）。
SOURCE_CN_PRICE = "cn_price"      # A股行情价格更新
SOURCE_US_PRICE = "us_price"      # 美股行情价格更新
SOURCE_FUTU_SYNC = "futu_sync"    # 富途持仓同步

SOURCE_LABELS: Dict[str, str] = {
    SOURCE_CN_PRICE: "A股行情",
    SOURCE_US_PRICE: "美股行情",
    SOURCE_FUTU_SYNC: "富途持仓同步",
}

# 超过这个秒数未成功更新，徽章会提示"已 N 未更新"（纯事实陈述，非告警）
DEFAULT_STALE_SEC = 300.0


@dataclass
class Freshness:
    """单个数据源的新鲜度记录（值对象；跨线程传递请用副本）"""

    source: str
    last_attempt_ts: float = 0.0   # 最后一次尝试（无论成败）
    last_success_ts: float = 0.0   # 最后一次成功（失败不回退，用于回答"数据停在几点"）
    last_ok: Optional[bool] = None  # None=从未上报；True=成功；False=失败
    last_error: str = ""
    ok_count: int = 0
    fail_count: int = 0

    def age_seconds(self, now: Optional[float] = None) -> Optional[float]:
        """距最后一次成功更新的秒数；从未成功过返回 None。"""
        if self.last_success_ts <= 0:
            return None
        return max(0.0, (now if now is not None else time.time()) - self.last_success_ts)

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "last_attempt_ts": self.last_attempt_ts,
            "last_success_ts": self.last_success_ts,
            "last_ok": self.last_ok,
            "last_error": self.last_error,
            "ok_count": self.ok_count,
            "fail_count": self.fail_count,
        }


class FreshnessTracker:
    """进程内数据新鲜度登记簿（线程安全）"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: Dict[str, Freshness] = {}

    def record_success(self, source: str) -> Freshness:
        """记录一次成功更新，返回记录副本"""
        now = time.time()
        with self._lock:
            rec = self._items.get(source) or Freshness(source=source)
            rec.last_attempt_ts = now
            rec.last_success_ts = now
            rec.last_ok = True
            rec.last_error = ""
            rec.ok_count += 1
            self._items[source] = rec
            return replace(rec)

    def record_failure(self, source: str, error: str = "") -> Freshness:
        """记录一次失败更新。

        注意：**不回退 last_success_ts** —— 失败时页面仍需要说清
        「数据实际停留在几点」，这个时间只能来自上一次成功。
        """
        now = time.time()
        with self._lock:
            rec = self._items.get(source) or Freshness(source=source)
            rec.last_attempt_ts = now
            rec.last_ok = False
            rec.last_error = str(error or "")[:200]
            rec.fail_count += 1
            self._items[source] = rec
            return replace(rec)

    def snapshot(self, source: str) -> Freshness:
        """读取某数据源的当前状态（返回副本，避免调用方持锁外读到中间态）"""
        with self._lock:
            rec = self._items.get(source)
            return replace(rec) if rec is not None else Freshness(source=source)

    def all_snapshots(self) -> Dict[str, Freshness]:
        with self._lock:
            return {k: replace(v) for k, v in self._items.items()}

    def reset(self, source: Optional[str] = None) -> None:
        """清空记录（测试用）。不传 source 则全部清空。"""
        with self._lock:
            if source is None:
                self._items.clear()
            else:
                self._items.pop(source, None)


_tracker: Optional[FreshnessTracker] = None
_tracker_lock = threading.Lock()


def get_freshness_tracker() -> FreshnessTracker:
    """获取进程内新鲜度登记簿（模块级单例，线程安全初始化）"""
    global _tracker
    if _tracker is None:
        with _tracker_lock:
            if _tracker is None:
                _tracker = FreshnessTracker()
    return _tracker


# ── 呈现（纯函数，便于守卫直接断言）─────────────────────────


def format_ago(seconds: Optional[float]) -> str:
    """把秒数渲染成「N 秒 / N 分钟 / N.N 小时 / N.N 天」。

    刻意不含「前」字 —— 由调用方按句式拼接（「更新于 X（N 分钟前）」
    与「距上次更新已 N 分钟」对时间量词的要求不同）。
    """
    if seconds is None:
        return "-"
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds} 秒"
    if seconds < 3600:
        return f"{seconds // 60} 分钟"
    if seconds < 86400:
        return f"{seconds / 3600:.1f} 小时"
    return f"{seconds / 86400:.1f} 天"


def _fmt_clock(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%H:%M:%S")


def format_badge(
    rec: Freshness,
    label: str = "",
    now: Optional[float] = None,
    stale_sec: float = DEFAULT_STALE_SEC,
) -> str:
    """把一条新鲜度记录渲染成页面徽章（纯函数）

    四种形态互不相同，颜色/文案都可区分：
      ⚪ 无记录 —— 该链路从未上报过（可能没启动，也可能埋点没接上）
      ❌ 失败   —— 最近一次更新出错，并给出"数据实际停留在几点"
      ⚠️ 陈旧   —— 最近一次成功，但已超过 stale_sec 未再更新
      ✅ 新鲜   —— 最近一次成功且在阈值内
    """
    name = label or SOURCE_LABELS.get(rec.source, rec.source)
    base = (
        "display:inline-block;padding:2px 8px;border-radius:6px;"
        "font-size:12px;font-weight:normal;margin-left:8px;white-space:nowrap;"
    )

    if rec.last_ok is None:
        return (
            f"<span style='{base}background:#f1f5f9;border:1px solid #cbd5e1;"
            f"color:#64748b;'>⚪ {name}：尚无更新记录</span>"
        )

    if rec.last_ok is False:
        stayed = (
            f" · 数据停留在 {_fmt_clock(rec.last_success_ts)}"
            if rec.last_success_ts > 0
            else " · 从未成功过"
        )
        err = f"：{rec.last_error}" if rec.last_error else ""
        return (
            f"<span style='{base}background:#fee2e2;border:1px solid #fca5a5;"
            f"color:#991b1b;'>❌ {name} 更新失败（{_fmt_clock(rec.last_attempt_ts)}）"
            f"{err}{stayed}</span>"
        )

    age = rec.age_seconds(now)
    age_txt = format_ago(age)
    if age is not None and age > stale_sec:
        return (
            f"<span style='{base}background:#fef3c7;border:1px solid #f59e0b;"
            f"color:#92400e;'>⚠️ {name} 距上次更新已 {age_txt}"
            f"（最后 {_fmt_clock(rec.last_success_ts)}）</span>"
        )

    return (
        f"<span style='{base}background:#dcfce7;border:1px solid #86efac;"
        f"color:#166534;'>✅ {name} 更新于 {_fmt_clock(rec.last_success_ts)}"
        f"（{age_txt}前）</span>"
    )
