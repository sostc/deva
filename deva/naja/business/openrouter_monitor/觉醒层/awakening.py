"""
OpenRouter 监控 - 觉醒层

影响觉醒系统的逻辑，提供觉醒相关的信号
"""

from typing import Dict, Optional


class OpenRouterAwakening:
    """OpenRouter 觉醒影响模块"""

    def generate_awakening_signal(self, trend_data: Dict) -> Dict:
        """生成觉醒系统信号

        Args:
            trend_data: 趋势分析结果

        Returns:
            觉醒系统信号
        """
        if not trend_data:
            return {
                "signal_type": "ai_compute_trend",
                "strength": 0.0,
                "confidence": 0.0,
                "message": "数据不足，无法生成觉醒信号",
                "impact_level": "low"
            }

        direction = trend_data.get("direction", "unknown")
        strength = trend_data.get("strength", 0)
        acceleration = trend_data.get("acceleration", 0)
        is_anomaly = trend_data.get("is_anomaly", False)
        alert_level = trend_data.get("alert_level", "normal")

        # 计算觉醒信号强度
        signal_strength = 0.0
        if direction in ["strong_up", "up"]:
            signal_strength = min(1.0, strength + abs(acceleration) / 50)
        elif direction in ["strong_down", "down"]:
            signal_strength = min(1.0, strength + abs(acceleration) / 50)
        elif is_anomaly:
            signal_strength = min(1.0, 0.7 + strength)

        # 确定影响级别
        if alert_level == "critical":
            impact_level = "high"
        elif alert_level == "warning":
            impact_level = "medium"
        elif direction == "strong_up" and acceleration > 5:
            impact_level = "medium"
        else:
            impact_level = "low"

        # 生成觉醒消息
        if direction == "strong_up":
            message = "AI 算力需求强劲上涨，可能影响相关行业投资机会"
        elif direction == "up":
            message = "AI 算力需求持续上涨，关注相关行业发展"
        elif direction == "down":
            message = "AI 算力需求下降，可能影响相关行业业绩"
        elif direction == "strong_down":
            message = "AI 算力需求大幅下降，需警惕相关行业风险"
        elif is_anomaly:
            message = "AI 算力需求出现异常波动，需密切关注"
        else:
            message = "AI 算力需求趋势稳定，保持观察"

        return {
            "signal_type": "ai_compute_trend",
            "strength": signal_strength,
            "confidence": min(1.0, signal_strength + 0.2),
            "message": message,
            "impact_level": impact_level,
            "trend_direction": direction,
            "trend_strength": strength,
            "acceleration": acceleration,
            "alert_level": alert_level
        }
