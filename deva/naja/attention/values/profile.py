"""
价值观配置管理

管理多种价值观配置的注册、切换和查询
"""

import time
import threading
import logging
from typing import Dict, List, Optional, Any
from collections import defaultdict

from .types import ValueType, ValueWeights, ValuePreferences, ValueProfile, InvestmentDirection


log = logging.getLogger(__name__)


class ValueProfileManager:
    """
    价值观配置管理器

    负责管理多个价值观配置的注册、查询、切换
    """

    def __init__(self):
        self._profiles: Dict[str, ValueProfile] = {}
        self._performance_history: Dict[str, List[float]] = defaultdict(list)
        self._trade_count: Dict[str, int] = defaultdict(int)
        self._lock = threading.RLock()
        self._init_default_profiles()

    def _init_default_profiles(self):
        """初始化默认价值观配置"""
        defaults = get_default_profiles()
        for profile in defaults:
            self.register_profile(profile)

    def register_profile(self, profile: ValueProfile) -> bool:
        """注册价值观配置"""
        with self._lock:
            if profile.value_type.value in self._profiles:
                log.warning(f"价值观配置 {profile.value_type.value} 已存在，将被覆盖")
            self._profiles[profile.value_type.value] = profile
            log.info(f"注册价值观配置: {profile.name} ({profile.value_type.value})")
            return True

    def get_profile(self, value_type: str) -> Optional[ValueProfile]:
        """获取价值观配置"""
        with self._lock:
            return self._profiles.get(value_type)

    def get_all_profiles(self) -> List[ValueProfile]:
        """获取所有价值观配置"""
        with self._lock:
            return list(self._profiles.values())

    def get_enabled_profiles(self) -> List[ValueProfile]:
        """获取所有已启用的价值观配置"""
        with self._lock:
            return [p for p in self._profiles.values() if p.enabled]

    def enable_profile(self, value_type: str) -> bool:
        """启用价值观配置"""
        with self._lock:
            profile = self._profiles.get(value_type)
            if profile:
                profile.enabled = True
                profile.last_modified = time.time()
                return True
            return False

    def disable_profile(self, value_type: str) -> bool:
        """禁用价值观配置"""
        with self._lock:
            profile = self._profiles.get(value_type)
            if profile:
                profile.enabled = False
                profile.last_modified = time.time()
                return True
            return False

    def update_profile_weight(self, value_type: str, weight: float) -> bool:
        """更新价值观配置权重"""
        with self._lock:
            profile = self._profiles.get(value_type)
            if profile:
                profile.weight = max(0.0, min(2.0, weight))
                profile.last_modified = time.time()
                return True
            return False

    def record_performance(self, value_type: str, return_pct: float):
        """记录价值观表现"""
        with self._lock:
            self._performance_history[value_type].append(return_pct)
            self._trade_count[value_type] += 1
            if len(self._performance_history[value_type]) > 1000:
                self._performance_history[value_type] = self._performance_history[value_type][-1000:]

    def get_performance(self, value_type: str) -> Dict[str, Any]:
        """获取价值观表现统计"""
        with self._lock:
            returns = self._performance_history.get(value_type, [])
            if not returns:
                return {
                    "avg_return": 0.0,
                    "total_trades": 0,
                    "win_rate": 0.0,
                    "confidence": 0.0,
                }

            wins = [r for r in returns if r > 0]
            return {
                "avg_return": sum(returns) / len(returns),
                "total_trades": len(returns),
                "win_rate": len(wins) / len(returns) if returns else 0.0,
                "confidence": min(len(returns) / 20.0, 1.0),
            }

    def get_all_performances(self) -> Dict[str, Dict[str, Any]]:
        """获取所有价值观表现"""
        with self._lock:
            return {vt: self.get_performance(vt) for vt in self._profiles.keys()}

    def get_suggestions(self) -> List[str]:
        """获取价值观调整建议"""
        suggestions = []
        with self._lock:
            for value_type, profile in self._profiles.items():
                if not profile.enabled:
                    continue
                perf = self.get_performance(value_type)
                if perf["total_trades"] < 3:
                    continue

                avg = perf["avg_return"]
                if avg > 5:
                    suggestions.append(f"📈 {profile.name}表现优秀({avg:+.1f}%)，建议增配")
                elif avg < -3:
                    suggestions.append(f"⚠️ {profile.name}表现不佳({avg:+.1f}%)，建议减配")
                else:
                    suggestions.append(f"➡️ {profile.name}表现稳定({avg:+.1f}%)，保持观察")
        return suggestions


def get_default_profiles() -> List[ValueProfile]:
    """获取默认价值观配置"""
    return [
        ValueProfile(
            name="先进生产力",
            value_type=ValueType.GROWTH,
            description="投资带领科技往前发展的公司，AI是核心，提高社会生产力。",
            weights=ValueWeights(
                price_sensitivity=0.3,
                volume_sensitivity=0.3,
                sentiment_weight=0.2,
                liquidity_weight=0.3,
                fundamentals_weight=0.9,
            ),
            preferences=ValuePreferences(
                risk_preference=0.7,
                time_horizon=0.8,
                concentration=0.6,
            ),
            applicable_regimes=["trend_up", "weak_trend_up", "neutral", "mixed"],
            principles=[
                "投资真正推动世界进步的公司",
                "AI是核心，代表先进生产力",
                "科技提高社会效率"
            ],
            implemented=True,
        ),
        ValueProfile(
            name="代表人民利益",
            value_type=ValueType.GROWTH,
            description="发现社会需要的、存在的问题，投资能解决供需关系的公司。",
            weights=ValueWeights(
                price_sensitivity=0.3,
                volume_sensitivity=0.3,
                sentiment_weight=0.4,
                liquidity_weight=0.3,
                fundamentals_weight=0.9,
            ),
            preferences=ValuePreferences(
                risk_preference=0.6,
                time_horizon=0.7,
                concentration=0.5,
            ),
            applicable_regimes=["trend_up", "weak_trend_up", "neutral", "mixed"],
            principles=[
                "发现社会面临的供需问题",
                "投资能解决人民需求的赛道",
                "代表先进生产力的发展方向"
            ],
            implemented=True,
        ),
        ValueProfile(
            name="先进文化方向",
            value_type=ValueType.GROWTH,
            description="投资拥有先进组织文化和精神理念的创新开拓者。",
            weights=ValueWeights(
                price_sensitivity=0.3,
                volume_sensitivity=0.3,
                sentiment_weight=0.3,
                liquidity_weight=0.3,
                fundamentals_weight=0.8,
            ),
            preferences=ValuePreferences(
                risk_preference=0.7,
                time_horizon=0.8,
                concentration=0.6,
            ),
            applicable_regimes=["trend_up", "weak_trend_up", "neutral", "mixed"],
            principles=[
                "寻找创新的先进组织文化",
                "投资有精神理念的开拓者",
                "代表先进文化思想"
            ],
            implemented=True,
        ),
    ]


__all__ = [
    "ValueProfileManager",
    "get_default_profiles",
]