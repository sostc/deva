"""Bandit 自适应交易系统 UI"""

from datetime import datetime
from pywebio.output import *
from pywebio import session
import threading

from deva.naja.page_help import render_help_collapse

_auto_refresh_enabled = True


def set_auto_refresh(enabled: bool):
    global _auto_refresh_enabled
    _auto_refresh_enabled = enabled


def _get_close_reason_display(reason: str) -> str:
    """获取平仓原因的显示文本"""
    reason_map = {
        "STOP_LOSS": "<span style='color:red;font-weight:bold;'>🔻 止损</span>",
        "TAKE_PROFIT": "<span style='color:green;font-weight:bold;'>🔺 止盈</span>",
        "MANUAL": "<span style='color:gray;'>手动</span>",
        "FORCE": "<span style='color:orange;'>强制</span>",
        "": "<span style='color:gray;'>-</span>"
    }
    return reason_map.get(reason, f"<span style='color:gray;'>{reason}</span>")


def _get_experiment_banner_html() -> str:
    """获取实验模式提示横幅的 HTML"""
    try:
        from deva.naja.strategy import get_strategy_manager
        mgr = get_strategy_manager()
        exp_info = mgr.get_experiment_info()
        
        if not exp_info.get("active"):
            return ""
        
        # 获取数据源名称
        from deva.naja.datasource import get_datasource_manager
        ds_mgr = get_datasource_manager()
        ds_mgr.load_from_db()
        ds_id = exp_info.get("datasource_id", "")
        ds_entry = ds_mgr.get(ds_id)
        ds_name = ds_entry.name if ds_entry else ds_id[:8] + "..."
        
        categories = exp_info.get("categories", [])
        categories_text = "、".join(categories) if categories else "-"
        target_count = int(exp_info.get("target_count", 0))
        
        return f"""
        <div style="margin-bottom:14px;padding:12px 14px;border-radius:10px;
                    background:linear-gradient(135deg,#fff3cd,#ffe8a1);
                    border:1px solid #f5d37a;color:#7a5a00;font-size:13px;">
            <strong>🧪 实验模式已开启</strong><br>
            类别：{categories_text} ｜ 数据源：{ds_name} ｜ 策略数：{target_count}
        </div>
        """
    except Exception:
        return ""


async def render_bandit_admin(ctx: dict):
    """渲染 Bandit 管理页面"""
    
    from deva.naja.bandit import (
        get_adaptive_cycle,
        get_bandit_optimizer,
        get_virtual_portfolio,
        get_signal_listener,
        get_market_observer,
    )
    
    cycle = get_adaptive_cycle()
    optimizer = get_bandit_optimizer()
    portfolio = get_virtual_portfolio()
    listener = get_signal_listener()
    observer = get_market_observer()
    
    status = cycle.get_status()
    positions = cycle.get_positions()
    history = cycle.get_history(limit=20)
    bandit_stats = optimizer.get_all_stats()
    portfolio_summary = portfolio.get_summary()
    
    with use_scope("bandit_header"):
        put_html("<h2>🎰 Bandit 自适应交易系统</h2>")
        
        # 显示实验模式提示
        experiment_banner = _get_experiment_banner_html()
        if experiment_banner:
            put_html(experiment_banner)
        
        try:
            render_help_collapse("bandit")
        except Exception:
            pass
        
        put_row([
            put_button("启动循环", onclick=lambda: _do_start(cycle), small=True),
            put_button("停止循环", onclick=lambda: _do_stop(cycle), small=True),
        ], size="auto")
        
        put_text("")
    
    with use_scope("bandit_status"):
        put_row([
            put_column([
                put_html("<b>运行状态</b>"),
                put_text(f"循环: {'🟢 运行中' if status['running'] else '🔴 已停止'}"),
                put_text(f"自动买入: {'✅ 启用' if status['auto_buy_enabled'] else '❌ 禁用'}"),
                put_text(f"自动调节: {'✅ 启用' if status['auto_adjust_enabled'] else '❌ 禁用'}"),
            ]),
            put_column([
                put_html("<b>信号监听</b>"),
                put_text(f"轮询间隔: {status['signal_listener']['poll_interval']}s"),
                put_text(f"最小置信度: {status['signal_listener']['min_confidence']}"),
                put_text(f"已处理信号: {status['signal_listener']['processed_count']}"),
            ]),
            put_column([
                put_html("<b>市场观察</b>"),
                put_text(f"模式: 被动订阅"),
                put_text(f"跟踪股票: {len(status['market_observer']['tracked_stocks'])}"),
                put_text(f"最新价格: {len(status['market_observer']['prices'])}"),
            ]),
        ], size="1fr 1fr 1fr")
    
    put_text("")
    
    with use_scope("bandit_portfolio"):
        put_html("<h3>💰 虚拟持仓</h3>")
        put_row([
            put_column([
                put_html("<b>资金状况</b>"),
                put_text(f"总资金: ¥{portfolio_summary['total_value']:,.2f}"),
                put_text(f"已用: ¥{portfolio_summary['used_capital']:,.2f}"),
                put_text(f"可用: ¥{portfolio_summary['available_capital']:,.2f}"),
            ]),
            put_column([
                put_html("<b>持仓统计</b>"),
                put_text(f"持仓数量: {portfolio_summary['position_count']}"),
                put_text(f"总收益: {portfolio_summary['total_return']:.2f}%"),
                put_text(f"总盈亏: ¥{portfolio_summary['total_profit_loss']:,.2f}"),
            ]),
        ], size="1fr 1fr")
    
    if positions:
        put_text("")
        put_html("<h4>当前持仓</h4>")

        html = """<table style='width:100%;border-collapse:collapse;font-size:14px;'>
        <tr style='background:#f0f0f0;'>
            <th style='padding:8px;border:1px solid #ddd;'>股票名称</th>
            <th style='padding:8px;border:1px solid #ddd;'>代码</th>
            <th style='padding:8px;border:1px solid #ddd;'>入场价</th>
            <th style='padding:8px;border:1px solid #ddd;'>现价</th>
            <th style='padding:8px;border:1px solid #ddd;'>收益率</th>
            <th style='padding:8px;border:1px solid #ddd;'>盈亏</th>
            <th style='padding:8px;border:1px solid #ddd;'>止盈价</th>
            <th style='padding:8px;border:1px solid #ddd;'>止损价</th>
            <th style='padding:8px;border:1px solid #ddd;'>买入时间</th>
            <th style='padding:8px;border:1px solid #ddd;'>持仓时间</th>
        </tr>"""

        for p in positions:
            color = "green" if p['return_pct'] > 0 else "red"
            # 获取止盈止损价格
            stop_loss = p.get('stop_loss', 0)
            take_profit = p.get('take_profit', 0)
            stop_loss_str = f"¥{stop_loss:.2f}" if stop_loss > 0 else "-"
            take_profit_str = f"¥{take_profit:.2f}" if take_profit > 0 else "-"
            # 获取买入时间（优先使用行情时间）
            market_time = p.get('market_time', 0)
            entry_time = p.get('entry_time', 0)
            buy_time = market_time if market_time > 0 else entry_time
            buy_time_str = datetime.fromtimestamp(buy_time).strftime("%m-%d %H:%M") if buy_time > 0 else "-"

            html += f"""<tr>
                <td style='padding:8px;border:1px solid #ddd;'>{p['stock_name']}</td>
                <td style='padding:8px;border:1px solid #ddd;'>{p['stock_code']}</td>
                <td style='padding:8px;border:1px solid #ddd;'>¥{p['entry_price']:.2f}</td>
                <td style='padding:8px;border:1px solid #ddd;'>¥{p['current_price']:.2f}</td>
                <td style='padding:8px;border:1px solid #ddd;color:{color};font-weight:bold;'>{p['return_pct']:.2f}%</td>
                <td style='padding:8px;border:1px solid #ddd;color:{color};'>¥{p['profit_loss']:.2f}</td>
                <td style='padding:8px;border:1px solid #ddd;color:green;'>{take_profit_str}</td>
                <td style='padding:8px;border:1px solid #ddd;color:red;'>{stop_loss_str}</td>
                <td style='padding:8px;border:1px solid #ddd;'>{buy_time_str}</td>
                <td style='padding:8px;border:1px solid #ddd;'>{p['holding_seconds'] / 3600:.1f}h</td>
            </tr>"""

        html += "</table>"
        put_html(html)
        
        # 添加止盈止损说明
        put_html("""
        <div style='margin-top:8px;font-size:12px;color:#666;'>
            <span style='color:green;'>▲ 止盈价</span> - 达到此价格自动卖出获利 | 
            <span style='color:red;'>▼ 止损价</span> - 跌破此价格自动卖出止损
        </div>
        """)
    else:
        put_text("暂无持仓")
    
    if history:
        put_text("")
        put_html("<h4>历史平仓记录</h4>")

        html = """<table style='width:100%;border-collapse:collapse;font-size:14px;'>
        <tr style='background:#f0f0f0;'>
            <th style='padding:8px;border:1px solid #ddd;'>股票名称</th>
            <th style='padding:8px;border:1px solid #ddd;'>代码</th>
            <th style='padding:8px;border:1px solid #ddd;'>入场价</th>
            <th style='padding:8px;border:1px solid #ddd;'>出场价</th>
            <th style='padding:8px;border:1px solid #ddd;'>收益率</th>
            <th style='padding:8px;border:1px solid #ddd;'>盈亏</th>
            <th style='padding:8px;border:1px solid #ddd;'>买入时间</th>
            <th style='padding:8px;border:1px solid #ddd;'>平仓原因</th>
            <th style='padding:8px;border:1px solid #ddd;'>平仓时间</th>
        </tr>"""

        for h in history:
            color = "green" if h['return_pct'] > 0 else "red"
            # 使用 exit_price 作为出场价，如果没有则使用 current_price
            exit_price = h.get('exit_price', 0) or h['current_price']
            # 使用 exit_time 作为平仓时间，如果没有则使用 last_update_time
            exit_time = h.get('exit_time', 0) or h['last_update_time']
            # 获取平仓原因
            close_reason = h.get('close_reason', '')
            reason_display = _get_close_reason_display(close_reason)
            # 获取买入时间（优先使用行情时间）
            market_time = h.get('market_time', 0)
            entry_time = h.get('entry_time', 0)
            buy_time = market_time if market_time > 0 else entry_time
            buy_time_str = datetime.fromtimestamp(buy_time).strftime("%m-%d %H:%M") if buy_time > 0 else "-"
            html += f"""<tr>
                <td style='padding:8px;border:1px solid #ddd;'>{h['stock_name']}</td>
                <td style='padding:8px;border:1px solid #ddd;'>{h['stock_code']}</td>
                <td style='padding:8px;border:1px solid #ddd;'>¥{h['entry_price']:.2f}</td>
                <td style='padding:8px;border:1px solid #ddd;'>¥{exit_price:.2f}</td>
                <td style='padding:8px;border:1px solid #ddd;color:{color};font-weight:bold;'>{h['return_pct']:.2f}%</td>
                <td style='padding:8px;border:1px solid #ddd;color:{color};'>¥{h['profit_loss']:.2f}</td>
                <td style='padding:8px;border:1px solid #ddd;'>{buy_time_str}</td>
                <td style='padding:8px;border:1px solid #ddd;'>{reason_display}</td>
                <td style='padding:8px;border:1px solid #ddd;'>{datetime.fromtimestamp(exit_time).strftime("%m-%d %H:%M")}</td>
            </tr>"""

        html += "</table>"
        put_html(html)
    
    put_text("")
    
    with use_scope("bandit_stats"):
        put_html("<h3>📊 Bandit 策略统计</h3>")
        
        if bandit_stats:
            stats_data = []
            for s in bandit_stats:
                stats_data.append([
                    s['strategy_id'],
                    s['pull_count'],
                    f"{s['avg_reward']:.2f}%",
                    f"¥{s['total_reward']:.2f}",
                ])
            
            put_table(stats_data, header=[
                "策略 ID", "执行次数", "平均收益", "总收益"
            ])
        else:
            put_text("暂无策略数据")
    
    put_text("")
    
    with use_scope("bandit_controls"):
        put_html("<h3>⚙️ 控制面板</h3>")
        
        put_row([
            put_column([
                put_button("手动选择策略", onclick=lambda: _do_select(optimizer), small=True),
                put_button("触发调节", onclick=lambda: _do_adjust(optimizer), small=True),
            ]),
            put_column([
                put_button("清空持仓", onclick=lambda: _do_clear(portfolio), small=True),
                put_button("重置 Bandit", onclick=lambda: _do_reset(optimizer), small=True),
            ]),
        ], size="1fr 1fr")


def _do_start(cycle):
    try:
        cycle.start()
        put_text("✅ 自适应循环已启动")
    except Exception as e:
        put_text(f"❌ 启动失败: {e}")


def _do_stop(cycle):
    try:
        cycle.stop()
        put_text("✅ 自适应循环已停止")
    except Exception as e:
        put_text(f"❌ 停止失败: {e}")


def _do_select(optimizer):
    try:
        from deva.naja.strategy import get_strategy_manager
        mgr = get_strategy_manager()
        entries = mgr.list_all()
        
        if not entries:
            put_text("⚠️ 没有可用策略")
            return
        
        available = [e.id for e in entries]
        result = optimizer.select_strategy(available)
        
        if result.get("success"):
            put_text(f"✅ 选择策略: {result['selected']}")
        else:
            put_text(f"❌ 选择失败: {result.get('error')}")
    except Exception as e:
        put_text(f"❌ 错误: {e}")


def _do_adjust(optimizer):
    try:
        result = optimizer.review_and_adjust()
        if result.get("success"):
            put_text(f"✅ 调节完成: {result.get('summary')}")
        else:
            put_text(f"❌ 调节失败: {result.get('error')}")
    except Exception as e:
        put_text(f"❌ 错误: {e}")


def _do_clear(portfolio):
    try:
        count = portfolio.close_all("MANUAL")
        put_text(f"✅ 已清空 {count} 个持仓")
    except Exception as e:
        put_text(f"❌ 清空失败: {e}")


def _do_reset(optimizer):
    try:
        optimizer._arms.clear()
        put_text("✅ Bandit 已重置")
    except Exception as e:
        put_text(f"❌ 重置失败: {e}")
