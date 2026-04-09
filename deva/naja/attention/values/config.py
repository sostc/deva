"""
价值观配置扩展

提供更细粒度的价值观配置选项
"""

from typing import Dict, List, Any
from .types import ValueType, ValueWeights, ValuePreferences, ValueProfile


VALUE_CONFIG: Dict[str, Dict[str, Any]] = {
    "trend": {
        "name": "趋势追踪",
        "description": "顺势而为，追涨杀跌。趋势是你的朋友。",
        "applicable_regimes": ["trend_up", "weak_trend_up"],
        "avoid_regimes": ["trend_down", "neutral"],
        "signals": {
            "buy": "放量突破 + 趋势形成",
            "sell": "趋势破位 + 放量下跌",
            "watch": "震荡整理 + 方向不明"
        },
        "indicators": {
            "price_change_threshold": 2.0,
            "volume_spike_threshold": 1.5,
            "momentum_threshold": 0.6
        },
        "risk_rules": {
            "max_loss_per_trade": 3.0,
            "stop_loss_style": "trailing",
            "position_sizing": "momentum_weighted"
        }
    },
    "contrarian": {
        "name": "逆向投资",
        "description": "人弃我取，分歧买入。别人恐惧时贪婪。",
        "applicable_regimes": ["trend_down", "weak_trend_down", "mixed"],
        "avoid_regimes": ["trend_up"],
        "signals": {
            "buy": "超跌 + 缩量 + 市场恐慌",
            "sell": "超涨 + 情绪狂热",
            "watch": "趋势明确时观望"
        },
        "indicators": {
            "price_drop_threshold": -5.0,
            "volume_shrink_threshold": 0.5,
            "sentiment_terror": 0.8
        },
        "risk_rules": {
            "max_loss_per_trade": 5.0,
            "stop_loss_style": "time_based",
            "position_sizing": "value_weighted"
        }
    },
    "value": {
        "name": "价值投资",
        "description": "均值回归，价格终究合理。安全边际是第一原则。",
        "applicable_regimes": ["neutral", "mixed"],
        "avoid_regimes": ["trend_up", "trend_down"],
        "signals": {
            "buy": "PE低估 + 价格低于价值",
            "sell": "PE高估 + 价格远高于价值",
            "watch": "市场情绪主导时观望"
        },
        "indicators": {
            "pe_threshold_low": 15.0,
            "pe_threshold_high": 30.0,
            "pb_threshold": 3.0,
            "dividend_yield_min": 2.0
        },
        "risk_rules": {
            "max_loss_per_trade": 10.0,
            "stop_loss_style": "fundamental",
            "position_sizing": "value_weighted"
        }
    },
    "momentum": {
        "name": "动量策略",
        "description": "强者恒强，弱者恒弱。趋势延续直到反转信号出现。",
        "applicable_regimes": ["trend_up", "trend_down", "weak_trend_up", "weak_trend_down"],
        "avoid_regimes": ["neutral"],
        "signals": {
            "buy": "题材轮动 + 资金接力",
            "sell": "动量衰竭 + 题材轮动减速",
            "watch": "题材轮动混乱时观望"
        },
        "indicators": {
            "block_rotation_speed": 0.8,
            "fund_flow_consistency": 0.7,
            "momentum_score_min": 0.6
        },
        "risk_rules": {
            "max_loss_per_trade": 4.0,
            "stop_loss_style": "momentum_based",
            "position_sizing": "block_weighted"
        }
    },
    "liquidity": {
        "name": "流动性猎人",
        "description": "资金流向决定价格方向。钱去哪里，价去哪里。",
        "applicable_regimes": ["trend_up", "neutral", "mixed"],
        "avoid_regimes": [],
        "signals": {
            "buy": "资金大幅流入 + 放量突破",
            "sell": "资金大幅流出 + 缩量下跌",
            "watch": "资金流向不明时观望"
        },
        "indicators": {
            "flow_threshold": 2.0,
            "volume_consistency": 0.7,
            "smart_money_ratio": 0.6
        },
        "risk_rules": {
            "max_loss_per_trade": 3.5,
            "stop_loss_style": "flow_based",
            "position_sizing": "flow_weighted"
        }
    },
    "growth": {
        "name": "成长投资",
        "description": "看未来增长潜力，不看当前估值。营收和市场份额是核心。",
        "applicable_regimes": ["trend_up", "weak_trend_up"],
        "avoid_regimes": ["trend_down"],
        "signals": {
            "buy": "营收高增长 + 市场份额扩大",
            "sell": "增长放缓 + 竞争加剧",
            "watch": "宏观经济下行时谨慎"
        },
        "indicators": {
            "revenue_growth_min": 20.0,
            "market_share_change": 2.0,
            "RnD_ratio": 5.0
        },
        "risk_rules": {
            "max_loss_per_trade": 15.0,
            "stop_loss_style": "growth_based",
            "position_sizing": "growth_weighted"
        },
        "implemented": False,
        "pending_strategies": ["growth_stock_screener", "revenue_acceleration_tracker"]
    },
    "event_driven": {
        "name": "事件驱动",
        "description": "重大事件创造Alpha。财报、并购、政策都是机会。",
        "applicable_regimes": ["neutral", "mixed", "trend_up", "trend_down"],
        "avoid_regimes": [],
        "signals": {
            "buy": "财报超预期 + 并购利好 + 政策受益",
            "sell": "事件兑现 + 预期落空",
            "watch": "事件不确定时观望"
        },
        "indicators": {
            "earning Surprise_threshold": 0.1,
            "ma_volume_spike": 3.0,
            "policy_impact_score": 0.7
        },
        "risk_rules": {
            "max_loss_per_trade": 8.0,
            "stop_loss_style": "event_based",
            "position_sizing": "event_weighted"
        },
        "implemented": False,
        "pending_strategies": ["earnings_surprise_detector", "ma_event_listener", "policy_impact_tracker"]
    },
    "market_making": {
        "name": "高频做市",
        "description": "买卖价差收益，量化波动风险。订单簿深度是生命线。",
        "applicable_regimes": ["neutral", "mixed"],
        "avoid_regimes": ["trend_up", "trend_down"],
        "signals": {
            "buy": "价差扩大 + 波动率上升",
            "sell": "价差收窄 + 波动率下降",
            "watch": "极端行情时减少仓位"
        },
        "indicators": {
            "bid_ask_spread": 0.05,
            "order_book_depth": 1000,
            "inventory_risk": 0.3
        },
        "risk_rules": {
            "max_loss_per_trade": 2.0,
            "stop_loss_style": "spread_based",
            "position_sizing": "spread_weighted"
        },
        "implemented": False,
        "pending_strategies": ["spread_hunter", "order_book_analyzer", "inventory_risk_manager"]
    },
    "sentiment_cycle": {
        "name": "情绪周期",
        "description": "恐惧与贪婪的周期博弈。媒体情绪是反向指标。",
        "applicable_regimes": ["mixed", "neutral", "trend_up", "trend_down"],
        "avoid_regimes": [],
        "signals": {
            "buy": "极度恐惧 + 媒体负面 + 逆向买入",
            "sell": "极度贪婪 + 媒体狂热 + 正向卖出",
            "watch": "情绪平稳时观望"
        },
        "indicators": {
            "fear_greed_index": 20.0,
            "media_sentiment_score": 0.3,
            "social_media_heat": 0.8
        },
        "risk_rules": {
            "max_loss_per_trade": 6.0,
            "stop_loss_style": "sentiment_based",
            "position_sizing": "sentiment_weighted"
        },
        "implemented": False,
        "pending_strategies": ["fear_greed_tracker", "media_sentiment_listener", "social_media_heat_detector"]
    },
    "liquidity_rescue": {
        "name": "流动性救援者",
        "description": "在市场恐慌、流动性枯竭时提供流动性支持，等待市场恢复后获利。",
        "applicable_regimes": ["trend_down", "weak_trend_down", "mixed"],
        "avoid_regimes": ["trend_up"],
        "signals": {
            "buy": "恐慌极点 + 流动性枯竭 + 事件开始平息",
            "sell": "流动性恢复 + 价格反弹到合理区间",
            "watch": "恐慌刚开始、卖压仍在加剧时观望"
        },
        "indicators": {
            "panic_index_threshold": 80.0,
            "spread_multiplier": 3.0,
            "volume_shrink_ratio": 0.5,
            "max_holding_days": 30,
            "recovery_wait_days": 7
        },
        "risk_rules": {
            "max_loss_per_trade": 8.0,
            "stop_loss_style": "time_based",
            "position_sizing": "rescue_opportunity_weighted",
            "max_portfolio_allocation": 0.25
        },
        "implemented": False,
        "pending_strategies": ["panic_peak_detector", "liquidity_crisis_tracker", "recovery_confirmation_monitor"],
        "core_principles": [
            "只在流动性最紧张时介入，不在恐慌刚开始时入场",
            "分批建仓，降低单次风险",
            "等待事件影响消退，不猜测底部",
            "恢复正常时果断退出，不贪最后一分钱"
        ],
        "data_requirements": {
            "liquidity_indicators": ["bid_ask_spread", "trading_volume", "order_book_depth"],
            "panic_indicators": ["fear_greed_index", "vix", "media_sentiment"],
            "price_indicators": ["price_drop_speed", "volume_recovery", "price_stabilization"],
            "event_indicators": ["event_impact_fading", "news_sentiment_shift"]
        }
    },
}


REGIME_COMPATIBILITY: Dict[str, List[str]] = {
    "trend_up": ["trend", "momentum", "liquidity"],
    "weak_trend_up": ["trend", "momentum"],
    "neutral": ["value", "liquidity", "balanced"],
    "mixed": ["contrarian", "liquidity", "balanced", "liquidity_rescue"],
    "weak_trend_down": ["contrarian", "momentum", "liquidity_rescue"],
    "trend_down": ["contrarian", "momentum", "liquidity_rescue"],
}


def get_value_config(value_type: str) -> Dict[str, Any]:
    """获取价值观配置详情"""
    return VALUE_CONFIG.get(value_type, {})


def get_compatible_values(regime: str) -> List[str]:
    """获取与市场状态兼容的价值观"""
    return REGIME_COMPATIBILITY.get(regime, ["balanced"])


def is_value_compatible(value_type: str, regime: str) -> bool:
    """判断价值观是否与市场状态兼容"""
    compatible = get_compatible_values(regime)
    return value_type in compatible


__all__ = [
    "VALUE_CONFIG",
    "REGIME_COMPATIBILITY",
    "get_value_config",
    "get_compatible_values",
    "is_value_compatible",
]
