"""
OpenRouterMonitor - 认知系统/TOKEN监控/算力监控

别名/关键词: TOKEN、算力、GPU、AI算力、openrouter、算力需求

注意: 本模块从 radar/openrouter_monitor.py 迁移到 cognition 层。
AI 算力趋势分析本质上是认知/分析任务，不是市场感知。
radar/openrouter_monitor.py 保留为向后兼容的转发层。

数据源（2026-10 起）：
  https://openrouter.ai/api/frontend/v1/rankings/model-rankings-chart
  返回 {"data": {"data": [{"x": "YYYY-MM-DD", "ys": {model: tokens}}], "cachedAt": ms}}
  即页面上「Weekly usage of models across OpenRouter」那张图的原始数据。

  ❗口径要点（踩过坑，读代码前先读这段）：
  - 每个点 = **1 个 7 天桶**（以周一为起点），不是 1 天。
  - 每点的 ys = top-9 模型 + 「Others」残差桶，因此 sum(ys) = **全站周总量**。
  - 最后一个点通常是**本周（尚未走完）**，必须剔除后再算环比，否则 4.52T vs 164T 会得出 -97%。
  - 2026-10 之前该接口曾是「逐日 + 无 Others 桶」，所以历史缓存量级与现在不可比。
    粒度由数据自身相邻间隔中位数推断（7→周、1→日），**不许写死**。

功能：
1. 每日获取 OpenRouter TOKEN 消耗数据（源为周频，每日拉一次以跟踪当周进度）
2. 分析趋势（上涨/下跌/加速/减速/异常）
3. 数据存储到 NB 表，供其他模块查询
4. 异常时发送雷达事件
"""

import asyncio
import logging
import re
from statistics import median
import httpx
from typing import Optional, Dict, List, TypedDict, Union, Any
from datetime import date, datetime, timedelta
from enum import Enum

logger = logging.getLogger(__name__)

TREND_TABLE = "openrouter_trend"

# ============================================================================
# 数据口径常量 —— 改这里之前先读模块 docstring 的「口径要点」
#
# ❗粒度必须**从数据本身推断**，不许写死。历史上这块栽过两次：
#   1) 源是日频，代码按周处理  -> 「周消耗」比真实周量小 8.3 倍
#   2) 源改回周频，代码写死日频 -> 「7 日滚动」把一整周的量当 1 天加总
# 现在：detect_granularity() 用相邻点间隔中位数判定，7→weekly、1→daily，
# 分析层按 period_days 统一处理，UI 按 granularity 换标签。
# ============================================================================
GRANULARITY_MODES = ("weekly", "daily", "unknown")
GRANULARITY_WEEK = "weekly"
GRANULARITY_DAY = "daily"
WEEK_DAYS = 7                   # 一个周桶覆盖的天数
STALE_GRACE_DAYS = 2            # 陈旧容忍：距今超过「周期长度 + 该值」天算陈旧
MIN_TREND_POINTS = 3            # 可比点少于此值只报"数据不足"，禁止输出方向结论

# 方向枚举唯一权威。UI 的映射表必须覆盖全部 6 个值，否则会静默落成"未知"。
DIRECTION_VALUES = ("strong_up", "up", "flat", "down", "strong_down", "unknown")

# 方向判定带：旧实现没有 flat 区间，-0.34% 也被判成 "down / 算力需求下降"
DIRECTION_FLAT_BAND = 1.0
DIRECTION_STRONG_BAND = 3.0

# 数据源接口（页面「Weekly usage of models across OpenRouter」那张图的原始数据）
RANKINGS_CHART_API = "https://openrouter.ai/api/frontend/v1/rankings/model-rankings-chart"
OTHER_BUCKET = "Others"         # 残差桶，代表 top-9 之外的全部模型

# 预编译正则表达式（仅作 HTML 兜底解析，主路径走 JSON 接口）
_WEEKLY_DATA_RE = re.compile(r'\\\"x\\\":\\\"(\d{4}-\d{2}-\d{2})\\\",\\\"ys\\\":\{([^}]+)\}')
_MODEL_DATA_RE = re.compile(r'\\\"([^\\\"]+)\\\":\s*(\d+)')

# 最近一次取数的诊断信息：http 状态、原始字节数、解析条数、失败原因。
# 作用：区分"网络挂了"和"抓到了但解析 0 条"——后者曾经静默了 160 天。
_FETCH_DIAG: Dict[str, Any] = {
    "http_status": None,
    "raw_len": 0,
    "parsed_count": 0,
    "error": "",
    "attempt_ts": None,
    "source": "",
    "granularity": "",
    "cached_at": None,
}


class AlertLevel(Enum):
    NORMAL = "normal"
    ATTENTION = "attention"
    WARNING = "warning"
    CRITICAL = "critical"


class WeeklyDataPoint(TypedDict):
    """单周数据点"""
    date: str  # ISO 日期格式 "YYYY-MM-DD"
    models: dict[str, int]  # model_id -> token_count


class AppRanking(TypedDict):
    """应用排行榜条目"""
    app_id: int
    title: str
    total_tokens: int
    total_requests: int
    rank: int
    description: Optional[str]
    origin_url: Optional[str]


class OpenRouterRankings:
    """OpenRouter 排行榜获取器

    主路径：JSON 接口（干净、有 Others 残差桶、无需正则）。
    兜底路径：解析 HTML 里的 RSC payload（接口挂了才走，且必须告警）。
    """

    BASE_URL = "https://openrouter.ai"
    RANKINGS_URL = f"{BASE_URL}/rankings"
    CHART_API = RANKINGS_CHART_API

    API_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
        "Referer": "https://openrouter.ai/rankings",
        "Accept": "application/json",
    }

    def parse_chart_payload(self, payload: Any) -> list[WeeklyDataPoint]:
        """把接口返回的 {"data": {"data": [...]}} 转成数据点列表

        容错三种形态：带 data 外壳、直接 list、以及单点对象。
        任何一条缺 x / ys 就跳过它，但绝不静默丢掉整批（数量由调用方比对）。
        """
        if isinstance(payload, dict):
            body = payload.get("data", payload)
            if isinstance(body, dict):
                rows = body.get("data")
            else:
                rows = body
        else:
            rows = payload

        if not isinstance(rows, list):
            return []

        out: list[WeeklyDataPoint] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            x = row.get("x") or row.get("date")
            ys = row.get("ys") or row.get("models")
            if not isinstance(x, str) or not isinstance(ys, dict):
                continue
            models: dict[str, int] = {}
            for name, val in ys.items():
                try:
                    iv = int(val)
                except (TypeError, ValueError):
                    continue
                if iv > 0:
                    models[str(name)] = iv
            if models:
                out.append(WeeklyDataPoint(date=x[:10], models=models))
        out.sort(key=lambda p: p["date"])
        return out

    def _parse_weekly_data(self, html_content: str) -> list[WeeklyDataPoint]:
        """兜底：解析 HTML 里的 RSC payload

        ⚠️ 这条路径在 2026-10 改版后已失效（payload 挪到接口了），
        保留只为接口异常时留一条诊断线索，不要当主路径用。
        """
        result = []
        for date_str, models_data in _WEEKLY_DATA_RE.findall(html_content):
            models: dict[str, int] = {}
            for model_id, token_count in _MODEL_DATA_RE.findall(models_data):
                try:
                    models[model_id] = int(token_count)
                except (TypeError, ValueError):
                    continue
            if models:
                result.append(WeeklyDataPoint(date=date_str, models=models))
        return result

    def _parse_ranking_data(self, models_data: Dict[str, Any]) -> List[AppRanking]:
        """将 token 数据转换为结构化排行榜条目的内部方法"""
        sorted_items = sorted(models_data.items(), key=lambda x: x[1] if isinstance(x[1], (int, float)) else 0, reverse=True)
        rankings: List[AppRanking] = []
        for rank, (name, token_count) in enumerate(sorted_items, start=1):
            try:
                total_tokens = int(token_count)
            except (TypeError, ValueError):
                continue
            rankings.append(AppRanking(
                app_id=rank,
                title=str(name),
                total_tokens=total_tokens,
                total_requests=max(1, total_tokens // 1000),
                rank=rank,
                description=None,
                origin_url=None,
            ))
        return rankings


def format_tokens(tokens: int) -> str:
    """格式化 token 数量"""
    if tokens >= 1_000_000_000_000:
        return f"{tokens / 1_000_000_000_000:.2f}T"
    elif tokens >= 1_000_000_000:
        return f"{tokens / 1_000_000_000:.2f}B"
    elif tokens >= 1_000_000:
        return f"{tokens / 1_000_000:.2f}M"
    else:
        return f"{tokens:,}"


def format_app_rankings(weekly_data_list: List[Dict], top_n: int = 10) -> List[Dict]:
    """将 weekly_data = [{"date": ..., "total": ..., "models": {...}}]
    格式转换为 AppRanking 排行榜

    Args:
        weekly_data_list: Weekly data 列表
        top_n: 返回前 N 名

    Returns:
        [{rank, title, total_tokens, total_requests, ...}]
    """
    if not weekly_data_list:
        return []
    all_models: Dict[str, int] = {}
    for week in weekly_data_list:
        models = week.get("models", {}) if isinstance(week, dict) else {}
        for model_name, tokens in models.items():
            try:
                all_models[str(model_name)] = all_models.get(str(model_name), 0) + int(tokens)
            except (TypeError, ValueError):
                continue
    rankings = OpenRouterRankings()._parse_ranking_data(all_models) if all_models else []
    return [dict(r) for r in rankings[:top_n]]


def _diagnose_empty_schema(html: str) -> str:
    """解析 0 条时，判断页面到底变成了什么样

    只说"正则需更新"没有用 —— 得让人一眼看出是「页面改版、数据源能力退化」
    还是「纯网络故障」。
    """
    if "or-table__body" in html and "tokens processed" in html:
        return (
            "页面已改版为『模型周榜』（top-10 模型 + 周环比），"
            "原『全站逐日 token 序列』接口已移除 —— 需重新定义口径"
        )
    if "rankings" in html and len(html) > 100_000:
        return "页面可访问但结构不认识（rankings 改版，解析器需更新）"
    if len(html) < 5_000:
        return "返回内容过短，疑似被拦截/重定向"
    return "页面内容异常，未识别出任何已知结构"


def detect_granularity(series: List[Dict]) -> str:
    """从数据自身推断粒度：相邻点间隔中位数为 7 -> 周，1 -> 日

    ❗不许写死。这个函数存在的唯一理由，就是历史两次"口径写死"事故：
    源从日频改成周频（或反过来）时代码毫无察觉，继续按旧周期解释数字。
    """
    ds: List[date] = []
    for item in series or []:
        d = _norm_date(item.get("date") if isinstance(item, dict) else None)
        if d is not None:
            ds.append(d)
    ds = sorted(set(ds))
    if len(ds) < 3:
        return "unknown"
    gaps = [(ds[i + 1] - ds[i]).days for i in range(len(ds) - 1)]
    gaps = [g for g in gaps if g > 0]
    if not gaps:
        return "unknown"
    med = median(gaps)
    if med >= 6:
        return GRANULARITY_WEEK
    if med <= 2:
        return GRANULARITY_DAY
    return "unknown"


async def fetch_series() -> Optional[List[Dict]]:
    """获取 OpenRouter 的 token 消耗时间序列（粒度由数据自身决定）

    主路径走 JSON 接口 `model-rankings-chart`，它返回的就是页面上
    「Weekly usage of models across OpenRouter」那张图的原始数据。

    失败绝不静默。三类失败必须可区分（曾经的 160 天假新鲜就是分不清它们）：
      - 网络/HTTP 失败    -> http_status 非 200 或抛异常
      - 抓到了但解析 0 条 -> http_status=200 且 parsed_count=0（结构变了）
      - 正常              -> parsed_count > 0

    诊断写入 _FETCH_DIAG，由 refresh_openrouter_data 落盘到 NB 的 health key。
    """
    _FETCH_DIAG.update({
        "http_status": None,
        "raw_len": 0,
        "parsed_count": 0,
        "error": "",
        "attempt_ts": datetime.now().isoformat(),
        "source": "",
        "granularity": "",
        "cached_at": None,
    })

    parser = OpenRouterRankings()
    points: list[WeeklyDataPoint] = []

    try:
        async with httpx.AsyncClient(timeout=30.0, headers=OpenRouterRankings.API_HEADERS) as client:
            # ---- 主路径：JSON 接口 ----
            try:
                resp = await client.get(OpenRouterRankings.CHART_API)
                _FETCH_DIAG["http_status"] = resp.status_code
                _FETCH_DIAG["raw_len"] = len(resp.content)
                resp.raise_for_status()
                payload = resp.json()
                body = payload.get("data", {}) if isinstance(payload, dict) else {}
                if isinstance(body, dict):
                    _FETCH_DIAG["cached_at"] = body.get("cachedAt")
                points = parser.parse_chart_payload(payload)
                _FETCH_DIAG["source"] = "api:model-rankings-chart"
            except Exception as api_err:
                _FETCH_DIAG["error"] = f"接口失败 {type(api_err).__name__}: {api_err}"
                logger.warning(f"[OpenRouter] JSON 接口不可用，转 HTML 兜底: {_FETCH_DIAG['error']}")
                resp = await client.get(OpenRouterRankings.RANKINGS_URL)
                _FETCH_DIAG["http_status"] = resp.status_code
                _FETCH_DIAG["raw_len"] = len(resp.text)
                resp.raise_for_status()
                points = parser._parse_weekly_data(resp.text)
                _FETCH_DIAG["source"] = "html:rsc-fallback"
                if points:
                    logger.warning("[OpenRouter] 已改用 HTML 兜底解析成功 —— 接口可能已变更，需排查")

            _FETCH_DIAG["parsed_count"] = len(points)

        if not points:
            # 最危险的一种"成功"：HTTP 200，但一条也解析不出来。
            _FETCH_DIAG["error"] = (
                f"HTTP {_FETCH_DIAG['http_status']} 但解析 0 条"
                f"（原始 {_FETCH_DIAG['raw_len']} 字节）：接口返回结构可能已变"
            )
            logger.warning(f"[OpenRouter] {_FETCH_DIAG['error']}")
            return None

        series = [
            {
                "date": p["date"],
                "total": sum(p["models"].values()),
                "models": p["models"],
            }
            for p in points
        ]
        gran = detect_granularity(series)
        _FETCH_DIAG["granularity"] = gran
        if gran == "unknown":
            logger.warning(
                f"[OpenRouter] 粒度无法识别（{len(series)} 点，首末 "
                f"{series[0]['date']}~{series[-1]['date']}）—— 下游按周处理会失真"
            )
        return series

    except Exception as e:
        _FETCH_DIAG["error"] = f"{type(e).__name__}: {e}"
        logger.warning(f"[OpenRouter] 数据获取失败: {_FETCH_DIAG['error']}")
        return None


def _norm_date(value: Any) -> Optional[date]:
    """把 'YYYY-MM-DD' / datetime / date 统一成 date，失败返回 None"""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.strptime(value[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return None
    return None


def _normalize_series(raw: List[Dict]) -> List[Dict]:
    """把上游数据整理成按日期升序、去重、total 为正的日序列"""
    merged: Dict[date, int] = {}
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        d = _norm_date(item.get("date"))
        if d is None:
            continue
        total = item.get("total")
        if total is None and isinstance(item.get("models"), dict):
            total = sum(int(v) for v in item["models"].values() if isinstance(v, (int, float)))
        try:
            total = int(total)
        except (TypeError, ValueError):
            continue
        if total <= 0:
            continue
        merged[d] = total
    return [{"date": d, "total": merged[d]} for d in sorted(merged)]


def _pct_change(curr: Optional[float], prev: Optional[float]) -> Optional[float]:
    if curr is None or prev is None or prev <= 0:
        return None
    return (curr - prev) / prev * 100.0


def _lag_rates(series: List[Dict], lag: int) -> List[Dict]:
    """去季节：每个点与 lag 天前的点比。lag=7 即"同星期对齐"。

    这是唯一能和周内季节性（周末用量天生低）干净分离的口径。
    """
    by_date = {s["date"]: s["total"] for s in series}
    rates: List[Dict] = []
    for s in series:
        prev_total = by_date.get(s["date"] - timedelta(days=lag))
        rate = _pct_change(s["total"], prev_total)
        if rate is not None:
            rates.append({"date": s["date"], "rate": rate, "total": s["total"]})
    return rates


def _rolling_sums(series: List[Dict], window: int) -> List[Dict]:
    """连续 window 天的滚动和（窗口内缺任意一天则该窗口不产出）"""
    by_date = {s["date"]: s["total"] for s in series}
    out: List[Dict] = []
    for s in series:
        days = [s["date"] - timedelta(days=offset) for offset in range(window)]
        if all(d in by_date for d in days):
            out.append({"date": s["date"], "total": sum(by_date[d] for d in days)})
    return out


def _insufficient_result(
    reason: str,
    data_points: int = 0,
    data_age_days: Optional[int] = None,
    granularity: str = "unknown",
) -> Dict:
    """数据不足时的诚实返回：明确说"算不出来"，绝不冒充"稳定/横盘" """
    period_days = WEEK_DAYS if granularity == GRANULARITY_WEEK else 1
    return {
        "granularity": granularity,
        "period_days": period_days,
        "period_label": "周" if granularity == GRANULARITY_WEEK else "日",
        "direction": "unknown",
        "strength": 0.0,
        "acceleration": 0.0,
        "is_anomaly": False,
        "anomaly_type": "",
        "message": f"❓ {reason}",
        "recommendation": f"数据不足（{reason}），暂不判断方向",
        "alert_level": AlertLevel.NORMAL.value,
        "latest_date": None,
        "latest_period_end": None,
        "latest_total": 0,
        "latest_total_formatted": "N/A",
        "previous_total": None,
        "previous_total_formatted": "N/A",
        "daily_change_pct": None,
        "latest_change": None,
        "change_basis": "none",
        "wow_same_weekday_pct": None,
        "wow_base_total": None,
        "wow_base_formatted": "N/A",
        "rolling_7d": None,
        "rolling_7d_formatted": "N/A",
        "rolling_7d_prev": None,
        "rolling_7d_change_pct": None,
        "rolling_window_days": WEEK_DAYS,
        "rolling_window_complete": False,
        "rolling_window_missing_days": WEEK_DAYS,
        "momentum_conflict": "",
        "trend_basis": "insufficient",
        "trend_points": 0,
        "trend_confidence": "none",
        "recent_avg_change": 0.0,
        "data_days": data_points,
        "data_weeks": 0,
        "data_points": data_points,
        "is_incomplete_week": False,
        "is_incomplete_period": False,
        "incomplete_total": None,
        "incomplete_total_formatted": "N/A",
        "top_models": [],
        "other_share_pct": None,
        "data_age_days": data_age_days,
        "is_stale": True,
        "stale_threshold_days": period_days + STALE_GRACE_DAYS,
        "comparable_points": 0,
    }


def analyze_trend(raw_data: List[Dict]) -> Dict:
    """分析 OpenRouter TOKEN 消耗趋势（粒度自适应）

    口径（唯一权威，全部由数据自身的 period_days 派生）：
      - latest_total   : 最近一个【已走完】周期的用量（周频=该周总量，日频=当天）
      - latest_change  : 周期环比（周频=周环比，日频=日环比）
      - rolling_7d     : 周频时即 latest_total；日频时=最近 7 天滚动和

    ❗两条铁律：
      1. 「当前未走完的周期」必须剔除后再算环比。周频源里最后一个桶通常只有
         一两天的量（实测 4.52T vs 完整周 164T），直接比会得出 -97% 的假崩盘。
      2. 周频数据没有"周内季节性"，日频数据有；所以去季节口径必须分粒度：
         周频用周期环比，日频用同星期对齐（lag=7）。混用会凭空造出 -20% 假下跌。

    数据不足时返回 direction="unknown" 并写明原因，不输出方向结论。
    """
    series = _normalize_series(raw_data)
    today = datetime.now().date()
    granularity = detect_granularity(series)
    period_days = WEEK_DAYS if granularity == GRANULARITY_WEEK else 1
    stale_threshold = period_days + STALE_GRACE_DAYS
    period_label = "周" if granularity == GRANULARITY_WEEK else "日"

    if not series:
        return _insufficient_result("无数据", granularity=granularity)

    def _period_end(d: date) -> date:
        return d + timedelta(days=period_days - 1)

    # --- 剔除当前未走完的周期 ---
    last_raw = series[-1]
    last_raw_end = _period_end(last_raw["date"])
    is_incomplete_period = last_raw_end >= today
    incomplete_total = last_raw["total"] if is_incomplete_period else None
    complete = [s for s in series if _period_end(s["date"]) < today]

    if not complete:
        result = _insufficient_result(
            "所有周期都还没走完，无法计算环比",
            data_points=len(series),
            granularity=granularity,
        )
        result.update({
            "is_incomplete_period": is_incomplete_period,
            "is_incomplete_week": is_incomplete_period,
            "incomplete_total": incomplete_total,
            "incomplete_total_formatted": format_tokens(incomplete_total) if incomplete_total else "N/A",
        })
        return result

    latest = complete[-1]
    latest_end = _period_end(latest["date"])
    data_age_days = (today - latest_end).days
    is_stale = data_age_days > stale_threshold

    # --- 周期环比（周频的主口径 / 日频的辅助口径）---
    pop_rates: List[Dict] = []
    for i in range(1, len(complete)):
        rate = _pct_change(complete[i]["total"], complete[i - 1]["total"])
        if rate is not None:
            pop_rates.append({"date": complete[i]["date"], "rate": rate, "total": complete[i]["total"]})
    period_change = pop_rates[-1]["rate"] if pop_rates else None
    previous_total = complete[-2]["total"] if len(complete) >= 2 else None

    # --- 去季节口径：周频=周期环比；日频=同星期对齐（方向另用滚动平滑）---
    trend_basis = "insufficient"
    if granularity == GRANULARITY_WEEK:
        trend_rates = pop_rates
        trend_basis = "week_over_week"
        change_basis = "week_over_week"
        daily_change = None
        wow_change = period_change
        wow_base_total = previous_total
    elif granularity == GRANULARITY_DAY:
        wow_rates = _lag_rates(complete, WEEK_DAYS)
        wow_change = wow_rates[-1]["rate"] if wow_rates else None
        wow_base_total = next(
            (s["total"] for s in complete if s["date"] == latest["date"] - timedelta(days=WEEK_DAYS)),
            None,
        )
        daily_change = period_change
        change_basis = "same_weekday"
        # 方向判定优先用 7 日滚动环比：它是平滑量，比单点 lag-7 抗噪；
        # 但"面板上给人看的环比"仍是同星期对齐（latest_change），两者分工不同。
        rolls_all = _rolling_sums(complete, WEEK_DAYS)
        roll_rates = []
        for i in range(1, len(rolls_all)):
            r = _pct_change(rolls_all[i]["total"], rolls_all[i - 1]["total"])
            if r is not None:
                roll_rates.append({"date": rolls_all[i]["date"], "rate": r})
        if len(roll_rates) >= MIN_TREND_POINTS:
            trend_rates, trend_basis = roll_rates, "rolling_7d"
        elif len(wow_rates) >= MIN_TREND_POINTS:
            trend_rates, trend_basis = wow_rates, "same_weekday"
        else:
            trend_rates, trend_basis = [], "insufficient"
    else:
        # 粒度识别失败：任何环比都可能张冠李戴，只报数据、不下结论
        result = _insufficient_result(
            f"数据粒度无法识别（{len(series)} 点，间隔不规则），拒绝输出环比",
            data_points=len(series),
            data_age_days=data_age_days,
            granularity=granularity,
        )
        result.update({
            "latest_date": latest["date"].isoformat(),
            "latest_period_end": latest_end.isoformat(),
            "latest_total": latest["total"],
            "latest_total_formatted": format_tokens(latest["total"]),
            "is_incomplete_period": is_incomplete_period,
            "is_incomplete_week": is_incomplete_period,
            "incomplete_total": incomplete_total,
            "incomplete_total_formatted": format_tokens(incomplete_total) if incomplete_total else "N/A",
            "is_stale": is_stale,
        })
        return result

    # --- 7 日口径（面板用）---
    if granularity == GRANULARITY_WEEK:
        rolling_latest = {"date": latest["date"], "total": latest["total"]}
        rolling_prev = {"date": complete[-2]["date"], "total": complete[-2]["total"]} if len(complete) >= 2 else None
        rolling_change = period_change
        missing_days: List[date] = []
        window_complete = True
    else:
        rolls = _rolling_sums(complete, WEEK_DAYS)
        rolling_latest = rolls[-1] if rolls else None
        rolling_prev = rolls[-2] if len(rolls) >= 2 else None
        rolling_change = (
            _pct_change(rolling_latest["total"], rolling_prev["total"])
            if rolling_latest and rolling_prev else None
        )
        window_days = [latest["date"] - timedelta(days=offset) for offset in range(WEEK_DAYS)]
        have = {s["date"] for s in complete}
        missing_days = [d for d in window_days if d not in have]
        window_complete = not missing_days

    # --- 数据不足：不输出方向 ---
    if len(trend_rates) < MIN_TREND_POINTS:
        result = _insufficient_result(
            f"可比点仅 {len(trend_rates)} 个（需 ≥{MIN_TREND_POINTS}）",
            data_points=len(series),
            data_age_days=data_age_days,
            granularity=granularity,
        )
        result.update({
            "latest_date": latest["date"].isoformat(),
            "latest_period_end": latest_end.isoformat(),
            "latest_total": latest["total"],
            "latest_total_formatted": format_tokens(latest["total"]),
            "latest_change": round(wow_change, 2) if wow_change is not None else None,
            "change_basis": change_basis,
            "daily_change_pct": round(daily_change, 2) if daily_change is not None else None,
            "wow_same_weekday_pct": round(wow_change, 2) if wow_change is not None else None,
            "wow_base_total": wow_base_total,
            "wow_base_formatted": format_tokens(wow_base_total) if wow_base_total else "N/A",
            "rolling_7d": rolling_latest["total"] if rolling_latest else None,
            "rolling_7d_formatted": format_tokens(rolling_latest["total"]) if rolling_latest else "N/A",
            "rolling_7d_change_pct": round(rolling_change, 2) if rolling_change is not None else None,
            "rolling_window_complete": window_complete,
            "rolling_window_missing_days": len(missing_days),
            "is_stale": is_stale,
            "is_incomplete_period": is_incomplete_period,
            "is_incomplete_week": is_incomplete_period,
            "incomplete_total": incomplete_total,
            "incomplete_total_formatted": format_tokens(incomplete_total) if incomplete_total else "N/A",
        })
        return result

    # --- 方向判定 ---
    recent = [r["rate"] for r in trend_rates[-4:]]
    older = [r["rate"] for r in trend_rates[-8:-4]]
    avg_recent = sum(recent) / len(recent)
    avg_older = sum(older) / len(older) if older else 0.0
    acceleration = avg_recent - avg_older

    if avg_recent > DIRECTION_STRONG_BAND:
        direction = "strong_up"
    elif avg_recent > DIRECTION_FLAT_BAND:
        direction = "up"
    elif avg_recent >= -DIRECTION_FLAT_BAND:
        direction = "flat"
    elif avg_recent >= -DIRECTION_STRONG_BAND:
        direction = "down"
    else:
        direction = "strong_down"

    strength = min(1.0, abs(avg_recent) / 10.0)

    # 置信度按周期算，不按点数拍脑袋：周频 8 周≈两个月，日频 28 天≈一个月
    if granularity == GRANULARITY_WEEK:
        confidence = "high" if len(complete) >= 8 else ("medium" if len(complete) >= 4 else "low")
    else:
        confidence = "high" if len(complete) >= 28 else ("medium" if len(complete) >= 14 else "low")

    # --- 异常检测（全部基于去季节口径，边界用 <=）---
    is_anomaly = False
    anomaly_type = ""

    if wow_change is not None and len(trend_rates) >= 3:
        wow_recent_3 = sum(r["rate"] for r in trend_rates[-3:]) / 3
        if wow_change <= -20 and wow_recent_3 < -10:
            is_anomaly, anomaly_type = True, "sudden_drop"
        elif direction in ("up", "strong_up") and wow_change <= -5:
            is_anomaly, anomaly_type = True, "uptrend_reversal"

    if not is_anomaly and len(trend_rates) >= 8:
        recent_4 = [r["rate"] for r in trend_rates[-4:]]
        older_4 = [r["rate"] for r in trend_rates[-8:-4]]
        mean_a, mean_b = sum(recent_4) / 4, sum(older_4) / 4
        var_a = sum((x - mean_a) ** 2 for x in recent_4) / 4
        var_b = sum((x - mean_b) ** 2 for x in older_4) / 4
        if var_b > 0 and var_a > var_b * 3:
            is_anomaly, anomaly_type = True, "volatility_spike"

    alert = _get_alert_level(direction, strength, acceleration, is_anomaly, anomaly_type)

    # --- 趋势与最新周期背离：必须显式标注 ---
    # 教训：4 周均值仍在涨、但最近一周已转跌时，只报"强劲上涨"会让面板上出现
    # "🚀 ... (-4.5%)" 这种自相矛盾的并排信息 —— 用户只能理解成"数字坏了"。
    momentum_conflict = ""
    latest_rate = wow_change if wow_change is not None else period_change
    if latest_rate is not None:
        if direction in ("up", "strong_up") and latest_rate < -DIRECTION_FLAT_BAND:
            momentum_conflict = "trend_up_latest_down"
        elif direction in ("down", "strong_down") and latest_rate > DIRECTION_FLAT_BAND:
            momentum_conflict = "trend_down_latest_up"

    # --- 结构明细：最新完整周期的构成（top 模型 + Others 占比）---
    top_models: List[Dict] = []
    other_share_pct = None
    raw_latest = next((s for s in raw_data if isinstance(s, dict) and _norm_date(s.get("date")) == latest["date"]), None)
    models = (raw_latest or {}).get("models") if isinstance(raw_latest, dict) else None
    if isinstance(models, dict) and models:
        total_models = sum(v for v in models.values() if isinstance(v, (int, float))) or 1
        ordered = sorted(models.items(), key=lambda kv: -(kv[1] if isinstance(kv[1], (int, float)) else 0))
        for name, val in ordered:
            if not isinstance(val, (int, float)):
                continue
            top_models.append({
                "name": str(name),
                "tokens": int(val),
                "formatted": format_tokens(int(val)),
                "share_pct": round(val / total_models * 100, 1),
            })
            if len(top_models) >= 6:
                break
        if OTHER_BUCKET in models and total_models:
            other_share_pct = round(models[OTHER_BUCKET] / total_models * 100, 1)

    # --- 文案 ---
    emojis = {
        "strong_up": "🚀", "up": "📈", "flat": "➡️",
        "down": "📉", "strong_down": "⚠️", "unknown": "❓",
    }
    emoji = emojis.get(direction, "➡️")
    # 背离时首字符必须让位给警告，否则"🚀 ... 涨势逆转"自相矛盾
    if momentum_conflict == "trend_up_latest_down":
        emoji = "⚠️"
    elif momentum_conflict == "trend_down_latest_up":
        emoji = "🔄"
    if granularity == GRANULARITY_WEEK:
        msg = f"{emoji} {latest['date'].isoformat()} 周 | 周消耗 {format_tokens(latest['total'])}"
        if wow_change is not None:
            msg += f" ({wow_change:+.1f}%)"
    else:
        week_txt = format_tokens(rolling_latest["total"]) if rolling_latest else "窗口不完整"
        msg = f"{emoji} {latest['date'].isoformat()} | 日 {format_tokens(latest['total'])} | 7日 {week_txt}"
        if rolling_change is not None:
            msg += f" ({rolling_change:+.1f}%)"
        msg += f" | 同星期 {wow_change:+.1f}%" if wow_change is not None else " | 同星期 N/A"
    if is_anomaly:
        msg += f" | ⚠️ 异常: {anomaly_type}"
    if momentum_conflict == "trend_up_latest_down":
        msg += f" | ⚠️ 涨势逆转（{len(recent)}期均值 {avg_recent:+.1f}%，最新 {latest_rate:+.1f}%）"
    elif momentum_conflict == "trend_down_latest_up":
        msg += f" | 🔄 跌势反转（{len(recent)}期均值 {avg_recent:+.1f}%，最新 {latest_rate:+.1f}%）"
    if is_incomplete_period and incomplete_total:
        msg += f" | 本周未完 已录 {format_tokens(incomplete_total)}"
    if is_stale:
        msg += f" | ⚠️ 数据已陈旧 {data_age_days} 天"

    if momentum_conflict == "trend_up_latest_down":
        recommendation = (
            f"⚠️ 涨势见顶迹象：{len(recent)}期趋势仍向上（均值 {avg_recent:+.1f}%），"
            f"但最新一期已转跌 {latest_rate:+.1f}% —— 建议先观察 1~2 期确认，勿追加算力仓位"
        )
    elif momentum_conflict == "trend_down_latest_up":
        recommendation = (
            f"🔄 跌势中反弹：{len(recent)}期趋势仍向下（均值 {avg_recent:+.1f}%），"
            f"但最新一期回升 {latest_rate:+.1f}% —— 建议等趋势确认后再评估"
        )
    elif is_anomaly:
        if anomaly_type == "sudden_drop":
            recommendation = f"⚠️ {period_label}消耗骤降！建议：先确认是否数据源异常，再看是否持续"
        elif anomaly_type == "uptrend_reversal":
            recommendation = "🔄 上涨趋势反转！建议：减仓算力投资，等待趋势确认"
        else:
            recommendation = "📊 波动异常！建议：谨慎操作，等待市场稳定"
    elif direction == "strong_up":
        recommendation = "🚀 算力需求强劲上涨！建议：适度增加算力投资配置"
    elif direction == "up":
        recommendation = "📈 算力需求温和上涨！建议：维持当前配置"
    elif direction == "flat":
        recommendation = "➡️ 消耗横盘！建议：维持当前配置，等待方向选择"
    elif direction == "down":
        recommendation = "📉 算力需求下降！建议：观望等待"
    else:
        recommendation = "⚠️ 算力需求快速下滑！建议：减仓算力投资"

    if confidence == "low":
        recommendation += "（低置信：仅 %d 个%s）" % (len(complete), period_label)

    return {
        "granularity": granularity,
        "period_days": period_days,
        "period_label": period_label,
        "direction": direction,
        "strength": round(strength, 4),
        "acceleration": round(acceleration, 2),
        "is_anomaly": is_anomaly,
        "anomaly_type": anomaly_type,
        "message": msg,
        "recommendation": recommendation,
        "alert_level": alert.value,

        "latest_date": latest["date"].isoformat(),
        "latest_period_end": latest_end.isoformat(),
        "latest_total": latest["total"],
        "latest_total_formatted": format_tokens(latest["total"]),
        "previous_total": previous_total,
        "previous_total_formatted": format_tokens(previous_total) if previous_total else "N/A",
        "daily_change_pct": round(daily_change, 2) if daily_change is not None else None,

        # 兼容旧消费方：latest_change 一直是"主环比"——
        # 周频=周环比，日频=同星期对齐（去季节后的当期变化，不是日环比）
        "latest_change": round(wow_change, 2) if wow_change is not None else None,
        "change_basis": change_basis,
        "wow_same_weekday_pct": round(wow_change, 2) if wow_change is not None else None,
        "wow_base_total": wow_base_total,
        "wow_base_formatted": format_tokens(wow_base_total) if wow_base_total else "N/A",

        "rolling_7d": rolling_latest["total"] if rolling_latest else None,
        "rolling_7d_formatted": format_tokens(rolling_latest["total"]) if rolling_latest else "N/A",
        "rolling_7d_prev": rolling_prev["total"] if rolling_prev else None,
        "rolling_7d_change_pct": round(rolling_change, 2) if rolling_change is not None else None,
        "rolling_window_days": WEEK_DAYS,
        "rolling_window_complete": window_complete,
        "rolling_window_missing_days": len(missing_days),

        "momentum_conflict": momentum_conflict,
        "trend_basis": trend_basis,
        "trend_points": len(trend_rates),
        "trend_confidence": confidence,
        "recent_avg_change": round(avg_recent, 2),
        "comparable_points": len(trend_rates),

        "data_days": len(series),
        "data_weeks": len(complete) if granularity == GRANULARITY_WEEK else len(trend_rates),
        "data_points": len(series),
        "is_incomplete_week": is_incomplete_period,
        "is_incomplete_period": is_incomplete_period,
        "incomplete_total": incomplete_total,
        "incomplete_total_formatted": format_tokens(incomplete_total) if incomplete_total else "N/A",
        "top_models": top_models,
        "other_share_pct": other_share_pct,
        "data_age_days": data_age_days,
        "is_stale": is_stale,
        "stale_threshold_days": stale_threshold,
    }


def _get_alert_level(direction: str, strength: float, acceleration: float, is_anomaly: bool, anomaly_type: str) -> AlertLevel:
    """获取警报级别"""
    if is_anomaly and anomaly_type in ["sudden_drop", "uptrend_reversal"]:
        return AlertLevel.CRITICAL
    if is_anomaly:
        return AlertLevel.WARNING
    if acceleration < -15 or acceleration > 15:
        return AlertLevel.WARNING
    if direction == "strong_up":
        return AlertLevel.ATTENTION
    return AlertLevel.NORMAL


def _emit_alert(level: AlertLevel, message: str) -> None:
    """统一的告警输出
    根据 AlertLevel 使用不同的日志级别输出。
    """
    formatted = f"[{level.value.upper()}] {message}"
    if level == AlertLevel.CRITICAL:
        logger.error(formatted)
    elif level == AlertLevel.WARNING:
        logger.warning(formatted)
    elif level == AlertLevel.ATTENTION:
        logger.info(formatted)
    else:  # NORMAL
        logger.debug(formatted)


def _iso(value: Any) -> str:
    d = _norm_date(value)
    return d.isoformat() if d else str(value)


def save_trend_data(trend_data: Dict, series: List[Dict]) -> None:
    """保存趋势数据到 NB 表（成功路径）

    历史全量保留（接口本身就回 53 个周桶，约一年），不再截断。
    旧实现只存 10 个点，连一个完整的 7 日滚动环比都凑不出来。
    """
    try:
        from deva import NB

        db = NB(TREND_TABLE)
        now = datetime.now().isoformat()

        save_data = {
            "timestamp": now,
            "granularity": trend_data.get("granularity", "unknown"),
            "period_days": trend_data.get("period_days", 1),
            "trend": trend_data,
            "weekly_history": [
                {
                    "date": _iso(w["date"]),
                    "total": w["total"],
                    "total_formatted": format_tokens(w["total"]),
                }
                for w in series
            ],
            "raw_data": [
                {"date": _iso(w["date"]), "total": w["total"], "models": w.get("models", {})}
                for w in series[-12:]
            ],
        }

        db["latest"] = save_data
        db["trend"] = trend_data
        db["health"] = {
            "last_attempt_ts": now,
            "last_success_ts": now,
            "last_error": "",
            "consecutive_failures": 0,
            "http_status": _FETCH_DIAG.get("http_status"),
            "raw_len": _FETCH_DIAG.get("raw_len"),
            "parse_count": _FETCH_DIAG.get("parsed_count"),
            "source": _FETCH_DIAG.get("source"),
            "granularity": _FETCH_DIAG.get("granularity"),
            "cached_at": _FETCH_DIAG.get("cached_at"),
            "data_latest_date": trend_data.get("latest_date"),
        }

        logger.debug(f"[OpenRouter] 数据已保存到 {TREND_TABLE} 表（{len(series)} 点）")

    except Exception as e:
        logger.warning(f"[OpenRouter] 数据保存失败: {e}")


def record_fetch_failure() -> None:
    """取数失败也要落盘

    规矩：失败【不许】回退 last_success_ts，只累加 consecutive_failures。
    面板据此显示"上次成功 X 天前 + 本次失败原因"，而不是继续冒充新鲜数据。
    """
    detail = _FETCH_DIAG.get("error") or "未知失败"
    try:
        from deva import NB

        db = NB(TREND_TABLE)
        prev = db.get("health")
        prev = prev if isinstance(prev, dict) else {}
        now = datetime.now().isoformat()

        db["health"] = {
            **prev,
            "last_attempt_ts": now,
            "last_error": detail,
            "consecutive_failures": int(prev.get("consecutive_failures") or 0) + 1,
            "http_status": _FETCH_DIAG.get("http_status"),
            "raw_len": _FETCH_DIAG.get("raw_len"),
            "parse_count": _FETCH_DIAG.get("parsed_count"),
        }
    except Exception as e:
        logger.warning(f"[OpenRouter] 失败状态落盘失败: {e}")

    logger.warning(f"[OpenRouter] 取数失败已记录: {detail}")


def _freshness_fields(latest_date: Any, period_days: int = 1) -> Dict:
    """按【当前时刻】计算数据年龄

    必须在读取时算，不能只在保存时算 —— 否则缓存躺了 160 天，
    里面记的 is_stale 还停在写入当天的 False，面板就成了"假新鲜"。

    ❗年龄必须从**周期结束日**算，不能从周期起始日算。
    周频桶的 x 是该周周一，若从周一起算，一个刚走完的周立刻显示"7 天前"，
    于是每周有 6 天在误报陈旧 —— 假陈旧和假新鲜一样毒。
    """
    d = _norm_date(latest_date)
    if d is None:
        return {
            "data_age_days": None,
            "is_stale": True,
            "stale_threshold_days": period_days + STALE_GRACE_DAYS,
        }
    period_end = d + timedelta(days=max(0, period_days - 1))
    age = (datetime.now().date() - period_end).days
    threshold = period_days + STALE_GRACE_DAYS
    return {
        "data_age_days": age,
        "is_stale": age > threshold,
        "stale_threshold_days": threshold,
    }


def send_to_radar(trend_data: Dict):
    """发送事件到雷达"""
    try:
        from deva.naja.radar.engine import get_radar_engine

        radar = get_radar_engine()
        if not radar:
            return

        score_map = {
            "critical": 0.9,
            "warning": 0.7,
            "attention": 0.5,
            "normal": 0.3
        }

        radar.ingest_result({
            "event_type": "openrouter_trend",
            "score": score_map.get(trend_data.get("alert_level", "normal"), 0.5),
            "message": f"{trend_data.get('message', '')}\n{trend_data.get('recommendation', '')}",
            "payload": trend_data,
            "signal_type": "openrouter_trend",
            "strategy_id": "openrouter_monitor",
            "strategy_name": "OpenRouter TOKEN 监控"
        })

        logger.debug("[OpenRouter] 雷达事件已发送")

    except Exception as e:
        logger.debug(f"[OpenRouter] 雷达发送失败: {e}")


async def refresh_openrouter_data() -> Optional[Dict]:
    """刷新 OpenRouter 数据并返回趋势分析结果

    供外部调用的主要接口。
    失败必须留痕（record_fetch_failure），且不得覆盖上一次成功的数据/时间戳。
    """
    logger.debug("[OpenRouter] 开始获取数据...")

    series = await fetch_series()
    if not series:
        # HTTP 200 但解析 0 条也走这里 —— 这类"成功"曾经静默了 160 天
        record_fetch_failure()
        _emit_alert(
            AlertLevel.WARNING,
            f"取数失败: {_FETCH_DIAG.get('error') or '未知原因'}",
        )
        return None

    gran = detect_granularity(series)
    logger.info(
        f"[OpenRouter] 获取到 {len(series)} 个数据点（粒度={gran}，"
        f"源={_FETCH_DIAG.get('source')}，"
        f"{series[0]['date']}~{series[-1]['date']}）"
    )

    trend_data = analyze_trend(series)
    trend_data.update(_freshness_fields(
        trend_data.get("latest_date"),
        period_days=int(trend_data.get("period_days") or 1),
    ))

    save_trend_data(trend_data, series)

    _update_radar_thread(trend_data)

    if trend_data.get("alert_level") in ["warning", "critical"]:
        send_to_radar(trend_data)

    try:
        level = AlertLevel(trend_data.get("alert_level") or "normal")
    except ValueError:
        level = AlertLevel.NORMAL
    _emit_alert(level, f"趋势分析: {trend_data.get('message', '')}")

    return trend_data


def _update_radar_thread(trend_data: Dict) -> None:
    """更新雷达监控脉络"""
    try:
        from deva.naja.radar.engine import RadarThread, get_radar_engine

        radar = get_radar_engine()

        thread = RadarThread(
            thread_id="openrouter_token",
            name="OpenRouter TOKEN 监控",
            description="全球 AI 算力 TOKEN 消耗趋势",
            category="AI算力",
            update_frequency="每周",
            update_interval_seconds=604800.0,
            last_update_ts=datetime.now().timestamp(),
            last_status=trend_data.get("message", ""),
            alert_level=trend_data.get("alert_level", "normal"),
            score=trend_data.get("strength", 0) * 100,
            icon="🤖",
            thread_type="consumer",
        )

        radar.register_thread(thread)

    except Exception as e:
        logger.error(f"[OpenRouter] 脉络更新失败: {e}")


def _attach_health(trend: Dict, db: Any) -> Dict:
    """把失败状态与实时新鲜度贴到趋势上，供面板直接渲染"""
    trend = dict(trend or {})
    trend.update(_freshness_fields(
        trend.get("latest_date"),
        period_days=int(trend.get("period_days") or 1),
    ))
    try:
        health = db.get("health")
    except Exception:
        health = None
    if isinstance(health, dict):
        trend["last_success_ts"] = health.get("last_success_ts")
        trend["last_error"] = health.get("last_error") or ""
        trend["consecutive_failures"] = health.get("consecutive_failures") or 0
        trend["parse_count"] = health.get("parse_count")
        trend["http_status"] = health.get("http_status")
    return trend


def get_openrouter_trend() -> Optional[Dict]:
    """获取缓存的 OpenRouter 趋势数据（已注入实时新鲜度与失败状态）"""
    try:
        from deva import NB

        db = NB(TREND_TABLE)
        trend = db.get("trend")

        if not isinstance(trend, dict):
            logger.debug("[OpenRouter] 缓存中无数据")
            return None

        trend = _attach_health(trend, db)
        if trend.get("is_stale"):
            logger.warning(
                f"[OpenRouter] 趋势数据已陈旧 {trend.get('data_age_days')} 天"
                f"（最新 {trend.get('latest_date')}），面板将标注陈旧"
            )
        return trend

    except Exception as e:
        logger.warning(f"[OpenRouter] 获取缓存失败: {e}")
        return None


def get_openrouter_full_data() -> Optional[Dict]:
    """获取完整的 OpenRouter 数据（包含历史）"""
    try:
        from deva import NB

        db = NB(TREND_TABLE)
        data = db.get("latest")

        if not isinstance(data, dict):
            logger.debug("[OpenRouter] 缓存中无数据")
            return None

        data = dict(data)
        latest_date = (data.get("trend") or {}).get("latest_date")
        if not latest_date and data.get("weekly_history"):
            latest_date = data["weekly_history"][-1].get("date")
        data.update(_freshness_fields(
            latest_date,
            period_days=int((data.get("trend") or {}).get("period_days") or 1),
        ))
        return data

    except Exception as e:
        logger.warning(f"[OpenRouter] 获取缓存失败: {e}")
        return None


def get_ai_compute_trend() -> Optional[Dict]:
    """获取 AI算力趋势信号（供认知系统使用）

    这个函数返回完整的趋势背景信息，不只是异常告警。
    用于识别"基本面强但价格弱"的背离机会。

    口径说明：粒度自适应（周频源 period_days=7、日频源=1）。
    unknown 一律如实外传，【绝不】伪装成 stable —— 下游据此决定要不要采信。

    Returns:
        {
            "signal_type": "ai_compute_trend",
            "cumulative_growth": 0.12,       # 7 日滚动和的环比（真周增长）
            "weekly_growth": 0.08,           # 同星期对齐环比
            "weekly_growth_rate": 0.15,      # 加速度
            "total_tokens": 164_000_000_000_000,  # 最近一个完整周期的用量
            "period_days": 7,                # 该周期覆盖天数（7=周桶，1=日）
            "granularity": "weekly",
            "rolling_7d": 164_000_000_000_000,    # 周频时即 total_tokens
            "trend_direction": "rising",     # rising / stable / falling / unknown
            "alert_level": "normal",
            "is_abnormal": False,
            "is_stale": True,                # 数据是否已停止更新
            "data_age_days": 160,
            "data_days": 110,
            "trend_confidence": "low",       # high / medium / low / none
            ...
        }
    """
    try:
        from deva import NB

        db = NB(TREND_TABLE)
        data = db.get("latest")
        trend = db.get("trend")

        if not isinstance(data, dict) or not isinstance(trend, dict):
            return None

        trend = _attach_health(trend, db)

        # 累计增长：优先 7 日滚动和环比（真正的"周"），否则退化成首尾对比并标注窗口
        cumulative_growth = 0.0
        growth_window_days = 0
        if trend.get("rolling_7d") and trend.get("rolling_7d_prev"):
            cumulative_growth = (trend["rolling_7d"] - trend["rolling_7d_prev"]) / trend["rolling_7d_prev"]
            growth_window_days = int(trend.get("period_days") or WEEK_DAYS)
        else:
            history = data.get("weekly_history") or []
            if len(history) >= 2:
                oldest = history[0].get("total") or 0
                newest = history[-1].get("total") or 0
                if oldest > 0:
                    cumulative_growth = (newest - oldest) / oldest
                    growth_window_days = len(history)

        weekly_growth = (trend.get("latest_change") or 0) / 100.0
        weekly_growth_rate = (trend.get("acceleration") or 0) / 100.0

        direction = trend.get("direction", "unknown")
        if not trend.get("trend_basis"):
            # 口径改造前写入的旧缓存：direction 是旧算法产物，对外一律按 unknown
            direction = "unknown"
        trend_direction_map = {
            "strong_up": "rising",
            "up": "rising",
            "flat": "stable",
            "down": "falling",
            "strong_down": "falling",
            "unknown": "unknown",   # 不伪装 stable：算不出来就是算不出来
        }
        trend_direction = trend_direction_map.get(direction, "unknown")

        return {
            "signal_type": "ai_compute_trend",
            "cumulative_growth": round(cumulative_growth, 3),
            "growth_window_days": growth_window_days,
            "weekly_growth": round(weekly_growth, 4),
            "weekly_growth_rate": round(weekly_growth_rate, 4),
            "total_tokens": trend.get("latest_total") or 0,
            "rolling_7d": trend.get("rolling_7d"),
            "trend_direction": trend_direction,
            "direction_raw": direction,
            "alert_level": trend.get("alert_level", "normal"),
            "is_abnormal": trend.get("is_anomaly", False),
            "related_blocks": ["AI算力", "半导体", "芯片"],
            "related_symbols": ["NVDA", "AMD", "TSLA", "台积电", "SMCI"],
            "timestamp": data.get("timestamp"),
            "latest_date": trend.get("latest_date"),
            "message": trend.get("message", ""),
            "recommendation": trend.get("recommendation", ""),
            "base_strength": round(trend.get("strength") or 0.0, 3),
            "period_days": int(trend.get("period_days") or 1),
            "granularity": trend.get("granularity", "unknown"),
            "momentum_conflict": trend.get("momentum_conflict", ""),
            # 曾经这里写死 False —— 周频源的"本周未完"就永久消失了
            "is_incomplete_week": bool(trend.get("is_incomplete_period")),
            "data_days": trend.get("data_days", 0),
            "data_weeks": trend.get("data_weeks", 0),
            "trend_confidence": trend.get("trend_confidence", "none"),
            "is_stale": trend.get("is_stale", True),
            "data_age_days": trend.get("data_age_days"),
        }

    except Exception as e:
        logger.warning(f"[OpenRouter] get_ai_compute_trend 失败: {e}")
        return None


def scheduled_openrouter_check():
    """调度任务：每周一执行"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(refresh_openrouter_data())
        loop.close()

        if result:
            logger.debug(f"[OpenRouter Scheduler] 检查完成: {result.get('message', '')}")
        else:
            logger.debug("[OpenRouter Scheduler] 检查失败")

    except Exception as e:
        logger.error(f"[OpenRouter Scheduler] 执行失败: {e}")


if __name__ == "__main__":
    result = asyncio.run(refresh_openrouter_data())
    if result:
        print()
        print("=" * 60)
        print("📊 OpenRouter TOKEN 趋势分析")
        print("=" * 60)
        print(f"消息: {result.get('message', '')}")
        print(f"建议: {result.get('recommendation', '')}")
        print(f"警报级别: {result.get('alert_level', 'unknown')}")
