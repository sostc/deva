"""
OpenRouter 监控 - 趋势分析器

负责分析 TOKEN 消耗趋势，检测异常情况
"""

from typing import Dict, List, Optional
from datetime import datetime


class OpenRouterTrendAnalyzer:
    """OpenRouter 趋势分析器"""

    def analyze_trend(self, weekly_data: List[Dict]) -> Dict:
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

        message = f"{emoji} {latest['date']} | {self.format_tokens(latest['total'])} | 周环比: {latest_rate['rate']:+.1f}%{latest_week_status}"
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
            "latest_total_formatted": self.format_tokens(latest["total"]),
            "latest_change": latest_rate["rate"],
            "recent_avg_change": recent_avg,
            "data_weeks": len(analysis_data),
            "is_incomplete_week": is_incomplete_week,
            "latest_date": latest["date"],
            "alert_level": self._get_alert_level(direction, strength, acceleration, is_anomaly, anomaly_type)
        }

    def _get_alert_level(self, direction: str, strength: float, acceleration: float, is_anomaly: bool, anomaly_type: str) -> str:
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

    def format_tokens(self, tokens: int) -> str:
        """格式化 token 数量"""
        if tokens >= 1_000_000_000_000:
            return f"{tokens / 1_000_000_000_000:.2f}T"
        elif tokens >= 1_000_000_000:
            return f"{tokens / 1_000_000_000:.2f}B"
        elif tokens >= 1_000_000:
            return f"{tokens / 1_000_000:.2f}M"
        else:
            return f"{tokens:,}"
