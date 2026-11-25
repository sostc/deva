"""守卫：首页「数据源 / 策略」的清单必须是**全系统**的，不许再漏。

背景（2026-10-20 实测）：

首页数据源卡原来只有 5 个（DatasourceManager 注册的 yaml），策略卡只有 17 个
（StrategyManager 注册的 yaml）。但系统里：

- 热点策略体系十几个**正在跑并向 TradingCenter 送信号**的策略，因为汇入代码里
  ``from deva.naja.strategy import get_hotspot_manager`` 这个名字根本不存在 +
  外层 ``except: pass``，一个都没进 StrategyManager —— 首页完全看不到；
- 十几个散落取数器（新浪行情总线、美股价格、富途同步、FRED、SEC/东财、IMA、
  文章监控…）压根不在任何清单里。

修好这两处之后，真正的问题变成：**怎么保证下次新增取数点不会再漏？**
靠人记得回来改首页是不可能的。所以本守卫把「漏登记」变成**守卫失败**：

    A. 扫全仓含外部网络库 import 的模块，断言每个都**已登记**（挂了探针或声明登记），
       或在 ALLOWLIST 里且写明原因；
    B. 扫描命中数必须 >= MIN_SCAN —— 否则是正则失效导致「空扫描假绿」；
    C. 登记册的四态守恒、unknown 必须带原因、适配器失败必须留痕、热点兜底不重复计数。

负向注入把 A/B/C 各破坏一次，确认断言真的会红。
"""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import re
import sys
import time
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REGISTRY_PATH = ROOT / "deva/naja/infra/observability/fleet_registry.py"

NET_RE = re.compile(
    r"^\s*(?:import\s+(?:requests|httpx|aiohttp|urllib|websocket|websockets)\b"
    r"|from\s+(?:requests|httpx|aiohttp|urllib|websocket|websockets)\s+import\b)",
    re.M,
)
#: 登记标记：挂了探针或做了声明式登记
REGISTERED_RE = re.compile(r"@probe\s*\(|declare_manifest_unit\s*\(")

EXCLUDE_DIRS = ("tests", "scripts", "skills", "examples", "docs",
                "__pycache__", "desktop", "archive")

#: 扫描命中数的下限。❗没有这条，正则一旦失效就会「0 命中 → 0 缺失 → 全绿」，
#: 守卫变成摆设 —— 这比没有守卫更危险（假绿会让人以为在守）。
MIN_SCAN = 15

#: 有网络库 import 但**不是取数点**的模块。每条必须写清原因，
#: 原因写不出来就说明它其实该登记，别往这里塞。
ALLOWLIST = {
    "deva/naja/__main__.py": "进程入口，只装配不取数",
    "deva/naja/bandit/portfolio_manager.py": (
        "不直接取数：券商数据由 futu_portfolio_syncer（ds:futu_account）同步，"
        "行情经 GlobalMarketAPI（ds:global_futures）"
    ),
    "deva/naja/cognition/openrouter_monitor.py": (
        "是数据源体系内 OpenRouter_TOKEN_消耗 的实现体，且首页另有「算力消耗」卡单独呈现"
    ),
    "deva/naja/datasource/plugins/jin10_fetcher.py": "数据源体系内的插件，随体系条目一起统计",
    "deva/naja/infra/ui/menu_bar_tray.py": "托盘图标的连通性探测，非业务取数",
    "deva/naja/market_hotspot/data/sina_parser.py": "纯解析器，不发请求",
    "deva/naja/market_hotspot/integration/market_hotspot_system.py": "编排层，取数由下层 fetcher 完成",
    "deva/naja/state/system/server_sync_handler.py": "远端状态同步（运维通道），不参与决策链路",
    "deva/naja/state/system/wake_sync_handlers.py": "唤醒补作业编排，取数由下属单元完成",
    "deva/naja/web_ui/routes.py": "HTTP 服务端，不对外取数",
}


def _load_registry_module():
    """❗不许用 import：那会拿到 sys.modules 里的旧对象，注入的新代码根本没读进来
    （全绿但什么都没守）。必须 spec 重加载，且**先登记 sys.modules 再 exec_module**
    —— 反过来的话模块内的 @dataclass 解析会抛 'NoneType' has no attribute '__dict__'。
    """
    spec = importlib.util.spec_from_file_location(
        "deva.naja.infra.observability.fleet_registry", REGISTRY_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _scan_network_modules() -> list[str]:
    base = ROOT / "deva/naja"
    hits = []
    for p in sorted(base.rglob("*.py")):
        rel = p.relative_to(ROOT).as_posix()
        if any(f"/{d}/" in rel for d in EXCLUDE_DIRS) or rel.endswith(".bak"):
            continue
        try:
            txt = p.read_text(encoding="utf-8")
        except Exception:
            continue
        if NET_RE.search(txt):
            hits.append(rel)
    return hits


def _registered_modules(hits) -> set[str]:
    return {rel for rel in hits
            if REGISTERED_RE.search((ROOT / rel).read_text(encoding="utf-8"))}


def _all_checks() -> list[str]:
    fails: list[str] = []
    F = _load_registry_module()

    # ── A. 完整性：每个取数模块都必须已登记或在 allowlist ──
    hits = _scan_network_modules()
    if len(hits) < MIN_SCAN:
        fails.append(
            f"只扫到 {len(hits)} 个含网络库 import 的模块（下限 {MIN_SCAN}）——"
            "极可能是扫描正则失效，此时「0 缺失」是假绿")
    registered = _registered_modules(hits)
    missing = [rel for rel in hits if rel not in registered and rel not in ALLOWLIST]
    for rel in missing:
        fails.append(
            f"取数模块未登记：{rel} —— 挂 @probe(...) 或 declare_manifest_unit(...)，"
            "否则首页数据源卡永远看不到它")

    # allowlist 里的路径必须真实存在（防止写错路径让判据悄悄失效）
    for rel in ALLOWLIST:
        if not (ROOT / rel).exists():
            fails.append(f"ALLOWLIST 里的路径不存在：{rel}")
        if not ALLOWLIST[rel].strip():
            fails.append(f"ALLOWLIST 条目缺原因：{rel}")

    # ── B. 四态守恒 + unknown 必须带原因 ──
    reg = F.FleetRegistry()
    now = time.time()
    reg.declare(F.UnitCard("a", F.KIND_DATASOURCE, "A", "probe", F.ST_RUNNING,
                           last_success_ts=now))
    reg.declare(F.UnitCard("b", F.KIND_DATASOURCE, "B", "probe", F.ST_STOPPED))
    reg.declare(F.UnitCard("c", F.KIND_DATASOURCE, "C", "probe", F.ST_UNKNOWN,
                           note="读不到状态"))
    reg.declare(F.UnitCard("d", F.KIND_DATASOURCE, "D", "probe", F.ST_SKIPPED,
                           note="收盘"))
    s = reg.summarize(F.KIND_DATASOURCE)
    if s["total"] != 4:
        fails.append(f"四态合计不等于总数：{s}")
    if s["running"] + s["stopped"] + s["unknown"] + s["skipped"] != s["total"]:
        fails.append(f"四态守恒被破坏：{s}")

    # ❗unknown 没有 note 就等于「不知道为什么不知道」—— 与写 0 同罪
    for card in reg.snapshot(kind=F.KIND_DATASOURCE):
        if card.state == F.ST_UNKNOWN and not card.note:
            fails.append(f"unknown 状态的 {card.unit_id} 没有写原因（note 为空）")

    # 探针比登记先跑时自动补的那张卡，也必须带原因（注入 2 打的就是这里）
    reg.report("probe:auto_created", ok=False, error=RuntimeError("boom"))
    auto = reg.get("probe:auto_created")
    if auto is None:
        fails.append("探针先于登记触发时没有自动补卡，事实会丢")
    elif not auto.note:
        fails.append("自动补的卡没有写原因（note 为空）")

    # ── C. 陈旧度必须「读取时算」，不能存结论 ──
    c = reg.get("a")
    s_before = reg.summarize(F.KIND_DATASOURCE, stale_after=3600)
    c.last_success_ts = now - 10 * 3600     # 同一张卡，只改事实
    s_after = reg.summarize(F.KIND_DATASOURCE, stale_after=3600)
    if "a" in [x.unit_id for x in s_before["stale"]]:
        fails.append("刚成功的卡被判成停更")
    if "a" not in [x.unit_id for x in s_after["stale"]]:
        fails.append("改了 last_success_ts 后停更判据没变 —— 说明结论被存下来了")

    # ── C2. 适配器失败必须留痕，不许静默 ──
    def _boom(*a, **k):
        raise RuntimeError("datasource manager 挂了")
    reg2 = F.FleetRegistry()
    with mock.patch("deva.naja.datasource.get_datasource_manager", _boom):
        n = F.collect_datasource_units(reg2)
    if n != 0:
        fails.append(f"适配器抛异常却返回了 {n} 条")
    status = reg2.all_sources().get("datasource_mgr")
    if not status or status.get("ok") is not False or not status.get("error"):
        fails.append(f"适配器失败没有落 source_status（静默）：{status}")

    # ── C3. 热点兜底不许把已挂接的策略数两遍 ──
    reg3 = F.FleetRegistry()
    reg3.declare(F.UnitCard("st:x", F.KIND_STRATEGY, "声明式X", "strategy_mgr",
                            F.ST_STOPPED))
    fake_mgr = mock.Mock()
    fake_mgr.strategies = {"x": mock.Mock(name="热点X", strategy_id="x", is_active=True,
                                          last_execution_time=0.0, execution_count=3,
                                          scope="symbol")}
    fake_mgr.strategies["x"].name = "热点X"
    with mock.patch("deva.naja.market_hotspot.strategies.strategy_manager."
                    "get_hotspot_manager", lambda: fake_mgr):
        F.collect_hotspot_units(reg3)
    cards = reg3.snapshot(kind=F.KIND_STRATEGY)
    if len(cards) != 1:
        fails.append(f"热点兜底把已挂接的策略数了两遍：{len(cards)} 条")
    elif cards[0].source != "strategy_mgr":
        fails.append(f"热点兜底覆盖了已有条目（source={cards[0].source}）")

    return fails


# ── 负向注入 ─────────────────────────────────────────────────────────────────

INJECTIONS = (
    {
        "name": "declard_if_absent 改成覆盖写（热点策略被数两遍）",
        "old": '            existing = self._units.get(card.unit_id)\n'
               '            if existing is not None:\n'
               '                return existing',
        "new": '            existing = self._units.get(card.unit_id)\n'
               '            if existing is not None:\n'
               '                pass',
    },
    {
        # ❗打的是「失败时把原因写进 note」那一行 —— 只改构造时的初始 note 没用，
        #   report() 随后会用异常覆盖它。注入必须落在**真正决定结果**的那一行。
        "name": "失败时不把原因写进 note（不知道为什么不知道）",
        "old": '                card.note = f"{type(error).__name__}: {error}"[:300]',
        "new": '                card.note = ""',
    },
    {
        "name": "适配器失败改成静默 pass（不留 source_status）",
        "old": '        reg.set_source_status(source, ok=False, error=f"{type(e).__name__}: {e}")\n'
               '        return 0\n'
               '\n'
               '    n = 0\n'
               '    for e in entries:',
        "new": '        return 0\n'
               '\n'
               '    n = 0\n'
               '    for e in entries:',
    },
    {
        # ❗NET_RE 定义在**本守卫文件**里，不在 fleet_registry.py。
        #   写错目标文件会让注入静默失效（锚点不命中 → 跳过 → 看起来 4/4 其实是 3/4）。
        "name": "扫描正则改坏（0 命中 → 0 缺失 → 假绿）",
        "file": "guard",
        "old": r'r"^\s*(?:import\s+(?:requests|httpx|aiohttp|urllib|websocket|websockets)\b"',
        "new": r'r"^\s*(?:import\s+(?:zzz_no_such_lib)\b"',
    },
)

GUARD_PATH = Path(__file__).resolve()


def run_injections() -> int:
    caught = 0
    missed = []
    for inj in INJECTIONS:
        target = GUARD_PATH if inj.get("file") == "guard" else REGISTRY_PATH
        original = target.read_text(encoding="utf-8")
        if inj["old"] not in original:
            print(f"  ⚠️ 锚点未命中，跳过：{inj['name']}（目标={target.name}）")
            missed.append(inj["name"])
            continue
        try:
            target.write_text(
                original.replace(inj["old"], inj["new"], 1), encoding="utf-8")
            if inj.get("file") == "guard":
                # ❗改**守卫自己**的源码不会影响已经加载进内存的模块对象 ——
                #   直接调 _all_checks() 用的还是旧 NET_RE，注入白做且看起来全绿。
                #   必须按文件重新加载一份再跑（spec 名不是 "__main__"，不会触发 main()）。
                spec = importlib.util.spec_from_file_location(
                    "_fleet_guard_reloaded", GUARD_PATH)
                mod = importlib.util.module_from_spec(spec)
                sys.modules[spec.name] = mod
                spec.loader.exec_module(mod)
                fails = mod._all_checks()
            else:
                fails = _all_checks()
        finally:
            target.write_text(original, encoding="utf-8")
        if fails:
            caught += 1
            print(f"  ✅ 被捕获：{inj['name']}")
            for f in fails[:2]:
                print(f"       · {str(f)[:110]}")
        else:
            print(f"  ❌ 没抓到 —— 这条注入白做了：{inj['name']}")

    print(f"\n负向注入：{caught}/{len(INJECTIONS)} 被捕获"
          + (f"（{len(missed)} 条锚点未命中，已计失败）" if missed else ""))
    return caught if not missed else -1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--exercise-injections", action="store_true")
    args = ap.parse_args()

    if args.exercise_injections:
        return 0 if run_injections() == len(INJECTIONS) else 1

    failures = _all_checks()
    if failures:
        print("❌ 全系统清单完整性守卫 失败：")
        for f in failures:
            print(f"   - {f}")
        return 1 if args.strict else 0

    hits = _scan_network_modules()
    reg = _registered_modules(hits)
    print(f"✅ 全系统清单完整性守卫全绿"
          f"（扫描 {len(hits)} 个取数模块：{len(reg)} 个已登记 · "
          f"{len(hits) - len(reg)} 个在白名单并写明原因 · 四态守恒 · "
          f"unknown 带原因 · 适配器失败留痕 · 热点兜底不重复计数）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
