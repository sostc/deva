"""Naja 统一 UI 导航模块

提供统一的导航菜单和样式定义，确保所有 Tab 页面风格一致。

主要功能：
- 统一导航菜单配置
- 全局页面样式
"""

from typing import List, Dict


def get_current_theme_config() -> dict:
    """获取当前主题配置字典（固定默认主题）"""
    return {
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
    }


def get_nav_menu_items() -> List[Dict[str, str]]:
    """获取导航菜单项配置"""
    return [
        {"name": "🏠 首页", "path": "/"},
        {"name": "🧠 认知", "path": "/cognition"},
        {"name": "🔗 供应链", "path": "/supplychain"},
        {"name": "📡 雷达", "path": "/radaradmin"},
        {"name": "📊 市场", "path": "/market"},
        {"name": "🧘 觉醒", "path": "/awakening"},
        {"name": "📚 学习", "path": "/learning"},
        {"name": "💰 信号流", "path": "/signaladmin"},
        {"name": "🛠️ 开发者工具", "path": "/devtools"},
    ]


def get_nav_menu_js() -> str:
    """获取导航菜单的 JavaScript 代码"""
    menu_items = get_nav_menu_items()

    menu_items_js = ",\n            ".join([
        f"{{name: '{item['name']}', path: '{item['path']}'}}"
        for item in menu_items
    ])

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
}})();
    """


def get_global_styles() -> str:
    """获取全局样式（兼容主题系统）"""
    theme = get_current_theme_config()
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
