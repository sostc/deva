"""守卫：首页状态卡不许把「不知道」画成「0」，也不许把「停更」画成「正常」。

背景（2026-10-20 实测）：

首页 10 张卡里有 4 个数字**从来不是真的**，而它们看起来和真数字一模一样：

1. ``BanditAutoRunner.get_stats()`` 不存在 → ``hasattr`` 挡掉 → 恒 0；
2. ``cognition_stats['signals_processed']`` 这个键全仓不存在 → 恒 0；
3. ``get_cognition_system()`` 这个函数全仓不存在 → 每次都 ImportError → 恒 0；
4. ``len(radar.get_recent_events(limit=100))`` 先截断再计数 → 上限 100，
   爆表时分不清「刚好 100」还是「早就超出」。

共同特征：**降级路径写了一个合法的数值**。0 在 UI 上和「确实是零」完全同形，
于是「模块没接上」被读成「今天没有交易」，可以静静挂上几个月。

本守卫钉三件事：
  A. 取数全挂时，主数字必须是「—」并写明原因，**不许是 0**；
  B. 持仓价格停更时，「持仓风险」卡的主数字必须是**陈旧只数**，
     不许用持仓总数顶上（那样停更 202 天也显示「40 持仓，一切正常」）；
  C. 决策卡的判读必须写出「为什么不动」（终分 / 门槛），
     只写「全 hold」等于什么都没说。

负向注入把 A、B 两条各破坏一次，确认断言真的会红。
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

STATS = ROOT / "deva/naja/home/ui/stats.py"

CARD_NAMES = ["账户（虚拟）", "决策", "持仓风险", "算力消耗",
              "数据源", "任务", "雷达事件", "认知",
              "Bandit", "策略", "字典", "智慧陪伴"]
TIERS = ["① 钱与决策", "② 链路在生产吗", "③ 反馈与配置"]


def _boom(*a, **k):
    raise RuntimeError("offline guard: container not initialised")


class FakePos:
    def __init__(self, code, entry, cur, qty, age_days):
        self.stock_code = code
        self.entry_price = entry
        self.current_price = cur
        self.quantity = qty
        self.return_pct = (cur - entry) / entry * 100 if entry else 0.0
        self.last_update_time = time.time() - age_days * 86400


class FakeVP:
    def __init__(self, summary=None, positions=None, explode=False):
        self._summary = summary or {}
        self._positions = positions or []
        self._explode = explode

    def get_summary(self):
        if self._explode:
            raise RuntimeError("db locked")
        return self._summary

    def get_all_positions(self, status=None):
        if self._explode:
            raise RuntimeError("db locked")
        return self._positions


class FakeTC:
    def __init__(self, window):
        self._window = window

    def get_decision_history(self, hours=24, limit=500):
        return self._window

    def get_recent_decisions(self, limit=1):
        return self._window[:1]


SUMMARY = {
    "total_capital": 1_000_000.0,
    "available_capital": 391_704.0,
    "total_value": 619_664.0,
    "position_count": 40,
    "total_profit_loss": 11_368.0,
    "total_return": 1.87,
}

GATE = ("主因=地势(风险温度1.30偏高) | 天时0.65 | 人和0.29·策略维 | "
        "0.378×折扣0.88=0.332 | 恐慌0·偏恐 | 行动:hold | "
        "✗未通过(终分0.332<门槛0.500)")


def _render_all_fail():
    """取数入口全挂，返回渲染出的 HTML。"""
    import deva.naja.register as reg_mod
    import deva.naja.radar as radar_pkg
    from deva.naja.home.ui import stats as S

    out = []
    with mock.patch.object(reg_mod, "SR", _boom), \
         mock.patch.object(S, "SR", _boom), \
         mock.patch.object(radar_pkg, "get_radar_engine", _boom):
        S.render_stats_cards({"put_html": out.append}, {}, {}, {}, {})
    return out[0]


def _all_checks() -> list:
    fails: list = []
    from deva.naja.home.ui import stats as S

    # ── A. 取数全挂：12 张卡、三层、主数字不许是 0 ──
    html = _render_all_fail()
    n_cards = html.count("border-radius: 12px; padding: 18px 14px")
    if n_cards != 12:
        fails.append(f"渲染出 {n_cards} 张卡，应为 12")
    for name in CARD_NAMES:
        if name not in html:
            fails.append(f"缺少卡片：{name}")
    for tier in TIERS:
        if tier not in html:
            fails.append(f"缺少分层标题：{tier}")
    for bad in ("None", "nan"):
        if bad in html:
            fails.append(f"渲染残留 {bad!r}")
    if "组合不可用" not in html:
        fails.append("组合取数失败时没有写明原因")

    with mock.patch.object(S, "SR", _boom):
        account = dict(S._account_card())
    if account["main"] != "—":
        fails.append(
            f"组合不可用时账户卡主数字是 {account['main']!r} —— 必须是「—」，"
            "写 0 等于把「不知道」画成「账户是 0」"
        )
    if "RuntimeError" not in account["judge"]:
        fails.append("账户卡异常时没有写出异常类型")

    # 本金为 0 时不许下 0% 的结论
    with mock.patch.object(S, "SR", lambda name: FakeVP({"total_capital": 0})):
        zero = dict(S._account_card())
    if zero["main"] != "—" or "未配置本金" not in zero["judge"]:
        fails.append(f"无本金时给出了结论：main={zero['main']!r} judge={zero['judge']!r}")

    # ── 成功路径：账户卡四层齐全 ──
    with mock.patch.object(S, "SR", lambda name: FakeVP(SUMMARY)):
        acc = dict(S._account_card())
    if acc["main"] != "101.1 万":
        fails.append(f"账户卡总资产算错：{acc['main']!r}")
    if "+11,368" not in acc["sub"]:
        fails.append(f"账户卡浮盈亏没上副行：{acc['sub']!r}")

    # ── B. 持仓风险：主数字必须是陈旧只数 ──
    def risk(positions):
        with mock.patch.object(S, "SR", lambda name: FakeVP(SUMMARY, positions)):
            return dict(S._position_risk_card())

    fresh = [FakePos("600000", 10, 11, 100, 0.2), FakePos("000001", 10, 9, 100, 0.5)]
    r = risk(fresh)
    if r["main"] != "0" or r["judge_color"] != S.C_GREEN:
        fails.append(f"全部新鲜的持仓被判成异常：{r}")

    mid = [FakePos("600000", 10, 11, 100, 4), FakePos("000001", 10, 9, 100, 0.5)]
    r = risk(mid)
    if r["main"] != "1" or r["judge_color"] != S.C_ORANGE:
        fails.append(
            f"2 只持仓里 1 只超 3 天，主数字应为 1（陈旧只数），实得 {r['main']!r}："
            "换成持仓总数就再也看不出停更"
        )

    stale = [FakePos("600000", 10, 11, 100, 201), FakePos("000001", 10, 9, 100, 4)]
    r = risk(stale)
    if r["main"] != "2" or r["judge_color"] != S.C_RED or "不可信" not in r["judge"]:
        fails.append(f"停更 201 天的持仓没有报红：{r}")
    if "000001" not in r["sub"] or "-10.0%" not in r["sub"]:
        fails.append(f"最差持仓没点出来：{r['sub']!r}")

    r = risk([])
    if r["main"] != "0" or "无未平仓持仓" not in r["judge"]:
        fails.append(f"空仓被报成陈旧：{r}")

    # ── C. 决策卡：必须写出「为什么不动」 ──
    import deva.naja.attention.orchestration.trading_center as tc_mod

    def decision(window):
        with mock.patch.object(tc_mod, "get_trading_center", lambda: FakeTC(window)):
            return dict(S._decision_card())

    now = time.time()
    held = [{"recorded_at": now - i, "approved": False, "action_type": "hold",
             "gate_reason": GATE, "risk_temperature": 1.30} for i in range(10)]
    d = decision(held)
    if "全 hold" not in d["sub"] or "地势" not in d["sub"]:
        fails.append(f"决策卡没写出主因：{d['sub']!r}")
    if "0.33" not in d["judge"] or "0.50" not in d["judge"]:
        fails.append(f"决策卡没写出终分/门槛差距：{d['judge']!r}")
    if d["judge_color"] != S.C_ORANGE:
        fails.append("风险温度 1.30 时判读仍是中性色（风险温度是反向指标）")

    d = decision([dict(x, approved=True) for x in held[:3]])
    if d["judge_color"] != S.C_GREEN or "放行" not in d["sub"]:
        fails.append(f"有放行时没转绿：{d}")

    d = decision([])
    if d["main"] != "0" or d["judge_color"] != S.C_GRAY:
        fails.append(f"无留痕时没走灰：{d}")

    # ── 既有口径不许回退 ──
    ok = dict(S._task_card({"total": 30, "running": 30, "failed_tasks": 0,
                            "total_failure": 0, "last_failure_ts": 0, "last_run_ts": 0}))
    if ok["judge_color"] != S.C_GREEN or ok["main"] != "30":
        fails.append(f"任务全绿判读错了：{ok}")
    dead = dict(S._task_card({"total": 16, "running": 0, "failed_tasks": 6,
                              "total_failure": 857, "last_failure_ts": time.time(),
                              "last_run_ts": 0}))
    if dead["judge_color"] != S.C_RED:
        fails.append("全部未运行没有优先报红")
    # ❗数据源卡已改从 FleetRegistry 取口径（2026-10-20），键是
    #   error_recent / error_historical / stale / unknown，不再是 error 计数。
    def ds_card(**kw):
        base = {"total": 22, "running": 20, "unknown": 0, "active": 20,
                "stale": [], "error_recent": [], "error_historical": [],
                "last_error_ts": 0, "last_success_ts": time.time()}
        base.update(kw)
        return dict(S._datasource_card(base))

    def _card(**kw):
        from deva.naja.infra.observability.fleet_registry import UnitCard, KIND_DATASOURCE
        d = dict(unit_id="x", kind=KIND_DATASOURCE, name="某取数点", source="probe")
        d.update(kw)
        return UnitCard(**d)

    old = ds_card(error_historical=[_card(), _card(), _card()],
                  last_error_ts=time.time() - 199 * 86400)
    if old["judge_color"] != S.C_BLUE:
        fails.append("199 天前的历史错误被报成当前故障")

    # 近期失败必须报红，且点名是哪几个
    bad = ds_card(error_recent=[_card(name="新浪A股行情")],
                  last_error_ts=time.time() - 60)
    if bad["judge_color"] != S.C_RED or "新浪A股行情" not in bad["judge"]:
        fails.append(f"近期采集失败没报红且没点名：{bad['judge']!r}")

    # ❗unknown 是「读不到状态」，绝不能画成异常（红）
    unk = ds_card(unknown=5, running=15)
    if unk["judge_color"] == S.C_RED:
        fails.append("「未观测到调用」被画成红色异常 —— unknown 不等于故障")
    if "未观测到调用" not in unk["judge"]:
        fails.append(f"unknown 数量没说出来：{unk['judge']!r}")

    # running 但久无产出 → 橙
    stl = ds_card(stale=[_card(last_success_ts=time.time() - 30 * 3600)])
    if stl["judge_color"] != S.C_ORANGE or "停更" not in stl["judge"]:
        fails.append(f"停更没报橙：{stl['judge']!r}")

    # 一张登记都没有 → 灰且明说
    empty = ds_card(total=0, running=0, active=0)
    if empty["judge_color"] != S.C_GRAY or empty["main"] != "0":
        fails.append(f"空登记册没有走灰：{empty}")

    # 策略卡：来源构成必须出现在副行（这是「17 个是哪几套凑的」的唯一答案）
    strat = dict(S._strategy_card({
        "total": 31, "running": 15, "output_total": 8, "unknown": 2,
        "by_source": {"strategy_mgr": 17, "hotspot": 14},
    }))
    if "声明式 17" not in strat["sub"] or "热点 14" not in strat["sub"]:
        fails.append(f"策略卡副行没给出来源构成：{strat['sub']!r}")
    if S._ratio(5, 0) != "前期无对比" or S._ratio(0, 0) != "持平":
        fails.append("环比在分母为 0 时编造了百分比")
    if S._money(None) != "—" or S._money(0) != "0":
        fails.append("金额格式把缺失和 0 混为一谈")

    return fails


# ── 负向注入 ─────────────────────────────────────────────────────────────────

INJECTIONS = (
    {
        "name": "账户卡取数失败时填 0（本次事故原状）",
        "old": 'main="—", color=C_GRAY, sub="",\n        judge="组合不可用"',
        "new": 'main="0", color=C_GRAY, sub="",\n        judge="组合不可用"',
    },
    {
        "name": "持仓风险主数字换成持仓总数（停更看不出来）",
        "old": 'card["main"] = str(stale3)',
        "new": 'card["main"] = str(count)',
    },
    {
        "name": "数据源卡删掉「停更」判据（跑着但没数据也显示正常）",
        "old": '    elif stale:\n        card["color"] = C_ORANGE',
        "new": '    elif False:\n        card["color"] = C_ORANGE',
    },
    {
        "name": "把 unknown 画成红色异常（把「不知道」当故障）",
        "old": '        card["judge"] = f"{unknown} 个未观测到调用 · 见下方清单"\n'
               '        card["judge_color"] = C_BLUE',
        "new": '        card["judge"] = f"{unknown} 个未观测到调用 · 见下方清单"\n'
               '        card["judge_color"] = C_RED',
    },
    {
        "name": "策略卡副行丢掉来源构成（看不出 17 个是哪几套凑的）",
        "old": 'f"{label.get(k, k)} {v}"',
        "new": 'f"{v}"',
    },
)


def run_injections() -> int:
    original = STATS.read_text(encoding="utf-8")
    caught = 0
    missed = []
    for inj in INJECTIONS:
        if inj["old"] not in original:
            print(f"  ⚠️ 锚点未命中，跳过：{inj['name']}")
            missed.append(inj["name"])
            continue
        try:
            STATS.write_text(original.replace(inj["old"], inj["new"], 1), encoding="utf-8")
            # ❗必须重载：不重载拿到的是 sys.modules 里的旧对象，
            #   注入的新代码根本没被读进来 → 全绿但什么都没守。
            import importlib
            from deva.naja.home.ui import stats as S
            importlib.reload(S)
            fails = _all_checks()
        finally:
            STATS.write_text(original, encoding="utf-8")
            import importlib
            from deva.naja.home.ui import stats as S2
            importlib.reload(S2)

        if fails:
            caught += 1
            print(f"  ✅ 被捕获：{inj['name']}")
            for f in fails[:2]:
                print(f"       · {str(f)[:110]}")
        else:
            print(f"  ❌ 没抓到 —— 这条注入白做了：{inj['name']}")

    print(f"\n负向注入：{caught}/{len(INJECTIONS)} 被捕获"
          + (f"（{len(missed)} 条锚点未命中，已计失败）" if missed else ""))
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
        print("❌ 首页状态卡守卫 失败：")
        for f in failures:
            print(f"   - {f}")
        return 1 if args.strict else 0

    print("✅ 首页状态卡守卫全绿"
          "（12 卡 3 层 · 缺失写「—」不写 0 · 停更按陈旧只数报 · 决策写出终分/门槛）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
