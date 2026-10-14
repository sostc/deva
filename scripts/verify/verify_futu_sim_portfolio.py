#!/usr/bin/env python3
"""守卫：富途模拟组合适配器（做 T 账本 ↔ 富途模拟仓）。

要防的失效（每一条都对应一类静默失效）
------------------------------------
1. **代码前缀剥不掉** → 持仓 ``HK.00700`` 与配置里的 ``00700`` 对不上，
   账本读到「持有 0」，而账户里明明有 300 股腾讯。这是本次**实跑抓到**的
   bug：``strip_market_prefix`` 只剥无点前缀，带点的要调用方先 partition。
2. **T+1 判据失效** → 富途持仓没有建仓时间，账本靠 ``entry_time`` 判可卖
   必然错。必须挂 ``sellable_qty``（can_sell_qty）并由账本取 min。
3. **两套账** → 下单后不重新拉持仓、而是本地加减份额，等于把「下单成功」
   当成「持仓变了」。份额守恒这条铁律上不能有任何估算。
4. **缓存不失效** → 下单后读到成交前的旧份额。
5. **全卖光被误判成失败** → 清仓后富途不再返回该持仓。
6. **混算币种** → 一个组合对象绑多个市场，港元美元人民币加一起。

用法::

    python scripts/verify/verify_futu_sim_portfolio.py            # 全量
    python scripts/verify/verify_futu_sim_portfolio.py --strict   # CI 用
    python scripts/verify/verify_futu_sim_portfolio.py --self-test
    python scripts/verify/verify_futu_sim_portfolio.py --exercise-injections
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

PORT_PY = REPO / "deva/naja/bandit/futu_sim_portfolio.py"
LEDGER_PY = REPO / "deva/naja/bandit/core_position.py"
RUNNER_PY = REPO / "deva/naja/bandit/t_rotation_runner.py"

# 静态：必须具备的要素
REQUIRED_RULES = [
    (PORT_PY, r"def bare_code", "缺少裸码换算（富途 HK.00700 → 00700）"),
    (PORT_PY, r"partition\(\"\.\"\)|partition\('\.'\)",
     "bare_code 必须处理带点形式（strip_market_prefix 只管无点前缀）"),
    (PORT_PY, r"sellable_qty", "缺少可卖数量字段"),
    (PORT_PY, r'row\.get\("can_sell_qty"\)|row\.get\(.can_sell_qty.\)',
     "sellable_qty 必须来自富途 can_sell_qty（权威 T+1 口径）"),
    (PORT_PY, r"def invalidate", "缺少缓存失效方法"),
    (PORT_PY, r"self\.invalidate\(\)", "下单后必须失效缓存，否则读到成交前的旧份额"),
    (PORT_PY, r"allow_missing", "卖出必须区分「清仓」与「没成交」"),
    (PORT_PY, r"entry_time:\s*float\s*=\s*0\.0",
     "entry_time 必须恒为 0（富途没有建仓时间，真正的 T+1 靠 sellable_qty）"),
    (PORT_PY, r"total_capital|available_capital",
     "get_summary 必须给出 total_capital / available_capital（引擎按这俩算可用资金）"),
    (LEDGER_PY, r"_sellable_cap", "账本缺少可卖上限计算"),
    (LEDGER_PY, r"min\(inherited, cap\)", "账本未用 can_sell_qty 做上限"),
    # ❗只检查"有这个开关"是不够的：开关存在但默认 True，装上新代码就会
    # 自动往模拟账户报单。默认必须是**关**。
    (RUNNER_PY, r'NAJA_T_ROTATION_ON_SIM",\s*False',
     "真仓开关默认必须是 False（装上新代码不能自动开始报单）"),
    (RUNNER_PY, r"_engines|_portfolios", "runner 未按市场分组合/引擎"),
]

# 静态：禁止出现
FORBIDDEN_RULES = [
    (PORT_PY, r"TrdEnv\.REAL|TrdEnv\.REAL\b|trd_env\s*=\s*\"REAL\"",
     "适配器绝不能碰真实环境"),
    (PORT_PY, r"self\._qty\s*[+\-]=|quantity\s*[+\-]=",
     "禁止本地加减份额（必须以富途持仓为准）"),
    (PORT_PY, r"汇率|exchange_rate|fx_rate|convert_currency",
     "禁止汇率换算（用户拍板各市场独立本币记账）"),
]

# 负向注入：故意把代码改坏，守卫必须报红
INJECTIONS = [
    {
        "name": "裸码换算退化成只剥无点前缀（底仓读成 0）",
        "file": PORT_PY,
        "old": '        head, _sep, tail = text.partition(".")\n',
        "new": '        return strip_market_prefix(text)\n        head, _sep, tail = text.partition(".")\n',
    },
    {
        "name": "后缀式代码被读成市场名（NVDA.US → US）",
        "file": PORT_PY,
        "old": "            if tail.upper() in _MARKET_TOKENS:\n                return strip_market_prefix(head)\n",
        "new": "",
    },
    {
        "name": "下单后不再失效缓存（读到成交前的旧份额）",
        "file": PORT_PY,
        "old": "            self.invalidate()  # 缓存里是成交前的旧份额，必须丢掉再查\n",
        "new": "",
    },
    {
        "name": "卖出不再区分清仓与未成交",
        "file": PORT_PY,
        "old": "            if allow_missing:\n                return None\n",
        "new": "",
    },
    {
        "name": "账本不再用 can_sell_qty 做上限（A股T+1失效）",
        "file": LEDGER_PY,
        "old": "        cap = self._sellable_cap(positions)\n        if cap is not None:\n            inherited = min(inherited, cap)\n",
        "new": "",
        "count": -1,
    },
    {
        "name": "真仓开关默认打开（装上就自动报单）",
        "file": RUNNER_PY,
        "old": 'else env_flag("NAJA_T_ROTATION_ON_SIM", False)',
        "new": 'else env_flag("NAJA_T_ROTATION_ON_SIM", True)',
    },
    {
        "name": "买入失败却伪造一个持仓出来（两套账）",
        "file": PORT_PY,
        "old": "        if not outcome.ok or outcome.skipped:\n            self._last_error = f\"{code} 买入未成交: {outcome.reason}\"\n",
        "new": "        if False:\n            self._last_error = f\"{code} 买入未成交: {outcome.reason}\"\n",
    },
]


# ─────────────────────────────────────────────────────────────
# 行为用例
# ─────────────────────────────────────────────────────────────

class _FakeBackend:
    def __init__(self, ok=True, reason="", skipped=False):
        self.ok = ok
        self.reason = reason
        self.skipped = skipped
        self.calls = []

    def submit(self, **kw):
        from types import SimpleNamespace

        self.calls.append(kw)
        return SimpleNamespace(
            ok=self.ok, skipped=self.skipped, reason=self.reason,
            quantity=kw.get("quantity"), price=kw.get("price"),
        )


def behaviour_checks() -> list:
    """真跑一遍适配器（富途侧用假数据），验证形状与语义。"""
    failures = []
    import importlib

    import deva.naja.bandit.futu_sim_portfolio as mod

    # ❗必须 reload：负向注入改的是**磁盘上的源码**，而模块只在首次 import
    # 时进内存。不重载的话：① 注入根本作用不到被测代码，行为用例永远绿；
    # ② 更糟的是若首次 import 恰好发生在文件被注入的那一刻，污染版会被
    # 永久固化在内存里，后面每一条注入都报同一个假结果（本次实跑踩到：
    # 6 条注入里 4 条报同一条"缓存没失效"，其实源码早就还原干净了）。
    mod = importlib.reload(mod)

    # 账本模块同样要重载（注入也可能改它），并且**必须禁掉写盘**：
    # CorePositionLedger 的 set_plan 会落盘到生产账本文件，守卫不该污染它。
    import deva.naja.bandit.core_position as cp_mod

    cp_mod = importlib.reload(cp_mod)
    CorePositionLedger = cp_mod.CorePositionLedger

    def _no_persist():
        return None

    CorePositionLedger._save = _no_persist

    # ① 裸码换算：富途持仓代码的各种形态
    cases = {
        "HK.00700": "00700", "US.QQQ": "QQQ", "SH.588200": "588200",
        "SZ.300750": "300750", "hk06666": "06666", "sh600487": "600487",
        "00700": "00700", "NVDA.US": "NVDA", "": "",
    }
    for raw, want in cases.items():
        got = mod.bare_code(raw)
        if got != want:
            failures.append(f"bare_code({raw!r}) = {got!r}，应为 {want!r}")

    # ② 持仓映射：剥前缀、忽略 qty=0、挂 sellable_qty
    pf = mod.FutuSimPortfolio("HK")
    pf._fetch_rows = lambda: [
        {"code": "HK.00700", "stock_name": "腾讯控股", "qty": 300.0,
         "can_sell_qty": 300.0, "cost_price": 419.4, "nominal_price": 424.6,
         "currency": "HKD", "position_id": "P1"},
        {"code": "HK.06666", "stock_name": "恒大物业", "qty": 24500.0,
         "can_sell_qty": 0.0, "cost_price": 1.205, "nominal_price": 1.2,
         "currency": "HKD", "position_id": "P2"},
        {"code": "HK.00999", "stock_name": "已清仓", "qty": 0.0,
         "can_sell_qty": 0.0, "cost_price": 1.0, "nominal_price": 1.0,
         "currency": "HKD", "position_id": "P3"},
    ]
    pf.invalidate()
    positions = pf.get_all_positions(status="OPEN")
    if len(positions) != 2:
        failures.append(f"qty=0 的持仓必须忽略，得到 {len(positions)} 条")
    codes = {p.stock_code for p in positions}
    if "HK.00700" in codes:
        failures.append("持仓代码仍带富途前缀（账本会匹配不上）")
    by_code = {p.stock_code: p for p in positions}
    if by_code.get("00700") is None:
        failures.append("00700 未出现在持仓里")
    elif by_code["00700"].sellable_qty != 300.0:
        failures.append(f"00700 sellable_qty={by_code['00700'].sellable_qty}，应为 300")
    if by_code.get("06666") is not None and by_code["06666"].sellable_qty != 0.0:
        failures.append("06666 的 can_sell_qty=0，映射后必须也是 0")

    # ③ 账本认这套数据：可卖上限生效
    ledger = CorePositionLedger()
    cap = ledger._sellable_cap(positions)
    if cap is None:
        failures.append("_sellable_cap 对富途持仓返回 None（上限没生效）")
    elif abs(cap - 300.0) > 1e-6:
        failures.append(f"_sellable_cap = {cap}，应为 300（只算可卖的）")

    class _VP:
        def __init__(self, q, t):
            self.quantity = q
            self.entry_time = t

    virtual = [_VP(100.0, time.time() - 86400)]
    if ledger._sellable_cap(virtual) is not None:
        failures.append("虚拟盘持仓没有 sellable_qty，_sellable_cap 必须返回 None（行为不变）")

    # ④ 卖出：超过可卖量必须下调
    pf2 = mod.FutuSimPortfolio("HK")
    pf2._fetch_rows = lambda: [
        {"code": "HK.00700", "stock_name": "腾讯控股", "qty": 1000.0,
         "can_sell_qty": 400.0, "cost_price": 400.0, "nominal_price": 420.0,
         "currency": "HKD", "position_id": "P1"},
    ]
    backend = _FakeBackend()
    pf2._backend = backend
    pf2.invalidate()
    pf2.reduce_position("P1", 900.0, 420.0)
    if not backend.calls:
        failures.append("卖出未下单")
    else:
        sold_qty = backend.calls[-1].get("quantity")
        if abs((sold_qty or 0) - 400.0) > 1e-6:
            failures.append(
                f"计划卖 900 但只能卖 400，实际下 {sold_qty}（未按可卖量下调）"
            )
        if backend.calls[-1].get("side") != "sell":
            failures.append("方向不是 sell")

    # ⑤ 卖出：无可卖份额必须拒绝
    pf3 = mod.FutuSimPortfolio("CN")
    pf3._fetch_rows = lambda: [
        {"code": "SZ.300750", "stock_name": "宁德时代", "qty": 300.0,
         "can_sell_qty": 0.0, "cost_price": 289.0, "nominal_price": 286.99,
         "currency": "CNH", "position_id": "P9"},
    ]
    backend3 = _FakeBackend()
    pf3._backend = backend3
    pf3.invalidate()
    out = pf3.reduce_position("P9", 100.0, 286.99)
    if backend3.calls:
        failures.append("A股当日买入（can_sell_qty=0）竟然下了卖单")
    if out is not None:
        failures.append("无可卖份额时 reduce_position 应返回 None")
    if not (pf3.last_error and "可卖" in pf3.last_error):
        failures.append(f"拒绝原因必须说明是可卖份额为 0: {pf3.last_error!r}")

    # ⑥ 买入失败必须返回 None（不本地造持仓）
    #    ❗账户里**已经有**这个标的才测得出来：空仓时 _reload 本来就返回 None，
    #    失败路径与成功路径长得一样，注入怎么改都全绿（本次实跑踩到的假绿）。
    pf4 = mod.FutuSimPortfolio("US")
    pf4._query_rows = lambda: [
        {"code": "US.QQQ", "stock_name": "QQQ", "qty": 5.0,
         "can_sell_qty": 5.0, "cost_price": 740.0, "nominal_price": 741.0,
         "currency": "USD", "position_id": "Q9"},
    ]
    pf4._backend = _FakeBackend(ok=False, reason="资金不足")
    pf4.invalidate()
    if pf4.open_position(
        strategy_id="s", strategy_name="n", stock_code="QQQ", stock_name="QQQ",
        price=740.0, quantity=10.0,
    ) is not None:
        failures.append(
            "买入失败却返回了持仓 —— 把账户里本就有的份额当成这次买到的，"
            "等于本地凭空造账，份额守恒会彻底失真"
        )

    # ⑦ 下单必失效缓存：连续两次读取之间下过单，第二次不能走缓存
    #    ❗patch 的是 _query_rows（真实查询层），不是 _fetch_rows ——
    #    替换后者会把缓存层一起换掉，测出来的是"没有缓存"而不是"缓存坏了"。
    calls = {"n": 0}

    def _counting():
        calls["n"] += 1
        return [
            {"code": "US.QQQ", "stock_name": "QQQ", "qty": 10.0,
             "can_sell_qty": 10.0, "cost_price": 740.0, "nominal_price": 741.0,
             "currency": "USD", "position_id": "Q1"},
        ]

    pf5 = mod.FutuSimPortfolio("US")
    pf5._query_rows = _counting
    pf5._backend = _FakeBackend()
    pf5.invalidate()
    pf5.get_all_positions(status="OPEN")
    before = calls["n"]
    pf5.get_all_positions(status="OPEN")  # 应命中缓存
    if calls["n"] != before:
        failures.append("缓存没生效（账本一次计算会打十几次富途接口，会触发限流）")
    pf5.open_position(
        strategy_id="s", strategy_name="n", stock_code="QQQ", stock_name="QQQ",
        price=741.0, quantity=1.0,
    )
    if calls["n"] <= before:
        failures.append("下单后没有失效缓存（会读到成交前的旧份额）")

    # ⑧ 全部卖光 ≠ 没成交
    #    清仓后富途不再返回这条持仓。不区分的话会把成功的清仓记成
    #    "买了单但没成交"，进而触发「买回失败」那类假警报。
    pf7 = mod.FutuSimPortfolio("HK")
    pf7._query_rows = lambda: []
    pf7._backend = _FakeBackend()
    pf7.invalidate()
    pf7._index["P1"] = ("HK", "00700")
    pf7.reduce_position("P1", 300.0, 424.6)
    if pf7.last_error and ("未成交" in pf7.last_error or "未出现" in pf7.last_error):
        failures.append(
            f"全部卖光被误判成没成交（allow_missing 缺失）: {pf7.last_error}"
        )

    # ⑨ 账本的可卖额度必须真的被 can_sell_qty 压住
    #    只测 _sellable_cap 是不够的：中间那层 min() 才是真正生效的地方。
    import datetime as _dt

    ledger_b = CorePositionLedger()
    ledger_b._save = _no_persist
    open_ts = _dt.datetime.now().replace(
        hour=0, minute=0, second=0, microsecond=0
    ).timestamp()
    pfb = mod.FutuSimPortfolio("CN")
    pfb._query_rows = lambda: [
        {"code": "SZ.300750", "stock_name": "宁德时代", "qty": 300.0,
         "can_sell_qty": 0.0, "cost_price": 289.0, "nominal_price": 286.99,
         "currency": "CNH", "position_id": "PB"},
    ]
    pfb.invalidate()
    got_b = ledger_b.sellable_today_shares(
        "300750", pfb, now=time.time(), session_open_ts=open_ts
    )
    if abs(got_b) > 1e-9:
        failures.append(
            f"A股当日买入（can_sell_qty=0）却被判为可卖 {got_b:.0f} 份 "
            f"—— 卖单会被富途以 T+1 为由拒掉"
        )

    # ⑩ get_summary 字段与虚拟盘对齐
    pf6 = mod.FutuSimPortfolio("HK")
    pf6._fetch_rows = lambda: []
    pf6._account = lambda: None
    pf6.invalidate()
    summary = pf6.get_summary()
    for key in ("total_value", "total_capital", "used_capital",
                "available_capital", "position_count"):
        if key not in summary:
            failures.append(f"get_summary 缺字段 {key}（引擎/账本会 KeyError 或兜底成 0）")
    if summary.get("currency") != "HKD":
        failures.append(f"HK 组合币种应为 HKD，得到 {summary.get('currency')!r}")

    return failures


# ─────────────────────────────────────────────────────────────
# 静态 / 注入
# ─────────────────────────────────────────────────────────────

def code_only(path: Path) -> str:
    """剥掉注释与 docstring 后的代码文本。

    ❗静态规则必须扫这个，不能扫原始文本：源码里写着「不做汇率换算」这种
    **说明性**文字，直接搜会把正确的实现判成违规（假红），反过来又逼人
    把注释写得含糊其辞。AST unparse 天然不带注释，再手动摘掉 docstring。
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef,
                                 ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            node.body = body[1:] or [ast.Pass()]
    return ast.unparse(tree)


def static_checks() -> list:
    failures = []
    cache: Dict[Path, str] = {}

    def text_of(path: Path) -> str:
        if path not in cache:
            cache[path] = path.read_text(encoding="utf-8") if path.exists() else ""
        return cache[path]

    def code_of(path: Path) -> str:
        key = (path, "code")
        if key not in cache:  # type: ignore[operator]
            try:
                cache[key] = code_only(path)  # type: ignore[index]
            except SyntaxError:
                cache[key] = text_of(path)  # type: ignore[index]
        return cache[key]  # type: ignore[index]

    for path, pattern, why in REQUIRED_RULES:
        if not path.exists():
            failures.append(f"文件不存在: {path}")
            continue
        if not re.search(pattern, code_of(path)) and not re.search(pattern, text_of(path)):
            failures.append(f"[静态] {path.name}: {why}")
    for path, pattern, why in FORBIDDEN_RULES:
        if not path.exists():
            continue
        if re.search(pattern, code_of(path)):
            failures.append(f"[禁止] {path.name}: {why}")
    return failures


def apply_injection(inj) -> bool:
    path: Path = inj["file"]
    text = path.read_text(encoding="utf-8")
    if inj["old"] not in text:
        print(f"  ⚠️  注入锚点不存在，跳过：{inj['name']}")
        return False
    # count=-1：同一段代码可能在多个方法里出现（账本里 carried_in_shares 与
    # sellable_today_shares 各有一份 min(inherited, cap)）。只替换第一处会
    # 改到别的方法上，用例却测的是另一处 → 注入静默失效，守卫假绿。
    count = inj.get("count", 1)
    path.write_text(text.replace(inj["old"], inj["new"], count), encoding="utf-8")
    try:
        ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError as e:
        path.write_text(text, encoding="utf-8")
        print(f"  ⚠️  注入后语法非法（无效用例），已还原：{inj['name']} → {e}")
        return False
    return True


def restore(inj, original: str):
    inj["file"].write_text(original, encoding="utf-8")


def run_injections() -> int:
    caught = 0
    for inj in INJECTIONS:
        original = inj["file"].read_text(encoding="utf-8")
        print(f"\n注入：{inj['name']}")
        if not apply_injection(inj):
            continue
        try:
            s_fail = static_checks()
            b_fail = behaviour_checks()
            found = s_fail + b_fail
            print(f"     [调试] 静态 {len(s_fail)} 项 / 行为 {len(b_fail)} 项")
        except Exception as e:
            found = [f"守卫自身抛异常: {e}"]
        finally:
            restore(inj, original)
        if found:
            caught += 1
            print(f"  ✅ 被捕获（{len(found)} 项）")
            for f in found[:4]:
                print(f"       · {f[:100]}")
        else:
            print("  ❌ 没抓到 —— 这条守卫是摆设！")
        # 逐例还原并确认，避免上一例的残留污染下一例
        if inj["file"].read_text(encoding="utf-8") != original:
            print("  🚨 还原失败，强制重写")
            inj["file"].write_text(original, encoding="utf-8")
    print(f"\n负向注入：{caught}/{len(INJECTIONS)} 被捕获")
    return caught


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--exercise-injections", action="store_true")
    args = ap.parse_args()

    if args.exercise_injections:
        return 0 if run_injections() == len(INJECTIONS) else 1

    if args.self_test:
        return run_injections() == len(INJECTIONS) and not static_checks()

    failures = static_checks() + behaviour_checks()
    if failures:
        print(f"❌ {len(failures)} 项不通过")
        for f in failures:
            print("  -", f)
        return 1
    print("✅ 富途模拟组合适配器守卫全绿（静态 + 行为）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
