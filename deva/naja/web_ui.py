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

_request_theme = None


def get_request_theme():
    """获取请求中的主题（从 Cookie 读取）"""
    global _request_theme
    return _request_theme


def set_request_theme(theme_name: str):
    """设置请求中的主题"""
    global _request_theme
    _request_theme = theme_name

# 导入认知系统UI
from .cognition.ui import CognitionUI
from .radar.ui import RadarUI
from .performance import PerformanceMonitorUI


def _init_lab_mode(lab_config: dict):
    """初始化实验室模式

    1. 创建回放数据源（如果指定了 table_name）
    2. 启动注意力系统实验模式

    Args:
        lab_config: 实验室配置，包含:
            - table_name: 回放数据表名
            - interval: 回放间隔（秒）
            - speed: 回放速度倍数
    """
    import uuid
    import time
    import os

    # 设置调试模式环境变量
    if lab_config.get("debug"):
        os.environ["NAJA_LAB_DEBUG"] = "true"
        print("🧪 实验室调试模式已启用")
    else:
        os.environ["NAJA_LAB_DEBUG"] = "false"

    from .datasource import get_datasource_manager, DataSourceEntry, UnitStatus
    from .strategy import get_strategy_manager

    table_name = lab_config.get("table_name")
    interval = lab_config.get("interval", 1.0)
    speed = lab_config.get("speed", 1.0)

    ds_mgr = get_datasource_manager()
    strategy_mgr = get_strategy_manager()

    datasource_id = None

    if table_name:
        result = ds_mgr.create(
            name=f"实验室-历史行情回放-{uuid.uuid4().hex[:8]}",
            source_type="replay",
            config={
                "table_name": table_name,
                "interval": interval,
                "speed": speed,
            }
        )

        if not result.get("success"):
            print(f"⚠️ 创建实验室数据源失败: {result.get('error', '未知错误')}")
            return

        datasource_id = result.get("id")
        print(f"🧪 已创建实验室数据源: {datasource_id}")

        time.sleep(0.5)

        lab_datasource = ds_mgr._items.get(datasource_id)
        if lab_datasource:
            lab_datasource.start()
            print(f"🧪 实验室数据源已启动，回放间隔: {interval}s")
        else:
            print(f"⚠️ 找不到已创建的数据源: {datasource_id}")
            datasource_id = None

    if strategy_mgr:
        time.sleep(0.5)

        if datasource_id:
            result = strategy_mgr.start_experiment(
                categories=[],  # 空列表表示所有类别
                datasource_id=datasource_id,
                include_attention=True  # 启用注意力策略
            )
            if result.get("success"):
                print(f"✅ 注意力策略实验模式已启动 (数据源: {datasource_id})")
            else:
                print(f"⚠️ 启动实验模式失败: {result.get('error', '未知错误')}")
        else:
            print("⚠️ 未指定回放数据表，仅启动注意力系统")


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
    """创建导航菜单 - 使用统一模块"""
    from .common.ui_theme import get_nav_menu_js
    js_code = get_nav_menu_js()
    
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
    """信号流 - 策略结果可视化"""
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


async def radaradmin():
    """雷达感知层"""
    from pywebio.session import eval_js
    try:
        theme = await eval_js("document.cookie.includes('naja-theme=') ? document.cookie.split('naja-theme=')[1].split(';')[0] : null")
        if theme:
            set_request_theme(theme)
    except:
        pass
    from .radar.ui import RadarUI
    ctx = _ctx()
    await ctx["init_naja_ui"]("雷达")
    ui = RadarUI()
    ui.render()


async def insightadmin():
    """洞察中心已整合到认知页面"""
    ctx = _ctx()
    await ctx["init_naja_ui"]("认知")
    ui = CognitionUI()
    ui.render()


async def cognition_page():
    """认知中枢页面"""
    from pywebio.session import eval_js
    try:
        theme = await eval_js("document.cookie.includes('naja-theme=') ? document.cookie.split('naja-theme=')[1].split(';')[0] : null")
        if theme:
            set_request_theme(theme)
    except:
        pass
    ui = CognitionUI()
    ui.render()


def memory_page():
    """兼容旧入口：重定向到认知页面"""
    ui = CognitionUI()
    ui.render()


async def llmadmin():
    """LLM 调节"""
    from .llm_controller.ui import render_llm_admin
    ctx = _ctx()
    await ctx["init_naja_ui"]("LLM 调节")
    return await render_llm_admin(ctx)


async def banditadmin():
    """Bandit 自适应交易"""
    from .bandit.ui import render_bandit_admin
    ctx = _ctx()
    await ctx["init_naja_ui"]("Bandit 自适应交易")
    await render_bandit_admin(ctx)


async def attentionadmin():
    """注意力调度系统"""
    from pywebio.session import eval_js
    try:
        theme = await eval_js("document.cookie.includes('naja-theme=') ? document.cookie.split('naja-theme=')[1].split(';')[0] : null")
        if theme:
            set_request_theme(theme)
    except:
        pass

    ctx = _ctx()
    await ctx["init_naja_ui"]("注意力调度系统")

    # 默认使用 ui.py，通过URL参数切换到 V2 版本
    from pywebio.session import eval_js
    url_params = None
    try:
        url_params = await eval_js("new URLSearchParams(window.location.search).get('ui')")
    except:
        pass

    if url_params == 'v2':
        toast("V2 UI 已合并到主版本", color="info")

    from .attention.ui import render_attention_admin
    await render_attention_admin(ctx)


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


def memory_page():
    """叙事主题记忆 - 叙事与主题分析"""
    ui = NewsRadarUI()
    ui.render()


async def performance_page():
    """性能监控页面"""
    from pywebio.session import eval_js
    try:
        theme = await eval_js("document.cookie.includes('naja-theme=') ? document.cookie.split('naja-theme=')[1].split(';')[0] : null")
        if theme:
            set_request_theme(theme)
    except:
        pass
    ui = PerformanceMonitorUI()
    ui.render()


def _get_log_stream_page():
    from .log_stream import log_stream_page
    return log_stream_page


def create_handlers(cdn: str = None):
    """创建路由处理器"""
    cdn_url = cdn or 'https://fastly.jsdelivr.net/gh/wang0618/PyWebIO-assets@v1.8.3/'

    return [
        (r'/', webio_handler(main, cdn=cdn_url)),
        (r'/cognition', webio_handler(cognition_page, cdn=cdn_url)),
        (r'/memory', webio_handler(memory_page, cdn=cdn_url)),
        (r'/insight', webio_handler(insightadmin, cdn=cdn_url)),
        (r'/performance', webio_handler(performance_page, cdn=cdn_url)),
        (r'/signaladmin', webio_handler(signaladmin, cdn=cdn_url)),
        (r'/dsadmin', webio_handler(dsadmin, cdn=cdn_url)),
        (r'/taskadmin', webio_handler(taskadmin, cdn=cdn_url)),
        (r'/strategyadmin', webio_handler(strategyadmin, cdn=cdn_url)),
        (r'/radaradmin', webio_handler(radaradmin, cdn=cdn_url)),
        (r'/llmadmin', webio_handler(llmadmin, cdn=cdn_url)),
        (r'/banditadmin', webio_handler(banditadmin, cdn=cdn_url)),
        (r'/attentionadmin', webio_handler(attentionadmin, cdn=cdn_url)),
        (r'/dictadmin', webio_handler(dictadmin, cdn=cdn_url)),
        (r'/tableadmin', webio_handler(tableadmin, cdn=cdn_url)),
        (r'/configadmin', webio_handler(configadmin, cdn=cdn_url)),
        (r'/logstream', webio_handler(lambda: _get_log_stream_page()(), cdn=cdn_url)),
    ]


def run_server(port: int = 8080, host: str = '0.0.0.0', lab_config: dict = None):
    """启动服务器

    Args:
        port: Web 服务器端口
        host: 绑定地址
        lab_config: 实验室模式配置，如 {'enabled': True, 'table_name': 'xxx', 'interval': 1.0}
    """
    print("=" * 60)
    print("🚀 Naja 管理平台启动中...")
    print("=" * 60)

    from .datasource import get_datasource_manager
    from .tasks import get_task_manager
    from .strategy import get_strategy_manager
    from .dictionary import get_dictionary_manager
    from .signal.stream import get_signal_stream
    from .supervisor import start_supervisor
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from tornado.ioloop import IOLoop
    import threading

    ds_mgr = get_datasource_manager()
    task_mgr = get_task_manager()
    strategy_mgr = get_strategy_manager()
    dict_mgr = get_dictionary_manager()

    load_results = {}
    restore_results = {}
    load_errors = {}
    restore_errors = {}

    def load_manager(manager, name):
        try:
            count = manager.load_from_db()
            return (name, count, None)
        except Exception as e:
            return (name, 0, str(e))

    def restore_manager(manager, name):
        try:
            result = manager.restore_running_states()
            return (name, result, None)
        except Exception as e:
            return (name, None, str(e))

    print("📂 并行加载持久化数据...")
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(load_manager, ds_mgr, "datasource"): "datasource",
            executor.submit(load_manager, task_mgr, "task"): "task",
            executor.submit(load_manager, strategy_mgr, "strategy"): "strategy",
            executor.submit(load_manager, dict_mgr, "dictionary"): "dictionary",
        }

        for future in as_completed(futures):
            name, count, error = future.result()
            if error:
                load_errors[name] = error
            else:
                load_results[name] = count

    ds_count = load_results.get("datasource", 0)
    task_count = load_results.get("task", 0)
    strategy_count = load_results.get("strategy", 0)
    dict_count = load_results.get("dictionary", 0)

    if load_errors:
        error_info = ", ".join([f"{k}: {v}" for k, v in load_errors.items()])
        print(f"⚠️ 部分数据加载失败: {error_info}")

    print(f"📂 加载完成: 数据源({ds_count}) 任务({task_count}) 策略({strategy_count}) 字典({dict_count})")

    print("🔄 并行恢复运行状态...")
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(restore_manager, ds_mgr, "datasource"): "datasource",
            executor.submit(restore_manager, task_mgr, "task"): "task",
            executor.submit(restore_manager, strategy_mgr, "strategy"): "strategy",
            executor.submit(restore_manager, dict_mgr, "dictionary"): "dictionary",
        }

        for future in as_completed(futures):
            name, result, error = future.result()
            if error:
                restore_errors[name] = error
            else:
                restore_results[name] = result

    if restore_errors:
        error_info = ", ".join([f"{k}: {v}" for k, v in restore_errors.items()])
        print(f"⚠️ 部分状态恢复失败: {error_info}")

    get_signal_stream()

    print("🎯 恢复 Bandit 自适应循环...")
    try:
        from .bandit import restore_bandit_state
        restore_bandit_state()
        print("✓ Bandit 自适应循环状态已恢复")
    except Exception as e:
        print(f"⚠️ Bandit 自适应循环恢复失败: {e}")

    print("🛡️ 启动系统监控...")
    start_supervisor()

    # 实验室模式初始化
    if lab_config and lab_config.get("enabled"):
        print("🧪 实验室模式已启用，准备启动...")
        _init_lab_mode(lab_config)

    handlers = create_handlers()

    print(f"🌐 启动 Web 服务器: http://localhost:{port}")
    print("=" * 60)

    server = NW('naja_webview', host=host, port=port, start=False)
    server.application.add_handlers('.*$', handlers)
    server.start()

    asyncio_loop = getattr(IOLoop.current(), 'asyncio_loop', None)
    if asyncio_loop is None or not asyncio_loop.is_running():
        Deva.run()
    else:
        import signal
        import threading

        shutdown_event = threading.Event()

        def shutdown_handler(signum, frame):
            import logging
            logger = logging.getLogger("deva.naja")
            logger.info("收到退出信号，正在优雅关闭...")
            shutdown_event.set()

        signal.signal(signal.SIGINT, shutdown_handler)
        signal.signal(signal.SIGTERM, shutdown_handler)

        try:
            shutdown_event.wait()
        except KeyboardInterrupt:
            shutdown_handler(None, None)
