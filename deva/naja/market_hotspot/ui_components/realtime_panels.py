"""实时面板渲染器

提供统一的实时面板渲染功能，支持多个面板定时更新。

使用方式：
    from deva.naja.market_hotspot.ui_components.realtime_panels import RealtimePanelRenderer

    async def render_page(ctx):
        renderer = RealtimePanelRenderer(ctx)

        # 添加需要实时更新的面板
        renderer.add_panel("market_state", render_market_state_panel, interval=10)
        renderer.add_panel("hotspot_flow", render_hotspot_flow_ui, interval=10)
        renderer.add_panel("hotspot_changes", lambda: render_hotspot_changes(_get_hotspot_changes_impl()), interval=10)

        # 渲染所有面板（包含 JS 轮询代码）
        await renderer.render_all()
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass

from deva.naja.infra.ui import RealtimePusher


@dataclass
class PanelConfig:
    """面板配置"""
    name: str
    render_func: Callable[[], str]
    scope_id: Optional[str] = None


class RealtimePanelRenderer:
    """
    实时面板渲染器

    统一管理多个需要实时更新的面板，提供：
    1. 一次性渲染所有面板
    2. 自动注入 SSE 推送订阅代码
    3. 所有面板同时更新（服务端主动推送）
    """

    def __init__(self, ctx: dict, container_scope: str = "realtime_panels"):
        """
        初始化实时面板渲染器

        Args:
            ctx: PyWebIO 上下文
            container_scope: 容器 scope 名称
        """
        self.ctx = ctx
        self.container_scope = container_scope
        self._panels: List[PanelConfig] = []
        self._pusher: Optional[RealtimePusher] = None

    def add_panel(self, name: str, render_func: Callable[[], str],
                  scope_id: str = None):
        """
        添加实时面板

        Args:
            name: 面板名称（用于 JS 中的 id）
            render_func: 渲染函数，返回 HTML 字符串
            scope_id: 自定义 scope id，默认使用 name
        """
        self._panels.append(PanelConfig(
            name=name,
            render_func=render_func,
            scope_id=scope_id or name
        ))

    async def render_all(self):
        """渲染所有面板（包含 SSE 推送订阅代码）"""
        if not self._panels:
            return

        with self.ctx["use_scope"](self.container_scope, clear=True):
            for panel in self._panels:
                self.ctx["put_html"](f'<div id="panel-{panel.scope_id}"></div>')

            self.ctx["put_html"](self._generate_js())

    def _generate_js(self) -> str:
        """生成 JavaScript SSE 订阅代码"""
        panels_config = []
        for panel in self._panels:
            panels_config.append({
                "name": panel.name,
                "scope_id": panel.scope_id
            })

        import json
        panels_json = json.dumps(panels_config)

        return f'''
        <script>
        (function() {{
            const PANELS = {panels_json};

            function updatePanel(panel, data) {{
                try {{
                    let html = '';

                    if (panel.name === 'market_state') {{
                        html = renderMarketState(data);
                    }} else if (panel.name === 'hotspot_flow') {{
                        html = renderHotspotFlow(data);
                    }} else if (panel.name === 'hotspot_changes') {{
                        html = renderHotspotChanges(data);
                    }} else if (panel.name === 'strategy_status') {{
                        html = renderStrategyStatus(data);
                    }} else if (panel.name === 'dual_engine') {{
                        html = renderDualEngine(data);
                    }} else if (panel.name === 'micro_changes') {{
                        html = renderMicroChanges(data);
                    }} else if (panel.name === 'recent_signals') {{
                        html = renderRecentSignals(data);
                    }} else {{
                        html = '<div style="padding:10px;color:#666;">Panel: ' + panel.name + '</div>';
                    }}

                    const el = document.getElementById('panel-' + panel.scope_id);
                    if (el) {{
                        el.innerHTML = html;
                    }}
                }} catch (e) {{
                    console.error('Update panel ' + panel.name + ' failed:', e);
                }}
            }}

            function updateAllPanels(data) {{
                for (const panel of PANELS) {{
                    updatePanel(panel, data);
                }}
            }}

            function renderMarketState(data) {{
                const cn = data.cn || {{}};
                const globalHotspot = cn.market_hotspot || 0;
                const activity = cn.market_activity || 0;
                const hotspotLevel = globalHotspot >= 0.6 ? '🔥高集中' : (globalHotspot >= 0.3 ? '📊中集中' : '💤分散');

                return '<div style="background: white; border: 1px solid #e2e8f0; border-radius: 12px; padding: 16px; margin-top: 12px;">' +
                    '<div style="font-weight: 600; margin-bottom: 12px; color: #1e293b;">📊 市场热点状态</div>' +
                    '<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">' +
                    '<div style="background: #f8fafc; padding: 12px; border-radius: 8px;">' +
                    '<div style="font-size: 11px; color: #64748b;">市场聚焦度</div>' +
                    '<div style="font-size: 20px; font-weight: bold; color: #3b82f6;">' + globalHotspot.toFixed(3) + '</div>' +
                    '<div style="font-size: 11px; color: #64748b;">' + hotspotLevel + '</div>' +
                    '</div>' +
                    '<div style="background: #f8fafc; padding: 12px; border-radius: 8px;">' +
                    '<div style="font-size: 11px; color: #64748b;">市场活跃度</div>' +
                    '<div style="font-size: 20px; font-weight: bold; color: #10b981;">' + activity.toFixed(3) + '</div>' +
                    '</div>' +
                    '</div></div>';
            }}

            function renderHotspotFlow(data) {{
                const cn = data.cn || {{}};
                const blocks = cn.hot_blocks || [];
                const stocks = cn.hot_stocks || [];

                if (blocks.length === 0 && stocks.length === 0) {{
                    return '<div style="padding: 20px; text-align: center; color: #64748b;">暂无热点数据</div>';
                }}

                const blocksHtml = blocks.slice(0, 6).map(function(b) {{
                    const weight = b.weight || 0;
                    const color = weight > 0.4 ? '#dc2626' : (weight > 0.2 ? '#f59e0b' : '#64748b');
                    const bgColor = color === '#dc2626' ? 'fee2e2' : (color === '#f59e0b' ? 'fef3c7' : 'f1f5f9');
                    return '<span style="background: #' + bgColor + '; padding: 4px 10px; border-radius: 4px; font-size: 12px; margin: 2px; display: inline-block;">' + (b.name || b.block_id || '') + ' ' + weight.toFixed(3) + '</span>';
                }}).join('');

                const stocksHtml = stocks.slice(0, 8).map(function(s) {{
                    const weight = s.weight || 0;
                    return '<span style="background: #dbeafe; padding: 3px 8px; border-radius: 4px; font-size: 11px; margin: 2px; display: inline-block;">' + (s.symbol || s.name || '') + ' ' + weight.toFixed(3) + '</span>';
                }}).join('');

                return '<div style="background: white; border: 1px solid #e2e8f0; border-radius: 12px; padding: 16px; margin-top: 12px;">' +
                    '<div style="font-weight: 600; margin-bottom: 12px; color: #1e293b;">🔥 热点流向</div>' +
                    '<div style="margin-bottom: 12px;">' +
                    '<div style="font-size: 12px; color: #64748b; margin-bottom: 8px;">热点板块</div>' +
                    '<div>' + (blocksHtml || '<span style="color: #94a3b8;">暂无</span>') + '</div>' +
                    '</div>' +
                    '<div>' +
                    '<div style="font-size: 12px; color: #64748b; margin-bottom: 8px;">热门股票</div>' +
                    '<div>' + (stocksHtml || '<span style="color: #94a3b8;">暂无</span>') + '</div>' +
                    '</div></div>';
            }}

            function renderHotspotChanges(data) {{
                return '<div style="background: white; border: 1px solid #e2e8f0; border-radius: 12px; padding: 16px; margin-top: 12px;">' +
                    '<div style="font-weight: 600; margin-bottom: 12px; color: #1e293b;">📈 热点变化</div>' +
                    '<div style="font-size: 12px; color: #64748b; text-align: center; padding: 20px;">点击查看详细变化记录</div></div>';
            }}

            function renderStrategyStatus(data) {{
                const processed = data.processed_snapshots || 0;
                return '<div style="background: white; border: 1px solid #e2e8f0; border-radius: 12px; padding: 16px; margin-top: 12px;">' +
                    '<div style="font-weight: 600; margin-bottom: 12px; color: #1e293b;">🧠 策略状态</div>' +
                    '<div style="font-size: 12px; color: #64748b;">已处理快照: ' + processed + '</div></div>';
            }}

            function renderDualEngine(data) {{
                return '<div style="background: white; border: 1px solid #e2e8f0; border-radius: 12px; padding: 16px; margin-top: 12px;">' +
                    '<div style="font-weight: 600; margin-bottom: 12px; color: #1e293b;">⚙️ 双引擎</div>' +
                    '<div style="font-size: 12px; color: #64748b;">实时监测中...</div></div>';
            }}

            function renderMicroChanges(data) {{
                return '<div style="background: white; border: 1px solid #e2e8f0; border-radius: 12px; padding: 16px; margin-top: 12px;">' +
                    '<div style="font-weight: 600; margin-bottom: 12px; color: #1e293b;">📊 微变化监测</div>' +
                    '<div style="font-size: 12px; color: #64748b;">实时监测中...</div></div>';
            }}

            function renderRecentSignals(data) {{
                return '<div style="background: white; border: 1px solid #e2e8f0; border-radius: 12px; padding: 16px; margin-top: 12px;">' +
                    '<div style="font-weight: 600; margin-bottom: 12px; color: #1e293b;">📡 最近信号</div>' +
                    '<div style="font-size: 12px; color: #64748b;">实时更新中...</div></div>';
            }}

            async function fetchSnapshot() {{
                try {{
                    const resp = await fetch('/api/market/hotspot');
                    const data = await resp.json();
                    updateAllPanels(data);
                }} catch (e) {{
                    console.error('获取快照失败:', e);
                }}
            }}

            fetchSnapshot();

            if (!window.NajaHotspotStream) {{
                window.NajaHotspotStream = (function() {{
                        const listeners = [];
                        let source = null;

                        function connect() {{
                            if (source) return;
                            source = new EventSource('/api/market/hotspot/stream');
                            source.onmessage = function(event) {{
                                try {{
                                    const data = JSON.parse(event.data);
                                    listeners.slice().forEach(function(listener) {{
                                        try {{ listener(data); }} catch (e) {{ console.error('Hotspot listener failed:', e); }}
                                    }});
                                }} catch (e) {{
                                    console.error('Hotspot stream parse failed:', e);
                                }}
                            }};
                            source.onerror = function(error) {{
                                console.error('Hotspot SSE connection failed:', error);
                                if (source) {{
                                    source.close();
                                    source = null;
                                }}
                            }};
                        }}

                        return {{
                            subscribe: function(listener) {{
                                listeners.push(listener);
                                connect();
                                return function() {{
                                    const index = listeners.indexOf(listener);
                                    if (index >= 0) listeners.splice(index, 1);
                                }};
                            }}
                        }};
                    }})();
            }}

            window.NajaHotspotStream.subscribe(updateAllPanels);
        }})();
        </script>
        '''


def create_realtime_renderer(ctx: dict, **kwargs) -> RealtimePanelRenderer:
    """便捷函数：创建实时面板渲染器"""
    return RealtimePanelRenderer(ctx, **kwargs)


__all__ = [
    "RealtimePanelRenderer",
    "create_realtime_renderer",
]
