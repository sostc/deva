#!/usr/bin/env python3
"""校验 HealthCheckManager 的注册链路是通的，健康检查中心面板不是死的。

================================================================================
它解决什么问题
================================================================================

`HealthCheckManager.register()` 曾经全仓只出现在**它自己的 docstring 里**
（health.py 155-157 行的用法示例），生产代码一个调用点都没有。于是 check_all()
恒返回空 dict，get_overall_status() 走 `if not reports` 分支，直接返回：

    HealthStatus.UNKNOWN / "No components registered"

对应 /health 页面上那个「🩺 健康检查中心」面板永远显示 ❓ UNKNOWN、总组件 0。
它不抛异常、不写日志 —— 面板在说"我没数据"，但没人听得见。

现在注册动作挂在 AppContainer.boot() 的 `_register_health_checks()` 上。本脚本
验证这条链路真的通了，而不是又变成一次性的。

================================================================================
三段检查
================================================================================

  ① 空管理器症状 —— 复刻修复前的表现（0 组件时必须报 UNKNOWN），
                   这样以后 panels 若再次显示 UNKNOWN，能立刻区分是
                   "真的没注册" 还是 "注册了但检查没跑起来"
  ② 注册链路     —— 调真实的 AppContainer._register_health_checks，
                   断言三个组件都进去了、check_all() 非空
  ③ 面板产出     —— 用 _render_health_check_panel 渲染一遍，断言 HTML 里
                   不再出现 "No components registered"，且列出了组件名

================================================================================
用法
================================================================================

    python3 -m scripts.verify.verify_health_check_registration            # 报告
    python3 -m scripts.verify.verify_health_check_registration --strict   # 违约退 1
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

EXPECTED_COMPONENTS = ("attention", "core", "tasks")


def _read_health_ui_source() -> str:
    """读取 health_ui.py 源码。

    面板是拼字符串的，读数是写死在 f-string 里的，只能靠静态比对来证明
    「读到的键」和「实际吐出来的键」是一套 —— 运行时看不出来，因为缺键时
    .get() 会静默补默认值。
    """
    from deva.naja.infra.observability import health_ui

    with open(health_ui.__file__, encoding="utf-8") as fh:
        return fh.read()


class _FakeScheduler:
    def __init__(self, running=True):
        self.running = running


class _ContainerProbe:
    """承载 AppContainer._register_health_checks 的最小宿主。

    该方法的检查项只依赖容器自身的三个字段，用一个轻量探针加载它，就能在不跑
    完整 boot() 的前提下验证「注册链路有没有接通」—— 这正是当初断掉的地方。
    """

    def __init__(self, scheduler_running=True):
        self._attention_os = object()
        self._trading_clock = object()
        self._task_manager = type("_TaskMgr", (), {"_scheduler": _FakeScheduler(scheduler_running)})()

    _register_health_checks = None  # 运行时由 AppContainer 绑定


def main():
    parser = argparse.ArgumentParser(description="校验健康检查注册链路")
    parser.add_argument("--strict", action="store_true", help="存在违约时以退出码 1 结束")
    args = parser.parse_args()

    from deva.naja.application.container import AppContainer
    from deva.naja.infra.observability.health import (
        HealthStatus,
        get_health_check_manager,
    )

    if _ContainerProbe._register_health_checks is None:
        _ContainerProbe._register_health_checks = AppContainer._register_health_checks

    violations = []
    manager = get_health_check_manager()

    # ── ① 空管理器的症状 ──────────────────────────────────────────────
    print("=" * 78)
    print("① 空管理器症状 —— 复刻修复前的表现")
    print("=" * 78)

    for name in EXPECTED_COMPONENTS:
        manager.unregister(name)
    empty_reports = manager.check_all()
    empty_overall = manager.get_overall_status()
    print(f"  组件数        : {len(empty_reports)}")
    print(f"  总体状态      : {empty_overall.status.value}")
    print(f"  消息          : {empty_overall.message}")

    if empty_reports or empty_overall.status is not HealthStatus.UNKNOWN:
        violations.append("清空后仍残留组件，check_all() 本应返回空、状态本应为 UNKNOWN")
    if "No components registered" not in empty_overall.message:
        violations.append(f"空管理器的兜底消息变了：{empty_overall.message!r}")

    # ── ② 注册链路 ────────────────────────────────────────────────────
    print()
    print("=" * 78)
    print("② 注册链路 —— 调真实的 _register_health_checks")
    print("=" * 78)

    probe = _ContainerProbe()
    probe._register_health_checks()

    reports = manager.check_all()
    overall = manager.get_overall_status()
    print(f"  已注册组件    : {sorted(reports)}")
    print(f"  总体状态      : {overall.status.value}")
    print(f"  消息          : {overall.message}")
    print(f"  details       : {overall.details}")
    for name, rep in sorted(reports.items()):
        print(f"    - {name:12s} {rep.status.value:10s} {rep.message[:60]}")

    missing = [c for c in EXPECTED_COMPONENTS if c not in reports]
    if missing:
        violations.append(f"这些组件没注册进去: {missing}")
    if not reports:
        violations.append("check_all() 返回空 —— 健康检查中心又会显示 UNKNOWN / 总组件 0")
    if overall.status is HealthStatus.UNKNOWN:
        violations.append(f"注册后总体状态仍是 UNKNOWN: {overall.message}")
    if overall.details.get("total", 0) != len(EXPECTED_COMPONENTS):
        violations.append(f"details['total'] = {overall.details.get('total')}，应为 {len(EXPECTED_COMPONENTS)}")

    # 幂等：重复注册不应叠加
    probe._register_health_checks()
    again = manager.check_all()
    print(f"  重复注册后    : {sorted(again)}（应与上一行一致）")
    if sorted(again) != sorted(reports):
        violations.append(f"重复注册出现了漂移: {sorted(again)} != {sorted(reports)}")

    # ── ③ 面板产出 ────────────────────────────────────────────────────
    print()
    print("=" * 78)
    print("③ 面板产出 —— 断言不再是那块死面板")
    print("=" * 78)

    from deva.naja.infra.observability.health_ui import _render_health_check_panel

    captured = []
    ctx = {"put_html": captured.append}
    _render_health_check_panel(ctx)
    html = "".join(captured)

    print(f"  HTML 长度     : {len(html)} 字符")
    print(f"  含 'No components registered' : {'No components registered' in html}")
    print(f"  含 '总组件'   : {'总组件' in html}")

    if "No components registered" in html:
        violations.append("面板仍在渲染 'No components registered' —— 注册没生效到 UI")
    for name in EXPECTED_COMPONENTS:
        if name not in html:
            violations.append(f"面板里看不到组件 {name}")
    if not html.strip():
        violations.append("面板没产出任何 HTML")

    # ── ④ 摘要读数对齐 ────────────────────────────────────────────────
    # 面板里 `health.get('xxx', 0)` 读的键必须真的存在于 get_health_summary()
    # 的返回值里。缺键时 .get() 会静默补默认值，卡片显示 0 却毫无异常——
    # 曾经就有 write_queue_size / failed_writes 两个键从来不存在，
    # 「失败 0」看着像健康，实际是读数错位。
    print()
    print("=" * 78)
    print("④ 摘要读数对齐 —— 面板读的键必须真的存在")
    print("=" * 78)

    from deva.naja.strategy.result_store import get_result_store

    actual_keys = set(get_result_store().get_health_summary())
    read_keys = set(re.findall(r"health\.get\(\s*['\"]([a-z_]+)['\"]", _read_health_ui_source()))

    print(f"  摘要实际字段  : {sorted(actual_keys)}")
    print(f"  面板读取字段  : {sorted(read_keys)}")

    phantom = read_keys - actual_keys
    if phantom:
        violations.append(
            f"面板读了摘要里不存在的键 {sorted(phantom)}："
            f".get(k, 0) 会静默返回 0，卡片会把错位读数显示成健康"
        )

    # ── 收尾：各组件的报告不能是空壳 ──────────────────────────────────
    for name, rep in reports.items():
        if not rep.message:
            violations.append(f"{name} 的报告 message 为空，检查项可能被静默吞异常")

    print()
    print("=" * 78)
    if violations:
        print(f"发现 {len(violations)} 处违约：")
        for i, v in enumerate(violations, 1):
            print(f"  {i}. {v}")
    else:
        print("全部通过：健康检查注册链路是通的")
    print("=" * 78)

    if violations and args.strict:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
