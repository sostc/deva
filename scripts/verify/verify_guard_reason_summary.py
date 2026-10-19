#!/usr/bin/env python3
"""守卫 run_all_guards 的**失败摘要必须指向真因**，不能被退出噪声顶掉。

================================================================================
背景（2026-10-19 实锤，不是推测）
================================================================================

``run_all_guards.first_reason()`` 原来是这样写的：

    lines = [l for l in out.splitlines() if l.strip()]
    for ln in reversed(lines):
        if ln.startswith("❌") or "失败" in ln or "Error:" in ln:
            return ln

**倒着取第一行匹配**看似省事，实际必吃最后的堆积噪声。真实输出里，守卫先打印
自己的结论，然后退出；而进程收尾阶段还会甩出无关 traceback —— 最典型的是 deva
总线底层的 ``RedisStream``（``import deva`` 就起了 topic=``bus`` 的消费者，对
本机 6379 做阻塞 xreadgroup），进程一收尾那条读就炸成
``redis.exceptions.ConnectionError: Connection closed by server.``。

后果：两份做 T 守卫明明是

    ❌ 9/25 项失败
    ❌ 3/3 项失败：check_batch_fill_is_silent, ...

真因是测试替身 ``FakeQuotes``/``QuoteSource`` 缺 ``fetch``（runner 改成批量取
行情的 ``c34f551`` 没同步改守卫），但汇总里长期显示成「redis ConnectionError」，
于是**连续几轮被当成环境噪声忽略**。

这是「日志展示的数 ≠ 真正用来算的数」的同一个病：**摘要也是展示**，摘要错了
等于诊断错了，而且它错的方式最坏 —— 让真正的失败看起来像环境问题。

================================================================================
核心不变量
================================================================================

**只要守卫输出里有结论行（``❌ N/M 项失败``），摘要就必须取自结论行，不许被
它之后的任何输出覆盖。**

反向也不能过头：没有结论行时（脚本自己崩了、或压根没有检查输出），仍要退回
反向扫描，否则摘要会变空 —— 「这一项为什么失败」就彻底没有答案了。

================================================================================
用法
================================================================================

    python3 scripts/verify/verify_guard_reason_summary.py
    python3 scripts/verify/verify_guard_reason_summary.py --strict
    python3 scripts/verify/verify_guard_reason_summary.py --exercise-injections
"""

from __future__ import annotations

import argparse
import ast
import importlib
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RUNNER_PY = REPO / "scripts" / "verify" / "run_all_guards.py"


def _rel(p: Path) -> str:
    try:
        return p.relative_to(REPO).as_posix()
    except ValueError:
        return str(p)


def _mod():
    """每次都 reload —— 注入改的是磁盘上的源码，不复载就会读到旧对象（假通过）。"""
    importlib.invalidate_caches()
    spec = importlib.util.spec_from_file_location("_rag_under_test", RUNNER_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── 用例素材：全部取自真实输出形态 ───────────────────────────────────────────
NOISE_TAIL = """[2026-10-19 23:41:12][INFO][deva] exit
bye bye, 75124
[2026-10-19 23:41:12][ERROR][deva.core.sources] RedisStream(bus) loop failed (retry 1/5)
Traceback (most recent call last):
  File "x.py", line 891, in process
    results = yield self.redis.xreadgroup(
redis.exceptions.ConnectionError: Connection closed by server.
"""

CASE_WITH_CONCLUSION = "18) 交易所号段判定 OK\n❌ 9/25 项失败\n" + NOISE_TAIL
CONCLUSION_EXPECT = "❌ 9/25 项失败"

CASE_NAMED_CONCLUSION = (
    "❌ 3/3 项失败：check_batch_fill_is_silent, check_true_stall_escalates_once\n"
    + NOISE_TAIL
)

CASE_LONG = (
    "".join(f"{i}) 某某检查 OK\n" for i in range(1, 41))
    + "❌ 2/25 项失败\n"
    + NOISE_TAIL
)

CASE_CRASH_ONLY = (
    "Traceback (most recent call last):\n"
    '  File "x.py", line 1, in <module>\n'
    "ValueError: boom\n"
)

CASE_NO_HIT = "some log line\nanother log line"


# ── 检查项 ───────────────────────────────────────────────────────────────────
def check_conclusion_beats_tail_noise() -> list:
    """结论行之后还有噪声 traceback 时，摘要必须取结论行。"""
    got = _mod().first_reason(CASE_WITH_CONCLUSION)
    if got != CONCLUSION_EXPECT:
        return [
            f"有结论行时摘要取到的是「{got}」而不是「{CONCLUSION_EXPECT}」—— "
            f"末尾的 redis 退出噪声把真因顶掉了，这正是两份做 T 守卫被误读的来源"
        ]
    return []


def check_named_conclusion_not_truncated_by_tail() -> list:
    """带名字的结论行要完整拿到（不能因为尾部的 Error 更靠后就丢掉清单）。"""
    got = _mod().first_reason(CASE_NAMED_CONCLUSION)
    if not got.startswith("❌ 3/3 项失败"):
        return [f"带清单的结论行没被选中：{got}"]
    if "check_batch_fill_is_silent" not in got:
        return [f"结论行里的失败清单丢失了：{got}"]
    return []


def check_long_output_still_finds_conclusion() -> list:
    """真守卫的输出很长（几十行 OK），结论行在末尾 —— 不许因为限行数漏掉它。"""
    got = _mod().first_reason(CASE_LONG)
    if got != "❌ 2/25 项失败":
        return [
            f"结论行在长输出末尾时没被取到（得到 {got}）—— "
            f"真实守卫一跑就是几十行，限制行数等于放弃摘要"
        ]
    return []


def check_falls_back_to_crash_traceback() -> list:
    """反方向：没有结论行（脚本自身崩溃）时，仍要给得出原因。"""
    got = _mod().first_reason(CASE_CRASH_ONLY)
    if "ValueError" not in got and "boom" not in got:
        return [f"没有结论行时摘要给不出崩溃信息（得到 {got!r}）—— 退回扫描失效了"]
    return []


def check_empty_output_is_safe() -> list:
    """没有输出不许抛异常（否则整份 runner 会在收尾时二次崩）。"""
    try:
        got = _mod().first_reason("")
    except Exception as e:  # noqa: BLE001
        return [f"空输出时 first_reason 抛出 {type(e).__name__}: {e}"]
    if got != "":
        return [f"空输出的摘要应为 ''，实为 {got!r}"]
    return []


def check_source_does_forward_scan() -> list:
    """源码层面：必须先正向找结论行，再反向兜底 —— 只靠反向会被噪声顶掉。"""
    tree = ast.parse(RUNNER_PY.read_text(encoding="utf-8"))
    fn = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "first_reason":
            fn = node
            break
    if fn is None:
        return [f"{_rel(RUNNER_PY)} 找不到 first_reason —— 锚点腐烂"]

    body_src = ast.unparse(fn)
    if "CONCLUSION_RE.match" not in body_src:
        return [
            f"{_rel(RUNNER_PY)} 的 first_reason 没有用 CONCLUSION_RE 先正向扫结论行"
        ]
    if "import re" not in RUNNER_PY.read_text(encoding="utf-8"):
        return [f"{_rel(RUNNER_PY)} 没有 import re 却在用 CONCLUSION_RE"]

    # 正向扫描必须**先于**反向兜底；反向兜底还必须有，否则脚本自身崩溃时摘要为空
    fwd = body_src.find("CONCLUSION_RE.match")
    rev = body_src.find("reversed(")
    if rev < 0:
        return [
            f"{_rel(RUNNER_PY)} 的 first_reason 丢掉了反向兜底 —— "
            f"脚本自身崩溃（没有结论行）时「为什么失败」将无答案"
        ]
    if fwd > rev:
        return [
            f"{_rel(RUNNER_PY)} 的反向兜底跑在结论行判定之前 —— 噪声先被取走，等于没改"
        ]
    return []


def _all_checks() -> list:
    failures: list = []
    failures += check_conclusion_beats_tail_noise()
    failures += check_named_conclusion_not_truncated_by_tail()
    failures += check_long_output_still_finds_conclusion()
    failures += check_falls_back_to_crash_traceback()
    failures += check_empty_output_is_safe()
    failures += check_source_does_forward_scan()
    return failures


# ── 负向注入 ─────────────────────────────────────────────────────────────────
INJECTIONS = [
    {
        "name": "改回纯反向扫描（噪声顶掉真因 —— 就是原来的 bug）",
        "old": (
            "    lines = [ln.rstrip() for ln in out.splitlines() if ln.strip()]\n"
            "    for ln in lines:\n"
            "        if CONCLUSION_RE.match(ln):\n"
            "            return ln.strip()[:110]\n"
        ),
        "new": "    lines = [ln.rstrip() for ln in out.splitlines() if ln.strip()]\n",
    },
    {
        "name": "摘要被截断到 10 字（失败清单丢失，看不出是哪项）",
        "old": "            return ln.strip()[:110]",
        "new": "            return ln.strip()[:10]",
    },
    {
        "name": "空输出时直接取 lines[-1]（跑空输出会 IndexError，runner 二次崩）",
        "old": '    return lines[-1][:110] if lines else ""',
        "new": "    return lines[-1][:110]",
    },
    {
        "name": "反向兜底被删（脚本自身崩溃时摘要变空）",
        "old": (
            "    for ln in reversed(lines):\n"
            "        s = ln.strip()\n"
            "        if s.startswith(\"❌\") or \"违约\" in s or \"失败\" in s or \"Error:\" in s:\n"
            "            return s[:110]\n"
        ),
        "new": "",
    },
    {
        "name": "结论行判定只在 MAX 行内生效（长输出里找不到结论）",
        "old": "    lines = [ln.rstrip() for ln in out.splitlines() if ln.strip()]\n    for ln in lines:",
        "new": (
            "    lines = [ln.rstrip() for ln in out.splitlines() if ln.strip()]\n"
            "    lines = lines[:5]\n"
            "    for ln in lines:"
        ),
    },
    {
        # 反方向：结论行判定里写注释提到 reversed 不算先反后正
        "name": "注释里出现 reversed(（反方向：不许误报）",
        "old": "    lines = [ln.rstrip() for ln in out.splitlines() if ln.strip()]\n    for ln in lines:",
        "new": (
            "    # 别退化成只扫 reversed(lines)\n"
            "    lines = [ln.rstrip() for ln in out.splitlines() if ln.strip()]\n"
            "    for ln in lines:"
        ),
        "expect_clean": True,
    },
]


def run_injections() -> int:
    original = RUNNER_PY.read_text(encoding="utf-8")
    caught = 0
    expected = len(INJECTIONS)
    missed = 0
    try:
        for inj in INJECTIONS:
            hits = original.count(inj["old"])
            if hits != 1:
                missed += 1
                print(f"❌ 注入锚点命中 {hits} 次（期望 1，守卫腐烂信号）：{inj['name']}")
                continue
            print(f"· 注入：{inj['name']}")
            RUNNER_PY.write_text(original.replace(inj["old"], inj["new"]), encoding="utf-8")
            try:
                found = _all_checks()
            except Exception as e:  # noqa: BLE001
                found = [f"守卫自身抛异常: {type(e).__name__}: {e}"]
            finally:
                RUNNER_PY.write_text(original, encoding="utf-8")

            if inj.get("expect_clean"):
                if found:
                    print(f"  ❌ 反方向用例被误报：{found[0][:110]}")
                else:
                    caught += 1
                    print("  ✅ 正确地没有报警（注释不是真的反向扫描）")
            elif found:
                caught += 1
                print(f"  ✅ 被捕获（{len(found)} 项）")
                for f in found[:2]:
                    print(f"       · {f[:110]}")
            else:
                print("  ❌ 没抓到 —— 这条守卫是摆设！")
    finally:
        if RUNNER_PY.read_text(encoding="utf-8") != original:
            print("  🚨 还原失败，强制重写")
            RUNNER_PY.write_text(original, encoding="utf-8")

    print(f"\n负向注入：{caught}/{expected} 被捕获"
          + (f"（另有 {missed} 条锚点未命中，已计失败）" if missed else ""))
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
        print("❌ 守卫摘要守卫 失败：")
        for f in failures:
            print(f"   - {f}")
        return 1 if args.strict else 0
    print("✅ 守卫摘要守卫全绿"
          "（结论行压过尾部噪声 · 崩溃仍可退回 · 空输出不炸 · 源码先正向后反向）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
