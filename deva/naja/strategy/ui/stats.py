"""策略统计面板渲染"""


def _render_strategy_stats_html(stats: dict, running_count: int, error_count: int) -> str:
    return f"""
    <div style="display:flex;flex-wrap:wrap;gap:16px;margin-bottom:24px;">
        <div style="flex:1;min-width:140px;background:linear-gradient(135deg,#667eea,#764ba2);padding:20px;border-radius:12px;color:#fff;box-shadow:0 4px 12px rgba(102,126,234,0.3);">
            <div style="font-size:13px;opacity:0.9;margin-bottom:4px;">总策略数</div>
            <div style="font-size:32px;font-weight:700;">{stats['total']}</div>
        </div>
        <div style="flex:1;min-width:140px;background:linear-gradient(135deg,#11998e,#38ef7d);padding:20px;border-radius:12px;color:#fff;box-shadow:0 4px 12px rgba(17,153,142,0.3);">
            <div style="font-size:13px;opacity:0.9;margin-bottom:4px;">运行中</div>
            <div style="font-size:32px;font-weight:700;">{running_count}</div>
        </div>
        <div style="flex:1;min-width:140px;background:linear-gradient(135deg,#ff416c,#ff4b2b);padding:20px;border-radius:12px;color:#fff;box-shadow:0 4px 12px rgba(255,65,108,0.3);">
            <div style="font-size:13px;opacity:0.9;margin-bottom:4px;">错误数</div>
            <div style="font-size:32px;font-weight:700;">{error_count}</div>
        </div>
    </div>
    """


def _render_result_stats_html(result_stats: dict) -> str:
    success_rate = result_stats.get('success_rate', 0)
    rate_color = '#28a745' if success_rate > 0.9 else '#ffc107' if success_rate > 0.7 else '#dc3545'

    return f"""
    <div style="margin:16px 0 12px 0;font-size:15px;font-weight:600;color:#333;">📊 执行结果监控</div>
    <div style="display:flex;gap:16px;margin-bottom:20px;flex-wrap:wrap;">
        <div style="flex:1;min-width:100px;background:#fff;padding:16px;border-radius:10px;box-shadow:0 2px 8px rgba(0,0,0,0.08);">
            <div style="font-size:12px;color:#666;margin-bottom:4px;">总执行次数</div>
            <div style="font-size:24px;font-weight:700;color:#333;">{result_stats.get('total_results', 0)}</div>
        </div>
        <div style="flex:1;min-width:100px;background:#fff;padding:16px;border-radius:10px;box-shadow:0 2px 8px rgba(0,0,0,0.08);">
            <div style="font-size:12px;color:#666;margin-bottom:4px;">成功次数</div>
            <div style="font-size:24px;font-weight:700;color:#28a745;">{result_stats.get('total_success', 0)}</div>
        </div>
        <div style="flex:1;min-width:100px;background:#fff;padding:16px;border-radius:10px;box-shadow:0 2px 8px rgba(0,0,0,0.08);">
            <div style="font-size:12px;color:#666;margin-bottom:4px;">失败次数</div>
            <div style="font-size:24px;font-weight:700;color:#dc3545;">{result_stats.get('total_failed', 0)}</div>
        </div>
        <div style="flex:1;min-width:100px;background:#fff;padding:16px;border-radius:10px;box-shadow:0 2px 8px rgba(0,0,0,0.08);">
            <div style="font-size:12px;color:#666;margin-bottom:4px;">平均耗时</div>
            <div style="font-size:24px;font-weight:700;color:#17a2b8;">{result_stats.get('avg_process_time_ms', 0):.1f}ms</div>
        </div>
        <div style="flex:1;min-width:100px;background:#fff;padding:16px;border-radius:10px;box-shadow:0 2px 8px rgba(0,0,0,0.08);">
            <div style="font-size:12px;color:#666;margin-bottom:4px;">成功率</div>
            <div style="font-size:24px;font-weight:700;color:{rate_color};">{success_rate*100:.1f}%</div>
        </div>
    </div>
    """
