"""
价值观与策略映射

建立价值观类型到具体策略的映射关系
"""

from typing import Dict, List, Any


VALUE_STRATEGY_MAPPING: Dict[str, Dict[str, Any]] = {
    "trend": {
        "primary": "momentum_tracker",
        "secondary": ["block_rotation_hunter"],
        "principles": [
            "趋势一旦形成，不会轻易改变",
            "不要逆势而行",
            "让利润奔跑"
        ],
        "indicators": ["趋势强度", "动量得分", "成交量确认"]
    },
    "contrarian": {
        "primary": "anomaly_sniper",
        "secondary": ["global_sentinel"],
        "principles": [
            "极端下跌是逆向买入的机会",
            "均值终将回归",
            "分歧产生机会"
        ],
        "indicators": ["乖离率", "情绪得分", "成交量萎缩率"]
    },
    "value": {
        "primary": "global_sentinel",
        "secondary": ["anomaly_sniper"],
        "principles": [
            "价格终将回归价值",
            "不要追高",
            "安全边际是第一原则"
        ],
        "indicators": ["PE", "PB", "股息率", "EV/EBITDA"]
    },
    "momentum": {
        "primary": "block_rotation_hunter",
        "secondary": ["momentum_tracker"],
        "principles": [
            "强者恒强，弱者恒弱",
            "趋势延续直到反转信号出现",
            "不要猜顶底"
        ],
        "indicators": ["题材轮动速度", "资金接力强度", "动量得分"]
    },
    "liquidity": {
        "primary": "smart_money_detector",
        "secondary": ["momentum_tracker"],
        "principles": [
            "资金流向决定价格方向",
            "放量突破是真突破",
            "缩量下跌可能见底"
        ],
        "indicators": ["资金流入率", "成交量放大倍数", "主力持仓变化"]
    },
    "balanced": {
        "primary": "global_sentinel",
        "secondary": ["momentum_tracker", "smart_money_detector"],
        "principles": [
            "多元分散，降低风险",
            "趋势跟随 + 价值兜底"
        ],
        "indicators": ["综合得分", "风险调整收益", "相关性"]
    }
}


STRATEGY_TO_VALUE_MAPPING: Dict[str, str] = {
    "momentum_tracker": "trend",
    "anomaly_sniper": "contrarian",
    "smart_money_detector": "liquidity",
    "global_sentinel": "value",
    "block_rotation_hunter": "momentum",
}


def get_primary_strategy(value_type: str) -> str:
    """获取价值观的主要策略"""
    mapping = VALUE_STRATEGY_MAPPING.get(value_type, {})
    return mapping.get("primary", "global_sentinel")


def get_secondary_strategies(value_type: str) -> List[str]:
    """获取价值观的次要策略"""
    mapping = VALUE_STRATEGY_MAPPING.get(value_type, {})
    return mapping.get("secondary", [])


def get_strategy_principles(value_type: str) -> List[str]:
    """获取价值观的核心原则"""
    mapping = VALUE_STRATEGY_MAPPING.get(value_type, {})
    return mapping.get("principles", [])


def get_strategy_indicators(value_type: str) -> List[str]:
    """获取价值观对应的指标"""
    mapping = VALUE_STRATEGY_MAPPING.get(value_type, {})
    return mapping.get("indicators", [])


def infer_value_type(strategy_id: str) -> str:
    """从策略ID推断价值观类型"""
    return STRATEGY_TO_VALUE_MAPPING.get(strategy_id, "balanced")


def get_all_strategies_for_value(value_type: str) -> List[str]:
    """获取价值观对应的所有策略"""
    primary = get_primary_strategy(value_type)
    secondary = get_secondary_strategies(value_type)
    return [primary] + secondary


__all__ = [
    "VALUE_STRATEGY_MAPPING",
    "STRATEGY_TO_VALUE_MAPPING",
    "get_primary_strategy",
    "get_secondary_strategies",
    "get_strategy_principles",
    "get_strategy_indicators",
    "infer_value_type",
    "get_all_strategies_for_value",
]