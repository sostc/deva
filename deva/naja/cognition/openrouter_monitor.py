"""
OpenRouterMonitor - 认知系统/TOKEN监控/算力监控

别名/关键词: TOKEN、算力、GPU、AI算力、openrouter、算力需求

注意: 本模块从 radar/openrouter_monitor.py 迁移到 cognition 层。
AI 算力趋势分析本质上是认知/分析任务，不是市场感知。
radar/openrouter_monitor.py 保留为向后兼容的转发层。

功能：
1. 每周一获取 OpenRouter TOKEN 消耗数据
2. 分析趋势（上涨/下跌/加速/减速/异常）
3. 数据存储到 NB 表，供其他模块查询
4. 异常时发送雷达事件

使用方式：
1. 手动触发: get_openrouter_trend() 或 refresh_openrouter_data()
2. 调度触发: 每周一 09:00 执行 (cron: 0 9 * * 1)
3. 其他模块查询: NB('openrouter_trend')
"""

import asyncio
import re
import httpx
from typing import Optional, Dict, List, TypedDict
from datetime import datetime
from enum import Enum

TREND_TABLE = "openrouter_trend"


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
    description: str | None
    origin_url: str | None


class OpenRouterRankings:
    """OpenRouter 排行榜异步获取器"""

    BASE_URL = "https://openrouter.ai"
    RANKINGS_URL = f"{BASE_URL}/rankings"

    async def get_weekly_token_usage(self) -> list[WeeklyDataPoint]:
        """
        获取每周 Token 使用量时间序列数据

        Returns:
            list[WeeklyDataPoint]: 每周数据列表，按日期升序排列
        """
        async with httpx.AsyncClient(
            timeout=30.0,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            }
        ) as client:
            response = await client.get(self.RANKINGS_URL)
            response.raise_for_status()

            return self._parse_weekly_data(response.text)

    def _parse_weekly_data(self, html_content: str) -> list[WeeklyDataPoint]:
        """
        解析 HTML 中的 RSC payload，提取每周 token 使用量数据
        """
        result = []
        pattern = r'\\\"x\\\":\\\"(\d{4}-\d{2}-\d{2})\\\",\\\"ys\\\":\{([^}]+)\}'
        matches = re.findall(pattern, html_content)

        for date_str, models_data in matches:
            models: dict[str, int] = {}
            model_pattern = r'\\\"([^\\\"]+)\\\":\s*(\d+)'
            model_matches = re.findall(model_pattern, models_data)

            for model_id, token_count in model_matches:
                models[model_id] = int(token_count)

            if models:
                result.append(WeeklyDataPoint(date=date_str, models=models))

        return result


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


async def fetch_weekly_data() -> Optional[List[Dict]]:
    """获取 OpenRouter 每周 TOKEN 数据"""
    try:
        client = OpenRouterRankings()
        weekly_data = await client.get_weekly_token_usage()

        if not weekly_data:
            return None

        return [
            {
                "date": w["date"],
                "total": sum(w["models"].values()),
                "models": w["models"]
            }
            for w in weekly_data
        ]

    except Exception as e:
        print(f"[OpenRouter] 数据获取失败: {e}")
        return None


def analyze_trend(weekly_data: List[Dict]) -> Dict:
    """分析趋势

    注意：OpenRouter 每周数据在周日 23:59 UTC 更新
    如果今天是周一到周六，最新周数据是不完整的
    """
    if len(weekly_data) < 2:
        return {
            "direction": "unknown",
            "strength": 0,
            "acceleration": 0,
            "is_anomaly": False,
            "anomaly_type": "",
            "message": "数据不足",
            "recommendation": "等待更多数据",
            "is_incomplete_week": True
        }

    today = datetime.now()
    current_weekday = today.weekday()

    latest_date = weekly_data[-1]["date"]
    latest_dt = datetime.strptime(latest_date, "%Y-%m-%d")

    days_since_latest = (today - latest_dt).days
    is_incomplete_week = days_since_latest <= 6 and current_weekday != 6

    if is_incomplete_week and len(weekly_data) >= 2:
        analysis_data = weekly_data[:-1]
        latest_week_status = "（不完整周，已排除）"
    else:
        analysis_data = weekly_data
        latest_week_status = "（完整周数据）"

    if len(analysis_data) < 2:
        return {
            "direction": "unknown",
            "strength": 0,
            "acceleration": 0,
            "is_anomaly": False,
            "anomaly_type": "",
            "message": "数据不足（不完整周已排除）",
            "recommendation": "等待更多数据",
            "is_incomplete_week": True
        }

    rates = []
    for i in range(1, len(analysis_data)):
        prev = analysis_data[i-1]["total"]
        curr = analysis_data[i]["total"]
        if prev > 0:
            rate = (curr - prev) / prev * 100
            rates.append({"date": analysis_data[i]["date"], "rate": rate, "total": curr})

    if len(rates) < 4:
        return {
            "direction": "unknown",
            "strength": 0,
            "acceleration": 0,
            "is_anomaly": False,
            "anomaly_type": "",
            "message": f"数据不足 ({len(rates)} 周有效数据)",
            "recommendation": "等待更多数据",
            "is_incomplete_week": is_incomplete_week
        }

    recent_8 = rates[-8:]
    older_8 = rates[-16:-8] if len(rates) >= 16 else rates[:-8]

    recent_avg = sum(r["rate"] for r in recent_8) / len(recent_8)
    older_avg = sum(r["rate"] for r in older_8) / len(older_8) if older_8 else 0

    acceleration = recent_avg - older_avg

    if recent_avg > 5:
        direction = "strong_up"
        strength = min(1.0, recent_avg / 20)
    elif recent_avg > 0:
        direction = "up"
        strength = min(1.0, recent_avg / 10)
    elif recent_avg > -5:
        direction = "down"
        strength = min(1.0, abs(recent_avg) / 10)
    else:
        direction = "strong_down"
        strength = min(1.0, abs(recent_avg) / 20)

    is_anomaly = False
    anomaly_type = ""

    last_3 = rates[-3:]
    if len(last_3) >= 3:
        last_rate = last_3[-1]["rate"]
        if last_rate < -20 and sum(r["rate"] for r in last_3) / 3 < -10:
            is_anomaly = True
            anomaly_type = "sudden_drop"
        elif direction in ["up", "strong_up"] and last_rate < -5:
            is_anomaly = True
            anomaly_type = "uptrend_reversal"

    if len(rates) >= 8 and not is_anomaly:
        recent_4 = rates[-4:]
        older_4 = rates[-8:-4]
        if older_4 and len(recent_4) == 4:
            recent_avg_val = sum(r["rate"] for r in recent_4) / 4
            older_avg_val = sum(r["rate"] for r in older_4) / 4
            recent_var = sum((r["rate"] - recent_avg_val)**2 for r in recent_4) / 4
            older_var = sum((r["rate"] - older_avg_val)**2 for r in older_4) / 4
            if older_var > 0 and recent_var > older_var * 3:
                is_anomaly = True
                anomaly_type = "volatility_spike"

    latest = analysis_data[-1]
    latest_rate = rates[-1] if rates else {"rate": 0}

    emojis = {"strong_up": "🚀", "up": "📈", "down": "📉", "strong_down": "⚠️", "unknown": "❓"}
    emoji = emojis.get(direction, "➡️")

    message = f"{emoji} {latest['date']} | {format_tokens(latest['total'])} | 周环比: {latest_rate['rate']:+.1f}%{latest_week_status}"
    if is_anomaly:
        message += f" | ⚠️ 异常: {anomaly_type}"

    if is_anomaly:
        if anomaly_type == "sudden_drop":
            recommendation = "⚠️ 算力需求骤降！建议：密切关注是否短暂调整还是持续下跌"
        elif anomaly_type == "uptrend_reversal":
            recommendation = "🔄 上涨趋势反转！建议：减仓算力投资，等待趋势确认"
        else:
            recommendation = "📊 波动异常！建议：谨慎操作，等待市场稳定"
    elif direction == "strong_up" and acceleration > 5:
        recommendation = "🚀 算力需求强劲上涨！建议：适度增加算力投资配置"
    elif direction == "strong_up":
        recommendation = "📈 算力需求稳定上涨！建议：保持算力投资，观察趋势变化"
    elif direction == "up":
        if acceleration > 3:
            recommendation = "⬆️ 上涨加速中！建议：适度加仓"
        elif acceleration < -3:
            recommendation = "⬆️ 上涨但增速放缓！建议：保持观察"
        else:
            recommendation = "➡️ 温和上涨！建议：维持当前配置"
    elif direction == "down":
        if acceleration < -3:
            recommendation = "⬇️ 下跌加速！建议：减仓算力投资"
        else:
            recommendation = "⬇️ 算力需求下降！建议：观望等待"
    else:
        recommendation = "➡️ 趋势不明！建议：保持观察"

    return {
        "direction": direction,
        "strength": strength,
        "acceleration": acceleration,
        "is_anomaly": is_anomaly,
        "anomaly_type": anomaly_type,
        "message": message,
        "recommendation": recommendation,
        "latest_total": latest["total"],
        "latest_total_formatted": format_tokens(latest["total"]),
        "latest_change": latest_rate["rate"],
        "recent_avg_change": recent_avg,
        "data_weeks": len(analysis_data),
        "is_incomplete_week": is_incomplete_week,
        "latest_date": latest["date"],
        "alert_level": _get_alert_level(direction, strength, acceleration, is_anomaly, anomaly_type)
    }


def _get_alert_level(direction: str, strength: float, acceleration: float, is_anomaly: bool, anomaly_type: str) -> str:
    """获取警报级别"""
    if is_anomaly and anomaly_type in ["sudden_drop", "uptrend_reversal"]:
        return "critical"
    if is_anomaly:
        return "warning"
    if acceleration < -15 or acceleration > 15:
        return "warning"
    if direction == "strong_up":
        return "attention"
    return "normal"


def save_trend_data(trend_data: Dict, weekly_data: List[Dict]):
    """保存趋势数据到 NB 表"""
    try:
        from deva import NB

        db = NB(TREND_TABLE)

        save_data = {
            "timestamp": datetime.now().isoformat(),
            "trend": trend_data,
            "weekly_history": [
                {
                    "date": w["date"],
                    "total": w["total"],
                    "total_formatted": format_tokens(w["total"])
                }
                for w in weekly_data[-10:]
            ],
            "raw_data": weekly_data[-4:] if len(weekly_data) >= 4 else weekly_data
        }

        db["latest"] = save_data
        db["trend"] = trend_data

        print(f"[OpenRouter] 数据已保存到 {TREND_TABLE} 表")

    except Exception as e:
        print(f"[OpenRouter] 数据保存失败: {e}")


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

        print(f"[OpenRouter] 雷达事件已发送")

    except Exception as e:
        print(f"[OpenRouter] 雷达发送失败: {e}")


async def refresh_openrouter_data() -> Optional[Dict]:
    """刷新 OpenRouter 数据并返回趋势分析结果

    供外部调用的主要接口
    """
    print("[OpenRouter] 开始获取数据...")

    weekly_data = await fetch_weekly_data()
    if not weekly_data:
        print("[OpenRouter] 数据获取失败")
        return None

    print(f"[OpenRouter] 获取到 {len(weekly_data)} 周数据")

    trend_data = analyze_trend(weekly_data)

    save_trend_data(trend_data, weekly_data)

    _update_radar_thread(trend_data)

    if trend_data.get("alert_level") in ["warning", "critical"]:
        send_to_radar(trend_data)

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
        print(f"[OpenRouter] 脉络更新失败: {e}")


def get_openrouter_trend() -> Optional[Dict]:
    """获取缓存的 OpenRouter 趋势数据

    供其他模块查询使用
    """
    try:
        from deva import NB

        db = NB(TREND_TABLE)
        trend = db.get("trend")

        if trend:
            print(f"[OpenRouter] 从缓存获取趋势数据: {trend.get('message', '')[:50]}...")
        else:
            print("[OpenRouter] 缓存中无数据")

        return trend

    except Exception as e:
        print(f"[OpenRouter] 获取缓存失败: {e}")
        return None


def get_openrouter_full_data() -> Optional[Dict]:
    """获取完整的 OpenRouter 数据（包含历史）"""
    try:
        from deva import NB

        db = NB(TREND_TABLE)
        data = db.get("latest")

        if data:
            print(f"[OpenRouter] 获取完整数据: {data.get('timestamp', '')}")
        else:
            print("[OpenRouter] 缓存中无数据")

        return data

    except Exception as e:
        print(f"[OpenRouter] 获取缓存失败: {e}")
        return None


def get_ai_compute_trend() -> Optional[Dict]:
    """获取 AI算力趋势信号（供认知系统使用）

    这个函数返回完整的趋势背景信息，不只是异常告警。
    用于识别"基本面强但价格弱"的背离机会。

    Returns:
        {
            "signal_type": "ai_compute_trend",
            "cumulative_growth": 2.15,      # 累计增长率 (215%)
            "weekly_growth": 0.08,          # 周环比增长率
            "weekly_growth_rate": 0.15,      # 周环比变化率
            "total_tokens": 1_500_000_000_000,
            "trend_direction": "rising",     # rising / falling / stable
            "alert_level": "normal",         # 异常检测
            "is_abnormal": False,
            "related_blocks": ["AI算力", "半导体"],
            "related_symbols": ["NVDA", "AMD", "台积电"],
            "timestamp": ...,
            "message": "...",
            "recommendation": "...",
            "base_strength": 0.85,          # 基础算力需求强度 (0-1)
            "is_incomplete_week": False
        }
    """
    try:
        from deva import NB

        db = NB(TREND_TABLE)
        data = db.get("latest")
        trend = db.get("trend")

        if not data or not trend:
            return None

        weekly_history = data.get("weekly_history", [])

        cumulative_growth = 0.0
        if len(weekly_history) >= 4:
            oldest_total = weekly_history[0]["total"]
            latest_total = weekly_history[-1]["total"]
            if oldest_total > 0:
                cumulative_growth = (latest_total - oldest_total) / oldest_total

        weekly_growth = trend.get("latest_change", 0) / 100.0
        weekly_growth_rate = trend.get("acceleration", 0) / 100.0

        direction = trend.get("direction", "unknown")
        trend_direction_map = {
            "strong_up": "rising",
            "up": "rising",
            "down": "falling",
            "strong_down": "falling",
            "unknown": "stable"
        }
        trend_direction = trend_direction_map.get(direction, "stable")

        base_strength = trend.get("strength", 0.5)

        return {
            "signal_type": "ai_compute_trend",
            "cumulative_growth": round(cumulative_growth, 3),
            "weekly_growth": round(weekly_growth, 4),
            "weekly_growth_rate": round(weekly_growth_rate, 4),
            "total_tokens": trend.get("latest_total", 0),
            "trend_direction": trend_direction,
            "alert_level": trend.get("alert_level", "normal"),
            "is_abnormal": trend.get("is_anomaly", False),
            "related_blocks": ["AI算力", "半导体", "芯片"],
            "related_symbols": ["NVDA", "AMD", "TSLA", "台积电", "SMCI"],
            "timestamp": data.get("timestamp"),
            "message": trend.get("message", ""),
            "recommendation": trend.get("recommendation", ""),
            "base_strength": round(base_strength, 3),
            "is_incomplete_week": trend.get("is_incomplete_week", False),
            "data_weeks": trend.get("data_weeks", 0)
        }

    except Exception as e:
        print(f"[OpenRouter] get_ai_compute_trend 失败: {e}")
        return None


def scheduled_openrouter_check():
    """调度任务：每周一执行"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(refresh_openrouter_data())
        loop.close()

        if result:
            print(f"[OpenRouter Scheduler] 检查完成: {result.get('message', '')}")
        else:
            print(f"[OpenRouter Scheduler] 检查失败")

    except Exception as e:
        print(f"[OpenRouter Scheduler] 执行失败: {e}")


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
