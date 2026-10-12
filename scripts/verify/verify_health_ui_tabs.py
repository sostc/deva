#!/usr/bin/env python3
"""校验 /health 仪表盘的 tab 容器结构没被打散。

================================================================================
它解决什么问题
================================================================================

health_ui.render_health_dashboard() 把 tab 骨架铺在一次 put_html 里
（`<div id="tab-content"><div id="overview">`，刻意不闭合），面板内容铺在后续
若干次 put_html 里，最后才补 `</div>`。

PyWebIO 的每次 put_html 都是**独立 DOM 片段**插入 —— 片段里未闭合的标签会被
浏览器自动补闭合。于是：

    #tab-content  建成空壳，立刻收口
    #overview     建成空壳，立刻收口
    面板内容      全部掉到外面，成了 tab-content 的兄弟节点

表现是五个 tab 区块同时可见、纵向堆叠成一堵墙，而点 tab 只是在几个空 div 上
切 display，页面毫无变化。因为没有任何异常抛出，这种失效**日志里看不见**。

修法是 BufferedRenderContext：把面板产出的片段全部攒起来，最后合成一份完整
HTML 只调一次 put_html。本脚本就是这条不变量的守卫。

================================================================================
四段检查
================================================================================

  ① 输出次数 —— 面板内容必须落在**一次** put_html 里（多次即标签配对会被打断）
  ② 标签配对 —— 拼好的文档不允许有未闭合标签或错配的闭合标签
  ③ 父子关系 —— #tab-content 的直接子元素必须恰好是五个 tab 容器，
               且容器本身的直接子元素也就是每个 tab 容器的父节点是 tab-content
  ④ 内容非空 —— 五个容器都得有内容，且 showTab 由 run_js 定义

================================================================================
用法
================================================================================

    python3 -m scripts.verify.verify_health_ui_tabs            # 报告模式
    python3 -m scripts.verify.verify_health_ui_tabs --strict   # 违约退出码 1
"""

import argparse
import asyncio
import os
import sys
from html.parser import HTMLParser

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

TAB_IDS = ("overview", "system", "performance", "loop", "tuning")

# 不需要闭合的空元素标签
VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}


class _StructureProbe(HTMLParser):
    """把 HTML 解析成一棵带 id / 父子关系的树，供结构断言使用。"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []          # [(tag, attrs_dict)]
        self.unclosed = []       # 文档结束时还开着的 [(tag, line)]
        self.mismatches = []     # 闭合标签与栈顶不符 [msg]
        self.parent_of = {}      # id -> 父 tag  id
        self.child_count = {}    # id -> 直接子元素个数

    # -- 树构建 ---------------------------------------------------------
    @staticmethod
    def _nearest_named_ancestor(stack):
        """栈里最近一个有 id 的祖先节点 id（没有则返回 None）。"""
        for i in range(len(stack) - 1, -1, -1):
            if stack[i][1].get("id"):
                return stack[i][1]["id"]
        return None

    def handle_starttag(self, tag, attrs):
        attrs = {k: (v if v is not None else "") for k, v in attrs}
        if tag in VOID_TAGS:
            return
        parent_id = self._nearest_named_ancestor(self.stack)
        node_id = attrs.get("id")
        if node_id:
            self.parent_of[node_id] = parent_id
        if parent_id:
            self.child_count[parent_id] = self.child_count.get(parent_id, 0) + 1
        self.stack.append((tag, attrs))

    def handle_startendtag(self, tag, attrs):
        # <div /> 这种自闭合形式不计入栈，但仍算父容器的一个子元素
        parent_id = self._nearest_named_ancestor(self.stack)
        if parent_id:
            self.child_count[parent_id] = self.child_count.get(parent_id, 0) + 1

    def handle_endtag(self, tag):
        if tag in VOID_TAGS:
            return
        if not self.stack:
            self.mismatches.append(f"多余的 </{tag}> @行 {self.getpos()[0]}")
            return
        if self.stack[-1][0] != tag:
            self.mismatches.append(
                f"期望 </{self.stack[-1][0]}> 实得 </{tag}> @行 {self.getpos()[0]}"
            )
            # 向内找同名开标签，找不到就放弃本次闭合（避免栈雪崩）
            for i in range(len(self.stack) - 1, -1, -1):
                if self.stack[i][0] == tag:
                    del self.stack[i:]
                    return
            return
        self.stack.pop()

    def finish_document(self):
        self.unclosed = [(tag, self.stack and idx) for idx, (tag, _) in enumerate(self.stack)]
        self.unclosed = [(tag, pos) for tag, pos in self.unclosed if pos is not None]
        return self


class _FakeCtx(dict):
    """替身渲染上下文：记录所有调用，不真的往浏览器输出。"""

    def __init__(self):
        super().__init__()
        self.calls = []  # [(kind, payload)]
        self["init_naja_ui"] = self._init_naja_ui
        self["put_html"] = self._put_html
        self["run_js"] = self._run_js
        self["toast"] = lambda *a, **k: None

    async def _init_naja_ui(self, title):
        self.calls.append(("init_naja_ui", title))

    def _put_html(self, html):
        self.calls.append(("put_html", html))

    def _run_js(self, js):
        self.calls.append(("run_js", js))


def render_offline():
    """在无浏览器环境里渲染仪表盘，返回 (ctx, 报告列表)。"""
    from deva.naja.infra.observability import health_ui

    ctx = _FakeCtx()
    asyncio.run(health_ui.render_health_dashboard(ctx))
    return ctx


def main():
    parser = argparse.ArgumentParser(description="校验 /health 仪表盘的 tab 容器结构")
    parser.add_argument("--strict", action="store_true", help="存在违约时以退出码 1 结束")
    args = parser.parse_args()

    violations = []

    print("=" * 78)
    print("① 输出次数 —— 面板内容必须落在一次 put_html 里")
    print("=" * 78)

    ctx = render_offline()
    html_chunks = [p for k, p in ctx.calls if k == "put_html"]
    js_chunks = [p for k, p in ctx.calls if k == "run_js"]

    print(f"  调用序列        : {[k for k, _ in ctx.calls]}")
    print(f"  put_html 次数   : {len(html_chunks)}   （期望 1）")
    print(f"  run_js 次数     : {len(js_chunks)}     （期望 ≥1，用于定义 showTab）")

    if len(html_chunks) != 1:
        violations.append(
            f"面板内容被拆进了 {len(html_chunks)} 次 put_html，"
            f"跨调用的未闭合标签会被浏览器自动补闭合，tab 容器将塌陷为兄弟节点"
        )
    if not js_chunks or not any("showTab" in js for js in js_chunks):
        violations.append("run_js 里没有定义 showTab，tab 按钮点了不会有反应")

    if not html_chunks:
        print("\n  ✗ 完全没有产出 HTML，后续检查跳过")
        _report(violations, args)
        return

    doc = html_chunks[0]
    print(f"  文档长度        : {len(doc)} 字符")

    # ── ② 标签配对 ────────────────────────────────────────────────────
    print()
    print("=" * 78)
    print("② 标签配对 —— 拼好的文档必须结构良好")
    print("=" * 78)

    probe = _StructureProbe()
    probe.feed(doc)
    probe.finish_document()

    print(f"  未闭合标签      : {probe.unclosed if probe.unclosed else '无'}")
    print(f"  闭合错配        : {probe.mismatches if probe.mismatches else '无'}")

    if probe.unclosed:
        violations.append(f"存在未闭合标签: {probe.unclosed}")
    if probe.mismatches:
        violations.append(f"存在闭合错配: {probe.mismatches[:3]}")

    # ── ③ 父子关系 ────────────────────────────────────────────────────
    print()
    print("=" * 78)
    print("③ 父子关系 —— #tab-content 的直接子元素必须恰好是五个 tab 容器")
    print("=" * 78)

    children_of_tab_content = [
        tid for tid, parent in probe.parent_of.items() if parent == "tab-content"
    ]
    print(f"  tab-content 直接子元素 : {sorted(children_of_tab_content)}")

    missing = [t for t in TAB_IDS if t not in children_of_tab_content]
    extra = [t for t in children_of_tab_content if t not in TAB_IDS]
    if missing:
        violations.append(f"以下 tab 容器不再直接挂在 #tab-content 下: {missing}")
    if extra:
        violations.append(f"#tab-content 下出现了预期外的一级容器: {extra}")
    # 只出现一次的 id（重复 id 会让 getElementById 取错节点）
    for tid in TAB_IDS:
        n = doc.count(f'id="{tid}"')
        print(f"  {tid:12s} id 出现 {n} 次，父节点={probe.parent_of.get(tid)}，子元素数={probe.child_count.get(tid, 0)}")
        if n != 1:
            violations.append(f"#{tid} 的 id 出现了 {n} 次（应恰好 1 次）")

    # ── ④ 内容非空 ────────────────────────────────────────────────────
    print()
    print("=" * 78)
    print("④ 内容非空 —— 五个容器都得装了东西")
    print("=" * 78)

    for tid in TAB_IDS:
        n = probe.child_count.get(tid, 0)
        mark = "✓" if n > 0 else "✗"
        print(f"  {mark} {tid:12s} 直接子元素数 = {n}")
        if n == 0:
            violations.append(f"#{tid} 是空容器（0 个子元素）")

    _report(violations, args)


def _report(violations, args):
    print()
    print("=" * 78)
    if violations:
        print(f"发现 {len(violations)} 处违约：")
        for i, v in enumerate(violations, 1):
            print(f"  {i}. {v}")
    else:
        print("全部通过：tab 结构完好")
    print("=" * 78)

    if violations and args.strict:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
