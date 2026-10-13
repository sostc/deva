#!/usr/bin/env python3
"""验证「托盘信息聚焦」—— 新闻可见性 + 通知聚合 + 菜单结构。

================================================================================
它解决什么问题
================================================================================

用户问「托盘菜单里现在有哪些信息会过载」。排查后发现问题**不只是太多**，
而是「该多的多、该少的少」：

  * ``market_24h_timeline.get_timeline_data_for_api`` 用 ``all_events[:15]``
    只按时间硬截断，而 cn/us 板块异动是**秒级持续更新**的 → 时间戳永远最新
    → 永远霸占全部 15 个名额 → ``high_score_news`` / ``jin10_news`` **几乎永不进列表**。
  * 连带 ``_check_and_send_notifications``（只认新闻类、遍历同一列表）
    **实际永不触发** —— 典型「链路写了、数据不在同一条路上」的静默失效。
  * 菜单被平铺事件流撑到 ~40 项；4 个裸数字统计行（``中30 | 美8 | 闻8 | 十7``）
    无单位无语境；``/focusadmin`` 没有入口；「打开日志」重复；低频运维页混进"常用页面"。

修法（用户要求：**新闻流仍留一级菜单直接可见 + 点击可总结**，故用「配额+排序+限长」
而非"折叠进子菜单"）：

  1. ``select_timeline_events`` —— 全仓**唯一**的截断口径，按类型给配额，
     保证新闻必现；不传配额则维持旧 ``[:15]``（``/market`` 等调用方零影响）。
  2. 托盘一级菜单：新闻优先排序 + 限长 12 条 + 「查看全部时间线」；
     状态行合并为一行；``/focusadmin`` 进常用页面；去重「打开日志」；
     低频运维页收进「系统」子菜单。
  3. 通知改**聚合 + 时限流**：时间窗内最多一条，持仓/关注主题命中的排前面。

================================================================================
五段检查
================================================================================

  ① **配额行为**（离线纯函数）：新闻必现；上限生效；不传配额 = 旧行为
  ② **托盘取数口径**：托盘侧确实传了 ``TRAY_TIMELINE_LIMITS``
  ③ **菜单结构静态守卫**：``/focusadmin`` 有入口；无重复日志项；低频页在「系统」子菜单；
     新闻流仍在**一级菜单**（用户硬要求）；旧的裸数字行已删
  ④ **通知聚合**：聚合 + 限流常量存在；**多候选只发一条**；窗口内不重复
  ⑤ **冷启动**：``menu_bar_tray`` / ``market_24h_timeline`` 可独立导入

================================================================================
用法
================================================================================

    cd <项目根>
    /Users/spark/.local/bin/python3 scripts/verify/verify_tray_focus.py
    /Users/spark/.local/bin/python3 scripts/verify/verify_tray_focus.py --strict

退出码：0 = PASS；--strict 下有违约则 1。

**只读约定**：本脚本只读源码与内存态，不写任何落盘表、不起服务、不改菜单。
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

_CHILD_ENV = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}

_TRAY_SRC = PROJECT_ROOT / "deva/naja/infra/ui/menu_bar_tray.py"
_TIMELINE_SRC = PROJECT_ROOT / "deva/naja/market_hotspot/ui_components/timeline/market_24h_timeline.py"
_ROUTES_SRC = PROJECT_ROOT / "deva/naja/web_ui/routes.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _block(source: str, start_marker: str, end_marker: str) -> str:
    """截取 start_marker 到 end_marker 之间的源码块（找不到返回空串）。"""
    i = source.find(start_marker)
    if i < 0:
        return ""
    j = source.find(end_marker, i)
    if j < 0:
        return ""
    return source[i:j]


def main() -> int:
    parser = argparse.ArgumentParser(description="验证托盘信息聚焦")
    parser.add_argument("--strict", action="store_true", help="有违约则退出码 1")
    args = parser.parse_args()

    violations: list[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        if ok:
            print(f"  ✅ {name}" + (f"  [{detail}]" if detail else ""))
        else:
            violations.append(name)
            print(f"  ❌ {name}" + (f"  [{detail}]" if detail else ""))

    tray_src = _read(_TRAY_SRC)
    timeline_src = _read(_TIMELINE_SRC)
    routes_src = _read(_ROUTES_SRC)
    # 菜单结构只针对**完整菜单** _build_menu；_build_simple_menu 是启动中的
    # 简化菜单（"启动中…"），它有自己的 3 行状态，不该被这里的守卫误伤。
    menu_src = _block(tray_src, "def _build_menu(self):", "def _on_open_page(self, path):")

    # ── ① 配额行为（离线纯函数）─────────────────────────────────────────
    print("=" * 68)
    print("① 时间线分类配额：新闻必现、上限生效、不传配额=旧行为")
    print("=" * 68)
    from deva.naja.market_hotspot.ui_components.timeline.market_24h_timeline import (
        TRAY_TIMELINE_LIMITS,
        select_timeline_events,
    )

    ev = [{"type": "cn_event", "timestamp": 1000 + i, "block_name": f"X{i}"}
          for i in range(30)]
    ev += [{"type": "high_score_news", "timestamp": 900 + i, "title": f"N{i}"}
           for i in range(3)]
    ev += [{"type": "jin10_news", "timestamp": 800, "title": "J"}]
    ev.sort(key=lambda x: x["timestamp"], reverse=True)

    legacy = select_timeline_events(ev, None)
    check("不传配额 → 保持旧 [:15]（/market 等调用方零影响）",
          len(legacy) == 15 and {e["type"] for e in legacy} == {"cn_event"},
          f"n={len(legacy)} types={sorted({e['type'] for e in legacy})}")

    picked = select_timeline_events(ev, TRAY_TIMELINE_LIMITS)
    types = [e["type"] for e in picked]
    check("配额后高分新闻必现", "high_score_news" in types, f"types={sorted(set(types))}")
    check("配额后金十快讯必现", "jin10_news" in types, "")
    check("板块异动被限流（不再霸屏）",
          types.count("cn_event") <= TRAY_TIMELINE_LIMITS["cn_event"],
          f"cn_event={types.count('cn_event')} / limit={TRAY_TIMELINE_LIMITS['cn_event']}")
    check("配额表给两类新闻都留了名额",
          TRAY_TIMELINE_LIMITS.get("high_score_news", 0) > 0
          and TRAY_TIMELINE_LIMITS.get("jin10_news", 0) > 0,
          str(TRAY_TIMELINE_LIMITS))
    check("输出仍按时间降序", [e["timestamp"] for e in picked]
          == sorted((e["timestamp"] for e in picked), reverse=True), "")
    check("空输入返回空", select_timeline_events([], TRAY_TIMELINE_LIMITS) == [], "")

    # ── ② 托盘取数口径 ────────────────────────────────────────────────
    print()
    print("=" * 68)
    print("② 托盘取数口径：托盘侧确实按配额取数")
    print("=" * 68)
    check("market_24h_timeline 暴露 select_timeline_events 与 TRAY_TIMELINE_LIMITS",
          "def select_timeline_events" in timeline_src
          and "TRAY_TIMELINE_LIMITS =" in timeline_src, "")
    check("托盘 _get_timeline_events 调用 select_timeline_events(..., TRAY_TIMELINE_LIMITS)",
          "select_timeline_events(all_events, TRAY_TIMELINE_LIMITS)" in tray_src, "")
    check("托盘数据接口（routes.TrayDataHandler）传 per_type_limits=TRAY_TIMELINE_LIMITS",
          "per_type_limits=TRAY_TIMELINE_LIMITS" in routes_src, "")
    check("没有残留的硬截断 all_events[:15]（口径已收口到唯一函数）",
          "for event in all_events[:15]" not in tray_src
          and "for event in all_events[:15]" not in timeline_src, "")

    # ── ③ 菜单结构静态守卫 ────────────────────────────────────────────
    print()
    print("=" * 68)
    print("③ 菜单结构：入口补齐 / 去重 / 低频页收拢 / 新闻流仍在一级")
    print("=" * 68)
    check("常用页面补了 /focusadmin 入口",
          '_on_open_page("/focusadmin")' in menu_src, "")
    check("「打开日志」不再重复（完整菜单里只出现一次）",
          menu_src.count('"📄 打开日志"') == 1, f"count={menu_src.count('\"📄 打开日志\"')}")

    common_block = _block(menu_src, "common_pages = rumps.MenuItem", "self._app.menu.add(common_pages)")
    system_block = _block(menu_src, 'system_menu = rumps.MenuItem', "self._app.menu.add(system_menu)")
    check("「常用页面」块已无 /logstream 与 /health（低频运维页移出）",
          "/logstream" not in common_block and "/health" not in common_block,
          f"common 块含 logstream={'/logstream' in common_block} health={'/health' in common_block}")
    check("「系统」子菜单含 /logstream 与 /health",
          "/logstream" in system_block and "/health" in system_block, "")
    check("「系统」子菜单含自启 / 同步 / 重启 / 退出",
          all(k in system_block for k in ("登录时自动启动", "从服务器同步", "重启服务", "退出")), "")

    # 用户硬要求：新闻流仍留一级菜单、可点总结
    check("新闻流仍在**一级菜单**（用户要求：不折叠进子菜单）",
          "self._app.menu.add(flow_head)" in menu_src, "")
    check("新闻流限长呈现（ordered[:12]，原为 events[:20]）",
          "ordered[:12]" in menu_src and "events[:20]" not in menu_src, "")
    check("一级菜单保留「一键总结」", "一键总结当前时间线" in menu_src, "")
    check("有「查看全部时间线」出口", "查看全部时间线" in menu_src, "")
    check("新闻优先排序（新闻在板块异动之前）",
          "news_first" in menu_src and "'high_score_news': 0" in menu_src, "")

    check("状态行已合并为一行（不再 3 行 标题/状态/端口）",
          "📊 Naja " in menu_src and "📍 端口:" not in menu_src, "")
    check("旧 4 个裸数字统计行已删（⏰ 全球市场时间线 | 🇨🇳 N | …）",
          "全球市场时间线 |" not in menu_src, "")
    check("旧的「日期分隔」两行（─ ×30 + 📅 日期）已删",
          '📅 {event_date}' not in menu_src and "'─'*30" not in menu_src, "")

    # ── ④ 通知聚合 ────────────────────────────────────────────────────
    print()
    print("=" * 68)
    print("④ 通知：聚合 + 限流（避免修完截断后从「不响」跳到「轰炸」）")
    print("=" * 68)
    check("存在限流常量 NOTIFY_MIN_INTERVAL", "NOTIFY_MIN_INTERVAL" in tray_src, "")
    check("有限流状态 _last_notify_ts 且被写入（而非只读）",
          "_last_notify_ts = 0.0" in tray_src and "self._last_notify_ts = now" in tray_src, "")
    check("聚合通知文案存在（N 条重要新闻）", "条重要新闻" in tray_src, "")
    check("有「相关性优先」排序（持仓/关注主题）", "_relevance_keywords" in tray_src, "")

    from deva.naja.infra.ui import menu_bar_tray as mbt

    t = mbt.MenuBarTray()
    t._naja_ready = True
    t._last_notify_ts = 0.0
    t._menu_cache = {"timeline": {"success": True, "list": [
        {"type": "high_score_news", "timestamp": 1, "score": 0.9, "title": "A"},
        {"type": "jin10_news", "timestamp": 2, "score": 0.85, "title": "B"},
        {"type": "cn_event", "timestamp": 3, "score": 0.99, "title": "板块异动"},
    ]}}
    sent: list = []
    t._send_notification = lambda title, subtitle="", message="": sent.append(
        (title, subtitle, message))
    t._relevance_keywords = lambda: set()

    t._check_and_send_notifications()
    check("多候选 → 只发一条聚合通知（3 候选含 1 条非新闻）",
          len(sent) == 1 and "2 条" in sent[0][0], f"sent={sent}")
    check("板块异动（cn_event）永不弹通知", all("板块异动" not in s[0] for s in sent), "")

    t._check_and_send_notifications()
    check("时间窗内不重复通知", len(sent) == 1, f"sent 条数={len(sent)}")

    # ── ⑤ 冷启动 ──────────────────────────────────────────────────────
    print()
    print("=" * 68)
    print("⑤ 冷启动：托盘与时间线模块可独立导入")
    print("=" * 68)
    cold = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, %r);\n"
         "from deva.naja.infra.ui.menu_bar_tray import MenuBarTray;\n"
         "from deva.naja.market_hotspot.ui_components.timeline.market_24h_timeline "
         "import select_timeline_events, TRAY_TIMELINE_LIMITS;\n"
         "print('ok')" % str(PROJECT_ROOT)],
        capture_output=True, text=True, env=_CHILD_ENV, timeout=300,
    )
    out = (cold.stdout or cold.stderr or "").strip().splitlines()
    check("子进程冷启动导入成功",
          cold.returncode == 0 and "ok" in (cold.stdout or ""), out[-1] if out else "")

    # ── 汇总 ──────────────────────────────────────────────────────────
    print()
    print("=" * 68)
    if violations:
        print(f"❌ 违约 {len(violations)} 项: {violations}")
        return 1 if args.strict else 0
    print("✅ 全部通过：托盘新闻流一级可见且新闻必现；菜单结构聚焦；通知聚合限流")
    return 0


if __name__ == "__main__":
    sys.exit(main())
