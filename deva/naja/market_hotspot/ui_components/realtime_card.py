"""实时市场热点卡片组件

提供实时推送的市场热点数据展示组件。
使用 SSE 订阅推送中心的数据，适合在页面中展示实时更新的市场热点数据。

使用方式：
    from deva.naja.market_hotspot.ui_components.realtime_card import SimpleRealtimeCard

    async def render_market_page(ctx):
        # 创建实时卡片
        card = SimpleRealtimeCard(ctx, scope="realtime_hotspot")
        await card.render()
"""

from __future__ import annotations

from typing import Dict, List, Optional


class SimpleRealtimeCard:
    """
    简化版实时卡片

    使用 SSE 订阅推送中心的数据并实时显示，适合快速集成。
    """

    def __init__(self, ctx: dict, scope: str = "simple_realtime"):
        self.ctx = ctx
        self.scope = scope

    async def render(self):
        """渲染卡片"""
        with self.ctx["use_scope"](self.scope, clear=True):
            self.ctx["put_html"](f'''
            <div id="realtime-card-{self.scope}" style="padding: 15px; background: #f8fafc; border-radius: 8px;">
                <div style="font-size: 14px; color: #64748b;">实时数据加载中...</div>
            </div>
            <script>
            (function() {{
                let updateCount = 0;

                function updateView(data) {{
                    console.log('[SimpleRealtimeCard] 收到数据:', data);

                    const cn = data.cn;
                    if (!cn) {{
                        console.log('[SimpleRealtimeCard] cn 为空');
                        document.getElementById('realtime-card-{self.scope}').innerHTML = '<div style="padding:20px;color:#666;">暂无数据</div>';
                        return;
                    }}

                    const blocks = cn.hot_blocks || [];
                    const stocks = cn.hot_stocks || [];

                    console.log('[SimpleRealtimeCard] blocks:', blocks.length, 'stocks:', stocks.length);

                    const blocksWithWeight = blocks.filter(function(b) {{ return (b.weight || 0) > 0; }});
                    const stocksWithWeight = stocks.filter(function(s) {{ return (s.weight || 0) > 0; }});

                    const blocksHtml = blocksWithWeight.slice(0, 8).map(function(b) {{
                        return '<span style="background: #dbeafe; padding: 3px 8px; border-radius: 4px; font-size: 12px; margin: 2px; display: inline-block;">' + (b.name || b.block_id || '') + ' ' + (b.weight || 0).toFixed(2) + '</span>';
                    }}).join('');

                    const stocksHtml = stocksWithWeight.slice(0, 10).map(function(s) {{
                        return '<span style="background: #dcfce7; padding: 3px 8px; border-radius: 4px; font-size: 12px; margin: 2px; display: inline-block;">' + (s.symbol || s.name || '') + ' ' + (s.weight || 0).toFixed(2) + '</span>';
                    }}).join('');

                    console.log('[SimpleRealtimeCard] blocksWithWeight:', blocksWithWeight.length, 'stocksWithWeight:', stocksWithWeight.length);

                    const html = '<div style="display: flex; justify-content: space-between; margin-bottom: 10px;">' +
                        '<strong style="font-size: 16px;">🔥 实时市场热点</strong>' +
                        '<span style="font-size: 12px; color: #64748b;">更新 #' + updateCount + ' - ' + new Date().toLocaleTimeString() + '</span>' +
                        '</div>' +
                        '<div style="margin-bottom: 8px;">' +
                        '<div style="font-size: 12px; color: #64748b; margin-bottom: 4px;">热点板块（' + blocksWithWeight.length + '个）</div>' +
                        '<div>' + (blocksHtml || '<span style="color: #999;">暂无热点板块</span>') + '</div>' +
                        '</div>' +
                        '<div>' +
                        '<div style="font-size: 12px; color: #64748b; margin-bottom: 4px;">热门股票（' + stocksWithWeight.length + '只）</div>' +
                        '<div>' + (stocksHtml || '<span style="color: #999;">暂无热门股票</span>') + '</div>' +
                        '</div>';

                    document.getElementById('realtime-card-{self.scope}').innerHTML = html;
                    console.log('[SimpleRealtimeCard] 更新完成');
                    updateCount++;
                }}

                async function fetchSnapshot() {{
                    try {{
                        const resp = await fetch('/api/market/hotspot');
                        const data = await resp.json();
                        updateView(data);
                    }} catch (e) {{
                        console.error('获取快照失败:', e);
                    }}
                }}

                fetchSnapshot();

                if (!window.NajaHotspotStream) {{
                    console.log('[SimpleRealtimeCard] 创建 window.NajaHotspotStream');
                    window.NajaHotspotStream = (function() {{
                        const listeners = [];
                        let source = null;

                        function connect() {{
                            if (source) return;
                            console.log('[SimpleRealtimeCard] 连接 SSE');
                            source = new EventSource('/api/market/hotspot/stream');
                            source.onmessage = function(event) {{
                                console.log('[SimpleRealtimeCard] SSE 收到消息');
                                try {{
                                    const data = JSON.parse(event.data);
                                    listeners.slice().forEach(function(listener) {{
                                        try {{
                                            listener(data);
                                            console.log('[SimpleRealtimeCard] listener 执行成功');
                                        }} catch (e) {{ console.error('[SimpleRealtimeCard] listener 执行失败:', e); }}
                                    }});
                                }} catch (e) {{ console.error('[SimpleRealtimeCard] 解析失败:', e); }}
                            }};
                            source.onerror = function(error) {{
                                console.error('[SimpleRealtimeCard] SSE 连接错误:', error);
                            }};
                        }}

                        return {{
                            subscribe: function(listener) {{
                                console.log('[SimpleRealtimeCard] 订阅新 listener');
                                listeners.push(listener);
                                connect();
                                return function() {{
                                    const index = listeners.indexOf(listener);
                                    if (index >= 0) listeners.splice(index, 1);
                                }};
                            }}
                        }};
                    }})();
                }} else {{
                    console.log('[SimpleRealtimeCard] window.NajaHotspotStream 已存在');
                }}

                console.log('[SimpleRealtimeCard] 调用 subscribe');
                window.NajaHotspotStream.subscribe(updateView);
                console.log('[SimpleRealtimeCard] 订阅完成');
            }})();
            </script>
            ''')


def create_simple_realtime_card(ctx: dict, **kwargs) -> SimpleRealtimeCard:
    """便捷函数：创建简化版实时卡片"""
    return SimpleRealtimeCard(ctx, **kwargs)


__all__ = [
    "SimpleRealtimeCard",
    "create_simple_realtime_card",
]
