#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""守卫：OpenRouter / TOKEN 消耗监控的数据口径与渲染诚实度。

背景（2026-10-19）
----------------
用户在面板上看到「周消耗 824.17B / 周环比 -20.0% / 趋势方向 ❓未知」，
三格数字全都站不住：

① **数据源是日频，代码全程当周频**。``weekly_history`` 里相邻日期差恒为 1 天，
   而变量名、文案、判断逻辑都按"一周一个点"写。后果：
   - 「周消耗 824.17B」实为**单日**，真实周量 ≈ 6.8T，**差 8.3 倍**；
   - 「周环比 -20%」实为**日环比**，且是周六比周五 —— 周末用量天生低，
     这 -20% 里约 12pp 是日历效应，不是需求下滑；
   - 「本周未完」用 ``days_since_latest <= 6`` 判断，把最新一天整条丢掉。
② **枚举失配**：分析层产出 ``strong_up/up/down/strong_down``，UI 映射表只认
   ``rising/falling/stable`` → 落默认值 → 方向**永远显示 ❓未知**。
   同一份 UI 里 ``AlertLevel.ATTENTION`` 也没有映射 → 告警显示「⚪ 未知」。
   这类错**不抛异常**，只是安静地把"算出 down"渲染成"不知道"。
③ **静默空 + 假新鲜**：缓存停在 2026-05-11 整整 160 天。日志里每天都是
   ``GET /rankings 200``，但解析 0 条（页面结构变了），失败走 ``logger.debug``，
   谁也不知道。而 ``is_stale`` 只在写入时算过，读取时不再重算 —— 躺着 160 天
   也照样显示「正常」。

④ **第二次口径事故（同日稍后）**：把源改判为"日频"后才发现，
   2026-10 起该页面给的是**周桶**（每点 = 7 天，以周一为起点），且每点带
   ``Others`` 残差桶 = 全站周总量。而最后一个桶通常是"本周未完"（实测
   4.52T vs 完整周 164T）—— 若直接和上一周比，会得出 **-97% 的假崩盘**。

   结论：**粒度不许写死任何一边**。必须由数据自身相邻间隔推断（7→周、1→日），
   分析层按 ``period_days`` 统一处理，UI 按 ``granularity`` 换标签。
   本守卫同时钉住「周频」和「日频」两条路径，任一侧退化都必须报红。

本守卫钉住这几类回退，并要求 ``--exercise-injections`` 全部被抓到。

用法
----
    python scripts/verify/verify_openrouter_monitor.py
    python scripts/verify/verify_openrouter_monitor.py --strict
    python scripts/verify/verify_openrouter_monitor.py --exercise-injections
"""

from __future__ import annotations

import argparse
import ast
import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OM_PY = ROOT / "deva/naja/cognition/openrouter_monitor.py"
TM_PY = ROOT / "deva/naja/cognition/ui/components/token_monitor.py"
TASK_YAML = ROOT / "deva/config/tasks/openrouter_monitor.yaml"

OM_NAME = "deva.naja.cognition.openrouter_monitor"
TM_NAME = "deva.naja.cognition.ui.components.token_monitor"

# 真实缓存里 05-01 ~ 05-10 的十天用量（确定性夹具，不读 NB）
_DAYS = [
    ("2026-05-01", 900219329162),
    ("2026-05-02", 1029513124829),
    ("2026-05-03", 891296757496),
    ("2026-05-04", 984116220661),
    ("2026-05-05", 1112524991331),
    ("2026-05-06", 1115169562829),
    ("2026-05-07", 1005738010663),
    ("2026-05-08", 1030535591495),
    ("2026-05-09", 824168787494),
    ("2026-05-10", 877258280496),
]


def _mod(name):
    return importlib.import_module(name)


def _om():
    return _mod(OM_NAME)


def _tm():
    return _mod(TM_NAME)


def _reload():
    importlib.reload(_mod(OM_NAME))
    importlib.reload(_mod(TM_NAME))


def _src(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _func_node(path: Path, name: str):
    tree = ast.parse(_src(path))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def _calls_in(path: Path, func_name: str) -> list:
    """函数体内被调用的名字（属性访问取最后一段）"""
    node = _func_node(path, func_name)
    if node is None:
        return []
    names = []
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            f = child.func
            if isinstance(f, ast.Name):
                names.append(f.id)
            elif isinstance(f, ast.Attribute):
                names.append(f.attr)
    return names


def _dict_literal(path: Path, func_name: str, var_name: str):
    """取函数里 ``var_name = { ... }`` 的字典节点"""
    node = _func_node(path, func_name)
    if node is None:
        return None
    for child in ast.walk(node):
        if isinstance(child, ast.Assign):
            for target in child.targets:
                if isinstance(target, ast.Name) and target.id == var_name:
                    if isinstance(child.value, ast.Dict):
                        return child.value
    return None


# ── ① 粒度不许写死：必须从数据自身推断 ────────────────────────────────────────
def check_granularity_constants() -> list:
    OM = _om()
    failures = []
    src = _src(OM_PY)

    # 曾经写死过 GRANULARITY = "daily" / "weekly"，两次都造成量级错误
    for bad in ('GRANULARITY = "daily"', 'GRANULARITY = "weekly"', "GRANULARITY = 'daily'", "GRANULARITY = 'weekly'"):
        if bad in src:
            failures.append(f"源码里仍有写死的 {bad!r} —— 粒度必须由 detect_granularity() 推断")

    if not hasattr(OM, "detect_granularity"):
        failures.append("缺少 detect_granularity()，粒度无法自证")

    if getattr(OM, "WEEK_DAYS", None) != 7:
        failures.append(f"WEEK_DAYS 应为 7，实得 {getattr(OM, 'WEEK_DAYS', None)!r}")

    grace = getattr(OM, "STALE_GRACE_DAYS", None)
    if not isinstance(grace, int) or not (0 <= grace <= 5):
        failures.append(f"STALE_GRACE_DAYS={grace!r} 不在 0~5（过大=陈旧看不见，过小=天天误报）")

    # 陈旧阈值必须由周期长度派生，不能是一个与粒度无关的常数
    if "STALE_THRESHOLD_DAYS" in src:
        failures.append("仍存在与粒度无关的 STALE_THRESHOLD_DAYS —— 周频会被日频阈值误伤")

    values = set(getattr(OM, "DIRECTION_VALUES", ()))
    if values != {"strong_up", "up", "flat", "down", "strong_down", "unknown"}:
        failures.append(f"DIRECTION_VALUES 不是约定的 6 值，实得 {sorted(values)}")

    if not getattr(OM, "RANKINGS_CHART_API", "").endswith("/model-rankings-chart"):
        failures.append("RANKINGS_CHART_API 不是 model-rankings-chart 接口 —— 又回去正则扒 HTML 了")
    return failures


# ── ①b 粒度自证：同一份代码必须同时认对周频与日频 ─────────────────────────────
def _weekly_fixture():
    """13 个完整周 + 1 个「本周未完」桶（日期相对今天，跨月/跨年都成立）"""
    from datetime import date as _d, timedelta as _t
    today = _d.today()
    monday = today - _t(days=today.weekday())
    vals = [58.04, 56.79, 69.05, 75.34, 93.38, 113.00, 115.46,
            126.76, 128.90, 145.85, 165.86, 171.84, 164.04]
    pts = []
    for i, v in enumerate(vals):
        d = monday - _t(weeks=len(vals) - i)
        pts.append({"date": d.isoformat(), "total": int(v * 1e12)})
    pts.append({"date": monday.isoformat(), "total": int(4.52e12)})  # 本周未完
    return pts


def check_granularity_autodetect() -> list:
    OM = _om()
    failures = []

    wk = OM.detect_granularity(_weekly_fixture())
    if wk != "weekly":
        failures.append(f"周桶序列被识别成 {wk!r}（应为 weekly）—— 会把整周的量当 1 天")

    dy = OM.detect_granularity([{"date": d, "total": t} for d, t in _DAYS])
    if dy != "daily":
        failures.append(f"日序列被识别成 {dy!r}（应为 daily）—— 会把 1 天当 1 周")

    # 间隔不规则必须如实说不知道，不许二选一蒙一个
    odd = [
        {"date": "2026-01-01", "total": 10},
        {"date": "2026-01-04", "total": 10},
        {"date": "2026-01-05", "total": 10},
        {"date": "2026-01-12", "total": 10},
    ]
    if OM.detect_granularity(odd) != "unknown":
        failures.append("间隔不规则的序列没有返回 unknown —— 会静默套用错误周期")
    return failures


# ── ①c 「本周未完」桶必须剔除，且不许参与环比 ──────────────────────────────────
def check_incomplete_period_excluded() -> list:
    OM = _om()
    failures = []
    pts = _weekly_fixture()
    res = OM.analyze_trend(pts)

    last_complete = int(164.04e12)
    if res.get("latest_total") != last_complete:
        failures.append(
            f"latest_total 应为最近完整周 {last_complete}，实得 {res.get('latest_total')} "
            f"—— 「本周未完」的 {int(4.52e12)} 没有被剔除"
        )

    exp = (164.04 - 171.84) / 171.84 * 100
    if res.get("latest_change") is None or abs(res["latest_change"] - exp) > 0.05:
        failures.append(f"周环比应为 {exp:.2f}%，实得 {res.get('latest_change')} —— 被残缺周带偏了")

    if res.get("latest_change") is not None and res["latest_change"] <= -50:
        failures.append("周环比出现 -50% 以上的跌幅 —— 典型的「拿残缺周比完整周」假崩盘")

    if not res.get("is_incomplete_period"):
        failures.append("没有标记 is_incomplete_period，面板无法提示「本周未完」")
    if res.get("incomplete_total") != int(4.52e12):
        failures.append(f"incomplete_total 应记录残缺周已录值，实得 {res.get('incomplete_total')}")

    if abs((res.get("period_days") or 0) - 7) > 0:
        failures.append(f"周频数据的 period_days 应为 7，实得 {res.get('period_days')}")
    return failures


# ── ② 禁止「按自然周边界截断」这类写死判据回流 ─────────────────────────────────
def check_no_daily_as_weekly() -> list:
    failures = []
    src = _src(OM_PY)

    # 旧实现用 days_since_latest <= 6 判断"本周未完"，结果把最新一天整条丢掉
    for marker in ("days_since_latest", "current_weekday"):
        if marker in src:
            failures.append(
                f"源码里仍有 {marker!r} —— 这是「按自然周猜边界」的旧判据（曾丢最新一天）"
            )

    # 周期起止必须由 period_days 派生，不许出现 isoweekday/weekday() 之类的手写边界
    if "isoweekday()" in src:
        failures.append("源码里用 isoweekday() 手算周期边界 —— 应由 period_days 统一派生")

    # 「未走完的周期」必须有显式剔除，而不是靠调用方自觉
    if "_period_end(" not in src:
        failures.append("缺少 _period_end 派生函数 —— 周期结束日算不出来，陈旧度和残缺判断都会错")

    # 周频 / 日频两条路径的字段都必须在
    for field in ("rolling_7d", "same_weekday", "week_over_week", "period_days"):
        if field not in src:
            failures.append(f"分析层缺少 {field!r} 口径字段")
    return failures


# ── ③ 行为：日量 / 7 日滚动 / 同星期环比必须分离 ────────────────────────────────
def check_metric_separation() -> list:
    OM = _om()
    failures = []

    data = [{"date": d, "total": t} for d, t in _DAYS]
    res = OM.analyze_trend(data)

    latest_expected = _DAYS[-1][1]
    if res.get("latest_total") != latest_expected:
        failures.append(f"latest_total 应是最新一天的 {latest_expected}，实得 {res.get('latest_total')}")

    roll_expected = sum(t for _, t in _DAYS[-7:])
    if res.get("rolling_7d") != roll_expected:
        failures.append(f"rolling_7d 应是最近 7 天之和 {roll_expected}，实得 {res.get('rolling_7d')}")

    wow_expected = (_DAYS[-1][1] - _DAYS[-8][1]) / _DAYS[-8][1] * 100
    if res.get("latest_change") is None or abs(res["latest_change"] - wow_expected) > 0.05:
        failures.append(
            f"latest_change 应是同星期环比 {wow_expected:.2f}%，实得 {res.get('latest_change')} "
            "—— 它被日环比顶替了"
        )

    daily_expected = (_DAYS[-1][1] - _DAYS[-2][1]) / _DAYS[-2][1] * 100
    if res.get("daily_change_pct") is None or abs(res["daily_change_pct"] - daily_expected) > 0.05:
        failures.append(f"daily_change_pct 应是日环比 {daily_expected:.2f}%，实得 {res.get('daily_change_pct')}")

    if res.get("latest_change") is not None and res.get("daily_change_pct") is not None:
        if abs(res["latest_change"] - res["daily_change_pct"]) < 1.0:
            failures.append("同星期环比与日环比几乎相等 —— 两种口径没有真正分开")

    if res.get("data_days") != len(_DAYS):
        failures.append(f"data_days 应为 {len(_DAYS)}，实得 {res.get('data_days')}")
    if res.get("data_weeks") != 3:
        failures.append(f"data_weeks 应是完整 7 日窗口的环比点数 3，实得 {res.get('data_weeks')}")

    # 这 10 天去季节后是横盘（滚动均值 -0.4%），旧实现却报 down
    if res.get("direction") != "flat":
        failures.append(f"10 天数据去季节后应判 flat（滚动均值约 -0.4%），实得 {res.get('direction')!r}")
    return failures


# ── ④ 数据不足必须诚实 ───────────────────────────────────────────────────────
def check_insufficient_is_honest() -> list:
    OM = _om()
    failures = []

    empty = OM.analyze_trend([])
    if empty.get("direction") != "unknown":
        failures.append(f"空输入应返回 unknown，实得 {empty.get('direction')!r}")
    if "无数据" not in (empty.get("message") or ""):
        failures.append(f"空输入没有写明原因，message={empty.get('message')!r}")
    if not empty.get("is_stale"):
        failures.append("空输入应判为陈旧")
    if "stable" in str(empty.get("direction")):
        failures.append("空输入被伪装成 stable")

    one = OM.analyze_trend([{"date": _DAYS[0][0], "total": _DAYS[0][1]}])
    if one.get("direction") != "unknown":
        failures.append(f"只有 1 天数据也应 unknown（可比点不足），实得 {one.get('direction')!r}")

    # 读取时按当前时刻重算年龄：160 天前必须判陈旧
    fresh = OM._freshness_fields("2026-05-10")
    if not fresh.get("is_stale"):
        failures.append("_freshness_fields 对 2026-05-10 未判陈旧 —— 年龄没有在读取时重算")
    if not isinstance(fresh.get("data_age_days"), int) or fresh["data_age_days"] < 30:
        failures.append(f"data_age_days 异常：{fresh.get('data_age_days')}")

    today = OM._freshness_fields(__import__("datetime").date.today().isoformat())
    if today.get("is_stale"):
        failures.append("当天数据被判陈旧 —— 门禁方向反了，会天天误报")
    return failures


# ── ⑤ 枚举全覆盖（分析层产出 ⊆ UI 映射） ───────────────────────────────────────
def check_enum_coverage() -> list:
    OM, TM = _om(), _tm()
    failures = []

    ui_dirs = set(getattr(TM, "DIRECTION_STYLE", {}))
    missing = set(OM.DIRECTION_VALUES) - ui_dirs
    if missing:
        failures.append(f"UI DIRECTION_STYLE 缺少方向值 {sorted(missing)} —— 会静默落成「未知」")

    alerts = {lv.value for lv in OM.AlertLevel}
    ui_alerts = set(getattr(TM, "ALERT_STYLE", {}))
    missing_alert = alerts - ui_alerts
    if missing_alert:
        failures.append(f"UI ALERT_STYLE 缺少告警级别 {sorted(missing_alert)} —— 会显示「未知级别」")

    # get_ai_compute_trend 的对外枚举也必须被 UI 覆盖
    node = _dict_literal(OM_PY, "get_ai_compute_trend", "trend_direction_map")
    if node is None:
        failures.append("找不到 trend_direction_map（锚点失效）")
    else:
        produced = {v.value for v in node.values if isinstance(v, ast.Constant)}
        ui_trend = set(getattr(TM, "TREND_DIR_STYLE", {}))
        missing_trend = produced - ui_trend
        if missing_trend:
            failures.append(f"UI TREND_DIR_STYLE 缺少 {sorted(missing_trend)}")

    if len(ui_dirs) < 6:
        failures.append(f"DIRECTION_STYLE 只有 {len(ui_dirs)} 项（应覆盖 6 值）")
    return failures


# ── ⑥ unknown 不许伪装成 stable ──────────────────────────────────────────────
def check_unknown_not_disguised() -> list:
    failures = []
    node = _dict_literal(OM_PY, "get_ai_compute_trend", "trend_direction_map")
    if node is None:
        return ["找不到 trend_direction_map（锚点失效）"]

    mapping = {}
    for k, v in zip(node.keys, node.values):
        if isinstance(k, ast.Constant) and isinstance(v, ast.Constant):
            mapping[k.value] = v.value

    if mapping.get("unknown") != "unknown":
        failures.append(
            f"trend_direction_map['unknown'] = {mapping.get('unknown')!r}"
            " —— 把「算不出来」伪装成「稳定」，下游会当成真信号"
        )
    return failures


# ── ⑦ 渲染全覆盖：6 方向 × 4 告警，不许出现兜底「未知」 ──────────────────────────
def _fake_trend(**kw):
    base = {
        "granularity": "daily",
        "period_days": 1,
        "period_label": "日",
        "direction": "down",
        "strength": 0.04,
        "acceleration": 0.0,
        "is_anomaly": False,
        "anomaly_type": "",
        "message": "m",
        "recommendation": "r",
        "alert_level": "normal",
        "latest_date": "2026-05-10",
        "latest_total": 877258280496,
        "latest_total_formatted": "877.26B",
        "daily_change_pct": 6.44,
        "latest_change": -1.58,
        "wow_same_weekday_pct": -1.58,
        "wow_base_total": 891296757496,
        "wow_base_formatted": "891.30B",
        "rolling_7d": 6949500000000,
        "rolling_7d_formatted": "6.95T",
        "rolling_7d_change_pct": -0.2,
        "rolling_window_days": 7,
        "rolling_window_complete": True,
        "rolling_window_missing_days": 0,
        "trend_basis": "same_weekday",
        "trend_points": 3,
        "trend_confidence": "low",
        "recent_avg_change": -0.4,
        "data_days": 10,
        "data_points": 10,
        "data_weeks": 3,
        "data_age_days": 0,
        "is_stale": False,
        "stale_threshold_days": 3,
        "comparable_points": 3,
        "momentum_conflict": "",
        "is_incomplete_period": False,
        "incomplete_total": None,
        "incomplete_total_formatted": "N/A",
        "previous_total": 891296757496,
        "previous_total_formatted": "891.30B",
        "top_models": [],
        "other_share_pct": None,
        "last_success_ts": "2026-05-11T16:32:30",
        "last_error": "",
        "consecutive_failures": 0,
        "parse_count": 110,
    }
    base.update(kw)
    return base


def _fake_weekly(**kw):
    """周频样本：真实 2026-10-12 那期（164.04T，环比 -4.54%，涨势逆转）"""
    base = _fake_trend(
        granularity="weekly",
        period_days=7,
        period_label="周",
        direction="strong_up",
        strength=0.6485,
        alert_level="attention",
        latest_date="2026-10-12",
        latest_period_end="2026-10-18",
        latest_total=164_040_000_000_000,
        latest_total_formatted="164.04T",
        previous_total=171_840_000_000_000,
        previous_total_formatted="171.84T",
        latest_change=-4.54,
        change_basis="week_over_week",
        trend_basis="week_over_week",
        wow_same_weekday_pct=None,
        rolling_7d=164_040_000_000_000,
        rolling_7d_formatted="164.04T",
        rolling_7d_change_pct=-4.54,
        is_incomplete_period=True,
        incomplete_total=int(4.52e12),
        incomplete_total_formatted="4.52T",
        data_points=53,
        data_weeks=52,
        comparable_points=51,
        momentum_conflict="trend_up_latest_down",
        stale_threshold_days=9,
        top_models=[
            {"name": "Others", "tokens": 67_470_000_000_000, "formatted": "67.47T", "share_pct": 41.1},
            {"name": "deepseek/deepseek-v4.1-flash-20260910", "tokens": 32_830_000_000_000, "formatted": "32.83T", "share_pct": 20.0},
            {"name": "z-ai/glm-5.3-flash-20260826", "tokens": 12_230_000_000_000, "formatted": "12.23T", "share_pct": 7.5},
        ],
        other_share_pct=41.1,
    )
    base.update(kw)
    return base


def _render(or_trend=None, ai_trend=None) -> str:
    import pywebio.output as po

    OM, TM = _om(), _tm()
    out = []
    old_put = po.put_html
    old_or, old_ai = OM.get_openrouter_trend, OM.get_ai_compute_trend
    po.put_html = lambda html, *a, **k: out.append(html)
    OM.get_openrouter_trend = lambda: or_trend
    OM.get_ai_compute_trend = lambda: ai_trend
    try:
        TM.render_token_monitor(None)
    finally:
        po.put_html = old_put
        OM.get_openrouter_trend, OM.get_ai_compute_trend = old_or, old_ai
    return "".join(out)


def check_render_covers_all_enums() -> list:
    TM = _tm()
    failures = []

    for direction, (label, _color) in TM.DIRECTION_STYLE.items():
        html = _render(or_trend=_fake_trend(direction=direction))
        if label not in html:
            failures.append(f"方向 {direction} 渲染后找不到标签「{label}」")
        if "❓ 未知" in html:
            failures.append(f"方向 {direction} 渲染出兜底「❓ 未知」—— 枚举又漏了")

    for level, (label, _color) in TM.ALERT_STYLE.items():
        html = _render(or_trend=_fake_trend(alert_level=level))
        if label not in html:
            failures.append(f"告警级别 {level} 渲染后找不到标签「{label}」")
        if "未知级别" in html:
            failures.append(f"告警级别 {level} 落进了兜底「未知级别」")
    return failures


# ── ⑧ 陈旧与失败必须上屏，且不许常亮 ─────────────────────────────────────────
def check_staleness_visible() -> list:
    failures = []

    stale_html = _render(or_trend=_fake_trend(is_stale=True, data_age_days=160))
    if "已停止更新" not in stale_html:
        failures.append("陈旧数据没有渲染「已停止更新」横幅")
    if "160" not in stale_html:
        failures.append("陈旧横幅没有写出「距今 N 天」")
    if "2026-05-10" not in stale_html:
        failures.append("陈旧横幅没有写出数据日期，用户无法判断旧到什么程度")

    fresh_html = _render(or_trend=_fake_trend(is_stale=False, data_age_days=0))
    if "已停止更新" in fresh_html:
        failures.append("新鲜数据也显示「已停止更新」—— 横幅常亮等于没警示")

    err_html = _render(or_trend=_fake_trend(
        is_stale=False, consecutive_failures=2, last_error="HTTP 200 但解析 0 条",
    ))
    if "解析 0 条" not in err_html:
        failures.append("取数失败原因没有上屏，用户看不出是网络问题还是页面结构变了")
    if "连续 2 次" not in err_html:
        failures.append("没有显示连续失败次数")
    return failures


# ── ⑨ 读取路径必须重算年龄 / 失败必须留痕 ──────────────────────────────────────
def check_read_path_and_failure_trace() -> list:
    failures = []

    for fn in ("get_openrouter_trend", "get_openrouter_full_data"):
        calls = _calls_in(OM_PY, fn)
        if "_freshness_fields" not in calls and "_attach_health" not in calls:
            failures.append(f"{fn} 没有重算新鲜度 —— 缓存躺 160 天也会显示「正常」")

    fetch_calls = _calls_in(OM_PY, "fetch_series")
    if fetch_calls.count("warning") < 2:
        failures.append("fetch_series 的告警不足 2 处（接口失败/解析 0 条都要 warning，不许 debug 静默）")

    # 「解析 0 条」那个分支必须自己 warning —— 只数全函数 warning 个数会被别的告警蒙混过关
    node = _func_node(OM_PY, "fetch_series")
    warned = False
    if node is not None:
        for child in ast.walk(node):
            if isinstance(child, ast.If):
                test = ast.dump(child.test)
                if "points" in test and "not" in test.lower():
                    for inner in ast.walk(child):
                        if (isinstance(inner, ast.Call) and isinstance(inner.func, ast.Attribute)
                                and inner.func.attr == "warning"):
                            warned = True
    if not warned:
        failures.append("「解析 0 条」分支没有 warning（这类假成功正是静默 160 天的原因）")

    if "解析 0 条" not in _src(OM_PY):
        failures.append("没有区分「HTTP 200 但解析 0 条」—— 这类假成功正是静默 160 天的原因")

    # 主路径必须是 JSON 接口；HTML 正则只能当兜底，且兜底成功也要告警
    if "parse_chart_payload" not in _src(OM_PY):
        failures.append("没有 parse_chart_payload —— 主路径退回正则扒 HTML，改版即静默失效")
    if "chunk" in _src(OM_PY) and "iter_bytes" in _src(OM_PY):
        failures.append("取数改成流式了？本守卫的锚点需要重新对齐")

    refresh_calls = _calls_in(OM_PY, "refresh_openrouter_data")
    if "record_fetch_failure" not in refresh_calls:
        failures.append("refresh_openrouter_data 失败时不落盘（record_fetch_failure 未调用）")

    # 失败绝不许回退 last_success_ts
    node = _func_node(OM_PY, "record_fetch_failure")
    if node is None:
        failures.append("找不到 record_fetch_failure（锚点失效）")
    else:
        for child in ast.walk(node):
            if isinstance(child, ast.Dict):
                keys = [k.value for k in child.keys if isinstance(k, ast.Constant)]
                if "last_success_ts" in keys:
                    failures.append("record_fetch_failure 里给 last_success_ts 赋了值 —— 失败会把时间戳刷新成「刚成功」")
    return failures


# ── ⑩ 调度必须日频（周频采日频源 = 必漏 6/7） ─────────────────────────────────
def check_schedule_is_daily() -> list:
    failures = []
    try:
        import yaml
        cfg = yaml.safe_load(_src(TASK_YAML)) or {}
    except Exception as e:  # noqa: BLE001
        return [f"任务 YAML 解析失败: {e}"]

    cron = ((cfg.get("config") or {}).get("cron_expr") or "").strip()
    parts = cron.split()
    if len(parts) != 5:
        failures.append(f"cron_expr={cron!r} 不是 5 段标准表达式")
    else:
        # 标准 cron：分 时 日 月 周。日频 = 日字段与周字段都必须为 *
        if parts[4] != "*":
            failures.append(f"cron_expr={cron!r} 仍是周频（周字段={parts[4]!r}）—— 日频数据源必须每天采")
        elif parts[2] != "*":
            failures.append(f"cron_expr={cron!r} 限定了日期（日字段={parts[2]!r}），不是每日采集")

    func_code = cfg.get("func_code") or ""
    if "data_days" not in func_code:
        failures.append("任务返回值没有 data_days（只有 data_weeks 时会继续误导）")
    return failures


# ── ⑪ 面板不许回退到旧的 3 值映射 ─────────────────────────────────────────────
def check_panel_no_legacy_mapping() -> list:
    failures = []
    src = _src(TM_PY)

    if "dir_config" in src:
        failures.append("面板里仍有 dir_config —— 那是只认 rising/falling/stable 的旧映射形态")

    if 'DIRECTION_STYLE = {' not in src:
        failures.append("找不到 DIRECTION_STYLE（映射表被改名/删除，本守卫的锚点失效）")

    # 风险色语义：需求下降必须是红/橙，不能是绿
    TM = _tm()
    down_colors = {TM.DIRECTION_STYLE[d][1] for d in ("down", "strong_down") if d in TM.DIRECTION_STYLE}
    if TM.C_GREEN in down_colors:
        failures.append("需求下降被渲染成绿色（健康色）—— 颜色在说谎")

    up_colors = {TM.DIRECTION_STYLE[d][1] for d in ("up", "strong_up") if d in TM.DIRECTION_STYLE}
    if TM.C_RED in up_colors:
        failures.append("需求上升被渲染成红色（危险色）—— 套用了 A 股涨红跌绿，与风险色体系冲突")
    return failures


# ── ⑫ 面板标签必须跟着粒度切换 ────────────────────────────────────────────────
def check_ui_label_follows_granularity() -> list:
    failures = []

    wk = _render(or_trend=_fake_weekly())
    for need in ("周消耗", "周环比", "164.04T", "171.84T", "本周未完", "4.52T", "涨势逆转"):
        if need not in wk:
            failures.append(f"周频渲染缺「{need}」")
    for bad in ("单日消耗", "同星期环比", "7 日合计"):
        if bad in wk:
            failures.append(f"周频数据上出现了日频标签「{bad}」—— 口径张冠李戴")
    # 表头也必须自证粒度，否则只看标题的人会被骗
    if "周频" not in wk:
        failures.append("周频渲染的表头没有写出「周频」")
    if "（日频）" in wk:
        failures.append("周频渲染的表头写成了「日频」")

    dy = _render(or_trend=_fake_trend())
    for need in ("单日消耗", "7 日合计", "同星期环比"):
        if need not in dy:
            failures.append(f"日频渲染缺「{need}」")
    for bad in ("周消耗", "周环比"):
        if bad in dy:
            failures.append(f"日频数据上出现了周频标签「{bad}」")
    if "（日频）" not in dy:
        failures.append("日频渲染的表头没有写出「日频」")
    if "周频" in dy:
        failures.append("日频渲染的表头写成了「周频」")

    # Others 是残差桶，不许混进"Top 模型"列表冒充一个模型
    if "Others</span>" in wk:
        failures.append("Others 残差桶被当成单个模型渲染进了 Top 榜")
    return failures


# ── ⑬ 陈旧阈值必须随周期派生，年龄从周期【结束日】算 ──────────────────────────
def check_freshness_period_aware() -> list:
    from datetime import date as _d, timedelta as _t
    OM = _om()
    failures = []

    today = _d.today()
    monday = today - _t(days=today.weekday())
    last_week_start = monday - _t(days=7)
    f = OM._freshness_fields(last_week_start.isoformat(), period_days=7)

    exp_age = (today - (last_week_start + _t(days=6))).days
    if f.get("data_age_days") != exp_age:
        failures.append(
            f"周频年龄应为 {exp_age} 天（从周日算），实得 {f.get('data_age_days')} —— 从周一起算会每周误报陈旧 6 天"
        )
    if f.get("stale_threshold_days") != 9:
        failures.append(f"周频陈旧阈值应为 7+2=9 天，实得 {f.get('stale_threshold_days')}")
    if f.get("is_stale"):
        failures.append("刚走完的一周被判陈旧 —— 周频面板一年会亮 300 天")

    old = OM._freshness_fields((today - _t(days=30)).isoformat(), period_days=1)
    if not old.get("is_stale"):
        failures.append("30 天前的日频数据未判陈旧")
    if old.get("stale_threshold_days") != 3:
        failures.append(f"日频陈旧阈值应为 1+2=3 天，实得 {old.get('stale_threshold_days')}")
    return failures


# ── ⑭ 雷达卡不许把口径写死成「同星期」 ─────────────────────────────────────────
def check_radar_panel_period_aware() -> list:
    failures = []
    path = ROOT / "deva/naja/radar/ui/panels.py"
    src = _src(path)

    if "同星期 {latest_change" in src:
        failures.append("雷达卡把环比写死成「同星期」—— 周频数据会被贴上日频标签")
    if "week_over_week" not in src:
        failures.append("雷达卡没有区分 week_over_week / same_weekday 口径")
    if "口径待刷新" not in src:
        failures.append("雷达卡对旧口径缓存没有写「口径待刷新」，会冒充结论")
    return failures


def _all_checks() -> list:
    return (
        check_granularity_constants()
        + check_granularity_autodetect()
        + check_incomplete_period_excluded()
        + check_no_daily_as_weekly()
        + check_metric_separation()
        + check_insufficient_is_honest()
        + check_enum_coverage()
        + check_unknown_not_disguised()
        + check_render_covers_all_enums()
        + check_staleness_visible()
        + check_read_path_and_failure_trace()
        + check_schedule_is_daily()
        + check_panel_no_legacy_mapping()
        + check_ui_label_follows_granularity()
        + check_freshness_period_aware()
        + check_radar_panel_period_aware()
    )


# ── 负向注入：每条都要被抓到，抓不到说明守卫是摆设 ─────────────────────────────
INJECTIONS = [
    {
        "name": "同星期环比退回日环比（lag 7 → lag 1）",
        "path": OM_PY,
        "old": "wow_rates = _lag_rates(complete, WEEK_DAYS)",
        "new": "wow_rates = _lag_rates(complete, 1)",
    },
    {
        "name": "把 flat 从方向判定里删掉（横盘被报成下跌）",
        "path": OM_PY,
        "old": '    elif avg_recent >= -DIRECTION_FLAT_BAND:\n        direction = "flat"',
        "new": '    elif avg_recent >= DIRECTION_FLAT_BAND:\n        direction = "flat"',
    },
    {
        "name": "UI 丢掉 flat 映射（回落成「未知」）",
        "path": TM_PY,
        "old": '    "flat": ("➡️ 横盘", C_BLUE),\n',
        "new": "",
    },
    {
        "name": "UI 丢掉 attention 告警级",
        "path": TM_PY,
        "old": '    "attention": ("🟡 关注", C_ORANGE),\n',
        "new": "",
    },
    {
        "name": "unknown 伪装成 stable",
        "path": OM_PY,
        "old": '"unknown": "unknown",   # 不伪装 stable：算不出来就是算不出来',
        "new": '"unknown": "stable",',
    },
    {
        "name": "读取路径不再重算新鲜度",
        "path": OM_PY,
        "old": "        trend = _attach_health(trend, db)\n        if trend.get(\"is_stale\"):",
        "new": "        trend = trend\n        if trend.get(\"is_stale\"):",
    },
    {
        "name": "陈旧年龄从周期起始日算（周频每周误报 6 天）",
        "path": OM_PY,
        "old": "    period_end = d + timedelta(days=max(0, period_days - 1))",
        "new": "    period_end = d",
    },
    {
        "name": "残缺周不剔除（直接拿 4.52T 比 171.84T）",
        "path": OM_PY,
        "old": '    complete = [s for s in series if _period_end(s["date"]) < today]',
        "new": "    complete = list(series)",
    },
    {
        "name": "粒度写死 weekly（日频源被当周桶）",
        "path": OM_PY,
        "old": "    granularity = detect_granularity(series)\n",
        "new": '    granularity = "weekly"\n',
    },
    {
        "name": "面板标签写死日频（周频数据贴日频标签）",
        "path": TM_PY,
        "old": '            header_txt = "📡 OpenRouter 用量（周频 · 全站）"',
        "new": '            header_txt = "📡 OpenRouter 用量（日频）"',
    },
    {
        "name": "解析 0 条退回 debug 静默",
        "path": OM_PY,
        "old": '            logger.warning(f"[OpenRouter] {_FETCH_DIAG[\'error\']}")',
        "new": '            logger.debug(f"[OpenRouter] {_FETCH_DIAG[\'error\']}")',
    },
    {
        "name": "失败时把 last_success_ts 刷成现在",
        "path": OM_PY,
        "old": '            "last_attempt_ts": now,\n            "last_error": detail,',
        "new": '            "last_attempt_ts": now,\n            "last_success_ts": now,\n            "last_error": detail,',
    },
    {
        "name": "调度退回周频",
        "path": TASK_YAML,
        "old": "  cron_expr: 0 9 * * *",
        "new": "  cron_expr: 0 9 * * 1",
    },
    {
        "name": "面板又用回只认 rising/falling/stable 的旧映射",
        "path": TM_PY,
        "old": 'DIRECTION_STYLE = {\n    "strong_up"',
        "new": 'dir_config = {"rising": 1}\nDIRECTION_STYLE = {\n    "strong_up"',
    },
]


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
        except Exception as e:  # noqa: BLE001
            found = [f"守卫自身抛异常: {type(e).__name__}: {e}"]
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
    return caught


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--exercise-injections", action="store_true")
    args = ap.parse_args()

    if args.exercise_injections:
        return 0 if run_injections() == len(INJECTIONS) else 1

    failures = _all_checks()
    if failures:
        print("❌ OpenRouter 监控口径/渲染守卫 失败：")
        for f in failures:
            print(f"   - {f}")
        return 1 if args.strict else 0
    print("✅ OpenRouter 监控守卫全绿"
          "（粒度自证 · 残缺周剔除 · 周/日两套标签 · 枚举全覆盖 · unknown 不伪装 · 陈旧/失败上屏）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
