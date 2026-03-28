"""Naja 统一 UI 主题和导航模块

提供统一的导航菜单和样式定义，确保所有 Tab 页面风格一致。

主要功能：
- 统一导航菜单配置
- 全局页面样式
- 多主题支持
"""

from typing import List, Dict

THEMES = {
    "dark": {
        "name": "🌙 暗夜紫",
        "description": "紫色调的暗色主题",
        "header_gradient": "linear-gradient(135deg, #0f172a 0%, #1e293b 100%)",
        "header_border": "#334155",
        "header_accent": "#0ea5e9",
        "header_title": "#f1f5f9",
        "header_subtitle": "#94a3b8",
        "body_bg": "#1e293b",
        "card_bg": "rgba(255,255,255,0.03)",
        "card_border": "rgba(255,255,255,0.08)",
        "card_title": "#64748b",
        "card_text": "#475569",
        "accent_blue": "#60a5fa",
        "accent_purple": "#c084fc",
        "accent_red": "#f87171",
        "accent_orange": "#fb923c",
        "accent_green": "#4ade80",
        "accent_yellow": "#fbbf24",
    },
    "midnight": {
        "name": "🌌 午夜蓝",
        "description": "蓝色调的深邃主题",
        "header_gradient": "linear-gradient(135deg, #0c1929 0%, #1a365d 100%)",
        "header_border": "#2d4a6f",
        "header_accent": "#38bdf8",
        "header_title": "#e2e8f0",
        "header_subtitle": "#94a3b8",
        "body_bg": "#0f172a",
        "card_bg": "rgba(56, 189, 248, 0.05)",
        "card_border": "rgba(56, 189, 248, 0.15)",
        "card_title": "#64748b",
        "card_text": "#475569",
        "accent_blue": "#38bdf8",
        "accent_purple": "#818cf8",
        "accent_red": "#f87171",
        "accent_orange": "#fb923c",
        "accent_green": "#34d399",
        "accent_yellow": "#fbbf24",
    },
    "forest": {
        "name": "🌲 森林绿",
        "description": "绿色调的自然主题",
        "header_gradient": "linear-gradient(135deg, #022c22 0%, #064e3b 100%)",
        "header_border": "#065f46",
        "header_accent": "#10b981",
        "header_title": "#ecfdf5",
        "header_subtitle": "#a7f3d0",
        "body_bg": "#064e3b",
        "card_bg": "rgba(16, 185, 129, 0.08)",
        "card_border": "rgba(16, 185, 129, 0.2)",
        "card_title": "#6ee7b7",
        "card_text": "#a7f3d0",
        "accent_blue": "#38bdf8",
        "accent_purple": "#a78bfa",
        "accent_red": "#f87171",
        "accent_orange": "#fb923c",
        "accent_green": "#34d399",
        "accent_yellow": "#fcd34d",
    },
    "sunset": {
        "name": "🌅 落日橙",
        "description": "暖色调的夕阳主题",
        "header_gradient": "linear-gradient(135deg, #1c0a00 0%, #3d1c00 100%)",
        "header_border": "#78350f",
        "header_accent": "#f97316",
        "header_title": "#fff7ed",
        "header_subtitle": "#fed7aa",
        "body_bg": "#3d1c00",
        "card_bg": "rgba(249, 115, 22, 0.08)",
        "card_border": "rgba(249, 115, 22, 0.2)",
        "card_title": "#fdba74",
        "card_text": "#fed7aa",
        "accent_blue": "#38bdf8",
        "accent_purple": "#c084fc",
        "accent_red": "#ef4444",
        "accent_orange": "#fb923c",
        "accent_green": "#4ade80",
        "accent_yellow": "#fbbf24",
    },
    "steel": {
        "name": "⚙️ 钢铁灰",
        "description": "冷灰色的工业主题",
        "header_gradient": "linear-gradient(135deg, #18181b 0%, #27272a 100%)",
        "header_border": "#3f3f46",
        "header_accent": "#a1a1aa",
        "header_title": "#fafafa",
        "header_subtitle": "#a1a1aa",
        "body_bg": "#09090b",
        "card_bg": "rgba(161, 161, 170, 0.05)",
        "card_border": "rgba(161, 161, 170, 0.15)",
        "card_title": "#71717a",
        "card_text": "#a1a1aa",
        "accent_blue": "#60a5fa",
        "accent_purple": "#a78bfa",
        "accent_red": "#f87171",
        "accent_orange": "#fb923c",
        "accent_green": "#4ade80",
        "accent_yellow": "#fbbf24",
    },
    "daylight": {
        "name": "☀️ 白天",
        "description": "清爽的浅色主题，适合白天使用",
        "header_gradient": "linear-gradient(135deg, #e0f2fe 0%, #f0f9ff 100%)",
        "header_border": "#bae6fd",
        "header_accent": "#0ea5e9",
        "header_title": "#0c4a6e",
        "header_subtitle": "#0284c7",
        "body_bg": "#e0f2fe",
        "card_bg": "rgba(224, 242, 254, 0.7)",
        "card_border": "rgba(14, 165, 233, 0.4)",
        "card_title": "#0369a1",
        "card_text": "#475569",
        "accent_blue": "#0ea5e9",
        "accent_purple": "#7c3aed",
        "accent_red": "#dc2626",
        "accent_orange": "#ea580c",
        "accent_green": "#16a34a",
        "accent_yellow": "#ca8a04",
    },
}

_current_theme = "dark"


def set_theme(theme_name: str):
    """设置当前主题"""
    global _current_theme
    if theme_name in THEMES:
        _current_theme = theme_name


def get_current_theme() -> dict:
    """获取当前主题配置（优先从请求上下文读取）"""
    global _current_theme
    from deva.naja.web_ui import get_request_theme
    theme_name = get_request_theme()
    if theme_name and theme_name in THEMES:
        return THEMES[theme_name]
    return THEMES.get(_current_theme, THEMES["dark"])


def get_nav_menu_items() -> List[Dict[str, str]]:
    """获取导航菜单项配置"""
    return [
        {"name": "🏠 首页", "path": "/"},
        {"name": "🧠 认知", "path": "/cognition"},
        {"name": "📡 雷达", "path": "/radaradmin"},
        {"name": "👁️ 注意力", "path": "/attentionadmin"},
        {"name": "🔣 QKV", "path": "/qkv"},
        {"name": "💰 信号流", "path": "/signaladmin"},
        {"name": "🗃️ 数据源", "path": "/dsadmin"},
        {"name": "⏱️ 任务", "path": "/taskadmin"},
        {"name": "🎯 策略", "path": "/strategyadmin"},
        {"name": "🤖 LLM", "path": "/llmadmin"},
        {"name": "🎰 Bandit", "path": "/banditadmin"},
        {"name": "📖 字典", "path": "/dictadmin"},
        {"name": "🗄️ 数据表", "path": "/tableadmin"},
        {"name": "💾 持久化", "path": "/runtime_state"},
        {"name": "🛠️ 系统", "path": "/system"},
        {"name": "🔧 配置", "path": "/configadmin"},
    ]


def get_nav_menu_js() -> str:
    """获取导航菜单的 JavaScript 代码"""
    menu_items = get_nav_menu_items()

    menu_items_js = ",\n            ".join([
        f"{{name: '{item['name']}', path: '{item['path']}'}}"
        for item in menu_items
    ])

    theme_options_json = []
    for key, theme in THEMES.items():
        theme_options_json.append(f'{{value: "{key}", label: "{theme["name"]}"}}')
    theme_options_str = ",".join(theme_options_json)

    return f"""
(function() {{
    var existingNav = document.querySelector('.navbar');
    if (existingNav) {{ existingNav.remove(); }}
    var existingTheme = document.getElementById('theme-panel');
    if (existingTheme) {{ existingTheme.remove(); }}

    var nav = document.createElement('nav');
    nav.className = 'navbar';
    Object.assign(nav.style, {{
        position: 'fixed', top: '0', left: '0', right: '0', width: '100%',
        zIndex: '999', backgroundColor: '#0f172a', borderBottom: '1px solid #334155',
        padding: '0 24px', height: '56px', display: 'flex',
        alignItems: 'center', justifyContent: 'space-between',
        boxShadow: '0 2px 8px rgba(0,0,0,0.3)'
    }});

    var brand = document.createElement('div');
    var brandLink = document.createElement('a');
    brandLink.href = '/';
    brandLink.innerHTML = '<span style="font-size: 22px;">🚀</span><span style="font-size: 18px; font-weight: 600; color: #f1f5f9; margin-left: 8px;">Naja</span>';
    brandLink.style.textDecoration = 'none';
    brandLink.style.display = 'flex';
    brandLink.style.alignItems = 'center';
    brand.appendChild(brandLink);

    var menu = document.createElement('div');
    Object.assign(menu.style, {{ display: 'flex', gap: '4px', alignItems: 'center' }});

    var currentPath = window.location.pathname;
    var menuItems = [{menu_items_js}];

    menuItems.forEach(function(item) {{
        var link = document.createElement('a');
        link.href = item.path;
        link.innerText = item.name;
        var isActive = currentPath === item.path;
        Object.assign(link.style, {{
            padding: '8px 14px',
            color: isActive ? '#60a5fa' : '#94a3b8',
            textDecoration: 'none', borderRadius: '8px', fontSize: '14px',
            fontWeight: isActive ? '600' : '500',
            backgroundColor: isActive ? 'rgba(96, 165, 250, 0.15)' : 'transparent',
            transition: 'all 0.2s ease'
        }});
        menu.appendChild(link);
    }});

    nav.appendChild(brand);
    nav.appendChild(menu);
    document.body.insertBefore(nav, document.body.firstChild);
    document.body.style.paddingTop = '56px';

    var themePanel = document.createElement('div');
    themePanel.id = 'theme-panel';
    Object.assign(themePanel.style, {{
        position: 'fixed', top: '70px', right: '20px', zIndex: '1000',
        background: 'rgba(15, 23, 42, 0.95)', border: '1px solid #334155',
        borderRadius: '10px', padding: '12px',
        boxShadow: '0 4px 20px rgba(0,0,0,0.4)'
    }});

    var themeOptions = [{theme_options_str}];
    var selectHtml = '<div style="font-size: 11px; color: #94a3b8; margin-bottom: 8px;">🎨 页面风格</div><select id="theme-select" onchange="window.switchTheme(this.value)" style="background: rgba(255,255,255,0.1); border: 1px solid #334155; border-radius: 6px; color: #f1f5f9; padding: 6px 10px; font-size: 12px; cursor: pointer; min-width: 120px;">';
    themeOptions.forEach(function(opt) {{
        selectHtml += '<option value="' + opt.value + '">' + opt.label + '</option>';
    }});
    selectHtml += '</select>';
    themePanel.innerHTML = selectHtml;
    document.body.appendChild(themePanel);
}})();
    """


def get_global_styles() -> str:
    """获取全局样式（兼容主题系统）"""
    theme = get_current_theme()
    return f"""
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background-color: {theme['body_bg']};
            margin: 0;
            padding: 0;
        }}
        .container {{
            max-width: 880px;
            margin: 0 auto;
            padding: 20px;
        }}
        :root {{
            --header-gradient: {theme['header_gradient']};
            --header-border: {theme['header_border']};
            --header-accent: {theme['header_accent']};
            --header-title: {theme['header_title']};
            --header-subtitle: {theme['header_subtitle']};
            --body-bg: {theme['body_bg']};
            --card-bg: {theme['card_bg']};
            --card-border: {theme['card_border']};
            --card-title: {theme['card_title']};
            --card-text: {theme['card_text']};
            --accent-blue: {theme['accent_blue']};
            --accent-purple: {theme['accent_purple']};
            --accent-red: {theme['accent_red']};
            --accent-orange: {theme['accent_orange']};
            --accent-green: {theme['accent_green']};
            --accent-yellow: {theme['accent_yellow']};
        }}
    </style>
    """


def render_nav_menu():
    """渲染导航菜单（供 pywebio 使用）"""
    from pywebio.output import put_html
    from pywebio.session import run_js

    js_code = get_nav_menu_js()
    run_js(js_code)
