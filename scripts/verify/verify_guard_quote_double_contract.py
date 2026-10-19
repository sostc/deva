#!/usr/bin/env python3
"""守卫：**接进 runner 的行情替身必须 `get` + `fetch` 双契约齐全**，不许悄悄烂掉。

================================================================================
背景（2026-10-19 实锤，不是推测）
================================================================================

``c34f551``（Naja Bot）把 ``TRotationRunner`` 的取数从「每个标的各建一次连」
改成「一轮只 ``fetch`` 一次再分给各标的」。runner 侧改了，**守卫里的测试替身
没跟着改** —— ``FakeQuotes`` / ``QuoteSource`` 只有 ``get`` 没有 ``fetch``。

后果链：

    runner 调 src.fetch(...) → AttributeError → 走 except 兜底
    → 每轮打一条「批量取行情失败」
    → 各标的拿到失败占位 → 全跳过

    verify_t_rotation_wiring      ❌ 9/25
    verify_core_position_batch_alerts ❌ 3/3

**最坏的地方在于：它报错了，而且报了两轮都被当成环境噪声。** 因为
``run_all_guards`` 的摘要被退出噪声顶掉（见 ``verify_guard_reason_summary``），
显示成「redis ConnectionError」。于是这两份守卫**长期红着却没人知道红在哪**，
本该被验证的分批逻辑一条没跑。

这是静默失效家族里最阴的一种：**测试的替身比被测代码先腐烂**。产品代码是好的，
替身是烂的，于是守卫测的是「降级路径稳不稳」，而不是「业务逻辑对不对」，
而且降级路径写得很稳 → 一片绿（或一片无法解释的红）。

================================================================================
核心不变量
================================================================================

**凡是以 ``quotes=`` 注入 runner 的本地替身类，必须同时实现**

    get(code, market=None)      —— 单点回退入口
    fetch(requests)             —— 批量入口（runner 每轮唯一取数口）

**缺任一即失败。** 并且 ``fetch`` 的返回必须对齐 ``FutuQuoteSource.fetch``：
**原始代码 → quote**，取不到的条目也要留在 dict 里且 ``ok=False`` ——
真实实现就是「失败的标的也在场」，替身不同构，测出来的行为就是假的。

反向也不能过头：只在守卫文件里定义、但**从没接进 ``quotes=``** 的类
（比如行情值对象 ``Quote`` / ``_MissingQuote``）不许误报 ——
它们本来就不该有取数方法。

================================================================================
用法
================================================================================

    python3 scripts/verify/verify_guard_quote_double_contract.py
    python3 scripts/verify/verify_guard_quote_double_contract.py --strict
    python3 scripts/verify/verify_guard_quote_double_contract.py --exercise-injections
"""

from __future__ import annotations

import argparse
import ast
import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
VERIFY_DIR = REPO / "scripts" / "verify"
RUNNER_PY = REPO / "deva" / "naja" / "bandit" / "t_rotation_runner.py"

REQUIRED = ("get", "fetch")
QUOTE_NAME_RE = ("quote",)

# 现状基线：verify 目录里有 3 处 `quotes=` 注入点，全都指向本地替身
# （做 T 链路 2 处 + 底仓分批告警 1 处）。
# 掉到 3 以下 = 要么某处替身退化成了裸 `object()`（该守卫从此测空气）、
# 要么扫描锚点腐烂。**加了新注入点请同步抬这个数**，别让它变成橡皮图章。
MIN_WIRED_DOUBLES = 3

# 顶层允许出现的节点：只含这些的模块 import 起来没有副作用，可以安全实例化替身
_SAFE_TOP = (
    ast.Import,
    ast.ImportFrom,
    ast.ClassDef,
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.Pass,
)

# 顶层允许直接调用的（守卫脚本标准套路：sys.path 摆位 + 切临时库）
_SAFE_TOPLEVEL_CALLS = {
    "isolate_guard_db",
    "sys.path.insert",
    "sys.path.append",
    "os.path.dirname",
    "os.path.join",
    "os.path.abspath",
    "os.makedirs",
    "os.environ.get",
    "logging.getLogger",
    "load_dotenv",
    "Path",
    "dict",
    "list",
    "tuple",
    "set",
    "float",
    "int",
    "str",
    "re.compile",
}


def _rel(p: Path) -> str:
    try:
        return p.relative_to(REPO).as_posix()
    except ValueError:
        return str(p)


def _guard_files() -> list:
    return sorted(VERIFY_DIR.glob("verify_*.py"))


# ── AST 工具 ─────────────────────────────────────────────────────────────────
def _classes(tree) -> dict:
    """模块里所有 ClassDef（含嵌套）→ 方法名集合。"""
    out: dict = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            out[node.name] = {
                n.name
                for n in node.body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
    return out


def _assigned_calls(tree) -> dict:
    """``x = Foo()`` → {x: Foo}，用来回查 ``quotes=x`` 这种间接注入。"""
    out = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue
        val = node.value
        if isinstance(val, ast.Call) and isinstance(val.func, ast.Name):
            out[node.targets[0].id] = val.func.id
    return out


def _wired_classes(tree, known: dict) -> list:
    """所有以 ``quotes=`` 注入、且是本模块**本地定义**的类名。

    返回**带重复**的列表：一处注入点算一次 —— 空转检查要数的是注入点，
    不是去重后的类名（同一个替身被注入两次，撤掉一处也得看得见）。
    """
    assigned = _assigned_calls(tree)
    found: list = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            if kw.arg != "quotes":
                continue
            val = kw.value
            if isinstance(val, ast.Call) and isinstance(val.func, ast.Name):
                cand = val.func.id
            elif isinstance(val, ast.Name):
                # 间接注入：`bus = FakeQuotes()` … `quotes=bus`
                cand = assigned.get(val.id, val.id)
            else:
                continue
            if cand in known:
                found.append(cand)
    return found


def _dotted(node) -> str | None:
    """`a.b.c` → "a.b.c"；其它 → None。"""
    parts = []
    cur = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if not isinstance(cur, ast.Name):
        return None
    parts.append(cur.id)
    return ".".join(reversed(parts))


def _safe_expr(node) -> bool:
    """表达式里只允许白名单调用（裸名字/属性引用无害）。"""
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            d = _dotted(n.func)
            if d is None or d not in _SAFE_TOPLEVEL_CALLS:
                return False
    return True


def _is_main_guard(test) -> bool:
    return any(isinstance(n, ast.Name) and n.id == "__name__" for n in ast.walk(test))


def _safe_stmt(node) -> bool:
    if isinstance(node, _SAFE_TOP):
        return True
    if isinstance(node, ast.Expr):
        return isinstance(node.value, ast.Constant) or _safe_expr(node)
    if isinstance(node, (ast.Assign, ast.AnnAssign)):
        return _safe_expr(node.value) if node.value is not None else True
    if isinstance(node, ast.If):
        # `if __name__ == "__main__":` 不算副作用（import 时不会执行）
        # ❗判据走 AST 而不是 unparse：`ast.unparse` 会把字符串渲染成单引号，
        #    拿 `'__name__'` 去匹配 `"__name__"` 永远匹配不上 → 全文件误报。
        if _is_main_guard(node.test):
            return True
        return (
            _safe_expr(node.test)
            and all(_safe_stmt(x) for x in node.body)
            and all(_safe_stmt(x) for x in node.orelse)
        )
    return False


def _top_level_unsafe_reason(tree) -> str:
    """顶层有副作用 → 返回原因；否则返回 ''。"""
    for node in tree.body:
        if _safe_stmt(node):
            continue
        return f"{type(node).__name__}: {ast.unparse(node)[:80]}"
    return ""


def _isolate_guard_db() -> None:
    """把 NB 指到临时库（幂等）。本守卫只实例化替身，但不写生产数据是硬规矩。"""
    if str(VERIFY_DIR) not in sys.path:
        sys.path.insert(0, str(VERIFY_DIR))
    try:
        from guard_sandbox import isolate_guard_db
    except Exception:  # noqa: BLE001 沙箱不可用就算了，检查照跑
        return
    isolate_guard_db()


def _load_module(path: Path, alias: str):
    spec = importlib.util.spec_from_file_location(alias, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── 扫描：接线 + 契约 ───────────────────────────────────────────────────────
def _scan() -> tuple:
    """返回 (违约的接线替身, 半残替身, 接线替身总数)。"""
    wired: list = []
    half: list = []
    total = 0
    for path in _guard_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as e:  # 语法都坏了，别的守卫会报，这里不重复
            wired.append((path, "<syntax>", [f"SyntaxError: {e}"]))
            continue
        classes = _classes(tree)
        sites = _wired_classes(tree, classes)
        total += len(sites)
        for name in sorted(set(sites)):
            missing = [m for m in REQUIRED if m not in classes[name]]
            if missing:
                wired.append((path, name, missing))
        # 名字带 quote 的类：只实现了其中一个 → 半残，迟早踩坑
        for name, methods in sorted(classes.items()):
            low = name.lower()
            if not any(k in low for k in QUOTE_NAME_RE):
                continue
            has = [m for m in REQUIRED if m in methods]
            if len(has) == 1:
                half.append((path, name, [m for m in REQUIRED if m not in methods]))
    return wired, half, total


def check_wired_doubles_have_both() -> list:
    """接进 `quotes=` 的替身必须 get + fetch 双全。"""
    wired, _, _ = _scan()
    out = []
    for path, cls, missing in wired:
        out.append(
            f"{_rel(path)} 的类 {cls} 被当 runner 的 quotes 注入，但缺 "
            f"{'/'.join(missing)} —— runner 会走 except 兜底，守卫测的就成了降级路径，"
            f"业务逻辑一条没跑到（2026-10-19：9/25 与 3/3 全假红）"
        )
    return out


def check_no_half_baked_quote_double() -> list:
    """名字带 quote 的替身只实现了一半 → 直接报，不许留着等人踩。"""
    _, half, _ = _scan()
    return [
        f"{_rel(path)} 的类 {cls} 只实现了 get/fetch 之一（缺 {'/'.join(missing)}）—— "
        f"半残替身只会让某条分支永远走降级"
        for path, cls, missing in half
    ]


def check_fetch_contract_keeps_original_keys() -> list:
    """运行时契约：fetch 必须返回 {原始代码: quote}，取不到的也要占位且 ok=False。

    ❗顶层有副作用的模块**不许静默跳过** —— 跳过等于这项检查是摆设（守卫
    「绿」≠在守）。真跳过了必须喊出来，让人去补白名单或拆顶层副作用。
    """
    out: list = []
    _isolate_guard_db()
    for path in _guard_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        classes = _classes(tree)
        wired = _wired_classes(tree, classes)
        if not wired:
            continue
        unsafe = _top_level_unsafe_reason(tree)
        if unsafe:
            out.append(
                f"{_rel(path)} 顶层有副作用、无法安全运行时校验（{unsafe}）—— "
                f"别让这项检查变成摆设：把顶层语句挪进函数，或补进白名单"
            )
            continue
        try:
            mod = _load_module(path, f"_qdc_{path.stem}")
        except Exception as e:  # noqa: BLE001 导入失败交给静态检查兜
            out.append(f"{_rel(path)} 无法安全导入以做运行时契约检查：{type(e).__name__}: {e}")
            continue
        for name in sorted(wired):
            cls = getattr(mod, name, None)
            if cls is None:
                out.append(f"{_rel(path)} 找不到类 {cls and name} —— 锚点腐烂")
                continue
            try:
                inst = cls()
                reqs = [("sh600000", "CN"), ("ZZZZZZ", "US")]
                res = inst.fetch(reqs)
            except Exception as e:  # noqa: BLE001 缺 fetch 就在这里现形
                out.append(
                    f"{_rel(path)}::{name}.fetch() 不可用：{type(e).__name__}: {e}"
                )
                continue
            if not isinstance(res, dict):
                out.append(f"{_rel(path)}::{name}.fetch() 应返回 dict，实为 {type(res).__name__}")
                continue
            for code, _m in reqs:
                if code not in res:
                    out.append(
                        f"{_rel(path)}::{name}.fetch() 的返回里丢了原始代码 {code} —— "
                        f"取不到的标的也必须占位（ok=False），否则下游按「行情缺失」整轮跳过"
                    )
                    continue
                if not hasattr(res[code], "ok"):
                    out.append(f"{_rel(path)}::{name}.fetch() 返回项缺 ok 属性（{code}）")
            missed = res.get("ZZZZZZ")
            if missed is not None and getattr(missed, "ok", None) is not False:
                out.append(f"{_rel(path)}::{name}.fetch() 对取不到的标的没有标 ok=False")
    return out


def _runner_prefetch():
    tree = ast.parse(RUNNER_PY.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "TRotationRunner":
            for sub in node.body:
                if isinstance(sub, ast.FunctionDef) and sub.name == "_prefetch_quotes":
                    return sub
    return None


def check_runner_uses_batch_fetch() -> list:
    """runner 侧的取数口必须是批量 `src.fetch(...)`，不许退回逐个 `get`。"""
    fn = _runner_prefetch()
    if fn is None:
        return [f"{_rel(RUNNER_PY)} 找不到 TRotationRunner._prefetch_quotes —— 锚点腐烂"]
    body = ast.unparse(fn)
    if "src.fetch(" not in body:
        return [
            f"{_rel(RUNNER_PY)}::_prefetch_quotes 不再调用 src.fetch(...) —— "
            f"替身契约改了的话必须同步改守卫替身，别让守卫测空气"
        ]
    if "for s in specs" not in body:
        return [f"{_rel(RUNNER_PY)}::_prefetch_quotes 没有把整轮 specs 一次喂给 fetch"]
    return []


def check_batch_failure_is_loud() -> list:
    """批量取数失败必须告警 —— `except: pass` 会让整轮静默失联。"""
    fn = _runner_prefetch()
    if fn is None:
        return [f"{_rel(RUNNER_PY)} 找不到 TRotationRunner._prefetch_quotes —— 锚点腐烂"]
    handlers = [
        h for n in ast.walk(fn)
        if isinstance(n, ast.Try)
        for h in n.handlers
    ]
    if not handlers:
        return [f"{_rel(RUNNER_PY)}::_prefetch_quotes 没有 try/except —— 一次网络抖动就能带崩整轮"]
    for h in handlers:
        src = ast.unparse(h)
        if "log.error" in src or "logger.error" in src or "log.warning" in src:
            return []
    return [
        f"{_rel(RUNNER_PY)}::_prefetch_quotes 的 except 里没有告警 —— "
        f"批量取数失败会静默，守卫红了你也不知道红在哪（就是这次的原始症状）"
    ]


def check_guard_is_not_vacuous() -> list:
    """至少还得找到 MIN_WIRED_DOUBLES 份接线的行情替身，否则本守卫是空转的。"""
    _, _, total = _scan()
    if total < MIN_WIRED_DOUBLES:
        return [
            f"只找到 {total} 份接线的行情替身（期望 ≥ {MIN_WIRED_DOUBLES}）—— "
            f"要么有替身被换成了裸 object()（守卫从此测空气），要么扫描锚点腐烂"
        ]
    return []


def _all_checks() -> list:
    failures: list = []
    failures += check_wired_doubles_have_both()
    failures += check_no_half_baked_quote_double()
    failures += check_fetch_contract_keeps_original_keys()
    failures += check_runner_uses_batch_fetch()
    failures += check_batch_failure_is_loud()
    failures += check_guard_is_not_vacuous()
    return failures


# ── 负向注入 ─────────────────────────────────────────────────────────────────
T_ROTATION = VERIFY_DIR / "verify_t_rotation_wiring.py"
BATCH_ALERTS = VERIFY_DIR / "verify_core_position_batch_alerts.py"

INJECTIONS = [
    {
        "name": "删掉 FakeQuotes.fetch（回到 c34f551 时的腐烂现场）",
        "file": T_ROTATION,
        "old": "    def fetch(self, requests):\n",
        "new": "    def fetch_removed(self, requests):\n",
    },
    {
        "name": "把 QuoteSource.fetch 改名（另一份守卫的替身烂掉）",
        "file": BATCH_ALERTS,
        "old": "    def fetch(self, requests):\n",
        "new": "    def fetch_many(self, requests):\n",
    },
    {
        "name": "fetch 丢掉取不到的标的（原始代码不在 key 里）",
        "file": T_ROTATION,
        "old": "            out[key] = quote if quote is not None else _MissingQuote(key)\n",
        "new": "            if quote is not None:\n                out[key] = quote\n",
    },
    {
        "name": "runner 退回逐个 get（批量契约被拆）",
        "file": RUNNER_PY,
        "old": "            return src.fetch([(s.code, s.market) for s in specs])\n",
        "new": "            return {s.code: src.get(s.code, s.market) for s in specs}\n",
    },
    {
        "name": "批量取数失败静默 pass",
        "file": RUNNER_PY,
        "old": '            log.error(f"[TRotationRunner] 批量取行情失败: {e}")\n',
        "new": "            pass\n",
    },
    {
        "name": "行情依赖换成裸 object()（替身消失，守卫从此测空气）",
        "file": T_ROTATION,
        "old": (
            "        portfolio=vp, quotes=bus, engine=eng, ledger=ledger, specs=[spec],\n"
        ),
        "new": (
            "        portfolio=vp, quotes=object(), engine=eng, ledger=ledger, specs=[spec],\n"
        ),
    },
    {
        # 反方向：守卫文件里那些**行情值对象**（Quote / _MissingQuote）本来就不该有
        # 取数方法。新增一个同名风格的空壳类，不许被误报成「半残替身」。
        "name": "新增不带取数方法的行情值对象（反方向：不许误报）",
        "file": T_ROTATION,
        "old": "class _MissingQuote:\n",
        "new": (
            "class QuoteSnapshot:\n"
            "    \"\"\"行情值对象（反方向用例）：不该有 get/fetch。\"\"\"\n"
            "\n"
            "    def __init__(self):\n"
            "        self.current = 1.0\n"
            "\n"
            "\n"
            "class _MissingQuote:\n"
        ),
        "expect_clean": True,
    },
]


def run_injections() -> int:
    originals = {}
    for inj in INJECTIONS:
        f = inj["file"]
        if f not in originals:
            originals[f] = f.read_text(encoding="utf-8")

    caught = 0
    expected = len(INJECTIONS)
    missed = 0
    reasons: list = []
    try:
        for inj in INJECTIONS:
            f = inj["file"]
            original = originals[f]
            hits = original.count(inj["old"])
            if hits != 1:
                missed += 1
                print(f"❌ 注入锚点命中 {hits} 次（期望 1，守卫腐烂信号）：{inj['name']}")
                continue
            print(f"· 注入：{inj['name']}")
            f.write_text(original.replace(inj["old"], inj["new"]), encoding="utf-8")
            try:
                found = _all_checks()
            except Exception as e:  # noqa: BLE001
                found = [f"守卫自身抛异常: {type(e).__name__}: {e}"]
            finally:
                f.write_text(original, encoding="utf-8")

            if inj.get("expect_clean"):
                if found:
                    print(f"  ❌ 反方向用例被误报：{found[0][:110]}")
                else:
                    caught += 1
                    print("  ✅ 正确地没有报警（值对象不是取数源）")
            elif found:
                caught += 1
                reasons.append(found[0][:60])
                print(f"  ✅ 被捕获（{len(found)} 项）")
                for x in found[:2]:
                    print(f"       · {x[:110]}")
            else:
                print("  ❌ 没抓到 —— 这条守卫是摆设！")
    finally:
        for f, original in originals.items():
            if f.read_text(encoding="utf-8") != original:
                print(f"  🚨 还原失败，强制重写 {_rel(f)}")
                f.write_text(original, encoding="utf-8")

    print(f"\n负向注入：{caught}/{expected} 被捕获"
          + (f"（另有 {missed} 条锚点未命中，已计失败）" if missed else ""))
    if len(set(reasons)) != len(reasons):
        print(f"⚠️  失败原因有重复（{len(reasons)} 条注入只有 {len(set(reasons))} 种原因）—— "
              f"可能是第一条注入把坏版本固化进了 sys.modules（假捕获），请逐条核对")
        return -1
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
        print("❌ 行情替身双契约守卫 失败：")
        for f in failures:
            print(f"   - {f}")
        return 1 if args.strict else 0
    print("✅ 行情替身双契约守卫全绿"
          "（接线的替身 get+fetch 齐全 · fetch 保留原始代码键 · runner 走批量 · 失败必告警）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
