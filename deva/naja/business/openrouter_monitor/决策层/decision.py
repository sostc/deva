"""
OpenRouter 监控 - 决策层

基于趋势分析结果生成决策建议和投资建议
"""

from typing import Dict, Optional


class OpenRouterDecisionMaker:
    """OpenRouter 决策生成器"""

    def generate_decision(self, trend_data: Dict) -> Dict:
        """基于趋势分析结果生成决策建议

        Args:
            trend_data: 趋势分析结果

        Returns:
            决策建议
        """
        if not trend_data:
            return {
                "decision": "wait",
                "confidence": 0.0,
                "message": "数据不足，无法生成决策",
                "recommendation": "等待更多数据"
            }

        direction = trend_data.get("direction", "unknown")
        strength = trend_data.get("strength", 0)
        acceleration = trend_data.get("acceleration", 0)
        is_anomaly = trend_data.get("is_anomaly", False)
        anomaly_type = trend_data.get("anomaly_type", "")
        alert_level = trend_data.get("alert_level", "normal")

        # 生成决策
        if is_anomaly:
            if anomaly_type == "sudden_drop":
                decision = "reduce"
                confidence = 0.8
                message = "算力需求骤降，建议减少算力相关投资"
                recommendation = "⚠️ 算力需求骤降！建议：密切关注是否短暂调整还是持续下跌"
            elif anomaly_type == "uptrend_reversal":
                decision = "reduce"
                confidence = 0.7
                message = "上涨趋势反转，建议减少算力相关投资"
                recommendation = "🔄 上涨趋势反转！建议：减仓算力投资，等待趋势确认"
            else:
                decision = "wait"
                confidence = 0.5
                message = "波动异常，建议观望"
                recommendation = "📊 波动异常！建议：谨慎操作，等待市场稳定"
        elif direction == "strong_up" and acceleration > 5:
            decision = "increase"
            confidence = 0.8
            message = "算力需求强劲上涨，建议增加算力相关投资"
            recommendation = "🚀 算力需求强劲上涨！建议：适度增加算力投资配置"
        elif direction == "strong_up":
            decision = "hold"
            confidence = 0.7
            message = "算力需求稳定上涨，建议保持算力相关投资"
            recommendation = "📈 算力需求稳定上涨！建议：保持算力投资，观察趋势变化"
        elif direction == "up":
            if acceleration > 3:
                decision = "increase"
                confidence = 0.6
                message = "上涨加速中，建议适度加仓"
                recommendation = "⬆️ 上涨加速中！建议：适度加仓"
            elif acceleration < -3:
                decision = "hold"
                confidence = 0.6
                message = "上涨但增速放缓，建议保持观察"
                recommendation = "⬆️ 上涨但增速放缓！建议：保持观察"
            else:
                decision = "hold"
                confidence = 0.5
                message = "温和上涨，建议维持当前配置"
                recommendation = "➡️ 温和上涨！建议：维持当前配置"
        elif direction == "down":
            if acceleration < -3:
                decision = "reduce"
                confidence = 0.7
                message = "下跌加速，建议减仓算力投资"
                recommendation = "⬇️ 下跌加速！建议：减仓算力投资"
            else:
                decision = "wait"
                confidence = 0.5
                message = "算力需求下降，建议观望等待"
                recommendation = "⬇️ 算力需求下降！建议：观望等待"
        else:
            decision = "wait"
            confidence = 0.4
            message = "趋势不明，建议保持观察"
            recommendation = "➡️ 趋势不明！建议：保持观察"

        return {
            "decision": decision,
            "confidence": confidence,
            "message": message,
            "recommendation": recommendation,
            "alert_level": alert_level,
            "direction": direction,
            "strength": strength,
            "acceleration": acceleration
        }
