"""Fleet Registry —— 「系统里有什么在跑、什么在取外部数据」的唯一口径

============================================================================
为什么要有这一层
============================================================================

首页的「数据源」卡原来只统计 ``DatasourceManager`` 里注册的条目（5 个 yaml），
「策略」卡只统计 ``StrategyManager`` 里的（17 个 yaml）。但系统里实际存在
**多套互不知情的清单**：

    ① DatasourceManager     yaml 驱动        首页在看
    ② StrategyManager       yaml 驱动        首页在看
    ③ HotspotStrategyManager 代码驱动，14 个  汇入失败 → 首页完全看不到
    ④ 十几个散落取数器 / 常驻 runner           没有清单 → 完全黑盒

在首页 UI 里补特例是补不全的：下次新增一个取数点，没人会记得回来改首页。
所以这里把它提升成**可枚举的一等事实**——一张登记册，首页只负责渲染。

============================================================================
三条硬规则（改动本文件前先读）
============================================================================

1. **只存事实，不存判断。**
   登记册里放的是「最后一次成功 / 失败是什么时候、跑了多少次」，
   **不是**「健康 / 不健康」。陈旧度一律在**读取时**算（见 ``summarize``）。
   存结论就意味着它会过期，而过期的「健康」比诚实的「不知道」危险得多。

2. **四态不许合并。**
   ``running`` / ``stopped`` / ``unknown`` / ``skipped`` 是四件事：
       running  在跑，且近期有成功产出
       stopped  确实停了（配置关掉 / 显式停止）
       unknown  读不到状态（没探针、对象取不到、适配器抛异常）—— **绝不当 0**
       skipped  按设计这次不该跑（收盘后行情源、未达热点阈值）
   把 unknown 合并进 stopped 或 0，就是把「看不见」伪装成「没问题」。

3. **累计计数 ≠ 当前故障。**
   ``error_count`` 是历史累计，199 天前炸过一次也会一直挂着。判据一律用
   ``last_error_ts`` 的**新鲜度**（见 ``summarize`` 的 ``recent_error``）。

4. **禁止静默失败。**
   适配器抛异常必须落一条 ``state=unknown`` 的源级记录 + ``log.warning``，
   不许 ``except: pass``。热点策略曾因此消失一整天且日志零痕迹。
"""

from __future__ import annotations

import functools
import inspect
import logging
import threading
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── 分类 ────────────────────────────────────────────────────────────────────
KIND_DATASOURCE = "datasource"
KIND_STRATEGY = "strategy"

# ── 四态（不许合并，见文件头规则 2）──────────────────────────────────────────
ST_RUNNING = "running"
ST_STOPPED = "stopped"
ST_UNKNOWN = "unknown"
ST_SKIPPED = "skipped"

#: 默认「陈旧」阈值（秒）：running 但这么久没有成功产出，就算可疑。
DEFAULT_STALE_AFTER = 6 * 3600.0
#: 「近期失败」窗口（秒）：只有这个窗口内的 last_error_ts 才算当前故障。
DEFAULT_RECENT_ERROR_WINDOW = 7 * 86400.0


@dataclass
class UnitCard:
    """一个「在跑的东西」的事实卡片。

    ❗只有事实，没有结论。``state`` 描述的是「它在不在跑」，不是「它好不好」；
    「好不好」由读取方（首页卡）结合 ``last_success_ts`` / ``last_error_ts`` 判断。
    """

    unit_id: str
    kind: str                    # datasource | strategy
    name: str
    source: str                  # datasource_mgr | strategy_mgr | hotspot | runner | probe | manifest
    state: str = ST_UNKNOWN      # running | stopped | unknown | skipped
    last_success_ts: float = 0.0
    last_error_ts: float = 0.0
    error_count: int = 0         # 累计，只作参考，不作当前故障判据
    output_count: int = 0
    cadence: str = ""            # 期望节拍："每 5s" / "cron 0 9 * * *" / "按需"
    note: str = ""               # unknown / skipped 的原因，拿不到就写这里

    def to_dict(self) -> dict:
        return asdict(self)


class FleetRegistry:
    """登记册。线程安全，key 为 ``unit_id``（全局唯一，跨来源去重靠它）。"""

    def __init__(self):
        self._units: Dict[str, UnitCard] = {}
        self._lock = threading.RLock()
        self._last_refresh_ts: float = 0.0
        #: 每个采集来源自身的健康情况。适配器炸了要在这里留痕，不许静默。
        self._source_status: Dict[str, Dict[str, Any]] = {}

    # ── 写入 ────────────────────────────────────────────────────────────────

    def declare(self, card: UnitCard) -> UnitCard:
        """登记（同 id 覆盖）。"""
        if not card or not card.unit_id:
            logger.warning("[FleetRegistry] 拒绝了缺 unit_id 的登记，来源=%s",
                           getattr(card, "source", "?"))
            return card
        with self._lock:
            # ❗先取出旧对象再改，绝不自赋值：``self._units[k] = self._units[k]``
            # 会先读再写同一张卡，但 report() 的累计计数在别处引用了同一对象时
            # 覆盖会丢更新。统一走「新建卡 + 覆盖」语义，计数由 report 维护。
            self._units[card.unit_id] = card
        return card

    def declare_if_absent(self, card: UnitCard) -> UnitCard:
        """只在同 id 不存在时登记。

        用于**冗余兜底**的适配器（如热点策略 P0 已挂进 StrategyManager，
        再单独采一遍就是重复计数）——先到的赢，后来的自动让位。
        """
        if not card or not card.unit_id:
            return card
        with self._lock:
            existing = self._units.get(card.unit_id)
            if existing is not None:
                return existing
            self._units[card.unit_id] = card
            return card

    def report(self, unit_id: str, ok: bool, error: Optional[BaseException] = None,
               output: int = 0) -> None:
        """探针回调：记录一次调用结果。

        ❗探针触发本身就证明「它还活着」，所以成功和失败都把 state 置为 running
        —— 失败记在 ``last_error_ts`` 里，由读取方按新鲜度判当前故障。
        """
        if not unit_id:
            return
        now = time.time()
        with self._lock:
            card = self._units.get(unit_id)
            if card is None:
                # 探针比登记先跑（理论上不该发生）：补一张卡，不让事实丢掉
                card = UnitCard(unit_id=unit_id, kind=KIND_DATASOURCE,
                                name=unit_id, source="probe",
                                note="探针先于登记触发")
                self._units[unit_id] = card
            card.state = ST_RUNNING
            if ok:
                card.last_success_ts = now
                if output:
                    card.output_count += int(output)
            else:
                card.last_error_ts = now
                card.error_count += 1
                if error is not None:
                    card.note = f"{type(error).__name__}: {error}"[:300]

    def clear_source(self, source: str) -> int:
        """清掉某个来源的旧条目（重采集前用）。返回清掉的数量。"""
        with self._lock:
            keys = [k for k, v in self._units.items() if v.source == source]
            for k in keys:
                del self._units[k]
            return len(keys)

    def set_source_status(self, source: str, ok: bool, count: int = 0,
                          error: str = "") -> None:
        with self._lock:
            self._source_status[source] = {
                "ok": ok, "count": count, "error": error, "ts": time.time(),
            }

    # ── 读取 ────────────────────────────────────────────────────────────────

    def get(self, unit_id: str) -> Optional[UnitCard]:
        with self._lock:
            return self._units.get(unit_id)

    def snapshot(self, kind: Optional[str] = None,
                 source: Optional[str] = None) -> List[UnitCard]:
        with self._lock:
            cards = list(self._units.values())
        if kind is not None:
            cards = [c for c in cards if c.kind == kind]
        if source is not None:
            cards = [c for c in cards if c.source == source]
        # 异常在前、其次未知、再其次运行中，便于 UI 直接取前几条
        order = {ST_UNKNOWN: 0, ST_SKIPPED: 1, ST_STOPPED: 2, ST_RUNNING: 3}
        cards.sort(key=lambda c: (order.get(c.state, 9), c.name))
        return cards

    def all_sources(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            return dict(self._source_status)

    def last_refresh_ts(self) -> float:
        return self._last_refresh_ts

    def summarize(self, kind: str,
                  stale_after: float = DEFAULT_STALE_AFTER,
                  error_window: float = DEFAULT_RECENT_ERROR_WINDOW,
                  active_window: float = 86400.0) -> dict:
        """汇总某一类 —— **陈旧度在这里算，不在登记时算**（规则 1）。

        返回：
            total/running/stopped/unknown/skipped
            active                近 active_window 内有成功产出的条目数（状态量）
            by_source             各来源条数
            error_recent          近期失败（last_error_ts 在窗口内）的条目
            error_historical      只有历史失败、近期已自愈的条目
            stale                 running 但超过 stale_after 没有成功产出
            never_success         running 但从未成功过
            last_success_ts       全类最近一次成功
            last_error_ts         全类最近一次失败
            output_total          累计产出
        """
        now = time.time()
        cards = self.snapshot(kind=kind)
        out = {
            "total": len(cards),
            "running": 0,
            "stopped": 0,
            "unknown": 0,
            "skipped": 0,
            "active": 0,
            "by_source": {},
            "error_recent": [],
            "error_historical": [],
            "stale": [],
            "never_success": [],
            "last_success_ts": 0.0,
            "last_error_ts": 0.0,
            "output_total": 0,
        }
        for c in cards:
            out[c.state] = out.get(c.state, 0) + 1
            out["by_source"][c.source] = out["by_source"].get(c.source, 0) + 1
            out["output_total"] += int(c.output_count or 0)
            out["last_success_ts"] = max(out["last_success_ts"], c.last_success_ts or 0)
            out["last_error_ts"] = max(out["last_error_ts"], c.last_error_ts or 0)
            if c.last_success_ts and (now - c.last_success_ts) < active_window:
                out["active"] += 1

            recent_err = c.last_error_ts > 0 and (now - c.last_error_ts) < error_window
            if recent_err:
                out["error_recent"].append(c)
            elif c.last_error_ts > 0:
                out["error_historical"].append(c)

            if c.state == ST_RUNNING:
                if not c.last_success_ts:
                    out["never_success"].append(c)
                elif (now - c.last_success_ts) > stale_after:
                    out["stale"].append(c)
        return out


# ── 单例 ────────────────────────────────────────────────────────────────────

_registry: Optional[FleetRegistry] = None
_registry_lock = threading.Lock()


def get_fleet_registry() -> FleetRegistry:
    global _registry
    if _registry is None:
        with _registry_lock:
            if _registry is None:
                _registry = FleetRegistry()
    return _registry


# ── 探针 ────────────────────────────────────────────────────────────────────

def probe(kind: str, unit_id: str, name: str, cadence: str = "",
          source: str = "probe") -> Callable:
    """把「取数 / 执行」函数登记成受监控单元，并在每次调用时自动记成败。

    用法::

        @probe(KIND_DATASOURCE, "ds:sina_ashare", "新浪A股行情", cadence="按需")
        def _fetch_from_sina(self, codes): ...

    为什么是装饰器而不是配置文件：配置文件靠人记得回来改，装饰器挂在**真正的
    取数函数**上，漏登记的代价从「默默不见」变成「漏个装饰器」——而漏装饰器
    会被 ``verify_fleet_registry_completeness`` 扫出来。
    """

    def _deco(fn: Callable) -> Callable:
        reg = get_fleet_registry()
        reg.declare_if_absent(UnitCard(
            unit_id=unit_id, kind=kind, name=name, source=source,
            state=ST_UNKNOWN, cadence=cadence,
            note="已登记，尚未观测到调用",
        ))

        def _count(result) -> int:
            try:
                return len(result)
            except TypeError:
                return 0

        if inspect.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def _async_wrapper(*args, **kwargs):
                try:
                    result = await fn(*args, **kwargs)
                except Exception as e:
                    reg.report(unit_id, ok=False, error=e)
                    raise
                reg.report(unit_id, ok=True, output=_count(result))
                return result
            return _async_wrapper

        @functools.wraps(fn)
        def _wrapper(*args, **kwargs):
            try:
                result = fn(*args, **kwargs)
            except Exception as e:
                reg.report(unit_id, ok=False, error=e)
                raise
            reg.report(unit_id, ok=True, output=_count(result))
            return result
        return _wrapper

    return _deco


def report_manual(unit_id: str, ok: bool, error: Optional[BaseException] = None,
                  output: int = 0) -> None:
    """不便于加装饰器时的手工上报（等价于探针的 report）。"""
    get_fleet_registry().report(unit_id, ok=ok, error=error, output=output)


# ── 声明式登记（探针的兜底）────────────────────────────────────────────────

def declare_manifest_unit(*, unit_id: str, kind: str, name: str, cadence: str = "",
                          reader: Optional[Callable[[], Dict[str, Any]]] = None,
                          note: str = "", source: str = "manifest") -> UnitCard:
    """登记一个暂时没法加探针的取数点 / 运行组件。

    ``reader`` 返回可选字段（``state`` / ``last_success_ts`` / ``last_error_ts`` /
    ``output_count`` / ``error_count`` / ``note``）。reader 抛异常或返回空 →
    落 ``state=unknown`` 并把异常类型写进 ``note``，**绝不当作 0**。
    """
    reg = get_fleet_registry()
    card = UnitCard(
        unit_id=unit_id, kind=kind, name=name, source=source,
        state=ST_UNKNOWN, cadence=cadence,
        note=note or "已声明登记，无探针",
    )
    if reader is not None:
        try:
            data = reader() or {}
            if not isinstance(data, dict):
                raise TypeError(f"reader 返回了 {type(data).__name__}，期望 dict")
            for key in ("last_success_ts", "last_error_ts"):
                if key in data:
                    setattr(card, key, float(data[key] or 0))
            for key in ("output_count", "error_count"):
                if key in data:
                    setattr(card, key, int(data[key] or 0))
            if data.get("state") in (ST_RUNNING, ST_STOPPED, ST_UNKNOWN, ST_SKIPPED):
                card.state = data["state"]
            if data.get("note"):
                card.note = str(data["note"])[:300]
        except Exception as e:
            # ❗不许静默：读不到状态必须变成一张「unknown + 原因」的卡
            card.state = ST_UNKNOWN
            card.note = f"状态读取失败（{type(e).__name__}: {e}）"[:300]
            logger.warning("[FleetRegistry] 声明单元 %s 状态读取失败（%s: %s）",
                           unit_id, type(e).__name__, e)
    return reg.declare(card)


# ── 来源级适配器 ────────────────────────────────────────────────────────────

def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return default


def _safe_int(value, default: int = 0) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return default


def _ds_cadence(md) -> str:
    """把数据源元数据拼成人读的节拍。"""
    try:
        trig = str(getattr(md, "scheduler_trigger", "") or "interval")
        if trig == "cron":
            return f"cron {getattr(md, 'cron_expr', '') or '?'}".strip()
        if trig == "once":
            return f"一次 {getattr(md, 'run_at', '') or '?'}".strip()
        if trig == "event":
            return f"事件（{getattr(md, 'event_source', '') or 'log'}）"
        return f"每 {getattr(md, 'interval', 0)}s"
    except Exception:
        return ""


def collect_datasource_units(reg: Optional[FleetRegistry] = None) -> int:
    """① DatasourceManager 里注册的条目（yaml 驱动）。"""
    reg = reg or get_fleet_registry()
    source = "datasource_mgr"
    reg.clear_source(source)
    try:
        from deva.naja.datasource import get_datasource_manager
        entries = get_datasource_manager().list_all()
    except Exception as e:
        logger.warning("[FleetRegistry] 数据源体系采集失败（%s: %s）", type(e).__name__, e)
        reg.set_source_status(source, ok=False, error=f"{type(e).__name__}: {e}")
        return 0

    n = 0
    for e in entries:
        try:
            st = getattr(e, "_state", None)
            md = getattr(e, "_metadata", None)
            last_success = max(_safe_float(getattr(st, "last_data_ts", 0)),
                               _safe_float(getattr(st, "last_activity_ts", 0)))
            last_error = _safe_float(getattr(st, "last_error_ts", 0))
            skip_ts = _safe_float(getattr(st, "last_skip_ts", 0))

            state = ST_RUNNING if getattr(e, "is_running", False) else ST_STOPPED
            # 「按设计跳过」优先：最近一次结果是 skip 就说 skip，别混进 error
            if skip_ts > 0 and skip_ts >= max(last_success, last_error):
                state = ST_SKIPPED

            reg.declare(UnitCard(
                unit_id=f"ds:{getattr(e, 'id', '') or getattr(md, 'id', '')}",
                kind=KIND_DATASOURCE,
                name=getattr(md, "name", "") or getattr(e, "id", ""),
                source=source,
                state=state,
                last_success_ts=last_success,
                last_error_ts=last_error,
                error_count=_safe_int(getattr(st, "error_count", 0)),
                output_count=_safe_int(getattr(st, "total_emitted", 0)),
                cadence=_ds_cadence(md),
                note=str(getattr(st, "last_skip_reason", "") or ""),
            ))
            n += 1
        except Exception as ex:
            logger.warning("[FleetRegistry] 数据源条目 %s 采集失败（%s: %s）",
                           getattr(e, "id", "?"), type(ex).__name__, ex)
    reg.set_source_status(source, ok=True, count=n)
    return n


def collect_strategy_units(reg: Optional[FleetRegistry] = None) -> int:
    """② StrategyManager 里的条目（yaml/NB 条目 + P0 挂接进来的热点策略）。"""
    reg = reg or get_fleet_registry()
    source = "strategy_mgr"
    reg.clear_source(source)
    try:
        from deva.naja.strategy import get_strategy_manager
        entries = get_strategy_manager().list_all()
    except Exception as e:
        logger.warning("[FleetRegistry] 策略体系采集失败（%s: %s）", type(e).__name__, e)
        reg.set_source_status(source, ok=False, error=f"{type(e).__name__}: {e}")
        return 0

    n = 0
    for e in entries:
        try:
            st = getattr(e, "_state", None)
            md = getattr(e, "_metadata", None)
            last_success = max(_safe_float(getattr(st, "last_process_ts", 0)),
                               _safe_float(getattr(st, "last_activity_ts", 0)))
            reg.declare(UnitCard(
                unit_id=f"st:{getattr(e, 'id', '') or getattr(md, 'id', '')}",
                kind=KIND_STRATEGY,
                name=getattr(md, "name", "") or getattr(e, "id", ""),
                source="hotspot" if getattr(md, "source", "") == "hotspot" else source,
                state=ST_RUNNING if getattr(e, "is_running", False) else ST_STOPPED,
                last_success_ts=last_success,
                last_error_ts=_safe_float(getattr(st, "last_error_ts", 0)),
                error_count=_safe_int(getattr(st, "error_count", 0)),
                output_count=_safe_int(getattr(st, "output_count", 0)),
                cadence=str(getattr(md, "window_interval", "") or ""),
            ))
            n += 1
        except Exception as ex:
            logger.warning("[FleetRegistry] 策略条目 %s 采集失败（%s: %s）",
                           getattr(e, "id", "?"), type(ex).__name__, ex)
    reg.set_source_status(source, ok=True, count=n)
    return n


def collect_hotspot_units(reg: Optional[FleetRegistry] = None) -> int:
    """③ HotspotStrategyManager 的兜底采集。

    ❗P0 之后热点策略已经挂进 StrategyManager，这里用 ``declare_if_absent``
    做**冗余安全网**：挂接成功时自动让位（不重复计数），挂接失败时仍能看见。
    """
    reg = reg or get_fleet_registry()
    source = "hotspot"
    try:
        from deva.naja.market_hotspot.strategies.strategy_manager import get_hotspot_manager
        strategies = getattr(get_hotspot_manager(), "strategies", {}) or {}
    except Exception as e:
        logger.warning("[FleetRegistry] 热点策略采集失败（%s: %s）", type(e).__name__, e)
        reg.set_source_status(source, ok=False, error=f"{type(e).__name__}: {e}")
        return 0

    n = 0
    for sid, s in strategies.items():
        try:
            reg.declare_if_absent(UnitCard(
                unit_id=f"st:{sid}",
                kind=KIND_STRATEGY,
                name=getattr(s, "name", sid),
                source=source,
                state=ST_RUNNING if getattr(s, "is_active", False) else ST_STOPPED,
                last_success_ts=_safe_float(getattr(s, "last_execution_time", 0)),
                output_count=_safe_int(getattr(s, "execution_count", 0)),
                cadence=f"热点驱动（scope={getattr(s, 'scope', '?')}）",
            ))
            n += 1
        except Exception as ex:
            logger.warning("[FleetRegistry] 热点策略 %s 采集失败（%s: %s）",
                           sid, type(ex).__name__, ex)
    reg.set_source_status(source, ok=True, count=n)
    return n


def refresh(reg: Optional[FleetRegistry] = None) -> Dict[str, int]:
    """重采集所有来源。单项失败不影响其他项，且都会留痕。"""
    reg = reg or get_fleet_registry()
    counts = {
        "datasource_mgr": collect_datasource_units(reg),
        "strategy_mgr": collect_strategy_units(reg),
        "hotspot": collect_hotspot_units(reg),
        "manifest": refresh_manifest_units(reg),
    }
    reg._last_refresh_ts = time.time()
    return counts


# ── 声明式清单（散落取数点 / 常驻 runner）────────────────────────────────────

#: 「在不在跑」的候选属性名。❗各 runner 写法不统一：BanditAutoRunner 用
#: ``_running``、TRotationRunner 用 ``running`` property、有的压根没有。
#: 逐个硬编码会漏，统一按候选名探测；**一个都没有就如实 unknown，不许猜 running**。
STATE_ATTR_CANDIDATES = ("is_running", "running", "_running", "active", "_active")


def _sr_getter(sr_name: str) -> Callable[[], Any]:
    def _get():
        from deva.naja.register import SR
        return SR(sr_name)
    return _get


def _mod_getter(module_path: str, func_name: str) -> Callable[[], Any]:
    """按模块路径 + 工厂函数名取对象。

    用于**没有进单例注册表**的组件（如 ``intent_runner`` 由 container 直接
    ``get_intent_runner()`` 启动，SR() 取它会 KeyError）。
    """
    def _get():
        import importlib
        mod = importlib.import_module(module_path)
        return getattr(mod, func_name)()
    return _get


def make_unit_reader(getter: Callable[[], Any], label: str,
                     **stat_keys: str) -> Callable[[], Dict[str, Any]]:
    """通用状态 reader 工厂。

    - ``state``：按 ``STATE_ATTR_CANDIDATES`` 探测，命中布尔 → running/stopped；
      全部落空 → ``unknown`` + note（**不许默认成 running 或 0**）。
    - ``stat_keys``：``output_count="processed_count"`` 之类，先查属性，
      再查 ``get_stats()`` 返回的键。
    """
    def _read() -> Dict[str, Any]:
        obj = getter()
        if obj is None:
            return {"state": ST_UNKNOWN, "note": f"{label} 取不到实例"}
        out: Dict[str, Any] = {}
        stats = None

        for attr in STATE_ATTR_CANDIDATES:
            if hasattr(obj, attr):
                try:
                    value = getattr(obj, attr)
                except Exception:
                    continue
                if callable(value):
                    try:
                        value = value()
                    except Exception:
                        continue
                if isinstance(value, bool):
                    out["state"] = ST_RUNNING if value else ST_STOPPED
                    break

        for key, path in stat_keys.items():
            value = None
            if hasattr(obj, path):
                try:
                    value = getattr(obj, path)
                except Exception:
                    value = None
            if value is None:
                if stats is None and hasattr(obj, "get_stats"):
                    try:
                        stats = obj.get_stats()
                    except Exception:
                        stats = {}
                if isinstance(stats, dict) and path in stats:
                    value = stats[path]
            if value is not None and not callable(value):
                try:
                    out[key] = float(value) if key.endswith("_ts") else int(value)
                except (TypeError, ValueError):
                    out[key] = value

        if "state" not in out:
            out["state"] = ST_UNKNOWN
            out["note"] = f"{label} 未暴露运行状态字段（无独立生命周期开关）"
        return out
    return _read


#: 常驻 runner / 引擎。这些不是 yaml 策略，但确实在持续做决策，必须在首页可见。
#: (unit_id, name, cadence, getter, stat_keys)
#:
#: ❗**为什么一律走模块级 getter，不用 SR()**：这些组件是 container / 各模块用
#: ``get_xxx_runner()`` **启动**的，而 register.py 的表里另有同名单例条目
#: （工厂是 ``Class()``）。用 SR() 会**造出第二个实例** —— 那个新实例从未 start()，
#: 于是首页读到「已停止」的**假红**，而真正在跑的那个没人问。
#: 「一个语义两个实例」是本仓明令禁止的，读状态尤其不能踩。
RUNNER_MANIFEST = (
    ("run:bandit_runner", "Bandit 自动运行器", "事件驱动",
     _mod_getter("deva.naja.bandit.runner", "get_bandit_runner"), {}),
    # adaptive_cycle 没有模块级 getter，只能走注册表
    ("run:adaptive_cycle", "自适应周期", "定时",
     _sr_getter("adaptive_cycle"), {}),
    ("run:t_rotation", "做T降本运行器", "盘中持续",
     _mod_getter("deva.naja.bandit.t_rotation_runner", "get_t_rotation_runner"), {}),
    ("run:intent_runner", "守望台 IntentRunner", "常驻节拍",
     _mod_getter("deva.naja.bandit.intent_runner", "get_intent_runner"), {}),
    ("run:daily_review", "每日复盘调度", "cron",
     _mod_getter("deva.naja.strategy.daily_review_scheduler",
                 "get_daily_review_scheduler"), {}),
    ("run:position_monitor", "持仓监控", "常驻",
     _mod_getter("deva.naja.attention.tracking.position_monitor",
                 "get_position_monitor"), {}),
    ("run:auto_tuner", "自动调参", "常驻",
     _mod_getter("deva.naja.infra.observability.auto_tuner", "get_auto_tuner"), {}),
    ("run:radar_engine", "雷达引擎", "常驻",
     _mod_getter("deva.naja.radar.engine", "get_radar_engine"), {}),
    ("run:cognition_orchestrator", "认知编排器", "事件驱动",
     _mod_getter("deva.naja.attention.orchestration.cognition_orchestrator",
                 "get_cognition_orchestrator"), {}),
)


def refresh_manifest_units(reg: Optional[FleetRegistry] = None) -> int:
    """重采集声明式清单里的常驻 runner。

    ❗散落取数点（source="manifest"）由各模块自己 import 时登记，**不在这里清**，
    否则会抹掉那些只在进程启动时登记一次的探针/声明。
    """
    reg = reg or get_fleet_registry()
    n = 0
    for unit_id, name, cadence, getter, stat_keys in RUNNER_MANIFEST:
        declare_manifest_unit(
            unit_id=unit_id, kind=KIND_STRATEGY, name=name,
            cadence=cadence, reader=make_unit_reader(getter, name, **stat_keys),
        )
        n += 1
    return n


__all__ = [
    "KIND_DATASOURCE", "KIND_STRATEGY",
    "ST_RUNNING", "ST_STOPPED", "ST_UNKNOWN", "ST_SKIPPED",
    "DEFAULT_STALE_AFTER", "DEFAULT_RECENT_ERROR_WINDOW",
    "UnitCard", "FleetRegistry", "get_fleet_registry",
    "probe", "report_manual", "declare_manifest_unit",
    "collect_datasource_units", "collect_strategy_units",
    "collect_hotspot_units", "refresh", "refresh_manifest_units",
    "RUNNER_MANIFEST", "make_unit_reader", "STATE_ATTR_CANDIDATES",
    "_sr_getter", "_mod_getter",
]
