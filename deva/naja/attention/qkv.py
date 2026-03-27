"""QKV 可视化页面

展示注意力系统的 Query、Key、Value 实时状态
"""

import time
from typing import Dict, Any, List


def get_qkv_data() -> Dict[str, Any]:
    """获取 QKV 实时数据"""
    try:
        from deva.naja.attention.center import get_orchestrator
        orchestrator = get_orchestrator()

        if not orchestrator or not hasattr(orchestrator, '_attention_kernel'):
            return _get_empty_qkv_data()

        kernel = orchestrator._attention_kernel
        query_state = orchestrator._attention_query_state

        if not kernel or not query_state:
            return _get_empty_qkv_data()

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
                            "timestamp": e.timestamp if hasattr(e, 'timestamp') else 0,
                            "score": item.get("score", 0),
                            "age": time.time() - item.get("time", 0) if item.get("time") else 0
                        })
        except Exception:
            pass

        query_data = {
            "market_regime": query_state.market_regime if hasattr(query_state, 'market_regime') else {},
            "risk_bias": query_state.risk_bias if hasattr(query_state, 'risk_bias') else 0.5,
            "attention_focus": query_state.attention_focus if hasattr(query_state, 'attention_focus') else {},
            "portfolio_state": query_state.portfolio_state if hasattr(query_state, 'portfolio_state') else {},
            "strategy_state": query_state.strategy_state if hasattr(query_state, 'strategy_state') else {},
        }

        multi_head_result = {}
        try:
            if hasattr(kernel, 'multi_head') and kernel.multi_head:
                for head in kernel.multi_head.heads:
                    head_result = head.compute(query_state, [])
                    multi_head_result[head.name] = head_result
        except Exception:
            pass

        return {
            "query": query_data,
            "events": events,
            "multi_head": multi_head_result,
            "timestamp": time.time(),
            "has_data": True
        }

    except Exception as e:
        return _get_empty_qkv_data()


def _get_empty_qkv_data() -> Dict[str, Any]:
    """获取空数据状态"""
    return {
        "query": {
            "market_regime": {"type": "unknown", "up_ratio": 0, "down_ratio": 0},
            "risk_bias": 0.5,
            "attention_focus": {},
            "portfolio_state": {},
            "strategy_state": {},
        },
        "events": [],
        "multi_head": {},
        "timestamp": time.time(),
        "has_data": False
    }


def render_qkv_page(ctx: Dict):
    """渲染 QKV 页面主入口"""

    qkv_data = get_qkv_data()

    ctx["put_html"](r"""
    <style>
        .qkv-container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        }
        .qkv-header {
            text-align: center;
            margin-bottom: 30px;
        }
        .qkv-header h1 {
            color: #00d4ff;
            font-size: 28px;
            margin: 0 0 10px 0;
        }
        .qkv-header p {
            color: #94a3b8;
            margin: 0;
        }
        .qkv-grid {
            display: grid;
            grid-template-columns: 1fr 1fr 1fr;
            gap: 20px;
            margin-bottom: 30px;
        }
        .qkv-panel {
            background: linear-gradient(135deg, rgba(15,23,42,0.9) 0%, rgba(30,41,59,0.9) 100%);
            border-radius: 12px;
            padding: 20px;
            border: 1px solid rgba(255,255,255,0.1);
        }
        .qkv-panel-query { border-top: 3px solid #00d4ff; }
        .qkv-panel-key { border-top: 3px solid #4ade80; }
        .qkv-panel-value { border-top: 3px solid #a855f7; }

        .panel-title {
            font-size: 16px;
            font-weight: 600;
            margin: 0 0 15px 0;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .panel-title .icon {
            font-size: 20px;
        }
        .qkv-panel-query .panel-title { color: #00d4ff; }
        .qkv-panel-key .panel-title { color: #4ade80; }
        .qkv-panel-value .panel-title { color: #a855f7; }

        .stat-row {
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid rgba(255,255,255,0.05);
        }
        .stat-label {
            color: #94a3b8;
            font-size: 13px;
        }
        .stat-value {
            color: #fff;
            font-size: 13px;
            font-weight: 500;
        }
        .stat-value.high { color: #4ade80; }
        .stat-value.medium { color: #fbbf24; }
        .stat-value.low { color: #f87171; }

        .focus-bar {
            margin: 8px 0;
        }
        .focus-bar-label {
            display: flex;
            justify-content: space-between;
            font-size: 12px;
            margin-bottom: 4px;
        }
        .focus-bar-track {
            background: #334155;
            border-radius: 4px;
            height: 8px;
            overflow: hidden;
        }
        .focus-bar-fill {
            height: 100%;
            border-radius: 4px;
            transition: width 0.3s ease;
        }

        .event-card {
            background: rgba(255,255,255,0.03);
            border-radius: 8px;
            padding: 12px;
            margin: 8px 0;
            border-left: 3px solid #4ade80;
        }
        .event-card-header {
            display: flex;
            justify-content: space-between;
            margin-bottom: 8px;
        }
        .event-source {
            font-weight: 600;
            color: #4ade80;
        }
        .event-time {
            color: #64748b;
            font-size: 11px;
        }
        .event-features {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 6px;
        }
        .feature-chip {
            background: rgba(255,255,255,0.05);
            border-radius: 4px;
            padding: 4px 8px;
            font-size: 11px;
        }
        .feature-chip .label { color: #94a3b8; }
        .feature-chip .value { color: #fff; font-weight: 500; }

        .head-card {
            background: rgba(255,255,255,0.03);
            border-radius: 8px;
            padding: 12px;
            margin: 8px 0;
        }
        .head-card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 8px;
        }
        .head-name {
            font-weight: 600;
            color: #a855f7;
        }
        .head-icon {
            font-size: 18px;
        }
        .metric-row {
            display: flex;
            justify-content: space-between;
            font-size: 12px;
            padding: 3px 0;
        }

        .qkv-flow {
            background: linear-gradient(135deg, rgba(15,23,42,0.9) 0%, rgba(30,41,59,0.9) 100%);
            border-radius: 12px;
            padding: 25px;
            border: 1px solid rgba(255,255,255,0.1);
            margin-bottom: 20px;
        }
        .flow-title {
            color: #00d4ff;
            font-size: 18px;
            font-weight: 600;
            margin: 0 0 25px 0;
            text-align: center;
        }
        .flow-diagram {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 20px 0;
        }
        .flow-node {
            text-align: center;
            flex: 1;
        }
        .flow-node-circle {
            width: 80px;
            height: 80px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0 auto 10px;
            font-size: 32px;
        }
        .flow-node-q { background: linear-gradient(135deg, #00d4ff 0%, #0099cc 100%); }
        .flow-node-k { background: linear-gradient(135deg, #4ade80 0%, #22c55e 100%); }
        .flow-node-attention { background: linear-gradient(135deg, #fbbf24 0%, #f59e0b 100%); }
        .flow-node-v { background: linear-gradient(135deg, #a855f7 0%, #9333ea 100%); }

        .flow-node-label {
            color: #fff;
            font-weight: 600;
            font-size: 14px;
        }
        .flow-node-sublabel {
            color: #94a3b8;
            font-size: 11px;
        }
        .flow-arrow {
            color: #64748b;
            font-size: 24px;
            flex: 0.5;
        }

        .formula-box {
            background: rgba(0,212,255,0.1);
            border: 1px solid rgba(0,212,255,0.3);
            border-radius: 8px;
            padding: 15px;
            margin-top: 20px;
            text-align: center;
        }
        .formula {
            color: #00d4ff;
            font-size: 16px;
            font-family: 'Courier New', monospace;
        }
        .formula-desc {
            color: #94a3b8;
            font-size: 12px;
            margin-top: 8px;
        }

        .empty-state {
            text-align: center;
            padding: 40px;
            color: #64748b;
        }
        .empty-state .icon {
            font-size: 48px;
            margin-bottom: 15px;
        }
    </style>
    """)

    page_html = _build_qkv_html(qkv_data)
    ctx["put_html"](page_html)


def _build_qkv_html(qkv_data: Dict[str, Any]) -> str:
    """构建 QKV 页面 HTML"""

    query = qkv_data.get("query", {})
    events = qkv_data.get("events", [])
    multi_head = qkv_data.get("multi_head", {})
    has_data = qkv_data.get("has_data", False)

    query_html = _render_query_panel(query)
    events_html = _render_events_panel(events)
    value_html = _render_value_panel(multi_head, query)
    flow_html = _render_flow_diagram(query, events, multi_head)

    return f"""
    <div class="qkv-container">
        <div class="qkv-header">
            <h1>🔣 QKV 可视化</h1>
            <p>注意力系统 Query / Key / Value 实时状态</p>
        </div>

        {flow_html}

        <div class="qkv-grid">
            {query_html}
            {events_html}
            {value_html}
        </div>
    </div>
    """


def _render_query_panel(query: Dict[str, Any]) -> str:
    """渲染 Query 面板"""
    market_regime = query.get("market_regime", {})
    regime_type = market_regime.get("type", "unknown") if isinstance(market_regime, dict) else "unknown"
    risk_bias = query.get("risk_bias", 0.5)
    attention_focus = query.get("attention_focus", {})
    portfolio = query.get("portfolio_state", {})

    regime_colors = {
        "trend_up": "#4ade80",
        "weak_trend_up": "#86efac",
        "neutral": "#94a3b8",
        "mixed": "#fbbf24",
        "weak_trend_down": "#fca5a5",
        "trend_down": "#f87171",
    }
    regime_color = regime_colors.get(regime_type, "#94a3b8")

    risk_level = "高" if risk_bias < 0.3 else "中" if risk_bias < 0.6 else "低"
    risk_color = "#f87171" if risk_bias < 0.3 else "#fbbf24" if risk_bias < 0.6 else "#4ade80"

    focus_bars = ""
    if attention_focus:
        sorted_focus = sorted(attention_focus.items(), key=lambda x: x[1], reverse=True)[:5]
        for name, value in sorted_focus:
            bar_width = min(value * 100, 100)
            fill_color = "#00d4ff" if value > 0.7 else "#60a5fa" if value > 0.4 else "#64748b"
            focus_bars += f"""
            <div class="focus-bar">
                <div class="focus-bar-label">
                    <span style="color: #fff;">{name}</span>
                    <span style="color: #94a3b8;">{value:.3f}</span>
                </div>
                <div class="focus-bar-track">
                    <div class="focus-bar-fill" style="width: {bar_width}%; background: {fill_color};"></div>
                </div>
            </div>
            """

    held_count = len(portfolio.get("held_symbols", [])) if isinstance(portfolio, dict) else 0
    total_return = portfolio.get("total_return", 0) if isinstance(portfolio, dict) else 0

    return f"""
    <div class="qkv-panel qkv-panel-query">
        <h3 class="panel-title">
            <span class="icon">🔍</span>
            <span>Query - 当前焦点</span>
        </h3>

        <div class="stat-row">
            <span class="stat-label">市场状态</span>
            <span class="stat-value" style="color: {regime_color};">{regime_type.upper()}</span>
        </div>
        <div class="stat-row">
            <span class="stat-label">风险偏好</span>
            <span class="stat-value" style="color: {risk_color};">{risk_bias:.2f} ({risk_level})</span>
        </div>
        <div class="stat-row">
            <span class="stat-label">持仓数量</span>
            <span class="stat-value">{held_count} 只</span>
        </div>
        <div class="stat-row">
            <span class="stat-label">组合收益</span>
            <span class="stat-value {'high' if total_return > 0 else 'low'}">{total_return:+.2f}%</span>
        </div>

        <div style="margin-top: 15px;">
            <div style="color: #94a3b8; font-size: 12px; margin-bottom: 10px;">注意力焦点 Top5</div>
            {focus_bars if focus_bars else '<div style="color: #64748b; font-size: 12px;">暂无数据</div>'}
        </div>
    </div>
    """


def _render_events_panel(events: List[Dict]) -> str:
    """渲染 Key 事件面板"""
    if not events:
        return """
        <div class="qkv-panel qkv-panel-key">
            <h3 class="panel-title">
                <span class="icon">🔑</span>
                <span>Key - 事件输入</span>
            </h3>
            <div class="empty-state">
                <div class="icon">📭</div>
                <div>暂无事件数据</div>
                <div style="font-size: 12px; margin-top: 5px;">等待市场事件流入...</div>
            </div>
        </div>
        """

    source_icons = {
        "market": "📈",
        "news": "📰",
        "flow": "💧",
        "meta": "🎯",
        "default": "📌"
    }

    events_html = ""
    for event in events[:5]:
        source = event.get("source", "unknown")
        icon = source_icons.get(source, source_icons["default"])
        age = event.get("age", 0)
        features = event.get("key", {})

        if isinstance(features, dict):
            price_change = features.get("price_change", 0)
            volume_spike = features.get("volume_spike", 0)
            alpha = features.get("alpha", 0)
            risk = features.get("risk", 0)
            confidence = features.get("confidence", 0)
        else:
            price_change = volume_spike = alpha = risk = confidence = 0

        events_html += f"""
        <div class="event-card">
            <div class="event-card-header">
                <span class="event-source">{icon} {source.upper()}</span>
                <span class="event-time">{age:.1f}s 前</span>
            </div>
            <div class="event-features">
                <div class="feature-chip">
                    <span class="label">价格</span>
                    <span class="value" style="color: {'#4ade80' if price_change > 0 else '#f87171'};">{price_change:+.2f}%</span>
                </div>
                <div class="feature-chip">
                    <span class="label">成交量</span>
                    <span class="value">{volume_spike:.2f}x</span>
                </div>
                <div class="feature-chip">
                    <span class="label">Alpha</span>
                    <span class="value" style="color: #00d4ff;">{alpha:.3f}</span>
                </div>
                <div class="feature-chip">
                    <span class="label">Risk</span>
                    <span class="value" style="color: #fbbf24;">{risk:.3f}</span>
                </div>
                <div class="feature-chip">
                    <span class="label">Confidence</span>
                    <span class="value" style="color: #a855f7;">{confidence:.3f}</span>
                </div>
            </div>
        </div>
        """

    return f"""
    <div class="qkv-panel qkv-panel-key">
        <h3 class="panel-title">
            <span class="icon">🔑</span>
            <span>Key - 事件输入 ({len(events)} 条)</span>
        </h3>
        {events_html}
    </div>
    """


def _render_value_panel(multi_head: Dict, query: Dict) -> str:
    """渲染 Value 输出面板"""
    if not multi_head:
        return """
        <div class="qkv-panel qkv-panel-value">
            <h3 class="panel-title">
                <span class="icon">💎</span>
                <span>Value - 输出价值</span>
            </h3>
            <div class="empty-state">
                <div class="icon">📭</div>
                <div>暂无输出数据</div>
                <div style="font-size: 12px; margin-top: 5px;">等待注意力计算...</div>
            </div>
        </div>
        """

    head_colors = {
        "market": "#4ade80",
        "news": "#60a5fa",
        "flow": "#f472b6",
        "meta": "#fbbf24",
    }
    head_icons = {
        "market": "📈",
        "news": "📰",
        "flow": "💧",
        "meta": "🎯",
    }

    heads_html = ""
    total_alpha = 0
    total_confidence = 0

    for name, output in multi_head.items():
        color = head_colors.get(name, "#94a3b8")
        icon = head_icons.get(name, "•")
        alpha = output.get("alpha", 0)
        confidence = output.get("confidence", 0)
        risk = output.get("risk", 0)

        total_alpha += alpha
        total_confidence += confidence

        heads_html += f"""
        <div class="head-card">
            <div class="head-card-header">
                <span class="head-icon">{icon}</span>
                <span class="head-name" style="color: {color};">{name.upper()}</span>
            </div>
            <div class="metric-row">
                <span style="color: #94a3b8;">Alpha</span>
                <span style="color: #00d4ff; font-weight: 600;">{alpha:.4f}</span>
            </div>
            <div class="metric-row">
                <span style="color: #94a3b8;">Confidence</span>
                <span style="color: #a855f7; font-weight: 600;">{confidence:.4f}</span>
            </div>
            <div class="metric-row">
                <span style="color: #94a3b8;">Risk</span>
                <span style="color: #fbbf24; font-weight: 600;">{risk:.4f}</span>
            </div>
        </div>
        """

    return f"""
    <div class="qkv-panel qkv-panel-value">
        <h3 class="panel-title">
            <span class="icon">💎</span>
            <span>Value - 多头输出</span>
        </h3>

        <div class="head-card" style="background: rgba(0,212,255,0.1); border: 1px solid rgba(0,212,255,0.3);">
            <div class="head-card-header">
                <span style="font-size: 18px;">Σ</span>
                <span style="color: #00d4ff; font-weight: 600;">TOTAL</span>
            </div>
            <div class="metric-row">
                <span style="color: #94a3b8;">Alpha</span>
                <span style="color: #00d4ff; font-weight: 600;">{total_alpha:.4f}</span>
            </div>
            <div class="metric-row">
                <span style="color: #94a3b8;">Confidence</span>
                <span style="color: #a855f7; font-weight: 600;">{total_confidence:.4f}</span>
            </div>
        </div>

        {heads_html}
    </div>
    """


def _render_flow_diagram(query: Dict, events: List, multi_head: Dict) -> str:
    """渲染注意力流向图"""
    regime_type = query.get("market_regime", {}).get("type", "unknown") if isinstance(query.get("market_regime"), dict) else "unknown"
    risk_bias = query.get("risk_bias", 0.5)
    event_count = len(events)
    head_count = len(multi_head)

    has_data = event_count > 0 and head_count > 0

    return f"""
    <div class="qkv-flow">
        <h3 class="flow-title">🔄 注意力流向</h3>

        <div class="flow-diagram">
            <div class="flow-node">
                <div class="flow-node-circle flow-node-q">🔍</div>
                <div class="flow-node-label">Query</div>
                <div class="flow-node-sublabel">{regime_type}</div>
                <div class="flow-node-sublabel">风险偏好: {risk_bias:.2f}</div>
            </div>

            <div class="flow-arrow">→</div>

            <div class="flow-node">
                <div class="flow-node-circle flow-node-k">🔑</div>
                <div class="flow-node-label">Key</div>
                <div class="flow-node-sublabel">{event_count} 事件</div>
                <div class="flow-node-sublabel">特征编码</div>
            </div>

            <div class="flow-arrow">→</div>

            <div class="flow-node">
                <div class="flow-node-circle flow-node-attention">🧩</div>
                <div class="flow-node-label">Attention</div>
                <div class="flow-node-sublabel">Score(Q,K)</div>
                <div class="flow-node-sublabel">softmax</div>
            </div>

            <div class="flow-arrow">→</div>

            <div class="flow-node">
                <div class="flow-node-circle flow-node-v">💎</div>
                <div class="flow-node-label">Value</div>
                <div class="flow-node-sublabel">{head_count} 头输出</div>
                <div class="flow-node-sublabel">加权聚合</div>
            </div>
        </div>

        <div class="formula-box">
            <div class="formula">Attention(Q, K, V) = softmax(QK^T / √d) × V</div>
            <div class="formula-desc">
                Query 决定"关注什么"，Key 描述"是什么"，Value 包含"值多少"。
                通过 Q-K 相似度计算注意力权重，再对 V 加权求和得到输出。
            </div>
        </div>
    </div>
    """


__all__ = ["render_qkv_page", "get_qkv_data"]