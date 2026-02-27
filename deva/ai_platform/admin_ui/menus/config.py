"""Menu configuration for Deva Admin UI.

This module contains menu configuration data and JavaScript template generators.
"""

from typing import Dict, List, Any


# ============================================================================
# Menu Item Configuration
# ============================================================================

class MenuItem:
    """Represents a navigation menu item."""
    
    def __init__(self, name: str, path: str, icon: str = None):
        self.name = name
        self.path = path
        self.icon = icon or self._extract_icon(name)
    
    def _extract_icon(self, name: str) -> str:
        """Extract icon from name if present (emoji at start)."""
        if name and len(name) > 0 and ord(name[0]) > 127:
            return name[0]
        return ""
    
    def to_dict(self) -> Dict[str, str]:
        """Convert to dictionary for JavaScript template."""
        return {
            "name": self.name,
            "path": self.path,
            "icon": self.icon,
        }


# Main navigation menu items
MAIN_MENU_ITEMS: List[MenuItem] = [
    MenuItem("🏠 首页", "/"),
    MenuItem("⭐ 关注", "/followadmin"),
    MenuItem("🌐 浏览器", "/browseradmin"),
    MenuItem("💾 数据库", "/dbadmin"),
    MenuItem("🚌 Bus", "/busadmin"),
    MenuItem("📊 命名流", "/streamadmin"),
    MenuItem("📡 数据源", "/datasourceadmin"),
    MenuItem("📈 策略", "/strategyadmin"),
    MenuItem("👁 监控", "/monitor"),
    MenuItem("⏰ 任务", "/taskadmin"),
    MenuItem("⚙️ 配置", "/configadmin"),
    MenuItem("📄 文档", "/document"),
    MenuItem("🤖 AI", "/aicenter"),
]


# Sidebar configuration
SIDEBAR_CONFIG: Dict[str, Any] = {
    "title": "📋 访问日志",
    "width": "340px",
    "default_open": True,
    "storage_key": "sidebarState",
}


# ============================================================================
# JavaScript Template Generators
# ============================================================================

def generate_menu_js_template() -> str:
    """Generate JavaScript template for navigation menu."""
    
    menu_items_js = ",\n            ".join([
        f"""{{name: '{item.name}', path: '{item.path}', action: () => {{
                window.__pageNavigating = true;
                if (window.sseConnection) {{
                    try {{
                        window.sseConnection.close();
                    }} catch (e) {{}}
                    window.sseConnection = null;
                }}
                window.location.href = '{item.path}';
            }}}}"""
        for item in MAIN_MENU_ITEMS
    ])
    
    return f"""
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
            height: '60px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            boxShadow: '0 1px 3px rgba(0,0,0,0.05)'
        }});
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
        Object.assign(menu.style, {{
            display: 'flex',
            gap: '4px',
            alignItems: 'center'
        }});

        const hamburger = document.createElement('button');
        hamburger.className = 'hamburger';
        hamburger.innerHTML = '<span></span><span></span><span></span>';
        Object.assign(hamburger.style, {{
            display: 'none',
            flexDirection: 'column',
            justifyContent: 'space-around',
            width: '30px',
            height: '25px',
            background: 'transparent',
            border: 'none',
            cursor: 'pointer',
            padding: '0'
        }});
        hamburger.querySelectorAll('span').forEach(span => {{
            Object.assign(span.style, {{
                width: '100%',
                height: '3px',
                background: '#1e293b',
                borderRadius: '2px',
                transition: 'all 0.3s ease'
            }});
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
                transition: 'all 0.2s ease',
                display: 'flex',
                alignItems: 'center',
                whiteSpace: 'nowrap'
            }});
            link.onmouseenter = () => {{
                if (!isActive) {{
                    link.style.backgroundColor = '#f1f5f9';
                    link.style.color = '#1e293b';
                }}
            }};
            link.onmouseleave = () => {{
                link.style.backgroundColor = isActive ? '#eff6ff' : 'transparent';
                link.style.color = isActive ? '#3b82f6' : '#64748b';
            }};
            link.onclick = item.action;
            menu.appendChild(link);
        }});

        let isMenuOpen = false;
        hamburger.onclick = () => {{
            isMenuOpen = !isMenuOpen;
            if (isMenuOpen) {{
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
            }} else {{
                menu.style.display = 'flex';
                menu.style.flexDirection = 'row';
                menu.style.position = 'static';
                menu.style.padding = '0';
                menu.style.boxShadow = 'none';
                menu.style.borderTop = 'none';
                hamburger.style.transform = 'rotate(0deg)';
            }}
        }};

        const handleResize = () => {{
            if (window.innerWidth <= 768) {{
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
            }} else {{
                hamburger.style.display = 'none';
                menu.style.display = 'flex';
                menu.style.flexDirection = 'row';
                menu.style.position = 'static';
                menu.style.padding = '0';
                menu.style.boxShadow = 'none';
                menu.style.borderTop = 'none';
                menu.style.marginLeft = '32px';
            }}
        }};

        window.addEventListener('resize', handleResize);
        handleResize();

        nav.appendChild(brand);
        nav.appendChild(menu);
        nav.appendChild(hamburger);
        document.body.insertBefore(nav, document.body.firstChild);
        document.body.style.paddingTop = '60px';
    """


def generate_sidebar_js_template() -> str:
    """Generate JavaScript template for sidebar."""
    config = SIDEBAR_CONFIG
    return f"""
        const sidebar = document.createElement('div');
        sidebar.id = 'custom-sidebar';
        Object.assign(sidebar.style, {{
            position: 'fixed',
            right: '0',
            top: '0',
            width: '{config["width"]}',
            height: '100vh',
            backgroundColor: '#ffffff',
            boxShadow: '-4px 0 20px rgba(0,0,0,0.08)',
            transition: 'transform 0.35s cubic-bezier(0.4, 0, 0.2, 1)',
            zIndex: '1000',
            borderLeft: '1px solid #e2e8f0',
            display: 'flex',
            flexDirection: 'column'
        }});
        const sidebarHeader = document.createElement('div');
        Object.assign(sidebarHeader.style, {{
            padding: '16px 20px',
            borderBottom: '1px solid #e2e8f0',
            backgroundColor: '#f8fafc',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between'
        }});
        sidebarHeader.innerHTML = '<span style="font-weight: 600; color: #1e293b; font-size: 15px;">{config["title"]}</span>';
        const toggleBtn = document.createElement('div');
        Object.assign(toggleBtn.style, {{
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
        }});
        let isOpen = localStorage.getItem('{config["storage_key"]}') !== 'closed';
        sidebar.style.transform = isOpen ? 'translateX(0)' : 'translateX(100%)';
        toggleBtn.innerHTML = isOpen ? '<span style="font-size: 20px; color: #64748b;">→</span>' : '<span style="font-size: 20px; color: #64748b;">←</span>';
        toggleBtn.onmouseenter = () => {{ toggleBtn.style.backgroundColor = '#f1f5f9'; }};
        toggleBtn.onmouseleave = () => {{ toggleBtn.style.backgroundColor = '#ffffff'; }};
        toggleBtn.onclick = function() {{
            isOpen = !isOpen;
            sidebar.style.transform = isOpen ? 'translateX(0)' : 'translateX(100%)';
            toggleBtn.innerHTML = isOpen ? '<span style="font-size: 20px; color: #64748b;">→</span>' : '<span style="font-size: 20px; color: #64748b;">←</span>';
            localStorage.setItem('{config["storage_key"]}', isOpen ? 'open' : 'closed');
            const mainContent = document.querySelector('.container-fluid');
            if (mainContent) {{
                mainContent.style.marginRight = isOpen ? '{config["width"]}' : '0';
                mainContent.style.transition = 'margin-right 0.35s cubic-bezier(0.4, 0, 0.2, 1)';
            }}
        }};
        const mainContent = document.querySelector('.container-fluid');
        if (mainContent) {{ mainContent.style.marginRight = isOpen ? '{config["width"]}' : '0'; }}
        const sidebarContent = document.createElement('div');
        Object.assign(sidebarContent.style, {{ flex: '1', overflow: 'hidden' }});
        sidebar.appendChild(sidebarHeader);
        sidebar.appendChild(sidebarContent);
        sidebar.appendChild(toggleBtn);
        document.body.appendChild(sidebar);
        console.log('Sidebar created');
    """


# ============================================================================
# Public API
# ============================================================================

def get_menu_items() -> List[Dict[str, str]]:
    """Get all menu items as dictionaries."""
    return [item.to_dict() for item in MAIN_MENU_ITEMS]


def get_menu_paths() -> List[str]:
    """Get all menu paths."""
    return [item.path for item in MAIN_MENU_ITEMS]


def get_menu_item_by_path(path: str) -> MenuItem:
    """Get a menu item by its path."""
    for item in MAIN_MENU_ITEMS:
        if item.path == path:
            return item
    return None


def add_menu_item(name: str, path: str, icon: str = None, position: int = None) -> None:
    """Add a new menu item.
    
    Args:
        name: Display name of the menu item
        path: URL path for the menu item
        icon: Optional icon (emoji or CSS class)
        position: Optional position to insert (appends if None)
    """
    new_item = MenuItem(name, path, icon)
    if position is not None:
        MAIN_MENU_ITEMS.insert(position, new_item)
    else:
        MAIN_MENU_ITEMS.append(new_item)


def remove_menu_item(path: str) -> bool:
    """Remove a menu item by its path.
    
    Returns:
        True if item was removed, False if not found
    """
    for i, item in enumerate(MAIN_MENU_ITEMS):
        if item.path == path:
            MAIN_MENU_ITEMS.pop(i)
            return True
    return False
