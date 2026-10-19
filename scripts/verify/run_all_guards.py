#!/usr/bin/env python3
"""一键跑全套守卫（严格档）—— 让「守卫烂了没人知道」这件事不可能再发生。

为什么要有它
============
本仓的守卫是**两级制**：不带 ``--strict`` 是「提示档」（打印失败但退出码 0），
带 ``--strict`` 才是「闸门档」（失败即非零）。闸门在 strict，于是：

* 谁要是习惯了裸跑 ``python3 scripts/verify/verify_xxx.py``，
  看到满屏 ❌ 也只会拿到退出码 0，很容易当成"没事"；
* 更隐蔽的是**守卫自己烂掉**：产品 API 改了名/加了必填参数，守卫的
  fixture 还在用旧签名 → 检查项一进去就 TypeError →
  打印 ❌ 但（非 strict 下）退出码 0。

实锤：``verify_t_rotation_wiring.py`` 在做 T 换富途行情（``b80dba1``）之后，
**24 项里有 17 项崩掉**，就这样躺了一个版本，直到有人逐个手跑才发现。
根因不是退出策略，是**没有一个统一入口去跑**。

❗第二个实锤（同一份守卫，2026-10-19）：``first_reason()`` 原来倒着扫输出，
把进程收尾的 ``redis ConnectionError``（deva 总线底层 RedisStream 的退出噪声）
当成了失败原因 → 真正的 ``❌ 9/25 项失败``（替身缺 ``fetch``）被压了一整轮没
人看见。**摘要也是展示，摘要错了＝诊断错了**，所以现在先取结论行。

跑法
----
    # 全跑（推荐，等价于 CI 的闸门）
    env -u PYTHONPATH TMPDIR=$(mktemp -d) \
        /opt/homebrew/opt/python@3.13/bin/python3.13 scripts/verify/run_all_guards.py

    # 只看失败的
    ... run_all_guards.py --quiet

    # 挑着跑
    ... run_all_guards.py --only t_rotation,manas,watch

跳过清单
--------
``SKIP`` 里的守卫**默认不跑**，因为跑它们会改变本机状态（重启真服务等）。
要跑必须显式 ``--include-dangerous``。
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

VERIFY_DIR = Path(__file__).resolve().parent
REPO = VERIFY_DIR.parents[1]

#: 会动本机状态的守卫 —— 默认跳过，必须有意识地打开。
SKIP: dict[str, str] = {
    "verify_naja_restart": "会真的重启正在运行的 Naja 服务（停旧起新），不是只读检查",
}

#: 不支持 --strict 的守卫（各自用专属参数），跑时不传 strict。
NO_STRICT_FLAG = {
    "verify_guard_db_isolation",       # 无 argparse，忽略 argv
    "verify_naja_restart",             # 见 SKIP
}

#: 单份守卫的超时（秒）。做 T/守望类要起线程、跑模拟盘，给宽一点。
DEFAULT_TIMEOUT = 900


def discover() -> list[Path]:
    return sorted(VERIFY_DIR.glob("verify_*.py"))


def accepts_strict(path: Path) -> bool:
    if path.stem in NO_STRICT_FLAG:
        return False
    try:
        return "--strict" in path.read_text(encoding="utf-8")
    except Exception:
        return False


#: 结论行，例如 ``❌ 9/25 项失败`` / ``❌ 3/3 项失败：a, b, c``。
#: 守卫跑完会**先**打印自己的结论，再退出；而进程收尾阶段常常还会甩出一堆
#: 无关 traceback（最典型的是 deva 总线底层的 RedisStream 在退出时抛
#: ``redis ConnectionError``）。只看最后一行必然吃到噪声。
CONCLUSION_RE = re.compile(r"^\s*❌\s*\d+\s*/\s*\d+")


def first_reason(out: str) -> str:
    """从输出里挑一行最能说明问题的，做摘要。

    ❗**必须先取结论行，不能只倒着扫**。倒着取第一行含 ``❌``/``失败``/``Error:``
    的行看似省事，但真实输出里结论之后还有一堆退出噪声 —— 实测两份做 T 守卫的
    失败摘要长期被末尾的 ``redis.exceptions.ConnectionError`` 顶掉，于是"为什么
    失败"被记成了完全无关的 redis。这是**日志展示的数 ≠ 真正用来算的数**的同一
    个病：摘要也是展示，它错了就等于诊断错了。
    """
    lines = [ln.rstrip() for ln in out.splitlines() if ln.strip()]
    for ln in lines:
        if CONCLUSION_RE.match(ln):
            return ln.strip()[:110]
    for ln in reversed(lines):
        s = ln.strip()
        if s.startswith("❌") or "违约" in s or "失败" in s or "Error:" in s:
            return s[:110]
    return lines[-1][:110] if lines else ""


def run_one(path: Path, timeout: int) -> tuple[str, str, float]:
    """:return: (state, reason, seconds)；state ∈ PASS/FAIL"""
    cmd = [sys.executable, str(path)]
    if accepts_strict(path):
        cmd.append("--strict")
    env = dict(os.environ)
    # 宿主（WorkBuddy/IDE）会通过 PYTHONPATH 注入 sitecustomize shim，
    # 污染子进程导入行为；守卫一律在干净环境里跑。
    env.pop("PYTHONPATH", None)
    env["TMPDIR"] = tempfile.mkdtemp(prefix="naja_guard_")
    t0 = time.time()
    try:
        p = subprocess.run(
            cmd, cwd=str(REPO), env=env,
            capture_output=True, text=True, timeout=timeout,
        )
        out = (p.stdout or "") + (p.stderr or "")
        rc = p.returncode
    except subprocess.TimeoutExpired:
        return "FAIL", f"⏱ 超时（>{timeout}s）", time.time() - t0
    except Exception as e:  # pragma: no cover
        return "FAIL", f"启动失败: {type(e).__name__}: {e}", time.time() - t0

    if rc == 0:
        return "PASS", "", time.time() - t0
    # rc=1 = 自查发现问题；其它 = 脚本自身出错（更严重：守卫坏了）
    tag = "" if rc == 1 else f"[rc={rc} 守卫自身出错] "
    return "FAIL", tag + (first_reason(out) or f"exit {rc}"), time.time() - t0


def main() -> int:
    ap = argparse.ArgumentParser(description="一键严格扫描全部守卫")
    ap.add_argument("--quiet", action="store_true", help="只打印失败的")
    ap.add_argument("--only", help="只跑名字里含这些关键字的（逗号分隔）")
    ap.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    ap.add_argument("--include-dangerous", action="store_true",
                    help="连 SKIP 里那些会改本机状态的也跑（谨慎）")
    ap.add_argument("--list", action="store_true", help="只列出会跑哪些")
    args = ap.parse_args()

    targets = discover()
    if args.only:
        keys = [k.strip() for k in args.only.split(",") if k.strip()]
        targets = [p for p in targets if any(k in p.stem for k in keys)]

    skipped: list[tuple[str, str]] = []
    runnable: list[Path] = []
    for p in targets:
        if p.stem in SKIP and not args.include_dangerous:
            skipped.append((p.stem, SKIP[p.stem]))
            continue
        runnable.append(p)

    if args.list:
        for p in runnable:
            print(f"  will run: {p.stem}  (strict={accepts_strict(p)})")
        for name, why in skipped:
            print(f"  SKIP: {name} —— {why}")
        return 0

    print("=" * 74)
    print(f"守卫全量扫描（严格档）  共 {len(runnable)} 份   "
          f"{time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 74)

    failures: list[tuple[str, str]] = []
    t_all = time.time()
    for i, p in enumerate(runnable, 1):
        state, reason, secs = run_one(p, args.timeout)
        if state == "FAIL":
            failures.append((p.stem, reason))
            print(f"  {i:>3}/{len(runnable)}  ❌ {p.stem:<44s} {secs:6.1f}s  {reason}")
        elif not args.quiet:
            print(f"  {i:>3}/{len(runnable)}  ✅ {p.stem:<44s} {secs:6.1f}s")

    print("-" * 74)
    for name, why in skipped:
        print(f"  ⏭️  跳过 {name} —— {why}")
    print(f"\n总计 {len(runnable)} 份：通过 {len(runnable) - len(failures)}，"
          f"失败 {len(failures)}，跳过 {len(skipped)}，用时 {time.time() - t_all:.0f}s")
    if failures:
        print("\n失败清单：")
        for name, reason in failures:
            print(f"  ❌ {name}\n      {reason}")
        return 1
    print("\n✅ 全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
