"""QKV 可视化页面

展示注意力系统的 Query、Key、Value 实时状态
包含价值观系统可视化
"""

import time
from typing import Dict, Any, List


def get_qkv_data() -> Dict[str, Any]:
    """获取 QKV 实时数据"""
    try:
        from deva.naja.attention.trading_center import get_trading_center
        tc = get_trading_center()
        os = tc.get_attention_os()
        kernel = os.kernel

        query_state = kernel._last_output if hasattr(kernel, '_last_output') else None

        events = []
        try:
            if hasattr(kernel, 'memory') and kernel.memory:
                for item in kernel.memory.store[-10:]:
                    e = item.get("event")
                    if e:
                        events.append({
                            "source": e.source if hasattr(e, 'source') else "unknown",
                            "key": e.key if hasattr(e, 'key') and e.key else e.features if hasattr(e, 'features') else {},
                            "value": e.value if hasattr(e, 'value') and e.value else {},
                            "features": e.features if hasattr(e, 'features') else {},
                            "timestamp": e.timestamp if hasattr(e, 'timestamp') else 0,
                            "score": item.get("score", 0),
                            "age": time.time() - item.get("time", 0) if item.get("time") else 0
                        })
        except Exception:
            pass

        query_data = {
            "harmony_strength": kernel.get_harmony().get("harmony_strength", 0.5),
            "should_act": kernel.get_harmony().get("should_act", False),
        }

        multi_head_result = {}
        try:
            if hasattr(kernel, 'multi_head') and kernel.multi_head:
                for head in kernel.multi_head.heads:
                    head_result = head.compute(query_state, [])
                    multi_head_result[head.name] = head_result
        except Exception:
            pass

        value_data = _get_value_data(query_state, events)

        rescue_state = {}

        return {
            "query": query_data,
            "events": events,
            "multi_head": multi_head_result,
            "values": value_data,
            "rescue_state": rescue_state,
            "timestamp": time.time(),
            "has_data": True
        }

    except Exception as e:
        return _get_empty_qkv_data()


def _get_value_data(query_state, events) -> Dict[str, Any]:
    """获取价值观数据"""
    try:
        from deva.naja.attention.values import get_value_system
        vs = get_value_system()
        performances = vs.get_all_performances() if vs else {}
        recent_attentions = vs.get_recent_attentions(5) if vs else []

        profiles = vs.get_all_profiles() if vs else []
        profile_list = [p.to_dict() for p in profiles] if profiles else []

        strategy_mapping = _get_strategy_value_mapping()

        return {
            "active_type": "trend",
            "active_type_display": "趋势追踪",
            "weights": {},
            "preferences": {},
            "suggestions": [],
            "performances": performances,
            "recent_attentions": recent_attentions,
            "profiles": profile_list,
            "strategy_mapping": strategy_mapping,
            "has_data": True
        }

    except Exception:
        return _get_empty_value_data()


def _get_strategy_value_mapping() -> Dict[str, Any]:
    """获取策略-价值观映射"""
    return {}


def _get_empty_qkv_data() -> Dict[str, Any]:
    """返回空的 QKV 数据"""
    return {
        "query": {},
        "events": [],
        "multi_head": {},
        "values": _get_empty_value_data(),
        "rescue_state": {},
        "timestamp": time.time(),
        "has_data": False
    }


def _get_empty_value_data() -> Dict[str, Any]:
    """返回空的价值观数据"""
    return {
        "active_type": "trend",
        "active_type_display": "趋势追踪",
        "weights": {},
        "preferences": {},
        "suggestions": [],
        "performances": {},
        "recent_attentions": [],
        "profiles": [],
        "strategy_mapping": {},
        "has_data": False
    }
