"""Radar UI - 感知层

拆分结构：
  constants.py   — 时间格式化、事件徽章渲染、交易时段映射
  header.py      — 页面标题 + 统计卡片
  panels.py      — 新闻获取器面板 + 工作引擎状态面板
  liquidity.py   — 流动性预测面板 + 通知历史
  events.py      — 事件类型分布 + 事件时间线
  controls.py    — 控制面板 + 刷新/清空
"""

from pywebio.output import put_html
from pywebio.session import run_js

from .constants import _fmt_time, _render_event_badge
from .header import render_header
from .panels import render_news_fetcher_panel, render_engine_status_panel
from .liquidity import render_liquidity_prediction_panel
from .events import render_stats_overview, render_event_timeline
from .controls import render_control_panel


class RadarUI:
    """雷达感知层 UI"""

    def __init__(self):
        from ..engine import get_radar_engine
        self.engine = get_radar_engine()

    def render(self):
        """渲染主页面"""
        from pywebio.session import set_env
        from deva.naja.infra.ui.ui_theme import get_global_styles, get_nav_menu_js

        set_env(title="Naja - 雷达", output_animation=False)
        put_html(get_global_styles())

        nav_js = get_nav_menu_js()
        switch_theme_js = """
            window.switchTheme = function(name) {
                document.cookie = 'naja-theme=' + name + '; path=/; max-age=31536000';
                document.body.style.opacity = '0';
                setTimeout(function() { location.reload(); }, 150);
            };
        """

        run_js("setTimeout(function(){" + nav_js + "}, 50);")
        run_js(switch_theme_js)

        from deva.naja.infra.ui.ui_theme import get_current_theme_config
        theme = get_current_theme_config()

        put_html('<div class="container">')
        render_header(self.engine)
        render_news_fetcher_panel(self.engine)
        render_engine_status_panel(self.engine)
        render_stats_overview(self.engine)
        render_event_timeline(self.engine)
        self._render_radar_logic()
        render_liquidity_prediction_panel(self.engine)
        render_control_panel(self.engine)
        put_html('</div>')

    def _render_radar_logic(self):
        """渲染雷达感知逻辑说明 - 详细工作原理"""
        from deva.naja.cognition.ui.system_architecture import get_radar_architecture_doc
        put_html(get_radar_architecture_doc())


def main():
    """主入口"""
    ui = RadarUI()
    ui.render()


if __name__ == "__main__":
    main()
