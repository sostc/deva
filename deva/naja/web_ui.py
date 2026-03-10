"""Naja 管理面板 - 基于 PyWebIO 和 Tornado 的 Web 应用程序

统一可恢复单元管理平台，提供：
- 数据源管理
- 任务管理
- 策略管理
- 数据字典管理
- 数据表管理
- 思想雷达（龙虾记忆系统）
"""

from pywebio.output import (
    put_text, put_markdown, put_table, put_buttons, put_html, 
    toast, popup, close_popup, put_row, put_code, put_collapse, set_scope
)
from pywebio.input import input_group, input, textarea, select, actions, NUMBER, checkbox, PASSWORD
from pywebio.session import set_env, run_js, run_async
from pywebio.platform.tornado import webio_handler

from deva import NW, Deva, NB
from .config import get_auth_config, set_config, ensure_auth_secret

# 导入思想雷达UI
from .home.lobster_tab import LobsterRadarUI


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
        {"name": "📡 雷达", "path": "/lobster"},
        {"name": "💰 信号", "path": "/signaladmin"},
        {"name": "🗃️ 数据源", "path": "/dsadmin"},
        {"name": "⏱️ 任务", "path": "/taskadmin"},
        {"name": "🎯 策略", "path": "/strategyadmin"},
        {"name": "📖 字典", "path": "/dictadmin"},
        {"name": "🗄️ 数据表", "path": "/tableadmin"},
        {"name": "🔧 配置", "path": "/configadmin"},
    ]
    
    menu_items_js = ",\n            ".join([
        f"{{name: '{item["name"]}', path: '{item["path"]}'}}"
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
    
    # 认证逻辑
    auth_config = get_auth_config()
    dev_mode = auth_config.get("dev_mode", False)
    
    # 开发模式下跳过认证
    if dev_mode:
        create_nav_menu()
        put_text("Hello, Developer. 欢迎光临 Naja 管理平台（开发模式）")
        return
    
    username = str(auth_config.get("username") or "").strip()
    password = str(auth_config.get("password") or "").strip()
    
    if not username or not password:
        # 显示创建账户界面
        put_markdown("### 首次使用引导")
        put_markdown("检测到尚未初始化管理员账号，请先创建登录用户名和密码。")
        
        def _validate_account(data):
            if not str(data.get("username", "")).strip():
                return ("username", "用户名不能为空")
            if len(str(data.get("password", ""))) < 6:
                return ("password", "密码至少 6 位")
            if data.get("password") != data.get("password_confirm"):
                return ("password_confirm", "两次输入的密码不一致")
            return None
        
        created = await input_group(
            "创建管理员账户",
            [
                input("用户名", name="username", required=True, placeholder="请输入管理员用户名"),
                input("密码", type=PASSWORD, name="password", required=True, placeholder="至少 6 位"),
                input("确认密码", type=PASSWORD, name="password_confirm", required=True, placeholder="再次输入密码"),
            ],
            validate=_validate_account,
        )
        new_username = str(created["username"]).strip()
        new_password = str(created["password"])
        
        set_config("auth", "username", new_username)
        set_config("auth", "password", new_password)
        
        toast("管理员账户已创建，请使用新账号登录", color="success")
        # 重新获取认证配置
        auth_config = get_auth_config()
        username = auth_config.get("username", "")
        password = auth_config.get("password", "")
    
    # 检查认证状态 - 使用简单的内存存储方式
    import json
    import threading
    
    # 使用线程本地存储来保持认证状态
    if not hasattr(init_naja_ui, "auth_storage"):
        init_naja_ui.auth_storage = {}
        init_naja_ui.auth_lock = threading.RLock()
    
    # 获取当前会话的唯一标识（使用浏览器localStorage存储固定的session_id）
    session_id = run_js("return localStorage.getItem('naja_session_id') || (function(){var id = 'session_' + Date.now(); localStorage.setItem('naja_session_id', id); return id;})();") or "default"
    
    with init_naja_ui.auth_lock:
        auth_token = init_naja_ui.auth_storage.get(session_id)
        if auth_token:
            try:
                auth_data = json.loads(auth_token)
                if auth_data.get("username") == username:
                    # 认证状态有效
                    create_nav_menu()
                    # put_html(f"<h1 style='margin-bottom: 20px;'>{title}</h1>")
                    put_text(f"Hello, {auth_data['username']}. 欢迎光临 Naja 管理平台")
                    return
            except:
                pass
    
    # 登录认证
    while True:
        user = await input_group('登录', [
            input('用户名', name='username'),
            input('密码', type=PASSWORD, name='password'),
        ])
        if user['username'] == username and user['password'] == password:
            # 保存认证状态到内存存储
            auth_data = {"username": user['username']}
            with init_naja_ui.auth_lock:
                init_naja_ui.auth_storage[session_id] = json.dumps(auth_data)
            break
        toast('用户名或密码错误', color='error')
    
    # 登录成功后创建导航菜单
    create_nav_menu()
    put_html(f"<h1 style='margin-bottom: 20px;'>{title}</h1>")
    put_text(f"Hello, {user['username']}. 欢迎光临 Naja 管理平台")


def _ctx(globals_dict: dict = None):
    """获取上下文"""
    from pywebio.output import put_datatable, put_button, clear, use_scope, set_scope
    from pywebio.input import input as put_input, file_upload as put_file_upload
    from pywebio import pin
    
    return {
        "put_text": put_text,
        "put_markdown": put_markdown,
        "put_table": put_table,
        "put_buttons": put_buttons,
        "put_html": put_html,
        "put_row": put_row,
        "put_code": put_code,
        "put_collapse": put_collapse,
        "put_datatable": put_datatable,
        "put_input": put_input,
        "put_button": put_button,
        "put_file_upload": put_file_upload,
        "clear": clear,
        "use_scope": use_scope,
        "set_scope": set_scope,
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
        "PASSWORD": PASSWORD,
        "set_env": set_env,
        "run_js": run_js,
        "init_naja_ui": init_naja_ui,
        "apply_global_styles": apply_global_styles,
        "create_nav_menu": create_nav_menu,
        "pin": pin,
    }


async def render_main(ctx: dict):
    """渲染主页"""
    await ctx["init_naja_ui"]("管理平台")
    from .home.ui import render_home
    await render_home(ctx)


async def main():
    """主页"""
    return await render_main(_ctx())


async def dsadmin():
    """数据源管理"""
    from .datasource.ui import render_datasource_admin
    ctx = _ctx()
    await ctx["init_naja_ui"]("数据源管理")
    return await render_datasource_admin(ctx)


async def signaladmin():
    """信号流"""
    from .signal.ui import render_signal_page
    ctx = _ctx()
    await ctx["init_naja_ui"]("信号流")
    await render_signal_page(ctx)


async def taskadmin():
    """任务管理"""
    from .tasks.ui import render_task_admin
    ctx = _ctx()
    await ctx["init_naja_ui"]("任务管理")
    return await render_task_admin(ctx)


async def strategyadmin():
    """策略管理"""
    from .strategy.ui import render_strategy_admin
    ctx = _ctx()
    await ctx["init_naja_ui"]("策略管理")
    return await render_strategy_admin(ctx)


async def dictadmin():
    """字典管理"""
    from .dictionary.ui import render_dictionary_admin
    ctx = _ctx()
    await ctx["init_naja_ui"]("字典管理")
    return await render_dictionary_admin(ctx)


async def tableadmin():
    """数据表管理"""
    from .tables.ui import render_tables_page
    ctx = _ctx()
    ctx["NB"] = NB
    ctx["pd"] = __import__("pandas")
    await ctx["init_naja_ui"]("数据表管理")
    set_scope("tables_content")
    render_tables_page(ctx)


async def configadmin():
    """配置管理"""
    from .config.ui import render_config_page
    ctx = _ctx()
    await ctx["init_naja_ui"]("配置管理")
    render_config_page(ctx)


def lobster_page():
    """思想雷达页面"""
    ui = LobsterRadarUI()
    ui.render()


def create_handlers(cdn: str = None):
    """创建路由处理器"""
    cdn_url = cdn or 'https://fastly.jsdelivr.net/gh/wang0618/PyWebIO-assets@v1.8.3/'
    
    return [
        (r'/', webio_handler(main, cdn=cdn_url)),
        (r'/lobster', webio_handler(lobster_page, cdn=cdn_url)),
        (r'/signaladmin', webio_handler(signaladmin, cdn=cdn_url)),
        (r'/dsadmin', webio_handler(dsadmin, cdn=cdn_url)),
        (r'/taskadmin', webio_handler(taskadmin, cdn=cdn_url)),
        (r'/strategyadmin', webio_handler(strategyadmin, cdn=cdn_url)),
        (r'/dictadmin', webio_handler(dictadmin, cdn=cdn_url)),
        (r'/tableadmin', webio_handler(tableadmin, cdn=cdn_url)),
        (r'/configadmin', webio_handler(configadmin, cdn=cdn_url)),
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
    from .signal.stream import get_signal_stream
    from .supervisor import start_supervisor
    
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
    
    print("📡 初始化信号流...")
    get_signal_stream()  # 初始化信号流并从持久化存储加载数据
    
    print("🛡️ 启动系统监控...")
    start_supervisor()
    
    handlers = create_handlers()
    
    print(f"🌐 启动 Web 服务器: http://localhost:{port}")
    print("=" * 60)
    
    NW('naja_webview', host=host, port=port).application.add_handlers('.*$', handlers)
    
    Deva.run()