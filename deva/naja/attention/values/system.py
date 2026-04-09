"""
价值观系统核心

提供价值观系统的全局单例访问
"""

import threading
import logging
from typing import Dict, List, Optional, Any

from .types import ValueType, ValueWeights, ValuePreferences, ValueProfile
from .profile import ValueProfileManager
from deva.naja.register import SR


log = logging.getLogger(__name__)


class ValueSystem:
    """
    价值观系统

    核心职责：
    1. 管理多种价值观配置
    2. 根据市场状态选择合适的价值观
    3. 追踪价值观的表现
    4. 通过反馈进化价值观
    """

    def __init__(self):
        self._manager = ValueProfileManager()
        self._active_type: str = "trend"
        self._active_weights: Optional[ValueWeights] = None
        self._active_preferences: Optional[ValuePreferences] = None
        self._recent_attentions: List[Dict[str, Any]] = []
        self._last_decision_reason: str = ""

    def get_active_value_type(self) -> str:
        """获取当前激活的价值观类型"""
        return self._active_type

    def set_active_value_type(self, value_type: str) -> bool:
        """设置当前激活的价值观类型"""
        profile = self._manager.get_profile(value_type)
        if not profile:
            log.warning(f"未找到价值观配置: {value_type}")
            return False

        self._active_type = value_type
        self._active_weights = profile.weights
        self._active_preferences = profile.preferences
        log.info(f"切换价值观: {value_type} ({profile.name})")
        return True

    def get_active_weights(self) -> ValueWeights:
        """获取当前价值观权重"""
        if self._active_weights is None:
            profile = self._manager.get_profile(self._active_type)
            if profile:
                self._active_weights = profile.weights
            else:
                self._active_weights = ValueWeights()
        return self._active_weights

    def get_active_preferences(self) -> ValuePreferences:
        """获取当前价值观偏好"""
        if self._active_preferences is None:
            profile = self._manager.get_profile(self._active_type)
            if profile:
                self._active_preferences = profile.preferences
            else:
                self._active_preferences = ValuePreferences()
        return self._active_preferences

    def get_active_profile(self) -> Optional[ValueProfile]:
        """获取当前激活的价值观配置"""
        return self._manager.get_profile(self._active_type)

    def get_all_profiles(self) -> List[ValueProfile]:
        """获取所有价值观配置"""
        return self._manager.get_all_profiles()

    def get_enabled_profiles(self) -> List[ValueProfile]:
        """获取所有已启用的价值观配置"""
        return self._manager.get_enabled_profiles()

    def record_performance(self, value_type: str, return_pct: float):
        """记录价值观表现"""
        self._manager.record_performance(value_type, return_pct)

    def get_performance(self, value_type: str) -> Dict[str, Any]:
        """获取价值观表现统计"""
        return self._manager.get_performance(value_type)

    def get_all_performances(self) -> Dict[str, Dict[str, Any]]:
        """获取所有价值观表现"""
        return self._manager.get_all_performances()

    def get_suggestions(self) -> List[str]:
        """获取价值观调整建议"""
        return self._manager.get_suggestions()

    def record_attention(self, symbol: str, score: float, reason: str):
        """记录一次注意力事件"""
        import time
        self._recent_attentions.append({
            "symbol": symbol,
            "score": score,
            "reason": reason,
            "timestamp": time.time(),
        })
        if len(self._recent_attentions) > 50:
            self._recent_attentions = self._recent_attentions[-50:]

    def get_recent_attentions(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取最近的注意力事件"""
        return self._recent_attentions[-limit:]

    def set_last_decision_reason(self, reason: str):
        """设置最后决策的理由"""
        self._last_decision_reason = reason

    def get_last_decision_reason(self) -> str:
        """获取最后决策的理由"""
        return self._last_decision_reason

    def calculate_alignment(self, features: Dict[str, Any]) -> float:
        """
        计算事件特征与当前价值观的匹配度

        Args:
            features: 事件特征，包含 price_change, volume_spike 等

        Returns:
            匹配度 (0-1)
        """
        weights = self.get_active_weights()
        active_type = self._active_type

        if active_type == "trend":
            price_score = min(abs(features.get("price_change", 0)) / 5.0, 1.0)
            momentum_score = features.get("momentum", 0.5)
            return (price_score * 0.6 + momentum_score * 0.4) * weights.price_sensitivity

        elif active_type == "contrarian":
            price_score = min(abs(features.get("price_change", 0)) / 8.0, 1.0)
            sentiment = features.get("sentiment", 0.5)
            return (price_score * 0.5 + (1 - sentiment) * 0.5) * weights.price_sensitivity

        elif active_type == "liquidity":
            volume_score = min(features.get("volume_spike", 1) / 3.0, 1.0)
            return volume_score * weights.volume_sensitivity

        elif active_type == "momentum":
            price_score = min(abs(features.get("price_change", 0)) / 3.0, 1.0)
            momentum_score = features.get("momentum", 0.5)
            return (price_score * 0.4 + momentum_score * 0.6) * weights.price_sensitivity

        elif active_type == "value":
            fundamentals_score = features.get("fundamentals_score", 0.5)
            return fundamentals_score * weights.fundamentals_weight

        elif active_type == "liquidity_rescue":
            panic_score = features.get("panic_level", 0) / 100.0
            liquidity_score = features.get("liquidity_score", 0.5)
            recovery_signal = features.get("recovery_signal", 0)

            liquidity_crisis_score = 1.0 - liquidity_score

            alignment = (
                panic_score * 0.35 +
                liquidity_crisis_score * 0.35 +
                recovery_signal * 0.30
            )

            alignment *= weights.liquidity_weight

            return min(1.0, alignment)

        return 0.5

    def generate_focus_reason(self, features: Dict[str, Any]) -> str:
        """
        生成关注理由

        Args:
            features: 事件特征

        Returns:
            关注理由字符串
        """
        active_type = self._active_type
        profile = self.get_active_profile()

        reasons = {
            "trend": f"符合趋势追踪原则，价格变化{features.get('price_change', 0):+.2f}%",
            "contrarian": f"异常信号出现，价格变化{features.get('price_change', 0):+.2f}%，可能出现均值回归",
            "liquidity": f"成交量放大{features.get('volume_spike', 1):.1f}倍，流动性异常",
            "momentum": f"动量信号强劲，趋势有望延续",
            "value": f"基本面优质，可能被低估",
            "balanced": f"多指标综合评分良好",
            "liquidity_rescue": (
                f"流动性救援机会：恐慌程度{features.get('panic_level', 0):.0f}%，"
                f"流动性得分{features.get('liquidity_score', 0.5):.2f}，"
                f"恢复信号{features.get('recovery_signal', 0):.2f}"
            ),
        }

        reason = reasons.get(active_type, "符合当前价值观")
        if profile:
            principle = profile.principles[0] if profile.principles else ""
            if principle:
                reason = f"{reason}。原则：\"{principle}\""
        return reason

    def to_dict(self) -> Dict[str, Any]:
        """导出系统状态"""
        profile = self.get_active_profile()
        return {
            "active_type": self._active_type,
            "active_type_display": ValueType.from_string(self._active_type).display_name,
            "profile": profile.to_dict() if profile else None,
            "weights": self.get_active_weights().to_dict(),
            "preferences": self.get_active_preferences().to_dict(),
            "performance": self.get_all_performances(),
            "suggestions": self.get_suggestions(),
            "recent_attentions": self.get_recent_attentions(5),
            "last_decision_reason": self._last_decision_reason,
        }


def initialize_value_system() -> ValueSystem:
    """初始化价值观系统"""
    vs = SR('value_system')
    if vs.get_active_value_type() == "trend":
        vs.set_active_value_type("trend")
    return vs


__all__ = [
    "ValueSystem",
    "get_value_system",
    "initialize_value_system",
]