#!/usr/bin/env python3
"""守卫 webio 页面的静态资源前缀 —— 别再让多段路径把 `/js/...` 拽成 `/learning/js/...`。

================================================================================
它解决什么问题
================================================================================

PyWebIO 渲染页面骨架（``pywebio/platform/page.py::render_page``）时：

    cdn is True   → base_url = jsdelivr CDN
    cdn 为假      → base_url = ''          ← 模板里资源变成**相对路径**
    cdn 为字符串  → base_url = cdn.rstrip('/') + '/'

``cdn=False`` 时 ``platform/tpl/index.html`` 输出的是

    <script src="js/pywebio.min.js?v=1.8.4"></script>   ← 没有前导斜杠

浏览器按**当前 URL 的目录**解析它：

    urljoin('/health',       'js/pywebio.min.js') → '/js/pywebio.min.js'          ✅
    urljoin('/learning/list','js/pywebio.min.js') → '/learning/js/pywebio.min.js' ❌

而 naja 的静态路由只注册在根下（``routes.py`` 的 ``/js/``、``/css/``、``/codemirror/``、
``/image/``，走 ``tornado.web.StaticFileHandler``）。于是**路径深度 ≥2 的页面**首屏
``pywebio.min.js`` 全 404 → ``WebIO`` 未定义 → 整页白屏/报错。

真实踩过（2026-10-14）：``/learning/list`` 报错，服务端 ``200``、**日志里没有 traceback**
（错误全在前端），只有一串 ``404 GET /learning/js/*.js``；``/health`` 却正常，因为它只有一段。
这个 bug 会随「谁再挂一个多段路由」复发，所以钉死成守卫。

================================================================================
核心不变量
================================================================================

**对每条 webio 页面路由、每个静态资源引用：按浏览器规则 ``urljoin(route, ref)`` 解析后，
落点必须仍在已注册的静态路由前缀之内。**

只有满足它，页面首屏才拿得到 ``pywebio.min.js``。注意 ``cdn=False`` 在**单段**路由上
恰好成立（``/health`` + ``js/x`` = ``/js/x``），在多段路由上必然不成立 —— 这正是"看起来
一直没事、加了子路径就炸"的原因，也是守卫必须逐路由枚举而不是抽查的原因。

================================================================================
四段检查
================================================================================

  ① 源码取值 —— ``create_handlers`` 里 ``cdn_url`` 的默认分支必须是非假字符串
  ② 全文件干净 —— 不允许出现 ``webio_handler(..., cdn=False/None/'')``
  ③ 行为渲染 —— 用真实 ``render_page`` 渲染，逐资源、逐路由做上述 urljoin 判定
  ④ 自证区分度 —— 换成 ``cdn=False`` 重跑判定，**必须**报出违约；否则守卫已失灵

================================================================================
用法
================================================================================

    python3 -m scripts.verify.verify_webio_static_prefix            # 报告模式
    python3 -m scripts.verify.verify_webio_static_prefix --strict   # 违约退出码 1
"""

import argparse
import ast
import os
import re
import sys
from urllib.parse import urljoin

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)

ROUTES_PY = os.path.join(REPO, "deva", "naja", "web_ui", "routes.py")

# 从模板里能抠出来的资源引用（data: 内联资源不算）
RES_RE = re.compile(r'(?:src|href)="([^"]+)"')
# (r'/xx/(.*)', StaticFileHandler, ...)  —— 根路径静态路由前缀
STATIC_ROUTE_RE = re.compile(r"\(r'(/[A-Za-z0-9_\-]+/)\(\.\*\)'\s*,\s*StaticFileHandler")
# (r'/xxx', webio_handler(...)) —— pywebio 页面路由
WEBIO_ROUTE_RE = re.compile(r"\(r'([^']+)',\s*webio_handler\(")
# create_handlers 里的 cdn 默认值
CDN_DEFAULT_RE = re.compile(r"cdn_url\s*=\s*cdn\s+if\s+cdn\s+is\s+not\s+None\s+else\s+(.+)$", re.M)
# 明显的 falsy 字面量
FALSY_CDN_RE = re.compile(r"webio_handler\([^)]*cdn\s*=\s*(False|None|''|\"\")")

DEFAULT_PREFIXES = ["/js/", "/css/", "/codemirror/", "/image/"]


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def parse_cdn_default(src):
    """返回 (原始表达式文本, Python 值)。"""
    m = CDN_DEFAULT_RE.search(src)
    if not m:
        return None, None
    expr = m.group(1).strip()
    try:
        value = ast.literal_eval(expr)
    except Exception:
        value = expr  # 非字面量，原样返回供人工判断
    return expr, value


def collect_routes(src):
    return {
        "static_prefixes": sorted(set(STATIC_ROUTE_RE.findall(src))) or DEFAULT_PREFIXES,
        "webio_routes": sorted(set(WEBIO_ROUTE_RE.findall(src))),
    }


def render_assets(cdn_value):
    """用真实 render_page 渲染一次，返回静态资源引用原样列表。"""
    from pywebio.platform.page import render_page

    def _app():
        pass

    html = render_page(_app, protocol="ws", cdn=cdn_value).decode("utf-8")
    return [ref for ref in RES_RE.findall(html) if not ref.startswith("data:")]


def _is_absolute(ref):
    return ref.startswith("/") or ref.startswith("http://") or ref.startswith("https://")


def diff_route_assets(routes, assets, prefixes):
    """逐路由判定：相对资源 urljoin 后的落点是否掉出已注册静态前缀。

    Returns:
        {route: [(原始引用, 解析后路径), ...]} —— 只含**落点不合法**（必然 404）的。
        单段路由上 cdn=False 的良性改写（``/health`` + ``js/x`` → ``/js/x``）不会入选。
    """
    bad = {}
    for route in routes:
        hits = []
        for ref in assets:
            if _is_absolute(ref):
                continue  # 绝对地址不受当前路径影响
            resolved = urljoin(route, ref)
            if not any(resolved.startswith(p) for p in prefixes):
                hits.append((ref, resolved))
        if hits:
            bad[route] = hits
    return bad


def find_violations(cdn_value, routes, assets):
    """给定 cdn 取值与渲染结果，返回违约列表（④ 段拿它跑反向用例）。"""
    v = []
    prefixes = routes["static_prefixes"]

    if not cdn_value:
        v.append(f"cdn 默认值 {cdn_value!r} 为假 → render_page 的 base_url 为空串，模板输出相对路径")
    elif not isinstance(cdn_value, str):
        v.append(f"cdn 默认值 {cdn_value!r} 不是字符串，render_page 只认 True/False/str，走不到绝对路径分支")

    # 相对资源本身就不安全：只要有任一多段路由，它就会被改写
    relative = [r for r in assets if not _is_absolute(r)]
    if relative:
        v.append(f"渲染出 {len(relative)} 个相对路径资源（例 {relative[:2]}），会按当前 URL 目录解析")

    for route, hits in diff_route_assets(routes["webio_routes"], assets, prefixes).items():
        ref, resolved = hits[0]
        v.append(f"路由 {route} 上 {ref!r} 会解析成 {resolved!r}，掉出静态路由 {prefixes}")

    # 绝对资源也得落在已注册前缀里（防有人把 StaticFileHandler 挪走）
    for ref in assets:
        if ref.startswith("/") and not any(ref.startswith(p) for p in prefixes):
            v.append(f"资源 {ref!r} 不落在任何已注册静态路由 {prefixes} 下（StaticFileHandler 被挪了？）")
    return v


def main():
    parser = argparse.ArgumentParser(description="校验 webio 页面静态资源前缀")
    parser.add_argument("--strict", action="store_true", help="存在违约时以退出码 1 结束")
    args = parser.parse_args()

    violations = []
    src = _read(ROUTES_PY)
    routes = collect_routes(src)

    print("=" * 78)
    print("① 源码取值 —— create_handlers 里 cdn_url 的默认分支")
    print("=" * 78)
    expr, cdn_value = parse_cdn_default(src)
    print(f"  cdn_url = cdn if cdn is not None else {expr}")
    print(f"  解析后的默认值 : {cdn_value!r}   非假: {'✓' if cdn_value else '✗'}   字符串: {isinstance(cdn_value, str)}")
    if expr is None:
        violations.append("routes.py 里找不到 `cdn_url = cdn if cdn is not None else ...`，守卫需要更新")

    print()
    print("=" * 78)
    print("② 全文件干净 —— 没有把 cdn 写死成假值")
    print("=" * 78)
    falsy = FALSY_CDN_RE.findall(src)
    print(f"  webio_handler(..., cdn=False/None/'') 命中数: {len(falsy)}")
    if falsy:
        violations.append(f"routes.py 里存在 cdn 写死为假值的 webio_handler: {falsy[:3]}")

    print()
    print("=" * 78)
    print("③ 行为渲染 —— 真实 render_page + 逐路由 urljoin")
    print("=" * 78)
    print(f"  已注册静态路由前缀 : {routes['static_prefixes']}")
    print(f"  webio 页面路由数   : {len(routes['webio_routes'])}")
    multi = [r for r in routes["webio_routes"] if r.count("/") >= 2]
    print(f"  多段路由（深度≥2） : {multi if multi else '无'}")

    # cdn 为假时也照渲染：违约报告要能指出"到底哪几条路由被击穿"
    assets = render_assets(cdn_value) if cdn_value is not None else []
    print(f"  渲染出的静态资源   : {len(assets)} 个，例 {assets[:3]}")
    changed = diff_route_assets(routes["webio_routes"], assets, routes["static_prefixes"])
    print(f"  落点不合法的路由数 : {len(changed)}")
    for route, hits in list(changed.items())[:3]:
        print(f"      {route} → {hits[0][1]}")

    violations += find_violations(cdn_value, routes, assets)

    print()
    print("=" * 78)
    print("④ 自证区分度 —— 把 cdn 换成 False，判定函数必须报违约")
    print("=" * 78)
    bad_assets = render_assets(False)
    bad_v = find_violations(False, routes, bad_assets)
    print(f"  cdn=False 时资源前缀: {bad_assets[:2]}")
    print(f"  判定函数报出违约数  : {len(bad_v)}   （必须 >0）")
    if not bad_v:
        violations.append(
            "把 cdn 换成 False 后判定函数不报违约 → 守卫已失效（认不出真 bug），比没有守卫更危险"
        )
    if multi:
        bad_routes = diff_route_assets(multi, bad_assets, routes["static_prefixes"])
        print(f"  cdn=False 时被击穿的多段路由: {sorted(bad_routes)}   （必须覆盖 {multi}）")
        if not bad_routes:
            violations.append(f"cdn=False 时多段路由 {multi} 未被判定为击穿 → 用例无区分度")

    print()
    print("=" * 78)
    if violations:
        print(f"发现 {len(violations)} 处违约：")
        for i, v in enumerate(violations, 1):
            print(f"  {i}. {v}")
    else:
        print("全部通过：所有 webio 页面的静态资源都是绝对路径，多段路由不会再 404")
    print("=" * 78)

    if violations and args.strict:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
