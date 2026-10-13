#!/usr/bin/env python3
"""守卫：富途统一行情源（``futu_quote_source``）。

守三件事：
1. **认不出就如实说认不出**。市场判不出来、代码拼不出来、快照里没有这个代码、
   缺最新价、缺昨收 —— 五种失败必须各自返回 ``ok=False`` 且带**不同**的原因。
   合起来只报一句"取不到行情"，等于把"标的写错了"和"OpenD 挂了"混为一谈。
2. **缺昨收 = 判据失效**。做 T 所有百分比都以昨收为锚，没有基准时判据会
   退化成瞎猜 —— 这种情况必须判失败，绝不能"先凑合着算"。
3. **不能静默丢标的**。取不到的标的也要出现在返回字典里（带 error），
   否则调用方看到的是"字典里没这个 key"，排查方向直接跑偏。

为什么还要单独守住「每次建连必关」
--------------------------------
``OpenQuoteContext`` 对 OpenD 的并发连接数有限制，泄漏的代价是**整条行情链路
在某次重启后集体失效**，且症状是"偶发取不到"，极难归因。

用法::

    python3 scripts/verify/verify_futu_quote_source.py --strict
    python3 scripts/verify/verify_futu_quote_source.py --self-test
    python3 scripts/verify/verify_futu_quote_source.py --exercise-injections
"""

from __future__ import annotations

import argparse
import importlib.util
import shutil
import sys
import tempfile
import types
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BANDIT = REPO / "deva" / "naja" / "bandit"

SRC_PY = BANDIT / "futu_quote_source.py"

# ---------------------------------------------------------------- 静态

STATIC_RULES = [
    (SRC_PY, r'def resolve\(',
     "缺少代码解析入口"),
    (SRC_PY, r'return "", "", note',
     "市场判不出来时未如实返回空市场（猜市场 = 拿错盘口的价当对的用）"),
    (SRC_PY, r'if current <= 0:',
     "缺最新价时未判失败"),
    (SRC_PY, r'if prev_close <= 0:',
     "❗缺昨收时未判失败 —— 做 T 的百分比基准没了，判据会退化成瞎猜"),
    (SRC_PY, r'finally:\s*\n\s*ctx\.close\(\)',
     "OpenQuoteContext 未在 finally 里关闭（连接泄漏会让整条行情链路偶发失效）"),
    (SRC_PY, r'by_full\.setdefault\(full, \[\]\)\.append\(key\)',
     "未按富途代码去重（同一标的多种写法会重复查询）"),
    (SRC_PY, r'快照中缺少',
     "快照里没有该代码时未报错（会静默变成「字典里没这个 key」）"),
    (SRC_PY, r'def amplitude_pct\(self\) -> float:',
     "缺少振幅口径（做 T 的死水闸门直接依赖它）"),
]

STATIC_FORBIDDEN = [
    (SRC_PY, r'prev_close\s*=\s*current',
     "拿现价当昨收兜底 —— 偏离度恒为 0，做 T 永不触发"),
    # ❗只禁**非零**写死：默认 0.0 是「未取到」的合法初值，一起禁了会假红
    (SRC_PY, r'lot_size:\s*float\s*=\s*[1-9]',
     "每手股数被写死（美股 1 / 港股 100 / A股 100，必须实查）"),
]

# 负向注入：改一处源码，check() 必须报错
INJECTIONS = [
    {
        "name": "缺昨收时不再判失败（判据失去基准，静默瞎猜）",
        "file": SRC_PY,
        "old": '        if prev_close <= 0:\n'
               '            q.error = f"{full} 无有效昨收，百分比基准缺失"\n'
               '            log.warning("[FutuQuote] %s", q.error)\n'
               '            return q\n',
        "new": "",
    },
    {
        "name": "快照缺该代码时静默丢弃（调用方只看到 key 不存在）",
        "file": SRC_PY,
        "old": '                if row is None:\n',
        "new": '                if row is None:\n                    continue\n',
    },
    {
        # ❗改成 pass 而不是删掉 finally：删了会 SyntaxError，
        # 那是「用例本身写坏了」，不是「守卫抓到了 bug」。
        "name": "行情上下文不再真正关闭（连接泄漏）",
        "file": SRC_PY,
        "old": "                ctx.close()",
        "new": "                pass",
    },
    {
        "name": "市场判不出来时硬塞一个 HK（拿错盘口的价）",
        "file": SRC_PY,
        "old": '            return "", "", note',
        "new": '            return "HK", "", note',
    },
]


# ---------------------------------------------------------------- 载入

def _stub_package(name: str, path=None):
    mod = types.ModuleType(name)
    if path is not None:
        mod.__path__ = [str(path)]
    sys.modules[name] = mod
    return mod


def _load_by_path(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载 {path}")
    mod = importlib.util.module_from_spec(spec)
    # 必须先登记进 sys.modules：@dataclass 解析注解时靠它反查所属模块
    sys.modules[name] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception:
        sys.modules.pop(name, None)
        raise
    return mod


class _FakeDF:
    """够用的 DataFrame 替身：``iterrows()`` + ``len()``。"""

    def __init__(self, rows):
        self.rows = list(rows)

    def __len__(self):
        return len(self.rows)

    def iterrows(self):
        for i, r in enumerate(self.rows):
            yield i, r


class _FakeCtx:
    def __init__(self, result, sink):
        self._result = result
        self._sink = sink

    def get_market_snapshot(self, codes):
        self._sink.append(list(codes))
        if isinstance(self._result, Exception):
            raise self._result
        return self._result

    def close(self):
        self._sink.append("CLOSED")


class Sandbox:
    """加载被测模块，并把 ``futu`` 换成可控桩件（守卫绝不连真 OpenD）。"""

    def __init__(self):
        self.calls: list = []
        self.result = (0, _FakeDF([]))
        self.mod = None

    def _install_futu_stub(self):
        futu = types.ModuleType("futu")

        def _ctx(host=None, port=None):
            return _FakeCtx(self.result, self.calls)

        futu.OpenQuoteContext = _ctx
        futu.RET_OK = 0
        sys.modules["futu"] = futu

    def load(self):
        if self.mod is not None:
            return self.mod
        self._install_futu_stub()
        _stub_package("deva")
        _stub_package("deva.naja")
        _stub_package("deva.naja.bandit", BANDIT)
        self.mod = _load_by_path("deva.naja.bandit.futu_quote_source", SRC_PY)
        return self.mod


# ---------------------------------------------------------------- 检查

def _row(code, *, last=10.0, prev=10.0, high=10.5, low=9.5,
         volume=1000.0, lot=100.0, spread=0.01):
    return {
        "code": code, "name": f"名-{code}",
        "last_price": last, "prev_close_price": prev,
        "open_price": prev, "high_price": high, "low_price": low,
        "volume": volume, "turnover": last * volume,
        "lot_size": lot, "price_spread": spread, "update_time": "2026-10-14 00:00:00",
    }


def check() -> list:
    """返回问题列表；空列表 = 通过。"""
    problems: list = []
    src = SRC_PY.read_text(encoding="utf-8")

    for path, pattern, why in STATIC_RULES:
        import re
        if not re.search(pattern, path.read_text(encoding="utf-8")):
            problems.append(f"[静态] {path.name}: {why}")
    for path, pattern, why in STATIC_FORBIDDEN:
        import re
        if re.search(pattern, path.read_text(encoding="utf-8")):
            problems.append(f"[静态-禁止] {path.name}: {why}")

    sb = Sandbox()
    mod = sb.load()

    # ① 三市场代码换算 —— 少一个市场，做 T 就少一个仓
    sb.result = (0, _FakeDF([
        _row("SH.588200", last=0.996, prev=0.996, high=1.013, low=0.953,
             lot=100, spread=0.001),
        _row("HK.00700", last=425.2, prev=425.8, high=425.6, low=419.8,
             lot=100, spread=0.2),
        _row("US.QQQ", last=743.5, prev=746.04, high=744.2, low=738.84,
             lot=1, spread=0.01),
    ]))
    got = mod.FutuQuoteSource().fetch([
        ("588200", "CN"), ("00700", "HK"), ("QQQ", "US"),
    ])
    expect = {
        "588200": ("CN", "SH.588200", 0.996, 100.0),
        "00700": ("HK", "HK.00700", 425.2, 100.0),
        "QQQ": ("US", "US.QQQ", 743.5, 1.0),
    }
    for key, (mkt, full, price, lot) in expect.items():
        q = got.get(key)
        if q is None:
            problems.append(f"[行为] {key} 未出现在结果里（静默丢标的）")
            continue
        if not q.ok:
            problems.append(f"[行为] {key} 应成功却失败: {q.error}")
            continue
        if q.market != mkt or q.futu_code != full:
            problems.append(
                f"[行为] {key} 换算错误: {q.market}/{q.futu_code} != {mkt}/{full}"
            )
        if abs(q.current - price) > 1e-9:
            problems.append(f"[行为] {key} 现价 {q.current} != {price}")
        if abs(q.lot_size - lot) > 1e-9:
            problems.append(f"[行为] {key} 每手 {q.lot_size} != {lot}（必须实查，不能写死）")

    # ② 无点前缀写法（行情总线/题材策略用的就是它）也要认得
    got2 = mod.FutuQuoteSource().fetch([("sh588200", None), ("hk00700", None)])
    for key, want in (("sh588200", "SH.588200"), ("hk00700", "HK.00700")):
        q = got2.get(key)
        if q is None or not q.ok:
            problems.append(f"[行为] 无点前缀 {key} 解析失败: {getattr(q, 'error', '缺失')}")
        elif q.futu_code != want:
            problems.append(f"[行为] 无点前缀 {key} → {q.futu_code} != {want}")

    # ③ 认不出市场 → 失败但**必须在结果里**，且带原因
    got3 = mod.FutuQuoteSource().fetch([("zzz_unknown", None)])
    q3 = got3.get("zzz_unknown")
    if q3 is None:
        problems.append("[行为] 认不出市场的标的被静默丢弃")
    elif q3.ok or not q3.error:
        problems.append("[行为] 认不出市场时未判失败/未给原因")

    # ④ 快照里没有这个代码 → 失败且带原因（不是 KeyError、不是静默缺）
    sb.result = (0, _FakeDF([_row("SH.588200")]))
    got4 = mod.FutuQuoteSource().fetch([("00700", "HK")])
    q4 = got4.get("00700")
    if q4 is None:
        problems.append("[行为] 快照缺该代码时标的被丢弃")
    elif q4.ok or not q4.error:
        problems.append("[行为] 快照缺该代码时未判失败")

    # ⑤ 缺昨收 → 判失败（做 T 的锚没了）
    sb.result = (0, _FakeDF([_row("SH.588200", last=1.0, prev=0.0)]))
    q5 = mod.FutuQuoteSource().fetch([("588200", "CN")]).get("588200")
    if q5 is None or q5.ok:
        problems.append("[行为] 缺昨收时未判失败（判据会失去基准）")
    elif not q5.error:
        problems.append("[行为] 缺昨收时未给原因")

    # ⑥ 缺最新价 → 判失败
    sb.result = (0, _FakeDF([_row("SH.588200", last=0.0, prev=1.0)]))
    q6 = mod.FutuQuoteSource().fetch([("588200", "CN")]).get("588200")
    if q6 is None or q6.ok:
        problems.append("[行为] 缺最新价时未判失败")

    # ⑦ 连不上 OpenD → 不抛异常，全部条目失败且带原因
    sb.result = RuntimeError("OpenD 未启动")
    try:
        got7 = mod.FutuQuoteSource().fetch([("588200", "CN"), ("00700", "HK")])
    except Exception as e:
        problems.append(f"[行为] 连接失败时把异常抛出去了（{e}），调用方线程会被打死")
        got7 = {}
    for key in ("588200", "00700"):
        q7 = got7.get(key)
        if q7 is None:
            problems.append(f"[行为] 连接失败时 {key} 被丢弃")
        elif q7.ok or not q7.error:
            problems.append(f"[行为] 连接失败时 {key} 未判失败")

    # ⑧ 每次取数都必须关闭连接
    sb.result = (0, _FakeDF([_row("SH.588200")]))
    sb.calls.clear()
    mod.FutuQuoteSource().fetch([("588200", "CN")])
    if "CLOSED" not in sb.calls:
        problems.append("[行为] 取数后未关闭连接（OpenD 连接会泄漏）")

    # ⑨ 批量：一次快照调用搞定，且按富途代码去重
    sb.calls.clear()
    mod.FutuQuoteSource().fetch([
        ("588200", "CN"), ("sh588200", None), ("00700", "HK"),
    ])
    queries = [c for c in sb.calls if isinstance(c, list)]
    if len(queries) != 1:
        problems.append(f"[行为] 批量取数发起了 {len(queries)} 次快照，应为 1 次")
    elif len(set(queries[0])) != len(queries[0]):
        problems.append(f"[行为] 同标的多种写法未去重: {queries[0]}")

    # ⑩ 振幅口径
    sb.result = (0, _FakeDF([_row("SH.588200", prev=10.0, high=10.6, low=9.4)]))
    q10 = mod.FutuQuoteSource().fetch([("588200", "CN")]).get("588200")
    if q10 is None or abs(q10.amplitude_pct - 12.0) > 1e-6:
        got_v = getattr(q10, "amplitude_pct", None)
        problems.append(f"[行为] 振幅算错: {got_v} != 12.0")

    return problems


# ---------------------------------------------------------------- 注入

def _run_injections() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="verify_futu_quote_"))
    backups = {}
    try:
        caught = 0
        for inj in INJECTIONS:
            path: Path = inj["file"]
            backups.setdefault(path, path.read_text(encoding="utf-8"))
            text = path.read_text(encoding="utf-8")
            if inj["old"] not in text:
                print(f"  ❌ 注入锚点不存在: {inj['name']}")
                continue
            path.write_text(text.replace(inj["old"], inj["new"], 1), encoding="utf-8")
            # 逐例注完立即还原：restore() 覆盖式还原会吃掉后续改动
            try:
                sys.modules.pop("deva.naja.bandit.futu_quote_source", None)
                problems = check()
            finally:
                path.write_text(backups[path], encoding="utf-8")
            if problems:
                caught += 1
                print(f"  ✅ 抓到: {inj['name']} → {problems[0]}")
            else:
                print(f"  ❌ 漏网: {inj['name']}")
        return 0 if caught == len(INJECTIONS) else 1
    finally:
        for path, text in backups.items():
            path.write_text(text, encoding="utf-8")
        shutil.rmtree(tmp, ignore_errors=True)


def _self_test() -> int:
    """守卫要自证：正常源码必须绿，且注入后必须红（两段都要有区分度）。"""
    sys.modules.pop("deva.naja.bandit.futu_quote_source", None)
    clean = check()
    print(f"[self-test] 正常源码问题数 = {len(clean)}（应为 0）")
    for p in clean:
        print(f"  ⚠️ {p}")

    print("[self-test] 负向注入：")
    rc = _run_injections()

    sys.modules.pop("deva.naja.bandit.futu_quote_source", None)
    after = check()
    print(f"[self-test] 还原后问题数 = {len(after)}（应为 0）")
    ok = (not clean) and rc == 0 and (not after)
    print("✅ 自证通过" if ok else "❌ 自证失败")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--exercise-injections", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        return _self_test()
    if args.exercise_injections:
        return _run_injections()

    problems = check()
    if problems:
        print(f"❌ 富途行情源守卫发现 {len(problems)} 个问题：")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("✅ 富途行情源守卫通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
