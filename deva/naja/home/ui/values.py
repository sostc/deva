"""首页价值观展示区域 — 持仓、关注、供需问题、流动性"""


def render_values_section() -> str:
    """渲染价值观展示区域 - 展示持仓、关注和供需问题"""
    holdings_html = ""
    watchlist_html = ""
    dynamics_html = ""
    liquidity_html = ""

    try:
        from deva.naja.attention.portfolio import Portfolio
        pf = Portfolio()
        holdings = pf.get_holdings()
        watchlist = pf.get_watchlist()

        if holdings:
            for h in holdings[:5]:
                return_color = "#4ade80" if h.return_pct >= 0 else "#f43f5e"
                return_sign = "+" if h.return_pct >= 0 else ""
                holdings_html += f'''<div style="padding:8px 12px;background:rgba(255,255,255,0.05);border-radius:8px;margin:4px 0;display:flex;justify-content:space-between;">
                    <span style="color:#fff;font-weight:600;">{h.name}</span>
                    <span style="color:{return_color};">{return_sign}{h.return_pct:.1f}%</span>
                </div>'''
        else:
            holdings_html = '<div style="color:#64748b;font-size:12px;padding:10px;">暂无持仓</div>'

        if watchlist:
            for w in watchlist[:5]:
                watchlist_html += f'''<div style="padding:6px 10px;background:rgba(96,165,250,0.1);border-radius:6px;margin:4px 0;color:#60a5fa;font-size:12px;">
                    {w.name}
                </div>'''
        else:
            watchlist_html = '<div style="color:#64748b;font-size:12px;padding:10px;">暂无自选</div>'

    except Exception as e:
        holdings_html = f'<div style="color:#64748b;font-size:12px;padding:10px;">暂无持仓 ({str(e)[:30]})</div>'
        watchlist_html = '<div style="color:#64748b;font-size:12px;padding:10px;">暂无自选</div>'

    dynamics_data = None
    try:
        from deva.naja.cognition.narrative import get_narrative_tracker
        tracker = get_narrative_tracker()
        if tracker:
            dynamics_data = tracker.get_value_market_summary()

        if dynamics_data and dynamics_data.get("value_signals"):
            signals = list(dynamics_data.get("value_signals", {}).items())[:5]
            for signal_type, signal_data in signals:
                dynamics_html += f'''<div style="padding:6px 10px;background:rgba(251,191,36,0.1);border-radius:6px;margin:4px 0;color:#fbbf24;font-size:12px;">
                    ⚡ {signal_type}
                </div>'''
        if not dynamics_html:
            dynamics_html = '<div style="color:#64748b;font-size:12px;padding:10px;">暂无供需问题</div>'
    except Exception as e:
        dynamics_html = f'<div style="color:#64748b;font-size:12px;padding:10px;">暂无供需问题 ({str(e)[:50]})</div>'

    try:
        from deva.naja.radar import get_global_market_scanner
        scanner = get_global_market_scanner()
        alerts = scanner.get_alerts(limit=5)

        if alerts:
            for alert in alerts:
                severity = getattr(alert, 'severity', 'unknown') if hasattr(alert, 'severity') else 'unknown'
                alert_html = f'''<div style="padding:6px 10px;background:rgba(168,85,247,0.1);border-radius:6px;margin:4px 0;color:#a855f7;font-size:12px;">
                    🌊 {severity}
                </div>'''
                liquidity_html += alert_html
        if not liquidity_html:
            liquidity_html = '<div style="color:#64748b;font-size:12px;padding:10px;">暂无流动性预警</div>'
    except Exception as e:
        liquidity_html = f'<div style="color:#64748b;font-size:12px;padding:10px;">暂无流动性预警 ({str(e)[:50]})</div>'

    block_section = f'''
        <div style="background: linear-gradient(135deg, rgba(34,197,94,0.2) 0%, rgba(34,197,94,0.05) 100%); border-radius: 12px; padding: 20px; border: 1px solid rgba(34,197,94,0.3);">
            <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 15px;">
                <span style="font-size: 28px;">🚀</span>
                <div>
                    <div style="font-size: 16px; font-weight: 600; color: #22c55e;">赛道投资（核心）</div>
                    <div style="font-size: 11px; color: #94a3b8;">投资先进生产力 · 代表人民利益 · 先进文化方向</div>
                </div>
            </div>
            <div style="font-size: 12px; color: #64748b; margin-bottom: 10px;">📊 已实现的投资</div>
            <div>{holdings_html}</div>
        </div>'''

    watchlist_section = f'''
        <div style="background: rgba(96,165,250,0.1); border-radius: 12px; padding: 16px; border: 1px solid rgba(96,165,250,0.2);">
            <div style="font-size: 14px; font-weight: 600; color: #60a5fa; margin-bottom: 10px;">📈 正在关注</div>
            <div>{watchlist_html}</div>
        </div>'''

    dynamics_section = f'''
        <div style="background: rgba(251,191,36,0.1); border-radius: 12px; padding: 16px; border: 1px solid rgba(251,191,36,0.2); margin-top: 15px;">
            <div style="font-size: 14px; font-weight: 600; color: #fbbf24; margin-bottom: 10px;">⚡ 供需问题挖掘</div>
            <div>{dynamics_html}</div>
        </div>'''

    liquidity_section = f'''
        <div style="background: rgba(168,85,247,0.1); border-radius: 12px; padding: 16px; border: 1px solid rgba(168,85,247,0.2); margin-top: 15px;">
            <div style="font-size: 14px; font-weight: 600; color: #a855f7; margin-bottom: 10px;">🌊 流动性机会</div>
            <div>{liquidity_html}</div>
        </div>'''

    link_html = '''
        <div style="margin-top: 20px; text-align: center;">
            <a href="/market" style="display: inline-block; padding: 10px 24px; background: linear-gradient(135deg, #00d4ff 0%, #0099cc 100%); border-radius: 20px; color: white; text-decoration: none; font-size: 13px; font-weight: 500;">
                📊 进入市场热点监测 →
            </a>
        </div>'''

    return '''
    <div style="margin-top: 30px; padding: 30px; background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); border-radius: 16px; box-shadow: 0 10px 40px rgba(0,0,0,0.2);">
        <h3 style="color: #fff; margin-bottom: 10px; text-align: center; font-size: 22px;">🎯 我们的使命：发现问题 · 解决问题 · 推动世界发展</h3>
        <p style="color: #94a3b8; text-align: center; margin-bottom: 25px; font-size: 13px;">
            领先于市场观察，验证我们的判断，赚钱是为了让改变世界可持续
        </p>

        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
            <div>''' + block_section + watchlist_section + '''</div>
            <div>''' + dynamics_section + liquidity_section + '''</div>
        </div>

        ''' + link_html + '''
    </div>
    '''
