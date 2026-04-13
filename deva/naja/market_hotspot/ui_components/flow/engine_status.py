"""热点系统流式 UI - 策略状态与双引擎面板"""

import logging

log = logging.getLogger(__name__)

from ._helpers import _fmt_ts


def render_strategy_status_panel() -> str:
    """渲染策略状态面板"""
    try:
        from deva.naja.market_hotspot.strategies import get_strategy_manager
        from ..common import get_market_phase_summary, get_ui_mode_context

        manager = get_strategy_manager()
        if not manager:
            return ""

        mode_ctx = get_ui_mode_context()
        phase_summary = get_market_phase_summary()
        cn_active = phase_summary.get('cn', {}).get('active', False)
        us_active = phase_summary.get('us', {}).get('active', False)
        if mode_ctx.get('is_replay'):
            current_market = "REPLAY"
        elif cn_active and us_active:
            current_market = "ALL"
        elif us_active:
            current_market = "US"
        elif cn_active:
            current_market = "CN"
        else:
            current_market = "CN"

        all_stats = manager.get_all_stats() if hasattr(manager, 'get_all_stats') else {}
        strategies = manager.strategies if hasattr(manager, 'strategies') else {}
        configs = manager.configs if hasattr(manager, 'configs') else {}

        total_strategies = len(strategies)
        if configs:
            active_strategies = sum(1 for c in configs.values() if getattr(c, 'enabled', False))
        else:
            active_strategies = sum(1 for s in strategies.values() if getattr(s, 'is_active', False))

        if current_market == "ALL":
            matched_strategies = total_strategies
        elif current_market == "REPLAY":
            matched_strategies = total_strategies
        else:
            matched_strategies = sum(
                1 for s in strategies.values()
                if getattr(s, 'market_scope', 'ALL') in ("ALL", current_market)
            )
        total_signals = all_stats.get('total_signals_generated', 0)
        recent_signals = all_stats.get('recent_signals_count', 0)
        is_running = getattr(manager, 'is_running', False)

        # 汇总执行/跳过计数
        total_exec_count = 0
        total_skip_count = 0

        strategy_list = []
        for name, strategy in list(strategies.items())[:6]:
            config = configs.get(name)
            if config is not None:
                is_active = getattr(config, 'enabled', False)
            else:
                is_active = getattr(strategy, 'is_active', False)
            signal_count = getattr(strategy, 'signal_count', 0)
            exec_count = getattr(strategy, 'execution_count', 0)
            skip_count = getattr(strategy, 'skip_count', 0)
            priority = getattr(config, 'priority', 5) if config else getattr(strategy, 'priority', 5)
            last_signal = getattr(strategy, 'last_signal_time', 0)
            last_signal_str = _fmt_ts(last_signal) if last_signal else "-"

            total_exec_count += exec_count
            total_skip_count += skip_count

            status_color = "#4ade80" if is_active else "#64748b"
            strategy_list.append({
                'name': name[:12],
                'status': status_color,
                'signals': signal_count,
                'exec': exec_count,
                'skip': skip_count,
                'priority': priority,
                'last': last_signal_str,
                'active': is_active
            })

    except Exception:
        return ""

    strategy_items = ""
    for s in strategy_list:
        p = s['priority']
        p_color = "#dc2626" if p <= 3 else ("#ca8a04" if p <= 6 else "#64748b")
        strategy_items += f"""
        <div style="display: flex; align-items: center; gap: 6px; padding: 4px 0; border-bottom: 1px solid rgba(255,255,255,0.05);">
            <div style="width: 6px; height: 6px; border-radius: 50%; background: {s['status']};"></div>
            <span style="font-size: 9px; color: #94a3b8; flex: 1;">{s['name']}</span>
            <span style="font-size: 7px; color: {p_color}; background: rgba(255,255,255,0.05); padding: 1px 3px; border-radius: 2px;">P{p}</span>
            <span style="font-size: 8px; color: #64748b;">{s['signals']}信号</span>
            <span style="font-size: 8px; color: #3b82f6;">{s['exec']}执行</span>
            <span style="font-size: 8px; color: #fb923c;">{s['skip']}跳过</span>
            <span style="font-size: 8px; color: #64748b;">{s['last']}</span>
        </div>
        """

    if not strategy_items:
        strategy_items = '<div style="color: #64748b; font-size: 10px; text-align: center; padding: 10px;">暂无策略</div>'

    return f"""
    <div style="
        margin-bottom: 12px;
        background: rgba(255,255,255,0.03);
        border-radius: 12px;
        padding: 14px 18px;
        border: 1px solid rgba(255,255,255,0.08);
    ">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
            <div style="font-size: 13px; font-weight: 600; color: #a855f7;">
                🎯 策略状态
            </div>
            <div style="font-size: 9px; color: #64748b;">
                活跃: {active_strategies}/{total_strategies} | 总信号: {total_signals:,}
                | 状态: <span style="color:{'#4ade80' if is_running else '#f87171'};">{'运行中' if is_running else '未运行'}</span>
                | 匹配: {matched_strategies} | 市场: {current_market}
            </div>
        </div>

        <div style="display: grid; grid-template-columns: repeat(5, 1fr); gap: 6px; margin-bottom: 10px;">
            <div style="text-align: center; padding: 6px; background: rgba(168,85,247,0.1); border-radius: 4px;">
                <div style="font-size: 14px; font-weight: 700; color: #a855f7;">{total_strategies}</div>
                <div style="font-size: 8px; color: #64748b;">总策略</div>
            </div>
            <div style="text-align: center; padding: 6px; background: rgba(74,222,128,0.1); border-radius: 4px;">
                <div style="font-size: 14px; font-weight: 700; color: #4ade80;">{active_strategies}</div>
                <div style="font-size: 8px; color: #64748b;">活跃</div>
            </div>
            <div style="text-align: center; padding: 6px; background: rgba(14,165,233,0.1); border-radius: 4px;">
                <div style="font-size: 14px; font-weight: 700; color: #0ea5e9;">{recent_signals}</div>
                <div style="font-size: 8px; color: #64748b;">最近信号</div>
            </div>
            <div style="text-align: center; padding: 6px; background: rgba(59,130,246,0.1); border-radius: 4px;">
                <div style="font-size: 14px; font-weight: 700; color: #3b82f6;">{total_exec_count:,}</div>
                <div style="font-size: 8px; color: #64748b;">执行次数</div>
            </div>
            <div style="text-align: center; padding: 6px; background: rgba(251,146,60,0.1); border-radius: 4px;">
                <div style="font-size: 14px; font-weight: 700; color: #fb923c;">{total_skip_count:,}</div>
                <div style="font-size: 8px; color: #64748b;">跳过次数</div>
            </div>
        </div>

        <div style="font-size: 8px; color: #64748b; margin-bottom: 4px; display: flex; justify-content: space-between; padding: 0 3px;">
            <span>策略</span>
            <span>信号</span>
            <span>最近</span>
        </div>
        {strategy_items}
    </div>
    """


def render_dual_engine_panel() -> str:
    """渲染双引擎状态面板"""
    try:
        from deva.naja.attention.orchestration.trading_center import get_trading_center
        from deva.naja.market_hotspot.integration import get_market_hotspot_integration

        orchestrator = get_trading_center()
        integration = get_market_hotspot_integration()

        if not integration or not integration.hotspot_system:
            return ""

        hs = integration.hotspot_system
        cn_dual_engine = getattr(hs, 'dual_engine', None)
        us_context = getattr(hs, '_us_context', None)

        cn_river_processed = 0
        cn_river_anomalies = 0
        cn_river_active = 0
        cn_pytorch_inferences = 0

        us_river_processed = 0
        us_river_anomalies = 0
        us_river_active = 0
        us_pytorch_inferences = 0

        if cn_dual_engine:
            cn_summary = cn_dual_engine.get_trigger_summary()
            cn_river_stats = cn_summary.get('river_stats', {})
            cn_pytorch_stats = cn_summary.get('pytorch_stats', {})
            cn_river_processed = cn_river_stats.get('processed_count', 0)
            cn_river_anomalies = cn_river_stats.get('anomaly_count', 0)
            cn_river_active = cn_river_stats.get('active_symbols', 0)
            cn_pytorch_inferences = cn_pytorch_stats.get('inference_count', 0)

        if us_context:
            us_summary = us_context.dual_engine.get_trigger_summary()
            us_river_stats = us_summary.get('river_stats', {})
            us_pytorch_stats = us_summary.get('pytorch_stats', {})
            us_river_processed = us_river_stats.get('processed_count', 0)
            us_river_anomalies = us_river_stats.get('anomaly_count', 0)
            us_river_active = us_river_stats.get('active_symbols', 0)
            us_pytorch_inferences = us_pytorch_stats.get('inference_count', 0)

    except Exception:
        return ""

    return f"""
    <div style="
        margin-bottom: 12px;
        background: rgba(255,255,255,0.03);
        border-radius: 12px;
        padding: 14px 18px;
        border: 1px solid rgba(255,255,255,0.08);
    ">
        <div style="font-size: 13px; font-weight: 600; color: #6366f1; margin-bottom: 10px;">
            ⚡ 双引擎状态
        </div>

        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 10px;">
            <div style="padding: 10px; background: rgba(34,197,94,0.1); border-radius: 6px; border-left: 3px solid #22c55e;">
                <div style="font-size: 10px; font-weight: 600; color: #22c55e; margin-bottom: 6px;">🌊 A股 River <span style="font-size: 9px; color: #86efac;">(注册 {cn_river_active:,})</span></div>
                <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 4px;">
                    <div>
                        <div style="font-size: 12px; font-weight: 700; color: #4ade80;">{cn_river_processed:,}</div>
                        <div style="font-size: 8px; color: #64748b;">处理数</div>
                    </div>
                    <div>
                        <div style="font-size: 12px; font-weight: 700; color: #fb923c;">{cn_river_anomalies:,}</div>
                        <div style="font-size: 8px; color: #64748b;">异动数</div>
                    </div>
                </div>
            </div>

            <div style="padding: 10px; background: rgba(59,130,246,0.1); border-radius: 6px; border-left: 3px solid #3b82f6;">
                <div style="font-size: 10px; font-weight: 600; color: #3b82f6; margin-bottom: 6px;">🌊 美股 River <span style="font-size: 9px; color: #93c5fd;">(注册 {us_river_active:,})</span></div>
                <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 4px;">
                    <div>
                        <div style="font-size: 12px; font-weight: 700; color: #60a5fa;">{us_river_processed:,}</div>
                        <div style="font-size: 8px; color: #64748b;">处理数</div>
                    </div>
                    <div>
                        <div style="font-size: 12px; font-weight: 700; color: #fb923c;">{us_river_anomalies:,}</div>
                        <div style="font-size: 8px; color: #64748b;">异动数</div>
                    </div>
                </div>
            </div>

            <div style="padding: 10px; background: rgba(168,85,247,0.1); border-radius: 6px; border-left: 3px solid #a855f7;">
                <div style="font-size: 10px; font-weight: 600; color: #a855f7; margin-bottom: 6px;">🧠 A股 PyTorch</div>
                <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 4px;">
                    <div>
                        <div style="font-size: 12px; font-weight: 700; color: #a855f7;">{cn_pytorch_inferences:,}</div>
                        <div style="font-size: 8px; color: #64748b;">推理数</div>
                    </div>
                </div>
            </div>

            <div style="padding: 10px; background: rgba(168,85,247,0.1); border-radius: 6px; border-left: 3px solid #7c3aed;">
                <div style="font-size: 10px; font-weight: 600; color: #7c3aed; margin-bottom: 6px;">🧠 美股 PyTorch</div>
                <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 4px;">
                    <div>
                        <div style="font-size: 12px; font-weight: 700; color: #8b5cf6;">{us_pytorch_inferences:,}</div>
                        <div style="font-size: 8px; color: #64748b;">推理数</div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    """
