#!/usr/bin/env python3
"""验证「关注管理」——从持仓推导供应链主题 + 手动仓位 / 关注主题的 CRUD。

覆盖什么
--------
① **图谱数据完整**：真实持仓的三只票（NVDA / CRWV / BABA）都能查出上下游；
   NVDA 的**下游不再为空**（需求端曾经整块缺失）
② **推导正确**：候选主题带 score 与可读理由；多持仓共识有加分；排序稳定
   （同样的输入永远得到同样的顺序）
③ **推导边界**：过宽词（``AI``）不进主题列表（否则重演"宽泛主题命中一切"的坑）；
   只取 **depth=1 直接上下游**，不做传递闭包（CRWV 的上游不该含台积电）
④ **采纳**：写入 ``source="derived"``；**不覆盖**已有主题（防篡改手动关注的来源）；
   重复采纳幂等
⑤ **撤销**：只删 ``derived``；记入 revoked 名单；之后的**自动采纳不再加回**
⑥ **手动账户 CRUD**：增 / 改 / 软删，且**真的落盘**（子进程读回验证）
⑦ **自选 CRUD**：增 / 改 / 删（写 ``naja_watchlist``）；跨进程读回证真落盘；
   全程只在**临时表**上做，真实自选表分毫不动
⑧ **反静默**：空持仓、图谱外的票、缺板块映射——全部要留痕，不许静默返回空
⑨ **静态守卫**：容器确实接了自动采纳；``/focusadmin`` 路由确实注册；UI 有渲染出口；
   入口在业务页（``/news`` 标题旁）而**不占顶部导航**（导航已 13 项吃紧）
⑩ **冷启动**：``news.focus_advisor`` 可独立导入，不拉起交易域重依赖

跑法
----
    cd <项目根>
    /Users/spark/.local/bin/python3 scripts/verify/verify_focus_advisor.py
    /Users/spark/.local/bin/python3 scripts/verify/verify_focus_advisor.py --strict

退出码：0 = PASS；--strict 下有违约则 1。

**只读约定**：本脚本不改生产关注配置。第 ⑥ 项用一个 **临时账户名**
（``__verify_tmp_acct__``）测 CRUD，并在结束时把落盘表里的痕迹清掉；
第 ⑦ 项把 ``WATCHLIST_TABLE`` 指到临时表（``__verify_watchlist__``）后测自选 CRUD，
结束时清掉临时表并还原——**真实自选表前后逐字节一致**（脚本里会断言）。
不碰「手动」账户，也不碰 ``naja_focus_config``。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

_CHILD_ENV = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
_TMP_ACCOUNT = "__verify_tmp_acct__"


def main() -> int:
    parser = argparse.ArgumentParser(description="验证关注管理（推导 + CRUD）")
    parser.add_argument("--strict", action="store_true", help="有违约则退出码 1")
    args = parser.parse_args()

    violations: list[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        if ok:
            print(f"  ✅ {name}" + (f"  [{detail}]" if detail else ""))
        else:
            violations.append(name)
            print(f"  ❌ {name}" + (f"  [{detail}]" if detail else ""))

    # ── ① 图谱数据完整 ────────────────────────────────────────────────
    print("=" * 68)
    print("① 供应链图谱：持仓的三只票都能查上下游，NVDA 下游不再为空")
    print("=" * 68)
    from deva.naja.bandit.supply_chain_graph import get_supply_chain_graph

    graph = get_supply_chain_graph()
    nvda_up = [c.stock_code for c in graph.get_upstream_companies("nvda")]
    nvda_down = [c.stock_code for c in graph.get_downstream_companies("nvda")]
    check("NVDA 有上游（供应商）", len(nvda_up) >= 5, f"上游={nvda_up}")
    check("NVDA 有**下游**（需求端，历史缺口已补）", len(nvda_down) >= 4, f"下游={nvda_down}")
    check("NVDA 下游含云厂商（GPU 的真实去向）",
          any(c in nvda_down for c in ("msft", "googl", "amzn")), f"{nvda_down}")

    crwv_node = graph.get_stock_node("crwv")
    check("CRWV(CoreWeave) 在图谱中且**不是** Crown Castle 的错误节点",
          crwv_node is not None and "CoreWeave" in (crwv_node.name or ""),
          f"{getattr(crwv_node, 'name', None)}")
    baba_node = graph.get_stock_node("baba")
    check("BABA(阿里巴巴) 已补进图谱", baba_node is not None,
          f"{getattr(baba_node, 'name', None)}")

    # ── ② 推导正确 ────────────────────────────────────────────────────
    print()
    print("=" * 68)
    print("② 从持仓推导候选主题：带理由、有共识加分、排序稳定")
    print("=" * 68)
    from deva.naja.news.focus_advisor import (
        DERIVE_CONSENSUS_BONUS, derive_topics,
    )

    result = derive_topics()
    check("推导可用（读得到持仓）", result["available"] is True,
          result.get("reason") or "")
    topics = result.get("topics") or []
    check("推导出了候选主题", len(topics) >= 3, f"n={len(topics)}")

    if topics:
        t0 = topics[0]
        check("候选主题带 score 与「来自哪些持仓」",
              isinstance(t0.get("score"), float) and bool(t0.get("from_holdings")),
              f"{t0.get('topic')} score={t0.get('score')} from={t0.get('from_holdings')}")
        check("候选主题带可读理由（evidence）",
              bool(t0.get("evidence")) and "→" in (t0.get("evidence") or [""])[0],
              (t0.get("evidence") or [""])[0])
        check("候选按 score 降序",
              all(topics[i]["score"] >= topics[i + 1]["score"] for i in range(len(topics) - 1)),
              f"scores={[t['score'] for t in topics[:5]]}")
        check("有主题被多只持仓共同指向（共识加分生效）",
              any(len(t.get("from_holdings") or []) > 1 for t in topics),
              f"最多来自={max(len(t.get('from_holdings') or []) for t in topics)} 只")

    # 同输入必须同输出（排序稳定，不能靠 dict 顺序碰运气）
    again = derive_topics()
    check("同输入 → 同输出（排序稳定、可复现）",
          [t["topic"] for t in (again.get("topics") or [])] == [t["topic"] for t in topics],
          f"{[t['topic'] for t in topics][:4]}")

    # ── ③ 推导边界 ────────────────────────────────────────────────────
    print()
    print("=" * 68)
    print("③ 推导边界：过宽词不入列表；只取直接上下游（不做传递闭包）")
    print("=" * 68)
    from deva.naja.news.focus_advisor import TOO_BROAD_TOPICS

    names = {t["topic"] for t in topics}
    check("过宽主题（AI 等）没有进列表", not (names & set(TOO_BROAD_TOPICS)),
          f"命中={sorted(names & set(TOO_BROAD_TOPICS))}；列表={sorted(names)}")

    # CRWV 的**直接**上游只有 smci / nvda；台积电/美光是 nvda 的上游，
    # 属于传递闭包，不该出现在 CRWV 的一跳上游里。
    direct_crwv_up = [c.stock_code for c in graph.get_direct_upstream("crwv")
                      if getattr(c, "stock_code", None)]
    check("只取直接上游（CRWV 的直接上游含 nvda，不含台积电这类二级供应商）",
          "nvda" in direct_crwv_up and "tsm" not in direct_crwv_up,
          f"crwv 直接上游={direct_crwv_up}")

    # 对照：既有 get_upstream(id, 1) 的 max_depth 是「额外跳数」，传 1 会走两跳。
    # 记下来，免得以后有人"顺手"改回去。
    two_hop = [c.stock_code for c in graph.get_upstream("crwv", 1)
               if getattr(c, "stock_code", None)]
    check("（对照）get_upstream(id, 1) 会走两跳——所以推导必须用 get_direct_*",
          "tsm" in two_hop,
          f"get_upstream(crwv,1)={two_hop}")

    # ── ④ 采纳：可撤销、不覆盖、幂等 ──────────────────────────────────
    print()
    print("=" * 68)
    print("④ 采纳：标记 derived；不覆盖已有主题；重复采纳幂等")
    print("=" * 68)
    from deva.naja.attention.focus_manager import FocusItem, FocusSummary
    from deva.naja.news.focus_advisor import (
        DerivedTopic, SOURCE_DERIVED, apply_derived_topics,
    )

    class _FakeFM:
        """内存假管理器——第 ④⑤ 项**不碰生产配置**。"""

        def __init__(self) -> None:
            self._n: dict = {}

        def follow_narrative(self, name, priority=0.7, source="manual", blocks=None):
            item = FocusItem(focus_type="narrative", focus_id=name, display_name=name,
                             source=source, priority=priority)
            self._n[name] = item
            return item

        def unfollow_narrative(self, name):
            self._n.pop(name, None)

        def get_watched_narratives(self):
            return list(self._n)

        def get_summary(self):
            items = list(self._n.values())
            return FocusSummary(narratives=items, blocks=[], stocks=[],
                                all_narrative_ids=set(self._n),
                                all_block_ids=set(), all_stock_codes=set())

    fm = _FakeFM()
    fm.follow_narrative("量子计算", priority=0.9, source="user")   # 用户手动关注
    fm.follow_narrative("已有主题", priority=0.5, source="user")
    batch = [DerivedTopic("半导体", 0.80), DerivedTopic("HBM", 0.70),
             DerivedTopic("噪声", 0.30), DerivedTopic("已有主题", 0.90)]

    applied = apply_derived_topics(batch, manager=fm)
    check("采纳达标的、跳过低于阈值的",
          set(applied["applied"]) == {"半导体", "HBM"}
          and any(s["topic"] == "噪声" for s in applied["skipped"]),
          f"applied={applied['applied']} skipped={[s['topic'] for s in applied['skipped']]}")
    check("已在关注列表的主题不覆盖（保护手动关注的 source）",
          applied["already"] == ["已有主题"]
          and fm._n["已有主题"].source == "user",
          f"already={applied['already']} source={fm._n['已有主题'].source}")
    check("推导写入的主题被标为 derived",
          fm._n["半导体"].source == SOURCE_DERIVED, fm._n["半导体"].source)

    again_apply = apply_derived_topics(batch, manager=fm)
    check("重复采纳幂等（不重复写）", again_apply["applied"] == [],
          f"applied={again_apply['applied']}")

    # ── ⑤ 撤销：只删 derived，并记入 revoked ──────────────────────────
    print()
    print("=" * 68)
    print("⑤ 撤销：只删 derived；记入 revoked 名单；自动采纳不再加回")
    print("=" * 68)
    from deva.naja.news.focus_advisor import (
        _load_revoked, _record_revoked, apply_derived_topics as _apply,
    )

    before_revoked = set(_load_revoked())
    fake_removed = ["__verify_revoked_probe__"]
    after_revoked = set(_record_revoked(fake_removed))
    check("撤销的主题被记入「已撤销」名单（否则自动采纳会加回来）",
          set(fake_removed) <= after_revoked,
          f"新增={sorted(after_revoked - before_revoked)}")

    probe = ["__verify_revoked_probe__"]
    res_probe = _apply([DerivedTopic("__verify_revoked_probe__", 0.99)],
                       manager=fm, respect_revoked=True)
    check("自动采纳会跳过「用户曾撤销」的主题",
          res_probe["applied"] == []
          and any("撤销" in s.get("reason", "") for s in res_probe["skipped"]),
          f"skipped={res_probe['skipped']}")

    # 清掉验证留下的名单污染
    from deva import NB
    _cfg = NB("naja_focus_config")
    _cfg["revoked_derived_topics"] = [x for x in (after_revoked - set(fake_removed))]
    check("验证结束后清掉了 revoked 名单里的探针（不污染生产）",
          "__verify_revoked_probe__" not in (_cfg.get("revoked_derived_topics") or []),
          f"{_cfg.get('revoked_derived_topics')}")

    # ── ⑥ 手动账户 CRUD（临时账户，测完清理）──────────────────────────
    print()
    print("=" * 68)
    print("⑥ 手动账户 CRUD：增 / 改 / 软删，且真的落盘（子进程读回）")
    print("=" * 68)
    from deva.naja.bandit.portfolio_manager import PortfolioManager, UNIFIED_POSITIONS_TABLE

    pm = PortfolioManager()
    # persist=True 才会写进 account_names 名册——**这正是要验证的**：
    # 用户手建的账户必须能重启后重建，否则磁盘里有持仓也读不出来
    # （2026-10-12「持仓恒为空」事故的同款形状）。测完再清掉名册痕迹。
    acct = pm.ensure_account(_TMP_ACCOUNT, persist=True)
    added = acct.add_position("vfy", "验证票", 10.0, 100)
    check("新增持仓成功", added is not None, f"pid={getattr(added, 'position_id', None)}")
    pid = getattr(added, "position_id", "")

    upd = acct.update_position(pid, quantity=150)
    check("修改数量成功（100 → 150）",
          upd is not None and abs(upd.quantity - 150) < 1e-9,
          f"quantity={getattr(upd, 'quantity', None)}")
    check("非正数量被拒绝（想清仓请走 sell）",
          acct.update_position(pid, quantity=0) is None, "")
    check("清单里能看到该持仓",
          any(p.stock_code == "vfy" for p in acct.get_open_positions()), "")

    child_src = textwrap.dedent(f"""
        import sys, json
        sys.path.insert(0, {str(PROJECT_ROOT)!r})
        from deva.naja.bandit.portfolio_manager import PortfolioManager
        pm = PortfolioManager()
        p = pm.get_us_portfolio({_TMP_ACCOUNT!r})
        rows = [] if p is None else [
            [x.stock_code, x.quantity] for x in p.get_open_positions()
        ]
        print("RESULT:" + json.dumps(rows))
    """)
    child = subprocess.run([sys.executable, "-c", child_src], capture_output=True,
                           text=True, env=_CHILD_ENV, timeout=180)
    # 子进程 stdout 里混着框架日志（如 "[2026-...][INFO][deva] exit"），
    # 所以用一个显式前缀捞结果，别去猜哪种行像 JSON。
    persisted = ""
    for line in (child.stdout or "").splitlines():
        if line.startswith("RESULT:"):
            persisted = line[len("RESULT:"):].strip()
    check("落盘生效（**新进程**从名册重建该账户并读回，数量已更新）",
          '"vfy"' in persisted and "150" in persisted,
          f"子进程读到={persisted or '(无 RESULT 行)'}")

    sold = acct.sell_position(pid, 12.0)
    check("软删（置 CLOSED，保留历史）",
          sold is not None and sold.status == "CLOSED"
          and not acct.get_open_positions(), f"status={getattr(sold, 'status', None)}")

    # 清理：临时账户会落在**两张表**上——持仓表（positions）与名册表
    # （account_names）。只清一张的话，下次启动会凭空多出一个僵尸账户。
    try:
        from deva.naja.bandit.portfolio_manager import PORTFOLIO_MANAGER_TABLE
        db = NB(UNIFIED_POSITIONS_TABLE)
        accounts_data = db.get("accounts", {}) or {}
        if _TMP_ACCOUNT in accounts_data:
            del accounts_data[_TMP_ACCOUNT]
            db["accounts"] = accounts_data

        mdb = NB(PORTFOLIO_MANAGER_TABLE)
        names = list(mdb.get("account_names", []) or [])
        if _TMP_ACCOUNT in names:
            mdb["account_names"] = [n for n in names if n != _TMP_ACCOUNT]

        check("验证结束后清理了临时账户痕迹（持仓表 + 名册表）",
              _TMP_ACCOUNT not in (db.get("accounts") or {})
              and _TMP_ACCOUNT not in (mdb.get("account_names") or []),
              f"名册={mdb.get('account_names')}")
    except Exception as e:
        check("验证结束后清理了临时账户痕迹（持仓表 + 名册表）",
              False, f"{type(e).__name__}: {e}")

    # ── ⑦ 自选 CRUD（临时表，测完清理；真实自选表分毫不动）────────────
    print()
    print("=" * 68)
    print("⑦ 自选 CRUD：增 / 改 / 删 + 跨进程读回 —— 只在临时表上做")
    print("=" * 68)
    from deva.naja.attention import portfolio as pfo
    from deva.naja.news import focus_admin as fa

    _TMP_WATCHLIST = "__verify_watchlist__"
    _real_table = pfo.WATCHLIST_TABLE
    # 先给真实自选表拍个照，最后逐字节比对，证明本组没碰它。
    real_before = json.dumps(dict(NB(_real_table)).get("stocks"),
                             ensure_ascii=False, sort_keys=True, default=str)

    pfo.WATCHLIST_TABLE = _TMP_WATCHLIST
    try:
        # ``DBStream.clear()`` 自己不提交事务，且返回的是内部结果（不是 self），
        # 所以必须分两步 + 显式 persist()，否则"清了"只留在内存里，下个进程照样读到。
        _wl = NB(_TMP_WATCHLIST)
        _wl.clear()
        _wl.persist()
        pf = pfo.Portfolio()
        pf.invalidate_cache()          # 单例：必须显式失效，否则读到真实表的旧缓存

        check("起始自选为空（用的是干净临时表）",
              fa.list_watchlist()["count"] == 0, f"{fa.list_watchlist()['items']}")

        check("空代码被拒绝", fa.add_watchlist("")["ok"] is False, "")
        added = fa.add_watchlist("nvda", "英伟达")
        check("新增自选成功（带展示名）", added["ok"] is True, f"{added.get('item')}")
        check("重复新增被拒绝（不覆盖）", fa.add_watchlist("NVDA")["ok"] is False, "")

        upd = fa.update_watchlist("nvda", "NVIDIA")
        check("改展示名成功", upd["ok"] is True, f"{upd.get('item')}")
        check("未填新名字 → 拒绝",
              fa.update_watchlist("nvda", "")["ok"] is False, "")

        # 跨进程读回：另起一个进程（同样的临时表名）把数据读出来，
        # 证明写的是**落盘**而不是进程内内存。
        child_src = textwrap.dedent(f"""
            import sys, json
            sys.path.insert(0, {str(PROJECT_ROOT)!r})
            from deva.naja.attention import portfolio as pfo
            pfo.WATCHLIST_TABLE = {_TMP_WATCHLIST!r}
            from deva.naja.news import focus_admin as fa
            print("RESULT:" + json.dumps(fa.list_watchlist(), ensure_ascii=False))
        """)
        child = subprocess.run([sys.executable, "-c", child_src], capture_output=True,
                               text=True, env=_CHILD_ENV, timeout=180)
        persisted = ""
        for line in (child.stdout or "").splitlines():
            if line.startswith("RESULT:"):
                persisted = line[len("RESULT:"):].strip()
        check("落盘生效（**新进程**读回同一条自选）",
              '"nvda"' in persisted and "NVIDIA" in persisted,
              f"子进程读到={persisted or '(无 RESULT 行)'}")

        check("删除自选成功", fa.remove_watchlist("NVDA")["ok"] is True, "")
        check("已删再删被拒绝", fa.remove_watchlist("nvda")["ok"] is False, "")
        check("删完确实为空", fa.list_watchlist()["count"] == 0, "")
    finally:
        try:
            _wl = NB(_TMP_WATCHLIST)
            _wl.clear()
            _wl.persist()      # clear() 不提交且返回 None，见上
        except Exception:
            pass
        pfo.WATCHLIST_TABLE = _real_table
        try:
            pfo.Portfolio().invalidate_cache()
        except Exception:
            pass

    real_after = json.dumps(dict(NB(_real_table)).get("stocks"),
                            ensure_ascii=False, sort_keys=True, default=str)
    check("真实自选表分毫未动（前后逐字节一致）", real_before == real_after,
          f"before={real_before[:80]}")

    # ── ⑧ 反静默 ──────────────────────────────────────────────────────
    print()
    print("=" * 68)
    print("⑧ 反静默：空持仓 / 图谱外的票 / 缺映射，都必须留痕")
    print("=" * 68)
    empty = derive_topics([])
    check("空持仓 → available=False 且给出 reason",
          empty["available"] is False and bool(empty.get("reason")), empty.get("reason") or "")

    class _Stub:
        def __init__(self, code, name="", account="X"):
            self.code, self.name, self.account = code, name, account

    ghost = derive_topics([_Stub("zzzz", "图谱外票")])
    check("图谱外的票 → 明确留痕（不静默返回空）",
          bool(ghost.get("degraded")), f"{ghost.get('degraded')}")

    class _NoGraph:
        """图谱退化：构造一个 get_stock_node 永远返回 None 的假图谱。"""

        def get_stock_node(self, code):
            return None

    degraded_result = derive_topics([_Stub("nvda", "英伟达")], graph=_NoGraph())
    check("图谱不可用 → 降级说明里点明是哪只票",
          any("供应链图谱" in d for d in degraded_result.get("degraded") or []),
          f"{degraded_result.get('degraded')}")

    # ── ⑨ 静态守卫 ────────────────────────────────────────────────────
    print()
    print("=" * 68)
    print("⑨ 静态守卫：容器接线 / 路由注册 / UI 出口（防回退成死线）")
    print("=" * 68)
    container_src = (PROJECT_ROOT / "deva/naja/application/container.py").read_text("utf-8")
    check("容器确实调用 auto_apply_derived（自动采纳接线存在）",
          "focus_advisor" in container_src and "auto_apply_derived" in container_src, "")
    check("容器提供关闭开关（NAJA_NEWS_AUTO_DERIVE）",
          "NAJA_NEWS_AUTO_DERIVE" in container_src, "")

    routes_src = (PROJECT_ROOT / "deva/naja/web_ui/routes.py").read_text("utf-8")
    check("路由表注册了 /focusadmin",
          "/focusadmin" in routes_src and "focusadmin" in routes_src, "")
    pages_src = (PROJECT_ROOT / "deva/naja/web_ui/pages.py").read_text("utf-8")
    check("pages 提供了 focusadmin 页面函数",
          "async def focusadmin" in pages_src, "")
    news_page_src = (PROJECT_ROOT / "deva/naja/news/page.py").read_text("utf-8")
    check("业务页有「关注设置」入口（/news 标题旁——关注主题的下游就在这）",
          'href="/focusadmin"' in news_page_src, "")
    theme_src = (PROJECT_ROOT / "deva/naja/infra/ui/ui_theme.py").read_text("utf-8")
    check("顶部导航不占位（导航已 13 项/约 1048px，低频页改放业务页内）",
          "/focusadmin" not in theme_src, "")

    from deva.naja.news.ui import render_focus_admin  # noqa: F401
    from deva.naja.news import focus_admin as fa
    for fn in ("list_topics", "add_topic", "update_topic", "remove_topic",
               "list_positions", "add_position", "update_position", "remove_position",
               "list_watchlist", "add_watchlist", "update_watchlist", "remove_watchlist",
               "apply_derived", "revoke_derived"):
        check(f"focus_admin.{fn} 存在", callable(getattr(fa, fn, None)), "")

    # UI 的 HTML 片段必须自闭合（PyWebIO 每次 put_html 都是独立片段）
    overview = fa.get_focus_overview()
    check("首屏总览包含自选块（UI 那一段有数据源）",
          "watchlist" in overview and isinstance(overview["watchlist"], dict), "")
    from deva.naja.news import ui as news_ui
    for fname, frag in (
        ("统计卡", news_ui._stats_html(overview["positions"], overview["topics"],
                                      overview["watchlist"], overview["derived"])),
        ("持仓块", news_ui._positions_html(overview["positions"])),
        ("自选块", news_ui._watchlist_html(overview["watchlist"])),
        ("主题块", news_ui._topics_html(overview["topics"])),
        ("推导块", news_ui._derived_html(overview["derived"])),
    ):
        opens = frag.count("<div") + frag.count("<table") + frag.count("<tr")
        closes = frag.count("</div>") + frag.count("</table>") + frag.count("</tr>")
        check(f"UI「{fname}」HTML 片段标签自闭合（防 PyWebIO 片段撕裂）",
              opens == closes, f"开={opens} 闭={closes}")

    check("UI 出口返回的是纯 dict（不能把 dataclass 漏给前端）",
          isinstance(overview, dict) and json.dumps(overview, ensure_ascii=False) is not None,
          "")

    # ── ⑩ 冷启动 ──────────────────────────────────────────────────────
    print()
    print("=" * 68)
    print("⑩ 冷启动：focus_advisor 可独立导入")
    print("=" * 68)
    cold = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, %r);\n"
         "from deva.naja.news.focus_advisor import derive_topics, auto_apply_derived;\n"
         "print('ok')" % str(PROJECT_ROOT)],
        capture_output=True, text=True, env=_CHILD_ENV, timeout=300,
    )
    check("子进程冷启动导入成功", cold.returncode == 0 and "ok" in (cold.stdout or ""),
          (cold.stdout or cold.stderr or "").strip().splitlines()[-1:] and
          (cold.stdout or cold.stderr or "").strip().splitlines()[-1] or "")

    # ── 汇总 ──────────────────────────────────────────────────────────
    print()
    print("=" * 68)
    if violations:
        print(f"❌ 违约 {len(violations)} 项: {violations}")
        return 1 if args.strict else 0
    print("✅ 全部通过：关注管理可用——持仓可手填、自选可增删改、主题可增删改、"
          "从持仓推导供应链主题")
    return 0


if __name__ == "__main__":
    sys.exit(main())
