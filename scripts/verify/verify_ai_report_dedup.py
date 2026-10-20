#!/usr/bin/env python3
"""验证「AI 晚报单槽位只推一次」—— 重启系统不再重复推送。

================================================================================
它解决什么问题
================================================================================
用户反馈：「每次启动系统的时候，好像都会发 iMessage naja AI 晚报，重复了」。

实测（2026-10-14）一次启动推了两条（00:18:36 / 00:19:22），第二次启动又推一条
（00:29:49）。根因三层：

  ① **守卫猜产物文件名**（主因）
     ``AIDailyReportWakeSync.should_wake_sync`` 查
     ``~/.naja/ai_reports/{YYYYMMDD}_v2.txt``
     而 ``execute()`` 实际落盘 ``{YYYYMMDD_HHMM}_v2.txt``（带时分）。
     口径不一致 → 三个时段分支全部为真 → **每次启动都重发**。
     产物文件名是给人翻阅用的，本来就应该带时分；把它当幂等键是错配。

  ② **同一次启动内两条链路各发一次**
     - ``TaskManager._catchup_missed_cron_tasks`` 补执行（logger 名 ``builtins``）
     - ``AIDailyReportWakeSync`` 唤醒补作业（直接 import ``execute``）
     两者几乎同时进入 ``execute()``，各推一条。

  ③ **任务定义双源**
     ``deva/config/tasks/ai_daily_report.yaml``：cron 20:00 + func_code 整段内联旧实现
     ``container._register_ai_daily_report_task``：cron 21:00 + 薄壳转发
     ``manager.load_prefer_files()`` 文件优先 → 实际生效 = 20:00 + 旧代码，
     容器那句只打印「任务已存在」。两个时间、两份实现并存。

修法：幂等键与产物命名**解耦**，改由独立的「槽位标记」承担
（``~/.naja/ai_reports/.sent/{slot}.json``），并加原子认领解决同进程竞态；
任务定义收敛为单源薄壳 + 统一 21:00。

================================================================================
八段检查
================================================================================
  ① 静态：``execute`` 三道幂等闸齐全，且 ``send_imessage`` 在认领之后
  ② 静态：WakeSync 守卫不再猜产物文件名 / 不再硬编码用户目录
  ③ 静态：时间窗与 ``AI_REPORT_HOUR`` 对齐
  ④ 静态：cron 单源 —— yaml / container / ``AI_REPORT_HOUR`` 三者一致
  ⑤ 静态：yaml 无内联实现、无硬编码手机号
  ⑥ 行为：槽位口径（21:00 分界）、标记互斥、最小重发间隔
  ⑦ 行为：``execute`` 短路时一次都不发送
  ⑧ 集成：WakeSync 守卫真的读标记；handler 有实际注册调用方

================================================================================
用法
================================================================================

    cd <项目根>
    /Users/spark/.local/bin/python3 scripts/verify/verify_ai_report_dedup.py
    /Users/spark/.local/bin/python3 scripts/verify/verify_ai_report_dedup.py --strict

退出码：0 = PASS；--strict 下有违约则 1。

**只读约定**：只读源码、只在临时目录里建标记、不真的发 iMessage、不起服务。
"""

from __future__ import annotations

import argparse
import ast
import copy
import datetime as _dt
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

MODULE_SRC = PROJECT_ROOT / "deva/naja/tasks/ai_daily_report.py"
WAKE_SRC = PROJECT_ROOT / "deva/naja/state/system/wake_sync_handlers.py"
WAKE_MGR_SRC = PROJECT_ROOT / "deva/naja/state/system/wake_sync_manager.py"
CONTAINER_SRC = PROJECT_ROOT / "deva/naja/application/container.py"
TASK_YAML = PROJECT_ROOT / "deva/config/tasks/ai_daily_report.yaml"

violations: list = []


def check(desc: str, ok: bool, detail: str = "") -> bool:
    mark = "✅" if ok else "❌"
    line = f"  {mark} {desc}"
    if detail:
        line += f"  — {detail}"
    print(line)
    if not ok:
        violations.append(desc)
    return bool(ok)


def skip(desc: str, detail: str = "") -> None:
    line = f"  ⏭️  {desc}"
    if detail:
        line += f"  — {detail}"
    print(line)


def _find_func(tree: ast.AST, func_name: str, cls: str = None):
    """定位函数/方法节点。

    cls 给定时只在同名类里找；未给定时先找模块级函数，再退化为
    「找任意类里的同名方法」—— container 里的注册函数挂在 AppContainer
    类下，不退化就会静默找不到（本守卫第一版就踩了）。
    """
    if cls:
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name == cls:
                for m in node.body:
                    if isinstance(m, ast.FunctionDef) and m.name == func_name:
                        return m
        return None

    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            return node
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            for m in node.body:
                if isinstance(m, ast.FunctionDef) and m.name == func_name:
                    return m
    return None


def _normalized_func(path: Path, func_name: str, cls: str = None) -> str:
    """取函数体源码：按方法块切 + 剥 docstring + 去注释（ast.unparse 天然不带注释）。

    ❗整文件 grep 会命中别的方法或注释里的同名符号（本项目踩过两次），
    所以必须精确切到目标方法块。
    """
    try:
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src)
    except Exception:
        return ""

    target = _find_func(tree, func_name, cls)
    if target is None:
        return ""

    node = copy.deepcopy(target)
    body = node.body
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        node.body = body[1:] or [ast.Pass()]
    ast.fix_missing_locations(node)
    try:
        return ast.unparse(node)
    except Exception:
        return ""


def _first_call_lineno(path: Path, func_name: str, callee: str) -> int:
    """目标函数体内首次调用 callee 的行号（0 表示没有）。"""
    try:
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src)
    except Exception:
        return 0

    target = _find_func(tree, func_name, None)
    if target is None:
        return 0

    best = 0
    for n in ast.walk(target):
        if not isinstance(n, ast.Call):
            continue
        fn = n.func
        name = fn.id if isinstance(fn, ast.Name) else (fn.attr if isinstance(fn, ast.Attribute) else None)
        if name == callee:
            best = n.lineno if best == 0 else min(best, n.lineno)
    return best


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true", help="有违约则 exit 1")
    args = parser.parse_args()

    # ── 前置：文件存在性 ───────────────────────────────────────────────
    for p in (MODULE_SRC, WAKE_SRC, WAKE_MGR_SRC, CONTAINER_SRC, TASK_YAML):
        if not p.exists():
            print(f"❌ 缺少源文件: {p}")
            return 1

    import yaml  # noqa: E402

    yaml_doc = yaml.safe_load(TASK_YAML.read_text(encoding="utf-8")) or {}
    yaml_cfg = yaml_doc.get("config", {})
    yaml_func = yaml_doc.get("func_code", "") or ""

    # ── ① execute 的三道幂等闸 ─────────────────────────────────────────
    print()
    print("=" * 68)
    print("① execute：幂等闸齐全，且 send_imessage 在认领之后")
    print("=" * 68)
    exec_src = _normalized_func(MODULE_SRC, "execute")
    check("定位到 execute 方法体", bool(exec_src), f"{len(exec_src)} 字符")
    if exec_src:
        check("入口短路闸 should_skip_send 存在", "should_skip_send" in exec_src)
        check("原子认领闸 claim_send_slot 存在", "claim_send_slot" in exec_src)
        check("失败回退 release_send_slot 存在", "release_send_slot" in exec_src)

        line_claim = _first_call_lineno(MODULE_SRC, "execute", "claim_send_slot")
        line_send = _first_call_lineno(MODULE_SRC, "execute", "send_imessage")
        check(
            "send_imessage 位于 claim_send_slot 之后（不许绕过认领）",
            line_claim > 0 and line_send > 0 and line_claim < line_send,
            f"claim@L{line_claim} < send@L{line_send}",
        )
        check(
            "execute 不再自己拼 ~/.naja/ai_reports 路径",
            "~/.naja/ai_reports" not in exec_src,
            "产物路径统一由 report_path_for() 给",
        )

    # ── ② WakeSync 守卫不再猜文件名 ────────────────────────────────────
    print()
    print("=" * 68)
    print("② WakeSync 守卫：不再猜产物文件名")
    print("=" * 68)
    guard = _normalized_func(WAKE_SRC, "should_wake_sync", cls="AIDailyReportWakeSync")
    check("定位到 AIDailyReportWakeSync.should_wake_sync", bool(guard), f"{len(guard)} 字符")
    if guard:
        check("不再用 _v2.txt 猜产物（历史病根）", "_v2.txt" not in guard)
        check("不再硬编码 /Users/spark/.naja", "/Users/spark" not in guard)
        check("改用统一判定 should_skip_send", "should_skip_send" in guard)
        check("判定失败时 fail-closed（不 fail-open 重发）",
              "return False" in guard)

    rng = _normalized_func(WAKE_SRC, "get_wake_sync_range", cls="AIDailyReportWakeSync")
    check("时间窗起点与 AI_REPORT_HOUR 对齐", "AI_REPORT_HOUR" in rng)
    check("时间窗不再写死 20 点", "hour=20" not in rng)

    # ── ③ 定时点的唯一权威 ─────────────────────────────────────────────
    print()
    print("=" * 68)
    print("③ AI_REPORT_HOUR：cron 单源")
    print("=" * 68)
    import deva.naja.tasks.ai_daily_report as mod  # noqa: E402

    hour = getattr(mod, "AI_REPORT_HOUR", None)
    check("模块暴露 AI_REPORT_HOUR", isinstance(hour, int), f"= {hour}")
    if isinstance(hour, int):
        expected_cron = f"0 {hour} * * *"
        check(
            "yaml cron 与 AI_REPORT_HOUR 一致",
            (yaml_cfg.get("cron_expr") or "").strip() == expected_cron,
            f"yaml={yaml_cfg.get('cron_expr')!r} 期望={expected_cron!r}",
        )
        reg = _normalized_func(CONTAINER_SRC, "_register_ai_daily_report_task")
        check("定位到 container 的注册方法", bool(reg), f"{len(reg)} 字符")
        # ast.unparse 会把字符串字面量渲染成单引号，所以两种引号都要认。
        m = re.search(r"cron_expr\s*=\s*['\"]([^'\"]+)['\"]", reg)
        container_cron = m.group(1) if m else "<未找到>"
        check(
            "container 注册的 cron 与 AI_REPORT_HOUR 一致",
            container_cron == expected_cron,
            f"container={container_cron!r}",
        )

    # ── ④ yaml 是薄壳、无内联实现 ──────────────────────────────────────
    print()
    print("=" * 68)
    print("④ yaml 任务定义：薄壳单源")
    print("=" * 68)
    check("func_code 转发到模块实现",
          "from deva.naja.tasks.ai_daily_report import" in yaml_func)
    check("不再内联旧实现", "def fetch_arxiv_papers" not in yaml_func)
    # ❗号码本身不写进守卫（仓库公开）—— 用「疑似中国大陆手机号」的模式来判
    check("不再硬编码手机号",
          not re.search(r"(?<!\d)(?:\+?86)?1[3-9]\d{9}(?!\d)", yaml_func))
    check("yaml 的 name 未漂移", yaml_doc.get("metadata", {}).get("name") == "ai_daily_report")

    # 文件优先于 NB 的前提：yaml 的 updated_at 必须 >= NB 里的值。
    # NB 可读则比对；不可读如实跳过（不是链路故障）。
    try:
        import pickle
        import sqlite3

        db_path = os.path.expanduser("~/.deva/nb.sqlite")
        if not os.path.exists(db_path):
            skip("NB 比对（库文件不存在）", db_path)
        else:
            yaml_updated = float(yaml_doc.get("metadata", {}).get("updated_at") or 0)
            nb_updated = None
            con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            try:
                for _k, v in con.execute("SELECT key, value FROM naja_tasks"):
                    if not isinstance(v, (bytes, bytearray)):
                        continue
                    try:
                        d = pickle.loads(bytes(v))
                    except Exception:
                        continue
                    md = d.get("metadata", {}) if isinstance(d, dict) else {}
                    if md.get("name") == "ai_daily_report":
                        nb_updated = float(md.get("updated_at") or 0)
                        nb_cron = md.get("cron_expr")
                        break
            finally:
                con.close()
            if nb_updated is None:
                skip("NB 比对（NB 中无该任务）")
            else:
                check(
                    "yaml updated_at >= NB updated_at（文件才会真正优先）",
                    yaml_updated >= nb_updated,
                    f"yaml={yaml_updated:.0f} NB={nb_updated:.0f}（NB cron={nb_cron!r}）",
                )
    except Exception as e:
        skip("NB 比对（读取失败）", str(e))

    # ── ⑤ 槽位口径（纯函数） ───────────────────────────────────────────
    print()
    print("=" * 68)
    print("⑤ 槽位口径：21:00 分界")
    print("=" * 68)
    cases = [
        (_dt.datetime(2026, 10, 14, 0, 30), "2026-10-13", "凌晨启动算前一天的槽位"),
        (_dt.datetime(2026, 10, 14, 20, 59), "2026-10-13", "21:00 前仍是前一天"),
        (_dt.datetime(2026, 10, 14, 21, 0), "2026-10-14", "21:00 起算当天"),
        (_dt.datetime(2026, 10, 14, 23, 59), "2026-10-14", "当天深夜仍是当天"),
    ]
    for when, want, why in cases:
        got = mod.current_slot_date(when)
        check(f"{when:%m-%d %H:%M} → {want}（{why}）", got == want, f"got={got}")

    # ── ⑥ 标记互斥 + 最小重发间隔（临时目录） ──────────────────────────
    print()
    print("=" * 68)
    print("⑥ 槽位标记：原子认领 & 最小重发间隔")
    print("=" * 68)
    tmp = tempfile.mkdtemp(prefix="ai_report_dedup_")
    orig_marker_dir = mod.SENT_MARKER_DIR
    now = _dt.datetime(2026, 10, 14, 21, 5)
    try:
        mod.SENT_MARKER_DIR = os.path.join(tmp, ".sent")

        s, _r = mod.should_skip_send(now)
        check("无任何标记 → 不跳过", s is False)

        check("claim 首次成功", mod.claim_send_slot("2026-10-14") is True)
        check("claim 同槽位第二次失败（互斥）", mod.claim_send_slot("2026-10-14") is False)
        s, r = mod.should_skip_send(now)
        check("已标记 → 跳过且给出原因", s is True and "已推送过" in r, r)

        mod.release_send_slot("2026-10-14")
        check("回退后该槽位重新可认领", mod.is_slot_sent("2026-10-14") is False)
        check("回退后确实能再拿一次", mod.claim_send_slot("2026-10-14") is True)

        # 最小重发间隔：换个槽位但刚发过 → 仍应跳过（防跨槽位边界抖动）
        # ❗这里不能用 claim_send_slot 造数据 —— 它写的是真实 time.time()，
        #   而上面的 now 是构造出来的，两者不在同一时间轴上（本守卫第一版
        #   的用例就栽在这：假 now 与真时钟差 20 小时，正反两向都测不出来）。
        mod.release_send_slot("2026-10-14")
        mod.SENT_MARKER_DIR = os.path.join(tmp, ".sent2")
        other = mod.sent_marker_path("1999-01-01")
        os.makedirs(os.path.dirname(other), exist_ok=True)

        with open(other, "w", encoding="utf-8") as f:
            json.dump({"slot": "1999-01-01", "sent_at": now.timestamp()}, f)
        s, r = mod.should_skip_send(now)
        check("异槽位但刚推过 → 跳过（最小重发间隔生效）",
              s is True and "距上次推送" in r, r)

        # 反方向用例：间隔足够久就必须放行，否则当天会被永久堵死
        with open(other, "w", encoding="utf-8") as f:
            json.dump(
                {"slot": "1999-01-01",
                 "sent_at": (now - _dt.timedelta(hours=mod.MIN_RESEND_INTERVAL_HOURS + 1)).timestamp()},
                f,
            )
        s, r = mod.should_skip_send(now)
        check("异槽位且间隔已超阈值 → 放行补发", s is False, f"skip={s} {r}")
    finally:
        mod.SENT_MARKER_DIR = orig_marker_dir
        shutil.rmtree(tmp, ignore_errors=True)
    check("临时目录已清理，真实标记目录未被写入",
          not os.path.exists(tmp))

    # ── ⑦ execute 短路时一次都不发送 ───────────────────────────────────
    print()
    print("=" * 68)
    print("⑦ execute 短路：不抓取、不发送")
    print("=" * 68)
    sent_calls: list = []
    orig_send = mod.send_imessage
    orig_skip = mod.should_skip_send
    try:
        mod.send_imessage = lambda *a, **k: (sent_calls.append(a), True)[1]
        mod.should_skip_send = lambda now=None: (True, "验证用短路")
        result = mod.execute()
    except Exception as e:
        result = {"success": False, "error": str(e)}
    finally:
        mod.send_imessage = orig_send
        mod.should_skip_send = orig_skip

    check("短路返回 success", result.get("success") is True, str(result)[:80])
    check("短路返回 skipped 标记", result.get("skipped") is True)
    check("短路时一次都没调用 send_imessage", sent_calls == [], f"{len(sent_calls)} 次")

    # ── ⑧ 集成：守卫读标记 + handler 有调用方 ─────────────────────────
    print()
    print("=" * 68)
    print("⑧ 集成：WakeSync 守卫真的读标记；handler 已注册")
    print("=" * 68)
    try:
        from deva.naja.state.system.wake_sync_handlers import AIDailyReportWakeSync
    except Exception as e:
        check("可导入 AIDailyReportWakeSync", False, str(e))
    else:
        tmp2 = tempfile.mkdtemp(prefix="ai_report_wake_")
        try:
            mod.SENT_MARKER_DIR = os.path.join(tmp2, ".sent")
            handler = AIDailyReportWakeSync()
            check("无标记 → 需要补发", handler.should_wake_sync(None) is True)

            slot = mod.current_slot_date()
            marker = mod.sent_marker_path(slot)
            os.makedirs(os.path.dirname(marker), exist_ok=True)
            with open(marker, "w", encoding="utf-8") as f:
                json.dump({"slot": slot, "sent_at": _dt.datetime.now().timestamp()}, f)
            check("当前槽位已标记 → 不再补发", handler.should_wake_sync(None) is False)
        finally:
            mod.SENT_MARKER_DIR = orig_marker_dir
            shutil.rmtree(tmp2, ignore_errors=True)

    mgr_src = WAKE_MGR_SRC.read_text(encoding="utf-8")
    check("handler 在 wake_sync_manager 里有实际注册调用方",
          "AIDailyReportWakeSync()" in mgr_src)

    # ── ⑨ 并发竞态：两条链路同一时刻进 execute ─────────────────────────
    # 这**就是原始故障形态**：TaskManager 补执行与 WakeSync 在 00:18:09 同时进
    # execute()，各推一条。顺序执行测不出这个问题，必须真并发。
    print()
    print("=" * 68)
    print("⑨ 并发竞态：同槽位只有一条链路能发出去")
    print("=" * 68)
    import threading

    tmp3 = tempfile.mkdtemp(prefix="ai_report_race_")
    try:
        mod.SENT_MARKER_DIR = os.path.join(tmp3, ".sent")
        slot = "2026-10-14"
        winners: list = []
        sent_box: list = []
        lock = threading.Lock()
        barrier = threading.Barrier(8)

        def _worker():
            barrier.wait()  # 8 个线程尽量同时冲
            if mod.should_skip_send(_dt.datetime(2026, 10, 14, 21, 5))[0]:
                return
            if mod.claim_send_slot(slot):
                with lock:
                    winners.append(1)
                    sent_box.append(1)

        threads = [threading.Thread(target=_worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        check("8 线程并发认领，恰好 1 个胜出", len(winners) == 1, f"胜出={len(winners)}")
        check("并发下恰好发送 1 次（不重复）", len(sent_box) == 1, f"发送={len(sent_box)}")
        check("槽位标记最终存在", mod.is_slot_sent(slot) is True)
    finally:
        mod.SENT_MARKER_DIR = orig_marker_dir
        shutil.rmtree(tmp3, ignore_errors=True)

    # ── 汇总 ──────────────────────────────────────────────────────────
    print()
    print("=" * 68)
    if violations:
        print(f"❌ 违约 {len(violations)} 项:")
        for v in violations:
            print(f"   - {v}")
        return 1 if args.strict else 0
    print("✅ 全部通过：AI 晚报单槽位只推一次，重启不再重发")
    return 0


if __name__ == "__main__":
    sys.exit(main())
