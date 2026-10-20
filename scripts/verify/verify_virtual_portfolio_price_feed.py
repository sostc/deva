#!/usr/bin/env python3
"""守卫：虚拟仓必须有真实价格源，且价格/账本不允许出现「半途状态」。

## 这份守卫守的是什么

虚拟仓（``VirtualPortfolio``，账户名 ``虚拟测试``）曾经是一个**没有价格输入**
的系统：

1. ``update_price()`` 只有 ``adaptive_cycle`` / ``tuner`` 两个调用方，而
   ``adaptive_cycle`` 是懒单例 —— 没人访问它，它就永远不会跑；
2. ``MarketDataBus.subscribe()`` 全仓**无人调用**；
3. 于是持仓现价永远停在开仓价（实测 NVDA ``entry=450 / current=450``，
   真实价 217），``update_price`` 里的止损止盈判定**一次都没执行过**。

修这条链的过程中又挖出三个「半途状态」：

- A 股行情明明抓到了 3 条，却因为 ``quotes`` 用**带前缀** key（``sh588200``）
  存、``fetch()`` 拿**裸码**（``588200``）查，被映射成 ``0.0``；
- ``update_price()`` 先改 ``current_price`` 再取市场时间 —— 时间服务一抛异常，
  价格变了、止损没判；
- ``close_position()`` 先写 ``status="CLOSED"`` 再取市场时间 —— 时间服务一抛
  异常，内存里已平仓、但 ``exit_time``/``close_reason`` 是空、``_used_capital``
  没减、落库和回调全没跑，变成幽灵持仓。

判据一律钉**行为**（真的调了什么、账本变成什么样），不是「源码里出现过某个词」。

用法：
    python scripts/verify/verify_virtual_portfolio_price_feed.py --strict
    python scripts/verify/verify_virtual_portfolio_price_feed.py --exercise-injections
"""

from __future__ import annotations

import argparse
import importlib.util
import copy
import re
import sys
import threading
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PASS = 0
FAIL = 0
FAILS: list[str] = []


def _ok(msg: str) -> None:
    global PASS
    PASS += 1
    print(f"  ✅ {msg}")


def _bad(msg: str) -> None:
    global FAIL
    FAIL += 1
    FAILS.append(msg)
    print(f"  ❌ {msg}")


def _load(rel_path: str, mod_name: str):
    """按文件路径重载模块。

    ❗不能用 ``import``：拿到的是 ``sys.modules`` 里的旧对象，注入的新代码
    根本没被读进来 —— 守卫会全绿，但什么都没守。必须先 ``sys.modules[name]=mod``
    再 ``exec_module``，否则 ``@dataclass`` 解析 ``KW_ONLY`` 时会因为模块还在
    半初始化状态抛 ``'NoneType' object has no attribute '__dict__'``。
    """
    path = ROOT / rel_path
    spec = importlib.util.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载 {rel_path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


# ── 判据 1：A 股行情 key 必须归一到裸码 ─────────────────────────────────────
SINA_ASHARE = (
    'var hq_str_sh588200="科创芯片ETF嘉实,0.910,0.920,0.920,0.930,0.905,'
    '0.919,0.920,12345678,11300000.00,1,2,3,4,5,6,7,8,9,10,2026-10-20,15:00:00,00";'
)


def check_ashare_key_normalized(mod) -> None:
    print("\n[1] A 股行情解析：key 必须归一成裸码")
    try:
        bus = object.__new__(mod.MarketDataBus)  # 只调纯函数，不碰网络/DB
        quotes = bus._parse_ashare_response(SINA_ASHARE, ["sh588200"])
    except Exception as e:  # noqa: BLE001
        _bad(f"A 股解析直接抛异常：{type(e).__name__}: {e}")
        return

    if not quotes:
        _bad("A 股解析返回空 —— 行情文本明明有 1 条，说明解析逻辑坏了")
        return

    q = quotes.get("588200")
    if q is None:
        _bad(
            "解析结果里没有裸码 key '588200'（拿到的是 "
            f"{sorted(quotes)}）—— fetch() 用裸码查，必然映射成 0.0"
        )
        return
    if abs(getattr(q, "current", 0) - 0.92) > 1e-6:
        _bad(f"588200 现价应解析为 0.92，实际 {getattr(q, 'current', None)}")
        return
    _ok("sh588200 解析后可用裸码 '588200' 取到现价 0.92")

    # 带前缀 key 应保留（兼容既有调用方），但**不能是唯一形态**
    if "sh588200" not in quotes:
        _bad("带前缀 key 'sh588200' 丢了 —— 既有调用方会静默拿不到数据")
    else:
        _ok("带前缀 key 仍保留，双形态可查")


# ── 判据 2：fetch 必须按「裸码 → 带前缀」逐级兜底 ──────────────────────────
def check_fetch_fallback(mod) -> None:
    print("\n[2] fetch 取价：必须多形态兜底")
    src = (ROOT / "deva/naja/bandit/market_data_bus.py").read_text(encoding="utf-8")
    m = re.search(r"def fetch\(.*?\n(.*?)\n    def ", src, re.S)
    body = m.group(1) if m else ""
    if not body:
        _bad("找不到 fetch() 函数体 —— 守卫过期，需同步")
        return
    if "_pick_price" not in body:
        _bad("fetch() 里没有 _pick_price 兜底，只查单个 key 会漏掉带前缀的行情")
    else:
        _ok("fetch() 通过 _pick_price 做多形态兜底")
    if "_format_code(code)" not in body:
        _bad("_pick_price 没尝试带交易所前缀的 key，A 股仍会 miss")
    else:
        _ok("_pick_price 会回退到带前缀 key")


# ── 判据 3：价格供给器绝不能把 0.0 写回持仓 ────────────────────────────────
class _FakeBus:
    def __init__(self, prices):
        self._prices = prices
        self.calls = 0

    def fetch(self, codes, force=False):
        self.calls += 1
        return {c: self._prices.get(c, 0.0) for c in codes}


class _FakePortfolio:
    def __init__(self, codes):
        self._positions = {
            f"p{i}": _FakePos(c, 10.0) for i, c in enumerate(codes)
        }
        self.updated: list[tuple[str, float]] = []
        self.flushed = 0

    def update_price(self, code, price):
        self.updated.append((code, price))
        return []

    def flush(self):
        self.flushed += 1


class _FakePos:
    def __init__(self, code, price):
        self.stock_code = code
        self.status = "OPEN"
        self.entry_price = price
        self.current_price = price


def check_feed_ignores_zero(feed_mod) -> None:
    print("\n[3] 价格供给器：取不到（0.0）的价格绝不能写回")
    vp = _FakePortfolio(["588200", "NVDA", "06666"])
    bus = _FakeBus({"NVDA": 217.09})  # 588200 / 06666 取不到 → 0.0
    # ❗manager=None 是**显式禁用**：不传的话 feed 会懒加载真 PortfolioManager
    # 去读生产库，守卫就变成污染源了。
    feed = feed_mod.PortfolioPriceFeed(
        portfolio=vp, bus=bus, save_interval=1e9, manager=None
    )
    try:
        r = feed.refresh_once()
    except Exception as e:  # noqa: BLE001
        _bad(f"refresh_once 抛异常：{type(e).__name__}: {e}")
        return

    written = dict(vp.updated)
    if "588200" in written:
        _bad(
            f"取不到价的 588200 被写回 {written['588200']} —— 现价会被清零、"
            "浮亏变 -100%，并立刻击穿任何止损"
        )
    else:
        _ok("取不到价的标的没有被写回（现价保持原值）")

    if abs(written.get("NVDA", 0) - 217.09) > 1e-6:
        _bad(f"NVDA 有价却没被写入（实际 {written.get('NVDA')}）")
    else:
        _ok("有价的 NVDA 正常写入 217.09")

    if r.get("unpriced", {}).get("588200") is None:
        _bad("诊断里没有记录 588200 的「取不到价」原因 —— 又变成静默的了")
    else:
        _ok("取不到价的标的进了 unpriced 诊断，原因可追溯")


# ── 判据 4：时间服务故障时，平仓不能停在半途 ──────────────────────────────
class _BoomClock:
    def get_market_time(self):
        raise RuntimeError("市场时间服务不可用")


class _SilentDB:
    def __init__(self):
        self.data = {}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def __setitem__(self, key, value):
        self.data[key] = value

    def __getitem__(self, key):
        return self.data[key]


def _make_portfolio(mod):
    vp = object.__new__(mod.VirtualPortfolio)
    vp.account_name = "guard_test"
    vp._positions = {
        "p1": mod.VirtualPosition(
            position_id="p1", strategy_id="s", strategy_name="n",
            stock_code="NVDA", stock_name="NVDA",
            entry_price=450.0, current_price=450.0, quantity=10.0,
            entry_time=1.0, last_update_time=1.0, status="OPEN",
            stop_loss=414.0, take_profit=900.0,
        )
    }
    vp._lock = threading.RLock()
    vp._position_callbacks = []
    vp._close_callbacks = []
    vp._total_capital = 10000.0
    vp._used_capital = 4500.0
    vp._max_position_pct = 0.3
    vp._max_total_pct = 0.9
    vp._db = _SilentDB()
    vp._market_time_service = _BoomClock()
    vp._save_positions = lambda: None  # ❗守卫绝不写生产库
    return vp


def check_close_no_half_state(mod) -> None:
    print("\n[4] close_position：时间服务坏掉也不许留下半途状态")
    vp = _make_portfolio(mod)
    raised = ""
    try:
        vp.close_position("p1", 217.09, "STOP_LOSS")
    except Exception as e:  # noqa: BLE001
        raised = f"{type(e).__name__}: {e}"

    p = vp._positions["p1"]
    if raised:
        _bad(f"时间服务故障直接让平仓失败：{raised}（应降级到本地时间，不该中断）")
        return
    _ok("时间服务故障时平仓仍完成（降级本地时间）")

    if p.status != "CLOSED":
        _bad(f"平仓后状态仍是 {p.status}，止损没有真正生效")
    else:
        _ok("持仓状态已置 CLOSED")

    if p.exit_time <= 0:
        _bad("exit_time 仍为 0 —— 平仓时间和状态不同步")
    else:
        _ok(f"exit_time 已写入（{p.exit_time:.0f}）")

    if p.close_reason != "STOP_LOSS":
        _bad(f"close_reason 是 {p.close_reason!r}，丢失了平仓原因")
    else:
        _ok("close_reason 保留 STOP_LOSS")

    if vp._used_capital >= 4500.0:
        _bad(f"used_capital 没扣减（仍 {vp._used_capital}）—— 资金被永久占用")
    else:
        _ok(f"used_capital 已扣减到 {vp._used_capital:.0f}")


# ── 判据 5：update_price 改价前必须先拿到时间 ──────────────────────────────
def check_update_price_order(mod) -> None:
    print("\n[5] update_price：时间戳必须在改价格之前取")
    src = (ROOT / "deva/naja/bandit/virtual_portfolio.py").read_text(encoding="utf-8")
    m = re.search(r"    def update_price\(.*?\n(.*?)\n    def ", src, re.S)
    body = m.group(1) if m else ""
    if not body:
        _bad("找不到 update_price 函数体")
        return
    lines = body.split("\n")
    i_time = next((i for i, l in enumerate(lines) if "get_market_time" in l), -1)
    i_mut = next((i for i, l in enumerate(lines) if "current_price = current_price" in l), -1)
    if i_time < 0:
        _bad("update_price 里没有取市场时间 —— 守卫过期")
        return
    if i_mut < 0:
        _bad("找不到「改现价」那一行 —— 守卫过期")
        return
    if i_time > i_mut:
        _bad(
            "取时间（行 %d）在改现价（行 %d）之后 —— 时间服务一抛异常就会"
            "留下「价格已改、止损未判」的半途状态" % (i_time, i_mut)
        )
    else:
        _ok("取时间在改现价之前，异常不会留下半途账本")

    # 行为侧：时间服务坏了也必须能更新价格并判止损
    vp = _make_portfolio(mod)
    try:
        closed = vp.update_price("NVDA", 217.09)
    except Exception as e:  # noqa: BLE001
        _bad(f"时间服务故障时 update_price 抛异常：{type(e).__name__}: {e}")
        return
    p = vp._positions["p1"]
    if p.status != "CLOSED" or not closed:
        _bad(f"现价 217 已跌破止损 414，却没触发止损（status={p.status}）")
    else:
        _ok("时间服务故障时仍正确触发止损平仓")


# ── 判据 6：容器必须真的启动价格供给器 ────────────────────────────────────
def check_container_wiring() -> None:
    print("\n[6] 容器装配：必须把价格供给器接起来")
    src = (ROOT / "deva/naja/application/container.py").read_text(encoding="utf-8")
    if "portfolio_price_feed" not in src:
        _bad("container 里没引用 portfolio_price_feed —— 虚拟仓又变回没人喂价")
        return
    _ok("container 引用了 portfolio_price_feed")
    if "get_portfolio_price_feed" not in src or "feed.start()" not in src:
        _bad("container 只 import 了却没 start()，线程不会跑")
    else:
        _ok("container 会真正 start() 供给器")

    m = re.search(r"tasks = \{(.*?)\}", src, re.S)
    if not m:
        _bad("找不到后台初始化 tasks 字典 —— 守卫过期")
        return
    if "虚拟仓价格源" not in m.group(1):
        _bad("供给器没进后台初始化 tasks，服务启动时不会被拉起")
    else:
        _ok("供给器在后台初始化 tasks 里（启动即拉起）")


# ── 判据 7：总线不覆盖的代码必须告警（不许伪装成取数失败）──────────────────
def check_unrouted_warning(mod) -> None:
    print("\n[7] 未覆盖市场：必须显式告警，不能静默返 0")
    src = (ROOT / "deva/naja/bandit/market_data_bus.py").read_text(encoding="utf-8")
    if "_warn_unrouted" not in src:
        _bad("没有 _warn_unrouted —— 港股等未覆盖代码会被静默丢弃")
        return
    _ok("存在 _warn_unrouted 告警路径")
    if "unrouted" not in src:
        _bad("_do_fetch_async 里没算 unrouted 集合，告警永远不会触发")
    else:
        _ok("_do_fetch_async 计算了 unrouted 集合并告警")


# ── 判据 8：本地记账账户必须也被喂价（第二层孤儿）──────────────────────────
class _FakeLocalPos:
    def __init__(self, code):
        self.stock_code = code
        self.status = "OPEN"
        self.current_price = 0.0


class _FakeLocalAccount:
    """替身必须与 ``USStockPortfolio`` **同构**（方法名/返回类型对齐）。"""

    def __init__(self, codes, account_type="us"):
        self.account_type = account_type
        self._codes = list(codes)
        self.updated: dict[str, float] = {}

    def get_open_positions(self):
        return [_FakeLocalPos(c) for c in self._codes]

    def update_prices_batch(self, price_map, prev_close_map=None):
        n = 0
        for c in self._codes:
            if c in price_map:
                self.updated[c] = price_map[c]
                n += 1
        return n


class _FakeManager:
    def __init__(self, accounts):
        self._accounts = dict(accounts)
        self.local_calls: list[dict] = []

    def get_local_accounts(self):
        return dict(self._accounts)

    def update_local_prices(self, price_map, prev_close_map=None):
        self.local_calls.append(dict(price_map))
        out = {}
        for name, p in self._accounts.items():
            n = p.update_prices_batch(price_map, prev_close_map)
            if n > 0:
                out[name] = n
        return out


def check_local_accounts_fed(feed_mod) -> None:
    print("\n[8] 本地记账账户：必须也被喂价（第二层孤儿）")
    local = _FakeLocalAccount(["nvda", "alab"])
    pm = _FakeManager({"Spark": local})
    vp = _FakePortfolio(["588200"])
    bus = _FakeBus({"588200": 0.92, "nvda": 217.09, "alab": 325.41})
    feed = feed_mod.PortfolioPriceFeed(
        portfolio=vp, bus=bus, save_interval=1e9, manager=pm
    )
    try:
        r = feed.refresh_once()
    except Exception as e:  # noqa: BLE001
        _bad(f"refresh_once 抛异常：{type(e).__name__}: {e}")
        return

    if not pm.local_calls:
        _bad("refresh_once 完全没调 update_local_prices —— 本地账户仍是孤儿，现价停在开仓价")
        return
    _ok("refresh_once 把价格交给了本地记账账户")

    if abs(local.updated.get("nvda", 0) - 217.09) > 1e-6:
        _bad(f"本地账户的 nvda 没被更新（实际 {local.updated.get('nvda')}）")
    else:
        _ok("本地账户 nvda 更新到 217.09")
    if abs(local.updated.get("alab", 0) - 325.41) > 1e-6:
        _bad(f"本地账户的 alab 没被更新（实际 {local.updated.get('alab')}）")
    else:
        _ok("本地账户 alab 更新到 325.41")

    # 两套持仓绝不能串：本地账户的代码不许走 vp.update_price（那边会判止损）
    vp_written = dict(vp.updated)
    if "nvda" in vp_written or "alab" in vp_written:
        _bad(f"本地账户的代码被喂给了虚拟仓 {sorted(vp_written)} —— 会按虚拟仓的止损位误平仓")
    else:
        _ok("本地账户代码没有串进虚拟仓（不会误触发止损）")

    if r.get("local_updated", {}).get("Spark") != 2:
        _bad(f"诊断 local_updated 不对：{r.get('local_updated')}（应记 Spark=2 条）")
    else:
        _ok("诊断里透出 local_updated，可追溯每轮喂了几条")


# ── 判据 9：券商账户（futu）不许被行情总线覆盖 ─────────────────────────────
def check_broker_accounts_excluded(pm_mod) -> None:
    print("\n[9] 券商账户：行情总线不得覆盖同步器写的价")
    cls = pm_mod.PortfolioManager
    obj = object.__new__(cls)  # 只调纯逻辑，不初始化 NB
    us = _FakeLocalAccount(["nvda"], account_type="us")
    futu = _FakeLocalAccount(["nvda"], account_type="futu")
    obj._us_portfolios = {"Spark": us, "FutuHK": futu}

    try:
        picked = cls.get_local_accounts(obj)
    except Exception as e:  # noqa: BLE001
        _bad(f"get_local_accounts 抛异常：{type(e).__name__}: {e}")
        return
    if "FutuHK" in picked:
        _bad("券商账户 FutuHK 被当成本地账户 —— 行情快照会覆盖券商真实价，对账必然对不上")
        return
    if "Spark" not in picked:
        _bad("本地账户 Spark 没进 get_local_accounts")
        return
    _ok("get_local_accounts 只返回本地记账账户（排除 futu）")

    try:
        res = cls.update_local_prices(obj, {"nvda": 999.0})
    except Exception as e:  # noqa: BLE001
        _bad(f"update_local_prices 抛异常：{type(e).__name__}: {e}")
        return
    if futu.updated:
        _bad(f"券商账户的价格被行情覆盖了 {futu.updated} —— 与券商 App 对不上的数字会进报表")
    else:
        _ok("券商账户价格未被行情总线覆盖")
    if abs(us.updated.get("nvda", 0) - 999.0) > 1e-6:
        _bad(f"本地账户没被更新（实际 {us.updated.get('nvda')}）")
    else:
        _ok("本地账户照常更新")
    if res.get("Spark") != 1:
        _bad(f"返回值不对：{res}（应 Spark=1）")
    else:
        _ok("返回值按账户汇总条数")


# ── 判据 10：美股路由不得靠硬编码白名单 ────────────────────────────────────
def check_us_symbol_routing(mod) -> None:
    print("\n[10] 美股路由：不得靠 10 只白名单")
    for code in ("alab", "crwv", "skuu", "NVDA"):
        if not mod.looks_like_us_symbol(code):
            _bad(f"{code} 不被认作美股 —— 白名单外的美股仍然取不到行情，持仓现价永远停在开仓价")
            return
    _ok("白名单外的美股（alab/crwv/skuu）也走美股路由")
    for code in ("588200", "sh588200", "06666", "00700"):
        if mod.looks_like_us_symbol(code):
            _bad(f"{code} 被误判成美股 —— 会拼出错误的 gb_ 前缀，A 股/港股彻底取不到")
            return
    _ok("A 股（6 位）与港股（5 位）不会被误判成美股")

    src = (ROOT / "deva/naja/bandit/market_data_bus.py").read_text(encoding="utf-8")
    if "in US_COMMON_CODES" in src:
        _bad("美股路由仍在用硬编码白名单 —— 白名单外的标的是永远的孤儿")
    else:
        _ok("美股路由不再引用硬编码白名单")


# ── 判据 11：静态表外、字段数较少的美股行也必须能解析 ──────────────────────
# 两个**互补**样本，让两道闸的失败原因可区分：
#   · gb_zzqx：32 字段但**不在静态表** → 只可能被「静态表 membership」闸拦下
#   · gb_alab：在真实响应里只有 23 字段 → 只可能被「len(fields) < 30」闸拦下
SINA_US_ZZQX = (
    'var hq_str_gb_zzqx="ZZQX,20.2400,1.50,2026-10-20 17:00:00,0.3000,20.0000,'
    '20.5000,19.8000,30.0000,10.0000,100000,200000,3000000,1.00,15.000000,0.00,'
    '2.00,0.00,0.00,1000,0,19.9000,-0.50,0,0,0,0,19.9400,0,0,0,0,0";'
)
SINA_US_ALAB = (
    'var hq_str_gb_alab="ALAB,286.5800,0.27,2026-10-20 17:00:38,0.7600,299.9700,'
    '300.6650,285.0400,499.4760,97.8900,2865133,4514300,49717361104,1.59,180.240000,'
    '0.00,2.81,0.00,0.00,173485104,0,281.0000,-1.95";'
)
# 期货行走另一条分支，用来确认「美股兜底」没有抢走期货
SINA_FUT_NQ = 'var hq_str_hf_NQ="29561.175,-0.02,29580.0,29600.0,29300.0,29561.0,14:05:00,29568.0,29500.0,29500.0,0,0,0,0,0,0,0,0,0,2026-10-20,纳斯达克100指数期货,1";'


def check_us_line_parsing(gmf_mod) -> None:
    print("\n[11] 美股解析：静态表外 + 字段数少的美股行必须能解析")
    api = object.__new__(gmf_mod.GlobalMarketAPI)  # 只调纯解析，不建 session

    # ① 静态表外的美股（字段充足）
    try:
        r0 = api._parse_response(SINA_US_ZZQX, ["gb_zzqx"])
    except Exception as e:  # noqa: BLE001
        _bad(f"_parse_response 抛异常：{type(e).__name__}: {e}")
        return
    if "zzqx" not in r0:
        _bad(
            "静态表外、字段充足的美股 zzqx 仍被丢弃 —— 美股分支只认静态配置表，"
            "表外标的（alab/skuu/crwv…）永远取不到价"
        )
        return
    _ok("静态表外的美股（zzqx，32 字段）正常解析")

    # ② 字段数少（真实 alab 响应 23 字段）
    try:
        r = api._parse_response(SINA_US_ALAB, ["gb_alab"])
    except Exception as e:  # noqa: BLE001
        _bad(f"_parse_response 抛异常：{type(e).__name__}: {e}")
        return
    if "alab" not in r:
        _bad(
            "alab（真实响应只有 23 字段，现价 286.58）被整行丢掉 —— "
            "命中 len(fields) < 30 硬阈值，冷门票现价永远不动"
        )
        return
    got = getattr(r["alab"], "current", 0)
    if abs(got - 286.58) > 1e-6:
        _bad(f"alab 现价解析成 {got}，应为 286.58")
        return
    _ok("字段数少的美股行（alab，23 字段）正常解析出 286.58")

    try:
        r2 = api._parse_response(SINA_FUT_NQ, ["hf_NQ"])
    except Exception as e:  # noqa: BLE001
        _bad(f"期货行解析抛异常：{type(e).__name__}: {e}")
        return
    if "NQ" not in r2:
        _bad("期货行 NQ 解析不出来了 —— 美股兜底抢占了期货分支")
    else:
        _ok("期货行仍走自己的分支（兜底没有抢走）")

    src = (ROOT / "deva/naja/market_hotspot/data/global_market_futures.py").read_text(encoding="utf-8")
    if "if len(fields) < 30:" in src:
        _bad("美股行仍是 len(fields) < 30 的硬阈值 —— 字段少的冷门票会被整行丢弃")
    else:
        _ok("美股行字段阈值只卡必需字段")


# ── 判据 12：持仓落库并发不得丢更新 ────────────────────────────────────────
class _RacyDB:
    """模拟 NB 的**反序列化语义**：``get`` 每次返回一份新副本。

    这正是丢更新的前提 —— 真实 NB 的 ``get`` 不是返回内存里的同一个对象，
    而是重新反序列化，所以「A 读 → B 读 → A 写 → B 写」时 B 写回的是
    不含 A 改动的旧快照。
    """

    def __init__(self, initial=None):
        self.data = dict(initial or {})
        self._l = threading.Lock()

    def get(self, key, default=None):
        with self._l:
            blob = self.data.get(key)
        if blob is None:
            return copy.deepcopy(default)
        time.sleep(0.002)  # 放大「两个线程都拿到同一份旧快照」的窗口
        return copy.deepcopy(blob)

    def __setitem__(self, key, value):
        with self._l:
            self.data[key] = copy.deepcopy(value)


class _NoLock:
    """把锁换成空操作 —— 用于负向注入。"""

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def check_positions_write_lock(vp_mod, pm_mod) -> None:
    print("\n[12] 持仓落库：虚拟仓与本地账户并发写不得丢更新")
    db = _RacyDB({"accounts": {"base": {"account_type": "us", "positions": {}}}})

    vp = object.__new__(vp_mod.VirtualPortfolio)
    vp.account_name = "vtest"
    vp._db = db
    vp._positions = {}
    vp._total_capital = 1.0
    vp._used_capital = 0.0

    us = object.__new__(pm_mod.USStockPortfolio)
    us.account_name = "usatest"
    us._db = db
    us._positions = {}
    us._equity = 0.0

    errs: list[str] = []

    def hammer(fn):
        for _ in range(25):
            try:
                fn()
            except Exception as e:  # noqa: BLE001
                errs.append(f"{type(e).__name__}: {e}")

    ts = [
        threading.Thread(target=hammer, args=(vp._save_positions,)),
        threading.Thread(target=hammer, args=(us._save_positions,)),
    ]
    for t in ts:
        t.start()
    for t in ts:
        t.join()

    if errs:
        _bad(f"并发落库抛异常：{errs[0]}")
        return

    accounts = db.data.get("accounts", {})
    missing = [n for n in ("base", "vtest", "usatest") if n not in accounts]
    if missing:
        _bad(
            f"并发落库丢了账户 {missing} —— 后写的一方拿旧快照覆盖了先写的，"
            "表现是「持仓现价/数量莫名回退」，而且没有任何报错"
        )
    else:
        _ok("并发落库后三个账户都还在（没有互相覆盖）")

    if not hasattr(vp_mod, "POSITIONS_WRITE_LOCK") or not hasattr(pm_mod, "POSITIONS_WRITE_LOCK"):
        _bad("模块里没有 POSITIONS_WRITE_LOCK —— 写锁被删了")
    else:
        _ok("两个模块都接入了 POSITIONS_WRITE_LOCK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--exercise-injections", action="store_true")
    args = parser.parse_args()

    print("=" * 70)
    print("虚拟仓价格源 / 半途状态 守卫")
    print("=" * 70)

    try:
        bus_mod = _load("deva/naja/bandit/market_data_bus.py", "_guard_bus")
        vp_mod = _load("deva/naja/bandit/virtual_portfolio.py", "_guard_vp")
        feed_mod = _load("deva/naja/bandit/portfolio_price_feed.py", "_guard_feed")
        pm_mod = _load("deva/naja/bandit/portfolio_manager.py", "_guard_pm")
        gmf_mod = _load(
            "deva/naja/market_hotspot/data/global_market_futures.py", "_guard_gmf"
        )
    except Exception as e:  # noqa: BLE001
        print(f"❌ 模块加载失败：{type(e).__name__}: {e}")
        traceback.print_exc()
        return 1

    for fn in (
        lambda: check_ashare_key_normalized(bus_mod),
        lambda: check_fetch_fallback(bus_mod),
        lambda: check_feed_ignores_zero(feed_mod),
        lambda: check_close_no_half_state(vp_mod),
        lambda: check_update_price_order(vp_mod),
        check_container_wiring,
        lambda: check_unrouted_warning(bus_mod),
        lambda: check_local_accounts_fed(feed_mod),
        lambda: check_broker_accounts_excluded(pm_mod),
        lambda: check_us_symbol_routing(bus_mod),
        lambda: check_us_line_parsing(gmf_mod),
        lambda: check_positions_write_lock(vp_mod, pm_mod),
    ):
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            _bad(f"判据执行异常：{type(e).__name__}: {e}")
            traceback.print_exc()

    total = PASS + FAIL
    print("\n" + "=" * 70)
    if FAIL:
        print(f"❌ {FAIL}/{total} 项失败")
        for f in FAILS:
            print(f"   - {f}")
        return 1
    print(f"✅ 全部 {total} 项通过")

    if args.exercise_injections:
        return _run_injections()
    return 0


# ── 负向注入：把每个修复逐个改回「坏版本」，守卫必须喊出来 ─────────────────
def _load_patched(rel_path: str, mod_name: str, old: str, new: str):
    """把源码改坏后用 exec 重新加载（不落盘、不污染工作区）。"""
    path = ROOT / rel_path
    src = path.read_text(encoding="utf-8")
    if old not in src:
        raise AssertionError(f"注入锚点找不到：{old[:60]!r}")
    patched = src.replace(old, new, 1)
    import types

    mod = types.ModuleType(mod_name)
    mod.__file__ = str(path)
    sys.modules[mod_name] = mod
    exec(compile(patched, str(path), "exec"), mod.__dict__)
    return mod


def _expect_catch(label: str, fn, should_fail_msg: str) -> bool:
    """跑一个判据，期望它**失败**；跑完把全局计数复原。"""
    global PASS, FAIL
    saved_pass, saved_fail = PASS, FAIL
    saved_fails = list(FAILS)
    before_fail = FAIL
    try:
        fn()
    except Exception:  # noqa: BLE001
        pass
    caught = FAIL > before_fail
    detail = FAILS[before_fail:] if caught else []
    PASS, FAIL = saved_pass, saved_fail
    FAILS[:] = saved_fails
    if caught:
        print(f"  ✅ 被捕获：{label} → {detail[0][:70] if detail else ''}")
    else:
        print(f"  ❌ 没抓到：{label} —— {should_fail_msg}")
    return caught


def _run_injections() -> int:
    print("\n" + "=" * 70)
    print("负向注入自证（把修复改回坏版本，守卫必须喊出来）")
    print("=" * 70)

    results: list[bool] = []

    # 注入 1：A 股 key 退回带前缀（原 bug）
    print("\n[注入 1] A 股行情 key 退回带前缀")
    try:
        mod = _load_patched(
            "deva/naja/bandit/market_data_bus.py", "_inj_bus_1",
            "                quotes[normalized] = q",
            "                pass",
        )
        results.append(_expect_catch(
            "A 股 key 不归一",
            lambda: check_ashare_key_normalized(mod),
            "key 退回 sh588200 后守卫仍然绿 —— 它没在守这件事",
        ))
    except Exception as e:  # noqa: BLE001
        print(f"  ❌ 锚点失效：{e}")
        results.append(False)

    # 注入 2：允许把 0.0 写回持仓
    print("\n[注入 2] 允许把取不到的 0.0 写回持仓")
    try:
        mod = _load_patched(
            "deva/naja/bandit/portfolio_price_feed.py", "_inj_feed_2",
            "            if price > 0:",
            "            if price >= 0:",
        )
        results.append(_expect_catch(
            "0.0 被写回",
            lambda: check_feed_ignores_zero(mod),
            "0.0 写回现价后守卫仍然绿 —— 它会掩盖「取不到价」把持仓清零",
        ))
    except Exception as e:  # noqa: BLE001
        print(f"  ❌ 锚点失效：{e}")
        results.append(False)

    # 注入 3：close_position 在改完状态后才可能抛（原半途 bug）
    print("\n[注入 3] close_position 改完状态再抛异常（半途账本）")
    try:
        mod = _load_patched(
            "deva/naja/bandit/virtual_portfolio.py", "_inj_vp_3",
            '            position.status = "CLOSED"',
            '            position.status = "CLOSED"\n'
            '            raise RuntimeError("injected: 模拟取时间失败")',
        )
        results.append(_expect_catch(
            "平仓半途状态",
            lambda: check_close_no_half_state(mod),
            "半途 CLOSED 仍被判通过 —— 幽灵持仓不会被发现",
        ))
    except Exception as e:  # noqa: BLE001
        print(f"  ❌ 锚点失效：{e}")
        results.append(False)

    # 注入 4：update_price 把取时间挪回改价之后（原顺序）
    print("\n[注入 4] update_price 取时间挪到改价之后")
    try:
        mod = _load_patched(
            "deva/naja/bandit/virtual_portfolio.py", "_inj_vp_4",
            "                position.last_update_time = now_ts",
            "                position.last_update_time = self._mts.get_market_time()",
        )
        results.append(_expect_catch(
            "取时间在改价之后",
            lambda: check_update_price_order(mod),
            "顺序退回原样后守卫仍然绿 —— 半途状态会重新出现",
        ))
    except Exception as e:  # noqa: BLE001
        print(f"  ❌ 锚点失效：{e}")
        results.append(False)

    # 注入 5：get_local_accounts 不再排除券商账户
    print("\n[注入 5] 券商账户混进「本地记账账户」")
    try:
        mod = _load_patched(
            "deva/naja/bandit/portfolio_manager.py", "_inj_pm_5",
            '            if getattr(p, "account_type", "us") != "futu"',
            "            if True",
        )
        results.append(_expect_catch(
            "券商账户未被排除",
            lambda: check_broker_accounts_excluded(mod),
            "券商账户被行情覆盖后守卫仍然绿 —— 报表数字会与券商 App 对不上",
        ))
    except Exception as e:  # noqa: BLE001
        print(f"  ❌ 锚点失效：{e}")
        results.append(False)

    # 注入 6：价格供给器不再喂本地账户
    print("\n[注入 6] 价格供给器只喂虚拟仓、不管本地账户")
    try:
        mod = _load_patched(
            "deva/naja/bandit/portfolio_price_feed.py", "_inj_feed_6",
            "                    local_updated = updater(local_prices) or {}",
            "                    local_updated = {}",
        )
        results.append(_expect_catch(
            "本地账户没人喂价",
            lambda: check_local_accounts_fed(mod),
            "本地账户再次变成孤儿，守卫仍然绿",
        ))
    except Exception as e:  # noqa: BLE001
        print(f"  ❌ 锚点失效：{e}")
        results.append(False)

    # 注入 7：美股路由退回 10 只白名单
    print("\n[注入 7] 美股路由退回硬编码白名单")
    try:
        mod = _load_patched(
            "deva/naja/bandit/market_data_bus.py", "_inj_bus_7",
            "    return c.isalpha() and 1 <= len(c) <= 5",
            '    return c.lower() in {"nvda", "aapl", "tsla", "msft", "googl", "amzn", "meta", "baba", "amd", "intc"}',
        )
        results.append(_expect_catch(
            "白名单外的美股取不到价",
            lambda: check_us_symbol_routing(mod),
            "退回白名单后守卫仍然绿 —— alab/crwv 会重新变成没有价格的孤儿",
        ))
    except Exception as e:  # noqa: BLE001
        print(f"  ❌ 锚点失效：{e}")
        results.append(False)

    # 注入 8：去掉「静态表外的美股」兜底
    print("\n[注入 8] 去掉美股兜底（退回静态表 membership）")
    try:
        mod = _load_patched(
            "deva/naja/market_hotspot/data/global_market_futures.py", "_inj_gmf_8",
            "                    or _looks_like_us_symbol(code_part)",
            "                    or False",
        )
        results.append(_expect_catch(
            "静态表外美股被丢",
            lambda: check_us_line_parsing(mod),
            "去掉兜底后守卫仍然绿 —— alab 会重新被静默丢弃",
        ))
    except Exception as e:  # noqa: BLE001
        print(f"  ❌ 锚点失效：{e}")
        results.append(False)

    # 注入 9：字段数阈值退回 30
    print("\n[注入 9] 美股行字段阈值退回 30")
    try:
        mod = _load_patched(
            "deva/naja/market_hotspot/data/global_market_futures.py", "_inj_gmf_9",
            "            if len(fields) < 8:",
            "            if len(fields) < 30:",
        )
        results.append(_expect_catch(
            "字段少的行被丢弃",
            lambda: check_us_line_parsing(mod),
            "阈值退回 30 后守卫仍然绿 —— 冷门票解析永远为空",
        ))
    except Exception as e:  # noqa: BLE001
        print(f"  ❌ 锚点失效：{e}")
        results.append(False)

    # 注入 10：把写锁换成空操作（等价于「没加锁」）
    print("\n[注入 10] 写锁换成空操作")
    try:
        vp_guard_mod = _load("deva/naja/bandit/virtual_portfolio.py", "_inj_vp_10")
        pm_guard_mod = _load("deva/naja/bandit/portfolio_manager.py", "_inj_pm_10")
        saved_vp = vp_guard_mod.POSITIONS_WRITE_LOCK
        saved_pm = pm_guard_mod.POSITIONS_WRITE_LOCK
        vp_guard_mod.POSITIONS_WRITE_LOCK = _NoLock()
        pm_guard_mod.POSITIONS_WRITE_LOCK = _NoLock()
        try:
            results.append(_expect_catch(
                "写锁被去掉",
                lambda: check_positions_write_lock(vp_guard_mod, pm_guard_mod),
                "锁被换成空操作后守卫仍然绿 —— 并发写会丢更新且无人发现",
            ))
        finally:
            vp_guard_mod.POSITIONS_WRITE_LOCK = saved_vp
            pm_guard_mod.POSITIONS_WRITE_LOCK = saved_pm
    except Exception as e:  # noqa: BLE001
        print(f"  ❌ 注入失败：{e}")
        results.append(False)

    ok = sum(1 for r in results if r)
    print("\n" + "=" * 70)
    print(f"{'✅' if ok == len(results) else '❌'} 负向注入 {ok}/{len(results)} 项被抓到")
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
