"""Awakening Status - 觉醒系统状态展示

基于重构后的 ManasEngine 和末那识架构：
- 4引擎+1观照：TimingEngine, RegimeEngine, ConfidenceEngine, RiskEngine + MetaManas
- ManasOutput 包含完整决策信息
- QKV 注意力能力：事件编码、多维评分、策略学习

使用方式：
    from deva.naja.attention.ui_components.awakening import render_awakening_status
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
        from deva.naja.attention.trading_center import get_trading_center
        tc = get_trading_center()
        os = tc.get_attention_os()
        kernel = os.kernel

        event_encoder_state = _get_event_encoder_state(kernel)
        multi_scorer_state = _get_multi_scorer_state(kernel)
        strategy_learning_state = _get_strategy_learning_state(os)

        return {
            "event_encoder": event_encoder_state,
            "multi_scorer": multi_scorer_state,
            "strategy_learning": strategy_learning_state,
            "has_data": True
        }
    except Exception:
        return {
            "event_encoder": {"total_encoded": 0, "key_features": [], "value_features": []},
            "multi_scorer": {"heads_count": 0, "fusion_alpha": 0.0},
            "strategy_learning": {"available": False, "market_state": {}, "selected_strategies": []},
            "has_data": False
        }


def _get_event_encoder_state(kernel) -> Dict[str, Any]:
    """获取事件编码器状态"""
    encoder_state = {
        "total_encoded": 0,
        "key_features": ["price", "sentiment", "volume", "alpha"],
        "value_features": ["alpha", "risk", "confidence"]
    }
    try:
        if hasattr(kernel, 'memory') and kernel.memory:
            events = kernel.memory.store[-10:]
            encoder_state["total_encoded"] = len(events)
    except Exception:
        pass
    return encoder_state


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


def _get_strategy_learning_state(os) -> Dict[str, Any]:
    """获取策略学习状态"""
    learning_state = {
        "available": False,
        "market_state": {},
        "selected_strategies": []
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

            perf = sl.bandit.get_all_performance() if hasattr(sl, 'bandit') and sl.bandit else {}
            strategies = list(perf.keys())[:3]

            selected = sl.select_strategies(
                global_attention=0.5,
                sector_attention={},
                available_strategies=strategies,
                top_k=3
            ) if hasattr(sl, 'select_strategies') else None
            if selected:
                learning_state["selected_strategies"] = selected.selected_strategies
            else:
                learning_state["selected_strategies"] = strategies
    except Exception:
        pass
    return learning_state


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
    strategy_learning = qkv_state.get("strategy_learning", {})

    total_encoded = event_encoder.get("total_encoded", 0)
    key_features = event_encoder.get("key_features", [])
    fusion_alpha = multi_scorer.get("fusion_alpha", 0.0)
    heads_count = multi_scorer.get("heads_count", 0)

    market_state = strategy_learning.get("market_state", {})
    selected_strategies = strategy_learning.get("selected_strategies", [])
    state_name = market_state.get("name", "unknown") if market_state else "unknown"

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

        <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 8px;">
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
                <div style="font-size: 10px; color: #64748b; margin-bottom: 4px;">📈 策略学习</div>
                <div style="font-size: 14px; font-weight: 600; color: #8b5cf6;">""" + state_name + """</div>
                <div style="font-size: 9px; color: #64748b; margin-top: 2px;">""" + (", ".join(selected_strategies[:2]) if selected_strategies else "not initialized") + """</div>
            </div>
        </div>
    </div>
    """
