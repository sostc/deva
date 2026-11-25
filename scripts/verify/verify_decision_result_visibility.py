#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""守卫：决策「批准 / 否决」与行动门判定必须**分流可见**，不许被高频否决淹没。

背景（2026-11-25）
------------------
用户反馈觉醒页「全是被拒绝的，看不出哪些通过，拒绝太多把通过的淹没了」。
核查生产库：

* ``naja_manas_gate_audit``：19 行折叠记录 / 300 次判定，**通过 0**；
* ``naja_decision_journal``：全量 2000 条，**approved=True 0 条**。

也就是说「通过被淹没」在真数据里不成立（真的一条都没有）。但界面呈现有
两个**真问题**，本守卫把它们钉死：

① **决策面板只显示最近 N 条**：整段全否定时，稀少（哪怕未来出现）的批准
   记录会被完全挤出视野，用户无从判断「有没有通过过」。现在
   ``get_decision_plan_summary`` 额外从完整历史窗口分流 ``recent_approved``
   与 ``rejected`` 计数，UI 把批准置顶并显示「批准 X / 否决 Y」平衡条。

② **门审计按含漂移数值的 reason 折叠**：「逆风(regime-0.47)」与
   「逆风(regime-0.50)」是同一类拒绝，旧写法拆成 19 行占满 ``recent(20)``。
   现在 ``_fold_key`` 剥掉数值按语义骨架折叠，数值仍在独立字段里逐条保留。

验收标准（负向注入是唯一验收）
------------------------------
正向：合成「9 否决 + 1 批准」的摘要渲染后必须同时出现批准记录与平衡计数；
门审计两条仅数值不同的同类拒绝必须折叠成 1 行且计数 2。
负向：注入「删掉批准置顶块」「折叠键不归一化」「平衡条写死 0」三类 bug，
守卫必须各自抓到（失败原因不同 → 证明真的在守这几处）。

用法
----
    python scripts/verify/verify_decision_result_visibility.py
    python scripts/verify/verify_decision_result_visibility.py --strict
    python scripts/verify/verify_decision_result_visibility.py --exercise-injections
"""

from __future__ import annotations

import argparse
import importlib
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERIFY_DIR = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, ROOT)
if str(VERIFY_DIR) not in sys.path:
    sys.path.insert(0, str(VERIFY_DIR))

# 本守卫的 NB 操作都在临时库；按仓规先隔离，绝不能碰生产库。
from guard_sandbox import isolate_guard_db  # noqa: E402
isolate_guard_db()

COMPONENTS_PY = ROOT / "deva/naja/attention/ui/components.py"
AUDIT_PY = ROOT / "deva/naja/attention/kernel/manas_gate_audit.py"
SUMMARY_PY = ROOT / "deva/naja/attention/orchestration/trading_center.py"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def check_summary_exposes_split() -> list:
    """静态：决策汇总必须暴露批准分流 + 否决计数。"""
    failures = []
    src = _source(SUMMARY_PY)
    # ❗判据钉「真的被赋值」，不是「字符串出现过」——docstring / 注释里
    # 也写着 recent_approved，只判 `in src` 会让「删掉分流那行」注入假绿。
    if '"recent_approved": approved_items' not in src:
        failures.append("get_decision_plan_summary 没有给 recent_approved 赋值 —— 批准记录仍会被否决挤出")
    if '"rejected"' not in src:
        failures.append("stats 里没有 rejected —— UI 无法显示「批准/否决」平衡")
    # 分流必须来自完整历史窗口，不能只从 limit 条 recent 里筛（那样全否时依旧 0）
    seg = src[src.find("def get_decision_plan_summary"):]
    seg = seg[:seg.find("\n    @") if "\n    @" in seg else len(seg)]
    if "2000" not in seg or "approved_items" not in seg:
        failures.append("批准分流没走完整历史窗口（recent 只有 limit 条，整段否决时筛不出通过）")
    return failures


def check_ui_renders_approved() -> list:
    """行为：喂「9 否决 + 1 批准」的摘要，渲染必须同时显示批准与平衡计数。"""
    failures = []
    try:
        mod = importlib.reload(importlib.import_module("deva.naja.attention.ui.components"))
    except Exception as e:  # noqa: BLE001
        return [f"无法导入 components：{type(e).__name__}: {e}"]

    summary = {
        "available": True,
        "latest": {"symbol": "00700", "side": "hold", "action_type": "hold",
                   "size_hint": 0, "confidence": 0.2, "approved": False, "gate_reason": "env"},
        "recent": [
            {"symbol": "00700", "side": "hold", "action_type": "hold",
             "size_hint": 0, "confidence": 0.2, "approved": False}
            for _ in range(9)
        ],
        "recent_approved": [
            {"symbol": "NVDA", "side": "buy", "action_type": "act_minimally",
             "size_hint": 0.1, "confidence": 0.8, "approved": True}
        ],
        "stats": {"total": 2000, "shown": 10, "approved": 7, "rejected": 1993,
                  "actionable": 7, "persisted": True},
    }
    try:
        html = mod.render_decision_plan_panel(summary)
    except Exception as e:  # noqa: BLE001
        return [f"渲染决策面板抛异常：{type(e).__name__}: {e}"]

    if "批准 7" not in html:
        failures.append("UI 没显示批准计数「批准 7」——平衡视图缺失")
    if "否决 1993" not in html:
        failures.append("UI 没显示否决计数「否决 1993」——平衡视图缺失")
    if "NVDA" not in html or "批准记录" not in html:
        failures.append("UI 没把批准记录置顶显示 —— 通过又被否决淹没了")
    return failures


def check_gate_audit_fold_normalized() -> list:
    """行为：仅数值漂移的同类拒绝必须折叠成 1 行，且数值刷新到最新。"""
    failures = []
    try:
        mod = importlib.reload(
            importlib.import_module("deva.naja.attention.kernel.manas_gate_audit")
        )
    except Exception as e:  # noqa: BLE001
        return [f"无法导入 manas_gate_audit：{type(e).__name__}: {e}"]

    log = mod.GateAuditLog(table="naja_verify_visibility_tmp", persist_every=10 ** 9)

    def _mk(reason: str, regime: float):
        return types.SimpleNamespace(
            action_gate_reason=reason, action_type="hold", should_act=False,
            regime_score=regime, timing_score=0.46, gate_factors={},
            intent_confidence=0, intent_relaxation=0, effective_threshold=0.5,
            manas_score=0.2, alpha=0.3, risk_temperature=1.63,
            confidence_score=0.31, bias_state=None,
        )

    log.record(_mk("环境阻力 | 主因=地势 | 逆风(regime-0.47) | 折扣0.78", 0.47))
    log.record(_mk("环境阻力 | 主因=地势 | 逆风(regime-0.50) | 折扣0.79", 0.50))
    if len(log) != 1:
        failures.append(f"同类拒绝应折叠成 1 行，实得 {len(log)} 行（数值漂移没被归一化）")
        return failures
    entry = log.recent(1)[0]
    if entry.get("occurrences") != 2:
        failures.append(f"折叠计数应为 2，实得 {entry.get('occurrences')}")
    if abs(float(entry.get("regime_score") or 0.0) - 0.50) > 1e-9:
        failures.append(f"折叠后 regime_score 应刷新为最新 0.50，实得 {entry.get('regime_score')}")
    stats = log.stats()
    if stats.get("held") != 2 or stats.get("acted") != 0:
        failures.append(f"stats 通过/拒绝分流错误：{stats.get('acted')}/{stats.get('held')}")
    if stats.get("act_ratio") != 0.0:
        failures.append(f"act_ratio 应为 0，实得 {stats.get('act_ratio')}")
    return failures


def check_recent_status_filter() -> list:
    """行为：recent 必须能按 should_act 分流，否则 UI 拿不到通过列表。"""
    failures = []
    mod = importlib.import_module("deva.naja.attention.kernel.manas_gate_audit")
    log = mod.GateAuditLog(table="naja_verify_filter_tmp", persist_every=10 ** 9)

    def _mk(should_act: bool, reason: str):
        return types.SimpleNamespace(
            action_gate_reason=reason,
            action_type="act_minimally" if should_act else "hold",
            should_act=should_act, regime_score=0.4, timing_score=0.5,
            gate_factors={}, intent_confidence=0, intent_relaxation=0,
            effective_threshold=0.5, manas_score=0.6, alpha=0.5,
            risk_temperature=1.0, confidence_score=0.6, bias_state=None,
        )

    log.record(_mk(False, "拒绝A"))
    log.record(_mk(True, "通过A"))
    log.record(_mk(False, "拒绝B"))
    if len(log.recent(10, should_act=True)) != 1:
        failures.append("recent(should_act=True) 没筛出唯一的通过记录")
    if len(log.recent(10, should_act=False)) != 2:
        failures.append("recent(should_act=False) 没筛出 2 条拒绝记录")
    if len(log.recent(10)) != 3:
        failures.append("recent() 默认应返回全部 3 条")
    return failures


def _all_checks() -> list:
    return (check_summary_exposes_split()
            + check_ui_renders_approved()
            + check_gate_audit_fold_normalized()
            + check_recent_status_filter())


# ── 负向注入：钉在「真的被执行」的分支上 ───────────────────────────────
INJECTIONS = [
    {
        "name": "UI 删掉批准置顶块（通过又被否决淹没）",
        "file": COMPONENTS_PY,
        "old": "        {approved_block}\n",
        "new": "",
    },
    {
        "name": "UI 平衡条写死计数为 0（显示谎报）",
        "file": COMPONENTS_PY,
        "old": 'f\'<span style="font-size:11px;font-weight:600;color:#16a34a;">✅ 批准 {approved_n}</span>\'\n',
        "new": "'<span>✅ 批准 0</span>'\n",
    },
    {
        "name": "折叠键不归一化（regime 数值漂移又拆成多行）",
        "file": AUDIT_PY,
        "old": "        return _REASON_DRIFT_RE.sub(\"#\", str(reason or \"\"))",
        "new": "        return str(reason or \"\")",
    },
    {
        "name": "决策汇总删掉批准分流（recent 全否时通过彻底消失）",
        "file": SUMMARY_PY,
        "old": '            "recent_approved": approved_items[:10],\n',
        "new": "",
    },
]


def _reload():
    for name in ("deva.naja.attention.ui.components",
                 "deva.naja.attention.kernel.manas_gate_audit"):
        try:
            importlib.reload(importlib.import_module(name))
        except Exception:  # noqa: BLE001
            pass


def run_injections() -> int:
    caught = 0
    reasons = []
    for inj in INJECTIONS:
        path: Path = inj["file"]
        original = _source(path)
        if inj["old"] not in original:
            print(f"❌ 注入锚点未命中（守卫腐烂）：{inj['name']}")
            continue
        if original.count(inj["old"]) != 1:
            print(f"❌ 锚点出现 {original.count(inj['old'])} 次（期望 1）：{inj['name']}")
            continue
        print(f"· 注入：{inj['name']}")
        path.write_text(original.replace(inj["old"], inj["new"]), encoding="utf-8")
        try:
            _reload()
            found = _all_checks()
        except Exception as e:  # noqa: BLE001
            found = [f"守卫抛异常: {type(e).__name__}: {e}"]
        finally:
            path.write_text(original, encoding="utf-8")
            _reload()
        if found:
            caught += 1
            reasons.append(found[0][:80])
            print(f"  ✅ 被捕获（{len(found)} 项）：{found[0][:100]}")
        else:
            print("  ❌ 没抓到 —— 这条是摆设")
    print(f"\n负向注入：{caught}/{len(INJECTIONS)} 被捕获")
    if reasons and len(set(reasons)) != len(reasons):
        print("  ⚠️ 失败原因有重复，可能不是各自独立的守点")
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
        print("❌ 决策结果可见性守卫失败：")
        for f in failures:
            print(f"   - {f}")
        return 1
    print("✅ 决策结果可见性守卫全绿（批准置顶 / 平衡计数 / 折叠归一化 / 状态筛选）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
