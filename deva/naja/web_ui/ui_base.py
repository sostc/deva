"""UI 基础组件（导航、初始化、上下文）"""

from __future__ import annotations

from pywebio.output import (
    put_text, put_markdown, put_table, put_buttons, put_html,
    toast, popup, close_popup, put_row, put_code, put_collapse, set_scope
)
from pywebio.input import input_group, input, textarea, select, actions, NUMBER, checkbox, PASSWORD
from pywebio.session import set_env, run_js, run_async

from deva import NB
from deva.naja.register import SR
from ..config import get_auth_config, set_config, ensure_auth_secret, verify_auth
from .styles import apply_global_styles


def create_nav_menu():
    """创建导航菜单 - 使用统一模块"""
    from ..infra.ui.ui_theme import get_nav_menu_js
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
        
        set_config("auth.username", new_username)
        set_config("auth.password", new_password)
        
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
        if verify_auth(user['username'], user['password']):
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


