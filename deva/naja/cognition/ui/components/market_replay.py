"""
Market Replay 组件
"""

import json


def render_market_replay(ui):
    from deva.naja.strategy.market_replay_analyzer import get_replay_history

    history = get_replay_history(limit=10)

    from pywebio.output import put_html

    if history:
        latest = history[0]
        put_html("""
        <div style="margin-top: 12px; padding: 12px; background: rgba(34,197,94,0.08); border-radius: 8px; border: 1px solid rgba(34,197,94,0.2);">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                <div style="font-size: 12px; font-weight: 600; color: #4ade80;">📊 市场复盘</div>
                <div style="font-size: 10px; color: #64748b;">""" + latest.get("time_str", "") + """</div>
            </div>
            <div style="display: flex; gap: 16px; font-size: 11px;">
                <div style="color: #94a3b8;">情绪: <span style="color: #e2e8f0;">""" + latest.get("market_sentiment", "未知") + """</span></div>
                <div style="color: #94a3b8;">均幅: <span style="color: #e2e8f0;">""" + f"{latest.get('avg_change', 0):+.2f}%" + """</span></div>
                <div style="color: #94a3b8;">广度: <span style="color: #e2e8f0;">""" + f"{latest.get('market_breadth', 0):.3f}" + """</span></div>
            </div>
        </div>
        """)

        if len(history) > 1:
            put_html('<div style="margin-top: 8px; font-size: 11px; color: #94a3b8;">📋 历史复盘记录：</div>')
            for i, h in enumerate(history[1:6], 1):
                ts = h.get('time_str', '')[:16]
                sentiment = h.get('market_sentiment', '未知')
                avg_change = h.get('avg_change', 0)
                top_narrative = h.get('top_narrative', '无')
                idx = i
                put_html(f"""
                <div style="margin-top: 6px; padding: 8px; background: rgba(255,255,255,0.03); border-radius: 6px; border: 1px solid rgba(255,255,255,0.06);">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div style="font-size: 11px;">
                            <span style="color: #64748b;">{ts}</span>
                            <span style="color: #e2e8f0; margin-left: 8px;">{sentiment}</span>
                            <span style="color: #94a3b8; margin-left: 8px;">{avg_change:+.1f}%</span>
                            <span style="color: #64748b; margin-left: 8px;">{top_narrative}</span>
                        </div>
                        <button onclick="showReplayDetail({idx})" style="background: rgba(34,197,94,0.2); border: 1px solid rgba(34,197,94,0.3); color: #4ade80; padding: 2px 8px; border-radius: 4px; cursor: pointer; font-size: 10px;">查看</button>
                    </div>
                </div>
                """)

            put_html(f"""
            <script>
            function showReplayDetail(idx) {{
                const history = {json.dumps(history[1:6])};
                const item = history[idx - 1];
                if (item && item.markdown) {{
                    alert(item.markdown);
                }}
            }}
            </script>
            """)
    else:
        render_market_replay_empty()


def render_market_replay_empty(ui):
    from pywebio.output import put_html
    put_html("""
    <div style="text-align: center; padding: 24px; color: #64748b; font-size: 12px;">
        <div style="font-size: 24px; margin-bottom: 8px;">📊</div>
        <div>暂无市场复盘数据</div>
    </div>
    """)