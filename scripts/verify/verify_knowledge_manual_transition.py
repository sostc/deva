#!/usr/bin/env python3
"""守卫知识层的「手动强制通过」—— 它必须真的能越过自动门槛，而自动路径必须仍然被拦。

================================================================================
它解决什么问题
================================================================================

学习层 UI（``/learning/list``、``/learning/detail``）对 ``observing`` / ``validating``
的条目渲染一个「✓ 强制通过」按钮，点下去打 ``POST /api/knowledge/action`` →
``learning_ui.handle_action('force_qualify', ...)`` → ``state_manager.transition(..., is_manual=True)``。

但 ``can_transition_to()`` 原来**完全不看 is_manual**，照旧套用自动门槛：

    evidence_count >= MIN_EVIDENCE_FOR_QUALIFIED(3)
    adjusted_confidence >= MIN_CONFIDENCE_THRESHOLD(0.5)

于是按钮在**最需要人工兜底**的条目上（证据不足）必然失败，返回笼统的「操作失败」。
真实踩过（2026-10-14）：

    [StateManager] 状态转换失败 ai_9e2ece3d: observing→qualified, 原因: 需要至少 3 个证据（当前 2）

这就是「UI 声称 manual、实现走 auto gate」的静默失效：日志只留一行 warning，
前端只显示「操作失败」，用户不知道撞的是哪条约束 —— 而按钮名字写着「强制」。

================================================================================
两条方向相反的 invariant（都要守）
================================================================================

  A) **人工可以越过** —— ``is_manual=True`` 时跳过证据数/置信度门槛，转换成功，
     并留下审计痕迹（manual_override / transition_type=manual / reason 里记明跳过了什么）
  B) **自动不能越过** —— ``is_manual=False`` 时门槛**仍然**拦得住；否则整治"手动被拦"的
     时候顺手把门槛整体删掉，等于用另一个 bug 换这个 bug

A 和 B 必须同时成立。只查 A 的守卫，在「门槛被整个删掉」时照样全绿 —— 那是最糟的假绿。

结构性约束（不能被人为越过）另有三条，也要钉住：
  * EXPIRED 只能重置到观察期，不能直接强制通过
  * 已是目标状态 → 转换失败
  * 目标状态白名单（只能从 OBSERVING / VALIDATING 升 QUALIFIED）

================================================================================
五段检查
================================================================================

  ① 人工越过门槛 —— observing + 证据 1 + 置信度 0.2 经 handle_action 强制通过成功
  ② 自动仍被拦住 —— 同样的数据走 is_manual=False，必须失败且状态不变
  ③ 结构约束     —— EXPIRED / 已是目标状态 / 白名单外，人工也不能越
  ④ 审计留痕     —— manual_override、transition_type=manual、reason 记明跳过口径
  ⑤ 失败原因可读 —— 失败时 message 必须带具体原因，不能再是笼统「操作失败」

数据全部落在**临时目录**（子类改掉 BASE_DIR），绝不碰生产 causality_knowledge.json。

================================================================================
用法
================================================================================

    python3 -m scripts.verify.verify_knowledge_manual_transition            # 报告模式
    python3 -m scripts.verify.verify_knowledge_manual_transition --strict   # 违约退出码 1
"""

import argparse
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "scripts", "verify"))

from guard_sandbox import isolate_guard_db  # noqa: E402

isolate_guard_db()  # 必须在任何 deva 导入之前

from deva.naja.knowledge.knowledge_store import (  # noqa: E402
    KnowledgeEntry, KnowledgeState, KnowledgeStore,
)
from deva.naja.knowledge.state_manager import KnowledgeStateManager  # noqa: E402
from deva.naja.knowledge.learning_ui import LearningUI  # noqa: E402


class _TmpStore(KnowledgeStore):
    """把落盘目录换到临时目录，避免守卫写脏生产知识库。"""

    def __init__(self, base: str):
        self.BASE_DIR = Path(base)
        self.KNOWLEDGE_FILE = self.BASE_DIR / "causality_knowledge.json"
        self.NARRATIVES_FILE = self.BASE_DIR / "narratives.json"
        self.ARTICLES_FILE = self.BASE_DIR / "learned_articles.json"
        self.DAILY_REPORTS_FILE = self.BASE_DIR / "daily_reports.json"
        self.STATS_FILE = self.BASE_DIR / "knowledge_stats.json"
        super().__init__()


class _FakeCognition:
    """替身：真实 inject_causality 会写生产 injected_knowledge.json。"""

    def __init__(self):
        self.calls = []

    def inject_causality(self, entry_id):
        self.calls.append(entry_id)
        return True


def _iso(days_ago=0):
    return (datetime.now() - timedelta(days=days_ago)).isoformat()


def make_entry(entry_id, status, evidence=1, confidence=0.2, days_ago=0):
    return KnowledgeEntry(
        id=entry_id,
        # ⚠️ cause 必须在用例内唯一：KnowledgeStore.add() 会按 cause 去重，
        # 撞了 cause 就走 update(existing.id, ...) 把上一条**顶掉**（连 id 一起改写），
        # 于是后面 store.get() 拿不到先加的那条。守卫自己踩过一次。
        cause=f"守卫用例-{entry_id}",
        effect="测试用结果",
        base_confidence=confidence,
        source="guard",
        original_title="guard 构造的条目",
        extracted_at=_iso(days_ago),
        category="test",
        status=status,
        adjusted_confidence=confidence,
        evidence_count=evidence,
        quality_score=0.5,
    )


def build():
    tmp = tempfile.mkdtemp(prefix="naja_know_guard_")
    store = _TmpStore(tmp)
    sm = KnowledgeStateManager(store=store)
    cog = _FakeCognition()
    ui = LearningUI(store=store, state_manager=sm, cognition_interface=cog)
    return tmp, store, sm, ui, cog


def main():
    parser = argparse.ArgumentParser(description="校验知识层手动强制通过")
    parser.add_argument("--strict", action="store_true", help="存在违约时以退出码 1 结束")
    args = parser.parse_args()

    violations = []
    tmp, store, sm, ui, cog = build()

    # ── ① 人工越过门槛 ────────────────────────────────────────────────
    print("=" * 78)
    print("① 人工越过门槛 —— 证据 1/3、置信度 0.20/0.50 的 observing 条目")
    print("=" * 78)

    weak = make_entry("guard_weak", KnowledgeState.OBSERVING.value, evidence=1, confidence=0.2)
    store.add(weak)

    can, why = sm.can_transition_to(weak, KnowledgeState.QUALIFIED, is_manual=True)
    print(f"  can_transition_to(is_manual=True) : {can}  ({why})")
    if not can:
        violations.append(f"人工强制通过仍被门槛拦住: {why}")

    res = ui.handle_action("force_qualify", "guard_weak")
    after = store.get("guard_weak")
    print(f"  handle_action 返回               : {res}")
    print(f"  状态                             : {weak.status} → {after.status}")
    if not res.get("success"):
        violations.append(f"handle_action('force_qualify') 失败: {res.get('message')}")
    if after.status != KnowledgeState.QUALIFIED.value:
        violations.append(f"强制通过后状态应为 qualified，实得 {after.status!r}")
    if "guard_weak" not in cog.calls:
        violations.append("强制通过后没有调用 cognition_interface.inject_causality（认知层拿不到这条知识）")

    # ── ② 自动仍被拦住（反方向 invariant） ────────────────────────────
    print()
    print("=" * 78)
    print("② 自动仍被拦住 —— 同样的数据走 is_manual=False")
    print("=" * 78)

    # 两条用例各自**只差一个维度**，任一门槛被删/被放宽都会露馅：
    #   只差证据维度   → 证据门槛没了就会误放行
    #   只差置信度维度 → 置信度门槛没了就会误放行
    # 反例：只用一个"两维都不足"的用例是不够的 —— 删掉任一门槛时另一条仍会拦住，
    # 守卫照样全绿（本守卫第一版就栽在这，负向验证时露的原形）。
    auto_cases = [
        ("guard_auto_no_evidence", dict(evidence=1, confidence=0.9), "只差证据维度"),
        ("guard_auto_no_conf", dict(evidence=5, confidence=0.1), "只差置信度维度"),
    ]
    for cid, kw, label in auto_cases:
        store.add(make_entry(cid, KnowledgeState.OBSERVING.value, **kw))
        ok = sm.transition(cid, KnowledgeState.QUALIFIED, reason="自动尝试升级")
        st = store.get(cid).status
        print(f"  {label:14s} 自动路径返回 : {ok}   （必须 False）  状态 {st!r}")
        if ok:
            violations.append(
                f"{label} 的条目被自动路径放行了（{cid}）—— 对应门槛被删或被放宽，"
                f"这是用另一个 bug 换这个 bug"
            )
        if st != KnowledgeState.OBSERVING.value:
            violations.append(f"{cid} 自动路径失败后状态被改成了 {st!r}（应当保持 observing）")

    # 反方向再补一刀：证据达标时自动路径**必须**放行（否则不是"门槛在拦"，是"链路断了"）
    auto_strong = make_entry(
        "guard_auto_strong", KnowledgeState.VALIDATING.value,
        evidence=3, confidence=0.6, days_ago=10,
    )
    store.add(auto_strong)
    ok_strong = sm.transition("guard_auto_strong", KnowledgeState.QUALIFIED, reason="自动满足条件")
    print(f"  证据3/置信度0.60 的自动路径返回  : {ok_strong}   （必须 True）")
    if not ok_strong:
        violations.append("证据与置信度都达标的条目，自动路径也升不上去 —— 门槛被改成了恒假")

    # ── ③ 结构性约束 ──────────────────────────────────────────────────
    print()
    print("=" * 78)
    print("③ 结构约束 —— 人工也不能越的三种情况")
    print("=" * 78)

    expired = make_entry("guard_expired", KnowledgeState.EXPIRED.value, evidence=0, confidence=0.0)
    store.add(expired)
    r = ui.handle_action("force_qualify", "guard_expired")
    print(f"  EXPIRED 强制通过    : {r}")
    if r.get("success"):
        violations.append("已过期条目被直接强制通过（应当先重置到观察期）")

    done = make_entry("guard_done", KnowledgeState.QUALIFIED.value, evidence=9, confidence=0.9)
    store.add(done)
    r2 = ui.handle_action("force_qualify", "guard_done")
    print(f"  已是 qualified 再点: {r2}")
    if r2.get("success"):
        violations.append("已经是目标状态却报成功")
    if "已经是目标状态" not in r2.get("message", ""):
        violations.append(f"已是目标状态的失败原因没透出: {r2.get('message')}")

    reset_ok = ui.handle_action("reset_to_observation", "guard_done")
    expired_after_reset = store.get("guard_done")
    print(f"  qualified 重置观察期: {reset_ok} → {expired_after_reset.status!r}")
    if not reset_ok.get("success") or expired_after_reset.status != KnowledgeState.OBSERVING.value:
        violations.append("qualified → 重置到观察期 这条既有路径被改坏了")

    # ── ④ 审计留痕 ────────────────────────────────────────────────────
    print()
    print("=" * 78)
    print("④ 审计留痕 —— 跳过了什么必须查得到")
    print("=" * 78)

    weak_now = store.get("guard_weak")
    logs = sm.get_transition_history("guard_weak")
    last = logs[-1] if logs else {}
    print(f"  manual_override  : {weak_now.manual_override}")
    print(f"  transition_type  : {last.get('transition_type')!r}")
    print(f"  reason           : {last.get('reason')!r}")
    if not weak_now.manual_override:
        violations.append("强制通过后 manual_override 没有置位（列表页的「手动」标签不会显示）")
    if last.get("transition_type") != "manual":
        violations.append(f"transition_type 应为 manual，实得 {last.get('transition_type')!r}")
    if "跳过自动门槛" not in (last.get("reason") or ""):
        violations.append(f"转换日志没记明跳过了哪些门槛: {last.get('reason')!r}")

    # ── ⑤ 失败原因可读 ────────────────────────────────────────────────
    print()
    print("=" * 78)
    print("⑤ 失败原因可读 —— 不能再是笼统的「操作失败」")
    print("=" * 78)

    for label, payload in (("过期条目", r), ("已是目标状态", r2)):
        msg = payload.get("message", "")
        print(f"  {label:10s}: {msg}")
        if msg.strip() == "操作失败":
            violations.append(f"{label} 的失败原因仍是笼统的「操作失败」，用户无从判断")

    print()
    print("=" * 78)
    if violations:
        print(f"发现 {len(violations)} 处违约：")
        for i, v in enumerate(violations, 1):
            print(f"  {i}. {v}")
    else:
        print("全部通过：人工可越过门槛、自动仍被拦住、结构约束与审计痕迹都在")
    print(f"（全部数据落在临时目录 {tmp}）")
    print("=" * 78)

    if violations and args.strict:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
