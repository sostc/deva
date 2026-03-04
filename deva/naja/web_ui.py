"""Naja 管理面板 - 基于 PyWebIO 和 Tornado 的 Web 应用程序

统一可恢复单元管理平台，提供：
- 数据源管理
- 任务管理
- 策略管理
- 数据字典管理
- 数据表管理
"""

from pywebio.output import (
    put_text, put_markdown, put_table, put_buttons, put_html, 
    toast, popup, close_popup, put_row, put_code, put_collapse, set_scope
)
from pywebio.input import input_group, input, textarea, select, actions, NUMBER, checkbox
from pywebio.session import set_env, run_js, run_async

from deva import NW, Deva, NB
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
        {"name": "🗃️ 数据表", "path": "/tableadmin"},
        {"name": "⚙️ 配置", "path": "/configadmin"},
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
            <a href="/tableadmin" style="text-decoration: none;">
                <div style="padding: 20px; background: linear-gradient(135deg, #fa709a 0%, #fee140 100%); border-radius: 12px; color: white; text-align: center;">
                    <div style="font-size: 24px;">🗃️</div>
                    <div style="font-size: 16px; font-weight: 600; margin-top: 8px;">数据表管理</div>
                </div>
            </a>
            <a href="/configadmin" style="text-decoration: none;">
                <div style="padding: 20px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 12px; color: white; text-align: center;">
                    <div style="font-size: 24px;">⚙️</div>
                    <div style="font-size: 16px; font-weight: 600; margin-top: 8px;">配置管理</div>
                </div>
            </a>
        </div>
    </div>
    """)
    
    ctx["put_html"]("""
    <div style="margin-top: 40px; padding: 30px; background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); border-radius: 16px; box-shadow: 0 10px 40px rgba(0,0,0,0.2);">
        <h3 style="color: #fff; margin-bottom: 25px; text-align: center; font-size: 22px;">🔄 Naja 数据流向与功能关系</h3>
        
        <div style="display: flex; justify-content: center; align-items: center; flex-wrap: wrap; gap: 20px; margin-bottom: 30px;">
            <!-- 数据源 -->
            <div style="text-align: center;">
                <div style="width: 120px; height: 120px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 50%; display: flex; align-items: center; justify-content: center; box-shadow: 0 8px 25px rgba(102,126,234,0.4); cursor: pointer; transition: transform 0.3s;" onmouseover="this.style.transform='scale(1.1)'" onmouseout="this.style.transform='scale(1)'">
                    <div>
                        <div style="font-size: 36px;">📡</div>
                        <div style="color: #fff; font-size: 14px; font-weight: 600; margin-top: 5px;">数据源</div>
                    </div>
                </div>
                <div style="color: #aaa; font-size: 12px; margin-top: 10px; max-width: 140px;">定时获取外部数据<br>生成实时数据流</div>
            </div>
            
            <!-- 箭头1 -->
            <div style="color: #4facfe; font-size: 28px; animation: pulse 1.5s infinite;">→</div>
            
            <!-- 策略 -->
            <div style="text-align: center;">
                <div style="width: 120px; height: 120px; background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); border-radius: 50%; display: flex; align-items: center; justify-content: center; box-shadow: 0 8px 25px rgba(79,172,254,0.4); cursor: pointer; transition: transform 0.3s;" onmouseover="this.style.transform='scale(1.1)'" onmouseout="this.style.transform='scale(1)'">
                    <div>
                        <div style="font-size: 36px;">📊</div>
                        <div style="color: #fff; font-size: 14px; font-weight: 600; margin-top: 5px;">策略</div>
                    </div>
                </div>
                <div style="color: #aaa; font-size: 12px; margin-top: 10px; max-width: 140px;">处理数据流<br>生成信号/结果</div>
            </div>
            
            <!-- 箭头2 -->
            <div style="color: #4facfe; font-size: 28px; animation: pulse 1.5s infinite;">→</div>
            
            <!-- 数据表 -->
            <div style="text-align: center;">
                <div style="width: 120px; height: 120px; background: linear-gradient(135deg, #fa709a 0%, #fee140 100%); border-radius: 50%; display: flex; align-items: center; justify-content: center; box-shadow: 0 8px 25px rgba(250,112,154,0.4); cursor: pointer; transition: transform 0.3s;" onmouseover="this.style.transform='scale(1.1)'" onmouseout="this.style.transform='scale(1)'">
                    <div>
                        <div style="font-size: 36px;">🗃️</div>
                        <div style="color: #fff; font-size: 14px; font-weight: 600; margin-top: 5px;">数据表</div>
                    </div>
                </div>
                <div style="color: #aaa; font-size: 12px; margin-top: 10px; max-width: 140px;">存储所有数据<br>支持查询分析</div>
            </div>
        </div>
        
        <!-- 辅助模块 -->
        <div style="display: flex; justify-content: center; gap: 60px; flex-wrap: wrap;">
            <!-- 字典 -->
            <div style="text-align: center;">
                <div style="width: 90px; height: 90px; background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%); border-radius: 50%; display: flex; align-items: center; justify-content: center; box-shadow: 0 6px 20px rgba(67,233,123,0.4); cursor: pointer; transition: transform 0.3s;" onmouseover="this.style.transform='scale(1.1)'" onmouseout="this.style.transform='scale(1)'">
                    <div>
                        <div style="font-size: 28px;">📚</div>
                        <div style="color: #fff; font-size: 12px; font-weight: 600; margin-top: 3px;">字典</div>
                    </div>
                </div>
                <div style="color: #aaa; font-size: 11px; margin-top: 8px;">维护参考数据<br>提供查询服务</div>
            </div>
            
            <!-- 任务 -->
            <div style="text-align: center;">
                <div style="width: 90px; height: 90px; background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); border-radius: 50%; display: flex; align-items: center; justify-content: center; box-shadow: 0 6px 20px rgba(240,147,251,0.4); cursor: pointer; transition: transform 0.3s;" onmouseover="this.style.transform='scale(1.1)'" onmouseout="this.style.transform='scale(1)'">
                    <div>
                        <div style="font-size: 28px;">⏰</div>
                        <div style="color: #fff; font-size: 12px; font-weight: 600; margin-top: 3px;">任务</div>
                    </div>
                </div>
                <div style="color: #aaa; font-size: 11px; margin-top: 8px;">执行一次性任务<br>定时调度作业</div>
            </div>
            
            <!-- 配置 -->
            <div style="text-align: center;">
                <div style="width: 90px; height: 90px; background: linear-gradient(135deg, #6a11cb 0%, #2575fc 100%); border-radius: 50%; display: flex; align-items: center; justify-content: center; box-shadow: 0 6px 20px rgba(106,17,203,0.4); cursor: pointer; transition: transform 0.3s;" onmouseover="this.style.transform='scale(1.1)'" onmouseout="this.style.transform='scale(1)'">
                    <div>
                        <div style="font-size: 28px;">⚙️</div>
                        <div style="color: #fff; font-size: 12px; font-weight: 600; margin-top: 3px;">配置</div>
                    </div>
                </div>
                <div style="color: #aaa; font-size: 11px; margin-top: 8px;">全局参数配置<br>默认值管理</div>
            </div>
        </div>
        
        <!-- 说明文字 -->
        <div style="margin-top: 30px; padding: 20px; background: rgba(255,255,255,0.05); border-radius: 12px; border-left: 4px solid #4facfe;">
            <div style="color: #fff; font-size: 14px; line-height: 1.8;">
                <strong style="color: #4facfe;">💡 使用流程：</strong><br>
                <span style="color: #ccc;">
                1️⃣ 创建 <strong style="color: #667eea;">数据源</strong> 获取实时数据流（如股票行情、API数据）<br>
                2️⃣ 创建 <strong style="color: #4facfe;">策略</strong> 绑定数据源，定义处理逻辑，生成信号<br>
                3️⃣ 创建 <strong style="color: #43e97b;">字典</strong> 维护参考数据（如股票代码、配置项）<br>
                4️⃣ 创建 <strong style="color: #f093fb;">任务</strong> 执行一次性或定时任务（如每日汇总）<br>
                5️⃣ 所有数据自动存储到 <strong style="color: #fa709a;">数据表</strong>，支持查询分析
                </span>
            </div>
        </div>
        
        <style>
            @keyframes pulse {
                0%, 100% { opacity: 1; }
                50% { opacity: 0.5; }
            }
        </style>
    </div>
    """)
    
    # 策略详解部分
    ctx["put_html"]("""
    <div style="margin-top: 40px;">
        <h3 style="margin-bottom: 20px;">📈 资金流向分析策略详解</h3>
        <p style="color: #666; margin-bottom: 25px;">基于实时行情数据，分析市场资金流向，捕获异动机会</p>
    </div>
    """)
    
    # 策略卡片
    strategies_info = [
        {
            "name": "市场强度分析",
            "icon": "💪",
            "color": "#667eea",
            "description": "分析市场整体涨跌情况，计算市场强度指标",
            "formula": "强度 = (上涨家数 - 下跌家数) / 总股票数 × 100%",
            "logic": [
                "统计上涨、下跌、平盘股票数量",
                "计算涨停、跌停股票数量",
                "计算强势股（涨幅>3%）数量",
                "综合得出市场强度指标",
            ],
            "output": "市场状态：强势(>30%) / 震荡(-30%~30%) / 弱势(<-30%)",
        },
        {
            "name": "快速异动捕获",
            "icon": "⚡",
            "color": "#f5576c",
            "description": "检测几十秒级别的价格快速变化和放量异动",
            "formula": "得分 = 价格速度分(30) + 量比分(30) + 加速度分(20) + 涨幅分(20)",
            "logic": [
                "计算60秒内价格变化速度",
                "计算当前成交量与均量的比值",
                "计算涨跌幅加速度",
                "综合得分≥50触发信号",
            ],
            "output": "异动股票列表，按得分排序",
        },
        {
            "name": "涨跌停监控",
            "icon": "🚀",
            "color": "#4facfe",
            "description": "实时监控涨停、跌停和大涨大跌股票",
            "formula": "涨停: 涨幅≥9.9% | 跌停: 涨幅≤-9.9%",
            "logic": [
                "筛选涨幅≥9.9%的涨停股",
                "筛选涨幅≤-9.9%的跌停股",
                "筛选涨幅5%-9.9%的大涨股",
                "筛选跌幅-5%到-9.9%的大跌股",
            ],
            "output": "涨跌停股票列表及成交额",
        },
        {
            "name": "成交额排行",
            "icon": "💰",
            "color": "#43e97b",
            "description": "分析成交额排名，发现资金关注的热门股票",
            "formula": "集中度 = 前10成交额 / 总成交额 × 100%",
            "logic": [
                "按成交额降序排列",
                "计算总成交额",
                "计算前10成交额占比",
                "识别资金集中度",
            ],
            "output": "成交额前20股票及集中度",
        },
        {
            "name": "滑动窗口趋势分析",
            "icon": "📈",
            "color": "#fa709a",
            "description": "分析5分钟内的价格趋势变化，发现趋势性机会",
            "formula": "趋势斜率 = 线性回归(时间序列, 涨幅序列)",
            "logic": [
                "维护60个数据点(5分钟)历史",
                "对涨跌幅序列做线性回归",
                "斜率>0.01且变化>1%为上升",
                "斜率<-0.01且变化<-1%为下降",
            ],
            "output": "趋势股票列表及变化幅度",
        },
    ]
    
    for i, strategy in enumerate(strategies_info):
        ctx["put_html"](f"""
        <div style="background: #fff; border-radius: 16px; box-shadow: 0 4px 20px rgba(0,0,0,0.08); margin-bottom: 20px; overflow: hidden; border: 1px solid #eee;">
            <div style="background: linear-gradient(135deg, {strategy['color']} 0%, {strategy['color']}dd 100%); padding: 20px; color: white;">
                <div style="display: flex; align-items: center; gap: 15px;">
                    <div style="font-size: 36px;">{strategy['icon']}</div>
                    <div>
                        <div style="font-size: 20px; font-weight: 600;">{strategy['name']}</div>
                        <div style="font-size: 14px; opacity: 0.9; margin-top: 5px;">{strategy['description']}</div>
                    </div>
                </div>
            </div>
            <div style="padding: 25px;">
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 25px;">
                    <div>
                        <div style="font-weight: 600; color: #333; margin-bottom: 12px; display: flex; align-items: center; gap: 8px;">
                            <span style="background: {strategy['color']}; color: white; padding: 2px 8px; border-radius: 4px; font-size: 12px;">公式</span>
                            计算逻辑
                        </div>
                        <div style="background: #f8f9fa; padding: 15px; border-radius: 8px; font-family: monospace; font-size: 13px; color: #555; border-left: 3px solid {strategy['color']};">
                            {strategy['formula']}
                        </div>
                    </div>
                    <div>
                        <div style="font-weight: 600; color: #333; margin-bottom: 12px; display: flex; align-items: center; gap: 8px;">
                            <span style="background: {strategy['color']}; color: white; padding: 2px 8px; border-radius: 4px; font-size: 12px;">步骤</span>
                            处理流程
                        </div>
                        <div style="background: #f8f9fa; padding: 15px; border-radius: 8px;">
                            {"".join([f'<div style="padding: 5px 0; color: #555; font-size: 13px; display: flex; align-items: center; gap: 8px;"><span style="background: {strategy["color"]}; color: white; width: 20px; height: 20px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 11px;">{j+1}</span>{step}</div>' for j, step in enumerate(strategy['logic'])])}
                        </div>
                    </div>
                </div>
                <div style="margin-top: 20px; padding: 15px; background: linear-gradient(135deg, {strategy['color']}11 0%, {strategy['color']}22 100%); border-radius: 8px; border: 1px dashed {strategy['color']}44;">
                    <div style="display: flex; align-items: center; gap: 8px; color: #333; font-size: 14px;">
                        <span style="font-size: 18px;">📤</span>
                        <strong>输出：</strong>
                        <span style="color: #666;">{strategy['output']}</span>
                    </div>
                </div>
            </div>
        </div>
        """)
    
    # 策略流程图
    ctx["put_html"]("""
    <div style="margin-top: 40px; padding: 30px; background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); border-radius: 16px; box-shadow: 0 10px 40px rgba(0,0,0,0.2);">
        <h3 style="color: #fff; margin-bottom: 25px; text-align: center; font-size: 22px;">🔄 策略数据处理流程</h3>
        
        <div style="display: flex; justify-content: center; align-items: center; flex-wrap: wrap; gap: 15px; margin-bottom: 30px;">
            <!-- 数据源 -->
            <div style="text-align: center; padding: 15px;">
                <div style="width: 80px; height: 80px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 12px; display: flex; align-items: center; justify-content: center; box-shadow: 0 4px 15px rgba(102,126,234,0.4);">
                    <div>
                        <div style="font-size: 28px;">📡</div>
                        <div style="color: #fff; font-size: 11px; font-weight: 600; margin-top: 3px;">数据源</div>
                    </div>
                </div>
                <div style="color: #aaa; font-size: 11px; margin-top: 8px;">realtime_quant_5s</div>
            </div>
            
            <div style="color: #4facfe; font-size: 24px;">→</div>
            
            <!-- 数据格式 -->
            <div style="text-align: center; padding: 15px;">
                <div style="width: 80px; height: 80px; background: linear-gradient(135deg, #6a11cb 0%, #2575fc 100%); border-radius: 12px; display: flex; align-items: center; justify-content: center; box-shadow: 0 4px 15px rgba(106,17,203,0.4);">
                    <div>
                        <div style="font-size: 28px;">📊</div>
                        <div style="color: #fff; font-size: 11px; font-weight: 600; margin-top: 3px;">DataFrame</div>
                    </div>
                </div>
                <div style="color: #aaa; font-size: 11px; margin-top: 8px;">5000+股票行情</div>
            </div>
            
            <div style="color: #4facfe; font-size: 24px;">→</div>
            
            <!-- 策略处理 -->
            <div style="text-align: center; padding: 15px;">
                <div style="width: 80px; height: 80px; background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); border-radius: 12px; display: flex; align-items: center; justify-content: center; box-shadow: 0 4px 15px rgba(79,172,254,0.4);">
                    <div>
                        <div style="font-size: 28px;">⚙️</div>
                        <div style="color: #fff; font-size: 11px; font-weight: 600; margin-top: 3px;">策略</div>
                    </div>
                </div>
                <div style="color: #aaa; font-size: 11px; margin-top: 8px;">5个分析策略</div>
            </div>
            
            <div style="color: #4facfe; font-size: 24px;">→</div>
            
            <!-- 信号输出 -->
            <div style="text-align: center; padding: 15px;">
                <div style="width: 80px; height: 80px; background: linear-gradient(135deg, #f5576c 0%, #f093fb 100%); border-radius: 12px; display: flex; align-items: center; justify-content: center; box-shadow: 0 4px 15px rgba(245,87,108,0.4);">
                    <div>
                        <div style="font-size: 28px;">🚨</div>
                        <div style="color: #fff; font-size: 11px; font-weight: 600; margin-top: 3px;">信号</div>
                    </div>
                </div>
                <div style="color: #aaa; font-size: 11px; margin-top: 8px;">异动/趋势信号</div>
            </div>
            
            <div style="color: #4facfe; font-size: 24px;">→</div>
            
            <!-- 数据存储 -->
            <div style="text-align: center; padding: 15px;">
                <div style="width: 80px; height: 80px; background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%); border-radius: 12px; display: flex; align-items: center; justify-content: center; box-shadow: 0 4px 15px rgba(67,233,123,0.4);">
                    <div>
                        <div style="font-size: 28px;">💾</div>
                        <div style="color: #fff; font-size: 11px; font-weight: 600; margin-top: 3px;">存储</div>
                    </div>
                </div>
                <div style="color: #aaa; font-size: 11px; margin-top: 8px;">结果持久化</div>
            </div>
        </div>
        
        <!-- 数据字段说明 -->
        <div style="background: rgba(255,255,255,0.05); border-radius: 12px; padding: 20px; margin-top: 20px;">
            <div style="color: #fff; font-size: 16px; font-weight: 600; margin-bottom: 15px;">📋 输入数据字段</div>
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px;">
                <div style="background: rgba(255,255,255,0.1); padding: 10px; border-radius: 8px;">
                    <div style="color: #4facfe; font-size: 13px; font-weight: 600;">name</div>
                    <div style="color: #aaa; font-size: 11px;">股票名称</div>
                </div>
                <div style="background: rgba(255,255,255,0.1); padding: 10px; border-radius: 8px;">
                    <div style="color: #4facfe; font-size: 13px; font-weight: 600;">now</div>
                    <div style="color: #aaa; font-size: 11px;">当前价格</div>
                </div>
                <div style="background: rgba(255,255,255,0.1); padding: 10px; border-radius: 8px;">
                    <div style="color: #4facfe; font-size: 13px; font-weight: 600;">close</div>
                    <div style="color: #aaa; font-size: 11px;">昨收价</div>
                </div>
                <div style="background: rgba(255,255,255,0.1); padding: 10px; border-radius: 8px;">
                    <div style="color: #4facfe; font-size: 13px; font-weight: 600;">volume</div>
                    <div style="color: #aaa; font-size: 11px;">成交量</div>
                </div>
                <div style="background: rgba(255,255,255,0.1); padding: 10px; border-radius: 8px;">
                    <div style="color: #4facfe; font-size: 13px; font-weight: 600;">turnover</div>
                    <div style="color: #aaa; font-size: 11px;">成交额</div>
                </div>
                <div style="background: rgba(255,255,255,0.1); padding: 10px; border-radius: 8px;">
                    <div style="color: #4facfe; font-size: 13px; font-weight: 600;">high/low</div>
                    <div style="color: #aaa; font-size: 11px;">最高/最低价</div>
                </div>
                <div style="background: rgba(255,255,255,0.1); padding: 10px; border-radius: 8px;">
                    <div style="color: #4facfe; font-size: 13px; font-weight: 600;">bid1-5</div>
                    <div style="color: #aaa; font-size: 11px;">买盘五档</div>
                </div>
                <div style="background: rgba(255,255,255,0.1); padding: 10px; border-radius: 8px;">
                    <div style="color: #4facfe; font-size: 13px; font-weight: 600;">ask1-5</div>
                    <div style="color: #aaa; font-size: 11px;">卖盘五档</div>
                </div>
            </div>
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


def create_handlers(cdn: str = None):
    """创建路由处理器"""
    cdn_url = cdn or 'https://fastly.jsdelivr.net/gh/wang0618/PyWebIO-assets@v1.8.3/'
    
    return [
        (r'/', webio_handler(main, cdn=cdn_url)),
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
