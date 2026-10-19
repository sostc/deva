#!/usr/bin/env python3
"""守卫：QueryStateUpdater 不许用 symbol_weights 伪造行情（宏观流动性的源头）。

守什么
------
``QueryState`` 是 ``GlobalMarketScanner`` 与 ``QueryStateUpdater`` **共享的单例**，
后写覆盖先写。``_on_hotspot_computed`` 原先在事件缺行情时这样兜底：

    returns = [event.symbol_weights[s] * 100 for s in symbols]     # ← 冒充「涨跌幅」
    volumes = [event.symbol_weights[s] * 1000000 for s in symbols]
    prices  = [event.symbol_weights[s] * 100 for s in symbols]     # 注释原话：「权重本身可以作为相对价格的代理」

而 ``symbol_weights`` 的量级是 **1.00~1.45**，×100 就成了「平均涨幅 142%」。
实测（2026-10-15 17:35，同一分钟连采三次）：

    /api/query/state 的 market_regime.avg_change = 142.3390579620452
    symbol_weights 均值 × 100                    = 142.3390579620452     Δ = 0

同一刻 ``hot_stocks[].change_pct`` 是 +1.67 / −3.72 / −3.94 —— 真数据本来就在手边。
危害不止一句「数字难看」：这批人造数会被 ``RegimeEngine`` 拿去算 ``regime_score``
与 ``macro_liquidity_signal``，把决策的**环境输入**变成假数；还会把 scanner 刚写进去的
真市场数据（当时是 ``trend_down``）覆盖成 ``trend_up``（``up_ratio`` 恒 1.0，因为权重全为正）。

本守卫守三条
------------
* **不许造假**：``_on_hotspot_computed`` 内不得出现 ``symbol_weights`` 参与算术；
* **必须校验 + 早退**：returns / volumes / prices 三件套要对齐，缺任一则跳过更新；
* **跳过必须留痕**：静默跳过等于「看着没更新，其实是链断了」，与不更新无法区分。

行为用例（光看字符串是假绿）
--------------------------
* 缺三件套 → QueryState **一个字节都不许写**，且跳过计数 +1；
* 三件套齐全 → 必须**原样**把 returns/volumes/prices 传下去（换成权重就得被抓）；
* 只缺 volumes（半真半假）→ 同样必须跳过。

用法
----
    python scripts/verify/verify_query_state_no_fabrication.py
    python scripts/verify/verify_query_state_no_fabrication.py --strict
    python scripts/verify/verify_query_state_no_fabrication.py --exercise-injections
"""

from __future__ import annotations

import argparse
import ast
import importlib
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

STATE_UPDATER_PY = ROOT / "deva/naja/attention/kernel/state_updater.py"

#: 真实行情三件套 —— 缺一不可（update_from_market 三个都消费）
REQUIRED_FIELDS = ("returns", "volumes", "prices")


def _find_fn(tree: ast.AST, name: str):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def _strip_doc(fn) -> str:
    """函数体去掉 docstring 后再 unparse。

    ❗必须剥：说明文字里也写着被检查的关键词（本文件守的 ``symbol_weights``
    正出现在注释/文档里），不剥就是**假绿** —— 护栏删掉照样"命中"。
    """
    body = list(getattr(fn, "body", ()) or ())
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
            and isinstance(body[0].value.value, str):
        body = body[1:]
    return "\n".join(ast.unparse(s) for s in body)


def _mentions_symbol_weights(node) -> bool:
    """子树里是否出现 ``....symbol_weights[...]`` 这种**取值**。

    只认下标取值：`list(event.symbol_weights.keys())` 是取代码，不该误判。
    """
    for sub in ast.walk(node):
        if isinstance(sub, ast.Subscript):
            base = sub.value
            name = getattr(base, "attr", None) or getattr(base, "id", None)
            if name == "symbol_weights":
                return True
    return False


# ── 静态检查 ─────────────────────────────────────────────────────────────────

def check_no_fabrication_static() -> list:
    failures: list = []
    tree = ast.parse(STATE_UPDATER_PY.read_text(encoding="utf-8"))
    fn = _find_fn(tree, "_on_hotspot_computed")
    if fn is None:
        return ["state_updater 找不到 _on_hotspot_computed（订阅结构换了？）"]

    # ① 任何算术里都不许出现 symbol_weights 的取值
    for node in ast.walk(fn):
        if isinstance(node, ast.BinOp):
            for side in (node.left, node.right):
                if _mentions_symbol_weights(side):
                    failures.append(
                        "_on_hotspot_computed 仍拿 symbol_weights 参与算术"
                        "（用权重伪造涨跌幅/成交量/价格）"
                    )

    # ② 必须校验事件是否带齐真实行情，并且**早退**
    verified = False
    for node in ast.walk(fn):
        if isinstance(node, ast.If) and "_has_real_market_data" in ast.unparse(node.test):
            if any(isinstance(s, ast.Return) for s in ast.walk(node)):
                verified = True
    if not verified:
        failures.append(
            "_on_hotspot_computed 未校验/未早退 `_has_real_market_data`"
            "（缺数据时会继续用假数更新 QueryState）"
        )

    # ③ 跳过必须留痕（静默跳过 = 链断了却看不出来）
    if "_note_skipped_hotspot" not in _strip_doc(fn):
        failures.append("_on_hotspot_computed 跳过时未调用 _note_skipped_hotspot（静默跳过）")

    # ④ 校验函数必须逐字段查三件套，且比对长度 —— 只查「非空」会让半真半假漏过去
    checker = _find_fn(tree, "_has_real_market_data")
    if checker is None:
        failures.append("缺 _has_real_market_data（没有单一出处校验行情是否真实）")
    else:
        body = _strip_doc(checker)
        for field in REQUIRED_FIELDS:
            if field not in body:
                failures.append(f"_has_real_market_data 未检查 {field}")
        if "len(" not in body:
            failures.append("_has_real_market_data 未比对长度（长度不齐会错位）")
    return failures


# ── 行为检查（真跑，不只看字符串） ────────────────────────────────────────────

class _RecordingQS:
    """只记录调用的假 QueryState（守卫不得写任何生产状态）。"""

    def __init__(self):
        self.calls: list = []

    def update_from_market(self, **kwargs):
        self.calls.append(kwargs)


def _mk_updater(min_market_sample: int = 0):
    mod = importlib.reload(
        importlib.import_module("deva.naja.attention.kernel.state_updater")
    )
    # ❗不调 __init__：它会 get_event_bus() 并真订阅全局事件（副作用）。
    up = mod.QueryStateUpdater.__new__(mod.QueryStateUpdater)
    up.qs = _RecordingQS()
    up._hotspot_skip_count = 0
    up._hotspot_skip_log_every = 10 ** 9       # 测试期不刷日志
    up._last_data_hash = None
    up._last_symbol_count = 0
    # 默认关掉「薄样本闸门」，让用例只考伪造守卫；闸门单独在场景 5 里验
    up._min_market_sample = min_market_sample
    return mod, up


def _mk_event(returns, volumes, prices, symbols=("aaa", "bbb")):
    return types.SimpleNamespace(
        market="US",
        timestamp=1234567890.0,
        symbol_weights={s: 1.45 for s in symbols},
        symbols=list(symbols),
        returns=list(returns),
        volumes=list(volumes),
        prices=list(prices),
    )


def check_updater_behavior() -> list:
    failures: list = []

    # 场景 1：缺三件套（线上就是这个状态：symbol_market_data 为空）
    _mod, up = _mk_updater()
    up._on_hotspot_computed(_mk_event([], [], []))
    if up.qs.calls:
        failures.append(
            "事件未携带真实行情，更新器仍写了 QueryState（伪造涨跌幅的入口没堵住）"
        )
    if up._hotspot_skip_count != 1:
        failures.append(
            f"跳过未计数（实得 {up._hotspot_skip_count}）—— 跳过必须留痕，不许静默"
        )

    # 场景 2：三件套齐全 → 必须原样透传，不许换成权重
    _mod2, up2 = _mk_updater()
    ret, vol, pri = [1.2, -0.5], [1000.0, 2000.0], [10.0, 20.0]
    up2._on_hotspot_computed(_mk_event(ret, vol, pri))
    if len(up2.qs.calls) != 1:
        failures.append(f"带真行情的事件应当更新一次 QueryState，实得 {len(up2.qs.calls)} 次")
    else:
        got = up2.qs.calls[0]
        for key, want in (("returns", ret), ("volumes", vol), ("prices", pri)):
            if list(got.get(key) or []) != want:
                failures.append(
                    f"QueryState 收到的 {key} 应原样等于事件真值 {want}，实得 {got.get(key)}"
                )

    # 场景 3：长度不齐（有 returns 但缺 volumes）同样必须跳过 —— 半真半假最危险
    _mod3, up3 = _mk_updater()
    up3._on_hotspot_computed(_mk_event(ret, [], pri))
    if up3.qs.calls:
        failures.append("returns 长度对齐但 volumes 缺失时仍写了 QueryState（口径混用）")

    # 场景 4（线上真实故障）：symbol_weights 是 WeightPool 注册表全集（含快照外标的），
    # 三件套只覆盖当次快照。以前用 `symbol_weights.keys()` 当标的清单 →
    # len(weights)=注册表(62) ≠ len(returns)=快照(57) → 每轮都跳过（累计 500 次）。
    # 正确行为：以 event.symbols 为准更新，且只透传快照那几只。
    _mod4, up4 = _mk_updater()
    ev4 = _mk_event(ret, vol, pri, symbols=("aaa", "bbb"))
    ev4.symbol_weights = {"aaa": 1.1, "bbb": 1.2, "ccc": 1.45, "ddd": 1.45}  # 注册表更大
    up4._on_hotspot_computed(ev4)
    if len(up4.qs.calls) != 1:
        failures.append(
            "symbol_weights 含快照外标的时被整轮跳过"
            f"（应仍更新一次，实得 {len(up4.qs.calls)} 次）"
        )
    elif list(up4.qs.calls[0].get("symbols") or []) != ["aaa", "bbb"]:
        failures.append(
            "更新时应用 event.symbols（当次快照），"
            f"实得 {up4.qs.calls[0].get('symbols')}"
        )

    # 场景 5：薄样本闸门。热点按频率档位分批推（实测 6 只的批次也来过），
    # 6 个标的的涨跌比不足以判 regime，必须被默认阈值挡掉，且不算「缺行情」。
    _mod5, up5 = _mk_updater(min_market_sample=10)
    thin = [f"s{i}" for i in range(6)]
    up5._on_hotspot_computed(
        _mk_event([1.0] * 6, [1.0] * 6, [10.0] * 6, symbols=tuple(thin))
    )
    if up5.qs.calls:
        failures.append("6 只的薄样本批次仍写了市场级状态（regime 会被噪声翻面）")
    if up5._hotspot_skip_count != 0:
        failures.append("薄样本被误记成「未携带真实行情」（两类跳过必须可区分）")
    return failures


# ── 负向注入 ─────────────────────────────────────────────────────────────────

INJECTIONS = [
    {
        "name": "缺行情时不早退（继续用假数更新 QueryState）",
        "file": STATE_UPDATER_PY,
        "old": "            if not self._has_real_market_data(event, len(symbols)):\n",
        "new": "            if False:\n",
    },
    {
        "name": "恢复 symbol_weights×100 伪造涨跌幅",
        "file": STATE_UPDATER_PY,
        "old": "            returns = list(event.returns)\n",
        "new": "            returns = [event.symbol_weights[s] * 100 for s in symbols]\n",
    },
    {
        "name": "跳过但不留痕（静默跳过 = 假绿）",
        "file": STATE_UPDATER_PY,
        "old": "                self._note_skipped_hotspot(event, len(symbols))\n",
        "new": "",
    },
    {
        "name": "校验放宽成「只看 returns 非空」（半真半假能过）",
        "file": STATE_UPDATER_PY,
        "old": '        for field in ("returns", "volumes", "prices"):\n',
        "new": '        for field in ("returns",):\n',
    },
]


def _all_checks() -> list:
    return check_no_fabrication_static() + check_updater_behavior()


def _reload():
    importlib.reload(
        importlib.import_module("deva.naja.attention.kernel.state_updater")
    )


def run_injections() -> int:
    """逐个注入 bug，确认守卫抓得到。锚点未命中一律判失败（防守卫腐烂）。"""
    caught = 0
    missed = []
    for inj in INJECTIONS:
        path: Path = inj["file"]
        original = path.read_text(encoding="utf-8")
        if inj["old"] not in original:
            missed.append(inj["name"])
            print(f"❌ 注入锚点未命中（守卫腐烂信号，锚点该修了）：{inj['name']}")
            continue
        print(f"· 注入：{inj['name']}")
        path.write_text(original.replace(inj["old"], inj["new"], 1), encoding="utf-8")
        try:
            _reload()
            found = _all_checks()
        except Exception as e:  # noqa: BLE001
            found = [f"守卫自身抛异常: {type(e).__name__}: {e}"]
        finally:
            path.write_text(original, encoding="utf-8")
            _reload()
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
        return 0 if run_injections() == len(INJECTIONS) else 1

    failures = _all_checks()
    if failures:
        print("❌ QueryState 不造假守卫 失败：")
        for f in failures:
            print(f"   - {f}")
        return 1
    print("✅ QueryState 不造假守卫全绿（禁 symbol_weights 算术 / 三件套校验 / 早退 / 留痕 / 行为用例）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
