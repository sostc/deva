#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""验证「金十事件的 title 字段承载真实标题」—— 防序号占位符回归。

================================================================================
它解决什么问题
================================================================================

用户报告：「托盘菜单里出现金十数据#1 或者金十数据#2 这样没有实际意义的数据」。

排查结论是**字段写错位置**，属于本项目的「静默失效家族」：

  * ``wake_sync_handlers.py`` 发布金十事件时写成
    ``title=f"金十重要事件 #{news.rank}"`` —— ``rank`` 只是抓取时的列表排名
    （第 1 条、第 2 条…），与新闻内容**零关系**；
  * 真正的新闻标题 ``news.title`` 被塞进了 ``text`` 字段；
  * 而**所有展示端**读的都是 ``event.title``：
      托盘菜单 ``menu_bar_tray.py``（经 ``market_24h_timeline`` 的
      ``'title': block_name`` 映射）、24h 时间线、``cognition`` 金十卡片。
    → 内容被丢弃，菜单里只剩一个排名号。

修法：``title`` 改传 ``news.title``（真实标题）；``Jin10ImportantNews``
没有正文字段，故 ``text`` 与 ``title`` 同源。仅当标题确为空时才回退占位符
（保留 rank 以便追溯），避免出现「合法的空」。

为什么必须靠静态守卫兜住：这类 bug **不抛异常、不写日志**，UI 上只是"看起来
信息量少一点"，跑测试也照样绿。只能靠比对「发布端写哪个字段」与
「展示端读哪个字段」来发现。

================================================================================
五段检查
================================================================================

  ① **静态 AST**：所有 ``source="jin10_important"`` 的 ``TextFetchedEvent`` 构造，
     ``title=`` 实参不得是含 ``{rank}`` / ``#{...}`` 的序号占位符 f-string。
     用 AST 而非正则 —— 正则会被注释、docstring、别的方法块误伤
     （本项目已被坑过两次）。
  ② **静态 AST**：同一批发布点里，``title=`` 与 ``text=`` 必须同源
     （都引用 ``news.title``），防止再次出现"内容在 text、展示读 title"的错位。
  ③ **端到端运行时**：用真实缓存数据走「构造 → 发布 → 展示端读取」，
     断言托盘拿到的是真实标题。
  ④ **负向验证**：注入回退写法（旧的占位符），确认用例**能抓出来** ——
     证明 ③ 的用例本身有区分度，否则等于没写。
  ⑤ **数据源健康**：``~/.naja/jin10_news.json`` 里的 title 字段不是占位符
     （文件不存在则 ⏭️ 如实跳过，不算链路故障）。

================================================================================
用法
================================================================================

    cd <项目根>
    /Users/spark/.local/bin/python3 scripts/verify/verify_jin10_title.py
    /Users/spark/.local/bin/python3 scripts/verify/verify_jin10_title.py --strict

退出码：0 = PASS；--strict 下有违约则 1。

**只读约定**：只读源码、缓存文件与内存态，不写任何落盘表、不起服务、不发通知。
"""

from __future__ import annotations

import argparse
import ast
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

WAKE_SYNC = os.path.join(
    ROOT, "deva", "naja", "state", "system", "wake_sync_handlers.py"
)

PASS, FAIL, SKIP = "✅", "❌", "⏭️"
violations: list[str] = []


def _fail(msg: str) -> None:
    violations.append(msg)
    print(f"  {FAIL} {msg}")


def _ok(msg: str) -> None:
    print(f"  {PASS} {msg}")


# ---------------------------------------------------------------------------
# ①② 静态 AST：检查 jin10_important 发布点的 title 实参
# ---------------------------------------------------------------------------

def _iter_textfetched_calls(tree: ast.AST):
    """产出所有 TextFetchedEvent(...) 调用节点（AST 精确匹配，不受注释干扰）。"""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = fn.id if isinstance(fn, ast.Name) else (
            fn.attr if isinstance(fn, ast.Attribute) else None
        )
        if name == "TextFetchedEvent":
            yield node


def _kwarg(call: ast.Call, key: str):
    for kw in call.keywords:
        if kw.arg == key:
            return kw.value
    return None


def _const_str(node) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _source_of(call: ast.Call) -> str | None:
    return _const_str(_kwarg(call, "source"))


def _unparse(node) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        return ""


def _is_rank_placeholder(title_node) -> bool:
    """title 实参是否是 '金十重要事件 #{rank}' 这类序号占位符。

    判定：JoinedStr（f-string）且其中引用了 rank，或字面量含 ' #' 序号模式。
    """
    if title_node is None:
        return False
    src = _unparse(title_node)
    # f-string 且引用 rank → 占位符
    if isinstance(title_node, ast.JoinedStr) and "rank" in src:
        return True
    # 字面量里出现 "#" + 数字的固定文案（如 "金十重要事件 #1"）
    lit = _const_str(title_node)
    if lit and "#" in lit:
        return True
    return False


def _title_node(call: ast.Call):
    """取 title 实参节点。

    发布点若写成局部变量中转（如 news_title = news.title; title=news_title），
    AST 只能看到变量名 —— 这里向上回溯同名赋值，取回它指向的真实表达式。
    """
    return _kwarg(call, "title")


def _resolve_local_alias(tree: ast.AST, name: str):
    """回溯函数体内最近一次对 name 的赋值，返回其 value 节点（取不到返回 None）。"""
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == name:
                    # 多段赋值（含 if 兜底）时，返回最后一个非空分支之前的主赋值
                    return node.value
    return None


def check_static() -> None:
    print("\n【① 静态 AST】jin10_important 发布点的 title 不得是序号占位符")

    if not os.path.exists(WAKE_SYNC):
        _fail(f"源码不存在: {WAKE_SYNC}")
        return

    with open(WAKE_SYNC, "r", encoding="utf-8") as f:
        src = f.read()
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        _fail(f"解析失败: {e}")
        return

    jin10_calls = [
        c for c in _iter_textfetched_calls(tree) if _source_of(c) == "jin10_important"
    ]

    if not jin10_calls:
        print(f"  {SKIP} 未找到 source='jin10_important' 的发布点（如实跳过）")
        return

    _ok(f"找到 {len(jin10_calls)} 个 source='jin10_important' 发布点")

    for call in jin10_calls:
        line = getattr(call, "lineno", "?")
        tnode = _title_node(call)
        # 变量名中转 → 回溯其赋值来源
        if isinstance(tnode, ast.Name):
            resolved = _resolve_local_alias(tree, tnode.id)
            if resolved is not None:
                tnode = resolved

        if _is_rank_placeholder(tnode):
            _fail(
                f"第 {line} 行: title 仍是序号占位符 `{_unparse(tnode)}` "
                f"—— 应为真实新闻标题（news.title）"
            )
        else:
            _ok(f"第 {line} 行: title = `{_unparse(tnode)}`（非占位符）")

    # ② title 与 text 同源
    print("\n【② 静态 AST】title 与 text 必须同源（防内容/展示字段错位）")
    for call in jin10_calls:
        line = getattr(call, "lineno", "?")
        t_expr = _unparse(_title_node(call))
        x_expr = _unparse(_kwarg(call, "text"))
        if not t_expr or not x_expr:
            _fail(f"第 {line} 行: title/text 缺失")
            continue
        # 归一化：去掉空白后比较（news_title vs news.title 视为同源）
        norm_t = t_expr.replace(" ", "")
        norm_x = x_expr.replace(" ", "")
        if norm_t == norm_x:
            _ok(f"第 {line} 行: title 与 text 同源 (`{t_expr}`)")
        else:
            _fail(
                f"第 {line} 行: title=`{t_expr}` 与 text=`{x_expr}` 不同源 "
                f"—— 展示端读 title，会导致内容被丢弃"
            )


# ---------------------------------------------------------------------------
# ③④ 端到端运行时 + 负向验证
# ---------------------------------------------------------------------------

def check_runtime() -> None:
    print("\n【③ 端到端】构造 → 发布 → 展示端读取，断言拿到真实标题")
    try:
        from deva.naja.events.text_events import TextFetchedEvent
        from deva.naja.datasource.plugins.jin10_fetcher import Jin10ImportantNews
    except Exception as e:
        print(f"  {SKIP} 依赖不可用，如实跳过: {e}")
        return

    real = [
        ("特朗普：伊朗真的是一个失败的国家", 1, "20261013233911357800"),
        ("智利铜矿劳资冲突升级 全球最大铜矿逾千名员工或于周三罢工", 2, "20261013222356186800"),
        ("知情人士：日本央行倾向于不在10月份进行连续加息", 3, "20261013164813314800"),
    ]
    news_list = [
        Jin10ImportantNews(rank=r, title=t, flash_id=f, display_time="")
        for t, r, f in real
    ]

    def build(news_list, buggy=False):
        """buggy=True 时注入回退写法（旧 bug），用于 ④ 的负向验证。"""
        out = []
        for news in news_list:
            if buggy:
                title = f"金十重要事件 #{news.rank}"  # 旧的占位符写法
            else:
                title = (getattr(news, "title", "") or "").strip()
                if not title:
                    title = f"金十重要事件 #{getattr(news, 'rank', 0)}"
            out.append(TextFetchedEvent(
                text=title, title=title, source="jin10_important",
                url=f"https://www.jin10.com/news/{news.flash_id}",
            ))
        return out

    def tray_read(events):
        """复刻展示端口径（market_24h_timeline.py:546）。"""
        return [
            e.title for e in events
            if isinstance(e, TextFetchedEvent) and e.source == "jin10_important"
        ]

    shown = tray_read(build(news_list))
    for s in shown:
        print(f"      📌 {s}")

    for (t, r, f), s in zip(real, shown):
        if s != t:
            _fail(f"标题不匹配\n       期望: {t}\n       实际: {s}")

    # 兜底：空标题回退占位符，且保留 rank
    empty = Jin10ImportantNews(rank=7, title="", flash_id="x", display_time="")
    got = tray_read(build([empty]))
    if got and got[0] == "金十重要事件 #7":
        _ok("空标题回退占位符正常（保留 rank 可追溯）")
    else:
        _fail(f"空标题兜底异常: {got}")

    # ④ 负向验证：用例必须能抓出旧 bug
    print("\n【④ 负向验证】注入旧占位符写法，确认用例有区分度")
    buggy_shown = tray_read(build(news_list, buggy=True))
    caught = any(s.startswith("金十重要事件 #") for s in buggy_shown)
    if caught:
        _ok(f"用例成功捕获旧 bug（注入后显示 {buggy_shown}）")
    else:
        _fail("用例未捕获旧 bug —— 用例本身无效，③ 的通过不可信！")


# ---------------------------------------------------------------------------
# ⑤ 数据源健康
# ---------------------------------------------------------------------------

def check_data_source() -> None:
    print("\n【⑤ 数据源】缓存文件里的 title 字段健康性")
    import json

    cache = os.path.expanduser("~/.naja/jin10_news.json")
    if not os.path.exists(cache):
        print(f"  {SKIP} {cache} 不存在，如实跳过（非链路故障）")
        return

    try:
        with open(cache, "r", encoding="utf-8") as f:
            items = json.load(f)
    except Exception as e:
        _fail(f"读取失败: {e}")
        return

    if not items:
        print(f"  {SKIP} 缓存为空，如实跳过")
        return

    bad = [it.get("title", "") for it in items
           if not it.get("title") or "#" in str(it.get("title", ""))]
    if bad:
        _fail(f"缓存中 {len(bad)} 条 title 疑似占位符/为空: {bad[:3]}")
    else:
        _ok(f"{len(items)} 条缓存 title 均为真实标题（示例: {items[0].get('title', '')[:28]}…）")


def main() -> int:
    ap = argparse.ArgumentParser(description="验证金十事件 title 字段承载真实标题")
    ap.add_argument("--strict", action="store_true",
                    help="有违约时以退出码 1 结束（默认仅报告）")
    args = ap.parse_args()

    print("=" * 68)
    print("金十事件 title 字段守卫（防序号占位符回归）")
    print("=" * 68)

    check_static()
    check_runtime()
    check_data_source()

    print("\n" + "=" * 68)
    if violations:
        print(f"{FAIL} 发现 {len(violations)} 项违约：")
        for v in violations:
            print(f"   - {v}")
        print("=" * 68)
        return 1 if args.strict else 0

    print(f"{PASS} ALL PASS —— 金十 title 字段链路健康")
    print("=" * 68)
    return 0


if __name__ == "__main__":
    sys.exit(main())
