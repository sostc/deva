"""反馈报告面板 - 展示 FeedbackReportGenerator 的数据收集与分析状态"""

import logging

log = logging.getLogger(__name__)


def render_feedback_report_panel() -> str:
    """渲染反馈报告面板

    数据源: get_feedback_report_generator().get_summary()
    返回字段: is_collecting, experiment_id, signals_count, feedback_count,
              bandit_count, duration_seconds
    """
    try:
        from deva.naja.market_hotspot.intelligence.feedback_report import get_feedback_report_generator
        generator = get_feedback_report_generator()
        if not generator:
            return _render_empty("反馈报告生成器未初始化")

        summary = generator.get_summary()
        if not summary:
            return _render_empty("暂无反馈数据")

        is_collecting = summary.get('is_collecting', False)
        experiment_id = summary.get('experiment_id') or '-'
        signals_count = summary.get('signals_count', 0)
        feedback_count = summary.get('feedback_count', 0)
        bandit_count = summary.get('bandit_count', 0)
        duration = summary.get('duration_seconds', 0)

        # 状态
        if is_collecting:
            status_color, status_text = "#16a34a", "🟢 收集中"
        else:
            status_color, status_text = "#64748b", "⚪ 待机"

        # 持续时间格式化
        if duration > 3600:
            duration_str = f"{duration / 3600:.1f}h"
        elif duration > 60:
            duration_str = f"{duration / 60:.0f}m"
        else:
            duration_str = f"{duration:.0f}s"

        # 反馈率
        if signals_count > 0:
            feedback_rate = feedback_count / signals_count * 100
        else:
            feedback_rate = 0

    except Exception as e:
        return _render_empty(f"加载失败: {e}")

    return f"""
    <div style="
        margin-bottom: 12px;
        background: rgba(255,255,255,0.03);
        border-radius: 12px;
        padding: 14px 18px;
        border: 1px solid rgba(255,255,255,0.08);
    ">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
            <div style="font-size: 13px; font-weight: 600; color: #06b6d4;">
                📋 反馈报告
            </div>
            <div style="font-size: 9px; color: {status_color};">
                {status_text}
            </div>
        </div>

        <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; margin-bottom: 10px;">
            <div style="text-align: center; padding: 8px; background: rgba(6,182,212,0.1); border-radius: 4px;">
                <div style="font-size: 14px; font-weight: 700; color: #06b6d4;">{signals_count}</div>
                <div style="font-size: 8px; color: #64748b;">信号数</div>
            </div>
            <div style="text-align: center; padding: 8px; background: rgba(168,85,247,0.1); border-radius: 4px;">
                <div style="font-size: 14px; font-weight: 700; color: #a855f7;">{feedback_count}</div>
                <div style="font-size: 8px; color: #64748b;">反馈数</div>
            </div>
            <div style="text-align: center; padding: 8px; background: rgba(251,146,60,0.1); border-radius: 4px;">
                <div style="font-size: 14px; font-weight: 700; color: #fb923c;">{bandit_count}</div>
                <div style="font-size: 8px; color: #64748b;">Bandit</div>
            </div>
            <div style="text-align: center; padding: 8px; background: rgba(74,222,128,0.1); border-radius: 4px;">
                <div style="font-size: 14px; font-weight: 700; color: #4ade80;">{feedback_rate:.0f}%</div>
                <div style="font-size: 8px; color: #64748b;">反馈率</div>
            </div>
        </div>

        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px;">
            <div style="padding: 6px; background: rgba(6,182,212,0.05); border-radius: 4px;">
                <div style="font-size: 8px; color: #06b6d4; margin-bottom: 2px;">🧪 实验</div>
                <div style="font-size: 8px; color: #94a3b8; word-break: break-all;">{experiment_id[:16] if experiment_id != '-' else '-'}</div>
            </div>
            <div style="padding: 6px; background: rgba(251,146,60,0.05); border-radius: 4px;">
                <div style="font-size: 8px; color: #fb923c; margin-bottom: 2px;">⏱️ 持续时间</div>
                <div style="font-size: 8px; color: #94a3b8;">{duration_str}</div>
            </div>
        </div>
    </div>
    """


def _render_empty(msg: str) -> str:
    return f"""
    <div style="
        margin-bottom: 12px;
        background: rgba(255,255,255,0.03);
        border-radius: 12px;
        padding: 14px 18px;
        border: 1px solid rgba(255,255,255,0.08);
    ">
        <div style="font-size: 13px; font-weight: 600; color: #06b6d4; margin-bottom: 10px;">
            📋 反馈报告
        </div>
        <div style="text-align: center; padding: 15px; color: #64748b; font-size: 11px;">
            {msg}
        </div>
    </div>
    """
