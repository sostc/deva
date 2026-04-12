"""Awakening Status - 觉醒系统状态展示

基于重构后的 ManasEngine 和末那识架构：
- 4引擎+1观照：TimingEngine, RegimeEngine, ConfidenceEngine, RiskEngine + MetaManas
- ManasOutput 包含完整决策信息
- QKV 注意力能力：事件编码、多维评分、策略学习

使用方式：
    from deva.naja.attention.ui import render_awakening_status
    html = render_awakening_status()
"""

from typing import Dict, Any


def render_awakening_status() -> str:
    """渲染觉醒系统完整状态"""
    manas_state = _get_manas_state()
    qkv_state = _get_qkv_state()

    overall_level = manas_state.get("overall_level", 0)
    overall_percent = int(overall_level * 100)
    overall_color = _get_level_color(overall_level)

    return """<div style="
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        border-radius: 14px;
        padding: 20px;
        margin: 10px 0;
        border: 1px solid #334155;
        box-shadow: 0 4px 20px rgba(0,0,0,0.2);
    ">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
            <div style="display: flex; align-items: center; gap: 10px;">
                <span style="font-size: 24px;">🧘</span>
                <div>
                    <div style="font-size: 16px; font-weight: 700; color: #f1f5f9;">觉醒系统</div>
                    <div style="font-size: 11px; color: #0ea5e9; margin-top: 2px;">明心见性，知行合一</div>
                </div>
            </div>
            <div style="text-align: center;">
                <div style="
                    background: """ + overall_color + """22;
                    border: 2px solid """ + overall_color + """;
                    border-radius: 12px;
                    padding: 8px 16px;
                ">
                    <div style="font-size: 11px; color: #94a3b8; margin-bottom: 4px;">觉醒进度</div>
                    <div style="font-size: 20px; font-weight: 700; color: """ + overall_color + """;">""" + str(overall_percent) + """%</div>
                </div>
            </div>
        </div>

        <div style="
            background: #0f172a;
            border-radius: 8px;
            height: 8px;
            margin-bottom: 20px;
            overflow: hidden;
        ">
            <div style="
                background: linear-gradient(90deg, """ + overall_color + """ 0%, #00d4ff 100%);
                height: 100%;
                width: """ + str(overall_percent) + """%;
                border-radius: 8px;
                transition: width 0.5s ease;
            "></div>
        </div>

        """ + _render_manas_core(manas_state) + """
        """ + _render_qkv_module(qkv_state) + """
    </div>
    """


def _get_manas_state() -> Dict[str, Any]:
    """获取末那识引擎完整状态"""
    try:
        from deva.naja.attention.kernel import get_manas_manager
        manager = get_manas_manager()
        if manager is None:
            return _get_default_state()

        if not manager.is_enabled():
            return _get_default_state()

        output = manager.compute()
        if output is None:
            return _get_default_state()

        awakened_level_str = output.get("awakening_level", "dormant")

        if awakened_level_str == "dormant":
            awakened_level_str = _compute_awakening_from_manas(output)

        awakening_map = {"dormant": 0.0, "awakening": 0.4, "illuminated": 0.7, "enlightened": 0.95}
        overall_level = awakening_map.get(awakened_level_str, 0.0)

        return {
            "overall_level": overall_level,
            "awakening_level": awakened_level_str,
            "manas_score": output.get("manas_score", 0.5),
            "timing_score": output.get("timing_score", 0.5),
            "regime_score": output.get("regime_score", 0.0),
            "confidence_score": output.get("confidence_score", 0.5),
            "risk_temperature": output.get("risk_temperature", 0.5),
            "should_act": output.get("should_act", False),
            "action_type": output.get("action_type", "hold"),
            "action_gate_reason": output.get("action_gate_reason", ""),
            "harmony_state": output.get("harmony_state", "neutral"),
            "harmony_strength": output.get("harmony_strength", 0.5),
            "bias_state": output.get("bias_state", "neutral"),
            "bias_correction": output.get("bias_correction", 1.0),
            "alpha": output.get("alpha", 1.0),
            "attention_focus": output.get("attention_focus", 1.0),
            "supply_chain_risk_level": output.get("supply_chain_risk_level", "LOW"),
            "portfolio_loss_pct": output.get("portfolio_loss_pct", 0.0),
        }
    except Exception as e:
        return _get_default_state(error=str(e))


def _get_qkv_state() -> Dict[str, Any]:
    """获取 QKV 系统完整状态"""
    try:
        from deva.naja.attention.orchestration.trading_center import get_trading_center
        tc = get_trading_center()
        os = tc.get_attention_os()
        kernel = os.kernel

        event_encoder_state = _get_event_encoder_state(kernel)
        multi_scorer_state = _get_multi_scorer_state(kernel)
        attention_memory_state = _get_attention_memory_state(kernel)
        awakened_memory_state = _get_awakened_memory_state()

        return {
            "event_encoder": event_encoder_state,
            "multi_scorer": multi_scorer_state,
            "attention_memory": attention_memory_state,
            "awakened_memory": awakened_memory_state,
            "has_data": True
        }
    except Exception:
        return {
            "event_encoder": {"total_encoded": 0, "key_features": [], "value_features": []},
            "multi_scorer": {"heads_count": 0, "fusion_alpha": 0.0},
            "attention_memory": {"total": 0, "level_distribution": {"high": 0, "medium": 0, "low": 0}, "avg_score": 0.0},
            "awakened_memory": {"total_patterns": 0, "market_stats": {}},
            "has_data": False
        }


def _get_event_encoder_state(kernel) -> Dict[str, Any]:
    """获取事件编码器状态"""
    encoder_state = {
        "total_encoded": 0,
        "key_features": ["price", "sentiment", "volume", "alpha"],
        "value_features": ["alpha", "risk", "confidence"]
    }
    return encoder_state


def _get_attention_memory_state(kernel) -> Dict[str, Any]:
    """获取注意力记忆系统状态

    AttentionMemory 已删除，记忆功能由 Cognition 系统提供
    """
    memory_state = {
        "total": 0,
        "level_distribution": {"high": 0, "medium": 0, "low": 0},
        "avg_score": 0.0,
        "note": "Memory moved to Cognition system"
    }
    return memory_state


def _get_awakened_memory_state() -> Dict[str, Any]:
    """获取觉醒系统记忆状态"""
    awakened_state = {
        "total_patterns": 0,
        "market_stats": {},
        "archive_stats": {}
    }
    try:
        from deva.naja.knowledge.alaya.awakened_alaya import AwakenedAlaya
        alaya = AwakenedAlaya()

        if hasattr(alaya, 'cross_market_memory') and alaya.cross_market_memory:
            cross_stats = alaya.cross_market_memory.get_stats()
            awakened_state["total_patterns"] = cross_stats.get("total_patterns", 0)
            awakened_state["market_stats"] = cross_stats.get("market_stats", {})

        if hasattr(alaya, 'pattern_archive') and alaya.pattern_archive:
            archive_stats = alaya.pattern_archive.get_archive_stats()
            awakened_state["archive_stats"] = archive_stats
    except Exception:
        pass
    return awakened_state


def _get_multi_scorer_state(kernel) -> Dict[str, Any]:
    """获取多维评分器状态"""
    scorer_state = {
        "heads_count": 0,
        "fusion_alpha": 0.0
    }
    try:
        if hasattr(kernel, 'multi_head') and kernel.multi_head:
            scorer_state["heads_count"] = len(kernel.multi_head.heads)
            result = kernel.multi_head.compute(kernel.get_harmony(), [])
            scorer_state["fusion_alpha"] = result.get("alpha", 0)
    except Exception:
        pass
    return scorer_state


def _compute_awakening_from_manas(output: Dict[str, Any]) -> str:
    """根据 Manas 输出数据计算觉醒等级"""
    manas_score = output.get("manas_score", 0.5)
    timing_score = output.get("timing_score", 0.5)
    confidence_score = output.get("confidence_score", 0.5)
    harmony_strength = output.get("harmony_strength", 0.5)
    should_act = output.get("should_act", False)

    awakening_score = 0.0
    awakening_score += manas_score * 0.4
    awakening_score += timing_score * 0.2

    if confidence_score > 0.3:
        awakening_score += 0.25
    elif confidence_score > 0.1:
        awakening_score += 0.1

    awakening_score += harmony_strength * 0.15

    if awakening_score >= 0.7 and should_act:
        return "enlightened"
    elif awakening_score >= 0.5:
        return "illuminated"
    elif awakening_score >= 0.25 or (confidence_score > 0.3 and timing_score > 0.4):
        return "awakening"
    else:
        return "dormant"


def _get_default_state(error: str = None) -> Dict[str, Any]:
    """获取默认状态"""
    return {
        "overall_level": 0.0,
        "awakening_level": "dormant",
        "manas_score": 0.5,
        "timing_score": 0.5,
        "regime_score": 0.0,
        "confidence_score": 0.5,
        "risk_temperature": 0.5,
        "should_act": False,
        "action_type": "hold",
        "harmony_state": "neutral",
        "harmony_strength": 0.5,
        "error": error,
    }


def _get_level_color(level: float) -> str:
    """获取等级颜色"""
    if level >= 0.8:
        return "#22c55e"
    elif level >= 0.5:
        return "#0ea5e9"
    elif level >= 0.2:
        return "#f59e0b"
    else:
        return "#64748b"


def _render_manas_core(state: Dict[str, Any]) -> str:
    """渲染末那识核心决策状态"""
    manas_score = state.get("manas_score", 0.5)
    timing = state.get("timing_score", 0.5)
    regime = state.get("regime_score", 0.0)
    confidence = state.get("confidence_score", 0.5)
    risk_temp = state.get("risk_temperature", 0.5)
    should_act = state.get("should_act", False)
    action_type = state.get("action_type", "hold")
    harmony_state = state.get("harmony_state", "neutral")
    harmony_strength = state.get("harmony_strength", 0.5)
    awakening_level = state.get("awakening_level", "dormant")
    bias_state = state.get("bias_state", "neutral")
    alpha = state.get("alpha", 1.0)
    supply_risk = state.get("supply_chain_risk_level", "LOW")

    status_color = "#22c55e" if should_act else "#f59e0b"
    status_text = f"行动:{action_type}" if should_act else "观望"

    awakening_text = {
        "dormant": "休眠",
        "awakening": "觉醒中",
        "illuminated": "照明",
        "enlightened": "觉悟",
    }.get(awakening_level, awakening_level)

    harmony_text = {
        "bullish": "多头",
        "bearish": "空头",
        "neutral": "中性",
    }.get(harmony_state, harmony_state)

    bias_text = {
        "bullish": "偏多",
        "bearish": "偏空",
        "neutral": "中性",
    }.get(bias_state, bias_state)

    return """<div style="margin-bottom: 16px;">
        <div style="
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
            padding-bottom: 8px;
            border-bottom: 1px solid #334155;
        ">
            <div style="display: flex; align-items: center; gap: 8px;">
                <span style="font-size: 16px;">🧠</span>
                <span style="font-size: 13px; font-weight: 600; color: #f1f5f9;">末那识引擎</span>
                <span style="font-size: 10px; color: #64748b; background: #1e293b; padding: 2px 6px; border-radius: 4px;">4引擎+1观照</span>
            </div>
            <div style="
                background: """ + status_color + """22;
                border: 1px solid """ + status_color + """;
                border-radius: 8px;
                padding: 3px 10px;
                font-size: 11px;
                color: """ + status_color + """;
            ">
                """ + status_text + """
            </div>
        </div>

        <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-bottom: 12px;">
            <div style="background: #0f172a; border-radius: 8px; padding: 10px; text-align: center;">
                <div style="font-size: 10px; color: #64748b; margin-bottom: 4px;">时机</div>
                <div style="font-size: 16px; font-weight: 600; color: #0ea5e9;">""" + f"{timing:.2f}" + """</div>
            </div>
            <div style="background: #0f172a; border-radius: 8px; padding: 10px; text-align: center;">
                <div style="font-size: 10px; color: #64748b; margin-bottom: 4px;">趋势</div>
                <div style="font-size: 16px; font-weight: 600; color: #8b5cf6;">""" + f"{regime:+.2f}" + """</div>
            </div>
            <div style="background: #0f172a; border-radius: 8px; padding: 10px; text-align: center;">
                <div style="font-size: 10px; color: #64748b; margin-bottom: 4px;">自信度</div>
                <div style="font-size: 16px; font-weight: 600; color: #22c55e;">""" + f"{confidence:.2f}" + """</div>
            </div>
            <div style="background: #0f172a; border-radius: 8px; padding: 10px; text-align: center;">
                <div style="font-size: 10px; color: #64748b; margin-bottom: 4px;">风险温度</div>
                <div style="font-size: 16px; font-weight: 600; color: #f59e0b;">""" + f"{risk_temp:.2f}" + """</div>
            </div>
        </div>

        <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 12px;">
            <div style="background: #0f172a; border-radius: 8px; padding: 10px; text-align: center;">
                <div style="font-size: 10px; color: #64748b; margin-bottom: 4px;">和谐度</div>
                <div style="font-size: 14px; font-weight: 600; color: #06b6d4;">""" + harmony_text + """ """ + f"{harmony_strength:.2f}" + """</div>
            </div>
            <div style="background: #0f172a; border-radius: 8px; padding: 10px; text-align: center;">
                <div style="font-size: 10px; color: #64748b; margin-bottom: 4px;">偏见修正</div>
                <div style="font-size: 14px; font-weight: 600; color: #ec4899;">""" + bias_text + """ """ + f"{alpha:.2f}" + """</div>
            </div>
            <div style="background: #0f172a; border-radius: 8px; padding: 10px; text-align: center;">
                <div style="font-size: 10px; color: #64748b; margin-bottom: 4px;">觉醒</div>
                <div style="font-size: 14px; font-weight: 600; color: #a855f7;">""" + awakening_text + """</div>
            </div>
        </div>

        <div style="background: #0f172a; border-radius: 8px; padding: 12px; text-align: center;">
            <div style="font-size: 10px; color: #64748b; margin-bottom: 6px;">末那识综合分数</div>
            <div style="font-size: 28px; font-weight: 700; color: #22c55e;">""" + f"{manas_score:.3f}" + """</div>
            <div style="font-size: 10px; color: #64748b; margin-top: 4px;">供应链风险: """ + supply_risk + """</div>
        </div>

        <div style="margin-top: 12px; padding: 10px; background: #0f172a; border-radius: 8px; font-size: 11px; color: #94a3b8;">
            <div style="font-weight: 600; color: #f1f5f9; margin-bottom: 6px;">💡 觉醒程度说明</div>
            <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 4px;">
                <div><span style="color: #64748b;">💤 休眠</span> - 信心不足，时机未到</div>
                <div><span style="color: #22c55e;">🌱 觉醒</span> - 信心回升，开始感知机会</div>
                <div><span style="color: #0ea5e9;">💡 照明</span> - 信心充足，策略适配市场</div>
                <div><span style="color: #a855f7;">🌟 觉悟</span> - 完全觉醒，高确信行动</div>
            </div>
        </div>
    </div>
    """


def _render_qkv_module(qkv_state: Dict[str, Any]) -> str:
    """渲染 QKV 注意力能力模块"""
    if not qkv_state:
        return ""

    event_encoder = qkv_state.get("event_encoder", {})
    multi_scorer = qkv_state.get("multi_scorer", {})
    attention_memory = qkv_state.get("attention_memory", {})
    awakened_memory = qkv_state.get("awakened_memory", {})

    total_encoded = event_encoder.get("total_encoded", 0)
    key_features = event_encoder.get("key_features", [])
    fusion_alpha = multi_scorer.get("fusion_alpha", 0.0)
    heads_count = multi_scorer.get("heads_count", 0)

    mem_total = attention_memory.get("total", 0)
    level_dist = attention_memory.get("level_distribution", {"high": 0, "medium": 0, "low": 0})
    avg_score = attention_memory.get("avg_score", 0.0)

    patterns_total = awakened_memory.get("total_patterns", 0)
    archive_stats = awakened_memory.get("archive_stats", {})

    pattern_types = list(archive_stats.keys())[:3] if archive_stats else []
    patterns_str = ", ".join(pattern_types) if pattern_types else "暂无归档"

    features_str = ", ".join(key_features[:4]) if key_features else ""

    return """<div style="margin-top: 12px;">
        <div style="
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
            padding-bottom: 8px;
            border-bottom: 1px solid #334155;
        ">
            <div style="display: flex; align-items: center; gap: 8px;">
                <span style="font-size: 16px;">⚡</span>
                <span style="font-size: 13px; font-weight: 600; color: #f1f5f9;">注意力能力</span>
                <span style="font-size: 10px; color: #64748b; background: #1e293b; padding: 2px 6px; border-radius: 4px;">QKV</span>
            </div>
        </div>

        <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-bottom: 8px;">
            <div style="background: #0f172a; border-radius: 8px; padding: 10px; text-align: center;">
                <div style="font-size: 10px; color: #64748b; margin-bottom: 4px;">📊 事件编码</div>
                <div style="font-size: 14px; font-weight: 600; color: #0ea5e9;">""" + str(total_encoded) + """ events</div>
                <div style="font-size: 9px; color: #64748b; margin-top: 2px;">""" + features_str + """</div>
            </div>
            <div style="background: #0f172a; border-radius: 8px; padding: 10px; text-align: center;">
                <div style="font-size: 10px; color: #64748b; margin-bottom: 4px;">🎯 多维评分</div>
                <div style="font-size: 14px; font-weight: 600; color: #22c55e;">""" + str(heads_count) + """ heads</div>
                <div style="font-size: 9px; color: #64748b; margin-top: 2px;">Alpha: """ + f"{fusion_alpha:.3f}" + """</div>
            </div>
            <div style="background: #0f172a; border-radius: 8px; padding: 10px; text-align: center;">
                <div style="font-size: 10px; color: #64748b; margin-bottom: 4px;">🧠 注意力记忆</div>
                <div style="font-size: 14px; font-weight: 600; color: #f59e0b;">""" + str(mem_total) + """ items</div>
                <div style="font-size: 9px; color: #64748b; margin-top: 2px;">H:""" + str(level_dist.get("high", 0)) + """ M:""" + str(level_dist.get("medium", 0)) + """ L:""" + str(level_dist.get("low", 0)) + """</div>
            </div>
            <div style="background: #0f172a; border-radius: 8px; padding: 10px; text-align: center;">
                <div style="font-size: 10px; color: #64748b; margin-bottom: 4px;">🌟 跨市场记忆</div>
                <div style="font-size: 14px; font-weight: 600; color: #a855f7;">""" + str(patterns_total) + """ patterns</div>
                <div style="font-size: 9px; color: #64748b; margin-top: 2px;">""" + patterns_str + """</div>
            </div>
        </div>
    </div>
    """
