"""实时市场热点卡片组件

提供实时推送的市场热点数据展示组件。
用于在页面中展示实时更新的市场热点数据。

使用方式：
    from deva.naja.market_hotspot.ui_components.realtime_card import RealtimeHotspotCard

    async def render_market_page(ctx):
        # 创建实时卡片
        card = RealtimeHotspotCard(ctx, scope="realtime_hotspot")
        await card.render()
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

from deva.naja.infra.ui import RealtimePusher
from deva.naja.market_hotspot.push_center import get_push_center


@dataclass
class HotspotDisplayData:
    """热点展示数据"""
    timestamp: float
    market: str
    global_hotspot: float
    activity: float
    hot_blocks: List[Dict[str, Any]]
    hot_stocks: List[Dict[str, Any]]


class RealtimeHotspotCard:
    """
    实时市场热点卡片

    订阅推送中心的数据，并实时显示在 PyWebIO 页面上。
    """

    def __init__(self, ctx: dict, scope: str = "realtime_hotspot",
                 show_blocks: bool = True,
                 show_stocks: bool = True,
                 max_blocks: int = 8,
                 max_stocks: int = 10,
                 title: str = None):
        """
        初始化实时热点卡片

        Args:
            ctx: PyWebIO 上下文
            scope: scope 名称
            show_blocks: 是否显示热点板块
            show_stocks: 是否显示热门股票
            max_blocks: 最多显示板块数
            max_stocks: 最多显示股票数
            title: 卡片标题
        """
        self.ctx = ctx
        self.scope = scope
        self.show_blocks = show_blocks
        self.show_stocks = show_stocks
        self.max_blocks = max_blocks
        self.max_stocks = max_stocks
        self.title = title or "实时市场热点"

        self._pusher: Optional[RealtimePusher] = None
        self._last_data: Optional[HotspotDisplayData] = None

    def _get_push_center(self):
        """获取推送中心"""
        return get_push_center()

    def _format_timestamp(self, ts: float) -> str:
        """格式化时间戳"""
        return time.strftime("%H:%M:%S", time.localtime(ts))

    def _render_html(self, data: HotspotDisplayData) -> str:
        """渲染热点数据为 HTML"""
        lines = []

        lines.append(f'<div style="padding: 10px; background: #f8fafc; border-radius: 8px; margin: 10px 0;">')

        lines.append(f'<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">')
        lines.append(f'<h3 style="margin: 0; color: #1e293b;">{self.title}</h3>')
        lines.append(f'<span style="font-size: 12px; color: #64748b;">{self._format_timestamp(data.timestamp)}</span>')
        lines.append(f'</div>')

        lines.append(f'<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 12px;">')
        lines.append(f'<div style="background: white; padding: 8px 12px; border-radius: 6px; box-shadow: 0 1px 2px rgba(0,0,0,0.05);">')
        lines.append(f'<div style="font-size: 11px; color: #64748b;">市场聚焦度</div>')
        lines.append(f'<div style="font-size: 18px; font-weight: bold; color: #3b82f6;">{data.global_hotspot:.2%}</div>')
        lines.append(f'</div>')
        lines.append(f'<div style="background: white; padding: 8px 12px; border-radius: 6px; box-shadow: 0 1px 2px rgba(0,0,0,0.05);">')
        lines.append(f'<div style="font-size: 11px; color: #64748b;">市场活跃度</div>')
        lines.append(f'<div style="font-size: 18px; font-weight: bold; color: #10b981;">{data.activity:.2%}</div>')
        lines.append(f'</div>')
        lines.append(f'</div>')

        if self.show_blocks and data.hot_blocks:
            lines.append(f'<div style="margin-bottom: 8px;">')
            lines.append(f'<div style="font-size: 12px; font-weight: 600; color: #475569; margin-bottom: 6px;">🔥 热点板块</div>')
            lines.append(f'<div style="display: flex; flex-wrap: wrap; gap: 6px;">')
            for block in data.hot_blocks[:self.max_blocks]:
                weight = block.get('weight', 0)
                bg_color = self._get_weight_color(weight)
                lines.append(f'<span style="background: {bg_color}; padding: 4px 8px; border-radius: 4px; font-size: 12px;">{block.get("name", block.get("block_id", ""))} {weight:.2%}</span>')
            lines.append(f'</div>')
            lines.append(f'</div>')

        if self.show_stocks and data.hot_stocks:
            lines.append(f'<div>')
            lines.append(f'<div style="font-size: 12px; font-weight: 600; color: #475569; margin-bottom: 6px;">📈 热门股票</div>')
            lines.append(f'<div style="display: flex; flex-wrap: wrap; gap: 6px;">')
            for stock in data.hot_stocks[:self.max_stocks]:
                weight = stock.get('weight', 0)
                bg_color = self._get_weight_color(weight)
                lines.append(f'<span style="background: {bg_color}; padding: 4px 8px; border-radius: 4px; font-size: 12px;">{stock.get("name", stock.get("symbol", ""))} {weight:.2%}</span>')
            lines.append(f'</div>')
            lines.append(f'</div>')

        lines.append(f'</div>')

        return ''.join(lines)

    def _get_weight_color(self, weight: float) -> str:
        """根据权重获取背景颜色"""
        if weight > 0.5:
            return "#fef3c7"
        elif weight > 0.3:
            return "#dbeafe"
        elif weight > 0.1:
            return "#e0e7ff"
        else:
            return "#f1f5f9"

    def _convert_to_display_data(self, data: Dict[str, Any]) -> HotspotDisplayData:
        """将推送数据转换为展示数据"""
        return HotspotDisplayData(
            timestamp=data.get('timestamp', time.time()),
            market=data.get('market', 'CN'),
            global_hotspot=data.get('global_hotspot', 0.0),
            activity=data.get('activity', 0.0),
            hot_blocks=data.get('hot_blocks', []),
            hot_stocks=data.get('hot_stocks', []),
        )

    async def render(self):
        """渲染卡片（同步方式，使用最新的缓存数据）"""
        push_center = self._get_push_center()
        latest_data = push_center.get_latest_data() if push_center else None

        self._pusher = RealtimePusher(self.ctx, self.scope)

        with self.ctx["use_scope"](self.scope, clear=True):
            if latest_data:
                display_data = self._convert_to_display_data(latest_data)
                self.ctx["put_html"](self._render_html(display_data))
            else:
                self.ctx["put_html"](f'''
                <div style="padding: 20px; text-align: center; color: #64748b;">
                    <div style="font-size: 14px;">{self.title}</div>
                    <div style="font-size: 12px; margin-top: 8px;">等待数据...</div>
                </div>
                ''')

        if latest_data:
            self._last_data = self._convert_to_display_data(latest_data)

    def start_realtime_updates(self):
        """启动实时更新（需要在页面渲染后调用）"""
        if self._pusher is None:
            self._pusher = RealtimePusher(self.ctx, self.scope)

        push_center = self._get_push_center()
        if push_center is None:
            return

        stream = push_center.get_stream()

        def on_data(data):
            if isinstance(data, dict):
                display_data = self._convert_to_display_data(data)
            else:
                return

            self._last_data = display_data
            self._pusher.clear()
            self._pusher.push_html(self._render_html(display_data))

        stream.sink(on_data)

    def stop_realtime_updates(self):
        """停止实时更新"""
        if self._pusher:
            self._pusher.stop_auto_push()


class SimpleRealtimeCard:
    """
    简化版实时卡片

    直接从推送中心获取数据并显示，适合快速集成。
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
                let lastData = null;
                let updateCount = 0;

                async function fetchAndUpdate() {{
                    try {{
                        const resp = await fetch('/api/market/hotspot');
                        const data = await resp.json();

                        if (data && data.cn) {{
                            const cn = data.cn;
                            const blocks = cn.hot_blocks || [];
                            const stocks = cn.hot_stocks || [];

                            const blocksHtml = blocks.slice(0, 8).map(b =>
                                `<span style="background: #dbeafe; padding: 3px 8px; border-radius: 4px; font-size: 12px; margin: 2px; display: inline-block;">${{b.name}} ${{(b.weight || 0).toFixed(2)}}</span>`
                            ).join('');

                            const stocksHtml = stocks.slice(0, 10).map(s =>
                                `<span style="background: #dcfce7; padding: 3px 8px; border-radius: 4px; font-size: 12px; margin: 2px; display: inline-block;">${{s.symbol || s.name}} ${{(s.weight || 0).toFixed(2)}}</span>`
                            ).join('');

                            const html = `
                                <div style="display: flex; justify-content: space-between; margin-bottom: 10px;">
                                    <strong style="font-size: 16px;">🔥 实时市场热点</strong>
                                    <span style="font-size: 12px; color: #64748b;">更新 #${"{{updateCount}}"} - ${{new Date().toLocaleTimeString()}}</span>
                                </div>
                                <div style="margin-bottom: 8px;">
                                    <div style="font-size: 12px; color: #64748b; margin-bottom: 4px;">热点板块</div>
                                    <div>${{blocksHtml || '<span style="color: #999;">暂无数据</span>'}}</div>
                                </div>
                                <div>
                                    <div style="font-size: 12px; color: #64748b; margin-bottom: 4px;">热门股票</div>
                                    <div>${{stocksHtml || '<span style="color: #999;">暂无数据</span>'}}</div>
                                </div>
                            `;

                            document.getElementById('realtime-card-{self.scope}').innerHTML = html;
                            updateCount++;
                        }}
                    }} catch (e) {{
                        console.error('获取数据失败:', e);
                    }}
                }}

                fetchAndUpdate();
                setInterval(fetchAndUpdate, 10000);
            }})();
            </script>
            ''')


def create_realtime_card(ctx: dict, **kwargs) -> RealtimeHotspotCard:
    """便捷函数：创建实时热点卡片"""
    return RealtimeHotspotCard(ctx, **kwargs)


def create_simple_realtime_card(ctx: dict, **kwargs) -> SimpleRealtimeCard:
    """便捷函数：创建简化版实时卡片"""
    return SimpleRealtimeCard(ctx, **kwargs)


__all__ = [
    "RealtimeHotspotCard",
    "SimpleRealtimeCard",
    "create_realtime_card",
    "create_simple_realtime_card",
]
