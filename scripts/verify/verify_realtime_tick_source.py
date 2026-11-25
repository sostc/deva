"""守卫：realtime_tick_5s 取数实现的三条硬要求。

背景（2026-10-21 实查）：NB 里那条数据源（id=e626eecd0b86）``run_count=0``、
``total_emitted=0`` —— 从上线起一条都没产过。修复 ImportError 后依然没产，
原因是**批量设计**根本跑不完：

1. 候选宇宙按板块代码段**硬枚举**约 5 万个代码（北交所一项就 3 万个，
   实际挂牌不到 300 只），97% 的请求打在空号上；
2. 800 个/批 × 63 批是**串行** await，而执行层给整轮只有 30 秒
   （``future.result(timeout=30)``）→ 必超时 → 每轮一条 TimeoutError；
3. 早先的实现在「一批都没返回」时 ``return None``，执行层按失败计，
   而若是返回 ``[]`` 又会被当成「跑完了但没内容」刷新 last_data_ts（假新鲜）。

所以本守卫钉三件事：

· **三态不许合并** —— 非交易时段 = skip 载荷；一批都没回来 = 失败载荷；
  真拿到数据 = ``list[dict]``（能计数、能消费）。
· **必须并发** —— 串行 63 批在任何合理超时下都跑不完。
· **宇宙要收敛** —— 全量扫完必须把有效代码存下来，之后不再打 5 万个空号。
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ❗必须早于任何 deva 导入：把 NB 的落盘位置重定向到临时 sqlite，
# 免得守卫跑一遍把生产库写脏（verify_guard_db_isolation 会查这一条）。
from guard_sandbox import isolate_guard_db  # noqa: E402

isolate_guard_db()

SRC = ROOT / "deva/naja/datasource/realtime_tick.py"


# ── 替身 ────────────────────────────────────────────────────────────────
class _FakeTable(dict):
    pass


class _FakeNB:
    """``deva.NB`` 的替身：内存表，不碰磁盘。"""

    def __init__(self):
        self.tables = {}

    def __call__(self, name):
        return self.tables.setdefault(name, _FakeTable())


class _BatchRecorder:
    """``_fetch_batch`` 的替身：记录并发峰值与每批规模。

    ❗替身必须跟产品 API 同构：签名 ``async (codes: list) -> dict``，
    返回空 dict 表示「这批全空」（新浪对未上市代码就是这个行为）。
    """

    def __init__(self, data_map=None):
        self.data = data_map or {}
        self.concurrent = 0
        self.peak = 0
        self.batch_sizes = []
        self.total_codes = 0

    async def __call__(self, codes):
        self.concurrent += 1
        self.peak = max(self.peak, self.concurrent)
        self.batch_sizes.append(len(codes))
        self.total_codes += len(codes)
        try:
            await asyncio.sleep(0.01)
            return {c: dict(self.data[c]) for c in codes if c in self.data}
        finally:
            self.concurrent -= 1

    def reset(self):
        self.concurrent = 0
        self.peak = 0
        self.batch_sizes = []
        self.total_codes = 0


def _install_fake_deva(nb):
    """装一棵假的 deva 包，让被测模块只依赖我们给的替身。

    被测模块顶层会 ``from deva.naja.infra.observability.fleet_registry import
    probe``（清单探针），所以假包必须**同构**地补上这条路径，
    否则一 import 就 ModuleNotFoundError，守卫还没开始测就死了。
    """
    fake_deva = types.ModuleType("deva")
    fake_deva.NB = nb
    fake_deva.__path__ = []
    sys.modules["deva"] = fake_deva

    prev = fake_deva
    for part in ("naja", "infra", "observability"):
        name = "deva." + ".".join(("naja", "infra", "observability")[:
                                  ("naja", "infra", "observability").index(part) + 1])
        m = types.ModuleType(name)
        m.__path__ = []
        sys.modules[name] = m
        setattr(prev, part, m)
        prev = m

    reg = types.ModuleType("deva.naja.infra.observability.fleet_registry")
    reg.KIND_DATASOURCE = "datasource"

    def _probe(kind, unit_id, name, cadence="", source="probe"):
        # 替身只登记、不上报，保证守卫不写任何真实台账
        def _deco(fn):
            return fn
        return _deco

    reg.probe = _probe
    sys.modules["deva.naja.infra.observability.fleet_registry"] = reg
    setattr(prev, "fleet_registry", reg)


def _restore_real_deva():
    """把假 deva 整棵摘掉，让后面能 import 到**真**的 deva（测真实交易时段判据要用）。"""
    for k in [k for k in sys.modules if k == "deva" or k.startswith("deva.")]:
        del sys.modules[k]


def _load_module(nb=None):
    """❗不许用 import：会拿到 sys.modules 里的旧对象，改了源码守卫还是全绿。"""
    if nb is not None:
        _install_fake_deva(nb)

    spec = importlib.util.spec_from_file_location("_rtt_under_test", SRC)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载 {SRC}")
    mod = importlib.util.module_from_spec(spec)
    # ❗先占位再 exec：否则 @dataclass 解析 KW_ONLY 会抛
    # 'NoneType' object has no attribute '__dict__'
    sys.modules["_rtt_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


def _sample_rows(n=3):
    """构造新浪风格的正常数据"""
    return {
        "sh600000": {"name": "浦发银行", "open": 10.0, "close": 10.0,
                     "now": 10.5, "high": 10.6, "low": 9.9, "volume": 500000},
        "sz000001": {"name": "平安银行", "open": 11.0, "close": 11.0,
                     "now": 10.8, "high": 11.2, "low": 10.7, "volume": 300000},
        "sh688001": {"name": "华兴源创", "open": 30.0, "close": 30.0,
                     "now": 31.0, "high": 31.5, "low": 29.8, "volume": 80000},
    }


def _all_checks() -> list:
    fails: list = []
    nb = _FakeNB()
    mod = _load_module(nb)
    rec = _BatchRecorder(_sample_rows())

    def setup(data_map=None, trading=True, phase="trading"):
        # ❗每个用例都从干净 NB 开始：有效宇宙会跨调用持久化，
        # 上一个用例写进去的缓存会让下一个用例只打 1 个代码，
        # 于是「正常票被误杀」这类假失败全靠污染凑出来。
        nb.tables.clear()
        rec.data = data_map if data_map is not None else _sample_rows()
        rec.reset()
        mod._fetch_batch = rec
        mod._market_state = lambda now=None: (trading, phase)
        # ❗候选必须多于一个批次（800），否则只有 1 批，
        # 「并发峰值 > 1」永远测不出来，守卫变成摆设。
        mod.candidate_codes = lambda: ["sh%06d" % i for i in range(600000, 602000)]

    def run(**kw):
        return asyncio.run(mod.fetch_realtime_tick_async(**kw))

    # ── 1. 非交易时段 → skip 载荷，绝不能是 None / 失败 ──────────────────
    try:
        setup(trading=False, phase="closed")
        res = run()
        if res is None:
            fails.append(
                "非交易时段返回了 None —— 执行层按失败计，error_count 会一路涨，"
                "真正的抓取失败被淹在里面（历史上 error_count=229 就是这么来的）"
            )
        elif not isinstance(res, dict) or not res.get("skipped"):
            fails.append(f"非交易时段应当返回 skip 载荷，实际 {type(res).__name__}: {str(res)[:80]}")
        elif res.get("success") is not True:
            fails.append("skip 载荷必须带 success=True，否则被判成失败")
    except Exception as e:  # noqa: BLE001
        fails.append(f"非交易时段用例无法执行：{type(e).__name__}: {e}")

    # ── 2. 一批都没回来 = 失败，不是「跑完了但没内容」 ───────────────────
    try:
        setup(data_map={})
        res = run()
        if isinstance(res, list):
            fails.append(
                "全部批次空返回了 list —— 执行层会刷新 last_data_ts 并记「0 条」，"
                "页面显示「刚刚有数据」而实际是网络/行情源挂了（假新鲜）"
            )
        elif not isinstance(res, dict) or res.get("success") is not False:
            fails.append(f"全批失败必须返回 success=False 的失败载荷，实际 {str(res)[:80]}")
        elif not res.get("error"):
            fails.append("失败载荷没带 error 原因，日志里查不出到底哪坏了")
    except Exception as e:  # noqa: BLE001
        fails.append(f"全批失败用例无法执行：{type(e).__name__}: {e}")

    # ── 3. 成功 → list[dict]，字段能被下游消费 ───────────────────────────
    try:
        setup()
        res = run()
        if not isinstance(res, list):
            fails.append(f"成功时应当返回 list[dict]，实际 {type(res).__name__}")
        elif not res:
            fails.append("有数据却返回了空列表")
        else:
            row = res[0]
            for key in ("code", "name", "now", "close", "p_change"):
                if key not in row:
                    fails.append(f"产出行缺少字段 {key}（下游按这个取数）")
            if not isinstance(row.get("code"), str):
                fails.append(f"code 字段类型异常：{type(row.get('code')).__name__}")
    except Exception as e:  # noqa: BLE001
        fails.append(f"成功用例无法执行：{type(e).__name__}: {e}")

    # ── 4. 必须并发：串行 63 批在任何合理超时下都跑不完 ──────────────────
    try:
        setup()
        run()
        if rec.peak <= 1:
            fails.append(
                f"抓取是串行的（并发峰值={rec.peak}）—— 63 批 × 单请求耗时 "
                "必然撞上执行层 30s 超时，这是 realtime_tick_5s 长期产出 0 的直接原因"
            )
    except Exception as e:  # noqa: BLE001
        fails.append(f"并发用例无法执行：{type(e).__name__}: {e}")

    # ── 5. 宇宙要收敛：全量扫完存下来，之后不再打空号 ────────────────────
    try:
        setup()
        run()
        first_total = rec.total_codes
        table = nb.tables.get(mod.UNIVERSE_TABLE, {})
        saved = table.get(mod.UNIVERSE_KEY)
        if not saved or not saved.get("codes"):
            fails.append(
                "全量扫描后没把有效宇宙写回 NB —— 下一轮还得打 5 万个空号，"
                "等于每轮都做一次全量（超时风险不降）"
            )
        else:
            rec.reset()
            run()  # 第二轮应当走缓存
            if rec.total_codes >= first_total and len(saved["codes"]) < first_total:
                fails.append(
                    f"第二轮仍打了 {rec.total_codes} 个代码（首轮 {first_total}），"
                    f"有效宇宙只有 {len(saved['codes'])} 个 —— 缓存没生效"
                )
    except Exception as e:  # noqa: BLE001
        fails.append(f"宇宙收敛用例无法执行：{type(e).__name__}: {e}")

    # ── 6. 过滤要生效：ST / 僵尸票 / 非个股 不许进产出 ───────────────────
    try:
        data = {
            "sh600001": {"name": "ST某某", "open": 1, "close": 1, "now": 1.1,
                         "high": 1.2, "low": 1.0, "volume": 500000},
            "sh600002": {"name": "僵尸票", "open": 2, "close": 2, "now": 0.3,
                         "high": 2, "low": 0.3, "volume": 50},
            "sh600003": {"name": "沪深300ETF", "open": 3, "close": 3, "now": 3.1,
                         "high": 3.2, "low": 3.0, "volume": 500000},
            "sh600004": {"name": "正常票", "open": 5, "close": 5, "now": 5.2,
                         "high": 5.3, "low": 4.9, "volume": 200000},
        }
        setup(data_map=data)
        res = run()
        codes = [r["code"] for r in res] if isinstance(res, list) else []
        if "sh600001" in codes:
            fails.append("ST 股没被过滤掉（风险股应剔除）")
        if "sh600002" in codes:
            fails.append("僵尸票没被过滤掉（量价异常应剔除）")
        if "sh600003" in codes:
            fails.append("非个股（ETF/指数）没被过滤掉")
        if "sh600004" not in codes:
            fails.append(f"正常票被误杀了，产出只剩 {codes}")
    except Exception as e:  # noqa: BLE001
        fails.append(f"过滤用例无法执行：{type(e).__name__}: {e}")

    # ── 7. 真实交易时段判据：下午盘必须算盘中 ────────────────────────────
    # ❗这条不 mock _market_state —— mock 掉就永远测不到真实判据。
    # 曾经写成 market_phase(...) == "trading"，而合法 phase 只有
    # morning / afternoon / lunch / closed，于是下午盘天天被当收盘 skip。
    try:
        from datetime import datetime as _dt
        from zoneinfo import ZoneInfo

        # ❗前面为了测宇宙收敛把整棵 deva 都换成了假模块（含
        # deva.naja.infra.observability.fleet_registry），这里要测**真实**的
        # market_session，必须把假的整棵摘掉、让 import 走到真的包。
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        _restore_real_deva()
        import deva as _real_deva  # noqa: F401  （触发真实包初始化）

        tz = ZoneInfo("Asia/Shanghai")
        # ❗传 None：别再把 deva 换成假模块，否则 market_session 还是导入不到
        fresh = _load_module(None)
        cases = [
            ("周三 10:30（早盘）", _dt(2026, 10, 21, 10, 30, tzinfo=tz), True),
            ("周三 14:00（下午盘）", _dt(2026, 10, 21, 14, 0, tzinfo=tz), True),
            ("周三 12:30（午休）", _dt(2026, 10, 21, 12, 30, tzinfo=tz), False),
            ("周三 08:00（开盘前）", _dt(2026, 10, 21, 8, 0, tzinfo=tz), False),
            ("周六 10:30", _dt(2026, 10, 24, 10, 30, tzinfo=tz), False),
        ]
        for label, when, expect in cases:
            trading, phase = fresh._market_state(when)
            if trading != expect:
                fails.append(
                    f"{label} 判定为 trading={trading}（phase={phase}），"
                    f"应为 {expect} —— 判错就会一整个时段取不到数"
                )
    except Exception as e:  # noqa: BLE001
        fails.append(f"交易时段判据用例无法执行：{type(e).__name__}: {e}")

    # ── 8. 换 event loop 必须重建 session ────────────────────────────────
    # ❗aiohttp session 绑在创建它的 loop 上。执行层每轮抓数可能用新 loop，
    # 旧写法只判 ``is None or closed`` → 第二轮起拿着绑在已关闭 loop 上的
    # session 发请求，全被 except 吞成「这批空」，于是首轮之后颗粒无收。
    try:
        fresh2 = _load_module(None)

        async def probe():
            s = await fresh2._get_session()
            return id(s)

        a = asyncio.run(probe())
        b = asyncio.run(probe())
        if a == b:
            fails.append(
                "第二个 event loop 复用了同一个 aiohttp session —— "
                "旧 loop 已关闭，请求会全部失败，首轮之后再也取不到数"
            )
    except Exception as e:  # noqa: BLE001
        fails.append(f"session 复用用例无法执行：{type(e).__name__}: {e}")

    return fails


def _injections() -> list:
    """负向注入：坏版本必须被抓到，且失败原因各不相同。"""
    results = []
    nb = _FakeNB()
    mod = _load_module(nb)

    # 坏版本 A：全批失败时返回 []（假新鲜）
    async def bad_empty(force=False):
        return []

    # 坏版本 B：串行抓取（并发峰值=1）
    async def bad_serial(force=False):
        codes = mod.candidate_codes()
        sem = asyncio.Semaphore(1)
        rec = _BatchRecorder(_sample_rows())

        async def one(b):
            async with sem:
                return await rec(b)

        out = {}
        for i in range(0, len(codes), 800):
            out.update(await one(codes[i:i + 800]))
        return mod.filter_rows(out)

    # 坏版本 C：非交易时段返回 None
    async def bad_none(force=False):
        return None

    cases = [
        ("全批失败返回 []（假新鲜）", bad_empty,
         lambda r: isinstance(r, list)),
        ("串行抓取（并发峰值=1）", bad_serial, None),
        ("非交易时段返回 None", bad_none,
         lambda r: r is None),
    ]

    for label, impl, predicate in cases:
        rec = _BatchRecorder(_sample_rows())
        mod._fetch_batch = rec
        mod._market_state = lambda now=None: (True, "trading")
        mod.fetch_realtime_tick_async = impl
        try:
            if label.startswith("串行"):
                asyncio.run(impl())
                bad = rec.peak <= 1
            else:
                res = asyncio.run(impl())
                bad = predicate(res) if predicate else False
            results.append((label, bad))
        except Exception:
            results.append((label, True))
    return results


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exercise-injections", action="store_true")
    args = ap.parse_args()

    if args.exercise_injections:
        results = _injections()
        print("=== 负向注入（坏版本必须被抓到）===")
        ok = 0
        for label, bad in results:
            print(f"  {'✅ 抓到' if bad else '❌ 漏了'}  {label}")
            if bad:
                ok += 1
        print(f"注入检出 {ok}/{len(results)}")
        return 0 if ok == len(results) else 1

    fails = _all_checks()
    if fails:
        print("❌ 守卫失败：")
        for f in fails:
            print(f"   - {f}")
        return 1
    print("✅ realtime_tick 三态语义 / 并发 / 宇宙收敛 / 过滤 均正确")
    return 0


if __name__ == "__main__":
    sys.exit(main())
