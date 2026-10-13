#!/usr/bin/env python3
"""守卫：Bandit 页面的「数据新鲜度」标注（时间戳 + 成败状态）

为什么有这个需求
----------------
Bandit 页面上的数字（A股持仓现价/收益率、美股行情）都是**异步更新**的：
行情推送一到就改，停推就冻结。以前页面只显示数字本身，用户无从判断
「这个价格是刚更新的，还是半小时前的」—— 一个"看起来很新"的旧数字，
比明摆着的报错更危险。

于是各数据块标题旁加了新鲜度徽章，如实回答：最后一次更新在何时、
成功还是失败。本守卫盯住这条链路的三个层面：

  ① 静态：三处埋点 + 两处徽章标注都还在（防止重构时被悄悄删掉）；
  ② 契约：FreshnessTracker 的成败语义正确 —— 尤其
     「失败不得回退上次成功时间戳」，否则失败徽章答不出「数据停在几点」；
     以及并发安全（行情回调在 observer 线程、UI 在协程里读写同一登记簿）。
  ③ 呈现：四种徽章（无记录/失败/陈旧/新鲜）输出互不相同 ——
     若两种状态渲染成一样，用户就分不出成功还是失败。

外加一条专门的回归防护（本次最容易踩的坑）：
  美股新鲜度必须区分「本轮真的去取数」与「休市回落持久化缓存」。
  休市时 results 会被旧价格填充，若无条件记成功，页面就会显示
  "刚刚更新" —— 假新鲜。这类错误不会报错，只会骗人。
"""

import argparse
import importlib.util
import re
import sys
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BANDIT = REPO / "deva" / "naja" / "bandit"

FRESHNESS_PY = BANDIT / "data_freshness.py"
UI_PY = BANDIT / "ui.py"
CYCLE_PY = BANDIT / "adaptive_cycle.py"
US_PRICE_PY = BANDIT / "us_stock_price_manager.py"
FUTU_PY = BANDIT / "futu_portfolio_syncer.py"

# (文件, 必须出现的正则, 说明)
STATIC_RULES = [
    (UI_PY, r"A股虚拟持仓\{_freshness_badges\(SOURCE_CN_PRICE\)\}",
     "A股持仓块标题必须标注 A股行情新鲜度"),
    (UI_PY, r"美股/港股持仓\{_freshness_badges\(SOURCE_US_PRICE, SOURCE_FUTU_SYNC\)\}",
     "美股/港股块标题必须同时标注美股行情与富途同步新鲜度"),
    (UI_PY, r"^from deva\.naja\.bandit\.data_freshness import \(",
     "ui.py 必须显式导入新鲜度模块（禁止裸字符串数据源名）"),
    (CYCLE_PY, r"record_success\(SOURCE_CN_PRICE\)",
     "A股行情「成功」埋点缺失"),
    (CYCLE_PY, r"record_failure\(\s*SOURCE_CN_PRICE",
     "A股行情「失败」埋点缺失"),
    (US_PRICE_PY, r"record_success\(SOURCE_US_PRICE\)",
     "美股行情「成功」埋点缺失"),
    (US_PRICE_PY, r"record_failure\(\s*SOURCE_US_PRICE",
     "美股行情「失败」埋点缺失"),
    (FUTU_PY, r"record_success\(SOURCE_FUTU_SYNC\)",
     "富途同步「成功」埋点缺失"),
    (FUTU_PY, r"record_failure\(\s*SOURCE_FUTU_SYNC",
     "富途同步「失败」埋点缺失"),
    # ★「假新鲜」专项：休市回落缓存不得被记成成功
    (US_PRICE_PY, r"if results and \(is_open or force\):",
     "美股新鲜度必须区分「真实取数」与「休市回落缓存」，否则休市会显示假新鲜"),
]

# 负向注入用例：改一处源码，check() 必须报错（否则守卫没有区分度）
INJECTIONS = [
    {
        "name": "把「失败」记成「成功」（last_ok 反转）",
        "file": FRESHNESS_PY,
        "old": "            rec.last_ok = False\n",
        "new": "            rec.last_ok = True\n",
        "section": "契约",
    },
    {
        "name": "删掉 A股块的徽章标注",
        "file": UI_PY,
        "old": "{_freshness_badges(SOURCE_CN_PRICE)}",
        "new": "",
        "section": "静态",
    },
    {
        "name": "去掉「真实取数」判据，无条件记成功（假新鲜）",
        "file": US_PRICE_PY,
        "old": "if results and (is_open or force):",
        "new": "if results:",
        "section": "静态",
    },
]


def _load_module():
    """直接按文件路径加载 data_freshness.py。

    刻意不走 `import deva...`：该模块只依赖 stdlib，单文件加载可以
    完全避开 deva 包初始化的副作用（日志/DB/单例装配），守卫不污染环境。

    注意必须先把模块登记进 sys.modules —— 否则 @dataclass 在解析
    `Optional[bool]` 这类字符串注解时会去 sys.modules 找 cls.__module__
    并拿到 None，直接抛 AttributeError。
    """
    name = "_freshness_under_test"
    spec = importlib.util.spec_from_file_location(name, FRESHNESS_PY)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载 {FRESHNESS_PY}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception:
        sys.modules.pop(name, None)
        raise
    return mod


# ---------------------------------------------------------------- ① 静态

def check_static() -> list:
    failures = []
    for path, pattern, desc in STATIC_RULES:
        if not path.exists():
            failures.append(f"{path.relative_to(REPO)} 不存在")
            continue
        src = path.read_text(encoding="utf-8")
        if not re.search(pattern, src, re.MULTILINE):
            failures.append(f"{path.relative_to(REPO)}：{desc}")
    return failures


# ---------------------------------------------------------------- ② 契约

def check_contract(mod) -> list:
    failures = []
    S = mod.SOURCE_CN_PRICE
    t = mod.FreshnessTracker()

    # 全新登记簿：不得凭空冒充"成功"
    rec = t.snapshot(S)
    if rec.last_ok is not None:
        failures.append("全新登记簿的 last_ok 应为 None（表示尚未上报）")
    if rec.age_seconds() is not None:
        failures.append("从未成功过时 age_seconds() 应返回 None，而不是一个假的旧时间")

    # 成功
    t.record_success(S)
    ok = t.snapshot(S)
    if ok.last_ok is not True:
        failures.append("record_success 后 last_ok 应为 True")
    if ok.ok_count != 1:
        failures.append("record_success 未累计成功次数")
    if ok.last_success_ts <= 0 or ok.age_seconds() is None:
        failures.append("record_success 未记录成功时间戳")
    success_ts = ok.last_success_ts

    # ❗关键 invariant：失败不得回退上次成功时间戳
    time.sleep(0.01)
    t.record_failure(S, "连接超时")
    bad = t.snapshot(S)
    if bad.last_ok is not False:
        failures.append("record_failure 后 last_ok 应为 False")
    if bad.fail_count != 1:
        failures.append("record_failure 未累计失败次数")
    if bad.last_error != "连接超时":
        failures.append("record_failure 未记录错误原因")
    if bad.last_success_ts != success_ts:
        failures.append(
            "record_failure 改写了 last_success_ts —— 失败徽章将答不出「数据停在几点」"
        )
    if bad.ok_count != 1:
        failures.append("record_failure 污染了 ok_count")

    # 快照必须是副本：调用方改它不得影响登记簿
    snap = t.snapshot(S)
    snap.ok_count = 999
    if t.snapshot(S).ok_count == 999:
        failures.append("snapshot() 返回的不是副本，调用方会污染登记簿")

    # 并发安全：行情回调与 UI 读在别的线程/协程里
    t2 = mod.FreshnessTracker()

    def worker():
        for _ in range(100):
            t2.record_success(S)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    total = t2.snapshot(S).ok_count
    if total != 800:
        failures.append(f"并发记录丢失：期望 800 次成功，实际 {total}（锁没护住）")

    # reset
    t.reset(S)
    if t.snapshot(S).last_ok is not None:
        failures.append("reset() 未清空该数据源的记录")

    # 数据源常量与标签登记一致（新增 source 忘登记 → UI 显示裸 key）
    expected = {mod.SOURCE_CN_PRICE, mod.SOURCE_US_PRICE, mod.SOURCE_FUTU_SYNC}
    if set(mod.SOURCE_LABELS) != expected:
        failures.append(
            f"SOURCE_LABELS 键与数据源常量不一致：{sorted(mod.SOURCE_LABELS)} vs {sorted(expected)}"
        )

    # dataclass 字段数 == to_dict() 键数（本仓硬规则）
    probe = mod.Freshness(source=S)
    if len(probe.to_dict()) != len(probe.__dataclass_fields__):
        failures.append(
            f"Freshness.to_dict() 键数({len(probe.to_dict())}) 与字段数"
            f"({len(probe.__dataclass_fields__)}) 不一致"
        )
    return failures


# ---------------------------------------------------------------- ③ 呈现

def check_render(mod) -> list:
    failures = []
    S = mod.SOURCE_CN_PRICE
    now = 1_700_000_000.0

    def mk(**kw):
        base = dict(source=S)
        base.update(kw)
        return mod.Freshness(**base)

    b_none = mod.format_badge(mk(), now=now)
    b_fresh = mod.format_badge(
        mk(last_attempt_ts=now, last_success_ts=now - 10, last_ok=True, ok_count=1), now=now)
    b_stale = mod.format_badge(
        mk(last_attempt_ts=now, last_success_ts=now - 3600, last_ok=True, ok_count=1), now=now)
    b_fail = mod.format_badge(
        mk(last_attempt_ts=now - 30, last_success_ts=now - 600, last_ok=False,
           last_error="连接超时", fail_count=1), now=now)

    # 四种状态必须互不相同 —— 否则用户分不出成功/失败
    if len({b_none, b_fresh, b_stale, b_fail}) != 4:
        failures.append("四种状态渲染有重复 —— 成功/失败/陈旧/无记录无法区分")

    for html, kw, name in [
        (b_none, "尚无更新记录", "无记录徽章"),
        (b_fresh, "更新于", "新鲜徽章"),
        (b_stale, "距上次更新", "陈旧徽章"),
        (b_fail, "更新失败", "失败徽章"),
    ]:
        if kw not in html:
            failures.append(f"{name}缺少关键词 {kw!r}")

    # 失败徽章最有用的信息：数据实际停在几点 + 为什么失败
    if "数据停留在" not in b_fail:
        failures.append("失败徽章未标出「数据停留在」时间")
    if "连接超时" not in b_fail:
        failures.append("失败徽章未透出错误原因")

    # 颜色必须可区分（失败红 / 陈旧黄 / 新鲜绿 / 无记录灰）
    if "#fee2e2" not in b_fail:
        failures.append("失败徽章未使用红色底")
    if "#fef3c7" not in b_stale:
        failures.append("陈旧徽章未使用黄色底")
    if "#dcfce7" not in b_fresh:
        failures.append("新鲜徽章未使用绿色底")

    # 阈值必须真的起作用
    edge_fresh = mod.format_badge(
        mk(last_attempt_ts=now, last_success_ts=now - 100, last_ok=True), now=now, stale_sec=300)
    edge_stale = mod.format_badge(
        mk(last_attempt_ts=now, last_success_ts=now - 400, last_ok=True), now=now, stale_sec=300)
    if edge_fresh == edge_stale:
        failures.append("stale_sec 阈值没有区分度（新鲜与陈旧渲染相同）")

    # format_ago 边界
    for sec, expect in [(30, "30 秒"), (90, "1 分钟"), (3700, "1.0 小时"), (90000, "1.0 天")]:
        got = mod.format_ago(sec)
        if got != expect:
            failures.append(f"format_ago({sec}) = {got!r}，期望 {expect!r}")
    if mod.format_ago(None) != "-":
        failures.append("format_ago(None) 应为 '-'")

    return failures


def check() -> int:
    print(f"被测模块：{FRESHNESS_PY.relative_to(REPO)}")
    try:
        mod = _load_module()
    except Exception as e:  # noqa: BLE001
        print(f"❌ 无法加载被测模块：{e}")
        return 1

    static_fail = check_static()
    contract_fail = check_contract(mod)
    render_fail = check_render(mod)

    for title, fails in [("静态（埋点/标注在位）", static_fail),
                         ("契约（成败语义/并发）", contract_fail),
                         ("呈现（四态可区分）", render_fail)]:
        if fails:
            print(f"\n❌ {title}：")
            for f in fails:
                print(f"    - {f}")
        else:
            print(f"✅ {title}：通过")

    if static_fail or contract_fail or render_fail:
        return 1
    print("\n✅ 通过：三处埋点在位、成败语义正确、四种徽章可区分")
    return 0


# ---------------------------------------------------------------- 自证

def self_test() -> int:
    """隔离自证：不碰真实文件，只验证「检查规则本身有区分度」。"""
    failures = []
    mod = _load_module()

    # 规则表非空且每条都有说明
    if len(STATIC_RULES) < 8:
        failures.append(f"静态规则过少（{len(STATIC_RULES)} 条），覆盖不全")
    for _, _, desc in STATIC_RULES:
        if not desc.strip():
            failures.append("存在没有说明文字的静态规则")

    # 每条静态规则的正则，都必须能匹配到它自己的目标文件（否则规则是死的）
    for path, pattern, desc in STATIC_RULES:
        src = path.read_text(encoding="utf-8")
        if not re.search(pattern, src, re.MULTILINE):
            failures.append(f"规则「{desc}」匹配不到 {path.name} —— 规则可能是死的")

    # 规则必须对「删掉埋点」敏感：拿一条规则做种子，改坏源码后不得再匹配
    seed_path, seed_pattern, _ = STATIC_RULES[0]
    broken = seed_path.read_text(encoding="utf-8").replace(
        "_freshness_badges(SOURCE_CN_PRICE)", "_freshness_badges()")
    if re.search(seed_pattern, broken, re.MULTILINE):
        failures.append("静态规则对「删掉数据源参数」不敏感 —— 没有区分度")

    # 契约/呈现的失败项在正常模块上必须为空
    c_fail = check_contract(mod)
    if c_fail:
        failures.append("契约检查在未注入时却报错（守卫自身有问题）：")
        failures.extend(c_fail)
    r_fail = check_render(mod)
    if r_fail:
        failures.append("呈现检查在未注入时却报错（守卫自身有问题）：")
        failures.extend(r_fail)

    if failures:
        print("❌ 自证失败：")
        for f in failures:
            print(f"    - {f}")
        return 1
    print("✅ 自证通过：规则均有区分度，且未注入时不误报")
    return 0


def exercise_injections() -> int:
    """行为自证：往真实源码注入已知 bug，check() 必须报错；逐例立即还原。"""
    failures = []
    for case in INJECTIONS:
        path, old, new = case["file"], case["old"], case["new"]
        if not path.exists():
            failures.append(f"[{case['name']}] 目标文件不存在")
            continue
        original = path.read_text(encoding="utf-8")
        if old not in original:
            failures.append(f"[{case['name']}] 注入锚点找不到（源码已变，请更新守卫）")
            continue

        try:
            path.write_text(original.replace(old, new, 1), encoding="utf-8")
            code = check()
            if code == 0:
                failures.append(f"[{case['name']}] 注入后守卫仍返回 0 —— 没有区分度")
            else:
                print(f"  ✅ 注入「{case['name']}」→ 守卫如期报错（{case['section']}段）")
        finally:
            path.write_text(original, encoding="utf-8")
            # 立即确认还原干净（注入脚本残留会污染后续改动）
            if path.read_text(encoding="utf-8") != original:
                failures.append(f"[{case['name']}] 源码还原失败，请手动检查 {path}")

    # 全部还原后再跑一次，必须回到绿
    if check() != 0:
        failures.append("注入用例跑完后守卫仍不通过 —— 还原不干净")

    if failures:
        print("\n❌ 注入自证失败：")
        for f in failures:
            print(f"    - {f}")
        return 1
    print(f"\n✅ 注入自证通过：{len(INJECTIONS)} 例注入全部被捕获，且已还原")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Bandit 数据新鲜度标注守卫")
    ap.add_argument("--strict", action="store_true", help="严格模式（默认行为）")
    ap.add_argument("--self-test", action="store_true", help="隔离自证：规则有区分度")
    ap.add_argument("--exercise-injections", action="store_true", help="真实注入后必须报错")
    args = ap.parse_args()

    if args.self_test:
        return self_test()
    if args.exercise_injections:
        return exercise_injections()
    return check()


if __name__ == "__main__":
    sys.exit(main())
