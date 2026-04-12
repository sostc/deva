"""Bandit 自适应交易系统 UI"""

from datetime import datetime
from pywebio.output import *
from pywebio import session
import threading

from deva.naja.infra.ui.page_help import render_help_collapse
from deva.naja.register import SR
from deva import NB

_auto_refresh_enabled = True


def _render_four_dimensions_panel() -> str:
    """渲染四维决策框架状态面板"""
    try:
        from deva.naja.attention.kernel import (
            get_four_dimensions_manager,
            FourDimensions,
        )
        manager = get_four_dimensions_manager()

        if manager is None:
            return """
            <div style="
                background: linear-gradient(135deg, #fef3c7, #fde68a);
                border-radius: 10px;
                padding: 12px 14px;
                margin: 10px 0;
                border: 1px solid #f59e0b;
            ">
                <strong>🎯 四维决策框架</strong> 未启用管理器<br>
                <span style="font-size: 12px; color: #92400e;">
                    系统未初始化四维管理器，可以通过 AttentionKernel 启用
                </span>
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
            header_color = "#16a34a"
            header_bg = "linear-gradient(135deg, #dcfce7, #bbf7d0)"
            header_border = "#86efac"
            status_icon = "🟢 已启用"
        else:
            header_color = "#64748b"
            header_bg = "linear-gradient(135deg, #f1f5f9, #e2e8f0)"
            header_border = "#cbd5e1"
            status_icon = "⚪ 已关闭"

        time_status = "🟢 交易中" if fd.time.is_trading_open else "🔴 非交易时段"
        capital_bar = min(fd.capital.cash_ratio * 100, 100)
        capital_color = "#16a34a" if fd.capital.cash_ratio > 0.2 else "#dc2626"
        capital_status = "有子弹" if fd.capital.has_bullets else "⚠️ 子弹不足"
        capability_status = "🟢 就绪" if fd.capability.is_ready else "🔴 未就绪"

        if fd.market.liquidity_signal < 0.3:
            market_status = "🔴 极度恐慌"
            market_color = "#dc2626"
        elif fd.market.liquidity_signal > 0.7:
            market_status = "🟢 极度贪婪"
            market_color = "#16a34a"
        else:
            market_status = "🟡 中性"
            market_color = "#ca8a04"

        trigger_reason = trigger_status.get('trigger_reason', '无')
        should_enable = trigger_status.get('should_enable', False)

        return f"""
        <div style="
            background: {header_bg};
            border-radius: 10px;
            padding: 12px 14px;
            margin: 10px 0;
            border: 1px solid {header_border};
        ">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                <div>
                    <strong style="color: {header_color}; font-size: 14px;">🎯 四维决策框架</strong>
                    <span style="font-size: 12px; color: #64748b; margin-left: 8px;">
                        {'自动模式' if auto_mode else '手动模式'}
                    </span>
                </div>
                <div style="font-size: 14px;">{status_icon}</div>
            </div>

            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 10px;">
                <!-- 天时 -->
                <div style="background: white; border-radius: 6px; padding: 8px;">
                    <div style="font-size: 11px; color: #64748b; margin-bottom: 4px;">⏰ 天时</div>
                    <div style="font-size: 12px; color: #0f172a;">{time_status}</div>
                    <div style="font-size: 11px; color: #64748b;">压力: {fd.time.pressure:.0%}</div>
                </div>

                <!-- 资金 -->
                <div style="background: white; border-radius: 6px; padding: 8px;">
                    <div style="font-size: 11px; color: #64748b; margin-bottom: 4px;">💰 资金</div>
                    <div style="font-size: 12px; color: {capital_color};">{capital_status}</div>
                    <div style="background: #e2e8f0; border-radius: 3px; height: 6px; width: 100%; margin-top: 4px;">
                        <div style="background: {capital_color}; border-radius: 3px; height: 6px; width: {capital_bar}%;"></div>
                    </div>
                    <div style="font-size: 10px; color: #64748b;">现金: {fd.capital.cash_ratio:.0%}</div>
                </div>

                <!-- 能力 -->
                <div style="background: white; border-radius: 6px; padding: 8px;">
                    <div style="font-size: 11px; color: #64748b; margin-bottom: 4px;">🛠️ 能力</div>
                    <div style="font-size: 12px; color: #0f172a;">{capability_status}</div>
                    <div style="font-size: 11px; color: #64748b;">策略数: {fd.capability.strategy_count}</div>
                </div>

                <!-- 市场 -->
                <div style="background: white; border-radius: 6px; padding: 8px;">
                    <div style="font-size: 11px; color: #64748b; margin-bottom: 4px;">📊 市场</div>
                    <div style="font-size: 12px; color: {market_color};">{market_status}</div>
                    <div style="font-size: 11px; color: {market_color};">信号: {fd.market.liquidity_signal:.2f}</div>
                </div>
            </div>

            <div style="background: rgba(0,0,0,0.05); border-radius: 6px; padding: 8px; font-size: 11px;">
                <div style="display: flex; justify-content: space-between;">
                    <span style="color: #64748b;">自动触发:</span>
                    <span style="color: {'#16a34a' if should_enable else '#64748b'};">
                        {'✅ 满足条件' if should_enable else '❌ 不满足'}
                    </span>
                </div>
                <div style="display: flex; justify-content: space-between; margin-top: 4px;">
                    <span style="color: #64748b;">触发原因:</span>
                    <span style="color: #92400e;">{trigger_reason if trigger_reason else '-'}</span>
                </div>
            </div>
        </div>
        """
    except ImportError:
        return """
        <div style="
            background: linear-gradient(135deg, #f1f5f9, #e2e8f0);
            border-radius: 10px;
            padding: 12px 14px;
            margin: 10px 0;
            border: 1px solid #cbd5e1;
        ">
            <strong style="color: #64748b;">🎯 四维决策框架</strong><br>
            <span style="font-size: 12px; color: #94a3b8;">
                未安装四维模块（需要 attention.kernel.four_dimensions）
            </span>
        </div>
        """
    except Exception as e:
        return f"""
        <div style="
            background: linear-gradient(135deg, #fef2f2, #fee2e2);
            border-radius: 10px;
            padding: 12px 14px;
            margin: 10px 0;
            border: 1px solid #fca5a5;
        ">
            <strong style="color: #dc2626;">🎯 四维决策框架</strong> 加载失败<br>
            <span style="font-size: 12px; color: #991b1b;">{str(e)[:50]}</span>
        </div>
        """


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
        get_bandit_optimizer,
        get_market_observer,
    )
    
    cycle = SR('adaptive_cycle')
    optimizer = get_bandit_optimizer()
    portfolio = SR('virtual_portfolio')
    listener = SR('signal_listener')
    observer = get_market_observer()
    
    status = cycle.get_status()
    positions = cycle.get_positions()
    history = cycle.get_history(limit=20)
    bandit_stats = optimizer.get_all_stats()
    portfolio_summary = portfolio.get_summary()
    
    with use_scope("bandit_header"):
        put_html("<h2>🎰 Bandit 自适应交易系统</h2>")

        put_row([
            put_column([
                put_button("启动循环", onclick=lambda: _do_start(cycle), small=True),
                put_button("停止循环", onclick=lambda: _do_stop(cycle), small=True),
            ]),
            put_column([
                put_link("📊 盈亏归因分析", url="/bandit_attribution", new_window=False),
            ]),
        ], size="auto 1fr")

        put_text("")

        # 显示实验模式提示
        experiment_banner = _get_experiment_banner_html()
        if experiment_banner:
            put_html(experiment_banner)

        try:
            render_help_collapse("bandit")
        except Exception:
            pass
    
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
        put_html("<h3>💰 A股虚拟持仓</h3>")
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

    try:
        put_text("")
        put_html("<h3>🇺🇸 美股/港股持仓</h3>")

        us_account_names = []
        pm = None
        try:
            from deva.naja.bandit.portfolio_manager import get_portfolio_manager
            pm = get_portfolio_manager()
            if pm:
                us_account_names = pm.get_all_account_names()
                put_text(f"PM账户: {us_account_names}")
        except Exception as e:
            put_text(f"PM初始化失败: {e}")

        futu_nb_accounts = []
        try:
            nb = NB("naja_bandit_positions")
            accounts_data = nb.get("accounts", {})
            for acc_name, acc_data in accounts_data.items():
                if acc_data.get("account_type") == "futu":
                    futu_nb_accounts.append(acc_name)
            put_text(f"富途账户: {futu_nb_accounts}")
        except Exception as e:
            put_text(f"NB读取失败: {e}")

        all_account_names = us_account_names + futu_nb_accounts

        for account_name in all_account_names:
            portfolio = None
            futu_positions = None
            if pm and account_name in us_account_names:
                portfolio = pm.get_us_portfolio(account_name)
                if portfolio:
                    positions = portfolio.get_all_positions()
                    summary = portfolio.get_summary()
                else:
                    continue
            elif account_name in futu_nb_accounts:
                nb = NB("naja_bandit_positions")
                accounts_data = nb.get("accounts", {})
                acc_data = accounts_data.get(account_name, {})
                futu_positions = acc_data.get("positions", {})
                summary = {
                    "equity": acc_data.get("equity", 0),
                    "total_value": sum(p.get("current_price", 0) * p.get("quantity", 0) for p in futu_positions.values()),
                    "total_cost": sum(p.get("entry_price", 0) * p.get("quantity", 0) for p in futu_positions.values()),
                    "position_count": len(futu_positions),
                    "total_profit_loss": 0,
                    "total_return_pct": 0,
                    "today_profit_loss": 0,
                }
                positions = None
            else:
                continue

            account_label = f"【{account_name}】" + (" (Futu)" if account_name in futu_nb_accounts else "")
            put_html(f"<h4>{account_label}</h4>")

            equity = summary.get('equity', 0)
            margin_debt = summary.get('margin_debt', 0)
            today_pl = summary.get('today_profit_loss', 0)

            put_row([
                put_column([
                    put_html("<b>账户资产</b>"),
                    put_text(f"净资产: ${equity:,.2f}" if equity > 0 else "净资产: -"),
                    put_text(f"融资负债: ${margin_debt:,.2f}" if margin_debt > 0 else "融资负债: -"),
                ]),
                put_column([
                    put_html("<b>持仓市值</b>"),
                    put_text(f"总市值: ${summary['total_value']:,.2f}"),
                    put_text(f"持仓成本: ${summary['total_cost']:,.2f}" if summary['total_cost'] > 0 else "持仓成本: -"),
                ]),
            ], size="1fr 1fr")

            put_row([
                put_column([
                    put_html("<b>持仓统计</b>"),
                    put_text(f"持仓数: {summary['position_count']}"),
                ]),
                put_column([
                    put_html("<b>盈亏情况</b>"),
                    put_text(f"持仓盈亏: ${summary['total_profit_loss']:,.2f} ({summary['total_return_pct']:+.2f}%)"),
                    put_text(f"今日盈亏: ${today_pl:,.2f}" if today_pl != 0 else "今日盈亏: -"),
                ]),
            ], size="1fr 1fr")

            if futu_positions:
                html = """<table style='width:100%;border-collapse:collapse;font-size:14px;margin-top:8px;'>
                <tr style='background:#e8f4fc;'>
                    <th style='padding:8px;border:1px solid #ddd;'>股票名称</th>
                    <th style='padding:8px;border:1px solid #ddd;'>代码</th>
                    <th style='padding:8px;border:1px solid #ddd;'>持股数</th>
                    <th style='padding:8px;border:1px solid #ddd;'>入场价</th>
                    <th style='padding:8px;border:1px solid #ddd;'>现价</th>
                    <th style='padding:8px;border:1px solid #ddd;'>市值</th>
                </tr>"""

                for pos_id, pos in futu_positions.items():
                    html += f"""<tr>
                        <td style='padding:8px;border:1px solid #ddd;'>{pos.get('stock_name', '')}</td>
                        <td style='padding:8px;border:1px solid #ddd;'>{pos.get('stock_code', '').upper()}</td>
                        <td style='padding:8px;border:1px solid #ddd;'>{pos.get('quantity', 0)}</td>
                        <td style='padding:8px;border:1px solid #ddd;'>${pos.get('entry_price', 0):.2f}</td>
                        <td style='padding:8px;border:1px solid #ddd;'>${pos.get('current_price', 0):.2f}</td>
                        <td style='padding:8px;border:1px solid #ddd;'>${pos.get('current_price', 0) * pos.get('quantity', 0):.2f}</td>
                    </tr>"""

                html += "</table>"
                put_html(html)
            elif positions:
                html = """<table style='width:100%;border-collapse:collapse;font-size:14px;margin-top:8px;'>
                <tr style='background:#e8f4fc;'>
                    <th style='padding:8px;border:1px solid #ddd;'>股票名称</th>
                    <th style='padding:8px;border:1px solid #ddd;'>代码</th>
                    <th style='padding:8px;border:1px solid #ddd;'>持股数</th>
                    <th style='padding:8px;border:1px solid #ddd;'>现价</th>
                    <th style='padding:8px;border:1px solid #ddd;'>今日涨跌</th>
                    <th style='padding:8px;border:1px solid #ddd;'>市值</th>
                    <th style='padding:8px;border:1px solid #ddd;'>盈亏</th>
                </tr>"""

                for p in positions:
                    today_color = "green" if p.today_return_pct > 0 else "red" if p.today_return_pct < 0 else "gray"
                    today_sign = "+" if p.today_return_pct >= 0 else ""
                    html += f"""<tr>
                        <td style='padding:8px;border:1px solid #ddd;'>{p.stock_name}</td>
                        <td style='padding:8px;border:1px solid #ddd;'>{p.stock_code.upper()}</td>
                        <td style='padding:8px;border:1px solid #ddd;'>{p.quantity}</td>
                        <td style='padding:8px;border:1px solid #ddd;'>${p.current_price:.2f}</td>
                        <td style='padding:8px;border:1px solid #ddd;color:{today_color};font-weight:bold;'>{today_sign}{p.today_return_pct:.2f}%</td>
                        <td style='padding:8px;border:1px solid #ddd;'>${p.market_value:.2f}</td>
                        <td style='padding:8px;border:1px solid #ddd;color:{today_color};'>${p.today_profit_loss:+.2f}</td>
                    </tr>"""

                html += "</table>"
                put_html(html)
            else:
                put_text("  暂无持仓")
    except Exception as e:
        put_html(f"<p style='color:red;'>加载美股账户失败: {str(e)}</p>")

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
            put_column([
                put_button("🔄 同步富途持仓", onclick=_do_sync_futu, small=True),
                put_button("📊 富途账户", onclick=lambda: _do_show_futu_accounts(), small=True),
            ]),
        ], size="1fr 1fr 1fr")


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


def _do_sync_futu():
    try:
        from deva.naja.bandit.futu_portfolio_syncer import get_futu_syncer
        syncer = get_futu_syncer()
        if syncer.sync():
            put_text("✅ 富途持仓同步成功")
        else:
            put_text("⚠️ 富途持仓同步失败，请检查 OpenD 是否运行")
    except Exception as e:
        put_text(f"❌ 同步失败: {e}")


def _do_show_futu_accounts():
    try:
        from deva.naja.bandit.futu_portfolio_syncer import get_futu_syncer
        syncer = get_futu_syncer()
        accounts = syncer.get_accounts()
        if accounts:
            put_text("📊 富途账户列表:")
            for acc in accounts:
                put_text(f"  • {acc['security_firm']} - ID: {acc['acc_id']} ({acc['trd_env']})")
        else:
            put_text("⚠️ 未发现富途账户，请确认 OpenD 已登录")
    except Exception as e:
        put_text(f"❌ 获取账户失败: {e}")
