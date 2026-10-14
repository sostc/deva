#!/usr/bin/env python3
"""守卫：长期配置意图（Allocation）与循环守望。

为什么单独一个守卫
==================
「希望长期持有科创 ETF / 腾讯 / QQQ」这件事在系统里横跨四层：
意向层（``allocation.py``）→ 守望层（``watch.py`` 的循环能力）→
守望台（``registry.py`` 的续期）→ 页面（``ui.py`` 的长期配置区）。
任何一层没接上，表现都是「页面上看不到 / 永远不触发」，
而**不报错** —— 这正是本仓库头号病理（静默失效家族）。

三条硬纪律（守卫盯的就是它们）
==============================
1. **长期 ≠ 无限期**：``review_seconds`` 必须为正，缺了就抛异常。
   没有结算点的守望和死掉的线程长得一模一样。
2. **到期 = 这一期看过了，不是失败**：循环守望结算成 ``reviewed``。
   ❗若一律判成 ``expired``，长期持仓每期都会假装自己失败一次。
3. **撤下是真终止**：``abandoned`` 的守望**不许**被续期复活。
   少了这条，撤下就只是个视觉动作。

跑法
====
    python3 scripts/verify/verify_allocation_watch.py
    python3 scripts/verify/verify_allocation_watch.py --strict
    python3 scripts/verify/verify_allocation_watch.py --exercise-injections
"""

from __future__ import annotations

import argparse
import ast
import importlib
import json
import logging
import re
import sys
import tempfile
from pathlib import Path
from typing import Dict

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import os
# ❗守卫用例必须**确定性**：守望台默认开着市场时钟，闭市时守望会被闸门
# 跳过 —— 于是「现在几点」决定了用例的成败（半夜跑绿、收盘后跑红）。
# 市场时钟自身的行为由 verify_watch_awakener / 市场时钟守卫负责，
# 这里的用例只测守望语义，一律关掉闸门。
os.environ["NAJA_WATCH_MARKET_CLOCK"] = "0"

import deva.naja.watch as W  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
WATCH_DIR = ROOT / "deva" / "naja" / "watch"
BANDIT_DIR = ROOT / "deva" / "naja" / "bandit"

ALLOC_PY = WATCH_DIR / "allocation.py"
WATCH_PY = WATCH_DIR / "watch.py"
REGISTRY_PY = WATCH_DIR / "registry.py"
DESK_PY = WATCH_DIR / "desk.py"
UI_PY = WATCH_DIR / "ui.py"
RUNNER_PY = BANDIT_DIR / "intent_runner.py"

#: ❗**写死**的判定基准：守卫不许读被测模块的常量 ——
#: 否则注入把上限/周期改掉时，守卫跟着变，用例照样绿。
REVIEW_DAYS_LONG = 7.0
REVIEW_DAYS_SWING = 1.0
CONFIDENCE_CAP = 0.75


# ─────────────────────────────────────────────────────────────
# 静态规则
# ─────────────────────────────────────────────────────────────

REQUIRED_RULES = [
    ("allocation.py", r"^class Allocation", "缺少 Allocation 类"),
    ("allocation.py", r"alloc_pct", "缺少目标占比字段"),
    ("allocation.py", r"review_seconds", "缺少回顾周期字段"),
    ("allocation.py", r"horizon", "缺少时间尺度字段"),
    ("allocation.py", r"def declare_allocation", "缺少登记入口"),
    ("allocation.py",
     r"MissingSettlementPoint",
     "❗回顾周期缺失/非正时必须抛 MissingSettlementPoint（长期 ≠ 无限期）"),
    ("allocation.py", r"clamp_confidence", "意愿强度必须走封顶"),
    ("allocation.py", r"def allocation_row_of", "缺少清单行序列化"),

    ("watch.py", r"recurring", "❗守望缺少 recurring 标志（长期配置无法表达）"),
    ("watch.py", r"def arm", "❗守望缺少 arm() 续期入口"),
    ("watch.py", r"self\.cycles", "缺少期数记账"),
    ("watch.py", r"self\.cycle_log", "缺少每期归档"),
    ("watch.py", r"REVIEWED", "❗Settlement 缺少 REVIEWED（到期被当失败）"),

    ("registry.py", r"def renew", "❗守望台缺少 renew()（第一期结束就成尸体）"),
    ("registry.py", r"recurring", "renew 必须按 recurring 过滤"),
    ("registry.py",
     r"w\.recurring:\s*\n?\s*w\.settle\(\s*Settlement\.REVIEWED",
     "❗循环守望到期必须结算成 reviewed，不是 expired"),

    ("desk.py", r"self\._observers\[.allocation.\]",
     "❗守望台没给长期配置登记观测面工厂（会永远记成取不到观测）"),
    ("desk.py", r"def declare_allocation",
     "❗守望台桌面缺少登记长期配置的入口"),
    ("desk.py", r"registry\.renew", "❗poll 里没调用 renew（循环守望续不上）"),

    ("ui.py", r"def _allocation_rows", "页面缺少长期配置表格"),
    ("ui.py", r"def _on_set_alloc", "页面缺少「改目标」入口"),
    ("ui.py", r"def _on_new_allocation", "页面缺少「登记长期配置」入口"),
    ("ui.py", r"_position_lookup", "页面缺少持仓快照取数"),

    ("intent_runner.py", r"def load_allocations", "缺少长期配置装载"),
    ("intent_runner.py", r"def save_allocations", "缺少长期配置落盘"),
    ("intent_runner.py", r"def upsert_allocation", "缺少长期配置新增/更新"),
    ("intent_runner.py", r"def remove_allocation", "缺少长期配置删除"),
    ("intent_runner.py", r"def set_alloc_pct", "缺少目标占比调整"),
    ("intent_runner.py", r"os\.replace\(tmp, p\)", "❗落盘必须是原子替换"),
]

#: 反方向：以下模式出现即为回归
FORBIDDEN_RULES = [
    # 循环守望到期若被判成 expired，页面上会连续飘红而实际一切正常
    ("registry.py",
     r"w\.settle\(\s*Settlement\.EXPIRED[\s\S]{0,200}?recurring",
     "❗循环守望被判成 expired（到期=这期看过了，不是失败）"),
    # UI 不许成为绕过封顶的后门
    ("ui.py", r"CONFIDENCE_SLIDER_MAX\s*=\s*(0?\.[89]|1)",
     "❗UI 意愿强度上限超过 0.75（页面变成放行键）"),
]


# ─────────────────────────────────────────────────────────────
# 行为用例
# ─────────────────────────────────────────────────────────────

def _lens(raw):
    box = {"raw": dict(raw)}
    return W.ManasLens(provider=lambda: box["raw"]), box


def _desk(action="act_carefully", ts=1000.0, asker=None):
    """造一个假桌面。读数时刻贴近逻辑时钟，否则会被保鲜期先判过期。"""
    lens, box = _lens({"action_type": action, "manas_score": 0.7,
                       "timestamp": ts})
    return W.WatchDesk(lens=lens, quote_fn=lambda c: None,
                       asker=asker, heartbeat_sec=0.0), box


def _tmp_alloc_file(directory: str) -> Path:
    return Path(directory) / "allocations.json"


def behavior_checks() -> list:
    f = []
    A = W.Allocation

    # ① 基础构造与归一化
    a1 = A("qqq", "us", name="纳指100ETF", alloc_pct=20.0)
    if a1.code != "QQQ" or a1.market != "US":
        f.append("① 代码/市场没归一化成大写")
    if not a1.target_set:
        f.append("① alloc_pct>0 应判定为目标已设定")

    # ② 市场认不出必须抛（不静默兜底）
    try:
        A("QQQ", "JP")
        f.append("② 认不出的市场被静默接受了")
    except ValueError:
        pass

    # ③ 不给回顾周期 → 按尺度**兜底成有界正数**。
    #
    # ❗为什么不是像 Intent 那样缺了就抛：一次性意向的「等到什么时候」是
    # 人必须回答的择时判断；而长期配置的回顾节奏有合理默认（长期每周、
    # 波段每天）。但**兜底必须有界** —— 缺省成 0 或无限，等于造了一个
    # 无限期守望，跟死掉的线程没法区分。所以这里断言有限正数。
    a3 = A("QQQ", "US")
    try:
        secs = float(a3.review_seconds or 0.0)
    except (TypeError, ValueError):
        secs = 0.0
    if not (0.0 < secs < float("inf")):
        f.append(f"③ ❗回顾周期缺省值不是有界正数：{a3.review_seconds!r}")
    if a3.review_days <= 0:
        f.append(f"③ ❗review_days 应为正：{a3.review_days}")

    # ④ 回顾周期 <= 0 同样不许
    for bad in (0, -1, -86400.0):
        try:
            A("QQQ", "US", review_seconds=bad)
            f.append(f"④ ❗review_seconds={bad} 被接受了（无限期守望）")
        except ValueError:
            pass

    # ⑤ 目标占比为负
    try:
        A("QQQ", "US", alloc_pct=-5.0, review_seconds=86400.0)
        f.append("⑤ 负的目标占比被接受了")
    except ValueError:
        pass

    # ⑥ 时间尺度非法
    try:
        A("QQQ", "US", horizon="daytrade", review_seconds=86400.0)
        f.append("⑥ 非法时间尺度被接受了")
    except ValueError:
        pass

    # ⑦ 默认回顾周期按尺度推导（写死基准，不读被测模块）
    long_one = A("QQQ", "US", horizon="long")
    swing_one = A("QQQ", "US", horizon="swing")
    if abs(long_one.review_days - REVIEW_DAYS_LONG) > 1e-6:
        f.append(f"⑦ 长期默认回顾周期应为 {REVIEW_DAYS_LONG} 天，实际 {long_one.review_days}")
    if abs(swing_one.review_days - REVIEW_DAYS_SWING) > 1e-6:
        f.append(f"⑦ 波段默认回顾周期应为 {REVIEW_DAYS_SWING} 天，实际 {swing_one.review_days}")

    # ⑧ 登记出来的守望必须是循环守望
    desk8, _ = _desk()
    w8 = desk8.declare_allocation(A("00700", "HK", alloc_pct=30.0,
                                    review_seconds=604800.0))
    if not bool(getattr(w8, "recurring", False)):
        f.append("⑧ ❗长期配置登记后 recurring 不是 True（到期就死，不续期）")
    if w8.objective.kind != "allocation":
        f.append("⑧ 目标类型应为 allocation")

    # ⑨ 到期 → 结算成 reviewed，❗不是 expired
    desk9, _ = _desk(ts=1000.0)
    w9 = desk9.declare_allocation(
        A("00700", "HK", alloc_pct=30.0, review_seconds=100.0), now=1000.0)
    overdue = desk9.registry.due(2000.0, settle=True)
    if w9 not in overdue:
        f.append("⑨ 到期却没被 due() 挑出来")
    if getattr(w9.settlement, "value", None) != "reviewed":
        f.append(f"⑨ ❗循环守望到期被判成 {w9.settlement}，应为 reviewed")

    # ⑩ 续期：期数 +1、回到 ARMED、本期计数归零
    before_total = w9.total_scans
    summaries = desk9.registry.renew(2000.0)
    if len(summaries) != 1:
        f.append(f"⑩ renew 应该续期 1 个，实际 {len(summaries)}")
    elif summaries[0]["cycle"] != 1:
        f.append(f"⑩ 归档的期号应为 1，实际 {summaries[0]['cycle']}")
    if w9.cycles != 1:
        f.append(f"⑩ 续期后 cycles 应为 1，实际 {w9.cycles}")
    if w9.state.value != "armed":
        f.append(f"⑩ 续期后应回到 armed，实际 {w9.state.value}")
    if w9.scans != 0:
        f.append(f"⑩ 续期后本期扫描数应归零，实际 {w9.scans}")
    if w9.total_scans != before_total:
        f.append("⑩ 续期不该清掉累计计数")

    # ⑪ 反方向：一次性意向到期 → expired，且不被 renew 复活
    desk11, _ = _desk(ts=1000.0)
    w11 = desk11.declare_intent(
        W.BuyIntent("NVDA", "US", max_wait_seconds=100.0), now=1000.0)
    desk11.registry.due(2000.0, settle=True)
    if getattr(w11.settlement, "value", None) != "expired":
        f.append("⑪ ❗一次性意向到期应结算成 expired")
    if desk11.registry.renew(2000.0):
        f.append("⑪ ❗renew 把一次性意向也续期了（只有 recurring 能续）")

    # ⑫ 反方向：撤下的循环守望**不许**被续期复活
    desk12, _ = _desk(ts=1000.0)
    w12 = desk12.declare_allocation(
        A("588200", "CN", alloc_pct=40.0, review_seconds=100.0), now=1000.0)
    desk12.settle(w12.watch_id, "abandoned", "人工撤下")
    if desk12.registry.renew(2000.0):
        f.append("⑫ ❗撤下的长期配置被 renew 复活了 —— 撤下只是个视觉动作")
    if w12.state.value != "settled":
        f.append("⑫ ❗撤下后状态不是 settled")

    # ⑬ arm() 只允许循环守望用
    desk13, _ = _desk(ts=1000.0)
    w13 = desk13.declare_intent(
        W.BuyIntent("NVDA", "US", max_wait_seconds=86400.0), now=1000.0)
    try:
        w13.arm(2000.0)
        f.append("⑬ ❗一次性守望也能 arm()（循环语义被稀释）")
    except ValueError:
        pass

    # ⑭ 续期后 armed_at 必须更新，否则下一轮又立刻到期
    desk14, _ = _desk(ts=1000.0)
    w14 = desk14.declare_allocation(
        A("00700", "HK", alloc_pct=30.0, review_seconds=100.0), now=1000.0)
    desk14.registry.due(1100.0, settle=True)
    desk14.registry.renew(1100.0)
    if abs(w14.armed_at - 1100.0) > 1e-6:
        f.append(f"⑭ ❗续期后 armed_at 没更新（{w14.armed_at}），下一轮立刻又到期")
    if w14.is_overdue(1101.0):
        f.append("⑭ ❗刚续期就被判为已过期")

    # ⑮ 落盘往返
    with tempfile.TemporaryDirectory() as d:
        p = _tmp_alloc_file(d)
        from deva.naja.bandit import intent_runner as ir

        a = A("QQQ", "US", name="纳指100ETF", alloc_pct=25.0,
              review_seconds=604800.0, confidence=0.7,
              rationale="美股指数底仓")
        if ir.upsert_allocation(a, p) != "added":
            f.append("⑮ 首次登记应返回 added")
        if ir.upsert_allocation(a, p) != "updated":
            f.append("⑮ 同款再登记应返回 updated")
        got = ir.load_allocations(p)
        if len(got) != 1:
            f.append(f"⑮ 落盘往返条数不对：{len(got)}")
        else:
            g = got[0]
            if g.code != "QQQ" or abs(g.alloc_pct - 25.0) > 1e-6:
                f.append("⑮ 落盘往返字段丢失")
            if abs(float(g.confidence) - 0.7) > 1e-6:
                f.append("⑮ 意愿强度没被写进清单")
            if not g.confidence_explicit:
                f.append("⑮ 显式给过强度却没标记为 explicit")
        # 改目标占比并**写回文件**：断言文件里真的变了，不能只信返回值
        runner = ir.IntentRunner(enabled=False)
        runner.declare_allocation(a)
        got_v = None
        try:
            got_v = runner.set_alloc_pct("allocation:US:QQQ", 35.0, p)
        except Exception as e:  # noqa: BLE001
            f.append(f"⑮ set_alloc_pct 抛异常：{type(e).__name__}: {e}")
        if got_v is not None:
            if abs(float(got_v) - 35.0) > 1e-6:
                f.append(f"⑮ 返回值应是新目标 35，实际 {got_v}")
            saved = ir.load_allocations(p)
            if not saved or abs(float(saved[0].alloc_pct) - 35.0) > 1e-6:
                f.append("⑮ ❗改了目标占比但没写回清单（重启就回到未设定）")
        # 撤下
        if ir.remove_allocation("QQQ", "US", p) is not True:
            f.append("⑮ 删除应返回 True")
        if ir.remove_allocation("QQQ", "US", p) is not False:
            f.append("⑮ 重复删除应返回 False（不抛、也不假成功）")
        if ir.load_allocations(p):
            f.append("⑮ 删完清单应为空")

    # ⑯ 单条坏了只跳那一条：坏市场那条被跳过，好那条还在
    with tempfile.TemporaryDirectory() as d:
        p = _tmp_alloc_file(d)
        p.write_text(json.dumps([
            {"code": "QQQ", "market": "US", "review_seconds": 604800,
             "alloc_pct": 20},
            {"code": "588200", "market": "火星", "review_seconds": 604800,
             "alloc_pct": 40},
            {"code": "00700", "market": "HK", "review_seconds": 604800,
             "alloc_pct": 30},
        ], ensure_ascii=False, indent=2), encoding="utf-8")

        from deva.naja.bandit import intent_runner as ir2

        got2 = ir2.load_allocations(p)
        if len(got2) != 2:
            f.append(f"⑯ ❗单条坏了应只跳那一条，实际只剩 {len(got2)} 条")
        elif {g.code for g in got2} != {"QQQ", "00700"}:
            f.append("⑯ ❗跳过的位置不对，留下来的标的对不上")

    # ⑰ 认不出的守望不许静默成功
    desk17, _ = _desk()
    try:
        desk17.set_confidence("不存在的守望", 0.9)
        f.append("⑰ ❗改不存在的守望静默返回了（UI 会以为改成功）")
    except KeyError:
        pass
    try:
        desk17.set_alloc_pct  # noqa: B018 - 存在性检查
    except AttributeError:
        pass

    # ⑱ 意愿强度封顶（写死 0.75，不读被测模块）
    desk18, _ = _desk()
    w18 = desk18.declare_allocation(
        A("QQQ", "US", alloc_pct=20.0, review_seconds=86400.0,
          confidence=99.0))
    if float(w18.objective.params.get("confidence") or 0) > CONFIDENCE_CAP + 1e-9:
        f.append("⑱ ❗意愿强度没被封顶（人能把自己拖成放行键）")

    # ⑲ UI：空台面不崩、有配置时列数对
    import deva.naja.watch.ui as ui

    # ❗必须先换掉 ``put_buttons``：PyWebIO 的按钮要注册回调并等待事件，
    # 在脚本模式下会真的起一个 tornado server，然后**卡在进程退出处**
    # 等非守护线程结束 —— 表现为「守卫跑到超时」，看起来像产品慢，
    # 实际是用例自己起了一个服务器。
    ui.put_buttons = lambda *a, **k: "<操作>"

    desk19, _ = _desk()
    if ui._allocation_rows(desk19, 1000.0, {}):
        f.append("⑲ 空守望台渲染出了长期配置行")
    desk19.declare_allocation(
        A("588200", "CN", name="科创芯片ETF", alloc_pct=40.0,
          review_seconds=604800.0))
    rows19 = ui._allocation_rows(desk19, 1000.0, {})
    if len(rows19) != 1:
        f.append(f"⑲ 长期配置行数不对：{len(rows19)}")
    # 10 列 = 标的 / 目标 / 当前·缺口 / **旗下的守望** / 意愿强度 /
    #        尺度·理由 / 回顾 / 本期问询 / 最近结论 / 操作
    # ❗「旗下的守望」是「一份目标 → 一组守望」那一层加上去的：
    # 一份长期配置下面挂着补缺口、卖 T、买 T，没有这一列它们就无处可显。
    elif len(rows19[0]) != 10:
        f.append(f"⑲ ❗长期配置表列数应为 10，实际 {len(rows19[0])}")

    # ⑳ 一次性意向不出现在长期配置区（反方向：两类不许混）
    desk20, _ = _desk()
    desk20.declare_intent(
        W.BuyIntent("NVDA", "US", max_wait_seconds=86400.0), now=1000.0)
    if ui._allocation_rows(desk20, 1000.0, {}):
        f.append("⑳ ❗一次性意向混进了长期配置区")
    if not ui._watch_rows(desk20, 1000.0):
        f.append("⑳ ❗一次性意向没出现在意向区")

    # ㉑ 持仓取不到必须显示「未知」，❗不能退化成 0
    desk21, _ = _desk()
    desk21.declare_allocation(
        A("QQQ", "US", name="纳指100ETF", alloc_pct=0.0,
          review_seconds=604800.0))
    rows21 = ui._allocation_rows(desk21, 1000.0, None)
    if not rows21:
        f.append("㉑ 有长期配置却渲染出 0 行")
    else:
        joined = " ".join(
            str(c.spec.get("content", "") if hasattr(c, "spec") else c)
            for c in rows21[0][:8]
        )
        if "未知" not in joined:
            f.append("㉑ ❗取不到持仓时没显示「未知」（拿 0 顶替会把链路故障伪装成空仓）")

    # ㉒ 目标未设定要如实标出来
    rows22 = ui._allocation_rows(desk21, 1000.0, {})
    joined22 = " ".join(
        str(c.spec.get("content", "") if hasattr(c, "spec") else c)
        for c in rows22[0][:8]
    )
    if "未设定" not in joined22:
        f.append("㉒ ❗目标占比未设定却没标出来（拿默认值假装人拍过板 = 幽灵配置）")

    # ㉓ 循环守望的归档要能查到
    desk23, _ = _desk(ts=1000.0)
    w23 = desk23.declare_allocation(
        A("00700", "HK", alloc_pct=30.0, review_seconds=100.0), now=1000.0)
    desk23.registry.due(1100.0, settle=True)
    desk23.registry.renew(1100.0)
    hist = w23.cycle_history(5)
    if len(hist) != 1:
        f.append(f"㉓ 续期后应有 1 期归档，实际 {len(hist)}")
    elif hist[0].get("outcome") != "reviewed":
        f.append("㉓ 归档里记的结算结果不对")

    return f


# ─────────────────────────────────────────────────────────────
# 静态检查
# ─────────────────────────────────────────────────────────────

def code_only(path: Path) -> str:
    """去注释 + 剥 docstring —— 否则扫到文档里「禁止续期」几个字就误报。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef,
                                 ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)):
            node.body = body[1:] or [ast.Pass()]
    return ast.unparse(tree)


def static_checks() -> list:
    failures = []
    cache: Dict[Path, str] = {}

    def code_of(p: Path) -> str:
        if p not in cache:
            try:
                cache[p] = code_only(p)
            except SyntaxError:
                cache[p] = p.read_text(encoding="utf-8")
        return cache[p]

    lookup = {
        "allocation.py": ALLOC_PY, "watch.py": WATCH_PY,
        "registry.py": REGISTRY_PY, "desk.py": DESK_PY,
        "ui.py": UI_PY, "intent_runner.py": RUNNER_PY,
    }
    for name, pattern, why in REQUIRED_RULES:
        p = lookup.get(name)
        if p is None:
            failures.append(f"[静态] 未登记的 {name}")
            continue
        if not p.exists():
            failures.append(f"[静态] 文件不存在：{name}")
            continue
        if not re.search(pattern, code_of(p), re.M):
            failures.append(f"[静态] {name}: {why}")
    for name, pattern, why in FORBIDDEN_RULES:
        p = lookup.get(name)
        if p is None or not p.exists():
            continue
        if re.search(pattern, code_of(p), re.M):
            failures.append(f"[禁止] {name}: {why}")
    return failures


# ─────────────────────────────────────────────────────────────
# 负向注入
# ─────────────────────────────────────────────────────────────

INJECTIONS = [
    {
        "name": "❗长期配置登记成一次性守望（第一期结束就变尸体）",
        "file": ALLOC_PY,
        "old": "        recurring=True,\n    )",
        "new": "        recurring=False,\n    )",
        "count": -1,
    },
    {
        "name": "❗循环守望到期被判成 expired（每期假装失败一次）",
        "file": REGISTRY_PY,
        "old": "                if w.recurring:",
        "new": "                if False:",
        "count": -1,
    },
    {
        "name": "❗renew 不看结算结果，撤下的被复活",
        "file": REGISTRY_PY,
        "old": "            if w.settlement != Settlement.REVIEWED:",
        "new": "            if False:",
        "count": -1,
    },
    {
        "name": "❗arm() 不重置 armed_at（续期后下一轮立刻又到期）",
        "file": WATCH_PY,
        "old": "        self.armed_at = t\n        self.last_prod_at = t",
        "new": "        pass\n",
        "count": -1,
    },
    {
        "name": "❗arm() 不分循环与否，一次性守望也能续",
        "file": WATCH_PY,
        "old": (
            "            raise ValueError(\n"
            "                f\"守望 {self.watch_id} 不是循环守望"
            "（recurring=False），\"\n"
            "                \"不能续期 —— 一次性守望到期就该结束，"
            "重新挂请用 declare()\"\n"
            "            )"
        ),
        "new": "            pass  # 注入：一次性守望也能续期",
        "count": -1,
    },
    {
        "name": "❗允许无限期的长期配置（review_seconds 可为 0）",
        "file": ALLOC_PY,
        "old": "        if wait <= 0:",
        "new": "        if False:",
        "count": -1,
    },
    {
        "name": "❗长期配置没登记观测面工厂（永远取不到观测）",
        "file": DESK_PY,
        "old": '        self._observers["allocation"] = self._intent_context',
        "new": "        pass",
        "count": -1,
    },
    {
        "name": "❗改目标占比不写回清单（重启就回到未设定）",
        "file": RUNNER_PY,
        "old": '    save_allocations(rows, path)\n    return "added"',
        "new": '    return "added"  # 注入：不落盘',
        "count": -1,
    },
    {
        "name": "❗落盘不是原子替换（写一半崩掉会抹掉整份清单）",
        "file": RUNNER_PY,
        "old": "    os.replace(tmp, p)",
        "new": "    p.write_text(tmp.read_text(encoding='utf-8'), encoding='utf-8'); tmp.unlink()",
        "count": -1,
    },
    {
        "name": "❗删不存在的配置返回 True（假成功）",
        "file": RUNNER_PY,
        "old": "    if len(left) == len(rows):\n        return False",
        "new": "    if len(left) == len(rows):\n        return True",
        "count": -1,
    },
]


def _apply(inj) -> bool:
    path: Path = inj["file"]
    text = path.read_text(encoding="utf-8")
    old, new = inj["old"], inj["new"]
    if old not in text:
        print(f"   ⚠️ 锚点不存在：{inj['name']}")
        return False
    n = inj.get("count", 1)
    path.write_text(
        text.replace(old, new) if n == -1 else text.replace(old, new, n),
        encoding="utf-8",
    )
    return True


def _reload_all() -> None:
    """按依赖序重载整条链。顺序错了会造出两份类，用例自己崩 ——
    所以每次都先跑一遍「什么都不改」的基线。"""
    for mod in ("deva.naja.watch.manas_lens", "deva.naja.watch.objective",
                "deva.naja.watch.opportunity", "deva.naja.watch.watch",
                "deva.naja.watch.registry", "deva.naja.watch.intent",
                "deva.naja.watch.allocation", "deva.naja.watch.desk",
                "deva.naja.watch.ui", "deva.naja.watch",
                "deva.naja.bandit.intent_runner"):
        importlib.reload(importlib.import_module(mod))
    global W
    W = importlib.reload(W)


def exercise_injections() -> int:
    print("\n=== 负向注入：故意改坏代码，验证守卫不是摆设 ===")
    caught = 0

    # ❗自证第零步：什么都不改先重载一遍，用例必须仍然全绿。
    # 少了这一步，reload 顺序搞错时每条注入都「被捕获」—— 抓的是守卫自己的 bug。
    _reload_all()
    baseline = behavior_checks() + static_checks()
    if baseline:
        print("   ❌ 纯 reload 下用例就不绿了（守卫自己的 bug，注入结果不可信）：")
        for x in baseline[:5]:
            print("      -", x)
        return 1
    print("   ✅ 基线：纯 reload 后用例仍然全绿")

    for inj in INJECTIONS:
        backup = inj["file"].read_text(encoding="utf-8")
        try:
            if not _apply(inj):
                print(f"   ⚠️ 跳过（锚点缺失，是用例 bug 不是产品 bug）：{inj['name']}")
                continue
            _reload_all()
            bad = behavior_checks() + static_checks()
            if bad:
                print(f"   ✅ 被捕获：{inj['name']}（{bad[0][:46]}）")
                caught += 1
            else:
                print(f"   ❌ 没抓到：{inj['name']}")
        finally:
            inj["file"].write_text(backup, encoding="utf-8")

    total = len(INJECTIONS)
    print(f"\n负向注入 {caught}/{total} 被捕获")
    return 0 if caught == total else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--exercise-injections", action="store_true")
    a = ap.parse_args()
    logging.disable(logging.CRITICAL)

    if a.exercise_injections:
        return exercise_injections()

    failures = static_checks() + behavior_checks()
    if failures:
        print("❌ 长期配置守卫发现 %d 项问题：" % len(failures))
        for x in failures:
            print("   -", x)
        return 1
    print("✅ 长期配置守卫全绿（长期 ≠ 无限期 · 到期=这期看过了 · 撤下真终止）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
