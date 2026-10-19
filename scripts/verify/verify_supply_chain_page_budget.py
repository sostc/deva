#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""守卫：``/supplychain`` 页面的加载预算，以及「失败不许假装加载中」。

背景（2026-10-19）
----------------
打开供应链页会卡 2~3 秒。根因不是渲染慢，是**请求线程在串行打 39 次 HTTP**，
而其中 27 只 A 股永远拿不到数据（东方财富被本机代理拒了），失败又不写缓存，
于是每次打开都把这 29 次注定失败的请求重放一遍。

修法是四件事，本守卫逐一钉死，防止被改回去：

① **负缓存**：失败的股票也要记住（TTL 300s），第二次起不再打网络。
   没有它，页面每开一次就重放一遍失败请求——这是 2.5 秒的**经常性**来源。
② **并发**：批量抓取走线程池，墙钟时间由最慢的一个决定，而不是全部之和。
③ **估值摘要只算一遍**：``get_valuation_summary`` 原来把 ``analyze_all_stocks``
   调了 3 遍（自己 + 低估榜 + 高估榜），实测 9.8s；现在算一遍 + 结果缓存。
④ **失败必须上屏**：拿不到数据时写**原因**（源名 + 异常），不许写「加载中」。
   顺带钉住 ``deva.naja.bandit`` 真的导出了估值引擎——它曾经只在 ``__all__``
   里写了名字、真实 import 缺失，导致估值面板死在 except 里没人发现。

❗为什么判据全用「调用了几次」而不是「花了多少秒」
------------------------------------------------
墙钟时间受代理快慢、机器负载影响，会把守卫变成 flaky 的摆设。
这里每条都用**可计数的确定性判据**：网络调用次数、并发峰值、重算次数。

用法
----
    python scripts/verify/verify_supply_chain_page_budget.py
    python scripts/verify/verify_supply_chain_page_budget.py --strict
    python scripts/verify/verify_supply_chain_page_budget.py --exercise-injections
"""

from __future__ import annotations

import argparse
import ast
import importlib
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FETCHER_PY = ROOT / "deva/naja/bandit/fundamental_data_fetcher.py"
VALUATION_PY = ROOT / "deva/naja/bandit/supply_chain_valuation.py"
MARKET_UI_PY = ROOT / "deva/naja/attention/ui/supply_chain/market_data.py"
BANDIT_INIT_PY = ROOT / "deva/naja/bandit/__init__.py"
CONTAINER_PY = ROOT / "deva/naja/application/container.py"

#: 一只永远拿不到数据的 A 股（构造出来只用于走失败分支，不发真实请求）
DEAD_A_CODE = "600519"


def _fetcher_module():
    return importlib.reload(importlib.import_module("deva.naja.bandit.fundamental_data_fetcher"))


def _valuation_module():
    return importlib.reload(importlib.import_module("deva.naja.bandit.supply_chain_valuation"))


def _market_ui_module():
    return importlib.reload(
        importlib.import_module("deva.naja.attention.ui.supply_chain.market_data")
    )


# ── ① 负缓存：失败的股票第二次不再打网络 ──────────────────────────────────────
def check_negative_cache() -> list:
    """同一只失败的股票，连续两次 get_fundamental 只能发一次网络请求。"""
    M = _fetcher_module()
    failures: list = []

    f = M.FundamentalDataFetcher()
    calls = {"n": 0}

    def always_fail(code):
        calls["n"] += 1
        return None

    f._fetch_a_stock = always_fail

    f.get_fundamental(DEAD_A_CODE)
    after_first = calls["n"]
    f.get_fundamental(DEAD_A_CODE)
    after_second = calls["n"]

    if after_first != 1:
        failures.append(
            f"负缓存守卫自身失效：第一次就该发 1 次请求，实际 {after_first} 次"
        )
    if after_second != 1:
        failures.append(
            f"❗负缓存没生效：同一只失败股票第二次又发了 {after_second - after_first} 次请求 "
            "—— 每次打开页面都会重放注定失败的 HTTP（这就是那 2.5 秒）"
        )
    return failures


# ── ② 并发：批量抓取必须是并发的 ──────────────────────────────────────────────
def check_batch_is_concurrent() -> list:
    """get_batch_fundamentals 的并发峰值必须 > 1，否则 39 只股票就是 39 次串行。"""
    M = _fetcher_module()
    failures: list = []

    f = M.FundamentalDataFetcher()
    stat = {"cur": 0, "peak": 0}
    lock = threading.Lock()

    def slow(code):
        with lock:
            stat["cur"] += 1
            stat["peak"] = max(stat["peak"], stat["cur"])
        time.sleep(0.06)
        with lock:
            stat["cur"] -= 1
        return None

    f.get_fundamental = slow
    f.get_batch_fundamentals([f"c{i}" for i in range(8)])

    if stat["peak"] < 2:
        failures.append(
            f"❗批量抓取退化成串行（并发峰值 {stat['peak']}）—— "
            "39 只股票的墙钟时间会重新变成全部之和"
        )
    return failures


# ── ③ 估值摘要只算一遍 ────────────────────────────────────────────────────────
def check_valuation_single_pass() -> list:
    """get_valuation_summary 期间 analyze_all_stocks 只能被调用 1 次。"""
    M = _valuation_module()
    failures: list = []

    engine = M.SupplyChainValuationEngine()
    calls = {"n": 0}

    def counting(force_refresh: bool = False):
        calls["n"] += 1
        return {}

    engine.analyze_all_stocks = counting
    engine.get_valuation_summary()

    if calls["n"] != 1:
        failures.append(
            f"❗估值摘要把全量分析跑了 {calls['n']} 遍（应为 1）—— "
            "每遍都是 39 只股票全量算四个维度，实测 3 遍要 9.8 秒"
        )
    return failures


def check_valuation_result_cached() -> list:
    """TTL 内的 analyze_all_stocks 不得重算（命中缓存就直接返回）。"""
    M = _valuation_module()
    failures: list = []

    engine = M.SupplyChainValuationEngine()
    sentinel = object()
    engine._analysis_cache = {"SENTINEL": sentinel}
    engine._analysis_ts = time.time()

    got = engine.analyze_all_stocks()
    if got.get("SENTINEL") is not sentinel:
        failures.append(
            "❗估值结果缓存没生效：TTL 内仍触发了全量重算（页面每次开都要重算 39 只）"
        )
    return failures


# ── ④ 失败必须上屏，不许写「加载中」 ──────────────────────────────────────────
def check_failure_reason_is_visible() -> list:
    """空数据 / 异常时，页面要写原因，不能写「加载中」。"""
    failures: list = []
    M = _market_ui_module()

    import deva.naja.bandit as bandit_pkg

    class _DeadFetcher:
        """一只都拿不到的抓取器，用来逼出空态文案。"""

        def get_supply_chain_fundamentals(self):
            return {}

        def get_fetch_diagnostics(self):
            return {
                "total": 39,
                "ok": 0,
                "failed": {DEAD_A_CODE: "eastmoney 不可达：ProxyError"},
                "failed_count": 39,
                "source_errors": {"eastmoney": "ProxyError: 代理拒绝连接"},
            }

    orig_fetcher = bandit_pkg.get_fundamental_data_fetcher
    orig_valuation = bandit_pkg.get_supply_chain_valuation_engine
    try:
        bandit_pkg.get_fundamental_data_fetcher = lambda: _DeadFetcher()
        html = M._render_realtime_market_data()
        if "加载中" in html:
            failures.append(
                "❗行情空态还在写「加载中」—— 数据源挂了和正在加载是两回事，"
                "这么写会让故障永远看起来像「再等等」"
            )
        if "不可达" not in html:
            failures.append("❗行情空态没写失败原因（应出现数据源错误/不可达提示）")

        def _boom():
            raise ImportError("cannot import name 'get_supply_chain_valuation_engine'")

        bandit_pkg.get_supply_chain_valuation_engine = _boom
        vhtml = M._render_valuation_analysis()
        if "加载中" in vhtml:
            failures.append(
                "❗估值面板异常时还在写「加载中」—— 导入断裂曾被这么吞掉半年没人发现"
            )
        if "ImportError" not in vhtml:
            failures.append("❗估值面板异常时没把真实异常类型写出来")
    finally:
        bandit_pkg.get_fundamental_data_fetcher = orig_fetcher
        bandit_pkg.get_supply_chain_valuation_engine = orig_valuation

    return failures


# ── ⑤ 估值引擎的导出不许再断 ──────────────────────────────────────────────────
def check_valuation_export_not_broken() -> list:
    """``from deva.naja.bandit import get_supply_chain_valuation_engine`` 必须成真。

    曾经只在 ``__all__`` 里写了名字、真实 import 缺失 —— 页面 200、面板空白、
    异常被 except 吞掉。这里用 AST 查真实 import（不靠 sys.modules），
    再补一次真导入当冒烟。
    """
    failures: list = []
    src = BANDIT_INIT_PY.read_text(encoding="utf-8")
    tree = ast.parse(src)

    imported = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").endswith(
            "supply_chain_valuation"
        ):
            if any(a.name == "get_supply_chain_valuation_engine" for a in node.names):
                imported = True

    if not imported:
        failures.append(
            "❗deva/naja/bandit/__init__.py 没有真实导入 get_supply_chain_valuation_engine "
            "（只在 __all__ 里写了名字不算）—— 供应链页估值面板会静默死掉"
        )
        return failures

    try:
        from deva.naja.bandit import get_supply_chain_valuation_engine  # noqa: F401
    except Exception as e:  # noqa: BLE001
        failures.append(
            f"❗估值引擎导入失败：{type(e).__name__}: {e}"
        )
    return failures


# ── ⑥ 启动预热：重启后第一次打开也不许慢 ─────────────────────────────────────
def check_startup_warmup() -> list:
    """服务启动时要预热供应链页，且预热不许进 tasks（不参与启动超时判定）。

    ❶ 缓存全是**进程内存**，重启即清空 —— 光靠缓存解决不了「重启后第一次慢」。
    ❷ 那 5 秒里 4.7 秒是模块首次 import，而 import **没法缓存**，只能提前付。
    ❸ 预热放进 tasks 会被启动超时判定当成「服务残缺」报 ERROR —— 它慢了只该
       让页面自己现抓一次，不该误报服务不健康。
    """
    failures: list = []
    src = CONTAINER_PY.read_text(encoding="utf-8")
    tree = ast.parse(src)

    func = next(
        (n for n in ast.walk(tree)
         if isinstance(n, ast.FunctionDef) and n.name == "init_supply_chain_page"),
        None,
    )
    if func is None:
        return ["❗AppContainer 里没有 init_supply_chain_page —— "
                "服务重启后第一次打开供应链页要付约 5 秒（4.7 秒是模块 import）"]

    lo = func.lineno
    hi = func.end_lineno or func.lineno

    # tasks 字典的范围：预热引用落在里面就说明它被塞进了超时判定
    tasks_lo = tasks_hi = -1
    for n in ast.walk(tree):
        if isinstance(n, ast.Assign) and isinstance(n.value, ast.Dict):
            if any(isinstance(t, ast.Name) and t.id == "tasks" for t in n.targets):
                tasks_lo = n.lineno
                tasks_hi = n.end_lineno or n.lineno

    # ❗判据必须是「真的被 .start() 起线程了」，不是「被引用了」。
    # 只查引用的话，把 `).start()` 删掉（线程建了不启动）照样全绿 —— 摆设一条。
    refs = []
    started = False
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "start":
            for sub in ast.walk(n):
                if isinstance(sub, ast.Name) and sub.id == "init_supply_chain_page":
                    started = True
        if isinstance(n, ast.Name) and n.id == "init_supply_chain_page" \
                and isinstance(n.ctx, ast.Load) and not (lo <= n.lineno <= hi):
            refs.append(n)

    if not refs:
        failures.append(
            "❗init_supply_chain_page 定义了但没人调用（代码变孤儿）—— "
            "重启后第一次打开供应链页仍会慢约 5 秒"
        )
    elif not started:
        failures.append(
            "❗init_supply_chain_page 被引用了但没有 .start()（线程建了不启动）—— "
            "预热永远不会执行，重启后第一次打开供应链页仍会慢约 5 秒"
        )

    if tasks_lo > 0 and any(tasks_lo <= r.lineno <= tasks_hi for r in refs):
        failures.append(
            "❗预热被塞进 tasks 字典 —— 它会参与启动超时判定，卡住就被报成"
            "「服务以残缺状态运行」。预热慢只该让那页自己现抓，不该误报服务健康。"
        )
    return failures


def _all_checks() -> list:
    failures: list = []
    failures += check_negative_cache()
    failures += check_batch_is_concurrent()
    failures += check_valuation_single_pass()
    failures += check_valuation_result_cached()
    failures += check_failure_reason_is_visible()
    failures += check_valuation_export_not_broken()
    failures += check_startup_warmup()
    return failures


# ── 负向注入：证明守卫真的在守 ────────────────────────────────────────────────
#: ❗锚点全部落在**真被执行**的分支上，命中数必须恰好为 1。
INJECTIONS = [
    {
        "name": "关掉负缓存（每次打开页面重放失败请求 → 那 2.5 秒回来）",
        "path": FETCHER_PY,
        "old": "            if self._negative_cache_enabled:",
        "new": "            if False:",
    },
    {
        "name": "并发退化成串行（39 只股票重新变成全部之和）",
        "path": FETCHER_PY,
        "old": "                raw = list(pool.map(self.get_fundamental, stock_codes))",
        "new": "                raw = [self.get_fundamental(c) for c in stock_codes]",
    },
    {
        "name": "估值摘要不再复用分析结果（全量分析跑 3 遍）",
        "path": VALUATION_PY,
        "old": "        undervalued = self.get_top_undervalued(3, results=all_results)",
        "new": "        undervalued = self.get_top_undervalued(3)",
    },
    {
        "name": "估值结果缓存失效（TTL 内也重算）",
        "path": VALUATION_PY,
        "old": "            and _time.time() - self._analysis_ts < self._update_interval",
        "new": "            and False",
    },
    {
        "name": "行情空态改回「加载中」（故障看起来像再等等）",
        "path": MARKET_UI_PY,
        "old": '                "行情源不可达 —— 全部股票都取不到数据</div>"',
        "new": '                "实时行情加载中...</div>"',
    },
    {
        "name": "删掉 bandit 对估值引擎的真实 import（面板静默死掉）",
        "path": BANDIT_INIT_PY,
        "old": "from .supply_chain_valuation import (",
        "new": "from .tuner import (",
    },
    {
        "name": "预热函数定义了但没起线程（重启后第一次打开又慢回 5 秒）",
        "path": CONTAINER_PY,
        "old": '                name="naja-init-supplychain-warm", daemon=True,\n            ).start()',
        "new": '                name="naja-init-supplychain-warm", daemon=True,\n            )',
    },
    {
        "name": "预热塞进 tasks（卡住会被误报成服务残缺）",
        "path": CONTAINER_PY,
        "old": '                "调度器": init_schedulers,',
        "new": '                "调度器": init_schedulers,\n                "供应链页预热": init_supply_chain_page,',
    },
]


def run_injections() -> int:
    caught = 0
    missed: list = []
    for inj in INJECTIONS:
        path: Path = inj["path"]
        original = path.read_text(encoding="utf-8")
        hits = original.count(inj["old"])
        if hits != 1:
            missed.append(inj["name"])
            print(f"❌ 注入锚点命中 {hits} 次（期望 1，守卫腐烂信号）：{inj['name']}")
            continue
        print(f"· 注入：{inj['name']}")
        path.write_text(original.replace(inj["old"], inj["new"]), encoding="utf-8")
        try:
            found = _all_checks()
        except Exception as e:  # noqa: BLE001
            found = [f"守卫自身抛异常: {type(e).__name__}: {e}"]
        finally:
            path.write_text(original, encoding="utf-8")
        if found:
            caught += 1
            print(f"  ✅ 被捕获（{len(found)} 项）")
            print(f"       · {found[0][:110]}")
        else:
            print("  ❌ 没抓到 —— 这条守卫是摆设！")
        if path.read_text(encoding="utf-8") != original:
            print("  🚨 还原失败，强制重写")
            path.write_text(original, encoding="utf-8")
    print(f"\n负向注入：{caught}/{len(INJECTIONS)} 被捕获"
          + (f"（另有 {len(missed)} 条锚点未命中，已计失败）" if missed else ""))
    return caught


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--exercise-injections", action="store_true")
    args = ap.parse_args()

    if args.exercise_injections:
        ok = run_injections() == len(INJECTIONS)
        return 0 if ok else 1

    failures = _all_checks()
    if failures:
        print("❌ 供应链页加载预算守卫 失败：")
        for f in failures:
            print(f"   - {f}")
        return 1 if args.strict else 0
    print("✅ 供应链页加载预算守卫全绿"
          "（负缓存·并发·估值只算一遍且带缓存·失败写原因·估值引擎导出未断）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
