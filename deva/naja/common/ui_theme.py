"""Naja 统一 UI 主题和导航模块

提供统一的导航菜单和样式定义，确保所有 Tab 页面风格一致。

主要功能：
- 统一导航菜单配置
- 全局页面样式
- 与 ui_style.py 配合使用
"""

from typing import List, Dict

# 导入已有的 ui_style 模块
from .ui_style import apply_strategy_like_styles, render_stats_cards, render_empty_state


def get_nav_menu_items() -> List[Dict[str, str]]:
    """获取导航菜单项配置
    
    菜单顺序：首页 -> 记忆 -> 雷达 -> 信号流 -> 数据源 -> 任务 -> 策略 -> LLM -> Bandit -> 注意力 -> 字典 -> 数据表 -> 性能 -> 配置
    """
    return [
        {"name": "🏠 首页", "path": "/"},
        {"name": "🧠 记忆", "path": "/memory"},
        {"name": "📡 雷达", "path": "/radaradmin"},
        {"name": "💰 信号流", "path": "/signaladmin"},
        {"name": "🗃️ 数据源", "path": "/dsadmin"},
        {"name": "⏱️ 任务", "path": "/taskadmin"},
        {"name": "🎯 策略", "path": "/strategyadmin"},
        {"name": "🤖 LLM", "path": "/llmadmin"},
        {"name": "🎰 Bandit", "path": "/banditadmin"},
        {"name": "👁️ 注意力", "path": "/attentionadmin"},
        {"name": "📖 字典", "path": "/dictadmin"},
        {"name": "🗄️ 数据表", "path": "/tableadmin"},
        {"name": "📈 性能", "path": "/performance"},
        {"name": "🔧 配置", "path": "/configadmin"},
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
        // 如果已存在导航栏，先移除
        const existingNav = document.querySelector('.navbar');
        if (existingNav) {{
            existingNav.remove();
        }}
        
        const nav = document.createElement('nav');
        nav.className = 'navbar';
        Object.assign(nav.style, {{
            position: 'fixed',
            top: '0',
            left: '0',
            right: '0',
            width: '100%',
            zIndex: '999',
            backgroundColor: '#ffffff',
            borderBottom: '1px solid #e2e8f0',
            padding: '0 24px',
            height: '56px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            boxShadow: '0 1px 3px rgba(0,0,0,0.05)'
        }});
        
        const brand = document.createElement('div');
        const brandLink = document.createElement('a');
        brandLink.href = '/';
        brandLink.innerHTML = '<span style="font-size: 22px;">🚀</span><span style="font-size: 18px; font-weight: 600; color: #1e293b; margin-left: 8px;">Naja</span>';
        brandLink.style.textDecoration = 'none';
        brandLink.style.display = 'flex';
        brandLink.style.alignItems = 'center';
        brand.appendChild(brandLink);

        const menu = document.createElement('div');
        Object.assign(menu.style, {{
            display: 'flex',
            gap: '4px',
            alignItems: 'center'
        }});

        const currentPath = window.location.pathname;
        const menuItems = [
            {menu_items_js}
        ];
        
        menuItems.forEach(item => {{
            const link = document.createElement('a');
            link.href = item.path;
            link.innerText = item.name;
            const isActive = currentPath === item.path;
            Object.assign(link.style, {{
                padding: '8px 14px',
                color: isActive ? '#3b82f6' : '#64748b',
                textDecoration: 'none',
                borderRadius: '8px',
                fontSize: '14px',
                fontWeight: isActive ? '600' : '500',
                backgroundColor: isActive ? '#eff6ff' : 'transparent',
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
    """获取全局样式"""
    return """
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background-color: #f8fafc;
            margin: 0;
            padding: 0;
        }
        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }
        .card {
            background: white;
            border-radius: 12px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            padding: 20px;
            margin-bottom: 20px;
        }
        .card-header {
            font-size: 18px;
            font-weight: 600;
            color: #1e293b;
            margin-bottom: 16px;
            padding-bottom: 12px;
            border-bottom: 1px solid #e2e8f0;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .severity-badge {
            display: inline-flex;
            align-items: center;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 600;
        }
        .severity-severe {
            background: #fee2e2;
            color: #dc2626;
        }
        .severity-critical {
            background: #fef3c7;
            color: #d97706;
        }
        .severity-warning {
            background: #dbeafe;
            color: #2563eb;
        }
        .severity-normal {
            background: #d1fae5;
            color: #059669;
        }
        .metric-card {
            background: white;
            border-radius: 12px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            padding: 16px;
            text-align: center;
        }
        .metric-value {
            font-size: 28px;
            font-weight: 700;
            margin-bottom: 4px;
        }
        .metric-label {
            font-size: 13px;
            color: #64748b;
        }
        .component-row {
            display: flex;
            align-items: center;
            padding: 12px 16px;
            border-bottom: 1px solid #e2e8f0;
            transition: background 0.2s;
        }
        .component-row:hover {
            background: #f8fafc;
        }
        .component-row:last-child {
            border-bottom: none;
        }
        .component-icon {
            width: 40px;
            height: 40px;
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 20px;
            margin-right: 16px;
        }
        .component-info {
            flex: 1;
        }
        .component-name {
            font-weight: 600;
            color: #1e293b;
            font-size: 14px;
        }
        .component-meta {
            color: #64748b;
            font-size: 12px;
            margin-top: 2px;
        }
        .component-metrics {
            text-align: right;
            margin-right: 16px;
        }
        .component-time {
            font-weight: 600;
            font-size: 14px;
        }
        .component-calls {
            color: #64748b;
            font-size: 12px;
        }
        .filter-tabs {
            display: flex;
            gap: 8px;
            margin-bottom: 20px;
        }
        .filter-tab {
            padding: 8px 16px;
            border-radius: 8px;
            font-size: 14px;
            cursor: pointer;
            transition: all 0.2s;
            border: none;
            background: #f1f5f9;
            color: #64748b;
        }
        .filter-tab:hover {
            background: #e2e8f0;
        }
        .filter-tab.active {
            background: #3b82f6;
            color: white;
        }
        .recommendation-box {
            background: #fef3c7;
            border-left: 4px solid #f59e0b;
            padding: 12px 16px;
            border-radius: 0 8px 8px 0;
            margin-top: 8px;
            font-size: 13px;
            color: #92400e;
        }
        table {
            width: 100%;
            border-collapse: collapse;
        }
        th, td {
            padding: 12px 16px;
            text-align: left;
            border-bottom: 1px solid #e2e8f0;
        }
        th {
            font-weight: 600;
            color: #64748b;
            font-size: 12px;
            text-transform: uppercase;
            background: #f8fafc;
        }
        tr:hover {
            background: #f8fafc;
        }
    </style>
    """


def render_nav_menu():
    """渲染导航菜单（供 pywebio 使用）"""
    from pywebio.output import put_html
    from pywebio.session import run_js
    
    js_code = get_nav_menu_js()
    run_js(js_code)


def render_global_styles():
    """渲染全局样式（供 pywebio 使用）"""
    from pywebio.output import put_html
    
    put_html(get_global_styles())
