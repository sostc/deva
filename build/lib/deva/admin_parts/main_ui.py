"""Main-page UI logic extracted from admin.py."""

from __future__ import annotations

import json
import re
from urllib.parse import urljoin

from openai import AsyncOpenAI, APIStatusError


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
    admin_info = ctx["NB"]("admin")
    if not admin_info.get("username"):
        admin_info = await ctx["input_group"]("创建管理员账户", [
            ctx["input"]("用户名", name="username"),
            ctx["input"]("密码", type=ctx["PASSWORD"], name="password"),
        ])
        ctx["NB"]("admin").update(admin_info)
    user_name = await ctx["basic_auth"](
        lambda username, password: username == admin_info["username"] and password == admin_info["password"],
        secret="random_value001",
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
        article = await tab.article
        page = await tab.page
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
        article = await tab.article
        if getattr(article, "text", None):
            ctx["popup"](f"{article.title}", [ctx["put_markdown"](">" + tab.url), ctx["put_markdown"](article.text)], size="large")
        else:
            ctx["popup"](f"iframe查看标签页 - {tab.url}", [ctx["put_html"](f'<iframe src="{tab.url}" style="width:100%;height:80vh;border:none;"></iframe>')], size="large")

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
    for tab in list(all_tabs):
        try:
            article = await tab.article
            if hasattr(article, "text"):
                contents.append(article.text)
        except Exception as e:
            (f"获取标签页 {tab.url} 内容时出错: {e}") >> ctx["log"]
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


async def async_json_gpt(ctx, prompts):
    config = ctx["NB"]("kimi")
    if isinstance(prompts, str):
        prompts = [prompts]
    messages = [{"role": "user", "content": prompt} for prompt in prompts]

    async def _sync_http_fallback():
        url = config["base_url"].rstrip("/") + "/chat/completions"
        headers = {
            "Authorization": f"Bearer {config['api_key']}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": config["model"],
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
            async_client = AsyncOpenAI(api_key=config["api_key"], base_url=config["base_url"])
            try:
                return await async_client.chat.completions.create(
                    model=config["model"],
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
      table { table-layout: fixed; width: 100%; }
      td, th { max-width: 250px; word-wrap: break-word; white-space: normal; }
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
    for t in list(ctx["tabs"]):
        try:
            page = await t.page
            j = await ctx["extract_important_links"](page)
            links = j.get("news_links", [])
            links >> ctx["log"]
            for i in links:
                try:
                    url = i.get("url") if isinstance(i, dict) else None
                    if not url:
                        continue
                    nt = ctx["tab"](url)
                    p = await nt.page
                    if p:
                        session.run_async(ctx["show_browser_status"]())
                        (p.url, p.article.summary) >> ctx["log"]
                except Exception as link_error:
                    ("处理链接失败: " + str(link_error)) >> ctx["log"]
                    continue
        except Exception as tab_error:
            ("处理标签页失败: " + str(tab_error)) >> ctx["log"]
            continue


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
        sidebar.style.position = 'fixed';
        sidebar.style.right = '0';
        sidebar.style.top = '0';
        sidebar.style.width = '300px';
        sidebar.style.height = '100vh';
        sidebar.style.backgroundColor = '#f5f5f5';
        sidebar.style.boxShadow = '-2px 0 5px rgba(0,0,0,0.1)';
        sidebar.style.transition = 'transform 0.3s ease';
        sidebar.style.zIndex = '1000';
        const toggleBtn = document.createElement('div');
        toggleBtn.style.position = 'absolute';
        toggleBtn.style.left = '-40px';
        toggleBtn.style.top = '20px';
        toggleBtn.style.width = '40px';
        toggleBtn.style.height = '40px';
        toggleBtn.style.backgroundColor = '#fff';
        toggleBtn.style.borderRadius = '5px 0 0 5px';
        toggleBtn.style.boxShadow = '-2px 0 5px rgba(0,0,0,0.1)';
        toggleBtn.style.cursor = 'pointer';
        toggleBtn.style.display = 'flex';
        toggleBtn.style.alignItems = 'center';
        toggleBtn.style.justifyContent = 'center';
        let isOpen = localStorage.getItem('sidebarState') !== 'closed';
        sidebar.style.transform = isOpen ? 'translateX(0)' : 'translateX(100%)';
        toggleBtn.innerHTML = isOpen ? '×' : '☰';
        toggleBtn.onclick = function() {
            isOpen = !isOpen;
            sidebar.style.transform = isOpen ? 'translateX(0)' : 'translateX(100%)';
            toggleBtn.innerHTML = isOpen ? '×' : '☰';
            localStorage.setItem('sidebarState', isOpen ? 'open' : 'closed');
            const mainContent = document.querySelector('.container-fluid');
            if (mainContent) {
                mainContent.style.marginRight = isOpen ? '300px' : '0';
                mainContent.style.transition = 'margin-right 0.3s ease';
            }
        };
        const mainContent = document.querySelector('.container-fluid');
        if (mainContent) { mainContent.style.marginRight = isOpen ? '300px' : '0'; }
        sidebar.appendChild(toggleBtn);
        document.body.appendChild(sidebar);
        const sidebarScope = document.getElementById('pywebio-scope-sidebar');
        sidebar.appendChild(sidebarScope);
    ''')
    with ctx["use_scope"]("sidebar"):
        ctx["put_html"](f"""<iframe src="{hash(ctx["NS"]('访问日志'))}" style="width:100%;height:120vh;border:none;"></iframe>""")


def create_nav_menu(ctx):
    ctx["run_js"]('''
        const nav = document.createElement('div');
        nav.className = 'navbar';
        nav.style.position = 'fixed';
        nav.style.top = '0';
        nav.style.width = '100%';
        nav.style.zIndex = '1000';
        nav.style.backgroundColor = '#f5f5f5';
        nav.style.borderBottom = '1px solid #ddd';
        nav.style.padding = '10px 20px';
        const brand = document.createElement('div');
        brand.className = 'brand';
        const brandLink = document.createElement('a');
        brandLink.href = '#';
        if (!/Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent)) {
            brandLink.innerText = document.title;
        }
        brandLink.style.fontSize = '20px';
        brandLink.style.fontWeight = 'bold';
        brandLink.style.color = '#333';
        brandLink.style.textDecoration = 'none';
        brand.appendChild(brandLink);
        const menu = document.createElement('div');
        menu.className = 'nav';
        menu.style.display = 'flex';
        menu.style.marginLeft = '20px';
        const currentPath = window.location.pathname;
        const menuItems = [
            {name: '首页', path: '/', action: () => location.reload()},
            {name: '数据库', path: '/dbadmin', action: () => window.location.href = '/dbadmin'},
            {name: 'Bus', path: '/busadmin', action: () => window.location.href = '/busadmin'},
            {name: '实时流', path: '/streamadmin', action: () => window.location.href = '/streamadmin'},
            {name: '任务', path: '/taskadmin', action: () => window.location.href = '/taskadmin'},
            {name: '文档', path: '/document', action: () => window.location.href = '/document'}
        ];
        menuItems.forEach(item => {
            const link = document.createElement('a');
            link.href = item.path;
            link.innerText = item.name;
            link.style.padding = '5px 15px';
            link.style.color = '#333';
            link.style.textDecoration = 'none';
            link.style.marginRight = '10px';
            link.style.borderRadius = '3px';
            if (currentPath === item.path) { link.style.backgroundColor = '#ddd'; }
            link.onmouseover = () => { link.style.backgroundColor = '#eee'; };
            link.onmouseout = () => { link.style.backgroundColor = currentPath === item.path ? '#ddd' : 'transparent'; };
            link.onclick = item.action;
            menu.appendChild(link);
        });
        nav.appendChild(brand);
        nav.appendChild(menu);
        document.body.insertBefore(nav, document.body.firstChild);
        document.body.style.paddingTop = '50px';
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

    topics = ctx["NB"]("topics").items()
    peoples = ctx["NB"]("people").items()
    ctx["put_markdown"]("### 焦点分析")
    people_table = [["人物", "描述", "操作"]]

    async def analyze_person(key, value):
        person = key
        action = "并将他的观点总结成几行经典的名言名句"
        full_prompt = f"获取关于{person}的最新6条新闻，要求返回的内容每一行都是一个一句话新闻，开头用一个和内容对应的图标，然后是一个不大于十个字的高度浓缩概括词，概括词用加粗字体，最后后面是新闻的一句话摘要，用破折号区隔开。每行一个新闻，不要有标题等其他任何介绍性内容，每行结尾也不要有类似[^2^]这样的引用标识，只需要返回6 条新闻即可。在新闻的最后面，总附加要求如下：{action}"
        async def async_content_func(session, scope):
            return await ctx["get_gpt_response"](prompt=full_prompt, session=session, scope=scope, model_type="kimi")
        ctx["run_async"](ctx["dynamic_popup"](title=f"人物分析: {key}", async_content_func=async_content_func))

    for key, value in peoples:
        actions = ctx["put_button"]("news", onclick=lambda k=key, v=value: ctx["run_async"](analyze_person(k, v)))
        people_table.append([ctx["truncate"](key), ctx["truncate"](value, 50), actions])

    topic_table = [["主题", "附加要求", "操作"]]
    action_inputs = {}

    async def analyze_topic(key, action_input):
        action = await ctx["pin"][ctx["stable_widget_id"](key, prefix="action")]
        topic = key
        full_prompt = f" 获取{topic}{action},要求返回的内容每一行都是一个一句话，开头用一个和内容对应的图标，然后是一个不大于十个字的高度浓缩概括词，概括词用加粗字体，再后面是一句话摘要，用破折号区隔开。每行一个内容，不要有标题等其他任何介绍性内容，只需要返回6 条新闻即可。"
        async def async_content_func(session, scope):
            return await ctx["get_gpt_response"](prompt=full_prompt, session=session, scope=scope, model_type="kimi")
        ctx["run_async"](ctx["dynamic_popup"](title=f"主题分析: {key}", async_content_func=async_content_func))

    for key, value in topics:
        action_input_name = ctx["stable_widget_id"](key, prefix="action")
        action_input = ctx["put_input"](name=action_input_name, value=value, placeholder="请输入附加要求")
        action_inputs[key] = action_input
        actions = ctx["put_button"]("分析", onclick=lambda k=key: ctx["run_async"](analyze_topic(k, action_inputs[k])))
        topic_table.append([ctx["truncate"](key), action_input, actions])

    ctx["put_row"]([
        ctx["put_table"](topic_table).style("width: 48%; margin-right: 2%"),
        ctx["put_table"](people_table).style("width: 48%; margin-left: 2%"),
    ]).style("display: flex; justify-content: space-between")

    ctx["put_markdown"]("### 浏览器")
    with ctx["put_collapse"]("书签", open=False):
        bookmarks = ctx["NB"]("bookmarks").items()
        bookmark_table = [["键", "值", "操作"]]
        for key, value in bookmarks:
            actions = ctx["put_buttons"](
                [{"label": "打开", "value": "open"}, {"label": "删除", "value": "delete"}],
                onclick=lambda v, k=key, val=value: (ctx["tab"](val), ctx["toast"](f"正在打开书签: {k}"), ctx["run_async"](ctx["show_browser_status"]())) if v == "open" else delete_bookmark(k),
            )
            bookmark_table.append([ctx["truncate"](key), ctx["truncate"](value, 50), actions])
        ctx["put_table"](bookmark_table)

        def open_all_bookmarks():
            for _, value in ctx["NB"]("bookmarks").items():
                ctx["tab"](value)
            ctx["toast"]("正在后台打开所有书签...")
            ctx["run_async"](ctx["show_browser_status"]())

        def delete_bookmark(key):
            ctx["NB"]("bookmarks").delete(key)
            ctx["toast"](f"已删除书签: {key}")
            ctx["run_js"]("window.location.reload()")

        ctx["put_row"]([
            ctx["put_button"]("一键打开所有书签", onclick=open_all_bookmarks).style("margin-right: 10px"),
            ctx["put_button"]("新建书签", onclick=lambda: ctx["edit_data_popup"](ctx["NB"]("bookmarks").items() | ctx["ls"], "bookmarks")),
        ]).style("display: flex; justify-content: flex-start; align-items: center")

    ctx["set_scope"]("browser_status")
    ctx["put_row"]([
        ctx["put_button"]("+ 标签页", onclick=ctx["open_new_tab"]).style("margin-right: 10px"),
        ctx["put_button"]("拓展阅读", onclick=lambda: (ctx["extended_reading"](), ctx["run_async"](ctx["show_browser_status"]()))).style("margin-right: 10px"),
        ctx["put_button"]("总结", onclick=ctx["summarize_tabs"]).style("margin-right: 10px"),
        ctx["put_button"]("关闭所有", onclick=lambda: ctx["run_async"](ctx["close_all_tabs"]()), color="danger"),
    ]).style("display: flex; justify-content: flex-start; align-items: center")
    ctx["run_async"](ctx["show_browser_status"]())

    ctx["put_markdown"]("### 定时任务")
    timers = [s for s in ctx["Stream"].instances() if isinstance(s, ctx["timer"])]
    ctx["put_buttons"](buttons=[s.func.__name__ for s in timers], onclick=[lambda t=t: ctx["show_timer_detail"](t) for t in timers])
    ctx["set_scope"]("timer_content")

    ctx["log"].sse("/logsse")
    with ctx["put_collapse"]("log", open=True):
        ctx["put_logbox"]("log", height=100)
    ctx["run_js"](ctx["sse_js"])

    with ctx["put_collapse"]("其他控件", open=True):
        ctx["put_input"]("write_to_log", type="text", value="", placeholder="手动写入日志")
        ctx["put_button"](">", onclick=ctx["write_to_log"])

    ctx["put_markdown"]("### 📱 Dtalk 消息存档")
    ctx["set_scope"]("dtalk_archive_display")
    ctx["show_dtalk_archive"]()


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
