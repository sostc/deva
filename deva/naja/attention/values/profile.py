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
            name="趋势追踪",
            value_type=ValueType.TREND,
            description="顺势而为，追涨杀跌。趋势是你的朋友。",
            weights=ValueWeights(
                price_sensitivity=0.8,
                volume_sensitivity=0.6,
                sentiment_weight=0.4,
                liquidity_weight=0.3,
                fundamentals_weight=0.2,
            ),
            preferences=ValuePreferences(
                risk_preference=0.6,
                time_horizon=0.3,
                concentration=0.5,
            ),
            applicable_regimes=["trend_up", "weak_trend_up"],
            principles=[
                "趋势一旦形成，不会轻易改变",
                "不要逆势而行",
                "让利润奔跑"
            ]
        ),
        ValueProfile(
            name="逆向投资",
            value_type=ValueType.CONTRARIAN,
            description="人弃我取，分歧买入。别人恐惧时贪婪。",
            weights=ValueWeights(
                price_sensitivity=0.6,
                volume_sensitivity=0.4,
                sentiment_weight=0.7,
                liquidity_weight=0.5,
                fundamentals_weight=0.5,
            ),
            preferences=ValuePreferences(
                risk_preference=0.3,
                time_horizon=0.8,
                concentration=0.3,
            ),
            applicable_regimes=["trend_down", "weak_trend_down", "mixed"],
            principles=[
                "极端行情是逆向投资者的机会",
                "均值终将回归",
                "分歧产生机会"
            ]
        ),
        ValueProfile(
            name="价值投资",
            value_type=ValueType.VALUE,
            description="均值回归，价格终究合理。安全边际是第一原则。",
            weights=ValueWeights(
                price_sensitivity=0.4,
                volume_sensitivity=0.3,
                sentiment_weight=0.3,
                liquidity_weight=0.3,
                fundamentals_weight=0.8,
            ),
            preferences=ValuePreferences(
                risk_preference=0.2,
                time_horizon=0.9,
                concentration=0.4,
            ),
            applicable_regimes=["neutral", "mixed"],
            principles=[
                "价格终将回归价值",
                "不要追高",
                "安全边际是第一原则"
            ]
        ),
        ValueProfile(
            name="动量策略",
            value_type=ValueType.MOMENTUM,
            description="强者恒强，弱者恒弱。趋势延续直到反转信号出现。",
            weights=ValueWeights(
                price_sensitivity=0.7,
                volume_sensitivity=0.5,
                sentiment_weight=0.5,
                liquidity_weight=0.4,
                fundamentals_weight=0.2,
            ),
            preferences=ValuePreferences(
                risk_preference=0.5,
                time_horizon=0.5,
                concentration=0.6,
            ),
            applicable_regimes=["trend_up", "trend_down", "weak_trend_up", "weak_trend_down"],
            principles=[
                "强者恒强，弱者恒弱",
                "趋势延续直到反转信号出现",
                "不要猜顶底"
            ]
        ),
        ValueProfile(
            name="流动性猎人",
            value_type=ValueType.LIQUIDITY,
            description="资金流向决定价格方向。钱去哪里，价去哪里。",
            weights=ValueWeights(
                price_sensitivity=0.5,
                volume_sensitivity=0.9,
                sentiment_weight=0.3,
                liquidity_weight=0.9,
                fundamentals_weight=0.2,
            ),
            preferences=ValuePreferences(
                risk_preference=0.5,
                time_horizon=0.4,
                concentration=0.5,
            ),
            applicable_regimes=["trend_up", "neutral", "mixed"],
            principles=[
                "资金流向决定价格方向",
                "放量突破是真突破",
                "缩量下跌可能见底"
            ]
        ),
        ValueProfile(
            name="流动性救援者",
            value_type=ValueType.LIQUIDITY_RESCUE,
            description="在市场恐慌、流动性枯竭时提供流动性支持，等待市场恢复后获利。",
            weights=ValueWeights(
                price_sensitivity=0.3,
                volume_sensitivity=0.9,
                sentiment_weight=0.6,
                liquidity_weight=0.9,
                fundamentals_weight=0.4,
            ),
            preferences=ValuePreferences(
                risk_preference=0.7,
                time_horizon=0.4,
                concentration=0.5,
            ),
            applicable_regimes=["trend_down", "weak_trend_down", "mixed"],
            principles=[
                "只在流动性最紧张时介入",
                "分批建仓，不猜底部",
                "等待事件消退，恢复后退出"
            ],
            implemented=True,
            pending_strategies=["level2_order_book", "vix_index"]
        ),
        ValueProfile(
            name="成长投资",
            value_type=ValueType.GROWTH,
            description="看未来增长潜力，不看当前估值。营收和市场份额是核心。",
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
            applicable_regimes=["trend_up", "weak_trend_up"],
            principles=[
                "看未来增长潜力",
                "营收和市场份额是核心",
                "高风险高回报"
            ],
            implemented=False,
            pending_strategies=["growth_stock_screener", "revenue_acceleration_tracker"]
        ),
        ValueProfile(
            name="事件驱动",
            value_type=ValueType.EVENT_DRIVEN,
            description="重大事件创造Alpha。财报、并购、政策都是机会。",
            weights=ValueWeights(
                price_sensitivity=0.5,
                volume_sensitivity=0.6,
                sentiment_weight=0.8,
                liquidity_weight=0.4,
                fundamentals_weight=0.4,
            ),
            preferences=ValuePreferences(
                risk_preference=0.6,
                time_horizon=0.3,
                concentration=0.5,
            ),
            applicable_regimes=["neutral", "mixed", "trend_up", "trend_down"],
            principles=[
                "重大事件创造Alpha",
                "财报、并购、政策都是机会",
                "事件兑现前入场"
            ],
            implemented=False,
            pending_strategies=["earnings_surprise_detector", "ma_event_listener", "policy_impact_tracker"]
        ),
        ValueProfile(
            name="高频做市",
            value_type=ValueType.MARKET_MAKING,
            description="买卖价差收益，量化波动风险。订单簿深度是生命线。",
            weights=ValueWeights(
                price_sensitivity=0.9,
                volume_sensitivity=0.8,
                sentiment_weight=0.1,
                liquidity_weight=0.9,
                fundamentals_weight=0.1,
            ),
            preferences=ValuePreferences(
                risk_preference=0.3,
                time_horizon=0.1,
                concentration=0.2,
            ),
            applicable_regimes=["neutral", "mixed"],
            principles=[
                "买卖价差收益",
                "量化波动风险",
                "订单簿深度是生命线"
            ],
            implemented=False,
            pending_strategies=["spread_hunter", "order_book_analyzer", "inventory_risk_manager"]
        ),
        ValueProfile(
            name="情绪周期",
            value_type=ValueType.SENTIMENT_CYCLE,
            description="恐惧与贪婪的周期博弈。媒体情绪是反向指标。",
            weights=ValueWeights(
                price_sensitivity=0.4,
                volume_sensitivity=0.5,
                sentiment_weight=0.9,
                liquidity_weight=0.3,
                fundamentals_weight=0.2,
            ),
            preferences=ValuePreferences(
                risk_preference=0.5,
                time_horizon=0.5,
                concentration=0.4,
            ),
            applicable_regimes=["mixed", "neutral", "trend_up", "trend_down"],
            principles=[
                "恐惧与贪婪的周期博弈",
                "媒体情绪是反向指标",
                "别人恐惧我贪婪"
            ],
            implemented=False,
            pending_strategies=["fear_greed_tracker", "media_sentiment_listener", "social_media_heat_detector"]
        ),
    ]


__all__ = [
    "ValueProfileManager",
    "get_default_profiles",
]