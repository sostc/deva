#!/usr/bin/env python3
"""守卫：自动建仓的「在飞单」幂等闸门。

要防的失效
----------
2026-10-14 富途模拟仓首航**实跑**踩到三件事，凑起来就是一次双倍仓位：

1. **报单 ≠ 成交**。SH.588200 从报单到 ``FILLED_ALL`` 用了 **4 秒**
   （13:00:24 → 13:00:28）。
2. **等待窗口只有 0.8 秒**。``FutuSimPortfolio._reload`` 重试 3 次 × 0.4s，
   等不到持仓就返回 ``None``。
3. **幂等槽位按分钟分槽** ``core_{日期}_{分钟}``，而轮询间隔是 30 秒。

只要成交慢一点、跨过分钟边界，下一轮 ``carried`` 仍读到 0，于是拿着全额
``missing`` 再报一单 —— 40 万份的底仓会变成 80 万份。内存标记救不了
（进程一重启就没了），所以判据必须是**问券商这笔单还在不在飞**。

顺带压住第二个副作用：``open_position`` 返回 ``None`` 曾被记成
``ERROR 底仓建仓失败（可能撞仓位限额）``—— 错了两层：那时单**已经报出去了**，
而且病因是猜的。真被额度挡住时，这类假警报会把真信号稀释掉。
用法
----

    python scripts/verify/verify_core_establish_inflight.py            # 全量
    python scripts/verify/verify_core_establish_inflight.py --strict   # CI 用
    python scripts/verify/verify_core_establish_inflight.py --exercise-injections
"""

from __future__ import annotations

import argparse
import ast
import logging
import re
import sys
import time
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from deva.naja.bandit.core_establish_gate import EstablishmentVerdict  # noqa: E402

RUNNER_PY = REPO / "deva/naja/bandit/t_rotation_runner.py"
PORT_PY = REPO / "deva/naja/bandit/futu_sim_portfolio.py"

# 静态：必须具备的要素
REQUIRED_RULES = [
    (PORT_PY, r"def in_flight_buy_orders", "组合缺少在飞单查询（建仓幂等的判据来源）"),
    (PORT_PY, r"ORDER_SETTLED_STATES", "缺少订单终态清单（在飞判定会退化成猜）"),
    (PORT_PY, r"def _query_orders",
     "订单拉取应与过滤判据拆开（不拆的话守卫连不上富途就测不了过滤逻辑）"),
    (PORT_PY, r"if rows is None", "必须显式处理查询失败(None)，不能顺手折叠成 []"),
    (RUNNER_PY, r"def _probe_inflight", "runner 缺少在飞单探测"),
    (RUNNER_PY, r"if inflight is None", "必须区分「查不到」与「确认没有」"),
    (RUNNER_PY, r"if inflight:", "有单在飞时必须跳过，不能重复报单"),
    (RUNNER_PY, r"getattr\(pf, .in_flight_buy_orders., None\)",
     "虚拟盘没有这个方法，必须用 getattr 探测后放行（duck-type 兼容）"),
]

# 静态：禁止出现（扫的是**剥掉注释/docstring**的代码，不是原文）
FORBIDDEN_RULES = [
    (PORT_PY, r"rows or \[\]",
     "禁止把查询失败(None) 折叠成空列表 —— 等于宣称「接口失联 = 可以下单」"),
    (RUNNER_PY, r"if not inflight",
     "禁止 `if not inflight` —— 会把 None（查不到）与 []（确认没有）混为一谈"),
    (RUNNER_PY, r"底仓建仓失败",
     "禁用旧的误导文案：走到那里时单**已经报出去了**，不是失败"),
    (RUNNER_PY, r"可能撞仓位限额",
     "禁止在未知原因时猜测病因（真被额度挡住时会把排查带偏）"),
]

# 负向注入：故意把代码改坏，守卫必须报红
INJECTIONS = [
    {
        "name": "runner 不再区分「查不到」：if inflight is None → if False",
        "file": RUNNER_PY,
        "old": "        if inflight is None:\n",
        "new": "        if False:\n",
    },
    {
        "name": "有单在飞也照样下单：if inflight: → if False:",
        "file": RUNNER_PY,
        "old": "        if inflight:\n",
        "new": "        if False:\n",
    },
    {
        "name": "组合把查询失败折叠成「没有」：return None → return []",
        "file": PORT_PY,
        "old": "            return None\n        out: List[Dict[str, Any]] = []\n",
        "new": "            return []\n        out: List[Dict[str, Any]] = []\n",
    },
    {
        "name": "终态判定被删（已成交的单永远算在飞 → 永久卡住不补）",
        "file": PORT_PY,
        "old": "            if status in self.ORDER_SETTLED_STATES:\n                continue\n",
        "new": "",
    },
    {
        "name": "过滤不再看买卖方向（卖单被当成在飞买单）",
        "file": PORT_PY,
        "old": (
            "            if str(row.get(\"trd_side\") or \"\").strip().upper() "
            "!= \"BUY\":\n                continue\n"
        ),
        "new": "",
    },
    {
        "name": "慢成交又变回 ERROR 假警报",
        "file": RUNNER_PY,
        "old": (
            "            log.info(\n"
            "                f\"[TRotationRunner] 🕐 {spec.name}({spec.code}) 已报单 \"\n"
        ),
        "new": (
            "            log.error(\n"
            "                f\"[TRotationRunner] 底仓建仓失败 {spec.name}({spec.code}) \"\n"
        ),
    },
    {
        "name": "折算目标时漏传 market（跨账户跨币种量纲）",
        "file": RUNNER_PY,
        "old": "self.total_assets(spec.market)",
        "new": "self.total_assets()",
    },
]


# ─────────────────────────────────────────────────────────────
# 行为用例
# ─────────────────────────────────────────────────────────────

class _CaptureHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append((record.levelname, record.getMessage()))


class _FakePF:
    """duck-type 组合：只实现 ``_maybe_establish_core`` 会碰到的那几个方法。

    ❗``in_flight_buy_orders`` 的返回值是本守卫的核心被测对象，三种形状
    必须分别构造：``[]`` / ``[{...}]`` / ``None``。
    """

    def __init__(self, inflight=None, open_result=None, total=1_000_000.0):
        self._inflight = inflight
        self._open_result = open_result
        self._total = total
        self.open_calls = []
        self.probe_calls = 0

    def get_summary(self):
        return {
            "total_capital": self._total, "available_capital": self._total,
            "used_capital": 0.0, "total_value": self._total,
            "position_count": 0, "currency": "CNY",
        }

    def get_all_positions(self, status=None):
        return []

    def in_flight_buy_orders(self, code):
        self.probe_calls += 1
        return self._inflight

    def open_position(self, **kw):
        self.open_calls.append(kw)
        return self._open_result


class _FakeEngine:
    """吃下 ``register_target`` 什么都不做 —— 本守卫只关心有没有下单。"""

    def __init__(self):
        self.targets = {}

    def register_target(self, code, target, name=None, note=None):
        self.targets[code] = target


class _VirtualPF(_FakePF):
    """虚拟盘：压根没有 ``in_flight_buy_orders``（下单即成交，无中间态）。

    runner 必须靠 ``getattr`` 探测到「没有这个方法」并放行 ——
    这道兼容要是漏了，虚拟盘路径会被完全挡死。
    """

    in_flight_buy_orders = None


class _FakeGate:
    """假闸门：把「补仓要不要问大环境」这件事固定住。

    ❗本守卫测的是**在飞单幂等**与「折算用的总资产口径」，不是大环境闸门。
    闸门现在默认开，若不在这里显式放行，所有正向用例都会被
    「决策中心不可用 → 本轮不建仓」挡掉，变成一个没人看得懂的全红。
    大环境闸门另有 ``verify_core_establish_gate.py`` 专门覆盖。
    """

    def __init__(self, verdict=None):
        self.verdict = verdict or EstablishmentVerdict(
            allowed=True, source="decision_center", action_type="act_fully",
            size_hint=1.0, reason="守卫注入放行",
        )
        self.calls = []

    def evaluate(self, spec, price, minutes_to_close):
        self.calls.append((spec.code, price, minutes_to_close))
        return self.verdict


def _establish(pf, ledger, runner_cls, spec_cls, virtual_fallback=None,
               verdict=None):
    """真的跑一次建仓决策，返回组合对象（用来数有没有下单）。"""
    spec = spec_cls(
        code="588200", bus_code="sh588200", name="科创芯片ETF嘉实",
        market="CN", target_shares=0.0, round_lot=100.0, alloc_pct=40.0,
    )
    gate = _FakeGate(verdict)
    runner = runner_cls(
        specs=[spec], establish_missing=True, poll_seconds=30.0,
        establish_gate=gate,
    )
    runner._portfolios = {"CN": pf}
    runner._engines = {"CN": _FakeEngine()}
    if virtual_fallback is not None:
        # 真仓模式下 self._portfolio（虚拟盘兜底）仍然在。故意给它一个
        # **明显不同**的总资产，让「漏传 market」折算时无所遁形。
        runner._portfolio = virtual_fallback
    runner._ledger = ledger
    now = time.time()
    quote = SimpleNamespace(current=0.986, prev_close=0.98)
    runner._maybe_establish_core(
        spec, quote, now, now - 600.0, time.strftime("%Y-%m-%d")
    )
    return pf


def behaviour_checks() -> list:
    failures = []
    import importlib

    # ❗必须 reload：负向注入改的是**磁盘上的源码**，而模块只在首次 import
    # 时进内存。不重载的话注入根本作用不到被测代码（全是假绿），更糟的是
    # 若首次 import 恰好发生在文件被注入那一刻，污染版会被永久固化。
    import deva.naja.bandit.core_position as cp_mod
    import deva.naja.bandit.futu_sim_portfolio as port_mod
    import deva.naja.bandit.t_rotation_runner as run_mod

    run_mod = importlib.reload(run_mod)
    port_mod = importlib.reload(port_mod)
    cp_mod = importlib.reload(cp_mod)

    # 守卫绝不落盘：
    CorePositionLedger = cp_mod.CorePositionLedger

    def _no_persist(*_a, **_kw):
        return None

    CorePositionLedger._save = _no_persist
    ledger = CorePositionLedger()
    ledger._save = _no_persist

    TRotationRunner = run_mod.TRotationRunner
    CoreHoldingSpec = run_mod.CoreHoldingSpec

    # ① 有单在飞 → 不许重复报单（双倍仓位是这次要挡的事故本身）
    pf1 = _FakePF(inflight=[{
        "order_id": "9275129", "code": "SH.588200",
        "trd_side": "BUY", "order_status": "SUBMITTED",
    }])
    pf1 = _establish(pf1, ledger, TRotationRunner, CoreHoldingSpec)
    if pf1.open_calls:
        failures.append("有买单在飞却仍然下了单 —— 会买成双倍仓位")
    if pf1.probe_calls < 1:
        failures.append("在飞单探测没被调用（闸门形同虚设）")

    # ② 查不到(None) → 保守不下单。
    #    ❗这是本守卫最要紧的一条：None 与 [] 在业务上完全相反，
    #    接口失联绝不能等于「放心下单」。
    pf2 = _FakePF(inflight=None)
    pf2 = _establish(pf2, ledger, TRotationRunner, CoreHoldingSpec)
    if pf2.open_calls:
        failures.append(
            "查不到在飞单(None) 却照样下单 —— 把「我不知道」当成了「没有」"
        )

    # ③ 确认没有([]) → 正常下单。闸门不能误伤正常建仓。
    pf3 = _FakePF(inflight=[], open_result=SimpleNamespace(position_id="P1"))
    pf3 = _establish(pf3, ledger, TRotationRunner, CoreHoldingSpec)
    if not pf3.open_calls:
        failures.append("确认没有在飞单却没下单（闸门误伤了正常建仓）")
    elif len(pf3.open_calls) != 1:
        failures.append(f"一轮只应报一单，实际 {len(pf3.open_calls)} 单")

    # ④ 虚拟盘不支持探测 → 照旧放行（duck-type 兼容不能倒退）
    pf4 = _VirtualPF(open_result=SimpleNamespace(position_id="P1"))
    pf4 = _establish(pf4, ledger, TRotationRunner, CoreHoldingSpec)
    if not pf4.open_calls:
        failures.append(
            "虚拟盘不支持在飞单探测时应照旧放行 —— duck-type 兼容漏了"
        )

    # ⑤ 慢成交（open_position 返回 None）不许再记 ERROR
    handler = _CaptureHandler()
    lg = logging.getLogger("deva.naja.bandit.t_rotation_runner")
    old_level = lg.level
    lg.addHandler(handler)
    lg.setLevel(logging.DEBUG)
    try:
        pf5 = _FakePF(inflight=[], open_result=None)
        pf5 = _establish(pf5, ledger, TRotationRunner, CoreHoldingSpec)
    finally:
        lg.removeHandler(handler)
        lg.setLevel(old_level)
    if not pf5.open_calls:
        failures.append("open_position 返回 None 的场景没跑到（用例前置失败）")
    errors = [msg for level, msg in handler.records if level == "ERROR"]
    if errors:
        failures.append(
            f"慢成交被记成 ERROR —— 正是要消灭的那种假警报: {errors[0][:80]}"
        )
    if not any("等待成交确认" in msg for _lvl, msg in handler.records):
        failures.append(
            "慢成交没有留下「已报单，等待成交确认」的可追溯记录（无从自证）"
        )

    # ⑥ 组合层：None 必须原样透传，不能被折叠成 []
    pfx = port_mod.FutuSimPortfolio("CN")
    pfx._query_orders = lambda: None
    got = pfx.in_flight_buy_orders("588200")
    if got is not None:
        failures.append(
            f"_query_orders 失败(None) 必须透传成 None，实际 {got!r} "
            f"—— 折叠成 [] 等于宣称「接口失联 = 可以下单」"
        )

    # ⑦ 组合层：过滤判据本身
    #    ❗每条数据都是反方向用例：不该算的不能算进去，该算的不能漏。
    #    特别是「未知状态」必须**保守算在飞**（认不出来按危险的那边算）。
    pfx2 = port_mod.FutuSimPortfolio("CN")
    pfx2._query_orders = lambda: [
        {"code": "SH.588200", "trd_side": "BUY", "order_status": "FILLED_ALL", "order_id": "1"},
        {"code": "SH.588200", "trd_side": "BUY", "order_status": "SUBMITTED", "order_id": "2"},
        {"code": "SH.588200", "trd_side": "SELL", "order_status": "SUBMITTED", "order_id": "3"},
        {"code": "SZ.300750", "trd_side": "BUY", "order_status": "SUBMITTED", "order_id": "4"},
        {"code": "SH.588200", "trd_side": "BUY", "order_status": "CANCELLED_ALL", "order_id": "5"},
        {"code": "SH.588200", "trd_side": "BUY", "order_status": "WHO_KNOWS", "order_id": "6"},
        {"code": "SH.588200", "trd_side": "BUY", "order_status": "FILLED_PART", "order_id": "7"},
    ]
    got7 = pfx2.in_flight_buy_orders("588200")
    ids = sorted(str(o.get("order_id")) for o in (got7 or []))
    if ids != ["2", "6", "7"]:
        failures.append(
            f"在飞单过滤错：应为 ['2','6','7']（已成交/已撤/卖单/别的标的不算，"
            f"未知状态与部分成交保守算在飞），实际 {ids}"
        )
    # 前缀：富途回的是 SH.588200，配置里是 588200
    if got7 and str(got7[0].get("order_id")) != "2":
        failures.append("订单代码前缀剥离失败（配置里的裸码匹配不上）")

    # ⑧ 目标份额必须按**本市场账户**折，不能掉进虚拟盘兜底。
    #    真仓模式三个市场是三个独立账户、三种本位币，漏传 market 就是
    #    「拿一堆账户的钱 ÷ 另一个市场的价格」。
    #    ❗反向对照：本用例刻意给虚拟盘兜底一个差很远的总资产。
    pf8 = _FakePF(inflight=[], open_result=SimpleNamespace(position_id="P1"))
    pf8 = _establish(
        pf8, ledger, TRotationRunner, CoreHoldingSpec,
        virtual_fallback=_FakePF(total=77_777.0),
    )
    if not pf8.open_calls:
        failures.append("⑧ 前置失败：没下单，量纲用例测不到")
    else:
        got_qty = float(pf8.open_calls[0].get("quantity") or 0.0)
        # CN 账户 1,000,000 × 40% ÷ 0.986 → 405678 → 取整到百 = 405600
        if abs(got_qty - 405600.0) > 1e-6:
            failures.append(
                f"目标份额用了错误的账户折算：下单 {got_qty:.0f} 份，"
                f"按 CN 账户应为 405600 份（掉进了虚拟盘兜底 = 跨账户量纲错）"
            )

    return failures


# ─────────────────────────────────────────────────────────────
# 静态 / 注入
# ─────────────────────────────────────────────────────────────

def code_only(path: Path) -> str:
    """剥掉注释与 docstring 后的代码文本。

    ❗静态规则必须扫这个，不能扫原始文本：源码注释里写着「不许记成
    底仓建仓失败」这种**说明性**文字，直接搜原文会把正确的实现判成
    违规（假红），反过来逼人把注释写得含糊其辞。
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
    cache = {}

    def code_of(path: Path) -> str:
        if path not in cache:
            try:
                cache[path] = code_only(path)
            except SyntaxError:
                cache[path] = path.read_text(encoding="utf-8")
        return cache[path]

    for path, pattern, why in REQUIRED_RULES:
        if not path.exists():
            failures.append(f"文件不存在: {path}")
            continue
        if not re.search(pattern, code_of(path)):
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
    # count=-1 用于同一段代码出现在多处的情况。默认只替换第一处会改到别处，
    # 用例却测的是没改到的那处 → 注入静默失效、守卫假绿。
    path.write_text(
        text.replace(inj["old"], inj["new"], inj.get("count", 1)),
        encoding="utf-8",
    )
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
            found = static_checks() + behaviour_checks()
        except Exception as e:
            found = [f"守卫自身抛异常: {e}"]
        finally:
            restore(inj, original)
        if found:
            caught += 1
            print(f"  ✅ 被捕获（{len(found)} 项）")
            for f in found[:3]:
                print(f"       · {f[:100]}")
        else:
            print("  ❌ 没抓到 —— 这条守卫是摆设！")
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

    failures = static_checks() + behaviour_checks()
    if failures:
        print(f"❌ {len(failures)} 项不通过")
        for f in failures:
            print("  -", f)
        return 1
    print("✅ 建仓在飞单闸门守卫全绿（静态 + 行为）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
