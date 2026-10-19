"""守卫：价值（企业真实价值）与反转（一致预期极端）探测。

钉住六类「看起来算出来了、其实是假的」问题：

1. **估值两把尺子**：格雷厄姆 ``现价÷√(22.5·EPS·BVPS)`` 与
   ``实际PB÷(ROE×15)``。判定规则是「全部说便宜才算便宜，任一说贵就算贵」，
   防止只挑对自己有利的那把尺子。
2. **拿不到就是 None**：ETF 的 PE/PB 是 ``nan``，绝不能被当成 0 →
   「PE=0，极度低估」是本项目最经典的假信号。
3. **ETF 换口径**：ETF 没有企业价值，只能看对净值的溢折价；
   溢折价 >3% 必须提示「净值可能滞后」，不许当成「便宜 4.7%」。
4. **日线量能**：没有成交量时 ``vol_ratio`` 必须是 None，不能默认 1.0
   （1.0 的意思是「量能正常」，不是「没数据」）。
5. **一致预期对称**：极端悲观 → 向上观察，极端乐观 → 向下风险；
   两者必须镜像。且「极端但没有边际改善」不许标成反转。
6. **页面**：渲染出来的 HTML 里不许出现 ``unknown`` / ``None`` / ``nan``；
   没数据必须写「未采集」并给原因。

两级制：裸跑=提示档(exit 0)，``--strict``=闸门档(exit 1)。
``--exercise-injections`` 会临时改源码注入 bug，验证每条检查真的会红。
"""

from __future__ import annotations

import argparse
import importlib
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

PROBE = ROOT / "deva/naja/attention/kernel/value_reversal_probe.py"
AWAKENING = ROOT / "deva/naja/attention/ui/awakening.py"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------- 1. 估值


def check_yardsticks() -> list:
    """两把尺子的公式与「宁可不说便宜」的判定规则。"""
    failures = []
    from deva.naja.attention.kernel import value_reversal_probe as vr

    # 价格 100 / PE 20 → EPS 5；BVPS 20 → 格雷厄姆 √(22.5×5×20)=47.434
    v = vr.compute_valuation(price=100.0, pe_ttm=20.0, pb=3.0, bvps=20.0, roe=0.15)
    expect_graham = math.sqrt(22.5 * 5.0 * 20.0)
    if v.graham is None or abs(v.graham - expect_graham) > 1e-6:
        failures.append(f"格雷厄姆数算错: {v.graham} ≠ {expect_graham}")
    if v.graham_ratio is None or abs(v.graham_ratio - 100.0 / expect_graham) > 1e-6:
        failures.append(f"格雷厄姆倍数算错（应为 现价÷防守价）: {v.graham_ratio}")
    # 合理 PB = ROE × 15 = 2.25；实际 3.0 → 1.333
    if v.pb_ratio_vs_fair is None or abs(v.pb_ratio_vs_fair - 3.0 / 2.25) > 1e-6:
        failures.append(f"ROE 尺算错（应为 实际PB÷(ROE×15)）: {v.pb_ratio_vs_fair}")
    if v.level != "rich":
        failures.append(f"两把尺子都说贵（2.11× / 1.33×）却判 {v.level}")

    # 一把说便宜（0.88）、一把说贵（2.00）→ 必须算贵，不能挑便宜的那把。
    # ❗比值要真的跨过 0.90 这条线：若两个都 >0.9，"all" 和 "any" 的写法
    #   结果相同，这条用例就抓不到「挑尺子」的 bug。
    mixed = vr.compute_valuation(price=35.0, pe_ttm=10.0, pb=4.5, bvps=20.0, roe=0.15)
    ratios = [r for r in (mixed.graham_ratio, mixed.pb_ratio_vs_fair) if r is not None]
    if len(ratios) < 2:
        failures.append("混合用例没算出两把尺子，用例本身不成立")
    elif not (min(ratios) <= 0.9 and max(ratios) >= 1.5):
        failures.append(f"混合用例不满足「一便宜一贵」前提: {ratios}")
    elif mixed.level != "rich":
        failures.append(f"一把尺子说便宜就判 {mixed.level} —— 挑对自己有利的尺子")

    # 两把都说便宜才行
    cheap = vr.compute_valuation(price=30.0, pe_ttm=10.0, pb=1.5, bvps=20.0, roe=0.15)
    if cheap.level != "cheap":
        failures.append(f"两把尺子都说便宜（价格 30 vs 防守价 ~47 / 合理PB 2.25 vs 1.5）却判 {cheap.level}")
    return failures


# ---------------------------------------------------------------- 2/3. 缺数据与 ETF


def check_missing_and_etf() -> list:
    failures = []
    from deva.naja.attention.kernel import value_reversal_probe as vr

    blank = vr.compute_valuation(price=10.0)
    if blank.level != "unknown":
        failures.append(f"无 PE/BVPS 时判成 {blank.level} —— 缺数据不许有结论")
    if blank.available:
        failures.append("无数据时 available 仍为 True")
    if not blank.missing:
        failures.append("无数据时没写缺哪几项（页面只能显示一个空结论）")
    if blank.graham == 0:
        failures.append("缺数据时 graham 是 0 —— 0 会被下游当成「防守价 0，极度便宜」")

    # ETF：nan 的 PE/PB 不参与，只看净值。±2% 内是申赎成本区间（判 fair）
    etf = vr.compute_valuation(price=0.918, nav=0.94, high_52w=1.694, low_52w=0.702)
    if etf.kind != "etf":
        failures.append(f"有净值却没识别成 ETF: {etf.kind}")
    if etf.level != "cheap":
        failures.append(f"折价 2.3% 应判 cheap，实得 {etf.level}")
    if etf.nav_premium_pct is None or abs(etf.nav_premium_pct + 0.0234) > 0.002:
        failures.append(f"溢折价算错: {etf.nav_premium_pct}")

    # ±2% 以内不叫便宜/贵，那只是申赎套利成本
    flat = vr.compute_valuation(price=0.918, nav=0.936)
    if flat.level != "fair":
        failures.append(f"折价 1.9%（在 2% 套利成本内）应判 fair，实得 {flat.level}")

    lag = vr.compute_valuation(price=709.8, nav=744.5)
    if not any("滞后" in note for note in lag.notes):
        failures.append("溢折价 4.7% 没有提示「净值可能滞后」—— 会被当成便宜 4.7%")

    # PE=0 / nan / 负 PE 都不能当便宜
    nan_pe = vr.compute_valuation(price=100.0, pe_ttm=float("nan"), bvps=20.0, roe=0.15)
    if nan_pe.pe_ttm is not None:
        failures.append("nan 的 PE 被保留下来了（应转成 None）")
    if nan_pe.level == "cheap":
        failures.append("PE 为 nan 却判成便宜 —— 把缺数据当成了低估值")
    return failures


# ---------------------------------------------------------------- 4. 日线


def check_position() -> list:
    failures = []
    from deva.naja.attention.kernel import value_reversal_probe as vr

    up = [float(i) for i in range(1, 40)]
    down = [float(i) for i in range(40, 1, -1)]
    rsi_up = vr.compute_rsi(up)
    rsi_down = vr.compute_rsi(down)
    # ❗别写 `(value or 0)`：RSI=0.0 是 falsy，会被当成「没算出来」→ 假失败
    if rsi_up is None or abs(rsi_up - 100.0) > 1e-6:
        failures.append(f"单边上涨 RSI 应为 100，实得 {rsi_up}")
    if rsi_down is None or abs(rsi_down - 0.0) > 1e-6:
        failures.append(f"单边下跌 RSI 应为 0，实得 {rsi_down}")
    if vr.compute_rsi([1.0, 2.0, 3.0]) is not None:
        failures.append("数据不足 14 日却给了 RSI（应 None）")

    closes = [100.0] * 60 + [95.0, 90.0, 85.0]
    pos = vr.compute_position(closes)
    if pos["drawdown60"] is None or abs(pos["drawdown60"] + 0.15) > 1e-9:
        failures.append(f"60 日回撤算错: {pos['drawdown60']}（应为 -0.15）")
    if pos["vol_ratio"] is not None:
        failures.append(f"没有成交量却给了量能比 {pos['vol_ratio']}（None≠1.0）")
    if pos["level"] != "mid":
        failures.append(f"回撤 15% 应判 mid，实得 {pos['level']}")

    empty = vr.compute_position([])
    if empty["level"] != "unknown" or empty["drawdown60"] is not None:
        failures.append("空日线序列没有降级成 unknown/None")
    return failures


# ---------------------------------------------------------------- 5. 一致预期


def _consensus(vr, side: str, **over):
    """构造极端悲观 / 极端乐观用例。"""
    if side == "pessimistic":
        args = dict(
            valuation={"pos_52w": 0.02},
            position={"drawdown60": -0.28, "rsi14": 22, "rsi14_prev": 18,
                      "vol_ratio": 0.70, "close": 86, "ma20": 95},
            news={"sample_ok": True, "neg_ratio": 0.85, "neg_trend": -0.2},
            panic={"panic_score": 80, "delta_breadth": 0.05},
        )
    elif side == "optimistic_deteriorating":
        args = dict(
            valuation={"pos_52w": 0.98},
            position={"drawdown60": -0.01, "rsi14": 78, "rsi14_prev": 84,
                      "vol_ratio": 1.3, "close": 120, "ma20": 130},
            news={"sample_ok": True, "neg_ratio": 0.05, "neg_trend": 0.3},
            panic={"panic_score": 5, "delta_breadth": -0.05},
        )
    else:  # optimistic_calm：极端乐观，但没有任何恶化证据
        args = dict(
            valuation={"pos_52w": 0.98},
            position={"drawdown60": -0.01, "rsi14": 70, "rsi14_prev": 60,
                      "vol_ratio": 0.90, "close": 150, "ma20": 130},
            news={"sample_ok": True, "neg_ratio": 0.05, "neg_trend": -0.1},
            panic={"panic_score": 5, "delta_breadth": 0.05},
        )
    args.update(over)
    return vr.evaluate_consensus(**args)


def check_consensus() -> list:
    failures = []
    from deva.naja.attention.kernel import value_reversal_probe as vr

    pess = _consensus(vr, "pessimistic")
    opt = _consensus(vr, "optimistic_deteriorating")
    calm = _consensus(vr, "optimistic_calm")

    if pess["direction"] != 1:
        failures.append(f"极端悲观应向上观察（direction=1），实得 {pess['direction']}")
    if opt["direction"] != -1:
        failures.append(f"极端乐观应向下风险（direction=-1），实得 {opt['direction']}")
    if pess.get("pessimism") is None or opt.get("pessimism") is None:
        failures.append("极端用例没算出悲观度")
    else:
        total = float(pess["pessimism"]) + float(opt["pessimism"])
        if not (95.0 <= total <= 105.0):
            failures.append(f"悲观/乐观不对称（两者之和 {total:.1f}，应≈100）")

    if not pess["watch"]:
        failures.append("极端悲观 + 4 条边际改善，却没标成「观察」")
    if not opt["watch"]:
        failures.append("极端乐观 + 5 条恶化证据，却没标成「风险确认」")
    if calm["watch"]:
        failures.append("极端乐观但零恶化证据，仍标成「值得盯」—— 极端被当成反转")

    # 方向触发器必须按侧切换，否则乐观侧的「改善」是反义词
    if pess["trigger_side"] != "improvement":
        failures.append(f"悲观侧触发器类型错: {pess['trigger_side']}")
    if opt["trigger_side"] != "deterioration":
        failures.append(f"乐观侧触发器类型错: {opt['trigger_side']}（应看恶化）")

    # 机会永远是 False：只读判断不许变成仓位建议
    for name, res in (("悲观", pess), ("乐观", opt)):
        if res.get("opportunity"):
            failures.append(f"{name}用例给出了 opportunity=True —— 价值判断不许当放行")

    # 极端但没有边际改善 → 不许标「观察」
    stale = _consensus(
        vr, "pessimistic",
        position={"drawdown60": -0.28, "rsi14": 22, "rsi14_prev": 26,
                  "vol_ratio": 1.3, "close": 80, "ma20": 95},
        news={"sample_ok": True, "neg_ratio": 0.85, "neg_trend": 0.4},
        panic={"panic_score": 80, "delta_breadth": -0.05},
    )
    if stale["watch"]:
        failures.append("极端悲观但零边际改善，仍标成「观察」—— 极端被当成反转")
    if "未见转机" not in stale["label"]:
        failures.append("极端但无改善时没写「未见转机」，页面读起来像已经反转了")

    # 缺维时不许编数据
    empty = vr.evaluate_consensus()
    if empty["pessimism"] is not None:
        failures.append("全维缺失仍算出悲观度（凭空造数）")
    if empty["label"] != "未采集":
        failures.append(f"全维缺失的文案是「{empty['label']}」，应为「未采集」")
    if not empty["dimensions_missing"]:
        failures.append("全维缺失没列出缺哪些维度")
    return failures


# ---------------------------------------------------------------- 6. 新闻


def check_news() -> list:
    failures = []
    from deva.naja.attention.kernel import value_reversal_probe as vr

    if vr.score_text("公司下调指引，分析师下调评级") >= 0:
        failures.append("负面词表打分不为负")
    if vr.score_text("上调目标价并宣布回购") <= 0:
        failures.append("正面词表打分不为正")
    if vr.score_text("今日天气晴") != 0:
        failures.append("无极性文本应得 0（0=无方向，不是中性 0.5）")

    items = [
        {"title": "英伟达下调指引", "text": "", "timestamp": 1000.0, "stock_codes": ["NVDA"]},
        {"title": "英伟达遭调查", "text": "", "timestamp": 1001.0, "stock_codes": ["NVDA"]},
    ]
    thin = vr.news_tone(items, ["NVDA"], now=2000.0, window_hours=72)
    if thin["tone"] != "no_signal":
        failures.append(f"只有 2 条相关新闻却给了结论 {thin['tone']}（样本不足应无结论）")
    if thin.get("sample_ok"):
        failures.append("2 条样本被当成足够")

    many = [
        {"title": "英伟达下调指引", "text": "", "timestamp": 1900.0, "stock_codes": ["NVDA"]},
        {"title": "英伟达遭调查", "text": "", "timestamp": 1910.0, "stock_codes": ["NVDA"]},
        {"title": "英伟达裁员", "text": "", "timestamp": 1920.0, "stock_codes": ["NVDA"]},
        {"title": "英伟达被罚款", "text": "", "timestamp": 1930.0, "stock_codes": ["NVDA"]},
    ]
    tone = vr.news_tone(many, ["NVDA"], now=2000.0, window_hours=72)
    if tone["tone"] != "negative":
        failures.append(f"4 条全负面却判 {tone['tone']}")
    if tone["neg_ratio"] is None or abs(tone["neg_ratio"] - 1.0) > 1e-9:
        failures.append(f"负面占比算错: {tone['neg_ratio']}")

    empty = vr.news_tone([], ["NVDA"], now=2000.0)
    if empty["neg_ratio"] is not None:
        failures.append("没有新闻却给出负面占比（None 才对）")
    if empty["tone"] != "no_signal":
        failures.append("没有新闻却给了语气结论")

    # 窗口过滤：72h（=259200s）之外的旧闻不算。now 必须离 ts 足够远，
    # 否则 cutoff 落到负数，什么都能通过 —— 用例自己先假绿。
    old = vr.news_tone(
        [{"title": "英伟达下调指引", "text": "", "timestamp": 1.0, "stock_codes": ["NVDA"]}] * 3,
        ["NVDA"], now=1_000_000.0, window_hours=72,
    )
    if old["n"] != 0:
        failures.append(f"72 小时窗口外的旧闻被计入（n={old['n']}）")
    return failures


# ---------------------------------------------------------------- 7. 页面


_STUB = {
    "ok": True,
    "as_of": 1792380000.0,
    "news_updated": 1792380000.0,
    "targets": 2,
    "errors": [],
    "reason": "",
    "rows": [
        {
            "code": "NVDA", "name": "英伟达", "price": 214.13,
            "valuation": {"kind": "stock", "level": "rich", "graham_ratio": 5.21,
                          "pb_ratio_vs_fair": 2.91, "notes": ["测试"], "missing": []},
            "position": {"level": "deep", "drawdown60": -0.21, "rsi14": 22.0,
                         "dev20": -0.09, "vol_ratio": 0.78},
            "news": {"tone": "negative", "n": 6, "scored": 5, "neg_ratio": 0.8,
                     "sample_ok": True, "neg_trend": -0.2, "headlines": ["利空"]},
            "consensus": {"label": "极端悲观·阴极生阳观察", "direction": 1, "watch": True,
                          "pessimism": 82.0, "crowding": 64.0, "triggers_hit": 3,
                          "triggers_total": 5, "dimensions_missing": [],
                          "triggers": [{"name": "RSI 回升", "hit": True}]},
        },
        {
            "code": "588200", "name": "科创芯片ETF", "price": 0.922,
            "valuation": {"kind": "etf", "level": "cheap", "nav_premium_pct": -0.025},
            "position": {"level": "deep", "drawdown60": -0.317, "rsi14": 5.0,
                         "dev20": -0.141, "vol_ratio": 1.07},
            "news": {"tone": "no_signal", "n": 1, "scored": 0, "sample_ok": False,
                     "headlines": []},
            "consensus": {"label": "多空分歧·无一致预期", "direction": 0, "watch": False,
                          "pessimism": 60.0, "crowding": 21.0, "triggers_hit": 0,
                          "triggers_total": 3, "dimensions_missing": [],
                          "triggers": []},
        },
    ],
}


def check_page() -> list:
    failures = []
    try:
        from deva.naja.attention.kernel import value_reversal_probe as vr
        from deva.naja.attention.ui import awakening as A

        vr.probe_watchlist = lambda **_kw: _STUB
        html = A._render_value_reversal({})
        vr.probe_watchlist = lambda **_kw: {
            "ok": False, "rows": [], "reason": "OpenD 未运行",
            "errors": ["NVDA: 连不上 OpenD"],
        }
        degraded = A._render_value_reversal({})
    except Exception as exc:  # noqa: BLE001
        return [f"渲染抛异常: {type(exc).__name__}: {exc}"]
    finally:
        importlib.reload(sys.modules["deva.naja.attention.kernel.value_reversal_probe"])

    for label in ("价值与反转", "高于价值带", "深跌", "偏空", "阴极生阳", "折价 2.5%", "题材级"):
        if label not in html:
            failures.append(f"卡片里没有「{label}」")
    for bad in ("unknown", "None", "nan", "折价 -"):
        if bad in html:
            failures.append(f"卡片里出现了内部枚举/空值「{bad}」")
    if "样本不足" not in html:
        failures.append("新闻样本不足时没有如实写「样本不足」")

    if "未采集" not in degraded or "OpenD 未运行" not in degraded:
        failures.append("取不到数据时没有「未采集 + 原因」")
    return failures


# ---------------------------------------------------------------- 8. 只读


def check_read_only() -> list:
    """模块与页面都不许有下单/改判定的调用。"""
    failures = []
    src = _text(PROBE)
    for token in ("place_order", "submit_order", "execution.submit", "action_type", "publish("):
        if token in src:
            failures.append(f"探测模块里出现「{token}」—— 价值判断不该能下单或改判定")
    if "size_hint" in src:
        failures.append("探测模块里出现 size_hint —— 不许给仓位建议")
    return failures


def _all_checks() -> list:
    failures = []
    for fn in (
        check_yardsticks,
        check_missing_and_etf,
        check_position,
        check_consensus,
        check_news,
        check_page,
        check_read_only,
    ):
        try:
            failures.extend(fn())
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{fn.__name__} 抛异常: {type(exc).__name__}: {exc}")
    return failures


INJECTIONS = [
    {
        "name": "格雷厄姆倍数写反（防守价÷现价）",
        "path": PROBE,
        "old": "        v.graham_ratio = price / v.graham",
        "new": "        v.graham_ratio = v.graham / price",
    },
    {
        "name": "判定改成「任一便宜就算便宜」",
        "path": PROBE,
        "old": "        if all(r <= 0.90 for r in ratios):",
        "new": "        if any(r <= 0.90 for r in ratios):",
    },
    {
        "name": "ETF 溢折价不提示净值滞后",
        "path": PROBE,
        "old": '        if abs(v.nav_premium_pct) > 0.03:\n            v.notes.append("溢折价超过 3%，大概率是 NAV 滞后，须核对当日净值再采信")',
        "new": '        if False:\n            v.notes.append("溢折价超过 3%，大概率是 NAV 滞后，须核对当日净值再采信")',
    },
    {
        "name": "缺成交量时量能比默认 1.0",
        "path": PROBE,
        "old": "    if volumes and len(volumes) >= 20:",
        "new": "    volumes = volumes or [1.0] * 20\n    if volumes and len(volumes) >= 20:",
    },
    {
        "name": "新闻样本不足也给结论",
        "path": PROBE,
        "old": '    if not out["sample_ok"]:\n        return out',
        "new": '    if False:\n        return out',
    },
    {
        "name": "反转只看极端、不看边际改善",
        "path": PROBE,
        "old": '    out["watch"] = bool(out["direction"] != 0 and out["triggers_hit"] >= 2)',
        "new": '    out["watch"] = bool(out["direction"] != 0)',
    },
    {
        "name": "页面把「未采集」写成 0",
        "path": AWAKENING,
        "old": "                未采集：{escape(str(reason))}{escape(detail)}",
        "new": "                0：{escape(str(reason))}{escape(detail)}",
    },
]


def _reload():
    for name in (
        "deva.naja.attention.kernel.value_reversal_probe",
        "deva.naja.attention.ui.awakening",
    ):
        mod = sys.modules.get(name)
        if mod is not None:
            importlib.reload(mod)


def run_injections() -> int:
    caught = 0
    missed = []
    for inj in INJECTIONS:
        path = inj["path"]
        original = path.read_text(encoding="utf-8")
        hits = original.count(inj["old"])
        if hits != 1:
            missed.append(inj["name"])
            print(f"❌ 注入锚点命中 {hits} 次（期望 1，守卫腐烂信号）：{inj['name']}")
            continue
        print(f"· 注入：{inj['name']}")
        path.write_text(original.replace(inj["old"], inj["new"]), encoding="utf-8")
        try:
            _reload()
            found = _all_checks()
        except Exception as exc:  # noqa: BLE001
            found = [f"守卫自身抛异常: {type(exc).__name__}: {exc}"]
        finally:
            path.write_text(original, encoding="utf-8")
            _reload()
        if found:
            caught += 1
            print(f"  ✅ 被捕获（{len(found)} 项）")
            print(f"       · {found[0][:110]}")
        else:
            print("  ❌ 没抓到 —— 这条守卫是摆设！")
        if path.read_text(encoding="utf-8") != original:
            print("  🚨 还原失败，强制重写")
            path.write_text(original, encoding="utf-8")
    print(f"\n负向注入：{caught}/{len(INJECTIONS)} 被捕获"
          + (f"（另有 {len(missed)} 条锚点未命中，已计失败）" if missed else ""))
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
        print("❌ 价值与反转 守卫 失败：")
        for f in failures:
            print(f"   - {f}")
        return 1 if args.strict else 0
    print("✅ 价值两把尺子 · 缺数据不造假 · ETF 换口径 · 日线量能 · 一致预期对称 · 页面诚实 全绿")
    return 0


if __name__ == "__main__":
    sys.exit(main())
