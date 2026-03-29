"""Bandit 盈亏归因分析 UI

提供完整的归因分析界面，包括：
1. 策略贡献度排名
2. 收益归因分解
3. 信号质量分析
4. 市场条件关联

每个模块都包含详细的使用说明。
"""

from datetime import datetime
from typing import Optional

from pywebio.output import *
from pywebio import session


def _format_return(return_val: float) -> str:
    """格式化收益率显示"""
    color = "#16a34a" if return_val >= 0 else "#dc2626"
    sign = "+" if return_val >= 0 else ""
    return f'<span style="color:{color};font-weight:bold;">{sign}{return_val:.2f}%</span>'


def _format_duration(seconds: float) -> str:
    """格式化持仓时长"""
    if seconds < 60:
        return f"{seconds:.0f}秒"
    elif seconds < 3600:
        return f"{seconds/60:.1f}分钟"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}小时"


def _get_confidence_label(confidence: float) -> str:
    """获取信心度标签"""
    if confidence > 0.7:
        return "🔵 高"
    elif confidence >= 0.4:
        return "🟡 中"
    else:
        return "🔴 低"


def _get_liquidity_label(liquidity: float) -> str:
    """获取流动性标签"""
    if liquidity > 0.7:
        return "🟢 高流动性"
    elif liquidity >= 0.3:
        return "🟡 中流动性"
    else:
        return "🔴 低流动性"


def _render_help_panel(title: str, content: str, scope: str) -> None:
    """渲染带使用说明的面板"""
    with use_scope(scope):
        put_html(f"""
        <div style="
            background: linear-gradient(135deg, #f0f9ff, #e0f2fe);
            border-radius: 8px;
            padding: 12px 16px;
            margin: 10px 0;
            border: 1px solid #7dd3fc;
        ">
            <div style="display: flex; align-items: center; margin-bottom: 8px;">
                <span style="font-size: 18px; margin-right: 8px;">💡</span>
                <strong style="color: #0369a1; font-size: 14px;">{title}</strong>
            </div>
            <div style="font-size: 12px; color: #475569; line-height: 1.6;">
                {content}
            </div>
        </div>
        """)


async def render_attribution_panel(strategy_id: Optional[str] = None):
    """渲染归因分析主面板

    Args:
        strategy_id: 可选，指定策略ID查看单个策略；None 表示所有策略
    """
    from deva.naja.bandit.attribution import get_attribution

    attr = get_attribution()
    report = attr.get_full_attribution_report(strategy_id=strategy_id)

    put_html("<h2>📊 盈亏归因分析</h2>")

    _render_help_panel(
        "归因分析使用说明",
        """
        <b>归因分析帮助你理解策略的真实贡献：</b><br>
        • <b>策略贡献度</b>：每个策略赚了/亏了多少钱，胜率如何<br>
        • <b>收益分解</b>：收益 = 选股贡献 + 时机贡献 + 仓位管理贡献<br>
        • <b>信号质量</b>：高信心信号是否比低信心信号表现更好？<br>
        • <b>市场条件</b>：策略在不同市场环境下的表现差异<br><br>
        <b>如何使用：</b><br>
        • 查看策略排名，找到最佳和最差的策略<br>
        • 分析信号质量，调整信心度阈值<br>
        • 根据市场条件选择合适的策略
        """,
        "attribution_help"
    )

    put_text("")

    with use_scope("attribution_summary"):
        summary = report.get("summary", {})
        contributions = report.get("contributions", [])

        put_html("<h3>📈 归因摘要</h3>")

        total_return = summary.get("total_return", 0)
        total_trades = summary.get("total_trades", 0)
        best_strategy = summary.get("best_strategy", "无")
        worst_strategy = summary.get("worst_strategy", "无")
        winning_count = summary.get("winning_strategies", 0)
        losing_count = summary.get("losing_strategies", 0)

        put_row([
            put_column([
                put_html("<b>总收益</b>"),
                put_html(_format_return(total_return)),
            ]),
            put_column([
                put_html("<b>总交易数</b>"),
                put_text(str(total_trades)),
            ]),
            put_column([
                put_html("<b>盈利策略</b>"),
                put_html(f'<span style="color:#16a34a;">{winning_count}个</span>'),
            ]),
            put_column([
                put_html("<b>亏损策略</b>"),
                put_html(f'<span style="color:#dc2626;">{losing_count}个</span>'),
            ]),
        ], size="1fr 1fr 1fr 1fr")

        put_text("")

        if best_strategy:
            put_html(f"<b>🏆 最佳策略</b>：{best_strategy}")
        if worst_strategy:
            put_html(f"<b>⚠️ 最差策略</b>：{worst_strategy}")

    put_text("")

    with use_scope("strategy_ranking"):
        put_html("<h3>🏅 策略贡献度排名</h3>")

        _render_help_panel(
            "策略贡献度说明",
            """
            <b>指标解释：</b><br>
            • <b>总收益</b>：该策略所有交易的总收益率累加<br>
            • <b>交易次数</b>：该策略执行的交易总数<br>
            • <b>胜率</b>：盈利交易占比<br>
            • <b>平均收益</b>：每笔交易的平均收益率<br>
            • <b>盈亏比</b>：总盈利 / 总亏损（越大越好）<br><br>
            <b>如何解读：</b><br>
            • 总收益为正且高的策略是主要盈利来源<br>
            • 胜率高但平均收益低的策略稳健<br>
            • 盈亏比 > 1 表示盈利能覆盖亏损
            """,
            "ranking_help"
        )

        if contributions:
            headers = ["排名", "策略ID", "总收益", "交易数", "胜率", "平均收益", "盈亏比"]
            table_html = """
            <table style="width:100%; border-collapse: collapse; margin: 10px 0;">
                <tr style="background: #f1f5f9;">
            """
            for h in headers:
                table_html += f'<th style="padding: 10px; text-align: left; border: 1px solid #e2e8f0;">{h}</th>'
            table_html += "</tr>"

            for i, c in enumerate(contributions):
                bg = "#ffffff" if i % 2 == 0 else "#f8fafc"
                table_html += f'<tr style="background: {bg};">'
                table_html += f'<td style="padding: 8px; border: 1px solid #e2e8f0;">#{c["rank"]}</td>'
                table_html += f'<td style="padding: 8px; border: 1px solid #e2e8f0;">{c["strategy_id"]}</td>'
                table_html += f'<td style="padding: 8px; border: 1px solid #e2e8f0;">{_format_return(c["total_return"])}</td>'
                table_html += f'<td style="padding: 8px; border: 1px solid #e2e8f0;">{c["total_trades"]}</td>'
                table_html += f'<td style="padding: 8px; border: 1px solid #e2e8f0;">{c["win_rate"]:.1f}%</td>'
                table_html += f'<td style="padding: 8px; border: 1px solid #e2e8f0;">{_format_return(c["avg_return"])}</td>'
                pl_ratio = f'{c["profit_loss_ratio"]:.2f}' if c["profit_loss_ratio"] != float('inf') else "∞"
                table_html += f'<td style="padding: 8px; border: 1px solid #e2e8f0;">{pl_ratio}</td>'
                table_html += "</tr>"

            table_html += "</table>"
            put_html(table_html)
        else:
            put_html("""
            <div style="
                background: #f8fafc;
                border-radius: 8px;
                padding: 20px;
                text-align: center;
                color: #64748b;
            ">
                暂无归因数据。平仓交易后会自动记录归因信息。
            </div>
            """)

    put_text("")

    with use_scope("attribution_breakdown"):
        put_html("<h3>📊 收益归因分解</h3>")

        _render_help_panel(
            "收益分解说明",
            """
            <b>收益分解原理：</b><br>
            • <b>选股贡献</b>：持仓时间越长，选股贡献越大（选对股票的重要性）<br>
            • <b>时机贡献</b>：持仓时间越短，时机贡献越大（买对时机的重要性）<br>
            • <b>仓位管理</b>：剩余的收益部分<br><br>
            <b>如何解读：</b><br>
            • 如果时机贡献远大于选股贡献：说明策略擅长择时<br>
            • 如果选股贡献远大于时机贡献：说明策略擅长选股<br>
            • 根据这个调整策略重心
            """,
            "breakdown_help"
        )

        breakdown = report.get("breakdown", {})
        if breakdown.get("total_return", 0) != 0:
            selection = breakdown.get("selection_return", 0)
            timing = breakdown.get("timing_return", 0)
            position = breakdown.get("position_return", 0)
            total = breakdown.get("total_return", 0)

            total_abs = abs(selection) + abs(timing) + abs(position) if total != 0 else 1

            selection_pct = abs(selection) / total_abs * 100
            timing_pct = abs(timing) / total_abs * 100
            position_pct = abs(position) / total_abs * 100

            bar_html = f"""
            <div style="background: #f1f5f9; border-radius: 8px; padding: 16px; margin: 10px 0;">
                <div style="display: flex; height: 30px; border-radius: 6px; overflow: hidden; margin-bottom: 10px;">
                    <div style="background: #3b82f6; width: {selection_pct:.1f}%; display: flex; align-items: center; justify-content: center; color: white; font-size: 12px;" title="选股贡献">
                        {'选股' if selection_pct > 10 else ''}
                    </div>
                    <div style="background: #f59e0b; width: {timing_pct:.1f}%; display: flex; align-items: center; justify-content: center; color: white; font-size: 12px;" title="时机贡献">
                        {'时机' if timing_pct > 10 else ''}
                    </div>
                    <div style="background: #10b981; width: {position_pct:.1f}%; display: flex; align-items: center; justify-content: center; color: white; font-size: 12px;" title="仓位管理">
                        {'仓位' if position_pct > 10 else ''}
                    </div>
                </div>
                <div style="display: flex; justify-content: space-around; font-size: 12px;">
                    <div><span style="color: #3b82f6;">●</span> 选股贡献: {_format_return(selection)}</div>
                    <div><span style="color: #f59e0b;">●</span> 时机贡献: {_format_return(timing)}</div>
                    <div><span style="color: #10b981;">●</span> 仓位管理: {_format_return(position)}</div>
                </div>
            </div>
            """
            put_html(bar_html)
        else:
            put_html("""
            <div style="
                background: #f8fafc;
                border-radius: 8px;
                padding: 20px;
                text-align: center;
                color: #64748b;
            ">
                暂无分解数据。
            </div>
            """)

    put_text("")

    with use_scope("signal_quality"):
        put_html("<h3>🎯 信号质量分析</h3>")

        _render_help_panel(
            "信号质量说明",
            """
            <b>信号信心度定义：</b><br>
            • <b>高信心 (>0.7)</b>：策略强烈看好的信号<br>
            • <b>中信心 (0.4-0.7)</b>：策略中等确定性的信号<br>
            • <b>低信心 (<0.4)</b>：策略不太确定的信号<br><br>
            <b>如何解读：</b><br>
            • 如果高信心信号的平均收益明显高于低信心：说明信心度指标有效<br>
            • 如果差异不大：考虑调整策略参数以产生更大差异<br>
            • <b>相关性</b>：信心度与收益的相关性（0-1），越高说明信心度越准
            """,
            "signal_help"
        )

        sq = report.get("signal_quality")
        if sq and sq.get("high_confidence_trades", 0) > 0:
            high_trades = sq.get("high_confidence_trades", 0)
            high_avg = sq.get("high_confidence_avg_return", 0)
            mid_trades = sq.get("medium_confidence_trades", 0)
            mid_avg = sq.get("medium_confidence_avg_return", 0)
            low_trades = sq.get("low_confidence_trades", 0)
            low_avg = sq.get("low_confidence_avg_return", 0)
            correlation = sq.get("confidence_return_correlation", 0)

            corr_color = "#16a34a" if correlation > 0.3 else "#f59e0b" if correlation > 0 else "#dc2626"
            corr_label = "强正相关 ✓" if correlation > 0.3 else "弱正相关" if correlation > 0 else "负相关 ✗"

            signal_table_html = """
            <table style="width:100%; border-collapse: collapse; margin: 10px 0;">
                <tr style="background: #f1f5f9;">
                    <th style="padding: 10px; text-align: left; border: 1px solid #e2e8f0;">信心度</th>
                    <th style="padding: 10px; text-align: left; border: 1px solid #e2e8f0;">交易数</th>
                    <th style="padding: 10px; text-align: left; border: 1px solid #e2e8f0;">平均收益</th>
                </tr>
                <tr style="background: #ffffff;">
                    <td style="padding: 8px; border: 1px solid #e2e8f0;">🔵 高信心 (&gt;0.7)</td>
                    <td style="padding: 8px; border: 1px solid #e2e8f0;">{high_trades}</td>
                    <td style="padding: 8px; border: 1px solid #e2e8f0;">{high_avg}</td>
                </tr>
                <tr style="background: #f8fafc;">
                    <td style="padding: 8px; border: 1px solid #e2e8f0;">🟡 中信心 (0.4-0.7)</td>
                    <td style="padding: 8px; border: 1px solid #e2e8f0;">{mid_trades}</td>
                    <td style="padding: 8px; border: 1px solid #e2e8f0;">{mid_avg}</td>
                </tr>
                <tr style="background: #ffffff;">
                    <td style="padding: 8px; border: 1px solid #e2e8f0;">🔴 低信心 (&lt;0.4)</td>
                    <td style="padding: 8px; border: 1px solid #e2e8f0;">{low_trades}</td>
                    <td style="padding: 8px; border: 1px solid #e2e8f0;">{low_avg}</td>
                </tr>
            </table>
            """.format(
                high_trades=high_trades,
                high_avg=_format_return(high_avg),
                mid_trades=mid_trades,
                mid_avg=_format_return(mid_avg),
                low_trades=low_trades,
                low_avg=_format_return(low_avg),
            )
            put_html(signal_table_html)

            put_html(f"""
            <div style="
                background: #f8fafc;
                border-radius: 8px;
                padding: 12px;
                margin-top: 10px;
                font-size: 13px;
            ">
                <b>信心度-收益相关性</b>：
                <span style="color: {corr_color}; font-weight: bold;">{correlation:.3f}</span>
                ({corr_label})
            </div>
            """)
        else:
            put_html("""
            <div style="
                background: #f8fafc;
                border-radius: 8px;
                padding: 20px;
                text-align: center;
                color: #64748b;
            ">
                暂无信号质量数据。
            </div>
            """)

    put_text("")

    with use_scope("market_condition"):
        put_html("<h3>🌡️ 市场条件关联</h3>")

        _render_help_panel(
            "市场条件说明",
            """
            <b>流动性信号（0-1）：</b><br>
            • <b>高流动性 (>0.7)</b>：市场资金充裕，适合做多<br>
            • <b>中流动性 (0.3-0.7)</b>：市场中性<br>
            • <b>低流动性 (<0.3)</b>：市场资金紧张，谨慎操作<br><br>
            <b>如何解读：</b><br>
            • 如果策略在高流动性环境下表现更好：说明策略喜欢顺势<br>
            • 如果策略在低流动性环境下表现更好：说明策略擅长逆向操作<br>
            • 根据市场条件调整策略使用权重
            """,
            "market_help"
        )

        mc = report.get("market_condition")
        if mc:
            liq_high_avg = mc.get("liquidity_high_avg", 0)
            liq_high_count = mc.get("liquidity_high_count", 0)
            liq_mid_avg = mc.get("liquidity_mid_avg", 0)
            liq_mid_count = mc.get("liquidity_mid_count", 0)
            liq_low_avg = mc.get("liquidity_low_avg", 0)
            liq_low_count = mc.get("liquidity_low_count", 0)

            best_liq = "高流动性"
            best_avg = liq_high_avg
            if liq_mid_avg > best_avg:
                best_liq = "中流动性"
                best_avg = liq_mid_avg
            if liq_low_avg > best_avg:
                best_liq = "低流动性"
                best_avg = liq_low_avg

            market_table_html = f"""
            <table style="width:100%; border-collapse: collapse; margin: 10px 0;">
                <tr style="background: #f1f5f9;">
                    <th style="padding: 10px; text-align: left; border: 1px solid #e2e8f0;">市场环境</th>
                    <th style="padding: 10px; text-align: left; border: 1px solid #e2e8f0;">交易数</th>
                    <th style="padding: 10px; text-align: left; border: 1px solid #e2e8f0;">平均收益</th>
                </tr>
                <tr style="background: #ffffff;">
                    <td style="padding: 8px; border: 1px solid #e2e8f0;">🟢 高流动性</td>
                    <td style="padding: 8px; border: 1px solid #e2e8f0;">{liq_high_count}</td>
                    <td style="padding: 8px; border: 1px solid #e2e8f0;">{_format_return(liq_high_avg)}</td>
                </tr>
                <tr style="background: #f8fafc;">
                    <td style="padding: 8px; border: 1px solid #e2e8f0;">🟡 中流动性</td>
                    <td style="padding: 8px; border: 1px solid #e2e8f0;">{liq_mid_count}</td>
                    <td style="padding: 8px; border: 1px solid #e2e8f0;">{_format_return(liq_mid_avg)}</td>
                </tr>
                <tr style="background: #ffffff;">
                    <td style="padding: 8px; border: 1px solid #e2e8f0;">🔴 低流动性</td>
                    <td style="padding: 8px; border: 1px solid #e2e8f0;">{liq_low_count}</td>
                    <td style="padding: 8px; border: 1px solid #e2e8f0;">{_format_return(liq_low_avg)}</td>
                </tr>
            </table>
            """
            put_html(market_table_html)

            put_html(f"""
            <div style="
                background: #f0fdf4;
                border-radius: 8px;
                padding: 12px;
                margin-top: 10px;
                font-size: 13px;
                border: 1px solid #86efac;
            ">
                <b>📌 最佳市场环境</b>：{best_liq}（平均收益: {_format_return(best_avg)}）
            </div>
            """)
        else:
            put_html("""
            <div style="
                background: #f8fafc;
                border-radius: 8px;
                padding: 20px;
                text-align: center;
                color: #64748b;
            ">
                暂无市场条件数据。
            </div>
            """)

    put_text("")

    with use_scope("trade_history"):
        put_html("<h3>📜 最近交易历史</h3>")

        history = attr.get_trade_history(strategy_id=strategy_id, limit=10, sort_by="exit_time")

        if history:
            history_table_html = """
            <table style="width:100%; border-collapse: collapse; margin: 10px 0;">
                <tr style="background: #f1f5f9;">
                    <th style="padding: 10px; text-align: left; border: 1px solid #e2e8f0;">策略</th>
                    <th style="padding: 10px; text-align: left; border: 1px solid #e2e8f0;">股票</th>
                    <th style="padding: 10px; text-align: left; border: 1px solid #e2e8f0;">收益</th>
                    <th style="padding: 10px; text-align: left; border: 1px solid #e2e8f0;">信号信心</th>
                    <th style="padding: 10px; text-align: left; border: 1px solid #e2e8f0;">市场流动性</th>
                    <th style="padding: 10px; text-align: left; border: 1px solid #e2e8f0;">持仓时间</th>
                    <th style="padding: 10px; text-align: left; border: 1px solid #e2e8f0;">平仓时间</th>
                </tr>
            """

            for i, h in enumerate(history):
                bg = "#ffffff" if i % 2 == 0 else "#f8fafc"
                entry_time = datetime.fromtimestamp(h.get("entry_time", 0)).strftime("%m-%d %H:%M")
                exit_time = datetime.fromtimestamp(h.get("exit_time", 0)).strftime("%m-%d %H:%M")
                return_val = h.get("total_return_pct", 0)
                confidence = h.get("signal_confidence", 0.5)

                history_table_html += f'<tr style="background: {bg};">'
                history_table_html += f'<td style="padding: 8px; border: 1px solid #e2e8f0;">{h.get("strategy_id", "")}</td>'
                history_table_html += f'<td style="padding: 8px; border: 1px solid #e2e8f0;">{h.get("stock_code", "")}</td>'
                history_table_html += f'<td style="padding: 8px; border: 1px solid #e2e8f0;">{_format_return(return_val)}</td>'
                history_table_html += f'<td style="padding: 8px; border: 1px solid #e2e8f0;">{_get_confidence_label(confidence)}</td>'
                history_table_html += f'<td style="padding: 8px; border: 1px solid #e2e8f0;">{_get_liquidity_label(h.get("market_liquidity", 0.5))}</td>'
                history_table_html += f'<td style="padding: 8px; border: 1px solid #e2e8f0;">{_format_duration(h.get("holding_seconds", 0))}</td>'
                history_table_html += f'<td style="padding: 8px; border: 1px solid #e2e8f0;">{exit_time}</td>'
                history_table_html += "</tr>"

            history_table_html += "</table>"
            put_html(history_table_html)
        else:
            put_html("""
            <div style="
                background: #f8fafc;
                border-radius: 8px;
                padding: 20px;
                text-align: center;
                color: #64748b;
            ">
                暂无交易历史。
            </div>
            """)


async def render_attribution_page(ctx: dict):
    """渲染独立的归因分析页面（可通过菜单访问）"""
    await render_attribution_panel(strategy_id=None)


__all__ = [
    "render_attribution_panel",
    "render_attribution_page",
]
