"""realtime_tick_5s — 盘中 A 股实时行情取数

归属层：infra/datasource（数据取数实现）。

NB 里那条数据源（id=e626eecd0b86）的 ``func_code`` 只做转发，逻辑全在本文件。
和 OpenRouter 那条（``cognition/openrouter_monitor.py``）是同一个约定：
**实现必须在仓库里**。400 行的内嵌字符串既没法 review，也没法被守卫覆盖，
每次改动都要往数据库里写一坨代码，写完还得重启才生效。

❗历史包袱（2026-10-21 修）

1. **候选宇宙是枚举出来的**：按板块代码段硬枚举约 5 万个代码
   （光北交所就 3 万个，实际挂牌不到 300 只），97% 的请求打在空代码上。
2. **批次是串行 await**：800 个/批 × 63 批，一个一个等，
   而执行层给整轮只留 30 秒 → 必然超时 → 每轮一条 TimeoutError。
3. 失败载荷 ``{"success": False}`` 曾被执行层当成正常产出 emit
   （已在 ``entry.py`` 的 ``_worker_loop`` 修）。

现在的做法：并发抓取 + **有效宇宙自收敛** + 单请求短超时 + 整轮预算。

自收敛是什么意思：第一次全量扫描后，把「新浪真的返回了数据」的代码记进 NB，
之后只打这份清单（约 5 千个，而不是 5 万个）。每 ``FULL_SCAN_INTERVAL_SEC``
重扫一次全量，防止新股上市/退市后清单僵死。
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from deva.naja.infra.observability.fleet_registry import KIND_DATASOURCE, probe

# ---- 抓取参数 ----------------------------------------------------------
# ❗并发度不是越大越好：hq.sinajs.cn 对单 IP 有频控，打太狠会被掐。
MAX_CONCURRENCY = 12
BATCH_SIZE = 800
REQUEST_TIMEOUT_SEC = 10          # 单批超时（原来是 30s，63 批串行直接用满预算）
ROUND_BUDGET_SEC = 25             # 整轮预算，必须 < 执行层 _execute_scheduled_fetch 的 30s
FULL_SCAN_INTERVAL_SEC = 6 * 3600  # 有效宇宙的有效期，过期重扫全量

UNIVERSE_TABLE = "naja_realtime_tick_universe"
UNIVERSE_KEY = "universe"

log_prefix = "[RealtimeTick]"


# ---- 代码空间 ----------------------------------------------------------
# 板块规则只用来生成**候选**（first time / 定期全量）。稳态用的是收敛后的清单。
BOARD_RANGES = [
    ("sh", 600000, 610000),
    ("sh", 601000, 602000),
    ("sh", 603000, 604000),
    ("sh", 605000, 606000),
    ("sh", 688000, 690000),   # 科创板
    ("sz", 0, 1000),          # 深市主板
    ("sz", 2000, 3000),       # 中小板
    ("sz", 300000, 302000),   # 创业板
    ("bj", 430000, 440000),   # 北交所
    ("bj", 830000, 840000),
    ("bj", 870000, 880000),
]

NON_STOCK_PREFIXES = (
    "sh000", "sh880", "sz399",   # 指数
    "sh51", "sh50", "sh501", "sh502",  # 基金
    "sh159", "sz159", "sz16", "sz184", "sz15",
)

NON_STOCK_KEYWORDS = ("指数", "ETF", "LOF", "基金", "债券", "国债", "企债")
RISK_KEYWORDS = ("ST", "*ST", "退", "退市")

ZOMBIE_VOLUME = 100     # 成交量低于 100 手
ZOMBIE_PRICE = 0.5      # 价格低于 0.5 元


def candidate_codes() -> List[str]:
    """按板块代码段枚举候选代码（约 5 万个，其中大部分是空号）"""
    codes: List[str] = []
    for prefix, start, end in BOARD_RANGES:
        width = 6 if prefix != "bj" else 6
        for i in range(start, end):
            codes.append(f"{prefix}{i:0{width}d}")
    return codes


# ---- 有效宇宙（自收敛） -------------------------------------------------
def _load_universe() -> Optional[Dict[str, Any]]:
    try:
        from deva import NB

        db = NB(UNIVERSE_TABLE)
        obj = db[UNIVERSE_KEY]  # ❗只读一次，别 db[k]=db[k]（右值会重新反序列化，改了全丢）
        if isinstance(obj, dict) and isinstance(obj.get("codes"), list):
            return obj
    except Exception:
        # 读不到就当没有缓存，走全量 —— 缓存只是优化，不是正确性依赖
        pass
    return None


def _save_universe(codes: List[str]) -> None:
    try:
        from deva import NB

        db = NB(UNIVERSE_TABLE)
        payload = {"codes": sorted(set(codes)), "updated_ts": time.time()}
        payload["updated_at"] = datetime.now().isoformat(timespec="seconds")
        db[UNIVERSE_KEY] = payload
    except Exception as e:
        print(f"{log_prefix} 有效宇宙写回失败（不致命，下轮重扫）: {e}")


def _resolve_scan_codes() -> Tuple[List[str], str]:
    """决定这一轮打哪些代码

    返回 (codes, mode)，mode ∈ {"cached", "full"}。
    """
    uni = _load_universe()
    if uni:
        age = time.time() - float(uni.get("updated_ts", 0))
        codes = uni.get("codes") or []
        if codes and age < FULL_SCAN_INTERVAL_SEC:
            return codes, "cached"
    return candidate_codes(), "full"


# ---- 抓取 --------------------------------------------------------------
_session = None
_session_loop = None


async def _get_session():
    """取（或重建）全局 session

    ❗aiohttp 的 session 绑在**创建它的那个 event loop** 上。
    执行层每轮抓数都可能用一个新的 loop（`asyncio.run` 每轮新建再关闭），
    而旧写法只判 ``_session is None or _session.closed`` ——
    第二轮拿着绑在已关闭 loop 上的 session 发请求，全部异常被
    ``except: return {}`` 吞成「这批空」，于是第一轮之后颗粒无收
    （2026-10-21 实测：首轮 9722 条，之后每轮「全部批次均未返回数据」）。
    所以这里额外记住 session 属于哪个 loop，换 loop 就重建。
    """
    global _session, _session_loop

    loop = asyncio.get_running_loop()
    if _session is not None and not _session.closed and _session_loop is not loop:
        # 旧 loop 已经关了，close() 大概率会抛；抛了就丢弃，别让它炸到调用方
        try:
            await _session.close()
        except Exception:
            pass
        _session = None

    if _session is None or _session.closed:
        import aiohttp

        _session = aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(limit=MAX_CONCURRENCY + 4, limit_per_host=MAX_CONCURRENCY),
            timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SEC),
        )
        _session_loop = loop
    return _session


async def _aclose_session() -> None:
    """关闭全局 session（必须在它所属的 loop 还活着时调用）

    ❗同步入口每轮都 ``new_event_loop`` + ``loop.close()``，而 session 是跨轮
    缓存的全局对象。如果不在这里主动关，旧 session 会带着仍打开的 connector
    被下一轮顶掉引用，随后被 GC —— asyncio 于是每轮刷两条
    ``Unclosed client session`` / ``Unclosed connector``（2026-10-21 实测：
    每 5 秒 2 条，5 分钟 500+ 条，把真正的 ERROR 全淹了）。
    """
    global _session, _session_loop
    if _session is not None and not _session.closed:
        try:
            await _session.close()
        except Exception:
            pass
    _session = None
    _session_loop = None


async def _fetch_and_cleanup(force: bool = False):
    """跑一轮，结束后关掉 session（供一次性 loop 的调用方使用）"""
    try:
        return await fetch_realtime_tick_async(force)
    finally:
        await _aclose_session()


def parse_sina_response(text: str) -> Dict[str, Dict[str, Any]]:
    """解析新浪 hq.sinajs.cn 返回

    新浪对未上市/退市的代码会返回空串，那不是错误，是「这个号不存在」——
    正是靠这一点把 5 万收敛到 5 千。
    """
    result: Dict[str, Dict[str, Any]] = {}
    for line in (text or "").strip().split("\n"):
        if '="' not in line:
            continue
        try:
            prefix, data = line.split('="', 1)
            code = prefix.split("_")[-1]
            data = data.rstrip('";')
            if not data:
                continue
            fields = data.split(",")
            # ❗别卡 len(fields) >= 33：新浪对冷门票返回的字段数本来就少，
            # 卡到 33 会把大量正常票判成无效（这里只用到前 9 个字段）。
            if len(fields) < 9:
                continue
            result[code] = {
                "name": fields[0],
                "open": float(fields[1]),
                "close": float(fields[2]),   # 昨收
                "now": float(fields[3]),     # 现价
                "high": float(fields[4]),
                "low": float(fields[5]),
                "volume": int(float(fields[8])),
            }
        except Exception:
            continue
    return result


async def _fetch_batch(codes: List[str]) -> Dict[str, Dict[str, Any]]:
    session = await _get_session()
    url = "https://hq.sinajs.cn/list=" + ",".join(codes)
    headers = {
        "Referer": "https://finance.sina.com.cn",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    try:
        async with session.get(url, headers=headers) as resp:
            if resp.status != 200:
                return {}
            return parse_sina_response(await resp.text())
    except Exception:
        # 单批失败不算整轮失败：63 批里挂 1 批不该让这一轮颗粒无收
        return {}


async def _fetch_all(codes: List[str]) -> Tuple[Dict[str, Dict[str, Any]], int]:
    """并发抓取，返回 (数据, 成功批次数)"""
    sem = asyncio.Semaphore(MAX_CONCURRENCY)
    batches = [codes[i:i + BATCH_SIZE] for i in range(0, len(codes), BATCH_SIZE)]

    async def one(batch: List[str]) -> Dict[str, Dict[str, Any]]:
        async with sem:
            return await _fetch_batch(batch)

    results = await asyncio.gather(*[one(b) for b in batches], return_exceptions=True)

    merged: Dict[str, Dict[str, Any]] = {}
    ok_batches = 0
    for r in results:
        if isinstance(r, BaseException) or not isinstance(r, dict):
            continue
        if r:
            ok_batches += 1
        merged.update(r)
    return merged, ok_batches


# ---- 过滤 --------------------------------------------------------------
def _is_non_stock(code: str, name: str) -> bool:
    if code.startswith(NON_STOCK_PREFIXES):
        return True
    return any(k in name for k in NON_STOCK_KEYWORDS)


def _is_risky(name: str) -> bool:
    return any(k in name for k in RISK_KEYWORDS)


def _is_zombie(volume: float, price: float) -> bool:
    return volume < ZOMBIE_VOLUME or price < ZOMBIE_PRICE


def filter_rows(raw: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """过滤噪音，输出可直接 emit 的行"""
    rows: List[Dict[str, Any]] = []
    for code, d in raw.items():
        name = d.get("name") or ""
        now = d.get("now") or 0.0
        close = d.get("close") or 0.0
        volume = d.get("volume") or 0
        if close <= 0 or now <= 0:
            continue
        if _is_non_stock(code, name) or _is_risky(name) or _is_zombie(volume, now):
            continue
        rows.append({
            "code": code,
            "name": name,
            "open": d.get("open"),
            "close": close,
            "now": now,
            "high": d.get("high"),
            "low": d.get("low"),
            "volume": volume,
            "p_change": round((now - close) / close, 6),
        })
    return rows


# ---- 交易时段 ----------------------------------------------------------
def _market_state(now: Optional[datetime] = None) -> Tuple[bool, str]:
    """(是否交易时段, phase 名)

    ❗phase 的合法取值是 morning / afternoon / lunch / closed，
    **没有 "trading"**。曾经这里写成 ``market_phase(...) == "trading"``，
    于是下午盘（phase=afternoon）被判成「非交易时段」直接 skip ——
    一天里有一半的盘中时间一条数据都取不到，而台账上看起来只是「按设计不取数」。
    盘中与否的唯一权威是 ``is_trading()`` / ``TRADING_PHASES``。
    """
    from deva.naja.bandit.market_session import is_trading, market_phase

    now = now or datetime.now()
    phase = str(market_phase("CN", now))
    try:
        trading = bool(is_trading("CN", now))
    except Exception:
        from deva.naja.bandit.market_session import TRADING_PHASES

        trading = phase in TRADING_PHASES
    return trading, phase


def _skip_payload(reason: str) -> Dict[str, Any]:
    """「按设计不取数」的唯一表达方式

    ❗不要用 None：执行层把 None 等价成「失败但没说原因」，于是收盘之后
    每 5 秒记一次错误，error_count 一路涨，真正的抓取失败全被淹在里面。
    """
    return {"skipped": reason, "reason": reason, "success": True}


def _fail_payload(err: str) -> Dict[str, Any]:
    return {"success": False, "error": err}


# ---- 入口 --------------------------------------------------------------
async def fetch_realtime_tick_async(force: bool = False) -> Any:
    """异步入口：返回 list[dict]（成功）/ skip 载荷 / 失败载荷"""
    now = datetime.now()
    if not force:
        trading, phase = _market_state(now)
        if not trading:
            return _skip_payload(f"非 A 股交易时段（当前 {phase}），按设计不取数")

    codes, mode = _resolve_scan_codes()
    try:
        raw, ok_batches = await asyncio.wait_for(
            _fetch_all(codes), timeout=ROUND_BUDGET_SEC
        )
    except asyncio.TimeoutError:
        return _fail_payload(
            f"整轮抓取超时（>{ROUND_BUDGET_SEC}s，{mode} 模式，{len(codes)} 个代码）"
        )
    except Exception as e:
        return _fail_payload(f"{type(e).__name__}: {e}")

    if not raw:
        # ❗一批都没返回 = 网络/源挂了，这是**失败**，不是「今天没有数据」。
        # 返回 [] 会让执行层刷新 last_data_ts（假新鲜），必须显式失败。
        return _fail_payload(
            f"全部批次均未返回数据（{mode} 模式，{len(codes)} 个代码），疑似网络或行情源不可用"
        )

    # 全量模式扫完就把有效宇宙收敛下来，之后几小时只打这份清单
    if mode == "full":
        _save_universe(list(raw.keys()))

    rows = filter_rows(raw)
    # ❗只打条数和极小样本，绝不打整份 rows：
    # 原写法把 5-6 千条 dict 全量拼进一行（单行约 730KB），
    # 2026-11-11~13 共 1783 次 × 730KB ≈ 1.3GB，占了 naja.console.log 的 99% 体积。
    # 完整行情本来就已经落库（行情表），日志里不需要第二份。
    print(
        f"{log_prefix} {mode} 模式：候选 {len(codes)} → 有数据 {len(raw)} → 过滤后 {len(rows)} 条"
        f"（成功批次 {ok_batches}）首={rows[0]['code'] if rows else '-'}"
        f" 尾={rows[-1]['code'] if rows else '-'} 样本={rows[:3]}"
    )
    return rows


@probe(KIND_DATASOURCE, "ds:realtime_tick_5s", "盘中实时行情（新浪全 A 股）", cadence="15s")
def fetch_data() -> Any:
    """同步入口（数据源 func_code 调用）

    执行层（DataSourceEntry）会在自己的线程里跑这个同步函数，
    所以内部自己建/复用一个事件循环。
    """
    try:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None and loop.is_running():
            # 已经在事件循环里 → 挪到独立线程跑，不能阻塞调用方
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                return ex.submit(asyncio.run, _fetch_and_cleanup()).result(
                    timeout=ROUND_BUDGET_SEC + 5
                )

        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(_fetch_and_cleanup())
        finally:
            # 先关 session（此时 loop 还活着），再关 loop —— 顺序反了就会漏 connector
            try:
                loop.run_until_complete(_aclose_session())
            except Exception:
                pass
            # aiohttp 的 DNS 解析走 loop.run_in_executor(None, ...)，会为这个
            # 临时循环创建默认执行器线程（asyncio_0）。loop.close() 不会关它，
            # 每轮取数都漏一个，必须显式 shutdown 才能回收（2026-11-26 实测）。
            try:
                if not loop.is_closed():
                    loop.run_until_complete(loop.shutdown_default_executor(timeout=5))
            except Exception:
                pass
            try:
                asyncio.set_event_loop(None)
            except Exception:
                pass
            try:
                loop.close()
            except Exception:
                pass
    except Exception as e:
        # ❗失败必须显式声明，别 return None 让上层猜是空还是错
        return _fail_payload(f"{type(e).__name__}: {e}")


def fetch_by_category(board: Optional[str] = None, force: bool = False) -> Any:
    """按板块取数（调试用）"""
    return fetch_data()
