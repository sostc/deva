#!/usr/bin/env python3
"""守卫：未定义名字（F821）—— web_ui 层必须为 0，其余存量只许减不许增

背景（为什么要有这个守卫）
------------------------------------------------------------------
/tableadmin 打开即崩，根因只是 `pages.py:160` 写了一句 `ctx["NB"] = NB`
而 `NB` 从来没被 import 过 —— `NameError`。

这不是孤例，而是**同一家族**的一类病：
  「本该 import 的名字没有 import」，或「只在某个函数里 import 了，
    别的函数/模块级也在用」。
共同特征是 **静态一眼可见、但只在特定代码路径被触发**，
于是它们不会在启动时暴露，而是等到某个用户点到某个页面、某个 bus
事件到达、某条降级分支被走到时才炸。本次普查出的两个典型：

  * signal_listener.py:37  `log` 在 module 级 `except ImportError`
    降级分支里被使用，而 `log = logging.getLogger(...)` 在**它下面**
    第 41 行 —— 也就是「降级路径自己会抛 NameError」，
    等于降级分支从未被真正跑通过。
  * metrics 未导入的 typing 名字（Set/Tuple/Callable…），
    平时无声，一旦走到那个函数就 NameError。

这类 bug 的成本极高而发现成本极低，所以用守卫钉住。

本守卫分两级
------------------------------------------------------------------
  ① **硬零**：`deva/naja/web_ui/` 下 F821 必须为 0。
     理由：那是用户直接用浏览器点到的入口层，代价最高，
     且这一层已经被清干净了，没有理由再退回去。
     （baseline 对它**不设豁免**，进了 baseline 也照样报。）

  ② **棘轮**：仓库其余位置的历史存量冻结在 baseline 里。
     出现任何**新的** (文件, 名字) 组合即失败；
     存量变少时提示收紧 baseline（只许减不许增）。

用法
------------------------------------------------------------------
    python3 scripts/verify/verify_undefined_names.py --strict
    python3 scripts/verify/verify_undefined_names.py --update-baseline
    python3 scripts/verify/verify_undefined_names.py --self-test   # 自证有区分度

依赖 ruff（首选）或 pyflakes；两者都没有时**如实跳过**（打印 ⏭️，exit 0），
不假装通过。
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCAN_ROOT = REPO_ROOT / "deva"
BASELINE_FILE = Path(__file__).resolve().parent / "undefined_names_baseline.json"

# ① 硬零目录（相对 REPO_ROOT，正斜杠结尾）
HARD_ZERO_DIRS = ("deva/naja/web_ui/",)

# ruff concise: deva/x/y.py:12:34: F821 Undefined name `Foo`
RUFF_RE = re.compile(
    r"^(?P<path>[^:]+):(?P<line>\d+):(?P<col>\d+): F821 Undefined name `(?P<name>[^`]+)`\s*$"
)
# pyflakes: deva/x/y.py:12:34: undefined name 'Foo'
PYFLAKES_RE = re.compile(
    r"^(?P<path>[^:]+):(?P<line>\d+):(?P<col>\d+): undefined name '(?P<name>[^']+)'\s*$"
)

EXCLUDE = ("--exclude", ".git,.venv,node_modules,__pycache__")


def _rel(p: str, base: Path = REPO_ROOT) -> str:
    """把绝对/相对路径统一成相对 base 的正斜杠路径"""
    path = Path(p)
    if path.is_absolute():
        try:
            path = path.relative_to(base)
        except ValueError:
            try:
                path = path.relative_to(REPO_ROOT)
            except ValueError:
                pass
    return str(path).replace("\\", "/")


def _run(cmd: list[str], cwd: Path) -> tuple[int, str]:
    proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def pick_tool() -> tuple[str, list[str]] | None:
    """返回 (工具名, 命令行前缀)；都不可用返回 None"""
    if shutil.which("ruff"):
        return "ruff", ["ruff", "check", "--select", "F821", "--no-cache", "--output-format", "concise"]
    pyflakes = shutil.which("pyflakes")
    if pyflakes:
        return "pyflakes", [pyflakes]
    here = Path(sys.executable)
    for mod, name in (("ruff", "ruff"), ("pyflakes", "pyflakes")):
        code, _ = _run([str(here), "-m", mod, "--version"], REPO_ROOT)
        if code == 0:
            prefix = [str(here), "-m", mod]
            if name == "ruff":
                prefix += ["check", "--select", "F821", "--no-cache", "--output-format", "concise"]
            return name, prefix
    return None


def scan(target: Path, tool: tuple[str, list[str]], root: Path = REPO_ROOT) -> list[tuple[str, str]]:
    """扫描 target，返回排序去重后的 (相对路径, 名字) 列表"""
    name, prefix = tool
    cmd = list(prefix)
    if name == "ruff":
        cmd += list(EXCLUDE)
    cmd.append(str(target))
    _, out = _run(cmd, root)

    regex = RUFF_RE if name == "ruff" else PYFLAKES_RE
    found: set[tuple[str, str]] = set()
    for line in out.splitlines():
        m = regex.match(line.strip())
        if m:
            found.add((_rel(m.group("path"), root), m.group("name")))
    return sorted(found)


def load_baseline() -> set[tuple[str, str]]:
    if not BASELINE_FILE.exists():
        return set()
    try:
        data = json.loads(BASELINE_FILE.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return set()
    out: set[tuple[str, str]] = set()
    for item in data.get("known", []):
        if isinstance(item, str) and ":" in item:
            path, _, nm = item.rpartition(":")
            out.add((path, nm))
    return out


def collect_failures() -> tuple[list[str], set[tuple[str, str]], set[tuple[str, str]]]:
    """返回 (失败列表, 当前命中集合, baseline 集合)"""
    tool = pick_tool()
    if tool is None:
        return [], set(), set()
    current = set(scan(SCAN_ROOT, tool))
    baseline = load_baseline()

    failures: list[str] = []

    # ① 硬零目录
    hard_zero = sorted(p for p, _ in current if p.startswith(HARD_ZERO_DIRS))
    if hard_zero:
        failures.append(f"web_ui 层出现未定义名字（必须为 0）：{hard_zero}")

    # ② 棘轮：新增项
    new_items = sorted(current - baseline)
    if new_items:
        failures.append(f"新增 {len(new_items)} 处未定义名字：")
        for path, nm in new_items:
            failures.append(f"    + {path} → {nm}")

    return failures, current, baseline


def check() -> int:
    tool = pick_tool()
    if tool is None:
        print("⏭️  跳过：未找到 ruff / pyflakes，无法扫描未定义名字")
        return 0

    print(f"检测器：{tool[0]}")
    failures, current_set, baseline = collect_failures()

    # 报告
    fixed = sorted(baseline - current_set)
    print(f"存量（baseline）：{len(baseline)} 处 | 当前：{len(current_set)} 处")
    if fixed:
        print(f"✅ 已修复 {len(fixed)} 处（可执行 --update-baseline 收紧）：")
        for path, nm in fixed[:10]:
            print(f"    - {path} → {nm}")
        if len(fixed) > 10:
            print(f"    ... 另有 {len(fixed) - 10} 处")

    if failures:
        print("\n❌ 守卫失败：")
        for line in failures:
            print(line)
        return 1

    print("✅ 通过：web_ui 层 0 处未定义名字；仓库其余位置无新增")
    return 0


def update_baseline() -> int:
    tool = pick_tool()
    if tool is None:
        print("⏭️  跳过：未找到 ruff / pyflakes")
        return 0
    current = scan(SCAN_ROOT, tool)
    remain = [f"{p}:{n}" for p, n in current if not p.startswith(HARD_ZERO_DIRS)]
    data = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "tool": tool[0],
        "note": (
            "未定义名字（F821）历史存量。守卫只允许这份清单变短："
            "出现新组合即失败；修好一处就重跑 --update-baseline。"
            "web_ui/ 不在此列 —— 那一层要求硬零。"
        ),
        "hard_zero_dirs": list(HARD_ZERO_DIRS),
        "known": remain,
    }
    BASELINE_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"已写入 {_rel(str(BASELINE_FILE))}：{len(remain)} 处存量")
    return 0


def self_test() -> int:
    """自证有区分度：注入一个已知的未定义名字，守卫必须报出来。

    只复制「扫描器 + 检测器」这条链路，不依赖仓库其余部分
    —— F821 是纯文件内语法判断，不需要能 import。
    """
    tool = pick_tool()
    if tool is None:
        print("⏭️  跳过自证：未找到 ruff / pyflakes")
        return 0

    failures: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        pkg = tmp_root / "deva" / "naja" / "web_ui"
        pkg.mkdir(parents=True)

        # ① 反例：干净文件不应被报
        clean = pkg / "clean_probe.py"
        clean.write_text("import os\n\n\ndef f():\n    return os.getcwd()\n", encoding="utf-8")
        hits = scan(pkg, tool, root=tmp_root)
        if hits:
            failures.append(f"干净文件被误报：{hits}")

        # ② 正例：注入未定义名字，必须报出来，且路径能对上
        dirty = pkg / "dirty_probe.py"
        dirty.write_text(
            "def f():\n    return totally_undefined_symbol_xyz\n", encoding="utf-8"
        )
        hits = scan(pkg, tool, root=tmp_root)
        names = {n for _, n in hits}
        if "totally_undefined_symbol_xyz" not in names:
            failures.append(f"注入的未定义名字未被报出（实际：{hits}）")
        paths = {p for p, _ in hits}
        if not any(p.endswith("dirty_probe.py") for p in paths):
            failures.append(f"报出的路径不含注入文件（实际：{paths}）")

        # ③ 目录过滤必须生效：web_ui 命中要能被 hard-zero 规则捞到
        covered = [p for p, _ in hits if p.startswith(HARD_ZERO_DIRS)]
        if not covered:
            failures.append(
                f"注入项未被 hard-zero 目录规则覆盖（实际路径：{paths}）"
            )

    # ④ 基线解析自证
    if load_baseline() and not isinstance(next(iter(load_baseline())), tuple):
        failures.append("baseline 解析格式不对")

    if failures:
        print("❌ 自证失败：")
        for f in failures:
            print("   ", f)
        return 1
    print("✅ 自证通过：干净文件不误报，注入的未定义名字被捕获且路径/目录规则生效")
    return 0


def exercise_hard_zero() -> int:
    """行为自证：往真实 web_ui 里临时注入一个未定义名字，--strict 必须失败。

    这条测的是「① 硬零」这一条 invariant —— 光靠上面的隔离自证，
    证明不了真实扫描路径也会把它归类到 HARD_ZERO_DIRS。
    """
    tool = pick_tool()
    if tool is None:
        print("⏭️  跳过：未找到 ruff / pyflakes")
        return 0

    victim = REPO_ROOT / "deva" / "naja" / "web_ui" / "pages.py"
    original = victim.read_text(encoding="utf-8")
    marker = "zz_undefined_probe_xyz"
    patched = original + f"\n\ndef _probe():\n    return {marker}\n"
    rc = 1
    try:
        victim.write_text(patched, encoding="utf-8")
        hits = scan(SCAN_ROOT, tool)
        covered = any(
            p.startswith(HARD_ZERO_DIRS) and n == marker for p, n in hits
        )
        if not covered:
            print("❌ 行为自证失败：真实 web_ui 注入后未被 hard-zero 规则捕获")
            rc = 1
        else:
            print("✅ 行为自证通过：真实 web_ui 注入未定义名字后即被 hard-zero 捕获")
            rc = 0
    finally:
        victim.write_text(original, encoding="utf-8")
        # 确认还原干净
        if victim.read_text(encoding="utf-8") != original:
            print("‼️  还原失败，请手动检查 pages.py")
            rc = 1
    return rc


def exercise_ratchet() -> int:
    """反方向行为自证：在 **web_ui 之外** 新造一处未定义名字，棘轮必须报「新增」。

    与 exercise_hard_zero 是两条不同的 invariant：
      - hard_zero  : web_ui 目录内，无论 baseline 如何，一律硬失败；
      - ratchet    : 目录外，只有「相对 baseline 是新增的」才失败。
    只用 web_ui 那个用例，删掉「棘轮」这条规则守卫照样绿 → 假绿。
    """
    if pick_tool() is None:
        print("⏭️  跳过：未找到 ruff / pyflakes")
        return 0

    probe = SCAN_ROOT / "naja" / "_probe_ratchet_undefined.py"
    marker = "zz_ratchet_probe_xyz"
    if probe.exists():
        print("‼️  探针文件已存在，先手动清理：", _rel(str(probe)))
        return 1
    rc = 1
    try:
        probe.write_text(
            f'"""临时探针，守卫自证用，跑完即删"""\n\n\ndef f():\n    return {marker}\n',
            encoding="utf-8",
        )
        failures, current, _ = collect_failures()
        # 硬零必须**不**触发（它不在 web_ui 下），棘轮必须触发
        hard_zero_hit = any(marker in line for line in failures if "web_ui 层" in line)
        ratchet_hit = any(marker in line for line in failures if line.strip().startswith("+"))
        ok = (not hard_zero_hit) and ratchet_hit
        rc = 0 if ok else 1
        if ok:
            print("✅ 反方向自证通过：web_ui 外的未定义名字由棘轮捕获（且不误判为硬零）")
        else:
            print(
                f"❌ 反方向自证失败：ratchet_hit={ratchet_hit} "
                f"hard_zero_misclassified={hard_zero_hit}"
            )
    finally:
        if probe.exists():
            probe.unlink()
        if probe.exists():
            print("‼️  探针未删除，请手动清理：", _rel(str(probe)))
            rc = 1
    return rc


def main() -> int:
    ap = argparse.ArgumentParser(description="未定义名字（F821）守卫")
    ap.add_argument("--strict", action="store_true", help="严格模式（默认行为）")
    ap.add_argument("--update-baseline", action="store_true", help="用当前扫描结果刷新存量清单")
    ap.add_argument("--self-test", action="store_true", help="自证守卫有区分度")
    ap.add_argument("--exercise-hard-zero", action="store_true", help="行为自证：真实注入后必须失败")
    ap.add_argument("--exercise-ratchet", action="store_true", help="反方向自证：web_ui 外的注入必须由棘轮捕获")
    args = ap.parse_args()

    if args.update_baseline:
        return update_baseline()
    if args.self_test:
        return self_test()
    if args.exercise_hard_zero:
        return exercise_hard_zero()
    if args.exercise_ratchet:
        return exercise_ratchet()
    return check()


if __name__ == "__main__":
    sys.exit(main())
