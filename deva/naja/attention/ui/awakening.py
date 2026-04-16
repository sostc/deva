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
    query_state = _get_query_state()

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

        """ + _render_system_overview(manas_state, query_state) + """
        """ + _render_manas_core(manas_state) + """
        """ + _render_qkv_module(qkv_state) + """
        """ + _render_current_state_narrative(manas_state, query_state) + """
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
        transformer_state = _get_transformer_state(kernel)
        in_context_state = _get_in_context_learning_state(kernel)

        return {
            "event_encoder": event_encoder_state,
            "multi_scorer": multi_scorer_state,
            "attention_memory": attention_memory_state,
            "awakened_memory": awakened_memory_state,
            "transformer": transformer_state,
            "in_context_learning": in_context_state,
            "has_data": True
        }
    except Exception:
        return {
            "event_encoder": {"total_encoded": 0, "key_features": [], "value_features": []},
            "multi_scorer": {"heads_count": 0, "fusion_alpha": 0.0},
            "attention_memory": {"total": 0, "level_distribution": {"high": 0, "medium": 0, "low": 0}, "avg_score": 0.0},
            "awakened_memory": {"total_patterns": 0, "market_stats": {}},
            "transformer": {"enabled": False, "available": False, "config": {}},
            "in_context_learning": {"enabled": False, "available": False, "demo_statistics": {}},
            "has_data": False
        }


def _get_transformer_state(kernel) -> Dict[str, Any]:
    """获取 Transformer 自注意力状态"""
    transformer_state = {
        "enabled": hasattr(kernel, '_enable_transformer') and kernel._enable_transformer,
        "available": hasattr(kernel, '_transformer_layer') and kernel._transformer_layer is not None,
        "feature_encoder": hasattr(kernel, '_feature_encoder') and kernel._feature_encoder is not None,
        "config": {
            "d_model": getattr(kernel._transformer_layer, 'd_model', 0) if hasattr(kernel, '_transformer_layer') else 0,
            "num_heads": getattr(kernel._transformer_layer, 'num_heads', 0) if hasattr(kernel, '_transformer_layer') else 0,
            "d_ff": getattr(kernel._transformer_layer.ffn, 'd_ff', 0) if hasattr(kernel, '_transformer_layer') and hasattr(kernel._transformer_layer, 'ffn') else 0
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
            learning_state["demo_statistics"] = kernel._in_context_learner.get_demo_statistics() if hasattr(kernel._in_context_learner, 'get_demo_statistics') else {}
    except Exception:
        pass
    
    return learning_state


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


# 全局QueryState实例缓存
_query_state_instance = None


def _get_query_state() -> Dict[str, Any]:
    """获取查询状态"""
    global _query_state_instance
    import logging
    log = logging.getLogger(__name__)
    
    try:
        from deva.naja.attention.kernel.state import QueryState
        from deva.naja.register import SR
        
        log.info(f"[AwakeningUI] 开始获取QueryState...")
        log.info(f"[AwakeningUI] 全局缓存实例: {_query_state_instance}")
        
        # 尝试从注册中心获取
        try:
            log.info(f"[AwakeningUI] 尝试从SR获取query_state...")
            qs = SR('query_state')
            if qs:
                summary = qs.get_summary()
                log.info(f"[AwakeningUI] 从SR获取QueryState成功: 市场状态={summary['market_regime']}, 关注焦点={summary['top_attention']}")
                return summary
        except KeyError as e:
            log.info(f"[AwakeningUI] SR中未找到query_state: {e}")
        except Exception as e:
            log.error(f"[AwakeningUI] 从SR获取query_state失败: {e}")
        
        # 如果注册中心没有，使用全局缓存的实例
        log.info(f"[AwakeningUI] 尝试使用全局缓存的实例...")
        if _query_state_instance is None:
            log.info(f"[AwakeningUI] 全局缓存实例为空，创建新实例")
            _query_state_instance = QueryState()
        
        summary = _query_state_instance.get_summary()
        log.info(f"[AwakeningUI] 从全局缓存获取QueryState: 市场状态={summary['market_regime']}, 关注焦点={summary['top_attention']}")
        return summary
    except Exception as e:
        log.error(f"[AwakeningUI] 获取QueryState失败: {e}", exc_info=True)
        return {
            "market_regime": "unknown",
            "risk_bias": 0.5,
            "attention_focus_count": 0,
            "top_attention": [],
            "strategy_count": 0,
            "portfolio_count": 0,
            "active_value_type": "trend",
            "value_weights": {
                "price_sensitivity": 0.5,
                "volume_sensitivity": 0.5,
                "sentiment_weight": 0.3,
                "liquidity_weight": 0.4,
                "fundamentals_weight": 0.3,
            }
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


def _render_system_overview(manas_state: Dict[str, Any], query_state: Dict[str, Any]) -> str:
    """渲染系统工作原理概览"""
    market_regime = query_state.get("market_regime", "unknown")
    top_attention = query_state.get("top_attention", [])
    attention_count = query_state.get("attention_focus_count", 0)
    
    regime_text = {
        "trend_up": "上涨趋势",
        "trend_down": "下跌趋势",
        "weak_trend_up": "弱上涨",
        "weak_trend_down": "弱下跌",
        "neutral": "震荡",
        "mixed": "混合",
        "unknown": "数据初始化中"
    }.get(market_regime, "数据初始化中")

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
                <span style="font-size: 16px;">🔍</span>
                <span style="font-size: 13px; font-weight: 600; color: #f1f5f9;">系统工作原理</span>
                <span style="font-size: 10px; color: #64748b; background: #1e293b; padding: 2px 6px; border-radius: 4px;">如何工作</span>
            </div>
        </div>

        <div style="display: grid; grid-template-columns: 1fr; gap: 12px;">
            <div style="background: #0f172a; border-radius: 8px; padding: 12px;">
                <div style="font-size: 12px; font-weight: 600; color: #f1f5f9; margin-bottom: 8px;">🔄 工作流程</div>
                <div style="display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 10px;">
                    <div style="flex: 1; min-width: 200px; background: #1e293b; border-radius: 6px; padding: 10px; text-align: center;">
                        <div style="font-size: 11px; color: #94a3b8; margin-bottom: 4px;">1. 数据采集</div>
                        <div style="font-size: 10px; color: #64748b;">市场数据、新闻情绪、资金流向</div>
                    </div>
                    <div style="flex: 1; min-width: 200px; background: #1e293b; border-radius: 6px; padding: 10px; text-align: center;">
                        <div style="font-size: 11px; color: #94a3b8; margin-bottom: 4px;">2. 事件编码</div>
                        <div style="font-size: 10px; color: #64748b;">QKV注意力机制，特征提取</div>
                    </div>
                    <div style="flex: 1; min-width: 200px; background: #1e293b; border-radius: 6px; padding: 10px; text-align: center;">
                        <div style="font-size: 11px; color: #94a3b8; margin-bottom: 4px;">3. 多维评分</div>
                        <div style="font-size: 10px; color: #64748b;">市场、新闻、资金、元认知</div>
                    </div>
                    <div style="flex: 1; min-width: 200px; background: #1e293b; border-radius: 6px; padding: 10px; text-align: center;">
                        <div style="font-size: 11px; color: #94a3b8; margin-bottom: 4px;">4. 决策生成</div>
                        <div style="font-size: 10px; color: #64748b;">时机、趋势、信心、风险评估</div>
                    </div>
                </div>
            </div>

            <div style="background: #0f172a; border-radius: 8px; padding: 12px;">
                <div style="font-size: 12px; font-weight: 600; color: #f1f5f9; margin-bottom: 8px;">📊 当前处理</div>
                <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px;">
                    <div style="background: #1e293b; border-radius: 6px; padding: 10px; text-align: center;">
                        <div style="font-size: 11px; color: #94a3b8; margin-bottom: 4px;">市场状态</div>
                        <div style="font-size: 14px; font-weight: 600; color: #0ea5e9;">""" + regime_text + """</div>
                    </div>
                    <div style="background: #1e293b; border-radius: 6px; padding: 10px; text-align: center;">
                        <div style="font-size: 11px; color: #94a3b8; margin-bottom: 4px;">关注焦点</div>
                        <div style="font-size: 14px; font-weight: 600; color: #22c55e;">""" + str(attention_count) + """ 个</div>
                    </div>
                    <div style="background: #1e293b; border-radius: 6px; padding: 10px; text-align: center;">
                        <div style="font-size: 11px; color: #94a3b8; margin-bottom: 4px;">核心关注</div>
                        <div style="font-size: 10px; color: #f1f5f9;">""" + (", ".join(top_attention[:3]) if top_attention else "暂无") + """</div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    """


def _render_current_state_narrative(manas_state: Dict[str, Any], query_state: Dict[str, Any]) -> str:
    """渲染当前状态的自然语言叙述"""
    awakening_level = manas_state.get("awakening_level", "dormant")
    should_act = manas_state.get("should_act", False)
    action_type = manas_state.get("action_type", "hold")
    harmony_state = manas_state.get("harmony_state", "neutral")
    market_regime = query_state.get("market_regime", "unknown")
    risk_bias = query_state.get("risk_bias", 0.5)
    top_attention = query_state.get("top_attention", [])
    
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
    
    regime_text = {
        "trend_up": "上涨趋势",
        "trend_down": "下跌趋势",
        "weak_trend_up": "弱上涨",
        "weak_trend_down": "弱下跌",
        "neutral": "震荡",
        "mixed": "混合",
        "unknown": "数据初始化中"
    }.get(market_regime, "数据初始化中")
    
    risk_text = "保守" if risk_bias < 0.4 else "中性" if risk_bias < 0.6 else "激进"
    
    narrative = "系统当前处于<span style='color: #a855f7; font-weight: 600;'>" + awakening_text + "</span>状态，"
    narrative += "市场整体呈现<span style='color: #0ea5e9; font-weight: 600;'>" + regime_text + "</span>格局。"
    narrative += "和谐度分析显示当前市场情绪<span style='color: #06b6d4; font-weight: 600;'>" + harmony_text + "</span>。"
    narrative += "系统风险偏好为<span style='color: #f59e0b; font-weight: 600;'>" + risk_text + "</span>。"
    narrative += "当前关注的核心方向包括：" + (", ".join(top_attention[:3]) if top_attention else "暂无明确焦点") + "。"
    
    if should_act:
        narrative += "系统建议<span style='color: #22c55e; font-weight: 600;'>" + action_type + "</span>操作。"
    else:
        narrative += "系统建议保持观望，等待更明确的信号。"
    
    return """<div style="margin-top: 16px;">
        <div style="
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
            padding-bottom: 8px;
            border-bottom: 1px solid #334155;
        ">
            <div style="display: flex; align-items: center; gap: 8px;">
                <span style="font-size: 16px;">💬</span>
                <span style="font-size: 13px; font-weight: 600; color: #f1f5f9;">系统状态解读</span>
                <span style="font-size: 10px; color: #64748b; background: #1e293b; padding: 2px 6px; border-radius: 4px;">自然语言</span>
            </div>
        </div>

        <div style="background: #0f172a; border-radius: 8px; padding: 16px;">
            <div style="font-size: 12px; line-height: 1.6; color: #f1f5f9;">
                """ + narrative + """
            </div>
        </div>
    </div>
    """


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
    transformer = qkv_state.get("transformer", {})
    in_context_learning = qkv_state.get("in_context_learning", {})

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

    transformer_enabled = transformer.get("enabled", False)
    transformer_available = transformer.get("available", False)
    transformer_config = transformer.get("config", {})
    d_model = transformer_config.get("d_model", 0)
    num_heads = transformer_config.get("num_heads", 0)

    in_context_enabled = in_context_learning.get("enabled", False)
    in_context_available = in_context_learning.get("available", False)
    demo_stats = in_context_learning.get("demo_statistics", {})
    total_demos = demo_stats.get("total_demos", 0)

    transformer_status_color = "#22c55e" if transformer_enabled and transformer_available else "#64748b"
    transformer_status_text = "已启用" if transformer_enabled and transformer_available else "未启用"
    
    in_context_status_color = "#22c55e" if in_context_enabled and in_context_available else "#64748b"
    in_context_status_text = "已启用" if in_context_enabled and in_context_available else "未启用"

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
                <span style="font-size: 10px; color: #64748b; background: #1e293b; padding: 2px 6px; border-radius: 4px;">QKV + Transformer</span>
            </div>
        </div>

        <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-bottom: 12px;">
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

        <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px;">
            <div style="background: #0f172a; border-radius: 8px; padding: 12px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                    <div style="display: flex; align-items: center; gap: 6px;">
                        <span style="font-size: 14px;">🔄</span>
                        <span style="font-size: 12px; font-weight: 600; color: #f1f5f9;">Transformer 自注意力</span>
                    </div>
                    <span style="font-size: 10px; padding: 2px 8px; border-radius: 4px; background: """ + transformer_status_color + """22; color: """ + transformer_status_color + """; border: 1px solid """ + transformer_status_color + """;">""" + transformer_status_text + """</span>
                </div>
                <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 6px;">
                    <div style="background: #1e293b; border-radius: 6px; padding: 8px; text-align: center;">
                        <div style="font-size: 9px; color: #64748b;">维度</div>
                        <div style="font-size: 13px; font-weight: 600; color: #0ea5e9;">""" + str(d_model) + """</div>
                    </div>
                    <div style="background: #1e293b; border-radius: 6px; padding: 8px; text-align: center;">
                        <div style="font-size: 9px; color: #64748b;">注意力头</div>
                        <div style="font-size: 13px; font-weight: 600; color: #22c55e;">""" + str(num_heads) + """</div>
                    </div>
                </div>
            </div>
            
            <div style="background: #0f172a; border-radius: 8px; padding: 12px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                    <div style="display: flex; align-items: center; gap: 6px;">
                        <span style="font-size: 14px;">🧩</span>
                        <span style="font-size: 12px; font-weight: 600; color: #f1f5f9;">上下文学习</span>
                    </div>
                    <span style="font-size: 10px; padding: 2px 8px; border-radius: 4px; background: """ + in_context_status_color + """22; color: """ + in_context_status_color + """; border: 1px solid """ + in_context_status_color + """;">""" + in_context_status_text + """</span>
                </div>
                <div style="background: #1e293b; border-radius: 6px; padding: 8px; text-align: center;">
                    <div style="font-size: 9px; color: #64748b;">历史示例</div>
                    <div style="font-size: 13px; font-weight: 600; color: #a855f7;">""" + str(total_demos) + """ demos</div>
                </div>
            </div>
        </div>
    </div>
    """
