"""页面帮助说明存储模块

将各页面的帮助说明存储在数据库中，支持动态更新。
"""

from typing import Dict, Optional
from deva import NB


HELP_TABLE = "naja_page_help"


def _get_help_db():
    return NB(HELP_TABLE)


def get_help_content(page_key: str) -> Optional[Dict]:
    """获取页面帮助说明"""
    db = _get_help_db()
    return db.get(page_key)


def set_help_content(page_key: str, content: Dict) -> bool:
    """设置页面帮助说明"""
    db = _get_help_db()
    db[page_key] = content
    return True


def init_default_helps():
    """初始化默认帮助说明"""
    db = _get_help_db()
    
    if "memory" not in db:
        db["memory"] = {
            "title": "🧠 记忆系统帮助",
            "sections": [
                {
                    "name": "页面介绍",
                    "content": "记忆系统（龙虾雷达）是一个基于 River 流式学习的长期记忆与事件分析系统。它能够持续学习市场事件，识别重要模式，并维护短期、中期、长期记忆。"
                },
                {
                    "name": "核心概念",
                    "content": """<ul style="margin:0;padding-left:20px;">
<li><strong>短期记忆</strong>：最近的事件缓存，用于实时处理</li>
<li><strong>中期记忆</strong>：高注意力事件归档，保留重要信息</li>
<li><strong>长期记忆</strong>：主题聚类结果，归纳事件模式</li>
<li><strong>注意力评分</strong>：基于多维度指标评估事件重要性</li>
</ul>"""
                },
                {
                    "name": "统计指标",
                    "content": """<ul style="margin:0;padding-left:20px;">
<li><strong>总事件数</strong>：系统累计处理的事件数量</li>
<li><strong>漂移检测</strong>：检测到的市场模式漂移次数</li>
<li><strong>主题数量</strong>：聚类产生的主题数量</li>
<li><strong>高注意力事件</strong>：评分高于阈值的重要事件</li>
</ul>"""
                }
            ]
        }
    
    if "llm_controller" not in db:
        db["llm_controller"] = {
            "title": "🤖 LLM 自动调节帮助",
            "sections": [
                {
                    "name": "功能介绍",
                    "content": "LLM 自动调节系统结合雷达事件和记忆摘要，利用大语言模型自动分析和调整策略参数。系统支持定时调节和事件驱动两种模式。"
                },
                {
                    "name": "调节模式",
                    "content": """<ul style="margin:0;padding-left:20px;">
<li><strong>⏰ 定时调节</strong>：按固定间隔（默认15分钟）运行，检查雷达事件并触发分析</li>
<li><strong>⚡ 事件驱动</strong>：当雷达事件数量超过阈值时自动触发</li>
</ul>"""
                },
                {
                    "name": "调节流程",
                    "content": """<ol style="margin:0;padding-left:20px;">
<li>读取雷达最近10分钟事件</li>
<li>如果事件数≥3，触发LLM分析</li>
<li>LLM读取策略配置和记忆摘要</li>
<li>生成优化建议并自动/手动应用</li>
</ol>"""
                },
                {
                    "name": "配置参数",
                    "content": """<ul style="margin:0;padding-left:20px;">
<li><strong>auto_adjust_enabled</strong>：是否启用自动调节</li>
<li><strong>auto_adjust_interval_seconds</strong>：调节间隔（默认900秒）</li>
<li><strong>auto_adjust_window_seconds</strong>：雷达事件窗口（默认600秒）</li>
<li><strong>auto_adjust_min_events</strong>：触发调节的最少事件数（默认3）</li>
</ul>"""
                }
            ]
        }
    
    if "bandit" not in db:
        db["bandit"] = {
            "title": "🎰 Bandit 自适应交易帮助",
            "sections": [
                {
                    "name": "功能介绍",
                    "content": "Bandit（多臂老虎机）系统是一个基于强化学习的自适应交易模块。它监听信号流，根据市场状态自动选择最优策略进行虚拟交易。"
                },
                {
                    "name": "核心组件",
                    "content": """<ul style="margin:0;padding-left:20px;">
<li><strong>SignalListener</strong>：监听信号流，检测交易信号</li>
<li><strong>VirtualPortfolio</strong>：虚拟持仓组合，记录交易历史</li>
<li><strong>MarketObserver</strong>：市场数据观察者，追踪持仓价格</li>
<li><strong>Optimizer</strong>：策略选择器，使用UCB算法优化</li>
</ul>"""
                },
                {
                    "name": "交易流程",
                    "content": """<ol style="margin:0;padding-left:20px;">
<li>监听信号流新信号</li>
<li>解析信号（股票代码、价格、策略）</li>
<li>创建虚拟持仓</li>
<li>追踪持仓价格变化</li>
<li>根据收益率自动调整策略权重</li>
</ol>"""
                },
                {
                    "name": "信号类型",
                    "content": """<ul style="margin:0;padding-left:20px;">
<li><strong>BUY/买入</strong>：买入信号，触发建仓</li>
<li><strong>SELL/卖出</strong>：卖出信号，触发平仓</li>
<li><strong>信号置信度</strong>：信号可信度阈值（默认0.5）</li>
</ul>"""
                },
                {
                    "name": "性能指标",
                    "content": """<ul style="margin:0;padding-left:20px;">
<li><strong>总收益率</strong>：虚拟组合的累计收益率</li>
<li><strong>持仓数</strong>：当前持有的股票数量</li>
<li><strong>胜率</strong>：盈利交易次数/总交易次数</li>
<li><strong>最大回撤</strong>：历史最大亏损幅度</li>
</ul>"""
                }
            ]
        }
    
    return True


init_default_helps()


def render_help_collapse(page_key: str):
    """渲染帮助说明（可折叠组件）"""
    from pywebio.output import put_collapse, put_html
    
    help_data = get_help_content(page_key)
    if not help_data:
        return None
    
    title = help_data.get("title", "📖 帮助说明")
    sections = help_data.get("sections", [])
    
    content_html = '<div style="font-size:13px;line-height:1.6;color:#374151;">'
    
    for section in sections:
        section_name = section.get("name", "")
        section_content = section.get("content", "")
        
        if section_name:
            content_html += f'<h4 style="margin:12px 0 8px;color:#1f2937;">{section_name}</h4>'
        content_html += f'<div>{section_content}</div>'
    
    content_html += '</div>'
    
    return put_collapse(title, put_html(content_html))


def render_help_inline(page_key: str, title: str = None):
    """渲染内联帮助说明"""
    from pywebio.output import put_html
    
    help_data = get_help_content(page_key)
    if not help_data:
        return None
    
    if title is None:
        title = help_data.get("title", "📖 帮助")
    
    sections = help_data.get("sections", [])
    
    content_html = '<div style="font-size:13px;line-height:1.6;color:#374151;padding:15px;background:#f9fafb;border-radius:8px;">'
    
    for section in sections:
        section_name = section.get("name", "")
        section_content = section.get("content", "")
        
        if section_name:
            content_html += f'<h4 style="margin:12px 0 8px;color:#1f2937;">{section_name}</h4>'
        content_html += f'<div>{section_content}</div>'
    
    content_html += '</div>'
    
    return put_html(content_html)
