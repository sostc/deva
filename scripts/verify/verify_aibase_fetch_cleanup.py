#!/usr/bin/env python3
"""验证「AIbase 抓取函数的作用域完整」—— finally 清理块不得引用未定义名。

================================================================================
它解决什么问题
================================================================================
`execute()` 里日志反复出现：::

    [AI_Report_v2] AIbase处理失败: name 'asyncio' is not defined

表现在「AIbase 日报学习一直没跑成」，根因是**作用域错配**：

    fetch_aibase_articles_list()
    fetch_aibase_daily_playwright()

两个 async 函数体内只写了 ``import asyncio as async_lib``（带别名），
但收尾的 ``finally`` 清理块却写成裸 ``asyncio.wait_for(...)`` / ``asyncio.TimeoutError``。
模块顶部**没有** ``import asyncio``，于是：

  * ``finally`` 一执行就抛 ``NameError``；
  * 该 ``NameError`` 把**正常返回值一起顶掉**（``articles`` / ``result_data`` 全丢）；
  * 调用方 ``except Exception`` 兜住，只留一行 "AIbase处理失败" —— **静默失效**；
  * 附带效应：``context.close()`` / ``browser.close()`` 从未执行 → 有泄漏风险。

注意：这不是"某个字打错了"，而是**「按名字取符号」却没核对作用域**这一类。
所以守卫按**类**来守，而不是只盯这两个函数。

================================================================================
四段检查
================================================================================
  ① 静态（全仓）：函数内 ``import asyncio as X`` 后，同函数内不得裸用 ``asyncio``
     （除非该函数自身或模块层另行绑定了 ``asyncio``）
  ② 静态：两个 AIbase 抓取函数的 ``finally`` 清理块引用了 ``async_lib``、不再出现裸 ``asyncio``
  ③ 行为：mock 掉 playwright，实跑 ``fetch_aibase_articles_list`` →
     不抛 NameError、返回列表、``context.close()`` / ``browser.close()`` **真的被调用**
  ④ 行为：mock 下 ``context.close()`` 抛 ``TimeoutError`` 时走 force 分支且不外泄异常

================================================================================
用法
================================================================================

    cd <项目根>
    /Users/spark/.local/bin/python3 scripts/verify/verify_aibase_fetch_cleanup.py
    /Users/spark/.local/bin/python3 scripts/verify/verify_aibase_fetch_cleanup.py --strict

退出码：0 = PASS；--strict 下有违约则 1。

**只读约定**：只读源码、只在内存里 mock、不联网、不起浏览器、不写任何持久文件。
"""

from __future__ import annotations

import argparse
import ast
import asyncio
import sys
import types
import warnings
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REPORT_SRC = REPO_ROOT / "deva" / "naja" / "tasks" / "ai_daily_report.py"

TARGET_FUNCS = ("fetch_aibase_articles_list", "fetch_aibase_daily_playwright")

violations: list[str] = []
total = 0


def check(label: str, ok: bool, detail: str = "") -> bool:
    global total
    total += 1
    mark = "✅" if ok else "❌"
    print(f"{mark} {label}" + (f"  —— {detail}" if detail else ""))
    if not ok:
        violations.append(f"{label}  {detail}")
    return ok


# ─────────────────────────────────────────────────────────────────────────────
# ① 静态：全仓扫「别名 import 后裸用」
# ─────────────────────────────────────────────────────────────────────────────
def _bound_names(fn: ast.AST) -> set[str]:
    """函数体内**自身**绑定的名字（import / 赋值 / 参数 / for / with / 推导式 / except / global）。"""
    names: set[str] = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Import):
            for a in node.names:
                names.add((a.asname or a.name).split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                if a.name != "*":
                    names.add(a.asname or a.name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            names.add(node.id)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            names.update(node.names)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
    return names


def _module_binds_asyncio(tree: ast.Module) -> bool:
    for node in tree.body:
        if isinstance(node, ast.Import) and any(a.name == "asyncio" for a in node.names):
            return True
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "asyncio":
                    return True
    return False


def scan_alias_scope(root: Path) -> list[str]:
    """全仓找「函数内 import asyncio as X，同函数内却裸用 asyncio」的地方。"""
    hits: list[str] = []
    for p in sorted(root.rglob("*.py")):
        if any(part in ("__pycache__", ".git", "node_modules", ".venv") for part in p.parts):
            continue
        try:
            # 全仓扫描会碰到非本守卫负责的文件（如 simhash.py 的 '\w' 非 raw 串），
            # 它们的 SyntaxWarning 与本检查无关，这里静音，免得污染输出。
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", SyntaxWarning)
                tree = ast.parse(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if _module_binds_asyncio(tree):
            continue  # 模块层已绑定 asyncio，裸用合法
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            aliases = {
                a.asname
                for n in ast.walk(fn)
                if isinstance(n, ast.Import)
                for a in n.names
                if a.name == "asyncio" and a.asname
            }
            if not aliases:
                continue
            if "asyncio" in _bound_names(fn):
                continue  # 函数内另有绑定（如裸 import asyncio），合法
            for n in ast.walk(fn):
                if isinstance(n, ast.Name) and n.id == "asyncio" and isinstance(n.ctx, ast.Load):
                    rel = p.relative_to(root)
                    hits.append(f"{rel}:{n.lineno} ({fn.name})")
    return hits


# ─────────────────────────────────────────────────────────────────────────────
# ② 静态：两个 AIbase 函数的 finally 块
# ─────────────────────────────────────────────────────────────────────────────
def _func_body_src(fn_name: str) -> str:
    tree = ast.parse(REPORT_SRC.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == fn_name:
            return ast.get_source_segment(REPORT_SRC.read_text(encoding="utf-8"), node) or ""
    return ""


# ─────────────────────────────────────────────────────────────────────────────
# ③ / ④ 行为：mock playwright 实跑
# ─────────────────────────────────────────────────────────────────────────────
class _FakePage:
    def __init__(self) -> None:
        self.closed = False

    async def goto(self, *a, **kw):
        return None

    async def wait_for_load_state(self, *a, **kw):
        return None

    async def query_selector_all(self, *a, **kw):
        return []

    async def query_selector(self, *a, **kw):
        return None

    async def content(self):
        return "<html><body>2026年10月14日</body></html>"

    async def text_content(self):
        return ""

    async def get_attribute(self, *a, **kw):
        return None

    async def close(self, **kw):
        self.closed = True


class _FakeContext:
    def __init__(self) -> None:
        self.closed = False
        self.forced = False
        self.pages: list[_FakePage] = []

    async def new_page(self):
        pg = _FakePage()
        self.pages.append(pg)
        return pg

    async def close(self, **kw):
        if kw.get("force"):
            self.forced = True
            self.closed = True
            return
        self.closed = True


class _FakeBrowser:
    def __init__(self) -> None:
        self.closed = False
        self.forced = False
        self.ctx = _FakeContext()

    async def new_context(self, **kw):
        return self.ctx

    async def close(self, **kw):
        if kw.get("force"):
            self.forced = True
        self.closed = True


class _FakeChromium:
    def __init__(self) -> None:
        self.browser = _FakeBrowser()

    async def launch(self, **kw):
        return self.browser


class _FakePlaywright:
    def __init__(self) -> None:
        self.chromium = _FakeChromium()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class _SlowCloseContext(_FakeContext):
    """close() 先超时，force=True 才成功 —— 走 except 分支。"""

    async def close(self, **kw):
        if kw.get("force"):
            self.forced = True
            self.closed = True
            return
        raise asyncio.TimeoutError("模拟 close 超时")


class _SlowCloseBrowser(_FakeBrowser):
    def __init__(self) -> None:
        super().__init__()
        self.ctx = _SlowCloseContext()

    async def close(self, **kw):
        if kw.get("force"):
            self.forced = True
            self.closed = True
            return
        raise asyncio.TimeoutError("模拟 close 超时")


def _install_fake_playwright(browser_cls=_FakeBrowser):
    saved = {k: sys.modules.get(k) for k in ("playwright", "playwright.async_api")}

    pkg = types.ModuleType("playwright")
    api = types.ModuleType("playwright.async_api")

    def _factory():
        pw = _FakePlaywright()
        pw.chromium = _FakeChromium()
        pw.chromium.browser = browser_cls()
        return pw

    api.async_playwright = _factory
    pkg.async_api = api
    sys.modules["playwright"] = pkg
    sys.modules["playwright.async_api"] = api
    return saved


def _restore(saved: dict):
    for k, v in saved.items():
        if v is None:
            sys.modules.pop(k, None)
        else:
            sys.modules[k] = v


async def _run_articles_list():
    from deva.naja.tasks.ai_daily_report import fetch_aibase_articles_list

    return await fetch_aibase_articles_list(days_back=7)


async def _run_daily_playwright():
    from deva.naja.tasks.ai_daily_report import fetch_aibase_daily_playwright

    return await fetch_aibase_daily_playwright()


async def _run_with_slow_close():
    from deva.naja.tasks.ai_daily_report import fetch_aibase_articles_list

    return await fetch_aibase_articles_list(days_back=7)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--strict", action="store_true", help="有违约则退出码 1")
    args = ap.parse_args()

    print("=" * 68)
    print("① 静态（全仓）：别名 import 后不得裸用 asyncio")
    print("=" * 68)
    hits = scan_alias_scope(REPO_ROOT)
    check(
        "全仓无「import asyncio as X 却裸用 asyncio」",
        not hits,
        "命中: " + ", ".join(hits) if hits else "0 处",
    )

    print()
    print("=" * 68)
    print("② 静态：AIbase 抓取函数的 finally 清理块")
    print("=" * 68)
    for fn_name in TARGET_FUNCS:
        src = _func_body_src(fn_name)
        check(f"{fn_name} 存在且可解析", bool(src), "找到函数体" if src else "未找到")
        if not src:
            continue
        # finally 块内不应出现「裸 asyncio」
        bare = [ln for ln in src.splitlines() if "asyncio." in ln and "async_lib" not in ln]
        # 排除函数开头的 import 行
        bare = [ln for ln in bare if not ln.strip().startswith("import ")]
        check(
            f"{fn_name} 无裸 asyncio 引用",
            not bare,
            "残留: " + " | ".join(s.strip() for s in bare[:3]) if bare else "全部走 async_lib",
        )
        check(
            f"{fn_name} 的 close 清理走 async_lib.wait_for",
            "async_lib.wait_for(context.close()" in src
            and "async_lib.wait_for(browser.close()" in src,
            "context/browser 均用 async_lib",
        )
        check(
            f"{fn_name} 的 timeout 捕获走 async_lib.TimeoutError",
            "except async_lib.TimeoutError:" in src,
            "两处 except 均用 async_lib",
        )

    print()
    print("=" * 68)
    print("③ 行为：mock playwright 实跑，finally 不再抛 NameError")
    print("=" * 68)
    saved = _install_fake_playwright(_FakeBrowser)
    try:
        try:
            articles = asyncio.run(_run_articles_list())
            check("fetch_aibase_articles_list 正常返回（无 NameError）", True, f"返回 {type(articles).__name__}")
            check("fetch_aibase_articles_list 返回类型为 list", isinstance(articles, list), f"{articles!r}")
        except NameError as e:
            check("fetch_aibase_articles_list 正常返回（无 NameError）", False, f"NameError: {e}")
        except Exception as e:
            check("fetch_aibase_articles_list 正常返回（无 NameError）", False, f"{type(e).__name__}: {e}")

        try:
            daily = asyncio.run(_run_daily_playwright())
            check("fetch_aibase_daily_playwright 正常返回（无 NameError）", True, f"返回 {type(daily).__name__}")
            check(
                "fetch_aibase_daily_playwright 返回 dict 且带 success 键",
                isinstance(daily, dict) and "success" in daily,
                f"{str(daily)[:60]}",
            )
        except NameError as e:
            check("fetch_aibase_daily_playwright 正常返回（无 NameError）", False, f"NameError: {e}")
        except Exception as e:
            check("fetch_aibase_daily_playwright 正常返回（无 NameError）", False, f"{type(e).__name__}: {e}")
    finally:
        _restore(saved)

    print()
    print("=" * 68)
    print("④ 行为：close 超时走 force 分支且不外泄")
    print("=" * 68)
    saved = _install_fake_playwright(_SlowCloseBrowser)
    try:
        try:
            asyncio.run(_run_with_slow_close())
            check("close 超时后仍正常返回（异常被 async_lib.TimeoutError 捕获）", True, "未外泄")
        except NameError as e:
            check("close 超时后仍正常返回（异常被 async_lib.TimeoutError 捕获）", False, f"NameError: {e}")
        except asyncio.TimeoutError as e:
            check("close 超时后仍正常返回（异常被 async_lib.TimeoutError 捕获）", False, f"TimeoutError 外泄: {e}")
        except Exception as e:
            check("close 超时后仍正常返回（异常被 async_lib.TimeoutError 捕获）", False, f"{type(e).__name__}: {e}")
    finally:
        _restore(saved)

    print()
    print("=" * 68)
    if violations:
        print(f"❌ 违约 {len(violations)}/{total} 项:")
        for v in violations:
            print(f"   - {v}")
        return 1 if args.strict else 0
    print(f"✅ 全部通过（{total} 项）：AIbase 抓取函数作用域完整，finally 不再静默失效")
    return 0


if __name__ == "__main__":
    sys.exit(main())
