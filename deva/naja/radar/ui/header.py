"""Radar UI — 页面标题 + 统计卡片"""

from pywebio.output import put_html

from .constants import get_cn_trading_status, get_us_trading_status


def render_header(engine):
    """渲染页面标题 - 酷炫深色风格"""
    summary_10m = engine.summarize(window_seconds=600) if engine else {}
    summary_1h = engine.summarize(window_seconds=3600) if engine else {}
    summary_24h = engine.summarize(window_seconds=86400) if engine else {}

    event_10m = summary_10m.get("event_count", 0)
    event_1h = summary_1h.get("event_count", 0)
    event_24h = summary_24h.get("event_count", 0)
    type_counts = summary_10m.get("event_type_counts", {})
    type_count = len(type_counts)

    engine_status = "🟢 运行中" if engine else "🔴 已停止"

    pattern_count = type_counts.get("radar_pattern", 0) + type_counts.get("pattern", 0)
    drift_count = type_counts.get("radar_data_distribution_shift", 0) + type_counts.get("drift", 0)
    anomaly_count = type_counts.get("radar_anomaly", 0) + type_counts.get("anomaly", 0)
    block_count = type_counts.get("radar_block_anomaly", 0) + type_counts.get("block_anomaly", 0) + type_counts.get("block_hotspot", 0)

    cn_phase, cn_phase_color = get_cn_trading_status()
    us_phase, us_phase_color = get_us_trading_status()

    put_html(f"""
    <div style="
        margin-bottom: 12px;
        background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
        border-radius: 14px;
        padding: 16px 20px;
        box-shadow: 0 4px 20px rgba(15, 23, 42, 0.25), inset 0 1px 0 rgba(255,255,255,0.05);
        border: 1px solid #334155;
        position: relative;
        overflow: hidden;
    ">
        <div style="position: absolute; top: 0; right: 0; width: 200px; height: 100%; background: radial-gradient(ellipse at top right, #f59e0b08 0%, transparent 60%); pointer-events: none;"></div>
        <div style="display: flex; justify-content: space-between; align-items: flex-start; position: relative;">
            <div>
                <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 6px;">
                    <span style="font-size: 24px; filter: drop-shadow(0 2px 4px rgba(0,0,0,0.3));">📡</span>
                    <div>
                        <div style="font-size: 16px; font-weight: 700; color: #f1f5f9;">雷达 <span style="font-size: 13px; font-weight: 400; color: #94a3b8;">感知层</span></div>
                        <div style="font-size: 11px; color: #f59e0b; margin-top: 2px;">只负责发现行情异常信号，不做调度与结论</div>
                    </div>
                </div>
                <div style="font-size: 12px; color: #64748b; margin-top: 6px;">输入：策略执行结果（信号、评分、题材异动）｜ 输出：异常事件 → 认知层</div>
            </div>
            <div style="display: flex; gap: 12px; text-align: center;">
                <div style="background: rgba(245, 158, 11, 0.1); border: 1px solid rgba(245, 158, 11, 0.3); border-radius: 10px; padding: 8px 14px; min-width: 80px;">
                    <div style="font-size: 11px; color: #64748b; margin-bottom: 4px;">10分钟</div>
                    <div style="font-size: 20px; font-weight: 700; color: #f59e0b;">{event_10m}</div>
                    <div style="font-size: 10px; color: #94a3b8;">事件</div>
                </div>
                <div style="background: rgba(14, 165, 233, 0.1); border: 1px solid rgba(14, 165, 233, 0.3); border-radius: 10px; padding: 8px 14px; min-width: 80px;">
                    <div style="font-size: 11px; color: #64748b; margin-bottom: 4px;">1小时</div>
                    <div style="font-size: 20px; font-weight: 700; color: #0ea5e9;">{event_1h}</div>
                    <div style="font-size: 10px; color: #94a3b8;">事件</div>
                </div>
                <div style="background: rgba(34, 197, 94, 0.1); border: 1px solid rgba(34, 197, 94, 0.3); border-radius: 10px; padding: 8px 14px; min-width: 80px;">
                    <div style="font-size: 11px; color: #64748b; margin-bottom: 4px;">24小时</div>
                    <div style="font-size: 20px; font-weight: 700; color: #22c55e;">{event_24h}</div>
                    <div style="font-size: 10px; color: #94a3b8;">事件</div>
                </div>
                <div style="background: rgba(168, 85, 247, 0.1); border: 1px solid rgba(168, 85, 247, 0.3); border-radius: 10px; padding: 8px 14px; min-width: 100px;">
                    <div style="font-size: 11px; color: #64748b; margin-bottom: 4px;">引擎状态</div>
                    <div style="font-size: 14px; font-weight: 700; color: #22c55e;">{engine_status}</div>
                    <div style="font-size: 10px; color: #94a3b8;">{type_count} 种类型</div>
                </div>
                <div style="background: rgba(59, 130, 246, 0.15); border: 1px solid rgba(59, 130, 246, 0.3); border-radius: 10px; padding: 8px 14px; min-width: 110px;">
                    <div style="font-size: 11px; color: #64748b; margin-bottom: 4px;">交易时段</div>
                    <div style="font-size: 12px; font-weight: 700; color: {cn_phase_color};">{cn_phase}</div>
                    <div style="font-size: 12px; font-weight: 700; color: {us_phase_color};">{us_phase}</div>
                </div>
            </div>
        </div>
        <div style="display: flex; gap: 8px; margin-top: 12px; padding-top: 12px; border-top: 1px solid #334155;">
            <div style="flex: 1; padding: 6px 10px; background: rgba(37, 99, 235, 0.15); border-radius: 6px; text-align: center;">
                <span style="font-size: 11px; color: #93c5fd;">📊 Pattern</span>
                <span style="font-size: 12px; font-weight: 600; color: #3b82f6; margin-left: 4px;">{pattern_count}</span>
            </div>
            <div style="flex: 1; padding: 6px 10px; background: rgba(147, 51, 234, 0.15); border-radius: 6px; text-align: center;">
                <span style="font-size: 11px; color: #d8b4fe;">📉 Drift</span>
                <span style="font-size: 12px; font-weight: 600; color: #a855f7; margin-left: 4px;">{drift_count}</span>
            </div>
            <div style="flex: 1; padding: 6px 10px; background: rgba(220, 38, 38, 0.15); border-radius: 6px; text-align: center;">
                <span style="font-size: 11px; color: #fca5a5;">⚡ Anomaly</span>
                <span style="font-size: 12px; font-weight: 600; color: #ef4444; margin-left: 4px;">{anomaly_count}</span>
            </div>
            <div style="flex: 1; padding: 6px 10px; background: rgba(239, 68, 68, 0.15); border-radius: 6px; text-align: center;">
                <span style="font-size: 11px; color: #fca5a5;">🔥 题材</span>
                <span style="font-size: 12px; font-weight: 600; color: #ef4444; margin-left: 4px;">{block_count}</span>
            </div>
        </div>
    </div>
    """)
