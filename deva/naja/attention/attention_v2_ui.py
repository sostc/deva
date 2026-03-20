"""
智能增强功能 UI 渲染模块

在现有 attention UI 基础上展示智能增强新增的：
- Predictive Attention (预测注意力)
- Attention Feedback Loop (反馈循环)
- Attention Budget System (预算系统)
- Attention Propagation (扩散传播)
- Strategy Learning (策略学习)
"""

from typing import Dict, List, Any, Optional
from datetime import datetime


def _get_intelligence_system():
    """获取智能增强系统"""
    try:
        from deva.naja.attention_integration import get_attention_integration
        integration = get_attention_integration()
        if hasattr(integration, 'intelligence_system') and integration.intelligence_system:
            return integration.intelligence_system
        return None
    except Exception:
        return None


def _render_predictive_attention_panel() -> str:
    """渲染预测注意力面板"""
    intelligence_system = _get_intelligence_system()
    if not intelligence_system or not hasattr(intelligence_system, 'predictive_engine'):
        return """
        <div style="
            background: #f0f9ff;
            border: 1px solid #e2e8f0;
            border-radius: 12px;
            padding: 16px;
            margin-top: 16px;
        ">
            <div style="font-weight: 600; margin-bottom: 8px; color: #64748b;">
                🔮 预测注意力
                <span style="font-size: 11px; color: #94a3b8; font-weight: normal; margin-left: 8px;">未启用</span>
            </div>
            <div style="color: #94a3b8; font-size: 12px;">预测注意力引擎未初始化</div>
        </div>
        """

    try:
        top_predictions = intelligence_system.predictive_engine.get_predictions_top_k(k=5)
        if not top_predictions:
            return """
            <div style="
                background: #f0f9ff;
                border: 1px solid #e2e8f0;
                border-radius: 12px;
                padding: 16px;
                margin-top: 16px;
            ">
                <div style="font-weight: 600; margin-bottom: 8px;">🔮 预测注意力</div>
                <div style="color: #64748b; font-size: 12px;">暂无预测数据</div>
            </div>
            """

        items_html = ""
        for symbol, (pred_score, curr_att) in list(top_predictions.items())[:5]:
            bar_width = pred_score * 100
            items_html += f"""
            <div style="margin-bottom: 8px;">
                <div style="display: flex; justify-content: space-between; font-size: 12px;">
                    <span style="font-weight: 600;">{symbol}</span>
                    <span style="color: #64748b;">预测: {pred_score:.3f} | 当前: {curr_att:.3f}</span>
                </div>
                <div style="background: #e2e8f0; height: 6px; border-radius: 3px; margin-top: 4px;">
                    <div style="background: #0ea5e9; height: 6px; border-radius: 3px; width: {bar_width}%;"></div>
                </div>
            </div>
            """

        return f"""
        <div style="
            background: #f0f9ff;
            border: 1px solid #e2e8f0;
            border-radius: 12px;
            padding: 16px;
            margin-top: 16px;
        ">
            <div style="font-weight: 600; margin-bottom: 12px;">
                🔮 预测注意力 Top5
            </div>
            {items_html}
        </div>
        """
    except Exception as e:
        return f"""
        <div style="
            background: #f0f9ff;
            border: 1px solid #e2e8f0;
            border-radius: 12px;
            padding: 16px;
            margin-top: 16px;
        ">
            <div style="font-weight: 600; margin-bottom: 8px;">🔮 预测注意力</div>
            <div style="color: #ef4444; font-size: 12px;">Error: {str(e)}</div>
        </div>
        """


def _render_feedback_loop_panel() -> str:
    """渲染反馈循环面板"""
    intelligence_system = _get_intelligence_system()
    if not intelligence_system or not hasattr(intelligence_system, 'feedback_loop'):
        return """
        <div style="
            background: #fef3c7;
            border: 1px solid #fcd34d;
            border-radius: 12px;
            padding: 16px;
            margin-top: 16px;
        ">
            <div style="font-weight: 600; margin-bottom: 8px; color: #64748b;">
                🔄 注意力反馈
                <span style="font-size: 11px; color: #94a3b8; font-weight: normal; margin-left: 8px;">未启用</span>
            </div>
            <div style="color: #94a3b8; font-size: 12px;">反馈循环系统未初始化</div>
        </div>
        """

    try:
        summary = intelligence_system.feedback_loop.get_summary()

        effective = summary.get('effective_patterns', [])
        ineffective = summary.get('ineffective_patterns', [])

        effective_html = "无" if not effective else ", ".join(effective[:3])
        ineffective_html = "无" if not ineffective else ", ".join(ineffective[:3])

        return f"""
        <div style="
            background: #fef3c7;
            border: 1px solid #fcd34d;
            border-radius: 12px;
            padding: 16px;
            margin-top: 16px;
        ">
            <div style="font-weight: 600; margin-bottom: 12px;">🔄 注意力反馈</div>
            <div style="font-size: 12px; margin-bottom: 8px;">
                <div style="color: #16a34a;">✅ 有效模式: {effective_html}</div>
                <div style="color: #dc2626; margin-top: 4px;">❌ 无效模式: {ineffective_html}</div>
            </div>
            <div style="font-size: 11px; color: #64748b;">
                总反馈数: {summary.get('total_feedback', 0)} |
                最近24h: {summary.get('recent_24h', 0)}
            </div>
        </div>
        """
    except Exception as e:
        return f"""
        <div style="
            background: #fef3c7;
            border: 1px solid #fcd34d;
            border-radius: 12px;
            padding: 16px;
            margin-top: 16px;
        ">
            <div style="font-weight: 600; margin-bottom: 8px;">🔄 注意力反馈</div>
            <div style="color: #ef4444; font-size: 12px;">Error: {str(e)}</div>
        </div>
        """


def _render_budget_panel() -> str:
    """渲染预算系统面板"""
    intelligence_system = _get_intelligence_system()
    if not intelligence_system or not hasattr(intelligence_system, 'budget_system'):
        return """
        <div style="
            background: #f0fdf4;
            border: 1px solid #bbf7d0;
            border-radius: 12px;
            padding: 16px;
            margin-top: 16px;
        ">
            <div style="font-weight: 600; margin-bottom: 8px; color: #64748b;">
                💰 注意力预算
                <span style="font-size: 11px; color: #94a3b8; font-weight: normal; margin-left: 8px;">未启用</span>
            </div>
            <div style="color: #94a3b8; font-size: 12px;">预算系统未初始化</div>
        </div>
        """

    try:
        summary = intelligence_system.get_summary()
        budget_summary = summary.get('budget_summary', {})

        utilization = budget_summary.get('budget_utilization', 0)
        tier1_count = len(budget_summary.get('tier1_symbols', []))
        tier2_count = len(budget_summary.get('tier2_symbols', []))
        tier3_count = len(budget_summary.get('tier3_symbols', []))

        return f"""
        <div style="
            background: #f0fdf4;
            border: 1px solid #bbf7d0;
            border-radius: 12px;
            padding: 16px;
            margin-top: 16px;
        ">
            <div style="font-weight: 600; margin-bottom: 12px;">💰 注意力预算</div>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; font-size: 12px;">
                <div>
                    <div style="color: #64748b;">预算使用</div>
                    <div style="font-weight: 600; color: #16a34a;">{utilization:.1%}</div>
                </div>
                <div>
                    <div style="color: #64748b;">高频数量</div>
                    <div style="font-weight: 600;">{tier1_count}</div>
                </div>
                <div>
                    <div style="color: #64748b;">中频数量</div>
                    <div style="font-weight: 600;">{tier2_count}</div>
                </div>
                <div>
                    <div style="color: #64748b;">低频数量</div>
                    <div style="font-weight: 600;">{tier3_count}</div>
                </div>
            </div>
        </div>
        """
    except Exception as e:
        return f"""
        <div style="
            background: #f0fdf4;
            border: 1px solid #bbf7d0;
            border-radius: 12px;
            padding: 16px;
            margin-top: 16px;
        ">
            <div style="font-weight: 600; margin-bottom: 8px;">💰 注意力预算</div>
            <div style="color: #ef4444; font-size: 12px;">Error: {str(e)}</div>
        </div>
        """


def _render_propagation_panel() -> str:
    """渲染注意力扩散面板"""
    intelligence_system = _get_intelligence_system()
    if not intelligence_system or not hasattr(intelligence_system, 'propagation'):
        return """
        <div style="
            background: #fae8ff;
            border: 1px solid #f5d0fe;
            border-radius: 12px;
            padding: 16px;
            margin-top: 16px;
        ">
            <div style="font-weight: 600; margin-bottom: 8px; color: #64748b;">
                🌊 注意力扩散
                <span style="font-size: 11px; color: #94a3b8; font-weight: normal; margin-left: 8px;">未启用</span>
            </div>
            <div style="color: #94a3b8; font-size: 12px;">扩散系统未初始化</div>
        </div>
        """

    try:
        summary = intelligence_system.propagation.get_propagation_summary()
        relations = intelligence_system.propagation.get_all_relations()[:5]

        relations_html = ""
        for rel in relations:
            from_sector = rel.get('from_sector', 'N/A')
            to_sector = rel.get('to_sector', 'N/A')
            strength = rel.get('strength', 0)
            relations_html += f"<div>{from_sector} → {to_sector} ({strength:.2f})</div>"

        return f"""
        <div style="
            background: #fae8ff;
            border: 1px solid #f5d0fe;
            border-radius: 12px;
            padding: 16px;
            margin-top: 16px;
        ">
            <div style="font-weight: 600; margin-bottom: 12px;">🌊 注意力扩散</div>
            <div style="font-size: 12px;">
                <div style="color: #64748b; margin-bottom: 4px;">板块关联 Top5:</div>
                <div style="color: #1e293b;">{relations_html or '暂无数据'}</div>
            </div>
        </div>
        """
    except Exception as e:
        return f"""
        <div style="
            background: #fae8ff;
            border: 1px solid #f5d0fe;
            border-radius: 12px;
            padding: 16px;
            margin-top: 16px;
        ">
            <div style="font-weight: 600; margin-bottom: 8px;">🌊 注意力扩散</div>
            <div style="color: #ef4444; font-size: 12px;">Error: {str(e)}</div>
        </div>
        """


def _render_strategy_learning_panel() -> str:
    """渲染策略学习面板"""
    intelligence_system = _get_intelligence_system()
    if not intelligence_system or not hasattr(intelligence_system, 'strategy_learning'):
        return """
        <div style="
            background: #fdf4ff;
            border: 1px solid #e9d5ff;
            border-radius: 12px;
            padding: 16px;
            margin-top: 16px;
        ">
            <div style="font-weight: 600; margin-bottom: 8px; color: #64748b;">
                📚 策略学习
                <span style="font-size: 11px; color: #94a3b8; font-weight: normal; margin-left: 8px;">未启用</span>
            </div>
            <div style="color: #94a3b8; font-size: 12px;">策略学习系统未初始化</div>
        </div>
        """

    try:
        summary = intelligence_system.strategy_learning.get_selection_summary()
        learning_stats = intelligence_system.strategy_learning.get_learning_stats()

        market_state = summary.get('market_state', 'unknown')
        selected_strategies = summary.get('selected_strategies', [])

        strategies_html = ", ".join(selected_strategies) if selected_strategies else "无"

        return f"""
        <div style="
            background: #fdf4ff;
            border: 1px solid #e9d5ff;
            border-radius: 12px;
            padding: 16px;
            margin-top: 16px;
        ">
            <div style="font-weight: 600; margin-bottom: 12px;">📚 策略学习</div>
            <div style="font-size: 12px;">
                <div style="margin-bottom: 8px;">
                    <span style="color: #64748b;">市场状态:</span>
                    <span style="font-weight: 600;">{market_state}</span>
                </div>
                <div style="margin-bottom: 8px;">
                    <span style="color: #64748b;">选中策略:</span>
                    <span>{strategies_html}</span>
                </div>
                <div>
                    <span style="color: #64748b;">学习次数:</span>
                    <span>{learning_stats.get('total_updates', 0)}</span>
                </div>
            </div>
        </div>
        """
    except Exception as e:
        return f"""
        <div style="
            background: #fdf4ff;
            border: 1px solid #e9d5ff;
            border-radius: 12px;
            padding: 16px;
            margin-top: 16px;
        ">
            <div style="font-weight: 600; margin-bottom: 8px;">📚 策略学习</div>
            <div style="color: #ef4444; font-size: 12px;">Error: {str(e)}</div>
        </div>
        """


def _render_intelligence_summary_panel() -> str:
    """渲染智能增强系统总览面板"""
    intelligence_system = _get_intelligence_system()
    if not intelligence_system:
        return """
        <div style="
            background: linear-gradient(135deg, #64748b22, #64748b11);
            border: 1px solid #e2e8f0;
            border-radius: 12px;
            padding: 16px;
            margin-top: 16px;
        ">
            <div style="font-weight: 600; margin-bottom: 8px;">
                🧠 智能增强系统
                <span style="font-size: 11px; color: #94a3b8; font-weight: normal; margin-left: 8px;">未启用</span>
            </div>
            <div style="color: #64748b; font-size: 12px;">
                智能增强系统未初始化。<br>
                可在配置中启用预测、反馈、预算等功能。
            </div>
        </div>
        """

    try:
        summary = intelligence_system.get_summary()
        enabled = summary.get('enabled_modules', {})

        enabled_modules = [k for k, v in enabled.items() if v]
        disabled_modules = [k for k, v in enabled.items() if not v]

        enabled_html = ", ".join(enabled_modules) if enabled_modules else "无"
        disabled_html = ", ".join(disabled_modules) if disabled_modules else "无"

        return f"""
        <div style="
            background: linear-gradient(135deg, #0ea5e922, #0ea5e911);
            border: 1px solid #0ea5e9;
            border-radius: 12px;
            padding: 16px;
            margin-top: 16px;
        ">
            <div style="font-weight: 600; margin-bottom: 8px;">
                🧠 智能增强系统
                <span style="font-size: 11px; color: #16a34a; font-weight: normal; margin-left: 8px;">已启用</span>
            </div>
            <div style="font-size: 12px; line-height: 1.8;">
                <div style="color: #16a34a;">✅ 已启用: {enabled_html}</div>
                <div style="color: #94a3b8;">⬜ 未启用: {disabled_html}</div>
            </div>
            <div style="margin-top: 12px; padding-top: 12px; border-top: 1px solid #e2e8f0;">
                <div style="font-size: 11px; color: #64748b;">
                    🧠 智能增强 = 预测变化 + 利用反馈 + 优化预算 + 扩散关联 + 学习策略
                </div>
                <div style="font-size: 11px; color: #64748b; margin-top: 4px;">
                    在基础注意力上增加预见性、自适应性和学习能力
                </div>
            </div>
        </div>
        """
    except Exception as e:
        return f"""
        <div style="
            background: linear-gradient(135deg, #64748b22, #64748b11);
            border: 1px solid #e2e8f0;
            border-radius: 12px;
            padding: 16px;
            margin-top: 16px;
        ">
            <div style="font-weight: 600; margin-bottom: 8px;">🧠 智能增强系统</div>
            <div style="color: #ef4444; font-size: 12px;">Error: {str(e)}</div>
        </div>
        """


def render_intelligence_panels() -> str:
    """渲染所有智能增强面板（组合使用）"""
    return f"""
    <div style="display: flex; flex-direction: column; gap: 16px;">
        {_render_intelligence_summary_panel()}
        {_render_predictive_attention_panel()}
        {_render_feedback_loop_panel()}
        {_render_budget_panel()}
        {_render_propagation_panel()}
        {_render_strategy_learning_panel()}
    </div>
    """


def render_v2_panels() -> str:
    """渲染所有智能增强面板（兼容旧名称）"""
    return render_intelligence_panels()
