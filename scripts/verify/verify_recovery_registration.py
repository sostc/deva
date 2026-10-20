"""守卫：可恢复单元必须真的被登记，``restore_all()`` 不许恒定返回「未注册」。

背景（2026-10-20 实测，不是推测）：

``RecoveryManager`` 是数据源/字典/策略/任务的统一恢复入口，
``AppContainer._start_schedulers()`` 里的唤醒流程会调
``recovery_manager.restore_all()``。但**全仓没有任何一处调用
``recovery_manager.register()``**。

于是每个启动周期日志都长这样：

    恢复={'datasource': {'success': False, 'error': 'Manager not registered'},
          'strategy':   {'success': False, 'error': 'Manager not registered'},
          'task':       {'success': False, 'error': 'Manager not registered'}}

后果不是报错，而是**静默**：数据源与策略在每次重启后都不会恢复运行，
首页「数据源 0/5」「策略 0/4」两个红色判读长期挂着，看着像渲染错误，
实际是真没跑。任务恰好还有一条独立恢复路径（``restore_runtime_state()``）
兜住，所以它看起来是好的 —— 这也让人更难发现问题。

这类 bug 的特征是「调用链完整、返回值合法、日志无害」，只有把
**返回值本身**当断言对象才抓得到。因此本守卫除了静态查接线，还要真跑一次
``restore_all()``，看它是不是给了「Manager not registered」。

另一个一并守住的是方向相反的坑：``restore_all()`` 每次都会先
``load_from_db()``，而该方法会 ``_items.clear()`` 重建条目 —— 对已经在跑的
TaskEntry 来说，旧线程变孤儿、新条目 ``is_running=False`` 又被启动一次，
同一个定时任务跑两份。所以 order 里**不许**出现 ``task``。
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTAINER = ROOT / "deva/naja/application/container.py"
WAKE = ROOT / "deva/naja/application/wake_orchestrator.py"


# ── 静态：接线 ───────────────────────────────────────────────────────────────

def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _find_func(tree: ast.Module, name: str):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def _calls(node: ast.AST) -> list:
    """收集一个函数体里出现的所有被调用名字的最后一段。"""
    names = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            fn = sub.func
            if isinstance(fn, ast.Attribute):
                names.append(fn.attr)
            elif isinstance(fn, ast.Name):
                names.append(fn.id)
    return names


def _check_container_wiring(fails: list) -> None:
    tree = _parse(CONTAINER)

    loader = _find_func(tree, "_load_persistent_managers")
    if loader is None:
        fails.append("container.py 缺少 _load_persistent_managers")
    elif "_register_recovery_managers" not in _calls(loader):
        fails.append(
            "_load_persistent_managers 没有调用 _register_recovery_managers —— "
            "管理器初始完却不登记，restore_all() 会恒返回「Manager not registered」"
        )

    register = _find_func(tree, "_register_recovery_managers")
    if register is None:
        fails.append("container.py 缺少 _register_recovery_managers")
    else:
        if "register" not in _calls(register):
            fails.append("_register_recovery_managers 没有调用 register()")
        src = ast.get_source_segment(CONTAINER.read_text(encoding="utf-8"), register) or ""
        if "recovery_manager" not in src:
            fails.append("_register_recovery_managers 没有碰 recovery_manager")

    # 注册时机：必须在管理器初始化**之后**，不能拿未初始化的对象充数
    if loader is not None:
        src = ast.get_source_segment(CONTAINER.read_text(encoding="utf-8"), loader) or ""
        reg_at = src.find("_register_recovery_managers")
        pool_at = src.find("as_completed")
        if reg_at < 0:
            # 调用被删掉的情况已由上一条断言报出，这里不重复报
            pass
        elif pool_at < 0:
            fails.append("_load_persistent_managers 里找不到 as_completed，无法校验注册时机")
        elif reg_at < pool_at:
            fails.append(
                "注册发生在并行初始化完成之前 —— 会登记进未初始化/初始化失败的管理器"
            )


def _check_wake_order(fails: list) -> None:
    src = WAKE.read_text(encoding="utf-8")
    tree = _parse(WAKE)
    func = _find_func(tree, "_recover_components")
    if func is None:
        fails.append("wake_orchestrator.py 缺少 _recover_components")
        return

    body = ast.get_source_segment(src, func) or ""
    if "restore_all" not in body:
        fails.append("_recover_components 没有调用 restore_all()")
        return

    # order 里不许有 task：会 load_from_db() 重建条目 → 定时任务跑两份
    has_task = any(
        isinstance(node, ast.Constant) and node.value == "task"
        for node in ast.walk(func)
    )
    if has_task:
        fails.append(
            "_recover_components 的 order 里出现了 'task' —— restore_all() 会先 "
            "load_from_db() 清空并重建条目，已在跑的任务线程变孤儿、新条目再启动一次"
        )


# ── 动态：restore_all() 的返回值本身 ─────────────────────────────────────────

class _FakeManager:
    """最小可恢复管理器替身：只需 load_from_db + restore_running_states。"""

    def __init__(self, restored: int = 2):
        self.loaded = 0
        self.called = 0
        self.restored = restored

    def load_from_db(self):
        self.loaded += 1

    def restore_running_states(self):
        self.called += 1
        return {
            "success": True,
            "restored_count": self.restored,
            "failed_count": 0,
            "skipped_count": 0,
            "results": [],
        }


def _check_restore_all_actually_works(fails: list) -> None:
    from deva.naja.infra.runtime.recoverable import recovery_manager

    snapshot = dict(recovery_manager._managers)
    unit = "__guard_probe__"
    fake = _FakeManager()
    try:
        recovery_manager.register(unit, fake)
        result = recovery_manager.restore_all(order=[unit])
    finally:
        recovery_manager._managers.clear()
        recovery_manager._managers.update(snapshot)

    got = result.get(unit) or {}
    if got.get("error") == "Manager not registered":
        fails.append(
            "restore_all() 对已注册单元仍返回「Manager not registered」 —— 注册进去了但没生效"
        )
    elif not got.get("success"):
        fails.append(f"restore_all() 对已注册单元返回失败：{got}")
    elif got.get("restored_count") != 2 or fake.called != 1:
        fails.append(f"restore_all() 没真的调到 restore_running_states：{got}")

    # 反方向：未注册的单元必须报「未注册」，否则本守卫的判据本身失效
    try:
        unregistered = recovery_manager.restore_all(order=["__not_registered__"])
    finally:
        recovery_manager._managers.clear()
        recovery_manager._managers.update(snapshot)
    miss = unregistered.get("__not_registered__") or {}
    if miss.get("error") != "Manager not registered":
        fails.append(
            "未注册单元没有返回「Manager not registered」 —— "
            "守卫的判据与现实不符，等于不会报警"
        )


def _all_checks() -> list:
    fails: list = []
    _check_container_wiring(fails)
    _check_wake_order(fails)
    _check_restore_all_actually_works(fails)
    return fails


# ── 负向注入：证明守卫不是摆设 ───────────────────────────────────────────────

INJECTIONS = (
    {
        "name": "删掉 _register_recovery_managers 调用（本次事故原状）",
        "path": CONTAINER,
        "old": "        self._register_recovery_managers(managers)\n",
        "new": "",
    },
    {
        "name": "order 里塞回 'task'（任务会跑两份）",
        "path": WAKE,
        "old": 'order=["datasource", "dictionary", "strategy"]',
        "new": 'order=["datasource", "strategy", "task"]',
    },
)


def run_injections() -> int:
    caught = 0
    missed = []
    for inj in INJECTIONS:
        path: Path = inj["path"]
        original = path.read_text(encoding="utf-8")
        if inj["old"] not in original:
            print(f"  ⚠️ 锚点未命中，跳过：{inj['name']}")
            missed.append(inj["name"])
            continue
        try:
            path.write_text(original.replace(inj["old"], inj["new"], 1), encoding="utf-8")
            fails = _all_checks()
        finally:
            path.write_text(original, encoding="utf-8")

        if fails:
            caught += 1
            print(f"  ✅ 被捕获：{inj['name']}")
            for f in fails[:2]:
                print(f"       · {f[:110]}")
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
        print("❌ 可恢复单元登记守卫 失败：")
        for f in failures:
            print(f"   - {f}")
        return 1 if args.strict else 0

    print("✅ 可恢复单元登记守卫全绿"
          "（寄存器真的 register · 时机在初始化之后 · order 不含 task · restore_all 真能恢复）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
