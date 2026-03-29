"""Attention Kernel UI - 多头注意力可视化

展示 Attention Kernel 的核心能力：
1. QueryState - 全局注意力焦点
2. MultiHeadAttention - 多头归因（市场/新闻/资金/元）
3. AttentionMemory - 持久记忆与衰减
4. Bandit 反馈闭环
"""

from typing import Dict, List, Any
import time


def render_kernel_dashboard(kernel_state: Dict[str, Any]) -> str:
    """
    渲染 Attention Kernel 全局仪表盘

    Args:
        kernel_state: 包含 query_state, heads, memory, feedback 的 dict

    Returns:
        HTML 字符串
    """
    query_state = kernel_state.get("query_state", {})
    heads_output = kernel_state.get("heads_output", {})
    memory_items = kernel_state.get("memory_items", [])
    feedback_info = kernel_state.get("feedback_info", {})

    html = f"""
    <div class="kernel-dashboard" style="
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        border-radius: 12px;
        padding: 20px;
        margin: 10px 0;
        color: #fff;
    ">
        <h3 style="margin: 0 0 20px 0; color: #00d4ff;">
            🧠 Attention Kernel - 注意力中枢
        </h3>

        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
            {render_query_state_panel(query_state)}
            {render_multi_head_panel(heads_output)}
        </div>

        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-top: 20px;">
            {render_memory_panel(memory_items)}
            {render_feedback_panel(feedback_info)}
        </div>
    </div>
    """
    return html


def render_query_state_panel(query_state: Dict[str, Any]) -> str:
    """渲染 QueryState 面板"""
    strategy_state = query_state.get("strategy_state", {})
    portfolio_state = query_state.get("portfolio_state", {})
    market_regime = query_state.get("market_regime", {})
    attention_focus = query_state.get("attention_focus", {})
    risk_bias = query_state.get("risk_bias", 0.5)
    macro_liquidity_signal = query_state.get("macro_liquidity_signal", 0.5)

    regime_type = market_regime.get("type", "unknown") if isinstance(market_regime, dict) else "unknown"
    regime_colors = {
        "trend": "#4ade80",
        "reversal": "#f87171",
        "volatile": "#fbbf24",
        "neutral": "#94a3b8"
    }
    regime_color = regime_colors.get(regime_type, "#94a3b8")

    if macro_liquidity_signal < 0.4:
        liquidity_label = "紧张"
        liquidity_color = "#f87171"
    elif macro_liquidity_signal > 0.7:
        liquidity_label = "宽松"
        liquidity_color = "#4ade80"
    else:
        liquidity_label = "中性"
        liquidity_color = "#fbbf24"

    focus_items = ""
    for key, value in attention_focus.items():
        bar_width = min(value * 100, 100) if value else 0
        focus_items += f"""
        <div style="margin: 5px 0;">
            <span style="font-size: 12px;">{key}</span>
            <div style="background: #334155; border-radius: 4px; height: 8px; width: 100%;">
                <div style="background: #00d4ff; border-radius: 4px; height: 8px; width: {bar_width}%;"></div>
            </div>
            <span style="font-size: 11px; color: #94a3b8;">{value:.2f}</span>
        </div>
        """

    return f"""
    <div style="
        background: rgba(0,212,255,0.1);
        border: 1px solid rgba(0,212,255,0.3);
        border-radius: 8px;
        padding: 15px;
    ">
        <h4 style="margin: 0 0 15px 0; color: #00d4ff;">
            🔍 QueryState - 当前焦点
        </h4>

        <div style="margin: 10px 0;">
            <span style="color: #94a3b8;">市场状态:</span>
            <span style="color: {regime_color}; font-weight: bold;">{regime_type.upper()}</span>
        </div>

        <div style="margin: 10px 0;">
            <span style="color: #94a3b8;">风险偏好:</span>
            <div style="background: #334155; border-radius: 4px; height: 8px; width: 150px; display: inline-block; vertical-align: middle; margin-left: 10px;">
                <div style="background: #f87171; border-radius: 4px; height: 8px; width: {risk_bias * 100}%;"></div>
            </div>
            <span style="color: #f87171; margin-left: 5px;">{risk_bias:.2f}</span>
        </div>

        <div style="margin: 10px 0;">
            <span style="color: #94a3b8;">宏观流动性:</span>
            <div style="background: #334155; border-radius: 4px; height: 8px; width: 150px; display: inline-block; vertical-align: middle; margin-left: 10px;">
                <div style="background: {liquidity_color}; border-radius: 4px; height: 8px; width: {macro_liquidity_signal * 100}%;"></div>
            </div>
            <span style="color: {liquidity_color}; margin-left: 5px;">{macro_liquidity_signal:.2f} ({liquidity_label})</span>
        </div>

        <div style="margin: 15px 0;">
            <span style="color: #94a3b8;">注意力焦点:</span>
            {focus_items if focus_items else '<span style="color: #64748b;">暂无</span>'}
        </div>

        <div style="margin: 10px 0; font-size: 12px; color: #64748b;">
            策略数: {len(strategy_state)} | 持仓: {len(portfolio_state)}
        </div>
    </div>
    """


def render_multi_head_panel(heads_output: Dict[str, Any]) -> str:
    """渲染多头注意力面板"""
    head_colors = {
        "market": "#4ade80",
        "news": "#60a5fa",
        "flow": "#f472b6",
        "meta": "#fbbf24"
    }

    head_icons = {
        "market": "📈",
        "news": "📰",
        "flow": "💧",
        "meta": "🎯"
    }

    heads_html = ""
    for name, output in heads_output.items():
        color = head_colors.get(name, "#94a3b8")
        icon = head_icons.get(name, "•")
        alpha = output.get("alpha", 0)
        confidence = output.get("confidence", 0)

        bar_width = min(confidence * 100, 100)

        heads_html += f"""
        <div style="
            background: rgba(255,255,255,0.05);
            border-radius: 6px;
            padding: 10px;
            margin: 8px 0;
        ">
            <div style="display: flex; align-items: center; margin-bottom: 8px;">
                <span style="font-size: 18px; margin-right: 8px;">{icon}</span>
                <span style="color: {color}; font-weight: bold;">{name.upper()}</span>
                <span style="margin-left: auto; color: #94a3b8;">α: {alpha:.3f}</span>
            </div>
            <div style="background: #334155; border-radius: 4px; height: 6px; width: 100%;">
                <div style="background: {color}; border-radius: 4px; height: 6px; width: {bar_width}%;"></div>
            </div>
            <div style="font-size: 11px; color: #64748b; margin-top: 4px;">
                Confidence: {confidence:.3f}
            </div>
        </div>
        """

    total_alpha = sum(o.get("alpha", 0) for o in heads_output.values())
    total_confidence = sum(o.get("confidence", 0) for o in heads_output.values())

    return f"""
    <div style="
        background: rgba(0,212,255,0.1);
        border: 1px solid rgba(0,212,255,0.3);
        border-radius: 8px;
        padding: 15px;
    ">
        <h4 style="margin: 0 0 15px 0; color: #00d4ff;">
            🧩 MultiHead - 多头归因
        </h4>

        {heads_html if heads_html else '<span style="color: #64748b;">等待数据...</span>'}

        <div style="
            border-top: 1px solid rgba(255,255,255,0.1);
            margin-top: 15px;
            padding-top: 10px;
            display: flex;
            justify-content: space-between;
        ">
            <span style="color: #94a3b8;">总 α:</span>
            <span style="color: #00d4ff; font-weight: bold;">{total_alpha:.3f}</span>
            <span style="color: #94a3b8;">总 Confidence:</span>
            <span style="color: #00d4ff; font-weight: bold;">{total_confidence:.3f}</span>
        </div>
    </div>
    """


def render_memory_panel(memory_items: List[Dict[str, Any]]) -> str:
    """渲染 AttentionMemory 面板"""
    items_html = ""
    for i, item in enumerate(memory_items[:5]):
        event = item.get("event", {})
        score = item.get("score", 0)
        event_time = item.get("time", 0)
        age = time.time() - event_time if event_time else 0

        source = event.source if hasattr(event, 'source') else str(event)[:20]
        features = event.features if hasattr(event, 'features') else {}

        bar_width = min(score * 100, 100)
        score_color = "#4ade80" if score > 0.5 else "#fbbf24" if score > 0.2 else "#64748b"

        items_html += f"""
        <div style="
            background: rgba(255,255,255,0.05);
            border-radius: 6px;
            padding: 8px;
            margin: 6px 0;
        ">
            <div style="display: flex; justify-content: space-between;">
                <span style="color: #94a3b8;">{source}</span>
                <span style="color: #64748b; font-size: 11px;">{age:.1f}s 前</span>
            </div>
            <div style="background: #334155; border-radius: 4px; height: 6px; width: 100%; margin: 5px 0;">
                <div style="background: {score_color}; border-radius: 4px; height: 6px; width: {bar_width}%;"></div>
            </div>
            <div style="font-size: 11px; color: #64748b;">
                Score: <span style="color: {score_color};">{score:.3f}</span>
                | Features: {len(features)}
            </div>
        </div>
        """

    decay_rate = 300
    decay_info = f"""
    <div style="font-size: 11px; color: #64748b; margin-top: 10px;">
        半衰期: {decay_rate}s | 存储: {len(memory_items)} 条
    </div>
    """

    return f"""
    <div style="
        background: rgba(74,222,128,0.1);
        border: 1px solid rgba(74,222,128,0.3);
        border-radius: 8px;
        padding: 15px;
    ">
        <h4 style="margin: 0 0 15px 0; color: #4ade80;">
            💾 AttentionMemory - 持久记忆
        </h4>

        {items_html if items_html else '<span style="color: #64748b;">暂无记忆...</span>'}

        {decay_info}
    </div>
    """


def render_feedback_panel(feedback_info: Dict[str, Any]) -> str:
    """渲染 Bandit 反馈面板"""
    reward = feedback_info.get("reward", 0)
    action = feedback_info.get("action", "N/A")
    last_update = feedback_info.get("last_update", 0)
    total_feedbacks = feedback_info.get("total_feedbacks", 0)

    reward_color = "#4ade80" if reward > 0 else "#f87171" if reward < 0 else "#94a3b8"
    reward_icon = "📈" if reward > 0 else "📉" if reward < 0 else "➖"

    time_since = time.time() - last_update if last_update else 0
    time_str = f"{time_since:.1f}s 前" if time_since < 60 else f"{time_since/60:.1f}m 前"

    return f"""
    <div style="
        background: rgba(168,85,247,0.1);
        border: 1px solid rgba(168,85,247,0.3);
        border-radius: 8px;
        padding: 15px;
    ">
        <h4 style="margin: 0 0 15px 0; color: #a855f7;">
            🎯 Bandit 反馈闭环
        </h4>

        <div style="text-align: center; padding: 15px;">
            <div style="font-size: 32px; margin-bottom: 10px;">{reward_icon}</div>
            <div style="color: {reward_color}; font-size: 24px; font-weight: bold;">
                {reward:+.3f}
            </div>
            <div style="color: #94a3b8; font-size: 12px;">最近奖励</div>
        </div>

        <div style="margin: 15px 0;">
            <div style="display: flex; justify-content: space-between; margin: 5px 0;">
                <span style="color: #94a3b8;">策略:</span>
                <span style="color: #fff;">{action}</span>
            </div>
            <div style="display: flex; justify-content: space-between; margin: 5px 0;">
                <span style="color: #94a3b8;">累计反馈:</span>
                <span style="color: #fff;">{total_feedbacks}</span>
            </div>
            <div style="display: flex; justify-content: space-between; margin: 5px 0;">
                <span style="color: #94a3b8;">上次更新:</span>
                <span style="color: #fff;">{time_str}</span>
            </div>
        </div>

        <div style="
            background: rgba(168,85,247,0.2);
            border-radius: 6px;
            padding: 10px;
            font-size: 11px;
            color: #c4b5fd;
        ">
            注意力随反馈动态演化
        </div>
    </div>
    """


def render_kernel_live_view(kernel) -> str:
    """
    渲染 AttentionKernel 的实时视图

    Args:
        kernel: AttentionKernel 实例

    Returns:
        HTML 字符串
    """
    query_state = {
        "strategy_state": {},
        "portfolio_state": {},
        "market_regime": {"type": "trend"},
        "attention_focus": {"market": 0.8, "news": 0.5},
        "risk_bias": 0.6
    }

    heads_output = {}
    if hasattr(kernel, 'multi_head') and kernel.multi_head:
        for head in kernel.multi_head.heads:
            heads_output[head.name] = {"alpha": 0.5, "confidence": 0.7}

    memory_items = []
    if hasattr(kernel, 'memory') and kernel.memory:
        memory_items = kernel.memory.store[-5:]

    feedback_info = {
        "reward": 0.1,
        "action": "momentum_strategy",
        "last_update": time.time() - 30,
        "total_feedbacks": 42
    }

    kernel_state = {
        "query_state": query_state,
        "heads_output": heads_output,
        "memory_items": memory_items,
        "feedback_info": feedback_info
    }

    return render_kernel_dashboard(kernel_state)


def render_attention_flow_diagram() -> str:
    """渲染注意力流程图"""
    return """
    <div style="
        background: rgba(0,0,0,0.3);
        border-radius: 12px;
        padding: 20px;
        margin: 20px 0;
    ">
        <h4 style="margin: 0 0 20px 0; color: #00d4ff;">
            🔄 注意力流转图
        </h4>

        <div style="display: flex; justify-content: space-between; align-items: center; margin: 30px 0;">
            <div style="text-align: center;">
                <div style="
                    background: #334155;
                    border-radius: 50%;
                    width: 80px;
                    height: 80px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    margin: 0 auto 10px;
                ">
                    <span style="font-size: 32px;">📡</span>
                </div>
                <div style="color: #fff;">事件</div>
                <div style="color: #64748b; font-size: 11px;">Event</div>
            </div>

            <div style="color: #00d4ff; font-size: 24px;">→</div>

            <div style="text-align: center;">
                <div style="
                    background: linear-gradient(135deg, #00d4ff 0%, #0099cc 100%);
                    border-radius: 50%;
                    width: 80px;
                    height: 80px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    margin: 0 auto 10px;
                ">
                    <span style="font-size: 32px;">🧠</span>
                </div>
                <div style="color: #00d4ff;">QueryState</div>
                <div style="color: #64748b; font-size: 11px;">确定焦点</div>
            </div>

            <div style="color: #00d4ff; font-size: 24px;">→</div>

            <div style="text-align: center;">
                <div style="
                    background: #334155;
                    border-radius: 50%;
                    width: 80px;
                    height: 80px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    margin: 0 auto 10px;
                    border: 2px solid #4ade80;
                ">
                    <span style="font-size: 32px;">🧩</span>
                </div>
                <div style="color: #4ade80;">MultiHead</div>
                <div style="color: #64748b; font-size: 11px;">多头归因</div>
            </div>

            <div style="color: #00d4ff; font-size: 24px;">→</div>

            <div style="text-align: center;">
                <div style="
                    background: #334155;
                    border-radius: 50%;
                    width: 80px;
                    height: 80px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    margin: 0 auto 10px;
                    border: 2px solid #a855f7;
                ">
                    <span style="font-size: 32px;">💾</span>
                </div>
                <div style="color: #a855f7;">Memory</div>
                <div style="color: #64748b; font-size: 11px;">持久记忆</div>
            </div>

            <div style="color: #00d4ff; font-size: 24px;">→</div>

            <div style="text-align: center;">
                <div style="
                    background: #334155;
                    border-radius: 50%;
                    width: 80px;
                    height: 80px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    margin: 0 auto 10px;
                    border: 2px solid #f87171;
                ">
                    <span style="font-size: 32px;">🎯</span>
                </div>
                <div style="color: #f87171;">Bandit</div>
                <div style="color: #64748b; font-size: 11px;">反馈闭环</div>
            </div>
        </div>

        <div style="
            background: rgba(0,212,255,0.1);
            border-radius: 8px;
            padding: 15px;
            margin-top: 20px;
            font-size: 13px;
            color: #94a3b8;
        ">
            <strong style="color: #00d4ff;">核心思想：</strong>
            注意力不是"发现"重要信息，而是"制造"重要性。
            系统关注什么，什么就变得重要。
        </div>
    </div>
    """


__all__ = [
    "render_kernel_dashboard",
    "render_query_state_panel",
    "render_multi_head_panel",
    "render_memory_panel",
    "render_feedback_panel",
    "render_kernel_live_view",
    "render_attention_flow_diagram",
    "render_four_dimensions_status",
]


def render_four_dimensions_status() -> str:
    """渲染四维决策框架状态"""

    try:
        from deva.naja.attention.kernel import (
            get_four_dimensions_manager,
            FourDimensions,
        )
    except ImportError:
        return """
        <div style="
            background: #f1f5f9;
            border-radius: 8px;
            padding: 12px;
            margin: 10px 0;
            border: 1px solid #e2e8f0;
        ">
            <div style="font-size: 12px; color: #64748b;">
                四维决策框架模块未安装
            </div>
        </div>
        """

    manager = get_four_dimensions_manager()

    if manager is None:
        return """
        <div style="
            background: linear-gradient(135deg, #fef3c7, #fde68a);
            border-radius: 8px;
            padding: 12px;
            margin: 10px 0;
            border: 1px solid #f59e0b;
        ">
            <div style="display: flex; align-items: center; gap: 8px;">
                <span style="font-size: 16px;">🎯</span>
                <div>
                    <div style="font-size: 13px; font-weight: 600; color: #92400e;">
                        四维决策框架
                    </div>
                    <div style="font-size: 11px; color: #b45309;">
                        未启用管理器 · 建议使用 FourDimensionsManager
                    </div>
                </div>
            </div>
        </div>
        """

    kernel_fd_enabled = manager.kernel.is_four_dimensions_enabled()
    trigger_status = manager.trigger.get_status()
    auto_mode = manager.trigger.is_auto_mode()

    fd = FourDimensions()
    fd.update(
        session_manager=manager.trigger._get_session_manager(),
        portfolio=manager.trigger._get_portfolio(),
        strategy_manager=manager.trigger._get_strategy_manager(),
        scanner=manager.trigger._get_scanner(),
        macro_signal=0.5
    )

    if kernel_fd_enabled:
        status_label = "已启用"
        status_color = "#16a34a"
        bg_color = "#f0fdf4"
        border_color = "#bbf7d0"
    else:
        status_label = "已关闭"
        status_color = "#64748b"
        bg_color = "#f8fafc"
        border_color = "#e2e8f0"

    time_icon = "🟢" if fd.time.is_trading_open else "🔴"
    time_text = "交易中" if fd.time.is_trading_open else "非交易"
    capital_bar = min(fd.capital.cash_ratio * 100, 100)
    capital_color = "#16a34a" if fd.capital.cash_ratio > 0.2 else "#dc2626"
    capital_text = "有子弹" if fd.capital.has_bullets else "⚠️子弹不足"
    cap_icon = "💰"
    cap_text = "就绪" if fd.capability.is_ready else "⚠️未就绪"
    market_icon = "📊"
    if fd.market.liquidity_signal < 0.3:
        market_status_text = "极度恐慌"
        market_color = "#dc2626"
    elif fd.market.liquidity_signal > 0.7:
        market_status_text = "极度贪婪"
        market_color = "#16a34a"
    else:
        market_status_text = "中性"
        market_color = "#ca8a04"

    should_enable = trigger_status.get('should_enable', False)
    trigger_reason = trigger_status.get('trigger_reason', None) or '-'

    return f"""
    <div style="
        background: {bg_color};
        border-radius: 10px;
        padding: 14px;
        margin: 10px 0;
        border: 1px solid {border_color};
    ">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
            <div style="display: flex; align-items: center; gap: 8px;">
                <span style="font-size: 18px;">🎯</span>
                <div>
                    <div style="font-size: 14px; font-weight: 600; color: {status_color};">
                        四维决策框架
                    </div>
                    <div style="font-size: 11px; color: #64748b;">
                        {'自动模式' if auto_mode else '手动模式'}
                    </div>
                </div>
            </div>
            <div style="
                background: {status_color};
                color: white;
                padding: 4px 10px;
                border-radius: 12px;
                font-size: 12px;
                font-weight: 600;
            ">
                {status_label}
            </div>
        </div>

        <div style="display: grid; grid-template-columns: 1fr 1fr 1fr 1fr; gap: 10px; margin-bottom: 12px;">
            <div style="background: white; border-radius: 6px; padding: 10px; text-align: center;">
                <div style="font-size: 18px; margin-bottom: 4px;">⏰</div>
                <div style="font-size: 12px; color: #0f172a;">{time_icon} {time_text}</div>
                <div style="font-size: 10px; color: #64748b; margin-top: 2px;">压力: {fd.time.pressure:.0%}</div>
            </div>

            <div style="background: white; border-radius: 6px; padding: 10px; text-align: center;">
                <div style="font-size: 18px; margin-bottom: 4px;">{cap_icon}</div>
                <div style="font-size: 12px; color: {capital_color};">{capital_text}</div>
                <div style="
                    background: #e2e8f0;
                    border-radius: 3px;
                    height: 5px;
                    width: 100%;
                    margin-top: 4px;
                ">
                    <div style="
                        background: {capital_color};
                        border-radius: 3px;
                        height: 5px;
                        width: {capital_bar}%;
                    "></div>
                </div>
                <div style="font-size: 10px; color: #64748b; margin-top: 2px;">{fd.capital.cash_ratio:.0%}</div>
            </div>

            <div style="background: white; border-radius: 6px; padding: 10px; text-align: center;">
                <div style="font-size: 18px; margin-bottom: 4px;">🛠️</div>
                <div style="font-size: 12px; color: #0f172a;">{cap_text}</div>
                <div style="font-size: 10px; color: #64748b; margin-top: 2px;">{fd.capability.strategy_count} 策略</div>
            </div>

            <div style="background: white; border-radius: 6px; padding: 10px; text-align: center;">
                <div style="font-size: 18px; margin-bottom: 4px;">{market_icon}</div>
                <div style="font-size: 12px; color: {market_color};">{market_status_text}</div>
                <div style="font-size: 10px; color: {market_color}; margin-top: 2px;">{fd.market.liquidity_signal:.2f}</div>
            </div>
        </div>

        <div style="
            background: rgba(0,0,0,0.03);
            border-radius: 6px;
            padding: 10px;
            font-size: 11px;
        ">
            <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
                <span style="color: #64748b;">自动触发条件:</span>
                <span style="color: {'#16a34a' if should_enable else '#94a3b8'};">
                    {'✅ 满足' if should_enable else '❌ 不满足'}
                </span>
            </div>
            <div style="display: flex; justify-content: space-between;">
                <span style="color: #64748b;">触发原因:</span>
                <span style="color: #7c3aed;">{trigger_reason}</span>
            </div>
        </div>

        <div style="
            margin-top: 10px;
            padding: 10px;
            background: rgba(14, 165, 233, 0.08);
            border-radius: 6px;
            font-size: 10px;
            color: #64748b;
        ">
            <div style="font-weight: 600; color: #0ea5e9; margin-bottom: 6px;">💡 四维决策框架说明</div>
            <div style="margin-bottom: 4px;">
                <strong>四维：</strong>天时(时间) · 资金(子弹) · 能力(策略) · 市场(机会)
            </div>
            <div style="margin-bottom: 4px;">
                <strong>门控：</strong>时间非交易→alpha=0 | 资金不足→alpha=0 | 策略未就绪→alpha×0.3
            </div>
            <div>
                <strong>自动启用条件：</strong>资金 &lt;20% 或 市场信号 &lt;0.3 或 &gt;0.8 时自动启用保守模式
            </div>
        </div>
    </div>
    """