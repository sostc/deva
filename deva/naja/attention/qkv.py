"""QKV 可视化页面

展示注意力系统的 Query、Key、Value 实时状态
包含价值观系统可视化
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
                            "features": e.features if hasattr(e, 'features') else {},
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

        value_data = _get_value_data(query_state, events)

        rescue_state = {}
        try:
            if hasattr(kernel, '_get_rescue_orchestrator'):
                orch = kernel._get_rescue_orchestrator()
                rescue_state = orch.get_state() if hasattr(orch, 'get_state') else {}
        except Exception:
            pass

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
        value_info = query_state.get_value_profile_info() if hasattr(query_state, 'get_value_profile_info') else {}
        weights = query_state.get_value_weights() if hasattr(query_state, 'get_value_weights') else {}
        preferences = query_state.get_value_preferences() if hasattr(query_state, 'get_value_preferences') else {}
        suggestions = query_state.get_value_suggestions() if hasattr(query_state, 'get_value_suggestions') else []

        from deva.naja.attention.values import get_value_system
        vs = get_value_system()
        performances = vs.get_all_performances() if vs else {}
        recent_attentions = vs.get_recent_attentions(5) if vs else []

        profiles = vs.get_all_profiles() if vs else []
        profile_list = [p.to_dict() for p in profiles] if profiles else []

        strategy_mapping = _get_strategy_value_mapping()

        return {
            "active_type": value_info.get("active_type", "trend"),
            "active_type_display": value_info.get("active_type_display", "趋势追踪"),
            "weights": weights,
            "preferences": preferences,
            "suggestions": suggestions,
            "performances": performances,
            "recent_attentions": recent_attentions,
            "profiles": profile_list,
            "strategy_mapping": strategy_mapping,
        }
    except Exception:
        return {
            "active_type": "trend",
            "active_type_display": "趋势追踪",
            "weights": {},
            "preferences": {},
            "suggestions": [],
            "performances": {},
            "recent_attentions": [],
            "profiles": [],
            "strategy_mapping": [],
        }


def _get_strategy_value_mapping() -> List[Dict[str, Any]]:
    """获取策略-价值观映射"""
    from deva.naja.attention.values.mapping import VALUE_STRATEGY_MAPPING

    implemented_strategies = {
        "global_sentinel": {"name": "全局市场监控", "value_type": "value"},
        "sector_hunter": {"name": "板块轮动猎人", "value_type": "momentum"},
        "momentum_tracker": {"name": "动量突破追踪", "value_type": "trend"},
        "anomaly_sniper": {"name": "异常模式狙击", "value_type": "contrarian"},
        "smart_money": {"name": "聪明资金检测", "value_type": "liquidity"},
    }

    mapping = []
    for strategy_id, info in implemented_strategies.items():
        value_type = info["value_type"]
        config = VALUE_STRATEGY_MAPPING.get(value_type, {})
        mapping.append({
            "strategy_id": strategy_id,
            "strategy_name": info["name"],
            "value_type": value_type,
            "value_name": config.get("name", value_type),
            "implemented": True,
            "primary": config.get("primary", "") == strategy_id,
        })

    return mapping


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
        "values": {
            "active_type": "trend",
            "active_type_display": "趋势追踪",
            "weights": {},
            "preferences": {},
            "suggestions": [],
            "performances": {},
            "recent_attentions": [],
            "profiles": [],
        },
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

        /* Tab Navigation */
        .qkv-tabs {
            display: flex;
            gap: 8px;
            margin-bottom: 20px;
            border-bottom: 1px solid rgba(255,255,255,0.1);
            padding-bottom: 12px;
        }
        .qkv-tab {
            padding: 10px 20px;
            border-radius: 8px 8px 0 0;
            background: rgba(255,255,255,0.05);
            color: #94a3b8;
            cursor: pointer;
            transition: all 0.3s ease;
            font-size: 14px;
            font-weight: 500;
            border: none;
        }
        .qkv-tab:hover {
            background: rgba(255,255,255,0.1);
            color: #fff;
        }
        .qkv-tab.active {
            background: linear-gradient(135deg, rgba(0,212,255,0.2) 0%, rgba(168,85,247,0.2) 100%);
            color: #00d4ff;
            border-bottom: 2px solid #00d4ff;
        }
        .qkv-tab-icon {
            margin-right: 6px;
        }

        /* Tab Content */
        .qkv-tab-content {
            display: none;
        }
        .qkv-tab-content.active {
            display: block;
        }

        /* Panel Styles */
        .qkv-grid {
            display: grid;
            grid-template-columns: 1fr 1fr 1fr;
            gap: 20px;
            margin-bottom: 30px;
        }
        .qkv-grid-2col {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin-bottom: 30px;
        }
        .qkv-grid-full {
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
        .qkv-panel-value-detail { border-top: 3px solid #a855f7; }
        .qkv-panel-values { border-top: 3px solid #fbbf24; }
        .qkv-panel-explain { border-top: 3px solid #f472b6; }
        .qkv-panel-evolution { border-top: 3px solid #22c55e; }

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
        .qkv-panel-values .panel-title { color: #fbbf24; }
        .qkv-panel-explain .panel-title { color: #f472b6; }
        .qkv-panel-evolution .panel-title { color: #22c55e; }

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

        /* Values Panel Styles */
        .value-selector {
            display: flex;
            gap: 8px;
            margin-bottom: 15px;
            flex-wrap: wrap;
        }
        .value-chip {
            padding: 6px 12px;
            border-radius: 16px;
            background: rgba(255,255,255,0.05);
            color: #94a3b8;
            font-size: 12px;
            cursor: pointer;
            transition: all 0.3s ease;
            border: 1px solid transparent;
        }
        .value-chip:hover {
            background: rgba(255,255,255,0.1);
        }
        .value-chip.active {
            background: rgba(251,191,36,0.2);
            color: #fbbf24;
            border-color: #fbbf24;
        }

        .weight-bar {
            margin: 12px 0;
        }
        .weight-bar-label {
            display: flex;
            justify-content: space-between;
            font-size: 12px;
            margin-bottom: 4px;
        }
        .weight-bar-track {
            background: #334155;
            border-radius: 4px;
            height: 6px;
            overflow: hidden;
        }
        .weight-bar-fill {
            height: 100%;
            border-radius: 4px;
            transition: width 0.3s ease;
        }

        .principle-item {
            background: rgba(255,255,255,0.03);
            border-radius: 6px;
            padding: 8px 12px;
            margin: 6px 0;
            font-size: 12px;
            color: #e2e8f0;
            border-left: 3px solid #fbbf24;
        }

        .attention-explain-card {
            background: rgba(255,255,255,0.03);
            border-radius: 8px;
            padding: 12px;
            margin: 8px 0;
            border-left: 3px solid #f472b6;
        }
        .attention-explain-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 8px;
        }
        .attention-symbol {
            font-weight: 600;
            color: #f472b6;
        }
        .attention-score {
            background: rgba(244,114,182,0.2);
            color: #f472b6;
            padding: 2px 8px;
            border-radius: 10px;
            font-size: 11px;
        }
        .attention-reason {
            font-size: 12px;
            color: #94a3b8;
            line-height: 1.5;
        }
        .attention-reason strong {
            color: #22c55e;
        }

        .evolution-bar {
            margin: 15px 0;
        }
        .evolution-bar-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 6px;
        }
        .evolution-name {
            font-size: 13px;
            color: #fff;
            font-weight: 500;
        }
        .evolution-return {
            font-size: 13px;
            font-weight: 600;
        }
        .evolution-return.positive { color: #4ade80; }
        .evolution-return.negative { color: #f87171; }
        .evolution-return.neutral { color: #94a3b8; }
        .evolution-track {
            background: #334155;
            border-radius: 4px;
            height: 10px;
            overflow: hidden;
        }
        .evolution-fill {
            height: 100%;
            border-radius: 4px;
            transition: width 0.5s ease;
        }

        .suggestion-card {
            background: rgba(255,255,255,0.03);
            border-radius: 8px;
            padding: 12px;
            margin: 8px 0;
            font-size: 13px;
        }
        .suggestion-card .emoji {
            margin-right: 8px;
        }

        .profile-card {
            background: rgba(255,255,255,0.05);
            border-radius: 8px;
            padding: 12px;
            margin: 8px 0;
            cursor: pointer;
            transition: all 0.3s ease;
            border: 1px solid transparent;
        }
        .profile-card:hover {
            background: rgba(255,255,255,0.08);
            border-color: rgba(255,255,255,0.1);
        }
        .profile-card.active {
            border-color: #fbbf24;
            background: rgba(251,191,36,0.1);
        }
        .profile-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 6px;
        }
        .profile-name {
            font-weight: 600;
            color: #fff;
        }
        .profile-status {
            font-size: 11px;
            padding: 2px 8px;
            border-radius: 10px;
        }
        .profile-status.enabled {
            background: rgba(74,222,128,0.2);
            color: #4ade80;
        }
        .profile-status.disabled {
            background: rgba(239,68,68,0.2);
            color: #f87171;
        }
        .profile-desc {
            font-size: 12px;
            color: #94a3b8;
        }
    </style>

    <script>
        function switchTab(tabName) {
            document.querySelectorAll('.qkv-tab').forEach(tab => tab.classList.remove('active'));
            document.querySelectorAll('.qkv-tab-content').forEach(content => content.classList.remove('active'));

            document.querySelector(`[data-tab="${tabName}"]`).classList.add('active');
            document.getElementById('tab-' + tabName).classList.add('active');
        }
    </script>
    """)

    page_html = _build_qkv_html(qkv_data)
    ctx["put_html"](page_html)


def _build_qkv_html(qkv_data: Dict[str, Any]) -> str:
    """构建 QKV 页面 HTML"""

    query = qkv_data.get("query", {})
    events = qkv_data.get("events", [])
    multi_head = qkv_data.get("multi_head", {})
    values = qkv_data.get("values", {})
    has_data = qkv_data.get("has_data", False)
    rescue_state = qkv_data.get("rescue_state", {})

    tab_nav = _render_tab_nav()
    overview_content = _render_overview_tab(query, events, multi_head, rescue_state)
    values_content = _render_values_tab(values, events)
    explain_content = _render_explain_tab(query, events, values)
    evolution_content = _render_evolution_tab(values)

    return f"""
    <div class="qkv-container">
        <div class="qkv-header">
            <h1>🔣 QKV 可视化</h1>
            <p>Query / Key / Value 实时注意力状态</p>
        </div>

        {tab_nav}

        <div id="tab-overview" class="qkv-tab-content active">
            {overview_content}
        </div>

        <div id="tab-values" class="qkv-tab-content">
            {values_content}
        </div>

        <div id="tab-explain" class="qkv-tab-content">
            {explain_content}
        </div>

        <div id="tab-evolution" class="qkv-tab-content">
            {evolution_content}
        </div>
    </div>
    """


def _render_tab_nav() -> str:
    """渲染Tab导航"""
    return """
    <div class="qkv-tabs">
        <button class="qkv-tab active" data-tab="overview" onclick="switchTab('overview')">
            <span class="qkv-tab-icon">📊</span>总览
        </button>
        <button class="qkv-tab" data-tab="values" onclick="switchTab('values')">
            <span class="qkv-tab-icon">📊</span>QKV状态
        </button>
        <button class="qkv-tab" data-tab="explain" onclick="switchTab('explain')">
            <span class="qkv-tab-icon">💭</span>注意力解释
        </button>
        <button class="qkv-tab" data-tab="evolution" onclick="switchTab('evolution')">
            <span class="qkv-tab-icon">📈</span>价值观演进
        </button>
    </div>
    """


def _render_overview_tab(query: Dict, events: List, multi_head: Dict, rescue_state: Dict = None) -> str:
    """渲染总览Tab"""
    query_html = _render_query_panel(query)
    events_html = _render_events_panel(events)
    value_html = _render_value_panel(multi_head, query)
    flow_html = _render_flow_diagram(query, events, multi_head)
    rescue_html = _render_liquidity_rescue_panel(rescue_state)

    return f"""
    {flow_html}
    <div class="qkv-grid">
        {query_html}
        {events_html}
        {value_html}
        {rescue_html}
    </div>
    """


def _render_values_tab(values: Dict, events: List) -> str:
    """渲染QKV实时状态Tab"""
    query = values.get("query", {}) if isinstance(values, dict) else {}
    multi_head = values.get("multi_head", {}) if isinstance(values, dict) else {}

    regime = query.get("market_regime", {})
    regime_type = regime.get("type", "unknown") if isinstance(regime, dict) else "unknown"
    risk_bias = query.get("risk_bias", 0.5)

    regime_colors = {
        "trend_up": "#4ade80",
        "weak_trend_up": "#86efac",
        "neutral": "#94a3b8",
        "mixed": "#fbbf24",
        "weak_trend_down": "#fca5a5",
        "trend_down": "#f87171",
    }
    regime_color = regime_colors.get(regime_type, "#94a3b8")

    risk_level = "保守" if risk_bias < 0.3 else "中性" if risk_bias < 0.6 else "激进"
    risk_color = "#f87171" if risk_bias < 0.3 else "#fbbf24" if risk_bias < 0.6 else "#4ade80"

    head_data = ""
    if multi_head:
        for name, output in multi_head.items():
            alpha = output.get("alpha", 0) if isinstance(output, dict) else 0
            confidence = output.get("confidence", 0) if isinstance(output, dict) else 0
            head_data += """
            <div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.05);">
                <span style="color:#60a5fa;font-weight:500;">{name}</span>
                <span style="color:#00d4ff;">α {alpha:.4f}</span>
                <span style="color:#a855f7;">conf {confidence:.4f}</span>
            </div>
            """.format(name=name.upper(), alpha=alpha, confidence=confidence)
    else:
        head_data = '<div style="color:#64748b;font-size:12px;">等待注意力计算...</div>'

    event_count = len(events) if events else 0

    if events:
        first_event = events[0]
        event_source = first_event.get("source", "market").upper()
        event_age = first_event.get("age", 0)
        event_features = first_event.get("features", {})
        if isinstance(event_features, dict):
            price_change = event_features.get("price_change", 0)
            volume_spike = event_features.get("volume_spike", 1)
            score = first_event.get("score", 0)
        else:
            price_change = volume_spike = score = 0

        event_html = '''
                <div style="padding:10px;background:rgba(74,222,128,0.1);border-radius:6px;border-left:3px solid #4ade80;margin-bottom:8px;">
                    <div style="display:flex;justify-content:space-between;font-size:12px;">
                        <span style="color:#4ade80;font-weight:600;">{source}</span>
                        <span style="color:#64748b;">{age:.1f}s前</span>
                    </div>
                    <div style="font-size:11px;color:#94a3b8;margin-top:5px;">
                        {price_change:+.2f}% / {volume_spike:.1f}x / α {score:.3f}
                    </div>
                </div>
        '''.format(source=event_source, age=event_age, price_change=price_change, volume_spike=volume_spike, score=score)
    else:
        event_html = '<div style="color:#64748b;font-size:12px;text-align:center;padding:20px;">等待事件流入...</div>'

    return '''
    <div style="margin-bottom:20px;">
        <div class="qkv-panel qkv-panel-query" style="margin-bottom:15px;">
            <h3 class="panel-title"><span class="icon">🔍</span>Query - 注意力焦点</h3>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:15px;">
                <div style="text-align:center;padding:15px;background:rgba(255,255,255,0.03);border-radius:8px;">
                    <div style="font-size:24px;font-weight:600;color:{regime_color};">{regime_type}</div>
                    <div style="font-size:11px;color:#94a3b8;margin-top:5px;">市场状态</div>
                </div>
                <div style="text-align:center;padding:15px;background:rgba(255,255,255,0.03);border-radius:8px;">
                    <div style="font-size:24px;font-weight:600;color:{risk_color};">{risk_bias:.2f}</div>
                    <div style="font-size:11px;color:#94a3b8;margin-top:5px;">风险偏好 ({risk_level})</div>
                </div>
            </div>
        </div>

        <div class="qkv-panel qkv-panel-key" style="margin-bottom:15px;">
            <h3 class="panel-title"><span class="icon">🔑</span>Key - 事件输入</h3>
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:15px;">
                <span style="color:#94a3b8;font-size:12px;">共 {event_count} 条事件</span>
                <span style="color:#4ade80;font-size:11px;">实时更新</span>
            </div>
            <div style="max-height:200px;overflow-y:auto;">
                {event_html}
            </div>
        </div>

        <div class="qkv-panel qkv-panel-value">
            <h3 class="panel-title"><span class="icon">💎</span>Value - 多头输出</h3>
            <div style="margin-bottom:10px;">
                <div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid rgba(0,212,255,0.3);font-size:12px;color:#00d4ff;">
                    <span>HEAD</span>
                    <span>Alpha</span>
                    <span>Confidence</span>
                </div>
                {head_data}
            </div>
        </div>
    </div>

    <div style="margin-top:20px;padding:20px;background:linear-gradient(135deg,rgba(0,212,255,0.1),rgba(168,85,247,0.1));border-radius:12px;border:1px solid rgba(0,212,255,0.2);text-align:center;">
        <div style="color:#00d4ff;font-size:14px;margin-bottom:10px;">💡 价值观详情请查看</div>
        <a href="/" style="display:inline-block;padding:8px 20px;background:linear-gradient(135deg,#00d4ff,#0099cc);border-radius:20px;color:#fff;text-decoration:none;font-size:13px;">
            🏠 首页 - 价值观总览
        </a>
    </div>
    '''.format(
        regime_color=regime_color,
        regime_type=regime_type.upper(),
        risk_color=risk_color,
        risk_bias=risk_bias,
        risk_level=risk_level,
        event_count=event_count,
        event_html=event_html,
        head_data=head_data
    )


def _get_value_description(value_type: str) -> str:
    descs = {
        "trend": "顺势而为，追涨杀跌。趋势是你的朋友。",
        "contrarian": "人弃我取，分歧买入。别人恐惧时贪婪。",
        "value": "均值回归，价格终究合理。安全边际是第一原则。",
        "momentum": "强者恒强，弱者恒弱。趋势延续直到反转信号出现。",
        "liquidity": "资金流向决定价格方向。钱去哪里，价去哪里。",
        "liquidity_rescue": "在市场恐慌时提供流动性，等待恢复后获利。",
        "balanced": "多种价值观均衡配置，分散风险。",
        "growth": "看未来增长潜力，营收和市场份额是核心。",
        "event_driven": "重大事件创造Alpha，财报、并购、政策都是机会。",
        "market_making": "买卖价差收益，订单簿深度是生命线。",
        "sentiment_cycle": "恐惧与贪婪的周期博弈，媒体情绪是反向指标。",
    }
    return descs.get(value_type, "")


def _render_strategy_mapping(strategy_mapping: List[Dict]) -> str:
    """渲染策略-价值观映射"""
    if not strategy_mapping:
        return '<div style="color: #64748b; font-size: 12px;">暂无映射数据</div>'

    value_colors = {
        "trend": "#4ade80",
        "contrarian": "#f472b6",
        "value": "#fbbf24",
        "momentum": "#60a5fa",
        "liquidity": "#a855f7",
        "liquidity_rescue": "#f97316",
    }

    html = ""
    for item in strategy_mapping:
        strategy_name = item.get("strategy_name", item.get("strategy_id", ""))
        value_name = item.get("value_name", item.get("value_type", ""))
        value_type = item.get("value_type", "")
        color = value_colors.get(value_type, "#94a3b8")
        primary = "★" if item.get("primary") else ""

        html += f"""
        <div style="display: flex; justify-content: space-between; align-items: center; padding: 6px 0; border-bottom: 1px solid rgba(255,255,255,0.05);">
            <span style="color: #fff; font-size: 12px;">{strategy_name} {primary}</span>
            <span style="color: {color}; font-size: 12px; font-weight: 500;">→ {value_name}</span>
        </div>
        """
    return html


def _render_pending_values(pending_profiles: List[Dict]) -> str:
    """渲染待实现的价值观"""
    if not pending_profiles:
        return '<div style="color: #64748b; font-size: 12px;">暂无待实现价值观</div>'

    html = '<div class="qkv-grid-2col">'
    for profile in pending_profiles:
        p_name = profile.get("name", "")
        p_desc = profile.get("description", "")
        p_principles = profile.get("principles", [])
        p_strategies = profile.get("pending_strategies", [])

        strategies_str = "、".join([s.replace("_", " ").title() for s in p_strategies]) if p_strategies else "待定"

        principles_html = ""
        for p in p_principles[:2]:
            principles_html += f'<div class="principle-item" style="opacity: 0.7;">💡 {p}</div>'

        html += f"""
        <div class="qkv-panel" style="border-style: dashed; opacity: 0.8;">
            <h3 class="panel-title" style="color: #94a3b8;">
                <span class="icon">🔒</span>
                <span>{p_name}</span>
                <span style="font-size: 11px; color: #64748b; margin-left: auto;">待实现</span>
            </h3>
            <div style="font-size: 13px; color: #94a3b8; margin-bottom: 10px;">{p_desc}</div>
            <div style="margin-bottom: 10px;">
                <div style="font-size: 11px; color: #64748b; margin-bottom: 5px;">核心理念:</div>
                {principles_html}
            </div>
            <div style="font-size: 11px; color: #f59e0b;">
                待实现策略: {strategies_str}
            </div>
        </div>
        """
    html += '</div>'
    return html


def _render_value_weights(weights: Dict) -> str:
    """渲染价值观权重"""
    if not weights:
        return '<div style="color: #64748b; font-size: 12px;">暂无数据</div>'

    items = [
        ("价格敏感度", weights.get("price_sensitivity", 0.5), "#00d4ff"),
        ("成交量敏感度", weights.get("volume_sensitivity", 0.5), "#4ade80"),
        ("情绪关注度", weights.get("sentiment_weight", 0.3), "#f472b6"),
        ("流动性关注", weights.get("liquidity_weight", 0.4), "#a855f7"),
        ("基本面权重", weights.get("fundamentals_weight", 0.3), "#fbbf24"),
    ]

    html = ""
    for name, value, color in items:
        bar_width = min(value * 100, 100)
        html += f"""
        <div class="weight-bar">
            <div class="weight-bar-label">
                <span style="color: #fff;">{name}</span>
                <span style="color: {color};">{value:.2f}</span>
            </div>
            <div class="weight-bar-track">
                <div class="weight-bar-fill" style="width: {bar_width}%; background: {color};"></div>
            </div>
        </div>
        """
    return html


def _render_value_preferences(preferences: Dict) -> str:
    """渲染价值观偏好"""
    if not preferences:
        return '<div style="color: #64748b; font-size: 12px;">暂无数据</div>'

    risk_level = preferences.get("risk_level", "中性")
    time_label = preferences.get("time_label", "中期")
    concentration_label = preferences.get("concentration_label", "均衡")

    risk_preference = preferences.get("risk_preference", 0.5)
    time_horizon = preferences.get("time_horizon", 0.5)
    concentration = preferences.get("concentration", 0.5)

    return f"""
    <div class="stat-row">
        <span class="stat-label">风险偏好</span>
        <span class="stat-value" style="color: #fbbf24;">{risk_level} ({risk_preference:.2f})</span>
    </div>
    <div class="stat-row">
        <span class="stat-label">时间视野</span>
        <span class="stat-value" style="color: #60a5fa;">{time_label} ({time_horizon:.2f})</span>
    </div>
    <div class="stat-row">
        <span class="stat-label">集中度</span>
        <span class="stat-value" style="color: #a855f7;">{concentration_label} ({concentration:.2f})</span>
    </div>
    """


def _render_principles(value_type: str) -> str:
    """渲染核心理念"""
    principles_map = {
        "trend": ["趋势一旦形成，不会轻易改变", "不要逆势而行", "让利润奔跑"],
        "contrarian": ["极端行情是逆向投资者的机会", "均值终将回归", "分歧产生机会"],
        "value": ["价格终将回归价值", "不要追高", "安全边际是第一原则"],
        "momentum": ["强者恒强，弱者恒弱", "趋势延续直到反转信号出现", "不要猜顶底"],
        "liquidity": ["资金流向决定价格方向", "放量突破是真突破", "缩量下跌可能见底"],
        "balanced": ["多元分散，降低风险", "趋势跟随 + 价值兜底", "动态平衡"],
    }

    principles = principles_map.get(value_type, ["均衡配置，分散风险"])

    html = ""
    for p in principles:
        html += f'<div class="principle-item">💡 {p}</div>'

    return html


def _render_explain_tab(query: Dict, events: List, values: Dict) -> str:
    """渲染注意力解释Tab"""
    recent_attentions = values.get("recent_attentions", [])

    if not recent_attentions:
        events_html = ""
        for event in events[:5]:
            features = event.get("features", {})
            if isinstance(features, dict):
                price_change = features.get("price_change", 0)
                volume_spike = features.get("volume_spike", 1)
                score = event.get("score", 0)
                source = event.get("source", "market")

                events_html += f"""
                <div class="attention-explain-card">
                    <div class="attention-explain-header">
                        <span class="attention-symbol">📈 {source.upper()}</span>
                        <span class="attention-score">score: {score:.3f}</span>
                    </div>
                    <div class="attention-reason">
                        价格变化 <strong>{price_change:+.2f}%</strong>，
                        成交量 <strong>{volume_spike:.1f}倍</strong>，
                        匹配度 <strong>{score:.2f}</strong>
                    </div>
                </div>
                """

        if not events_html:
            events_html = '''
            <div class="empty-state">
                <div class="icon">📭</div>
                <div>暂无注意力事件</div>
                <div style="font-size: 12px; margin-top: 5px;">等待市场事件流入...</div>
            </div>
            '''
    else:
        events_html = ""
        for att in recent_attentions:
            symbol = att.get("symbol", "unknown")
            score = att.get("score", 0)
            reason = att.get("reason", "")
            events_html += f"""
            <div class="attention-explain-card">
                <div class="attention-explain-header">
                    <span class="attention-symbol">🎯 {symbol}</span>
                    <span class="attention-score">匹配度: {score:.3f}</span>
                </div>
                <div class="attention-reason">{reason}</div>
            </div>
            """

    active_type_display = values.get("active_type_display", "趋势追踪")

    return f"""
    <div class="qkv-grid-full">
        <div class="qkv-panel qkv-panel-explain">
            <h3 class="panel-title">
                <span class="icon">💭</span>
                <span>注意力焦点解释 - 当前价值观：{active_type_display}</span>
            </h3>
            <div style="font-size: 13px; color: #94a3b8; margin-bottom: 15px;">
                解释为什么系统关注这些事件，以及它们与当前价值观的匹配程度
            </div>
            {events_html}
        </div>
    </div>
    """


def _render_evolution_tab(values: Dict) -> str:
    """渲染价值观演进Tab"""
    performances = values.get("performances", {})
    suggestions = values.get("suggestions", [])

    evolution_bars = ""
    if performances:
        sorted_perfs = sorted(performances.items(), key=lambda x: x[1].get("avg_return", 0), reverse=True)
        for value_type, perf in sorted_perfs:
            avg_return = perf.get("avg_return", 0)
            total_trades = perf.get("total_trades", 0)
            confidence = perf.get("confidence", 0)

            display_names = {
                "trend": "趋势追踪",
                "contrarian": "逆向投资",
                "value": "价值投资",
                "momentum": "动量策略",
                "liquidity": "流动性猎人",
                "balanced": "均衡配置",
            }
            name = display_names.get(value_type, value_type)

            is_positive = avg_return > 0
            return_class = "positive" if is_positive else "negative"
            bar_color = "#4ade80" if is_positive else "#f87171"
            bar_width = min(abs(avg_return) * 5, 100)

            evolution_bars += f"""
            <div class="evolution-bar">
                <div class="evolution-bar-header">
                    <span class="evolution-name">{name}</span>
                    <span class="evolution-return {return_class}">{avg_return:+.2f}% ({total_trades}笔)</span>
                </div>
                <div class="evolution-track">
                    <div class="evolution-fill" style="width: {bar_width}%; background: {bar_color};"></div>
                </div>
            </div>
            """
    else:
        evolution_bars = '''
        <div class="empty-state">
            <div class="icon">📊</div>
            <div>暂无表现数据</div>
            <div style="font-size: 12px; margin-top: 5px;">运行一段时间后会自动统计</div>
        </div>
        '''

    suggestions_html = ""
    if suggestions:
        for sug in suggestions:
            emoji = "📈" if "增配" in sug else ("⚠️" if "减配" in sug else "➡️")
            suggestions_html += f'''
            <div class="suggestion-card">
                <span class="emoji">{emoji}</span> {sug}
            </div>
            '''
    else:
        suggestions_html = '''
        <div class="suggestion-card">
            <span class="emoji">⏳</span> 积累更多交易数据后提供建议
        </div>
        '''

    return f"""
    <div class="qkv-grid-2col">
        <div class="qkv-panel qkv-panel-evolution">
            <h3 class="panel-title">
                <span class="icon">📈</span>
                <span>价值观表现</span>
            </h3>
            <div style="font-size: 13px; color: #94a3b8; margin-bottom: 15px;">
                各价值观近期的平均收益表现
            </div>
            {evolution_bars}
        </div>

        <div class="qkv-panel qkv-panel-evolution">
            <h3 class="panel-title">
                <span class="icon">💡</span>
                <span>系统建议</span>
            </h3>
            <div style="font-size: 13px; color: #94a3b8; margin-bottom: 15px;">
                基于当前表现数据给出的调整建议
            </div>
            {suggestions_html}
        </div>
    </div>
    """


def _render_liquidity_rescue_panel(rescue_state: Dict = None) -> str:
    """渲染流动性救援监测面板"""
    if rescue_state is None:
        rescue_state = {}

    state = rescue_state.get("current_state", {}) or {}
    recommended_action = rescue_state.get("recommended_action", "watch")
    panic_detector = rescue_state.get("panic_detector", {})
    crisis_tracker = rescue_state.get("crisis_tracker", {})
    recovery_monitor = rescue_state.get("recovery_monitor", {})

    level = state.get("level", "normal") if isinstance(state, dict) else "normal"
    panic_score = state.get("panic_score", 0) if isinstance(state, dict) else 0
    liquidity_score = state.get("liquidity_score", 1.0) if isinstance(state, dict) else 1.0

    level_colors = {
        "normal": "#4ade80",
        "warning": "#fbbf24",
        "opportunity": "#f59e0b",
        "peak": "#f97316",
        "crisis": "#ef4444",
        "recovery": "#06b6d4",
    }
    level_color = level_colors.get(level, "#94a3b8")

    level_names = {
        "normal": "正常",
        "warning": "预警",
        "opportunity": "机会",
        "peak": "恐慌极点",
        "crisis": "危机",
        "recovery": "恢复中",
    }
    level_name = level_names.get(level, level)

    action_icons = {
        "watch": "👁️",
        "rescue": "🚨",
        "confirm_rescue": "✅",
        "prepare_rescue": "📊",
        "hold": "⏸️",
        "exit": "💰",
        "prepare_exit": "📤",
    }
    action_icon = action_icons.get(recommended_action, "👁️")

    panic_trend = panic_detector.get("trend", "unknown") if panic_detector else "unknown"
    crisis_level = crisis_tracker.get("current_crisis_level", 0) if crisis_tracker else 0
    consecutive_recoveries = recovery_monitor.get("consecutive_recoveries", 0) if recovery_monitor else 0

    return f"""
    <div class="qkv-panel" style="border-left: 3px solid {level_color};">
        <h3 class="panel-title" style="color: {level_color};">
            <span class="icon">🚨</span>
            <span>流动性救援监测</span>
            <span style="font-size: 11px; background: {level_color}20; padding: 2px 8px; border-radius: 10px; margin-left: auto;">
                {level_name}
            </span>
        </h3>

        <div class="qkv-grid-2col" style="gap: 15px;">
            <div>
                <div style="font-size: 12px; color: #94a3b8; margin-bottom: 5px;">恐慌指数</div>
                <div style="display: flex; align-items: center; gap: 10px;">
                    <span style="font-size: 28px; font-weight: 600; color: {level_color};">{panic_score:.0f}</span>
                    <span style="font-size: 11px; color: #64748b;">{panic_trend}</span>
                </div>
                <div style="font-size: 11px; color: #64748b; margin-top: 5px;">
                    流动性得分: {liquidity_score:.2f}
                </div>
            </div>

            <div>
                <div style="font-size: 12px; color: #94a3b8; margin-bottom: 5px;">推荐操作</div>
                <div style="display: flex; align-items: center; gap: 10px;">
                    <span style="font-size: 28px;">{action_icon}</span>
                    <span style="font-size: 14px; color: #fff; font-weight: 500;">{recommended_action.upper()}</span>
                </div>
            </div>
        </div>

        <div style="margin-top: 15px; padding: 10px; background: rgba(255,255,255,0.03); border-radius: 8px;">
            <div style="font-size: 11px; color: #64748b; margin-bottom: 8px;">危机追踪</div>
            <div style="display: flex; gap: 15px; font-size: 12px;">
                <div>
                    <span style="color: #94a3b8;">危机等级:</span>
                    <span style="color: #fff; margin-left: 5px;">{crisis_level:.2f}</span>
                </div>
                <div>
                    <span style="color: #94a3b8;">连续恢复:</span>
                    <span style="color: #fff; margin-left: 5px;">{consecutive_recoveries}次</span>
                </div>
            </div>
        </div>

        <div style="margin-top: 10px;">
            <div style="font-size: 11px; color: #64748b; margin-bottom: 8px;">漏斗状态</div>
            <div style="display: flex; gap: 5px;">
                <div style="flex: 1; height: 6px; background: #22c55e; border-radius: 3px; opacity: 0.3;"></div>
                <div style="flex: 1; height: 6px; background: #eab308; border-radius: 3px; opacity: 0.3;"></div>
                <div style="flex: 1; height: 6px; background: #f97316; border-radius: 3px; opacity: {1.0 if level in ['peak', 'crisis'] else 0.3};"></div>
                <div style="flex: 1; height: 6px; background: #ef4444; border-radius: 3px; opacity: {1.0 if level == 'crisis' else 0.3};"></div>
            </div>
            <div style="display: flex; justify-content: space-between; font-size: 10px; color: #64748b; margin-top: 3px;">
                <span>预过滤</span><span>分析</span><span>极点</span><span>危机</span>
            </div>
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
                Query(价值观) 决定"关注什么"，Key(事件) 描述"是什么"，Value(价值) 包含"值多少"。
                价值观不同，同样的事件计算出不同的价值。
            </div>
        </div>
    </div>
    """


__all__ = ["render_qkv_page", "get_qkv_data"]
