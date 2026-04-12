"""全局自动调优监控视图 - 实时展示各模块的自动调优状态及工作频率

功能:
1. 模块状态总览 - 以直观可视化方式展示系统内所有模块的当前活跃状态
2. 频率监控 - 实时显示每个模块的当前工作频率数值及单位
3. 调优状态指示 - 明确标识各模块是处于降频状态、升频状态还是维持稳定状态
4. 系统流转可视化 - 通过流程图或动态连接线展示模块间的交互关系及数据流转路径
5. 状态变化记录 - 显示各模块最近一次调优操作的时间、类型及幅度
"""

from typing import Dict, List, Any, Optional
import time
from deva.naja.register import SR

_cached_module_status = None
_cached_module_status_time = 0
_cache_ttl = 2.0


def _fmt_ts(ts: float) -> str:
    if not ts:
        return "-"
    try:
        from datetime import datetime
        dt = datetime.fromtimestamp(ts)
        return dt.strftime("%H:%M:%S")
    except Exception:
        return "-"


def _fmt_ts_full(ts: float) -> str:
    if not ts:
        return "-"
    try:
        from datetime import datetime
        dt = datetime.fromtimestamp(ts)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(ts)


def _fmt_interval(seconds: float) -> str:
    if seconds is None:
        return "-"
    if seconds >= 60:
        return f"{seconds/60:.1f}min"
    elif seconds >= 1:
        return f"{seconds:.1f}s"
    else:
        return f"{seconds*1000:.0f}ms"


class TuningState:
    UP = "up"
    DOWN = "down"
    STABLE = "stable"


def _get_tuning_state(before_val, after_val) -> str:
    if before_val is None or after_val is None:
        return TuningState.STABLE
    try:
        before = float(before_val)
        after = float(after_val)
        if after > before:
            return TuningState.UP
        elif after < before:
            return TuningState.DOWN
        else:
            return TuningState.STABLE
    except (ValueError, TypeError):
        return TuningState.STABLE


def _get_state_color(state: str) -> str:
    if state == TuningState.UP:
        return "#4ade80"
    elif state == TuningState.DOWN:
        return "#f87171"
    return "#60a5fa"


def _get_state_icon(state: str) -> str:
    if state == TuningState.UP:
        return "📈"
    elif state == TuningState.DOWN:
        return "📉"
    return "➡️"


CATEGORY_DISPLAY_NAMES = {
    'system_overload': '系统过载',
    'performance_degradation': '性能下降',
    'resource_exhaustion': '资源耗尽',
    'error_spike': '错误飙升',
    'resource_conservation': '资源节约',
    'performance_good': '性能良好',
    'manual': '手动触发',
}

PARAM_DISPLAY_NAMES = {
    'thread_pool': '线程池',
    'thread_pool_rejected': '任务队列',
    'memory': '内存',
    'strategy_performance': '策略性能',
    'lock_contention': '锁竞争',
    'datasource_delay': '数据源延迟',
    'cache_hit_rate': '缓存命中率',
    'datasource_error_rate': '数据源错误率',
    'replay_processing': '回放处理',
    'pytorch_error_rate': 'PyTorch错误率',
    'memory_pressure': '内存压力',
    'upstream_inactive': '上游不活跃',
    'manual_tune': '手动调优',
}


def get_all_module_status() -> List[Dict]:
    global _cached_module_status, _cached_module_status_time
    now = time.time()

    if _cached_module_status is not None and (now - _cached_module_status_time) < _cache_ttl:
        return _cached_module_status

    modules = []
    _cached_events = None

    try:
        from deva.naja.infra.observability.auto_tuner import get_auto_tuner
        tuner = get_auto_tuner()
        tuner._ensure_initialized()
        conditions = tuner.get_conditions_status()
        _cached_events = tuner.get_recent_events(limit=100)

        for cond in conditions:
            name = cond['name']
            trigger_count = cond['trigger_count']
            last_trigger = cond['last_trigger_ts']

            state = TuningState.STABLE
            if trigger_count > 0 and _cached_events:
                for evt in _cached_events:
                    if evt['param'] == name:
                        state = _get_tuning_state(evt.get('before'), evt.get('after'))
                        break

            modules.append({
                'id': name,
                'name': PARAM_DISPLAY_NAMES.get(name, name),
                'category': cond.get('action', ''),
                'state': state,
                'trigger_count': trigger_count,
                'last_trigger_ts': last_trigger,
                'threshold': cond.get('threshold'),
                'cooldown': cond.get('cooldown'),
                'active': trigger_count > 0 and (now - last_trigger) < 300,
            })
    except Exception:
        pass

    try:
        from deva.naja.market_hotspot.scheduling.frequency_scheduler import FrequencyScheduler, FrequencyLevel
        from deva.naja.market_hotspot.integration import get_market_hotspot_integration

        integration = get_market_hotspot_integration()
        if integration and integration.hotspot_system:
            fs = integration.hotspot_system.frequency_scheduler
            if fs:
                summary = fs.get_schedule_summary()
                modules.append({
                    'id': 'frequency_scheduler',
                    'name': '频率调度器',
                    'category': 'scheduling',
                    'state': TuningState.STABLE,
                    'high_freq': summary.get('high_frequency', 0),
                    'medium_freq': summary.get('medium_frequency', 0),
                    'low_freq': summary.get('low_frequency', 0),
                    'total_switches': summary.get('total_switches', 0),
                    'trigger_count': summary.get('total_switches', 0),
                    'last_trigger_ts': summary.get('last_schedule', 0),
                    'active': True,
                })

            afc = integration.hotspot_system.adaptive_freq_controller
            if afc:
                config = afc.get_config()
                modules.append({
                    'id': 'adaptive_frequency',
                    'name': '自适应频率',
                    'category': 'scheduling',
                    'state': TuningState.STABLE,
                    'low_interval': config.low_interval,
                    'medium_interval': config.medium_interval,
                    'high_interval': config.high_interval,
                    'trigger_count': 0,
                    'last_trigger_ts': 0,
                    'active': True,
                })
    except Exception:
        pass

    try:
        from deva.naja.datasource import get_datasource_manager
        mgr = get_datasource_manager()
        if mgr:
            datasources = mgr.list_all()
            running_count = 0
            error_count = 0
            total_interval = 0
            count = 0

            for ds in datasources:
                state = getattr(ds, '_state', None)
                if state:
                    status_val = getattr(state, 'status', 0)
                    if status_val == 2:
                        running_count += 1
                    run_c = getattr(state, 'run_count', 0)
                    err_c = getattr(state, 'error_count', 0)
                    if run_c > 0 and err_c > 0:
                        error_count += 1
                interval = getattr(ds._metadata, 'interval', 5.0) if hasattr(ds, '_metadata') else 5.0
                total_interval += interval
                count += 1

            avg_interval = total_interval / count if count > 0 else 5.0

            modules.append({
                'id': 'datasource_manager',
                'name': '数据源管理',
                'category': 'datasource',
                'state': TuningState.STABLE,
                'running_count': running_count,
                'total_count': len(datasources),
                'error_count': error_count,
                'avg_interval': avg_interval,
                'trigger_count': error_count,
                'last_trigger_ts': 0,
                'active': running_count > 0,
            })
    except Exception:
        pass

    try:
        from deva.naja.strategy import get_strategy_manager
        mgr = get_strategy_manager()
        if mgr:
            strategies = mgr.list_all() if hasattr(mgr, 'list_all') else []
            active_count = sum(1 for s in strategies if getattr(s, 'enabled', False))

            modules.append({
                'id': 'strategy_manager',
                'name': '策略管理',
                'category': 'strategy',
                'state': TuningState.STABLE,
                'active_count': active_count,
                'total_count': len(strategies),
                'trigger_count': 0,
                'last_trigger_ts': 0,
                'active': active_count > 0,
            })
    except Exception:
        pass

    try:
        from deva.naja.bandit.market_observer import get_market_observer

        listener = SR('signal_listener')
        if listener:
            modules.append({
                'id': 'signal_listener',
                'name': '信号监听器',
                'category': 'bandit',
                'state': TuningState.STABLE,
                'running': getattr(listener, '_running', False),
                'poll_interval': getattr(listener, '_poll_interval', 5.0),
                'trigger_count': 0,
                'last_trigger_ts': 0,
                'active': getattr(listener, '_running', False),
            })

        observer = get_market_observer()
        if observer:
            modules.append({
                'id': 'market_observer',
                'name': '市场观察器',
                'category': 'bandit',
                'state': TuningState.STABLE,
                'running': getattr(observer, '_running', False),
                'fetch_interval': getattr(observer, '_fetch_interval', 5.0),
                'trigger_count': 0,
                'last_trigger_ts': 0,
                'active': getattr(observer, '_running', False),
            })
    except Exception:
        pass

    try:
        from deva.naja.attention.orchestration.trading_center import get_trading_center
        orchestrator = get_trading_center()
        if orchestrator:
            stats = orchestrator.get_stats()
            modules.append({
                'id': 'attention_orchestrator',
                'name': '注意力编排器',
                'category': 'attention',
                'state': TuningState.STABLE,
                'processed_frames': stats.get('processed_frames', 0),
                'global_attention': stats.get('global_attention', 0),
                'high_attention_count': stats.get('high_attention_count', 0),
                'trigger_count': 0,
                'last_trigger_ts': 0,
                'active': stats.get('processed_frames', 0) > 0,
            })
    except Exception:
        pass

    _cached_module_status = modules
    _cached_module_status_time = now
    return modules


def get_recent_tuning_events(limit: int = 20) -> List[Dict]:
    try:
        from deva.naja.infra.observability.auto_tuner import get_auto_tuner
        tuner = get_auto_tuner()
        tuner._ensure_initialized()
        events = tuner.get_recent_events(limit=limit)

        processed_events = []
        for evt in events:
            state = _get_tuning_state(evt.get('before'), evt.get('after'))
            processed_events.append({
                'timestamp': evt.get('timestamp', 0),
                'param': evt.get('param', ''),
                'param_name': PARAM_DISPLAY_NAMES.get(evt.get('param', ''), evt.get('param', '')),
                'before': evt.get('before'),
                'after': evt.get('after'),
                'reason': evt.get('reason', ''),
                'action': evt.get('action', ''),
                'category': CATEGORY_DISPLAY_NAMES.get(evt.get('category', ''), evt.get('category', '')),
                'explanation': evt.get('explanation', ''),
                'impact': evt.get('impact', ''),
                'llm_suggestion': evt.get('llm_suggestion', ''),
                'success': evt.get('success', True),
                'triggered_by_llm': evt.get('triggered_by_llm', False),
                'state': state,
            })
        return processed_events
    except Exception:
        return []


def get_module_flow_diagram() -> str:
    nodes = [
        {"id": "datasource", "name": "📡 数据源", "color": "#60a5fa", "y": 0},
        {"id": "signal_listener", "name": "👂 信号监听", "color": "#a855f7", "y": 1},
        {"id": "market_observer", "name": "📊 市场观察", "color": "#8b5cf6", "y": 1},
        {"id": "attention", "name": "👁️ 注意力", "color": "#14b8a6", "y": 2},
        {"id": "frequency", "name": "⏱️ 频率调度", "color": "#f97316", "y": 2},
        {"id": "strategies", "name": "🎯 策略", "color": "#ec4899", "y": 3},
        {"id": "auto_tuner", "name": "⚙️ 自动调优", "color": "#64748b", "y": 4},
        {"id": "output", "name": "📤 输出", "color": "#22c55e", "y": 5},
    ]

    links = [
        {"from": "datasource", "to": "signal_listener"},
        {"from": "datasource", "to": "market_observer"},
        {"from": "signal_listener", "to": "attention"},
        {"from": "market_observer", "to": "attention"},
        {"from": "attention", "to": "frequency"},
        {"from": "attention", "to": "strategies"},
        {"from": "frequency", "to": "strategies"},
        {"from": "strategies", "to": "auto_tuner"},
        {"from": "auto_tuner", "to": "datasource"},
        {"from": "strategies", "to": "output"},
    ]

    return {"nodes": nodes, "links": links}


def render_tuning_monitor_panel() -> str:
    modules = get_all_module_status()
    events = get_recent_tuning_events(limit=10)
    flow = get_module_flow_diagram()

    tuner_status_html = _render_tuner_status()
    modules_html = _render_modules_grid(modules)
    flow_html = _render_flow_diagram(flow)
    events_html = _render_events_list(events)

    return f"""
    <div style="
        margin-bottom: 12px;
        background: rgba(255,255,255,0.03);
        border-radius: 12px;
        padding: 14px 18px;
        border: 1px solid rgba(255,255,255,0.08);
    ">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
            <div style="font-size: 14px; font-weight: 600; color: #6366f1;">
                🎛️ 全局自动调优监控
            </div>
            <div style="font-size: 10px; color: #64748b;">
                实时监控 | 智能调优
            </div>
        </div>

        {tuner_status_html}

        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 12px;">
            <div>
                <div style="font-size: 11px; font-weight: 600; color: #64748b; margin-bottom: 8px;">
                    📊 模块状态总览
                </div>
                {modules_html}
            </div>
            <div>
                <div style="font-size: 11px; font-weight: 600; color: #64748b; margin-bottom: 8px;">
                    🔄 系统流转
                </div>
                {flow_html}
            </div>
        </div>

        <div style="margin-top: 12px;">
            <div style="font-size: 11px; font-weight: 600; color: #64748b; margin-bottom: 8px;">
                📋 状态变化记录
            </div>
            {events_html}
        </div>
    </div>
    """


def _render_tuner_status() -> str:
    try:
        from deva.naja.infra.observability.auto_tuner import get_auto_tuner
        tuner = get_auto_tuner()
        tuner._ensure_initialized()
        status = tuner.get_status()

        enabled = status.get('enabled', False)
        running = status.get('running', False)
        conditions_count = status.get('conditions_count', 0)
        events_count = status.get('events_count', 0)
        active_conditions = status.get('active_conditions', 0)

        status_color = "#4ade80" if running else "#f87171"
        status_text = "🟢 运行中" if running else "🔴 已停止"
        enabled_text = "✅ 已启用" if enabled else "❌ 已禁用"

    except Exception:
        status_color = "#64748b"
        status_text = "🔴 未连接"
        enabled_text = "❌ 未启用"
        conditions_count = 0
        events_count = 0
        active_conditions = 0

    return f"""
    <div style="display: grid; grid-template-columns: repeat(5, 1fr); gap: 8px;">
        <div style="text-align: center; padding: 8px; background: rgba(99,102,241,0.1); border-radius: 6px;">
            <div style="font-size: 16px; font-weight: 700; color: #6366f1;">{conditions_count}</div>
            <div style="font-size: 9px; color: #64748b;">监控条件</div>
        </div>
        <div style="text-align: center; padding: 8px; background: rgba(74,222,128,0.1); border-radius: 6px;">
            <div style="font-size: 16px; font-weight: 700; color: #4ade80;">{events_count}</div>
            <div style="font-size: 9px; color: #64748b;">调优事件</div>
        </div>
        <div style="text-align: center; padding: 8px; background: rgba(251,146,60,0.1); border-radius: 6px;">
            <div style="font-size: 16px; font-weight: 700; color: #fb923c;">{active_conditions}</div>
            <div style="font-size: 9px; color: #64748b;">活跃条件</div>
        </div>
        <div style="text-align: center; padding: 8px; background: rgba(255,255,255,0.05); border-radius: 6px;">
            <div style="font-size: 11px; font-weight: 600; color: {status_color};">{status_text}</div>
            <div style="font-size: 9px; color: #64748b;">运行状态</div>
        </div>
        <div style="text-align: center; padding: 8px; background: rgba(255,255,255,0.05); border-radius: 6px;">
            <div style="font-size: 11px; font-weight: 600; color: #60a5fa;">{enabled_text}</div>
            <div style="font-size: 9px; color: #64748b;">启用状态</div>
        </div>
    </div>
    """


def _render_modules_grid(modules: List[Dict]) -> str:
    if not modules:
        return '<div style="color: #64748b; font-size: 10px; text-align: center; padding: 20px;">暂无模块数据</div>'

    items_html = ""
    for mod in modules[:12]:
        mod_id = mod.get('id', '')
        name = mod.get('name', mod_id)
        state = mod.get('state', TuningState.STABLE)
        state_color = _get_state_color(state)
        state_icon = _get_state_icon(state)
        active = mod.get('active', False)
        category = mod.get('category', '')

        extra_info = ""
        if 'high_freq' in mod:
            extra_info = f"<span style='color:#ef4444'>高{mod.get('high_freq',0)}</span> <span style='color:#f97316'>中{mod.get('medium_freq',0)}</span> <span style='color:#22c55e'>低{mod.get('low_freq',0)}</span>"
        elif 'running_count' in mod:
            extra_info = f"<span style='color:#4ade80'>{mod.get('running_count',0)}</span>/{mod.get('total_count',0)}"
        elif 'active_count' in mod:
            extra_info = f"<span style='color:#4ade80'>{mod.get('active_count',0)}</span>/{mod.get('total_count',0)}"
        elif 'poll_interval' in mod:
            extra_info = f"间隔: {_fmt_interval(mod.get('poll_interval', 0))}"
        elif 'fetch_interval' in mod:
            extra_info = f"间隔: {_fmt_interval(mod.get('fetch_interval', 0))}"
        elif 'low_interval' in mod:
            extra_info = f"高:{_fmt_interval(mod.get('high_interval',1))} 中:{_fmt_interval(mod.get('medium_interval',10))} 低:{_fmt_interval(mod.get('low_interval',60))}"
        elif 'global_attention' in mod:
            ga = mod.get('global_attention', 0)
            extra_info = f"注意力: <span style='color:{'#4ade80' if ga > 0.6 else '#fb923c' if ga > 0.3 else '#64748b'}'>{ga:.3f}</span>"

        trigger_count = mod.get('trigger_count', 0)
        last_trigger = mod.get('last_trigger_ts', 0)
        last_str = _fmt_ts(last_trigger) if last_trigger else "-"

        active_dot = "🟢" if active else "⚪"

        items_html += f"""
        <div style="
            padding: 8px;
            background: rgba(255,255,255,0.03);
            border-radius: 6px;
            border-left: 3px solid {state_color};
            margin-bottom: 4px;
        ">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div style="display: flex; align-items: center; gap: 4px;">
                    {active_dot}
                    <span style="font-size: 10px; font-weight: 600; color: #e2e8f0;">{name}</span>
                </div>
                <div style="font-size: 10px; color: {state_color};">
                    {state_icon} {'升频' if state == TuningState.UP else '降频' if state == TuningState.DOWN else '稳定'}
                </div>
            </div>
            <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 4px;">
                <div style="font-size: 9px; color: #64748b;">{extra_info}</div>
                <div style="font-size: 8px; color: #475569;">{last_str} | {trigger_count}次</div>
            </div>
        </div>
        """

    return items_html


def _render_flow_diagram(flow: Dict) -> str:
    nodes = flow.get('nodes', [])
    links = flow.get('links', [])

    if not nodes:
        return '<div style="color: #64748b; font-size: 10px; text-align: center;">暂无流程数据</div>'

    node_map = {n['id']: n for n in nodes}

    lanes = {}
    for node in nodes:
        y = node.get('y', 0)
        if y not in lanes:
            lanes[y] = []
        lanes[y].append(node)

    diagram_html = ""
    for y in sorted(lanes.keys()):
        lane_nodes = lanes[y]
        diagram_html += '<div style="display: flex; gap: 8px; justify-content: center; margin-bottom: 8px;">'
        for node in lane_nodes:
            node_id = node['id']
            name = node['name']
            color = node.get('color', '#64748b')

            connections = []
            for link in links:
                if link['from'] == node_id:
                    connections.append(f"→{link['to']}")
                elif link['to'] == node_id:
                    connections.append(f"{link['from']}→")

            conn_str = " ".join(connections[:3])

            diagram_html += f"""
            <div style="
                padding: 6px 10px;
                background: rgba(255,255,255,0.05);
                border-radius: 6px;
                border: 1px solid {color}40;
                text-align: center;
                min-width: 70px;
            ">
                <div style="font-size: 10px; color: {color}; font-weight: 600;">{name}</div>
                {f'<div style="font-size: 7px; color: #64748b; margin-top: 2px;">{conn_str}</div>' if conn_str else ''}
            </div>
            """
        diagram_html += '</div>'

        if y < max(lanes.keys()):
            diagram_html += '<div style="text-align: center; color: #475569; font-size: 8px; margin: -4px 0;">⬇️</div>'

    return f"""
    <div style="
        background: rgba(0,0,0,0.2);
        border-radius: 8px;
        padding: 10px;
        max-height: 200px;
        overflow-y: auto;
    ">
        {diagram_html}
    </div>
    """


def _render_events_list(events: List[Dict]) -> str:
    if not events:
        return '<div style="color: #64748b; font-size: 10px; text-align: center; padding: 15px;">暂无调优记录</div>'

    rows_html = ""
    for evt in events[:8]:
        timestamp = _fmt_ts_full(evt.get('timestamp', 0))
        param_name = evt.get('param_name', evt.get('param', ''))
        state = evt.get('state', TuningState.STABLE)
        state_color = _get_state_color(state)
        state_icon = _get_state_icon(state)
        before = evt.get('before')
        after = evt.get('after')
        reason = evt.get('reason', '')[:40]
        category = evt.get('category', '')
        triggered_by_llm = evt.get('triggered_by_llm', False)

        llm_tag = '<span style="background: rgba(168,85,247,0.2); color: #a855f7; padding: 1px 4px; border-radius: 3px; font-size: 7px;">LLM</span>' if triggered_by_llm else ''

        value_change = ""
        if before is not None and after is not None:
            value_change = f"<span style='color: {state_color}'>{before} → {after}</span>"
        elif after is not None:
            value_change = f"<span style='color: #60a5fa'>{after}</span>"

        rows_html += f"""
        <tr style="border-bottom: 1px solid rgba(255,255,255,0.05);">
            <td style="padding: 6px 4px; font-size: 9px; color: #64748b; white-space: nowrap;">{timestamp}</td>
            <td style="padding: 6px 4px; font-size: 9px; color: #e2e8f0;">{param_name}</td>
            <td style="padding: 6px 4px; font-size: 9px; color: {state_color};">{state_icon} {'升' if state == TuningState.UP else '降' if state == TuningState.DOWN else '稳'}</td>
            <td style="padding: 6px 4px; font-size: 9px; max-width: 120px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{value_change}</td>
            <td style="padding: 6px 4px; font-size: 8px; color: #475569; max-width: 150px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="{reason}">{reason}</td>
            <td style="padding: 6px 4px; font-size: 8px; color: #64748b;">{category}{llm_tag}</td>
        </tr>
        """

    return f"""
    <div style="
        background: rgba(0,0,0,0.2);
        border-radius: 8px;
        overflow: hidden;
    ">
        <table style="width: 100%; border-collapse: collapse; font-size: 10px;">
            <thead>
                <tr style="background: rgba(99,102,241,0.1);">
                    <th style="padding: 6px 4px; text-align: left; font-size: 9px; color: #6366f1;">时间</th>
                    <th style="padding: 6px 4px; text-align: left; font-size: 9px; color: #6366f1;">参数</th>
                    <th style="padding: 6px 4px; text-align: left; font-size: 9px; color: #6366f1;">状态</th>
                    <th style="padding: 6px 4px; text-align: left; font-size: 9px; color: #6366f1;">数值变化</th>
                    <th style="padding: 6px 4px; text-align: left; font-size: 9px; color: #6366f1;">原因</th>
                    <th style="padding: 6px 4px; text-align: left; font-size: 9px; color: #6366f1;">类别</th>
                </tr>
            </thead>
            <tbody>
                {rows_html}
            </tbody>
        </table>
    </div>
    """


def render_frequency_monitor_panel() -> str:
    try:
        from deva.naja.market_hotspot.scheduling.frequency_scheduler import FrequencyScheduler, FrequencyLevel
        from deva.naja.market_hotspot.integration import get_market_hotspot_integration

        integration = get_market_hotspot_integration()
        if not integration or not integration.hotspot_system:
            return _render_frequency_empty_state()

        fs = integration.hotspot_system.frequency_scheduler
        if not fs:
            return _render_frequency_empty_state()

        summary = fs.get_schedule_summary()
        high_count = summary.get('high_frequency', 0)
        medium_count = summary.get('medium_frequency', 0)
        low_count = summary.get('low_frequency', 0)
        total = high_count + medium_count + low_count

        afc = integration.hotspot_system.adaptive_freq_controller
        config = afc.get_config() if afc else None

        high_interval = config.high_interval if config else 1.0
        medium_interval = config.medium_interval if config else 10.0
        low_interval = config.low_interval if config else 60.0

        attention_config = integration.hotspot_system.frequency_scheduler.config if integration.hotspot_system.frequency_scheduler else None
        if attention_config:
            low_th = attention_config.low_threshold
            high_th = attention_config.high_threshold
        else:
            low_th = 1.0
            high_th = 2.5

    except Exception:
        return _render_frequency_empty_state()

    high_pct = (high_count / total * 100) if total > 0 else 0
    medium_pct = (medium_count / total * 100) if total > 0 else 0
    low_pct = (low_count / total * 100) if total > 0 else 0

    return f"""
    <div style="
        margin-bottom: 12px;
        background: rgba(255,255,255,0.03);
        border-radius: 12px;
        padding: 14px 18px;
        border: 1px solid rgba(255,255,255,0.08);
    ">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
            <div style="font-size: 13px; font-weight: 600; color: #f97316;">
                ⏱️ 频率监控
            </div>
            <div style="font-size: 9px; color: #64748b;">
                阈值: 低&lt;{low_th} | 高&gt;{high_th}
            </div>
        </div>

        <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 12px;">
            <div style="text-align: center; padding: 10px; background: rgba(239,68,68,0.1); border-radius: 8px; border-top: 3px solid #ef4444;">
                <div style="font-size: 20px; font-weight: 700; color: #ef4444;">{high_count}</div>
                <div style="font-size: 9px; color: #64748b;">高频 (1s)</div>
                <div style="font-size: 8px; color: #ef4444;">{high_pct:.1f}%</div>
            </div>
            <div style="text-align: center; padding: 10px; background: rgba(249,115,22,0.1); border-radius: 8px; border-top: 3px solid #f97316;">
                <div style="font-size: 20px; font-weight: 700; color: #f97316;">{medium_count}</div>
                <div style="font-size: 9px; color: #64748b;">中频 (10s)</div>
                <div style="font-size: 8px; color: #f97316;">{medium_pct:.1f}%</div>
            </div>
            <div style="text-align: center; padding: 10px; background: rgba(34,197,94,0.1); border-radius: 8px; border-top: 3px solid #22c55e;">
                <div style="font-size: 20px; font-weight: 700; color: #22c55e;">{low_count}</div>
                <div style="font-size: 9px; color: #64748b;">低频 (60s)</div>
                <div style="font-size: 8px; color: #22c55e;">{low_pct:.1f}%</div>
            </div>
        </div>

        <div style="background: rgba(0,0,0,0.2); border-radius: 6px; padding: 10px; margin-bottom: 10px;">
            <div style="font-size: 10px; color: #64748b; margin-bottom: 8px;">频率分布</div>
            <div style="display: flex; height: 12px; border-radius: 6px; overflow: hidden;">
                <div style="width: {high_pct}%; background: linear-gradient(90deg, #ef4444, #dc2626);"></div>
                <div style="width: {medium_pct}%; background: linear-gradient(90deg, #f97316, #ea580c);"></div>
                <div style="width: {low_pct}%; background: linear-gradient(90deg, #22c55e, #16a34a);"></div>
            </div>
        </div>

        <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; font-size: 9px;">
            <div style="text-align: center; padding: 6px; background: rgba(239,68,68,0.05); border-radius: 4px;">
                <div style="color: #ef4444; font-weight: 600;">{_fmt_interval(high_interval)}</div>
                <div style="color: #64748b;">高频间隔</div>
            </div>
            <div style="text-align: center; padding: 6px; background: rgba(249,115,22,0.05); border-radius: 4px;">
                <div style="color: #f97316; font-weight: 600;">{_fmt_interval(medium_interval)}</div>
                <div style="color: #64748b;">中频间隔</div>
            </div>
            <div style="text-align: center; padding: 6px; background: rgba(34,197,94,0.05); border-radius: 4px;">
                <div style="color: #22c55e; font-weight: 600;">{_fmt_interval(low_interval)}</div>
                <div style="color: #64748b;">低频间隔</div>
            </div>
        </div>
    </div>
    """


def _render_frequency_empty_state() -> str:
    try:
        from .common import get_market_phase_summary, get_ui_mode_context
        phase_summary = get_market_phase_summary()
        mode_ctx = get_ui_mode_context()
        cn_info = phase_summary.get('cn', {})
        us_info = phase_summary.get('us', {})

        def _format_market_line(label, info):
            phase_name = info.get('phase_name', '未知')
            next_phase = info.get('next_phase_name', '')
            next_time = info.get('next_change_time', '')
            if info.get('phase') == 'closed' and next_time:
                return f"{label}{phase_name} →{next_phase} {next_time}"
            return f"{label}{phase_name}"

        cn_line = _format_market_line("A股", cn_info)
        us_line = _format_market_line("美股", us_info)
        mode_label = mode_ctx.get('mode_label', '实盘模式')
        time_hint = mode_ctx.get('market_time_str', '') if mode_ctx.get('is_replay') else ''
        hint_text = f"将在交易时段自动启用（{cn_line} | {us_line} | {mode_label} {time_hint}）"
    except Exception:
        hint_text = "将在交易时段自动启用"

    return f"""
    <div style="
        margin-bottom: 12px;
        background: rgba(255,255,255,0.03);
        border-radius: 12px;
        padding: 14px 18px;
        border: 1px solid rgba(255,255,255,0.08);
    ">
        <div style="font-size: 13px; font-weight: 600; color: #f97316; margin-bottom: 10px;">
            ⏱️ 频率监控
        </div>
        <div style="text-align: center; padding: 30px; color: #64748b;">
            <div style="font-size: 11px;">频率调度系统未初始化</div>
            <div style="font-size: 9px; margin-top: 4px;">{hint_text}</div>
        </div>
    </div>
    """


def render_datasource_tuning_panel() -> str:
    try:
        from deva.naja.datasource import get_datasource_manager
        from deva.naja.infra.runtime.recoverable import UnitStatus

        mgr = get_datasource_manager()
        if not mgr:
            return _render_datasource_empty_state()

        datasources = mgr.list_all()
        running = []
        stopped = []
        error_list = []

        for ds in datasources:
            state = getattr(ds, '_state', None)
            if not state:
                stopped.append(ds)
                continue

            status_val = getattr(state, 'status', 0)
            if status_val != UnitStatus.RUNNING.value:
                stopped.append(ds)
                continue

            running.append(ds)

            run_count = getattr(state, 'run_count', 0)
            error_count = getattr(state, 'error_count', 0)
            if run_count >= 5 and error_count / run_count > 0.1:
                error_list.append({
                    'name': ds.name,
                    'error_rate': error_count / run_count,
                    'interval': getattr(ds._metadata, 'interval', 5.0) if hasattr(ds, '_metadata') else 5.0
                })

        running_count = len(running)
        total_count = len(datasources)
        error_count = len(error_list)

        top_errors = sorted(error_list, key=lambda x: x['error_rate'], reverse=True)[:5]

    except Exception:
        return _render_datasource_empty_state()

    error_rows = ""
    for err in top_errors:
        rate = err['error_rate'] * 100
        rate_color = "#ef4444" if rate > 30 else "#f97316" if rate > 10 else "#64748b"
        error_rows += f"""
        <tr>
            <td style="padding: 4px 6px; font-size: 9px; color: #e2e8f0;">{err['name'][:15]}</td>
            <td style="padding: 4px 6px; font-size: 9px; color: {rate_color};">{rate:.1f}%</td>
            <td style="padding: 4px 6px; font-size: 9px; color: #64748b;">{_fmt_interval(err['interval'])}</td>
        </tr>
        """

    if not error_rows:
        error_rows = '<tr><td colspan="3" style="padding: 10px; text-align: center; color: #64748b; font-size: 9px;">运行良好，无异常</td></tr>'

    return f"""
    <div style="
        margin-bottom: 12px;
        background: rgba(255,255,255,0.03);
        border-radius: 12px;
        padding: 14px 18px;
        border: 1px solid rgba(255,255,255,0.08);
    ">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
            <div style="font-size: 13px; font-weight: 600; color: #0ea5e9;">
                📡 数据源调优
            </div>
            <div style="font-size: 9px; color: #64748b;">
                <span style="color: #4ade80;">{running_count}</span> / {total_count} 运行中
            </div>
        </div>

        <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-bottom: 12px;">
            <div style="text-align: center; padding: 8px; background: rgba(74,222,128,0.1); border-radius: 6px;">
                <div style="font-size: 16px; font-weight: 700; color: #4ade80;">{running_count}</div>
                <div style="font-size: 8px; color: #64748b;">运行中</div>
            </div>
            <div style="text-align: center; padding: 8px; background: rgba(100,116,139,0.1); border-radius: 6px;">
                <div style="font-size: 16px; font-weight: 700; color: #64748b;">{total_count - running_count}</div>
                <div style="font-size: 8px; color: #64748b;">已停止</div>
            </div>
            <div style="text-align: center; padding: 8px; background: rgba(249,115,22,0.1); border-radius: 6px;">
                <div style="font-size: 16px; font-weight: 700; color: #f97316;">{error_count}</div>
                <div style="font-size: 8px; color: #64748b;">需调优</div>
            </div>
            <div style="text-align: center; padding: 8px; background: rgba(14,165,233,0.1); border-radius: 6px;">
                <div style="font-size: 16px; font-weight: 700; color: #0ea5e9;">{total_count}</div>
                <div style="font-size: 8px; color: #64748b;">总计</div>
            </div>
        </div>

        <div style="background: rgba(0,0,0,0.2); border-radius: 6px; overflow: hidden;">
            <div style="font-size: 10px; color: #64748b; padding: 6px 8px; background: rgba(249,115,22,0.1);">
                ⚠️ 需要调优的数据源
            </div>
            <table style="width: 100%; border-collapse: collapse;">
                <thead>
                    <tr style="background: rgba(255,255,255,0.03);">
                        <th style="padding: 4px 6px; text-align: left; font-size: 8px; color: #64748b;">名称</th>
                        <th style="padding: 4px 6px; text-align: right; font-size: 8px; color: #64748b;">错误率</th>
                        <th style="padding: 4px 6px; text-align: right; font-size: 8px; color: #64748b;">间隔</th>
                    </tr>
                </thead>
                <tbody>
                    {error_rows}
                </tbody>
            </table>
        </div>
    </div>
    """


def _render_datasource_empty_state() -> str:
    return """
    <div style="
        margin-bottom: 12px;
        background: rgba(255,255,255,0.03);
        border-radius: 12px;
        padding: 14px 18px;
        border: 1px solid rgba(255,255,255,0.08);
    ">
        <div style="font-size: 13px; font-weight: 600; color: #0ea5e9; margin-bottom: 10px;">
            📡 数据源调优
        </div>
        <div style="text-align: center; padding: 20px; color: #64748b;">
            <div style="font-size: 10px;">数据源管理系统未初始化</div>
        </div>
    </div>
    """
