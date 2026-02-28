"""Menu rendering functions for Deva Admin UI."""

from .config import MAIN_MENU_ITEMS, SIDEBAR_CONFIG, generate_menu_js_template, generate_sidebar_js_template


def create_nav_menu(ctx):
    """Create navigation menu.
    
    Args:
        ctx: Context dictionary with run_js function
    """
    js_template = generate_menu_js_template()
    ctx["run_js"](js_template)


def create_sidebar(ctx):
    """Create sidebar.

    Args:
        ctx: Context dictionary with run_js and use_scope functions
    """
    # 在页面加载完成后再创建 sidebar，确保 scope 元素已存在
    ctx["run_js"](f"""
    (function() {{
        // 等待 DOM 加载完成
        if (document.readyState === 'loading') {{
            document.addEventListener('DOMContentLoaded', initSidebar);
        }} else {{
            initSidebar();
        }}
        
        function initSidebar() {{
            // 等待一小段时间确保 PyWebIO scope 已创建
            setTimeout(function() {{
                {generate_sidebar_js_template()}
                
                // 查找并附加 sidebar scope
                const sidebarScope = document.getElementById('pywebio-scope-sidebar');
                if (sidebarScope) {{
                    const sidebarContent = document.querySelector('#custom-sidebar > div:nth-child(2)');
                    if (sidebarContent) {{
                        sidebarScope.style.height = '100%';
                        sidebarScope.style.overflow = 'hidden';
                        sidebarContent.appendChild(sidebarScope);
                        console.log('Sidebar scope attached');
                    }}
                }}
            }}, 100);
        }}
    }})();
    """)

    # 在 sidebar scope 中嵌入访问日志的 webview iframe
    with ctx["use_scope"]("sidebar"):
        access_log_stream = ctx["NS"]('访问日志')
        access_log_hash = hash(access_log_stream)

        ctx["put_html"](f"""
            <div style="height:100%;display:flex;flex-direction:column;overflow:hidden;">
                <div style="padding:12px 16px;border-bottom:1px solid #e2e8f0;background:#f8fafc;flex-shrink:0;">
                    <span style="font-weight:600;color:#1e293b;font-size:14px;">📋 访问日志</span>
                </div>
                <iframe src="/{access_log_hash}" style="flex:1;width:100%;border:none;background:#fff;" onload="console.log('访问日志 iframe 已加载:', this.src)"></iframe>
            </div>
        """)


def init_floating_menu_manager(ctx):
    """Initialize floating menu manager for summary popups.
    
    Args:
        ctx: Context dictionary with run_js function
    """
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
