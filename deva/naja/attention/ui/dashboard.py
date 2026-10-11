"""Attention System Dashboard - 注意力系统状态监控

展示注意力系统的核心能力：
1. 事件编码 - EventEncoder: 事件 → Key/Value 投影
2. 多维评分 - MultiScorer: 融合价格、情绪，资金流、历史Alpha四个维度
3. 末那识决策 - ManasEngine: 天时+地势+人和三维融合决策
4. 策略学习 - StrategyLearning: 基于Bandit的市场状态适应
5. 注意力记忆 - AttentionMemory: 持久化注意力历史（已移除，由Cognition提供）
6. 快照历史 - SnapshotManager: 经典时刻回放
"""

import time
from typing import Dict, Any, List


def get_attention_monitor_data() -> Dict[str, Any]:
    """获取注意力系统完整状态数据"""
    try:
        from deva.naja.attention.orchestration.trading_center import get_trading_center
        tc = get_trading_center()
        os = tc.get_attention_os()
        kernel = os.kernel

        return {
            "event_encoder": _get_event_encoder_state(kernel),
            "multi_scorer": _get_multi_scorer_state(kernel),
            "manas_engine": _get_manas_engine_state(kernel),
            "manas_gate_audit": _get_gate_audit_state(),
            "strategy_learning": _get_strategy_learning_state(os),
            "attention_memory": _get_memory_state(kernel),
            "symbol_weights": _get_symbol_weights_state(kernel),
            "transformer_attention": _get_transformer_attention_state(kernel),
            "in_context_learning": _get_in_context_learning_state(kernel),
            "timestamp": time.time(),
            "has_data": True
        }
    except Exception:
        return _get_empty_monitor_data()


def _get_event_encoder_state(kernel) -> Dict[str, Any]:
    """获取事件编码器状态"""
    encoder_state = {
        "enabled": hasattr(kernel, 'encoder') and kernel.encoder is not None,
        "encoded_events": [],
        "encoding_summary": {
            "total_encoded": 0,
            "key_features": ["price_change", "sentiment", "volume_spike", "historical_alpha"],
            "value_features": ["alpha", "risk", "confidence"]
        }
    }
    return encoder_state


def _get_multi_scorer_state(kernel) -> Dict[str, Any]:
    """获取多维评分器状态"""
    scorer_state = {
        "enabled": hasattr(kernel, 'multi_head') and kernel.multi_head is not None,
        "heads": {},
        "fusion_result": {"alpha": 0, "risk": 0, "confidence": 0}
    }

    try:
        if hasattr(kernel, 'multi_head') and kernel.multi_head:
            for head in kernel.multi_head.heads:
                head_result = head.compute(kernel.get_harmony(), [])
                scorer_state["heads"][head.name] = {
                    "alpha": head_result.get("alpha", 0),
                    "risk": head_result.get("risk", 0),
                    "confidence": head_result.get("confidence", 0),
                    "scorer_type": _get_scorer_type(head.name)
                }
            scorer_state["fusion_result"] = kernel.multi_head.compute(kernel.get_harmony(), [])
    except Exception:
        pass

    return scorer_state


def _read_engine_components(engine, score_key: str, component_keys) -> Dict[str, Any]:
    """读子引擎最近一次 compute 的分量与分数。

    此前这里写 `getattr(te, '_time_pressure', 0)` 这类读法，而这些属性**从未存在**
    → 时序/环境面板的分量恒为 0，是个死面板。现在统一走子引擎自己在 compute 里
    记录的 `get_last_components()`；并且优先复用**打分路径那一次**的分量，
    而不是在这里再 compute 一遍（旧写法用无参 compute()，喂不到 scanner，
    面板分数与内核打分不一致）。
    """
    comp: Dict[str, Any] = {}
    if hasattr(engine, "get_last_components"):
        comp = dict(engine.get_last_components() or {})
    if not comp:
        # 从未 compute 过（例如启动后还没跑过 tick）：兜底算一次
        try:
            engine.compute()
        except Exception:
            pass
        if hasattr(engine, "get_last_components"):
            comp = dict(engine.get_last_components() or {})

    return {
        "score": comp.get(score_key, 0.0),
        "components": {k: comp.get(k, 0) for k in component_keys},
        "extra": {k: v for k, v in comp.items()
                  if k not in component_keys and k != score_key},
    }


def _get_manas_engine_state(kernel) -> Dict[str, Any]:
    """获取末那识引擎状态"""
    manas_state = {
        "available": False,
        "timing_engine": {},
        "regime_engine": {},
        "confidence_engine": {},
        "risk_engine": {},
        "meta_manas": {},
        "output": {}
    }

    try:
        manas = kernel.get_manas_engine()
        if manas is None:
            return manas_state

        manas_state["available"] = True

        if getattr(manas, 'timing_engine', None):
            manas_state["timing_engine"] = _read_engine_components(
                manas.timing_engine, "timing_score",
                ("time_pressure", "volatility", "density", "structure"))

        if getattr(manas, 'regime_engine', None):
            manas_state["regime_engine"] = _read_engine_components(
                manas.regime_engine, "regime_score",
                ("trend", "liquidity", "diffusion"))

        if getattr(manas, 'confidence_engine', None):
            manas_state["confidence_engine"] = _read_engine_components(
                manas.confidence_engine, "confidence_score",
                ("hit_rate", "rolling_pnl", "bandit_confidence"))

        if getattr(manas, 'risk_engine', None):
            manas_state["risk_engine"] = _read_engine_components(
                manas.risk_engine, "risk_temperature",
                ("cash_ratio", "drawdown", "volatility"))

        if getattr(manas, 'meta_manas', None):
            mm = manas.meta_manas
            mm_state = mm.get_state() if hasattr(mm, 'get_state') else {}
            manas_state["meta_manas"] = {
                "bias_state": mm_state.get("bias_state", "neutral"),
                "bias_direction": mm_state.get("bias_direction", "none"),
                # 教练语：把内部纠偏乘子翻译成给人看的提醒
                "bias_message": mm_state.get("bias_message", ""),
                "avg_aggressiveness": mm_state.get("avg_aggressiveness", 0),
                "aggressiveness_samples": mm_state.get("aggressiveness_samples", 0),
            }

        harmony = kernel.get_harmony()
        manas_state["output"] = {
            "harmony_state": harmony.get("harmony_state", "unknown"),
            "harmony_strength": harmony.get("harmony_strength", 0),
            "should_act": harmony.get("should_act", False),
            "action_type": harmony.get("action_type", "hold")
        }
    except Exception:
        pass

    return manas_state


def _get_gate_audit_state() -> Dict[str, Any]:
    """获取行动门留痕（「为什么不让你动」按次可查）。"""
    try:
        from deva.naja.attention.kernel.manas_gate_audit import get_gate_audit_log
        log = get_gate_audit_log()
        return {
            "available": True,
            "stats": log.stats(),
            "recent": log.recent(limit=20),
        }
    except Exception:
        return {"available": False, "stats": {}, "recent": []}


def _get_strategy_learning_state(os) -> Dict[str, Any]:
    """获取策略学习状态"""
    learning_state = {
        "available": False,
        "market_state": {},
        "selected_strategies": [],
        "strategy_performance": {},
        "learning_stats": {}
    }

    try:
        if hasattr(os, 'strategy_learning') and os.strategy_learning:
            sl = os.strategy_learning
            learning_state["available"] = True

            if hasattr(sl, 'state_detector') and sl.state_detector:
                current_state = sl.state_detector.get_current_state()
                if current_state:
                    learning_state["market_state"] = {
                        "name": sl.state_detector.get_state_name(current_state),
                        "volatility": current_state.volatility,
                        "trend": current_state.trend,
                        "liquidity": current_state.liquidity
                    }

            if hasattr(sl, 'bandit') and sl.bandit:
                perf = sl.bandit.get_all_performance()
                learning_state["strategy_performance"] = {
                    sid: {"total_reward": sp.total_reward, "play_count": sp.play_count, "avg_reward": sp.avg_reward}
                    for sid, sp in perf.items()
                }

            if hasattr(sl, 'get_learning_stats'):
                learning_state["learning_stats"] = sl.get_learning_stats()

            selected = sl.select_strategies(global_attention=0.5, block_attention={}, available_strategies=list(learning_state["strategy_performance"].keys()), top_k=3)
            if selected:
                learning_state["selected_strategies"] = selected.selected_strategies
    except Exception:
        pass

    return learning_state


def _get_memory_state(kernel) -> Dict[str, Any]:
    """获取注意力记忆状态（已移除，由Cognition提供）"""
    return {
        "enabled": False,
        "total_events": 0,
        "recent_events": [],
        "memory_stats": {},
        "note": "Memory moved to Cognition system"
    }


def _get_symbol_weights_state(kernel) -> Dict[str, Any]:
    """获取 symbol weights 状态"""
    weights_state = {"top_symbols": [], "top_blocks": [], "total_symbols": 0}
    try:
        if hasattr(kernel, 'get_top_symbols'):
            weights_state["top_symbols"] = kernel.get_top_symbols(10)
            weights_state["total_symbols"] = len(weights_state["top_symbols"])
        if hasattr(kernel, 'get_top_blocks'):
            weights_state["top_blocks"] = kernel.get_top_blocks(5)
    except Exception:
        pass
    return weights_state


def _get_scorer_type(head_name: str) -> str:
    """获取评分器类型描述"""
    scorer_map = {
        "market": "价格变动评分", "news": "新闻情绪评分", "flow": "资金流评分",
        "meta": "历史Alpha评分", "trend": "趋势评分", "reversal": "反转评分", "breakout": "突破评分"
    }
    return scorer_map.get(head_name, "未知评分")


def _get_transformer_attention_state(kernel) -> Dict[str, Any]:
    """获取Transformer自注意力状态"""
    transformer_state = {
        "enabled": hasattr(kernel, '_enable_transformer') and kernel._enable_transformer,
        "available": hasattr(kernel, '_transformer_layer') and kernel._transformer_layer is not None,
        "feature_encoder": hasattr(kernel, '_feature_encoder') and kernel._feature_encoder is not None,
        "config": {
            "d_model": getattr(kernel, '_transformer_layer', {}).d_model if hasattr(kernel, '_transformer_layer') and hasattr(kernel._transformer_layer, 'd_model') else 0,
            "num_heads": getattr(kernel, '_transformer_layer', {}).num_heads if hasattr(kernel, '_transformer_layer') and hasattr(kernel._transformer_layer, 'num_heads') else 0,
            "d_ff": getattr(kernel, '_transformer_layer', {}).ffn.d_ff if hasattr(kernel, '_transformer_layer') and hasattr(kernel._transformer_layer, 'ffn') and hasattr(kernel._transformer_layer.ffn, 'd_ff') else 0
        }
    }
    return transformer_state


def _get_in_context_learning_state(kernel) -> Dict[str, Any]:
    """获取上下文学习状态"""
    learning_state = {
        "enabled": hasattr(kernel, '_enable_in_context') and kernel._enable_in_context,
        "available": hasattr(kernel, '_in_context_learner') and kernel._in_context_learner is not None,
        "demo_statistics": {}
    }
    
    try:
        if hasattr(kernel, '_in_context_learner') and kernel._in_context_learner:
            learning_state["demo_statistics"] = kernel._in_context_learner.get_demo_statistics()
    except Exception:
        pass
    
    return learning_state


def _get_empty_monitor_data() -> Dict[str, Any]:
    """返回空的监控数据"""
    return {
        "event_encoder": {"enabled": False, "encoded_events": [], "encoding_summary": {"total_encoded": 0}},
        "multi_scorer": {"enabled": False, "heads": {}, "fusion_result": {}},
        "manas_engine": {"available": False, "timing_engine": {}, "regime_engine": {}, "output": {}},
        "manas_gate_audit": {"available": False, "stats": {}, "recent": []},
        "strategy_learning": {"available": False, "market_state": {}, "selected_strategies": []},
        "attention_memory": {"enabled": False, "total_events": 0, "recent_events": []},
        "symbol_weights": {"top_symbols": [], "top_blocks": []},
        "transformer_attention": {"enabled": False, "available": False, "config": {}},
        "in_context_learning": {"enabled": False, "available": False, "demo_statistics": {}},
        "timestamp": time.time(),
        "has_data": False
    }


def render_attention_monitor_page(ctx):
    """渲染注意力监控页面"""
    from pywebio.output import put_html, put_text, use_scope
    from .awakening import render_awakening_status

    data = get_attention_monitor_data()
    put_html("<h2>🧘 觉醒系统</h2>")
    put_text(f"Last updated: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(data['timestamp']))}")

    with use_scope("monitor_grid", clear=True):
        put_html(render_awakening_status())


def get_hotspot_snapshots(hours: int = 24, limit: int = 50) -> Dict[str, Any]:
    """获取热点系统历史快照"""
    result = {"snapshots": [], "stats": {"total": 0, "time_range": {"start": None, "end": None}, "symbol_appearance": {}}, "has_data": False}

    try:
        from deva.naja.state.snapshot import get_snapshot_manager
        sm = get_snapshot_manager()
        records = sm.get_hotspot_snapshots(hours=hours, limit=limit)

        if not records:
            return result

        result["has_data"] = True
        result["stats"]["total"] = len(records)

        for record in records:
            if isinstance(record, dict):
                ts = record.get("timestamp", 0)
                symbols = [s.get("symbol") for s in record.get("top_symbols", []) if isinstance(s, dict)]
                for sym in symbols:
                    if sym:
                        result["stats"]["symbol_appearance"][sym] = result["stats"]["symbol_appearance"].get(sym, 0) + 1

                result["snapshots"].append({
                    "timestamp": ts,
                    "time_str": time.strftime("%H:%M:%S", time.localtime(ts)) if ts else "N/A",
                    "date_str": time.strftime("%Y-%m-%d", time.localtime(ts)) if ts else "N/A",
                    "top_symbols": symbols[:5],
                    "block_weights": record.get("block_weights", {}),
                    "active_blocks": record.get("active_blocks", []),
                    "market_context": record.get("market_context", {}),
                    "total_hotspot_count": record.get("total_hotspot_count", 0)
                })

        if result["snapshots"]:
            timestamps = [s["timestamp"] for s in result["snapshots"] if s["timestamp"]]
            if timestamps:
                result["stats"]["time_range"]["start"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(min(timestamps)))
                result["stats"]["time_range"]["end"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(max(timestamps)))
    except Exception as e:
        result["error"] = str(e)

    return result


def get_classic_moments(hours: int = 24, limit: int = 10) -> Dict[str, Any]:
    """获取经典时刻"""
    result = {
        "moments": [],
        "classification": {"high_hotspot": [], "market_alert": [], "regime_change": [], "low_activity": []},
        "has_data": False
    }

    snapshots = get_hotspot_snapshots(hours=hours, limit=limit * 3)
    if not snapshots.get("has_data"):
        return result

    result["has_data"] = True

    for snap in snapshots.get("snapshots", []):
        moment_type = []
        reason = []

        if snap.get("total_hotspot_count", 0) > 100:
            moment_type.append("high_hotspot")
            reason.append(f"高热度事件: {snap['total_hotspot_count']}次")

        context = snap.get("market_context", {})
        if context.get("us_phase") in ["pre_market", "after_hours"]:
            moment_type.append("market_alert")
            reason.append(f"盘后/盘前阶段: {context.get('us_phase')}")

        blocks = snap.get("active_blocks", [])
        if len(blocks) > 5:
            moment_type.append("regime_change")
            reason.append(f"多题材活跃: {len(blocks)}个")

        if snap.get("total_hotspot_count", 0) < 5:
            moment_type.append("low_activity")
            reason.append("低活跃期")

        if moment_type:
            result["moments"].append({
                "timestamp": snap["timestamp"],
                "time_str": snap["time_str"],
                "date_str": snap["date_str"],
                "type": moment_type,
                "reason": reason
            })

    return result


__all__ = ["get_attention_monitor_data", "render_attention_monitor_page", "get_hotspot_snapshots", "get_classic_moments"]
