"""Main-page UI logic extracted from admin.py."""

from __future__ import annotations

import asyncio  # 添加异步支持
import json
import re
from urllib.parse import urljoin

from openai import AsyncOpenAI, APIStatusError

from ..llm.config_utils import (
    build_model_config_example,
    build_model_config_message,
    get_model_config_status,
)


def cut_foot(ctx):
    ctx["run_js"]('document.getElementsByClassName("footer")[0].style.display="none"')
    ctx["put_link"]("浙ICP备2021016438号", "https://beian.miit.gov.cn/").style("position: fixed;bottom: 10px;right: 10px")


def put_out(ctx, msg, type="text", scope="", session=""):
    target_scope = "#pywebio-scope-" + scope
    if not session:
        session = ctx["get_session_implement"]().get_current_session()
    data = {
        "command": "output",
        "spec": {
            "type": type,
            "content": msg,
            "inline": True,
            "position": -1,
            "sanitize": True,
            "scope": target_scope,
        },
        "task_id": "_start_main_task-Qoqo1zPS7O",
    }
    {"level": "DEBUG", "source": "deva.admin", "message": "put_out send_task_command", "scope": scope, "type": type} >> ctx["log"]
    return session.send_task_command(data)


async def write_to_log(ctx):
    text = await ctx["pin"].write_to_log
    ctx["logbox_append"]("log", text + "\n")
    text >> ctx["log"]


def show_timer_detail(ctx, t):
    ctx["clear"]("timer_content")
    with ctx["use_scope"]("timer_content"):
        table_data = [
            ["属性", "值"],
            ["函数名", t.func.__name__],
            ["功能描述", t.func.__doc__.strip() if t.func.__doc__ else "无描述"],
            ["执行间隔", f"{t.interval}秒"],
            ["执行状态", "运行中" if t.started else "已停止"],
            ["生命周期", f"{t.ttl}秒"],
            ["下游消费者", ", ".join(map(str, t.downstreams)) or "无"],
        ]
        ctx["put_markdown"](f"### {t.func.__name__} 任务详情")
        ctx["put_table"](table_data)


async def init_admin_ui(ctx, title):
    ctx["setup_admin_runtime"](enable_webviews=True, enable_timer=True, enable_scheduler=True)
    cut_foot(ctx)
    
    from ..config import config
    auth_config = config.get_auth_config()
    username = str(auth_config.get("username") or "").strip()
    password = str(auth_config.get("password") or "").strip()
    
    if not username or not password:
        ctx["put_markdown"]("### 首次使用引导")
        ctx["put_markdown"]("检测到尚未初始化管理员账号，请先创建登录用户名和密码。")

        def _validate_account(data):
            if not str(data.get("username", "")).strip():
                return ("username", "用户名不能为空")
            if len(str(data.get("password", ""))) < 6:
                return ("password", "密码至少 6 位")
            if data.get("password") != data.get("password_confirm"):
                return ("password_confirm", "两次输入的密码不一致")
            return None

        created = await ctx["input_group"](
            "创建管理员账户",
            [
                ctx["input"]("用户名", name="username", required=True, placeholder="请输入管理员用户名"),
                ctx["input"]("密码", type=ctx["PASSWORD"], name="password", required=True, placeholder="至少 6 位"),
                ctx["input"]("确认密码", type=ctx["PASSWORD"], name="password_confirm", required=True, placeholder="再次输入密码"),
            ],
            validate=_validate_account,
        )
        new_username = str(created["username"]).strip()
        new_password = str(created["password"])
        
        config.set("auth.username", new_username)
        config.set("auth.password", new_password)
        auth_config = config.get_auth_config()
        
        ctx["toast"]("管理员账户已创建，请使用新账号登录", color="success")
    
    secret = config.ensure_auth_secret()
    verify_username = config.get("auth.username", "")
    verify_password = config.get("auth.password", "")
    
    user_name = await ctx["basic_auth"](
        lambda username, password: username == verify_username and password == verify_password,
        secret=secret,
    )
    ctx["create_sidebar"]()
    ctx["set_env"](title=title)
    ctx["create_nav_menu"]()
    ctx["put_text"](f"Hello, {user_name}. 欢迎光临，恭喜发财")


async def show_browser_status(ctx):
    tabs = ctx["tabs"]
    if not tabs:
        with ctx["use_scope"]("browser_status"):
            ctx["clear"]("browser_status")
            ctx["put_text"]("当前没有打开的浏览器标签页")
        return None

    browser = ctx["browser"]
    browser.table_data = [["序号", "URL", "标题", "操作"]]
    tabs_copy = list(tabs)
    for i, tab in enumerate(tabs_copy):
        try:
            article = await asyncio.wait_for(tab.article, timeout=10.0)
            page = await asyncio.wait_for(tab.page, timeout=5.0)
        except asyncio.TimeoutError:
            ctx["toast"](f"加载标签页超时: {tab.url}", color="warning")
            continue
        if not page:
            continue
        if article:
            title = article.title
            summary = article.summary
        else:
            title = page.html.search("<title>{}</title>") | ctx["first"]
            summary = "无法获取摘要"
        actions = ctx["put_buttons"](
            [{"label": "查看", "value": "view"}, {"label": "关闭", "value": "close"}],
            onclick=lambda v, t=tab: ctx["view_tab"](t) if v == "view" else ctx["close_tab"](t),
        )
        browser.table_data.append([
            i + 1,
            ctx["truncate"](tab.url),
            ctx["put_html"](f'<span title="{summary}" style="cursor:pointer;text-decoration:underline dotted">{ctx["truncate"](title)}</span>'),
            actions,
        ])

    with ctx["use_scope"]("browser_status", clear=True):
        ctx["put_table"](browser.table_data)
    return browser.table_data


def view_tab(ctx, tab):
    async def get_content():
        ctx["toast"](f"正在加载: {tab.url}", color="info")
        try:
            article = await asyncio.wait_for(tab.article, timeout=15.0)
            if getattr(article, "text", None):
                ctx["popup"](f"{article.title}", [ctx["put_markdown"](">" + tab.url), ctx["put_markdown"](article.text)], size="large")
            else:
                ctx["popup"](f"iframe查看标签页 - {tab.url}", [ctx["put_html"](f'<iframe src="{tab.url}" style="width:100%;height:80vh;border:none;"></iframe>')], size="large")
        except asyncio.TimeoutError:
            ctx["toast"](f"加载标签页超时: {tab.url}", color="error")
            ctx["popup"](f"加载失败 - {tab.url}", [ctx["put_text"]("页面加载超时，请稍后重试。")], size="large")
        except Exception as e:
            ctx["toast"](f"加载标签页失败: {e}", color="error")
            ctx["popup"](f"加载失败 - {tab.url}", [ctx["put_text"](f"加载失败: {str(e)}")], size="large")

    ctx["run_async"](get_content())


def close_tab(ctx, tab):
    tab.close()
    ctx["toast"](f"已关闭标签页: {tab.url}")
    ctx["run_async"](ctx["show_browser_status"]())


async def open_new_tab(ctx):
    url = await ctx["input_group"]("请输入要打开的URL", [
        ctx["input"]("URL", name="url", type=ctx["TEXT"]),
        ctx["actions"]("操作", [{"label": "确定", "value": "confirm"}, {"label": "取消", "value": "cancel"}], name="action"),
    ])
    if url["action"] == "cancel":
        return
    raw_url = url["url"]
    if not raw_url:
        return
    url_pattern = re.compile(r"^https?://(?:www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b(?:[-a-zA-Z0-9()@:%_\+.~#?&//=]*)$")
    if not url_pattern.match(raw_url):
        ctx["toast"](f"无效的URL格式: {raw_url}", color="error")
        return
    ctx["toast"](f"浏览器在后台打开新标签页 ing: {raw_url}")
    ctx["tab"](raw_url)
    ctx["run_async"](ctx["show_browser_status"]())


def init_floating_menu_manager(ctx):
    js_code = """
    const FloatingMenuManager = {
        init() { this.restoreMenus(); },
        createMenu(content, title, menuId = null) {
            const menuCount = document.querySelectorAll('.summary-floating-menu').length;
            if (menuCount >= 10) { this.removeOldestMenu(); }
            const menuData = { content, title: title || '摘要', timestamp: Date.now() };
            if (!menuId) {
                menuId = `summary_menu_${Date.now()}`;
                localStorage.setItem(menuId, JSON.stringify(menuData));
            }
            const menu = this._createMenuElement(menuData, menuCount);
            menu.dataset.menuId = menuId;
            document.body.appendChild(menu);
            return menuId;
        },
        _createMenuElement(menuData, menuCount) {
            const { content, title } = menuData;
            const menu = document.createElement('div');
            menu.className = 'summary-floating-menu';
            Object.assign(menu.style, { position: 'fixed', bottom: '20px', right: `${20 + (menuCount * 60)}px`, zIndex: String(1000 + menuCount), backgroundColor: '#fff', borderRadius: '5px', boxShadow: '0 2px 10px rgba(0,0,0,0.1)', padding: '10px', cursor: 'pointer', width: '50px', height: '50px', display: 'flex', justifyContent: 'center', alignItems: 'center', transition: 'all 0.3s ease' });
            const icon = document.createElement('div'); icon.innerText = '📄'; icon.style.fontSize = '24px'; menu.appendChild(icon);
            const tooltip = document.createElement('div'); tooltip.innerText = title; Object.assign(tooltip.style, { position: 'absolute', bottom: '60px', left: '50%', transform: 'translateX(-50%)', backgroundColor: '#333', color: '#fff', padding: '5px 10px', borderRadius: '4px', fontSize: '12px', whiteSpace: 'nowrap', opacity: '0', transition: 'opacity 0.2s ease', pointerEvents: 'none' }); menu.appendChild(tooltip);
            const deleteBtn = document.createElement('div'); deleteBtn.innerText = '×'; Object.assign(deleteBtn.style, { position: 'absolute', top: '-5px', right: '-5px', width: '20px', height: '20px', backgroundColor: '#ff4444', color: '#fff', borderRadius: '50%', display: 'flex', justifyContent: 'center', alignItems: 'center', cursor: 'pointer', opacity: '0', transition: 'opacity 0.2s ease' }); menu.appendChild(deleteBtn);
            menu.onmouseenter = () => { menu.style.transform = 'scale(1.1)'; menu.style.boxShadow = '0 4px 15px rgba(0,0,0,0.2)'; tooltip.style.opacity = '1'; deleteBtn.style.opacity = '1'; };
            menu.onmouseleave = () => { menu.style.transform = 'scale(1)'; menu.style.boxShadow = '0 2px 10px rgba(0,0,0,0.1)'; tooltip.style.opacity = '0'; deleteBtn.style.opacity = '0'; };
            menu.onclick = () => this.showPopup(content, title);
            deleteBtn.onclick = (e) => { e.stopPropagation(); this.removeMenu(menu.dataset.menuId); };
            return menu;
        },
        removeMenu(menuId) {
            const menu = document.querySelector(`[data-menu-id="${menuId}"]`);
            if (menu) { menu.remove(); localStorage.removeItem(menuId); this.adjustMenuPositions(); }
        },
        removeOldestMenu() {
            const menus = Array.from(document.querySelectorAll('.summary-floating-menu'));
            if (menus.length === 0) return;
            const oldestMenu = menus.reduce((oldest, current) => {
                const oldestTime = JSON.parse(localStorage.getItem(oldest.dataset.menuId))?.timestamp || 0;
                const currentTime = JSON.parse(localStorage.getItem(current.dataset.menuId))?.timestamp || 0;
                return oldestTime < currentTime ? oldest : current;
            });
            this.removeMenu(oldestMenu.dataset.menuId);
        },
        adjustMenuPositions() {
            const menus = document.querySelectorAll('.summary-floating-menu');
            menus.forEach((menu, index) => { menu.style.right = `${20 + (index * 60)}px`; });
        },
        restoreMenus() {
            Object.keys(localStorage).forEach(key => {
                if (key.startsWith('summary_menu_')) {
                    const data = JSON.parse(localStorage.getItem(key));
                    if (data) this.createMenu(data.content, data.title, key);
                }
            });
        },
        showPopup(content, title) {
            const popup = document.createElement('div');
            popup.className = 'summary-popup';
            Object.assign(popup.style, { position: 'fixed', top: '50%', left: '50%', transform: 'translate(-50%, -50%)', backgroundColor: '#fff', padding: '20px', borderRadius: '8px', boxShadow: '0 4px 20px rgba(0,0,0,0.2)', maxWidth: '80%', maxHeight: '80vh', overflow: 'auto', zIndex: '2000' });
            const titleEl = document.createElement('h3'); titleEl.innerText = title; titleEl.style.marginBottom = '10px';
            const contentEl = document.createElement('div'); contentEl.innerHTML = content.replace(/\\n/g, '<br>');
            const closeBtn = document.createElement('button'); closeBtn.innerText = '关闭'; closeBtn.style.marginTop = '15px'; closeBtn.onclick = () => popup.remove();
            popup.appendChild(titleEl); popup.appendChild(contentEl); popup.appendChild(closeBtn); document.body.appendChild(popup);
        }
    };
    if (!window.FloatingMenuManager) { window.FloatingMenuManager = FloatingMenuManager; FloatingMenuManager.init(); }
    """
    ctx["run_js"](js_code)


async def dynamic_popup(ctx, title, async_content_func):
    with ctx["popup"]("Dynamic Popup", closable=True):
        scope = "Dynamic_summary"
        session = ctx["get_session_implement"]().get_current_session()
        with ctx["use_scope"](scope, clear=True):
            try:
                summary = await ctx["run_asyncio_coroutine"](async_content_func(session=session, scope=scope))
            except Exception as e:
                e >> ctx["log"]
                summary = ""
                ctx["toast"](f"生成摘要失败: {str(e)}", color="error")
        with ctx["use_scope"](scope, clear=True):
            ctx["put_out"](summary, type="markdown", scope=scope, session=session)
            summary >> ctx["log"]
            ctx["put_button"]("发送到钉钉", onclick=lambda: ("@md@焦点分析|" + summary >> ctx["Dtalk"]()) and ctx["toast"]("已发送到钉钉"))
            ctx["run_js"](f"""
                const summaryScope = document.getElementById('pywebio-scope-{scope}');
                const summaryContent = summaryScope.innerHTML;
                const firstLine = summaryScope.querySelector('h1, h2, h3, h4, h5, h6, p')?.innerText || '';
                const summaryTitle = firstLine.substring(0, 20) + (firstLine.length > 20 ? '...' : '');
                if (!window.FloatingMenuManager) {{ console.warn('FloatingMenuManager not initialized'); }}
                FloatingMenuManager.createMenu(summaryContent, summaryTitle);
            """)


async def summarize_tabs(ctx):
    all_tabs = list(ctx["tabs"])
    contents = []
    
    # 并发控制 - 最多同时处理3个标签页
    semaphore = asyncio.Semaphore(3)
    
    async def get_tab_content(tab):
        async with semaphore:
            try:
                article = await asyncio.wait_for(tab.article, timeout=8.0)
                if hasattr(article, "text"):
                    return article.text
            except asyncio.TimeoutError:
                (f"获取标签页 {tab.url} 内容超时") >> ctx["log"]
            except Exception as e:
                (f"获取标签页 {tab.url} 内容时出错: {e}") >> ctx["log"]
        return None
    
    # 并发获取所有标签页内容
    tasks = [get_tab_content(tab) for tab in all_tabs]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # 过滤有效内容
    for result in results:
        if isinstance(result, str) and result:
            contents.append(result)
    
    if not contents:
        ctx["toast"]("没有可总结的内容", color="error")
        return
    combined_content = "\n\n".join(contents)
    if len(combined_content) > 20000:
        combined_content = combined_content[:20000]
        ctx["toast"]("内容过长，已截取前10000字符进行总结", color="warning")
    ctx["toast"]("正在生成摘要，请稍候...")

    async def async_content_func(session, scope):
        return await ctx["get_gpt_response"](
            prompt=f"请分析随后给的多篇新闻内容，要求返回的内容每一行都是一个一句话新闻，开头用一个和内容对应的图标，然后是一个不大于十个字的高度浓缩概括词，概括词用加粗字体，最后后面是新闻的一句话摘要，用破折号区隔开。每行一个新闻，不要有标题等其他任何介绍性内容，只需要返回6 条新闻即可。\n{combined_content}",
            session=session,
            scope=scope,
        )

    ctx["run_async"](ctx["dynamic_popup"](title="总结摘要", async_content_func=async_content_func))


def render_llm_config_guide(ctx, model_types=("kimi", "deepseek")):
    missing_status = []
    for model_type in model_types:
        status = get_model_config_status(ctx["NB"], model_type)
        if not status["ready"]:
            missing_status.append(status)

    if not missing_status:
        return

    ctx["put_markdown"]("### 模型配置引导")
    ctx["put_markdown"]("检测到以下模型配置未完成，相关功能将自动跳过。请在 Python 环境执行以下代码后刷新页面：")
    for status in missing_status:
        ctx["put_markdown"](f"#### {status['model_type']}")
        ctx["put_markdown"](
            "```python\n"
            + build_model_config_example(status["model_type"], status["missing"])
            + "\n```"
        )


async def async_json_gpt(ctx, prompts):
    status = get_model_config_status(ctx["NB"], "kimi")
    if not status["ready"]:
        message = build_model_config_message("kimi", status["missing"])
        message >> ctx["log"]
        ctx["toast"](message + " 请先完成配置。", color="warning")
        return None
    config = status["config"]
    if isinstance(prompts, str):
        prompts = [prompts]
    messages = [{"role": "user", "content": prompt} for prompt in prompts]

    async def _sync_http_fallback():
        url = config.get("base_url", "").rstrip("/") + "/chat/completions"
        headers = {
            "Authorization": f"Bearer {config.get('api_key')}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": config.get("model"),
            "messages": messages,
            "stream": False,
            "max_tokens": 8000,
            "response_format": {"type": "json_object"},
        }
        resp = await ctx["asyncio"].to_thread(
            ctx["requests"].post,
            url,
            headers=headers,
            data=ctx["json"].dumps(payload),
            timeout=30,
        )
        data = resp.json()
        if resp.status_code >= 400:
            raise RuntimeError(f"HTTP {resp.status_code}: {data}")
        return data["choices"][0]["message"]["content"]

    try:
        async def _openai_call():
            async_client = AsyncOpenAI(api_key=config.get("api_key"), base_url=config.get("base_url"))
            try:
                return await async_client.chat.completions.create(
                    model=config.get("model"),
                    messages=messages,
                    stream=False,
                    max_tokens=8000,
                    response_format={"type": "json_object"},
                )
            finally:
                await async_client.close()

        completion = await ctx["run_ai_in_worker"](_openai_call())
        return completion.choices[0].message.content
    except APIStatusError as e:
        status = getattr(e, "status_code", None)
        if status == 402:
            ctx["toast"]("模型余额不足（402），已跳过本次拓展阅读。", color="warning")
            ("GPT API余额不足(402): " + str(e)) >> ctx["log"]
        else:
            ctx["toast"](f"模型请求失败({status})，已跳过。", color="error")
            ("GPT API请求失败: " + str(e)) >> ctx["log"]
        return None
    except Exception as e:
        # Some environments (tornado callbacks / mixed runtimes) may not expose
        # a detectable async backend for httpx/anyio.
        if "unknown async library" in str(e):
            ("GPT API异步上下文异常，回退到同步HTTP通道: " + str(e)) >> ctx["log"]
            try:
                return await _sync_http_fallback()
            except Exception as fb_err:
                ctx["toast"](f"模型请求异常，回退失败: {fb_err}", color="error")
                ("GPT API回退失败: " + str(fb_err)) >> ctx["log"]
                return None
        ctx["toast"](f"模型请求异常，已跳过: {e}", color="error")
        ("GPT API异常: " + str(e)) >> ctx["log"]
        return None


async def extract_important_links(ctx, page):
    all_links = []
    for link in page.html.find("a"):
        href = link.attrs.get("href", "")
        if not href:
            continue
        full_url = urljoin(page.url, href)
        title = link.text.strip()
        if title:
            all_links.append({"title": title, "url": full_url})
    prompt = f"""
    作为一个新闻分析师，请从下面数据是一个网页里面的连接数据，分析一下哪些连接是经常更新发布的链接，从链接位置和特征，分析找出最新的10个链接, 再按照链接的标题内容判断这 10 个链接嘴重要的 3 个链接，最后返回这 3 个链接\n{all_links}
    最终返回的json,这是您需要的 JSON 数据：
    {{
      "news_links": [
        {{"title": "......","url": "http://....."}},
        {{"title": "......","url": "http://....."}},
        {{"title": "......","url": "http://....."}}
      ]
    }}
    严格遵守 JSON 格式，不返回额外解释或多余文本。
    """
    response = await ctx["async_json_gpt"](prompt)
    if not response:
        return {"news_links": []}
    try:
        payload = json.loads(response)
    except Exception as e:
        ("解析模型JSON失败: " + str(e)) >> ctx["log"]
        return {"news_links": []}
    if not isinstance(payload, dict):
        return {"news_links": []}
    links = payload.get("news_links")
    if not isinstance(links, list):
        payload["news_links"] = []
    return payload


def truncate(text, max_length=20):
    return text if len(text) <= max_length else text[:max_length] + "..."


def set_table_style(ctx):
    ctx["put_html"]("""
    <style>
      table { table-layout: fixed; width: 100%; border-collapse: collapse; }
      td, th { max-width: 250px; word-wrap: break-word; white-space: normal; padding: 10px; border-bottom: 1px solid #e5e7eb; }
      th { background: #f8fafc; font-weight: 600; text-align: left; }
      tr:hover { background: #f1f5f9; }
    </style>
    """)


def apply_global_styles(ctx):
    ctx["put_html"]("""
    <style>
      :root {
        --primary-color: #3b82f6;
        --primary-hover: #2563eb;
        --success-color: #10b981;
        --danger-color: #ef4444;
        --warning-color: #f59e0b;
        --bg-color: #f8fafc;
        --card-bg: #ffffff;
        --border-color: #e2e8f0;
        --text-primary: #1e293b;
        --text-secondary: #64748b;
        --shadow-sm: 0 1px 2px 0 rgb(0 0 0 / 0.05);
        --shadow-md: 0 4px 6px -1px rgb(0 0 0 / 0.1);
        --shadow-lg: 0 10px 15px -3px rgb(0 0 0 / 0.1);
        --radius-sm: 6px;
        --radius-md: 10px;
        --radius-lg: 16px;
      }
      body {
        background: var(--bg-color);
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
        color: var(--text-primary);
        line-height: 1.6;
      }
      .container-fluid { max-width: 1400px; margin: 0 auto; padding: 20px; }
      .card {
        background: var(--card-bg);
        border-radius: var(--radius-lg);
        box-shadow: var(--shadow-md);
        padding: 20px;
        margin-bottom: 20px;
        border: 1px solid var(--border-color);
        transition: box-shadow 0.2s ease;
      }
      .card:hover { box-shadow: var(--shadow-lg); }
      .card-title {
        font-size: 18px;
        font-weight: 600;
        color: var(--text-primary);
        margin-bottom: 16px;
        padding-bottom: 12px;
        border-bottom: 2px solid var(--primary-color);
        display: flex;
        align-items: center;
        gap: 8px;
      }
      .card-title::before {
        content: '';
        width: 4px;
        height: 20px;
        background: var(--primary-color);
        border-radius: 2px;
      }
      .btn-group { display: flex; gap: 10px; flex-wrap: wrap; margin: 12px 0; }
      .btn {
        padding: 8px 16px;
        border-radius: var(--radius-sm);
        font-size: 14px;
        font-weight: 500;
        cursor: pointer;
        transition: all 0.2s ease;
        border: none;
        display: inline-flex;
        align-items: center;
        gap: 6px;
      }
      .btn-primary { background: var(--primary-color); color: white; }
      .btn-primary:hover { background: var(--primary-hover); transform: translateY(-1px); }
      .btn-danger { background: var(--danger-color); color: white; }
      .btn-danger:hover { background: #dc2626; transform: translateY(-1px); }
      .btn-success { background: var(--success-color); color: white; }
      .btn-success:hover { background: #059669; transform: translateY(-1px); }
      .btn-outline { background: transparent; border: 1px solid var(--border-color); color: var(--text-primary); }
      .btn-outline:hover { background: var(--bg-color); border-color: var(--primary-color); }
      .input-field {
        padding: 10px 14px;
        border: 1px solid var(--border-color);
        border-radius: var(--radius-sm);
        font-size: 14px;
        transition: border-color 0.2s ease, box-shadow 0.2s ease;
        width: 100%;
        box-sizing: border-box;
      }
      .input-field:focus { outline: none; border-color: var(--primary-color); box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1); }
      .section-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(400px, 1fr)); gap: 20px; }
      .stat-card {
        background: linear-gradient(135deg, var(--primary-color) 0%, #8b5cf6 100%);
        color: white;
        border-radius: var(--radius-md);
        padding: 20px;
        text-align: center;
      }
      .stat-value { font-size: 32px; font-weight: 700; }
      .stat-label { font-size: 14px; opacity: 0.9; }
      .badge {
        display: inline-block;
        padding: 4px 10px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: 500;
      }
      .badge-success { background: #dcfce7; color: #166534; }
      .badge-warning { background: #fef3c7; color: #92400e; }
      .badge-danger { background: #fee2e2; color: #991b1b; }
      .collapse-header { cursor: pointer; user-select: none; }
      .collapse-content { animation: fadeIn 0.3s ease; }
      @keyframes fadeIn { from { opacity: 0; transform: translateY(-10px); } to { opacity: 1; transform: translateY(0); } }
      @media (max-width: 768px) {
        .section-grid { grid-template-columns: 1fr; }
        .container-fluid { padding: 10px; }
      }
    </style>
    """)


def show_bus_status(ctx):
    status = ctx["get_bus_runtime_status"]()
    rows = [["字段", "值"]]
    for key in ["mode", "type", "topic", "group", "connected", "stopped", "redis_ready", "loop_running", "error"]:
        rows.append([key, str(status.get(key, ""))])
    with ctx["use_scope"]("bus_status", clear=True):
        ctx["put_table"](rows)


def _fmt_ts(ts):
    try:
        return __import__("datetime").datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(ts)


def show_bus_clients(ctx):
    clients = ctx["get_bus_clients"]()
    rows = [["client_key", "pid", "host", "mode", "group", "started_at", "updated_at"]]
    for c in clients:
        rows.append([
            str(c.get("client_key", "")),
            str(c.get("pid", "")),
            str(c.get("host", "")),
            str(c.get("mode", "")),
            str(c.get("group", "")),
            _fmt_ts(c.get("started_at")),
            _fmt_ts(c.get("updated_at")),
        ])
    if len(rows) == 1:
        rows.append(["-", "-", "-", "-", "-", "-", "-"])
    with ctx["use_scope"]("bus_clients", clear=True):
        ctx["put_table"](rows)


def show_bus_recent_messages(ctx, limit=20):
    msgs = ctx["get_bus_recent_messages"](limit=limit)
    rows = [["#", "ts", "sender", "message"]]
    for i, item in enumerate(reversed(msgs), start=1):
        if isinstance(item, dict):
            ts = _fmt_ts(item.get("ts"))
            sender = str(item.get("sender", ""))
            message = str(item.get("message", item))
        else:
            ts = "-"
            sender = "-"
            message = str(item)
        rows.append([str(i), ts, sender, message[:300]])
    if len(rows) == 1:
        rows.append(["-", "-", "-", "-"])
    with ctx["use_scope"]("bus_messages", clear=True):
        ctx["put_table"](rows)


def refresh_bus_admin(ctx):
    show_bus_status(ctx)
    show_bus_clients(ctx)
    show_bus_recent_messages(ctx, limit=20)


def send_bus_message_from_input(ctx):
    async def _send():
        message = await ctx["pin"].bus_message_input
        if not message:
            ctx["toast"]("请输入消息内容", color="warning")
            return
        try:
            ctx["send_bus_message"](message=message, sender="admin")
            ctx["toast"]("消息已发送到 bus", color="success")
            refresh_bus_admin(ctx)
        except Exception as e:
            ctx["toast"](f"发送失败: {e}", color="error")

    ctx["run_async"](_send())


async def process_tabs(ctx, session):
    # 限制同时处理的标签页数量
    MAX_CONCURRENT_TABS = 3
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_TABS)
    
    async def process_single_tab(t):
        async with semaphore:
            try:
                page = await asyncio.wait_for(t.page, timeout=10.0)
                j = await asyncio.wait_for(ctx["extract_important_links"](page), timeout=15.0)
                links = j.get("news_links", [])
                links >> ctx["log"]
                
                # 限制同时打开的链接数量
                MAX_CONCURRENT_LINKS = 5
                for i in links[:MAX_CONCURRENT_LINKS]:
                    try:
                        url = i.get("url") if isinstance(i, dict) else None
                        if not url:
                            continue
                        nt = ctx["tab"](url)
                        p = await asyncio.wait_for(nt.page, timeout=8.0)
                        if p:
                            session.run_async(ctx["show_browser_status"]())
                            (p.url, p.article.summary) >> ctx["log"]
                    except asyncio.TimeoutError:
                        (f"处理链接超时: {url}") >> ctx["log"]
                        continue
                    except Exception as link_error:
                        ("处理链接失败: " + str(link_error)) >> ctx["log"]
                        continue
            except asyncio.TimeoutError:
                (f"处理标签页超时: {t.url}") >> ctx["log"]
                return
            except Exception as tab_error:
                ("处理标签页失败: " + str(tab_error)) >> ctx["log"]
                return
    
    # 并发处理标签页
    tasks = [process_single_tab(t) for t in list(ctx["tabs"])]
    await asyncio.gather(*tasks, return_exceptions=True)


def extended_reading(ctx):
    session = ctx["get_session_implement"]().get_current_session()
    async def _launch():
        await ctx["process_tabs"](session)
    ctx["run_async"](_launch())
    ctx["toast"]("已开始拓展阅读任务", color="info")


async def close_all_tabs(ctx):
    if not ctx["tabs"]:
        ctx["toast"]("当前没有打开的标签页", color="info")
        return
    confirm = await ctx["actions"]("确认关闭所有标签页吗？", [{"label": "确认", "value": "confirm"}, {"label": "取消", "value": "cancel"}])
    if confirm == "confirm":
        for tab in list(ctx["tabs"]):
            tab.close()
        ctx["toast"]("所有标签页已关闭", color="success")
        await ctx["show_browser_status"]()


def create_sidebar(ctx):
    ctx["set_scope"]("sidebar")
    ctx["run_js"]('''
        const sidebar = document.createElement('div');
        sidebar.id = 'custom-sidebar';
        Object.assign(sidebar.style, {
            position: 'fixed',
            right: '0',
            top: '0',
            width: '340px',
            height: '100vh',
            backgroundColor: '#ffffff',
            boxShadow: '-4px 0 20px rgba(0,0,0,0.08)',
            transition: 'transform 0.35s cubic-bezier(0.4, 0, 0.2, 1)',
            zIndex: '1000',
            borderLeft: '1px solid #e2e8f0',
            display: 'flex',
            flexDirection: 'column'
        });
        const sidebarHeader = document.createElement('div');
        Object.assign(sidebarHeader.style, {
            padding: '16px 20px',
            borderBottom: '1px solid #e2e8f0',
            backgroundColor: '#f8fafc',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between'
        });
        sidebarHeader.innerHTML = '<span style="font-weight: 600; color: #1e293b; font-size: 15px;">📋 访问日志</span>';
        const toggleBtn = document.createElement('div');
        Object.assign(toggleBtn.style, {
            position: 'absolute',
            left: '-48px',
            top: '50%',
            transform: 'translateY(-50%)',
            width: '48px',
            height: '80px',
            backgroundColor: '#ffffff',
            borderRadius: '12px 0 0 12px',
            boxShadow: '-4px 0 12px rgba(0,0,0,0.08)',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            border: '1px solid #e2e8f0',
            borderRight: 'none',
            transition: 'all 0.2s ease'
        });
        let isOpen = localStorage.getItem('sidebarState') !== 'closed';
        sidebar.style.transform = isOpen ? 'translateX(0)' : 'translateX(100%)';
        toggleBtn.innerHTML = isOpen ? '<span style="font-size: 20px; color: #64748b;">→</span>' : '<span style="font-size: 20px; color: #64748b;">←</span>';
        toggleBtn.onmouseenter = () => { toggleBtn.style.backgroundColor = '#f1f5f9'; };
        toggleBtn.onmouseleave = () => { toggleBtn.style.backgroundColor = '#ffffff'; };
        toggleBtn.onclick = function() {
            isOpen = !isOpen;
            sidebar.style.transform = isOpen ? 'translateX(0)' : 'translateX(100%)';
            toggleBtn.innerHTML = isOpen ? '<span style="font-size: 20px; color: #64748b;">→</span>' : '<span style="font-size: 20px; color: #64748b;">←</span>';
            localStorage.setItem('sidebarState', isOpen ? 'open' : 'closed');
            const mainContent = document.querySelector('.container-fluid');
            if (mainContent) {
                mainContent.style.marginRight = isOpen ? '340px' : '0';
                mainContent.style.transition = 'margin-right 0.35s cubic-bezier(0.4, 0, 0.2, 1)';
            }
        };
        const mainContent = document.querySelector('.container-fluid');
        if (mainContent) { mainContent.style.marginRight = isOpen ? '340px' : '0'; }
        const sidebarContent = document.createElement('div');
        Object.assign(sidebarContent.style, { flex: '1', overflow: 'hidden' });
        sidebar.appendChild(sidebarHeader);
        sidebar.appendChild(sidebarContent);
        sidebar.appendChild(toggleBtn);
        document.body.appendChild(sidebar);
        const sidebarScope = document.getElementById('pywebio-scope-sidebar');
        if (sidebarScope) { sidebarContent.appendChild(sidebarScope); }
    ''')
    with ctx["use_scope"]("sidebar"):
        ctx["put_html"](f"""<iframe src="/{hash(ctx["NS"]('访问日志'))}" style="width:100%;height:calc(100vh - 60px);border:none;background:#fff;"></iframe>""")


def create_nav_menu(ctx):
    ctx["run_js"]('''
        const nav = document.createElement('nav');
        nav.className = 'navbar';
        Object.assign(nav.style, {
            position: 'fixed',
            top: '0',
            left: '0',
            right: '0',
            width: '100%',
            zIndex: '999',
            backgroundColor: '#ffffff',
            borderBottom: '1px solid #e2e8f0',
            padding: '0 24px',
            height: '60px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            boxShadow: '0 1px 3px rgba(0,0,0,0.05)'
        });
        const brand = document.createElement('div');
        brand.className = 'brand';
        const brandLink = document.createElement('a');
        brandLink.href = '/';
        brandLink.innerHTML = '<span style="font-size: 22px; font-weight: 700; color: #3b82f6;">⚡</span><span style="font-size: 18px; font-weight: 600; color: #1e293b; margin-left: 8px;">Deva</span>';
        brandLink.style.textDecoration = 'none';
        brandLink.style.display = 'flex';
        brandLink.style.alignItems = 'center';
        brand.appendChild(brandLink);
        
        const menu = document.createElement('div');
        menu.className = 'nav-menu';
        Object.assign(menu.style, {
            display: 'flex',
            gap: '4px',
            alignItems: 'center'
        });
        
        const hamburger = document.createElement('button');
        hamburger.className = 'hamburger';
        hamburger.innerHTML = '<span></span><span></span><span></span>';
        Object.assign(hamburger.style, {
            display: 'none',
            flexDirection: 'column',
            justifyContent: 'space-around',
            width: '30px',
            height: '25px',
            background: 'transparent',
            border: 'none',
            cursor: 'pointer',
            padding: '0'
        });
        hamburger.querySelectorAll('span').forEach(span => {
            Object.assign(span.style, {
                width: '100%',
                height: '3px',
                background: '#1e293b',
                borderRadius: '2px',
                transition: 'all 0.3s ease'
            });
        });
        
        const currentPath = window.location.pathname;
        const menuItems = [
            {name: '🏠 首页', path: '/', action: () => {
                window.__pageNavigating = true;
                if (window.sseConnection) {
                    try {
                        window.sseConnection.close();
                    } catch (e) {}
                    window.sseConnection = null;
                }
                window.location.href = '/';
            }},
            {name: '⭐ 关注', path: '/followadmin', action: () => {
                window.__pageNavigating = true;
                if (window.sseConnection) {
                    try {
                        window.sseConnection.close();
                    } catch (e) {}
                    window.sseConnection = null;
                }
                window.location.href = '/followadmin';
            }},
            {name: '🌐 浏览器', path: '/browseradmin', action: () => {
                window.__pageNavigating = true;
                if (window.sseConnection) {
                    try {
                        window.sseConnection.close();
                    } catch (e) {}
                    window.sseConnection = null;
                }
                window.location.href = '/browseradmin';
            }},
            {name: '💾 数据库', path: '/dbadmin', action: () => {
                window.__pageNavigating = true;
                if (window.sseConnection) {
                    try {
                        window.sseConnection.close();
                    } catch (e) {}
                    window.sseConnection = null;
                }
                window.location.href = '/dbadmin';
            }},
            {name: '🚌 Bus', path: '/busadmin', action: () => {
                window.__pageNavigating = true;
                if (window.sseConnection) {
                    try {
                        window.sseConnection.close();
                    } catch (e) {}
                    window.sseConnection = null;
                }
                window.location.href = '/busadmin';
            }},
            {name: '📊 命名流', path: '/streamadmin', action: () => {
                window.__pageNavigating = true;
                if (window.sseConnection) {
                    try {
                        window.sseConnection.close();
                    } catch (e) {}
                    window.sseConnection = null;
                }
                window.location.href = '/streamadmin';
            }},
            {name: '📡 数据源', path: '/datasourceadmin', action: () => {
                window.__pageNavigating = true;
                if (window.sseConnection) {
                    try {
                        window.sseConnection.close();
                    } catch (e) {}
                    window.sseConnection = null;
                }
                window.location.href = '/datasourceadmin';
            }},
            {name: '📈 策略', path: '/strategyadmin', action: () => {
                window.__pageNavigating = true;
                if (window.sseConnection) {
                    try {
                        window.sseConnection.close();
                    } catch (e) {}
                    window.sseConnection = null;
                }
                window.location.href = '/strategyadmin';
            }},
            {name: '👁 监控', path: '/monitor', action: () => {
                window.__pageNavigating = true;
                if (window.sseConnection) {
                    try {
                        window.sseConnection.close();
                    } catch (e) {}
                    window.sseConnection = null;
                }
                window.location.href = '/monitor';
            }},
            {name: '⏰ 任务', path: '/taskadmin', action: () => {
                window.__pageNavigating = true;
                if (window.sseConnection) {
                    try {
                        window.sseConnection.close();
                    } catch (e) {}
                    window.sseConnection = null;
                }
                window.location.href = '/taskadmin';
            }},
            {name: '⚙️ 配置', path: '/configadmin', action: () => {
                window.__pageNavigating = true;
                if (window.sseConnection) {
                    try {
                        window.sseConnection.close();
                    } catch (e) {}
                    window.sseConnection = null;
                }
                window.location.href = '/configadmin';
            }},
            {name: '📄 文档', path: '/document', action: () => {
                window.__pageNavigating = true;
                if (window.sseConnection) {
                    try {
                        window.sseConnection.close();
                    } catch (e) {}
                    window.sseConnection = null;
                }
                window.location.href = '/document';
            }}
        ];
        menuItems.forEach(item => {
            const link = document.createElement('a');
            link.href = item.path;
            link.innerText = item.name;
            const isActive = currentPath === item.path;
            Object.assign(link.style, {
                padding: '8px 14px',
                color: isActive ? '#3b82f6' : '#64748b',
                textDecoration: 'none',
                borderRadius: '8px',
                fontSize: '14px',
                fontWeight: isActive ? '600' : '500',
                backgroundColor: isActive ? '#eff6ff' : 'transparent',
                transition: 'all 0.2s ease',
                display: 'flex',
                alignItems: 'center',
                whiteSpace: 'nowrap'
            });
            link.onmouseenter = () => {
                if (!isActive) {
                    link.style.backgroundColor = '#f1f5f9';
                    link.style.color = '#1e293b';
                }
            };
            link.onmouseleave = () => {
                link.style.backgroundColor = isActive ? '#eff6ff' : 'transparent';
                link.style.color = isActive ? '#3b82f6' : '#64748b';
            };
            link.onclick = item.action;
            menu.appendChild(link);
        });
        
        let isMenuOpen = false;
        hamburger.onclick = () => {
            isMenuOpen = !isMenuOpen;
            if (isMenuOpen) {
                menu.style.display = 'flex';
                menu.style.flexDirection = 'column';
                menu.style.position = 'absolute';
                menu.style.top = '60px';
                menu.style.left = '0';
                menu.style.right = '0';
                menu.style.backgroundColor = '#ffffff';
                menu.style.padding = '16px';
                menu.style.boxShadow = '0 4px 20px rgba(0,0,0,0.15)';
                menu.style.borderTop = '1px solid #e2e8f0';
                hamburger.style.transform = 'rotate(90deg)';
            } else {
                menu.style.display = 'flex';
                menu.style.flexDirection = 'row';
                menu.style.position = 'static';
                menu.style.padding = '0';
                menu.style.boxShadow = 'none';
                menu.style.borderTop = 'none';
                hamburger.style.transform = 'rotate(0deg)';
            }
        };
        
        const handleResize = () => {
            if (window.innerWidth <= 768) {
                hamburger.style.display = 'flex';
                menu.style.display = isMenuOpen ? 'flex' : 'none';
                menu.style.flexDirection = 'column';
                menu.style.position = 'absolute';
                menu.style.top = '60px';
                menu.style.left = '0';
                menu.style.right = '0';
                menu.style.backgroundColor = '#ffffff';
                menu.style.padding = isMenuOpen ? '16px' : '0';
                menu.style.boxShadow = isMenuOpen ? '0 4px 20px rgba(0,0,0,0.15)' : 'none';
                menu.style.borderTop = isMenuOpen ? '1px solid #e2e8f0' : 'none';
            } else {
                hamburger.style.display = 'none';
                menu.style.display = 'flex';
                menu.style.flexDirection = 'row';
                menu.style.position = 'static';
                menu.style.padding = '0';
                menu.style.boxShadow = 'none';
                menu.style.borderTop = 'none';
                menu.style.marginLeft = '32px';
            }
        };
        
        window.addEventListener('resize', handleResize);
        handleResize();
        
        nav.appendChild(brand);
        nav.appendChild(menu);
        nav.appendChild(hamburger);
        document.body.insertBefore(nav, document.body.firstChild);
        document.body.style.paddingTop = '60px';
    ''')


def show_dtalk_archive(ctx):
    with ctx["use_scope"]("dtalk_archive_display", clear=True):
        dtalk_archive = ctx["NB"]("dtalk_archive")
        if not dtalk_archive:
            ctx["put_text"]("暂无 Dtalk 消息记录")
            return
        archive_table = [["时间", "消息内容", "操作"]]
        for timestamp, message in sorted(dtalk_archive.items(), key=lambda x: float(x[0]), reverse=True):
            readable_time = ctx["datetime"].fromtimestamp(float(timestamp)).strftime("%Y-%m-%d %H:%M:%S")
            display_message = message[:100] + "..." if len(message) > 100 else message
            actions = ctx["put_buttons"](
                [{"label": "查看", "value": "view"}, {"label": "删除", "value": "delete"}],
                onclick=lambda v, t=timestamp, m=message: ctx["view_dtalk_message"](t, m) if v == "view" else ctx["delete_dtalk_message"](t),
            )
            archive_table.append([readable_time, display_message, actions])
        ctx["put_table"](archive_table)
        ctx["put_button"]("清空所有消息", onclick=ctx["clear_all_dtalk_messages"], color="danger")


def view_dtalk_message(ctx, timestamp, message):
    readable_time = ctx["datetime"].fromtimestamp(float(timestamp)).strftime("%Y-%m-%d %H:%M:%S")
    ctx["popup"](f"Dtalk 消息 - {readable_time}", [
        ctx["put_markdown"](f"**发送时间:** {readable_time}"),
        ctx["put_markdown"]("**消息内容:**"),
        ctx["put_markdown"](message),
    ], size="large")


def delete_dtalk_message(ctx, timestamp):
    del ctx["NB"]("dtalk_archive")[timestamp]
    ctx["toast"]("消息已删除", color="success")
    ctx["show_dtalk_archive"]()


def clear_all_dtalk_messages(ctx):
    ctx["NB"]("dtalk_archive").clear()
    ctx["toast"]("所有消息已清空", color="success")
    ctx["show_dtalk_archive"]()


async def render_main(ctx):
    await ctx["init_admin_ui"]("Deva管理面板")
    ctx["init_floating_menu_manager"]()
    ctx["set_table_style"]()
    ctx["apply_global_styles"]()
    render_llm_config_guide(ctx)

    ctx["put_html"]('<div class="card"><div class="card-title">⏰ 定时任务</div>')
    timers = [s for s in ctx["Stream"].instances() if isinstance(s, ctx["timer"])]
    ctx["put_html"]('<div class="btn-group">')
    ctx["put_buttons"](buttons=[f"📋 {s.func.__name__}" for s in timers], onclick=[lambda t=t: ctx["show_timer_detail"](t) for t in timers])
    ctx["put_html"]('</div>')
    ctx["set_scope"]("timer_content")
    ctx["put_html"]('</div>')

    ctx["put_html"]('<div class="card"><div class="card-title">📋 系统日志</div>')
    ctx["log"].sse("/logsse")
    with ctx["put_collapse"]("实时日志", open=True):
        ctx["put_logbox"]("log", height=150)
    ctx["run_js"](ctx["sse_js"])

    with ctx["put_collapse"]("🔧 调试工具", open=False):
        ctx["put_html"]('<div style="display:flex;gap:10px;align-items:center;">')
        ctx["put_input"]("write_to_log", type="text", value="", placeholder="手动写入日志内容...")
        ctx["put_button"]("📤 发送", onclick=ctx["write_to_log"])
        ctx["put_html"]('</div>')
    ctx["put_html"]('</div>')

    ctx["put_html"]('<div class="card"><div class="card-title">📱 Dtalk 消息存档</div>')
    ctx["set_scope"]("dtalk_archive_display")
    ctx["show_dtalk_archive"]()
    ctx["put_html"]('</div>')


async def render_bus_admin(ctx):
    await ctx["init_admin_ui"]("Deva Bus 管理")
    ctx["put_markdown"]("### Bus 状态")
    ctx["put_row"]([
        ctx["put_button"]("刷新", onclick=lambda: refresh_bus_admin(ctx)).style("margin-right: 10px"),
        ctx["put_text"]("bus 已定位为跨进程 stream（Redis 优先，失败回退本地）。"),
    ]).style("display: flex; justify-content: flex-start; align-items: center")

    ctx["put_markdown"]("### 发送消息")
    ctx["put_row"]([
        ctx["put_input"]("bus_message_input", type="text", value="", placeholder="输入要发送到 bus 的消息"),
        ctx["put_button"]("发送到 Bus", onclick=lambda: send_bus_message_from_input(ctx)),
    ]).style("display: flex; justify-content: flex-start; align-items: center")

    ctx["put_markdown"]("### 已连接进程（心跳）")
    ctx["set_scope"]("bus_clients")

    ctx["put_markdown"]("### 最新消息")
    ctx["set_scope"]("bus_messages")

    ctx["set_scope"]("bus_status")
    refresh_bus_admin(ctx)
