#!/usr/bin/env python3
"""守卫自身 hygiene：不许把测试数据写进生产库 ``~/.deva/nb.sqlite``。

背景
----
``NB(name)`` 在**实例化时**才读环境变量 ``DEVA_DB_PATH`` 决定落盘位置。
守卫一旦用了真实 NB（哪怕账户名叫 ``T_ROTATION_GUARD`` 这种一看就是测试的
名字），跑一遍就会把假持仓、假价格写进生产库：

    T_ROTATION_TEST 账户下 588200 持仓 9000 份 @3350.25
    ↑ 那是 ``verify_t_rotation_core.py`` 构造的假价格序列，
      却跟真钱躺在同一个 sqlite 里，UI 上照样统计进总资金。

约定
----
* 会写 NB 的守卫：脚本顶部 ``isolate_guard_db()``（见 ``guard_sandbox.py``），
  必须在**任何 deva 导入之前**。
* 确实要读真实数据的守卫（如 ``verify_focus_advisor.py`` 要靠真实持仓推导
  供应链主题）：显式声明 ``TOUCHES_PRODUCTION_DB = True`` 并写清理由，
  同时沿用既有的「临时表名 / 临时账户 + 跑完清理 + 真实表前后比对」约定。

本守卫做两件事
--------------
1. **静态**：扫 ``scripts/verify/*.py``，凡碰到 NB / VirtualPortfolio 的，
   必须满足上面两条约定之一。
2. **运行期**：真跑一遍做 T 的两套守卫，比对生产库 ``accounts`` 的前后指纹。
   静态检查能被注释绕过，这条绕不过去 —— 但代价是：若某个守卫真的没隔离，
   它会**当场污染生产库**，所以本守卫跑前先拍快照、跑后若有变化立即还原。

跑法
----
    cd <项目根>
    env -u PYTHONPATH TMPDIR=$(mktemp -d) \\
        /Users/spark/.local/bin/python3 scripts/verify/verify_guard_db_isolation.py

退出码：0 = PASS；任何违约 1。
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import subprocess
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
VERIFY_DIR = os.path.join(ROOT, "scripts", "verify")
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

PY = sys.executable or "python3"

# 明确的白名单：这些脚本**故意**读真实数据，已在自己的 docstring 里说明，
# 并靠「临时表 + 跑完清理 + 真实表前后比对」保证不脏 —— 不套临时库。
DECLARED_PRODUCTION_READERS = {
    "verify_focus_advisor.py",
    "verify_core_hotpath_micro.py",   # 只建空表测命名空间缓存，不落业务数据
}

# 会触发落盘的调用形态
WRITE_HINTS = ("NB(", "NB ('", "VirtualPortfolio(", "DBStream(")

TARGETS = [
    "scripts/verify/verify_t_rotation_core.py",
    "scripts/verify/verify_t_rotation_wiring.py",
]

_failures = []


def _check(name, ok, detail=""):
    tag = "OK  " if ok else "FAIL"
    print(f"[{tag}] {name}{('  —— ' + detail) if detail else ''}")
    if not ok:
        _failures.append((name, detail))


# ────────────────────────────────────────────────────────────── 静态
def _strips_docstring(src: str) -> str:
    """按 AST 剥掉 docstring，避免注释/文档里的示例造成假警报。"""
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return src
    lines = src.splitlines()
    drop = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc is None:
                continue
            b = node.body[0]
            for i in range(b.lineno - 1, b.end_lineno):
                drop.add(i)
    return "\n".join(ln for i, ln in enumerate(lines) if i not in drop)


def check_static_isolation_declared():
    """① 每个碰 NB 的守卫，必须隔离或显式声明读生产库。"""
    print()
    print("① 静态：碰 NB 的守卫必须隔离 or 显式声明")
    scripts = sorted(
        f for f in os.listdir(VERIFY_DIR)
        if f.endswith(".py") and f not in {
            "guard_sandbox.py", "verify_guard_db_isolation.py",
        }
    )
    touched = []
    for fn in scripts:
        src = open(os.path.join(VERIFY_DIR, fn), encoding="utf-8").read()
        code = _strips_docstring(src)
        if not any(h in code for h in WRITE_HINTS):
            continue
        touched.append(fn)
        isolated = "isolate_guard_db()" in code
        declared = "TOUCHES_PRODUCTION_DB = True" in code
        # ``DBStream(...)`` 显式传 filename= 的（如 dbstream_commit / bus_bulk
        # 自己指到 tempdir）本来就没碰生产库，别误报。
        n_calls = len(re.findall(r"DBStream\(", code))
        n_named = len(re.findall(r"DBStream\([^()]*filename=", code))
        dbstream_only = n_calls > 0 and n_calls == n_named and not (
            "NB(" in code or "VirtualPortfolio(" in code
        )
        ok = isolated or declared or fn in DECLARED_PRODUCTION_READERS or dbstream_only
        reason = (
            "已隔离" if isolated else
            "已声明读生产库" if declared else
            "DBStream 自带 filename，不碰生产库" if dbstream_only else
            "白名单（只读/空表）"
        )
        _check(f"{fn}", ok, reason if ok else "既没隔离也没声明 —— 会往生产库写")

    _check("扫描到碰 NB 的脚本数 > 0", len(touched) > 0, f"{len(touched)} 个")


def check_static_isolation_before_deva_import():
    """② 隔离调用必须早于任何 deva 导入 —— 晚了等于没隔离。

    ``global_namespace`` 会缓存 NB 实例；只要此前有一次 ``NB(...)``，
    环境变量就再也不生效了。
    """
    print()
    print("② 静态：隔离调用必须早于 deva 导入")
    for rel in TARGETS:
        path = os.path.join(ROOT, rel)
        src = open(path, encoding="utf-8").read()
        lines = src.splitlines()
        first_deva = next(
            (i for i, ln in enumerate(lines)
             if ln.lstrip().startswith(("from deva", "import deva"))
             or "from deva." in ln or "import deva." in ln),
            None,
        )
        isolate_line = next(
            (i for i, ln in enumerate(lines) if "isolate_guard_db()" in ln), None
        )
        ok = isolate_line is not None and (
            first_deva is None or isolate_line < first_deva
        )
        _check(
            f"{os.path.basename(rel)}",
            ok,
            f"隔离在第 {isolate_line + 1} 行"
            + (f"，首个 deva 导入在第 {first_deva + 1} 行" if first_deva else "")
            if ok else "没找到隔离调用，或它排在 deva 导入之后",
        )


# ────────────────────────────────────────────────────────────── 运行期
def _snapshot():
    from deva import NB
    accounts = dict(NB("naja_bandit_positions").get("accounts", {}) or {})
    blob = json.dumps(accounts, ensure_ascii=False, sort_keys=True, default=str)
    return accounts, hashlib.md5(blob.encode("utf-8")).hexdigest()


def _restore(accounts):
    from deva import NB
    db = NB("naja_bandit_positions")
    db["accounts"] = accounts


def check_runtime_production_db_untouched():
    """③ 真跑一遍做 T 守卫，生产库 accounts **账户集合**不许变。

    ❗2026-10-21 修：原来比对整个 accounts 的 md5。但 Naja 服务在跑的时候
    会自己刷新账户现金/市值，指纹在两次快照之间就漂了 —— 于是这条守卫
    在盘中随机报「生产库被污染」，而新增账户其实是空的（现场证据：
    ``指纹 ee6de231f613 → f3abbcde991b；新增账户 []``）。
    把服务自己的写入算成守卫污染，等于用假红掩盖真问题：真红的时候没人信。

    守卫真正要防的是「测试数据写进生产库」，那必然体现为**账户集合变了**
    （多出测试账户 / 少了真实账户）。所以判据改成账户 key 集合；
    内容指纹只做提示，不一致时明确说清是数值漂移而非污染。
    """
    print()
    print("③ 运行期：跑一遍做 T 守卫，生产库 accounts 账户集合不变")
    before_accounts, before_md5 = _snapshot()
    before_keys = sorted(before_accounts)
    print(f"      跑前指纹 {before_md5[:12]}  账户 {len(before_keys)} 个")

    for rel in TARGETS:
        mid_before, mid_md5 = _snapshot()
        mid_keys = sorted(mid_before)
        proc = subprocess.run(
            ["env", "-u", "PYTHONPATH", f"TMPDIR={os.environ.get('TMPDIR') or '/tmp'}",
             PY, rel],
            capture_output=True, text=True, cwd=ROOT, timeout=600,
        )
        tail = [l for l in proc.stdout.splitlines() if l.strip().startswith(("❌", "✅"))]
        print(f"      {os.path.basename(rel):34s} exit={proc.returncode}  {tail[-1][:40] if tail else ''}")

        # ★ 每个目标跑完立刻比对，而不是最后统一比：
        #   有的守卫结尾会 clear_history 把痕迹抹平，
        #   只在最后看一次的话，中间的污染就被它自己打扫干净了。
        mid_after, mid_after_md5 = _snapshot()
        if sorted(mid_after) != mid_keys:
            print(f"      ⚠️ 检测到生产库账户集合被写：{mid_keys} → {sorted(mid_after)}")
        elif mid_after_md5 != mid_md5:
            print(f"      · 数值有漂移（{mid_md5[:12]} → {mid_after_md5[:12]}），"
                  f"账户集合未变 —— 是服务/行情在写，不是守卫污染")

    after_accounts, after_md5 = _snapshot()
    after_keys = sorted(after_accounts)
    same = after_keys == before_keys
    if not same:
        # 当场还原：守卫漏隔离导致污染，不能就这么留下
        try:
            _restore(before_accounts)
        except Exception as e:  # pragma: no cover
            print(f"      ⚠️ 还原失败，需人工介入: {e}")
        new_keys = set(after_accounts) - set(before_accounts)
        gone_keys = set(before_accounts) - set(after_accounts)
        _check(
            "生产库 accounts 未被污染（已尝试还原）",
            False,
            f"账户集合 {before_keys} → {after_keys}；"
            f"新增 {sorted(new_keys)}，丢失 {sorted(gone_keys)}",
        )
    else:
        note = f"账户集合一致（{len(after_keys)} 个）"
        if after_md5 != before_md5:
            note += (f"；内容指纹 {before_md5[:12]} → {after_md5[:12]} 有漂移"
                     f"—— 服务在刷新现金/市值，不是守卫污染")
        _check("生产库 accounts 未被污染", True, note)


def _injections() -> int:
    """负向注入：判据放宽到「账户集合」之后，真污染必须还红。

    ❗只放宽了「数值漂移不算污染」，没放宽「多出账户不算污染」。
    这条注入就是把后者破坏一次，确认守卫没变成摆设。
    """
    print("=" * 68)
    print("负向注入 —— 坏版本必须被抓到")
    print("=" * 68)

    from unittest import mock

    orig_snapshot = globals()["_snapshot"]
    calls = {"n": 0}

    def _polluted_snapshot():
        """第 2 次起多出一个测试账户 —— 典型的生产库污染。"""
        calls["n"] += 1
        acc, md5 = orig_snapshot()
        if calls["n"] >= 2:
            acc = dict(acc)
            acc["guard_polluted_account"] = {"cash": 1}
        return acc, md5

    results = []
    _failures.clear()
    globals()["_snapshot"] = _polluted_snapshot
    try:
        # 不真跑 T 守卫（慢），也不真还原（避免写生产库）
        with mock.patch.object(subprocess, "run",
                               return_value=types.SimpleNamespace(returncode=0, stdout="✅ ok")), \
             mock.patch.object(sys.modules[__name__], "_restore", lambda accounts: None):
            check_runtime_production_db_untouched()
    finally:
        globals()["_snapshot"] = orig_snapshot

    caught = any("未被污染" in name for name, _ in _failures)
    results.append(("生产库多出测试账户（真污染）", caught))
    for label, ok in results:
        print(f"  {'✅ 抓到' if ok else '❌ 漏了'}  {label}")
    bad = sum(1 for _, ok in results if not ok)
    print(f"\n注入检出 {len(results) - bad}/{len(results)}")
    return 1 if bad else 0


def main():
    if "--exercise-injections" in sys.argv:
        return _injections()

    print("=" * 68)
    print("守卫 hygiene —— 测试数据不许写进 ~/.deva/nb.sqlite")
    print("=" * 68)

    check_static_isolation_declared()
    check_static_isolation_before_deva_import()
    check_runtime_production_db_untouched()

    print()
    print("=" * 68)
    if _failures:
        print(f"❌ {len(_failures)} 项违约")
        for name, detail in _failures:
            print(f"   · {name}: {detail}")
        return 1
    print("✅ ALL PASS —— 守卫与生产库已隔离")
    return 0


if __name__ == "__main__":
    sys.exit(main())
