"""Naja 管理面板 - 基于 PyWebIO 和 Tornado 的 Web 应用程序

统一可恢复单元管理平台，提供：
- 数据源管理
- 任务管理
- 策略管理
- 数据字典管理
"""

from pywebio.output import (
    put_text, put_markdown, put_table, put_buttons, put_html, 
    toast, popup, close_popup, put_row, put_code, put_collapse
)
from pywebio.input import input_group, input, textarea, select, actions, NUMBER, checkbox
from pywebio.session import set_env, run_js, run_async

from deva import NW, Deva
from pywebio.platform.tornado import webio_handler


def apply_global_styles():
    """应用全局样式"""
    put_html("""
    <style>
        :root {
            --primary-color: #3b82f6;
            --primary-hover: #2563eb;
            --success-color: #28a745;
            --danger-color: #dc3545;
            --warning-color: #ffc107;
            --text-color: #1e293b;
            --text-muted: #64748b;
            --bg-color: #f8fafc;
            --border-color: #e2e8f0;
        }
        
        .stats-card {
            display: inline-block;
            padding: 15px 25px;
            margin: 5px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border-radius: 12px;
            text-align: center;
            min-width: 100px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }
        
        .stats-value {
            font-size: 28px;
            font-weight: bold;
        }
        
        .stats-label {
            font-size: 12px;
            opacity: 0.9;
            margin-top: 4px;
        }
        
        .status-running {
            color: var(--success-color);
            font-weight: 600;
        }
        
        .status-stopped {
            color: var(--text-muted);
        }
        
        .status-error {
            color: var(--danger-color);
            font-weight: 600;
        }
        
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 16px;
            background: white;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }
        
        th {
            background: var(--bg-color);
            padding: 12px 16px;
            text-align: left;
            font-weight: 600;
            color: var(--text-color);
            border-bottom: 2px solid var(--border-color);
        }
        
        td {
            padding: 12px 16px;
            border-bottom: 1px solid var(--border-color);
        }
        
        tr:hover {
            background: var(--bg-color);
        }
        
        .detail-section {
            margin: 16px 0;
            padding: 16px;
            background: var(--bg-color);
            border-radius: 8px;
        }
        
        .detail-title {
            font-size: 16px;
            font-weight: 600;
            color: var(--text-color);
            margin-bottom: 12px;
            padding-bottom: 8px;
            border-bottom: 1px solid var(--border-color);
        }
    </style>
    """)


def create_nav_menu():
    """创建导航菜单"""
    menu_items = [
        {"name": "🏠 首页", "path": "/"},
        {"name": "📡 数据源", "path": "/dsadmin"},
        {"name": "⏰ 任务", "path": "/taskadmin"},
        {"name": "📊 策略", "path": "/strategyadmin"},
        {"name": "📚 字典", "path": "/dictadmin"},
    ]
    
    menu_items_js = ",\n            ".join([
        f"""{{name: '{item["name"]}', path: '{item["path"]}'}}"""
        for item in menu_items
    ])
    
    js_code = f"""
    (function() {{
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
    
    run_js(js_code)


async def init_naja_ui(title: str):
    """初始化 UI"""
    set_env(title=f"Naja - {title}", output_animation=False)
    apply_global_styles()
    create_nav_menu()
    put_html(f"<h1 style='margin-bottom: 20px;'>{title}</h1>")


def _ctx(globals_dict: dict = None):
    """获取上下文"""
    return {
        "put_text": put_text,
        "put_markdown": put_markdown,
        "put_table": put_table,
        "put_buttons": put_buttons,
        "put_html": put_html,
        "put_row": put_row,
        "put_code": put_code,
        "put_collapse": put_collapse,
        "toast": toast,
        "popup": popup,
        "close_popup": close_popup,
        "input_group": input_group,
        "input": input,
        "textarea": textarea,
        "select": select,
        "actions": actions,
        "checkbox": checkbox,
        "NUMBER": NUMBER,
        "set_env": set_env,
        "run_js": run_js,
        "init_naja_ui": init_naja_ui,
        "apply_global_styles": apply_global_styles,
        "create_nav_menu": create_nav_menu,
    }


async def render_main(ctx: dict):
    """渲染主页"""
    await ctx["init_naja_ui"]("管理平台")
    
    from .datasource import get_datasource_manager
    from .tasks import get_task_manager
    from .strategy import get_strategy_manager
    from .dictionary import get_dictionary_manager
    
    ds_mgr = get_datasource_manager()
    task_mgr = get_task_manager()
    strategy_mgr = get_strategy_manager()
    dict_mgr = get_dictionary_manager()
    
    ds_stats = ds_mgr.get_stats()
    task_stats = task_mgr.get_stats()
    strategy_stats = strategy_mgr.get_stats()
    dict_stats = dict_mgr.get_stats()
    
    ctx["put_markdown"]("""### 🚀 Naja 管理平台
    
基于 **RecoverableUnit** 抽象的统一管理平台，提供数据源、任务、策略、数据字典的统一管理。

**核心特性：**
- ✅ 统一的状态管理
- ✅ 自动恢复机制
- ✅ 代码动态编译
- ✅ 持久化存储
""")
    
    ctx["put_html"](f"""
    <div style="display: flex; flex-wrap: wrap; gap: 15px; margin: 20px 0;">
        <div class="stats-card" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);">
            <div class="stats-value">{ds_stats['total']}</div>
            <div class="stats-label">📡 数据源</div>
        </div>
        <div class="stats-card" style="background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);">
            <div class="stats-value">{task_stats['total']}</div>
            <div class="stats-label">⏰ 任务</div>
        </div>
        <div class="stats-card" style="background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);">
            <div class="stats-value">{strategy_stats['total']}</div>
            <div class="stats-label">📊 策略</div>
        </div>
        <div class="stats-card" style="background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%);">
            <div class="stats-value">{dict_stats['total']}</div>
            <div class="stats-label">📚 字典</div>
        </div>
    </div>
    """)
    
    ctx["put_html"]("""
    <div style="margin-top: 30px;">
        <h3>快速导航</h3>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-top: 15px;">
            <a href="/dsadmin" style="text-decoration: none;">
                <div style="padding: 20px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 12px; color: white; text-align: center;">
                    <div style="font-size: 24px;">📡</div>
                    <div style="font-size: 16px; font-weight: 600; margin-top: 8px;">数据源管理</div>
                </div>
            </a>
            <a href="/taskadmin" style="text-decoration: none;">
                <div style="padding: 20px; background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); border-radius: 12px; color: white; text-align: center;">
                    <div style="font-size: 24px;">⏰</div>
                    <div style="font-size: 16px; font-weight: 600; margin-top: 8px;">任务管理</div>
                </div>
            </a>
            <a href="/strategyadmin" style="text-decoration: none;">
                <div style="padding: 20px; background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); border-radius: 12px; color: white; text-align: center;">
                    <div style="font-size: 24px;">📊</div>
                    <div style="font-size: 16px; font-weight: 600; margin-top: 8px;">策略管理</div>
                </div>
            </a>
            <a href="/dictadmin" style="text-decoration: none;">
                <div style="padding: 20px; background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%); border-radius: 12px; color: white; text-align: center;">
                    <div style="font-size: 24px;">📚</div>
                    <div style="font-size: 16px; font-weight: 600; margin-top: 8px;">字典管理</div>
                </div>
            </a>
        </div>
    </div>
    """)


async def main():
    """主页"""
    return await render_main(_ctx())


async def dsadmin():
    """数据源管理"""
    from .datasource.ui import render_datasource_admin
    return await render_datasource_admin(_ctx())


async def taskadmin():
    """任务管理"""
    from .tasks.ui import render_task_admin
    return await render_task_admin(_ctx())


async def strategyadmin():
    """策略管理"""
    from .strategy.ui import render_strategy_admin
    return await render_strategy_admin(_ctx())


async def dictadmin():
    """字典管理"""
    from .dictionary.ui import render_dictionary_admin
    return await render_dictionary_admin(_ctx())


def create_handlers(cdn: str = None):
    """创建路由处理器"""
    cdn_url = cdn or 'https://fastly.jsdelivr.net/gh/wang0618/PyWebIO-assets@v1.8.3/'
    
    return [
        (r'/', webio_handler(main, cdn=cdn_url)),
        (r'/dsadmin', webio_handler(dsadmin, cdn=cdn_url)),
        (r'/taskadmin', webio_handler(taskadmin, cdn=cdn_url)),
        (r'/strategyadmin', webio_handler(strategyadmin, cdn=cdn_url)),
        (r'/dictadmin', webio_handler(dictadmin, cdn=cdn_url)),
    ]


def run_server(port: int = 8080, host: str = '0.0.0.0'):
    """启动服务器"""
    print("=" * 60)
    print("🚀 Naja 管理平台启动中...")
    print("=" * 60)
    
    from .datasource import get_datasource_manager
    from .tasks import get_task_manager
    from .strategy import get_strategy_manager
    from .dictionary import get_dictionary_manager
    
    ds_mgr = get_datasource_manager()
    task_mgr = get_task_manager()
    strategy_mgr = get_strategy_manager()
    dict_mgr = get_dictionary_manager()
    
    print("📂 加载数据源...")
    ds_mgr.load_from_db()
    ds_mgr.restore_running_states()
    
    print("📂 加载任务...")
    task_mgr.load_from_db()
    task_mgr.restore_running_states()
    
    print("📂 加载策略...")
    strategy_mgr.load_from_db()
    strategy_mgr.restore_running_states()
    
    print("📂 加载字典...")
    dict_mgr.load_from_db()
    dict_mgr.restore_running_states()
    
    handlers = create_handlers()
    
    print(f"🌐 启动 Web 服务器: http://localhost:{port}")
    print("=" * 60)
    
    NW('naja_webview', host=host, port=port).application.add_handlers('.*$', handlers)
    
    Deva.run()
