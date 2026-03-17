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
                    "name": "功能介绍",
                    "content": "记忆系统是 Naja 的叙事分析引擎，专注于检测市场<strong>叙事层面</strong>的变化，包括热点主题、市场注意力焦点、概念漂移等非技术信号。"
                },
                {
                    "name": "与雷达系统的区别",
                    "content": """<table style="width:100%;border-collapse:collapse;font-size:12px;">
<tr style="background:#fef2f2;">
<td style="padding:8px;border:1px solid #fecaca;"><strong>记忆 (叙事)</strong></td>
<td style="padding:8px;border:1px solid #fecaca;"><strong>雷达 (技术)</strong></td>
</tr>
<tr>
<td style="padding:8px;border:1px solid #e5e7eb;">热点主题、叙事变化</td>
<td style="padding:8px;border:1px solid #e5e7eb;">量价突破、波动率变化</td>
</tr>
<tr style="background:#f9fafb;">
<td style="padding:8px;border:1px solid #e5e7eb;">市场注意力焦点</td>
<td style="padding:8px;border:1px solid #e5e7eb;">技术模式切换</td>
</tr>
<tr>
<td style="padding:8px;border:1px solid #e5e7eb;">市场共识/情绪</td>
<td style="padding:8px;border:1px solid #e5e7eb;">可交易的信号</td>
</tr>
</table>"""
                },
                {
                    "name": "三层记忆体系",
                    "content": """<table style="width:100%;border-collapse:collapse;font-size:12px;">
<tr style="background:#e0f2fe;">
<td style="padding:6px 10px;border:1px solid #bae6fd;color:#0369a1;"><strong>短期记忆</strong></td>
<td style="padding:6px 10px;border:1px solid #bae6fd;">最近 5 分钟内的事件，快速衰减</td>
</tr>
<tr style="background:#dcfce7;">
<td style="padding:6px 10px;border:1px solid #bbf7d0;color:#15803d;"><strong>中期记忆</strong></td>
<td style="padding:6px 10px;border:1px solid #bbf7d0;">最近 1 小时的事件，中速衰减</td>
</tr>
<tr style="background:#ede9fe;">
<td style="padding:6px 10px;border:1px solid #ddd6fe;color:#7c3aed;"><strong>长期记忆</strong></td>
<td style="padding:6px 10px;border:1px solid #ddd6fe;">历史重要事件，长期保留</td>
</tr>
</table>"""
                },
                {
                    "name": "核心指标说明",
                    "content": """<table style="width:100%;border-collapse:collapse;font-size:12px;">
<tr style="background:#f3f4f6;">
<td style="padding:6px 10px;border:1px solid #e5e7eb;"><strong>累计事件</strong></td>
<td style="padding:6px 10px;border:1px solid #e5e7eb;">记忆系统成立以来记录的所有事件总数</td>
</tr>
<tr>
<td style="padding:6px 10px;border:1px solid #e5e7eb;"><strong>高注意力</strong></td>
<td style="padding:6px 10px;border:1px solid #e5e7eb;">注意力分数高于阈值的重要事件数量</td>
</tr>
<tr style="background:#f3f4f6;">
<td style="padding:6px 10px;border:1px solid #e5e7eb;"><strong>主题数量</strong></td>
<td style="padding:6px 10px;border:1px solid #e5e7eb;">识别出的独立市场主题/叙事数量</td>
</tr>
<tr>
<td style="padding:6px 10px;border:1px solid #e5e7eb;"><strong>漂移次数</strong></td>
<td style="padding:6px 10px;border:1px solid #e5e7eb;">检测到的市场叙事漂移事件次数</td>
</tr>
</table>"""
                },
                {
                    "name": "工作原理",
                    "content": """<ul style="margin:0;padding-left:20px;">
<li>策略执行结果 → 记忆沉淀 → 形成主题</li>
<li>主题通过注意力机制评分 → 高注意力主题触发雷达事件</li>
<li>AI 大脑可查询记忆 → 获取历史上下文</li>
<li>漂移检测 → 发现叙事模式变化</li>
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
    
    if "radar" not in db:
        db["radar"] = {
            "title": "📡 雷达系统帮助",
            "sections": [
                {
                    "name": "功能介绍",
                    "content": "雷达系统专注检测市场<strong>技术层面</strong>的变化，包括量价突破、波动率变化、模式切换等可交易的技术信号。"
                },
                {
                    "name": "与记忆系统的区别",
                    "content": """<table style="width:100%;border-collapse:collapse;font-size:12px;">
<tr style="background:#fef2f2;">
<td style="padding:8px;border:1px solid #fecaca;"><strong>雷达 (技术)</strong></td>
<td style="padding:8px;border:1px solid #fecaca;"><strong>记忆 (叙事)</strong></td>
</tr>
<tr>
<td style="padding:8px;border:1px solid #e5e7eb;">量价突破、波动率变化</td>
<td style="padding:8px;border:1px solid #e5e7eb;">热点主题、叙事变化</td>
</tr>
<tr style="background:#f9fafb;">
<td style="padding:8px;border:1px solid #e5e7eb;">技术模式切换</td>
<td style="padding:8px;border:1px solid #e5e7eb;">市场注意力焦点</td>
</tr>
<tr>
<td style="padding:8px;border:1px solid #e5e7eb;">可交易的信号</td>
<td style="padding:8px;border:1px solid #e5e7eb;">市场共识/情绪</td>
</tr>
</table>"""
                },
                {
                    "name": "字段说明",
                    "content": """<table style="width:100%;border-collapse:collapse;font-size:12px;">
<tr style="background:#f3f4f6;">
<td style="padding:6px 10px;border:1px solid #e5e7eb;"><strong>时间</strong></td>
<td style="padding:6px 10px;border:1px solid #e5e7eb;">事件发生时间</td>
</tr>
<tr>
<td style="padding:6px 10px;border:1px solid #e5e7eb;"><strong>事件</strong></td>
<td style="padding:6px 10px;border:1px solid #e5e7eb;">事件类型：pattern(模式)、drift(漂移)、anomaly(异常)</td>
</tr>
<tr style="background:#f3f4f6;">
<td style="padding:6px 10px;border:1px solid #e5e7eb;"><strong>分数</strong></td>
<td style="padding:6px 10px;border:1px solid #e5e7eb;">事件严重程度/置信度 (0-10)</td>
</tr>
<tr>
<td style="padding:6px 10px;border:1px solid #e5e7eb;"><strong>策略</strong></td>
<td style="padding:6px 10px;border:1px solid #e5e7eb;">触发该事件的策略名称</td>
</tr>
<tr style="background:#f3f4f6;">
<td style="padding:6px 10px;border:1px solid #e5e7eb;"><strong>信号类型</strong></td>
<td style="padding:6px 10px;border:1px solid #e5e7eb;">检测到的具体信号类型</td>
</tr>
<tr>
<td style="padding:6px 10px;border:1px solid #e5e7eb;"><strong>说明</strong></td>
<td style="padding:6px 10px;border:1px solid #e5e7eb;">事件的详细描述</td>
</tr>
</table>"""
                },
                {
                    "name": "技术信号类型",
                    "content": """<table style="width:100%;border-collapse:collapse;font-size:12px;">
<tr style="background:#fef2f2;">
<td style="padding:6px 10px;border:1px solid #fecaca;color:#dc2626;"><strong>fast_anomaly</strong></td>
<td style="padding:6px 10px;border:1px solid #fecaca;">快速异常 - 短时间内数据分布剧烈变化</td>
</tr>
<tr style="background:#fffbeb;">
<td style="padding:6px 10px;border:1px solid #fde68a;color:#d97706;"><strong>volume_breakout</strong></td>
<td style="padding:6px 10px;border:1px solid #fde68a;">成交量突破 - 成交量模式突变，可能预示突破</td>
</tr>
<tr style="background:#eff6ff;">
<td style="padding:6px 10px;border:1px solid #bfdbfe;color:#2563eb;"><strong>block_rotation</strong></td>
<td style="padding:6px 10px;border:1px solid #bfdbfe;">板块轮动 - 资金在板块间流动</td>
</tr>
<tr style="background:#f0fdf4;">
<td style="padding:6px 10px;border:1px solid #bbf7d0;color:#16a34a;"><strong>trend_analysis</strong></td>
<td style="padding:6px 10px;border:1px solid #bbf7d0;">趋势分析 - 市场趋势模式漂移</td>
</tr>
<tr style="background:#f3e8ff;">
<td style="padding:6px 10px;border:1px solid #e9d5ff;color:#9333ea;"><strong>tick_drift_adwin</strong></td>
<td style="padding:6px 10px;border:1px solid #e9d5ff;">ADWIN漂移 - 基于ADWIN算法的价格漂移</td>
</tr>
</table>"""
                }
            ]
        }
    
    if "strategy" not in db:
        db["strategy"] = {
            "title": "⚙️ 策略系统帮助",
            "sections": [
                {
                    "name": "功能介绍",
                    "content": "策略系统是 Naja 的核心执行引擎，负责处理数据流并生成决策信号。每个策略可以绑定一个或多个数据源，接收数据后执行自定义逻辑。"
                },
                {
                    "name": "与任务系统的区别",
                    "content": """<table style="width:100%;border-collapse:collapse;font-size:12px;">
<tr style="background:#fef2f2;">
<td style="padding:8px;border:1px solid #fecaca;"><strong>策略</strong></td>
<td style="padding:8px;border:1px solid #fecaca;"><strong>任务</strong></td>
</tr>
<tr>
<td style="padding:8px;border:1px solid #e5e7eb;">绑定数据源，实时处理数据流</td>
<td style="padding:8px;border:1px solid #e5e7eb;">定时/手动触发，执行一次性操作</td>
</tr>
<tr style="background:#f9fafb;">
<td style="padding:8px;border:1px solid #e5e7eb;">持续运行，响应数据变化</td>
<td style="padding:8px;border:1px solid #e5e7eb;">按计划执行，执行完即结束</td>
</tr>
<tr>
<td style="padding:8px;border:1px solid #e5e7eb;">输出结构化信号（雷达/记忆/交易）</td>
<td style="padding:8px;border:1px solid #e5e7eb;">执行任意操作（刷新/计算/推送）</td>
</tr>
<tr style="background:#f9fafb;">
<td style="padding:8px;border:1px solid #e5e7eb;">支持状态持久化</td>
<td style="padding:8px;border:1px solid #e5e7eb;">通常无状态</td>
</tr>
</table>"""
                },
                {
                    "name": "字段说明",
                    "content": """<table style="width:100%;border-collapse:collapse;font-size:12px;">
<tr style="background:#f3f4f6;">
<td style="padding:6px 10px;border:1px solid #e5e7eb;"><strong>名称</strong></td>
<td style="padding:6px 10px;border:1px solid #e5e7eb;">策略的唯一标识名称</td>
</tr>
<tr>
<td style="padding:6px 10px;border:1px solid #e5e7eb;"><strong>类型</strong></td>
<td style="padding:6px 10px;border:1px solid #e5e7eb;">策略类型：declarative、river、plugin、legacy</td>
</tr>
<tr style="background:#f3f4f6;">
<td style="padding:6px 10px;border:1px solid #e5e7eb;"><strong>状态</strong></td>
<td style="padding:6px 10px;border:1px solid #e5e7eb;">运行中/已停止</td>
</tr>
<tr>
<td style="padding:6px 10px;border:1px solid #e5e7eb;"><strong>数据源</strong></td>
<td style="padding:6px 10px;border:1px solid #e5e7eb;">策略绑定的数据源（支持多数据源）</td>
</tr>
<tr style="background:#f3f4f6;">
<td style="padding:6px 10px;border:1px solid #e5e7eb;"><strong>简介</strong></td>
<td style="padding:6px 10px;border:1px solid #e5e7eb;">策略的功能描述</td>
</tr>
<tr>
<td style="padding:6px 10px;border:1px solid #e5e7eb;"><strong>最近数据</strong></td>
<td style="padding:6px 10px;border:1px solid #e5e7eb;">最新一次执行的时间</td>
</tr>
</table>"""
                },
                {
                    "name": "策略类型说明",
                    "content": """<table style="width:100%;border-collapse:collapse;font-size:12px;">
<tr style="background:#e0f2fe;">
<td style="padding:6px 10px;border:1px solid #bae6fd;color:#0369a1;"><strong>declarative</strong></td>
<td style="padding:6px 10px;border:1px solid #bae6fd;">声明式策略 - 通过配置定义数据处理流水线</td>
</tr>
<tr style="background:#dcfce7;">
<td style="padding:6px 10px;border:1px solid #bbf7d0;color:#15803d;"><strong>river</strong></td>
<td style="padding:6px 10px;border:1px solid #bbf7d0;">流式策略 - 基于 River 库的在线学习策略</td>
</tr>
<tr style="background:#ede9fe;">
<td style="padding:6px 10px;border:1px solid #ddd6fe;color:#7c3aed;"><strong>plugin</strong></td>
<td style="padding:6px 10px;border:1px solid #ddd6fe;">插件策略 - 外部插件形式的策略</td>
</tr>
<tr style="background:#f1f5f9;">
<td style="padding:6px 10px;border:1px solid #e2e8f0;color:#475569;"><strong>legacy</strong></td>
<td style="padding:6px 10px;border:1px solid #e2e8f0;">传统策略 - 早期实现的 Python 代码策略</td>
</tr>
</table>"""
                },
                {
                    "name": "输出规范",
                    "content": """<p style="font-size:12px;color:#4b5563;margin:8px 0;">策略通过设置 <code>output_target</code> 指定输出目标，不同目标有不同的字段要求：</p>
<table style="width:100%;border-collapse:collapse;font-size:12px;">
<tr style="background:#fef2f2;">
<td style="padding:6px 10px;border:1px solid #fecaca;color:#dc2626;"><strong>radar</strong></td>
<td style="padding:6px 10px;border:1px solid #fecaca;"><span style="color:#dc2626;">必需：</span>signal_type, score</td>
<td style="padding:6px 10px;border:1px solid #fecaca;">可选：value, message</td>
</tr>
<tr style="background:#fffbeb;">
<td style="padding:6px 10px;border:1px solid #fde68a;color:#d97706;"><strong>memory</strong></td>
<td style="padding:6px 10px;border:1px solid #fde68a;"><span style="color:#d97706;">必需：</span>content</td>
<td style="padding:6px 10px;border:1px solid #fde68a;">可选：topic, sentiment, tags</td>
</tr>
<tr style="background:#f0fdf4;">
<td style="padding:6px 10px;border:1px solid #bbf7d0;color:#16a34a;"><strong>bandit</strong></td>
<td style="padding:6px 10px;border:1px solid #bbf7d0;"><span style="color:#16a34a;">必需：</span>signal_type, stock_code, price</td>
<td style="padding:6px 10px;border:1px solid #bbf7d0;">可选：confidence, amount, reason</td>
</tr>
</table>"""
                },
                {
                    "name": "信号流展示字段",
                    "content": """<p style="font-size:12px;color:#4b5563;margin:8px 0;">当输出到信号流展示时，支持以下字段：</p>
<table style="width:100%;border-collapse:collapse;font-size:12px;">
<tr style="background:#f3f4f6;">
<td style="padding:6px 10px;border:1px solid #e5e7eb;"><strong>html</strong></td>
<td style="padding:6px 10px;border:1px solid #e5e7eb;">自定义HTML内容（优先使用）</td>
</tr>
<tr>
<td style="padding:6px 10px;border:1px solid #e5e7eb;"><strong>signals</strong></td>
<td style="padding:6px 10px;border:1px solid #e5e7eb;">信号数组，每项包含 name(名称), code(代码), p_change(涨跌幅), score(评分)</td>
</tr>
<tr style="background:#f3f4f6;">
<td style="padding:6px 10px;border:1px solid #e5e7eb;"><strong>signal_type</strong></td>
<td style="padding:6px 10px;border:1px solid #e5e7eb;">信号类型，决定图标和颜色（fast_anomaly, volume_breakout, trend_analysis 等）</td>
</tr>
<tr>
<td style="padding:6px 10px;border:1px solid #e5e7eb;"><strong>signal_count</strong></td>
<td style="padding:6px 10px;border:1px solid #e5e7eb;">信号数量</td>
</tr>
<tr style="background:#f3f4f6;">
<td style="padding:6px 10px;border:1px solid #e5e7eb;"><strong>output_preview</strong></td>
<td style="padding:6px 10px;border:1px solid #e5e7eb;">简短预览文本（截断时备用）</td>
</tr>
</table>
<p style="font-size:11px;color:#6b7280;margin-top:8px;">💡 建议：优先返回 <code>html</code> 字段自定义展示，其次返回 <code>signals</code> 数组自动生成表格</p>"""
                }
            ]
        }
    
    if "task" not in db:
        db["task"] = {
            "title": "📋 任务系统帮助",
            "sections": [
                {
                    "name": "功能介绍",
                    "content": "任务系统用于执行一次性或周期性的后台操作，与策略的数据流处理不同，任务通常是定时/手动触发的一次性操作。"
                },
                {
                    "name": "与策略系统的区别",
                    "content": """<table style="width:100%;border-collapse:collapse;font-size:12px;">
<tr style="background:#fef2f2;">
<td style="padding:8px;border:1px solid #fecaca;"><strong>策略</strong></td>
<td style="padding:8px;border:1px solid #fecaca;"><strong>任务</strong></td>
</tr>
<tr>
<td style="padding:8px;border:1px solid #e5e7eb;">绑定数据源，实时处理数据流</td>
<td style="padding:8px;border:1px solid #e5e7eb;">定时/手动触发，执行一次性操作</td>
</tr>
<tr style="background:#f9fafb;">
<td style="padding:8px;border:1px solid #e5e7eb;">持续运行，响应数据变化</td>
<td style="padding:8px;border:1px solid #e5e7eb;">按计划执行，执行完即结束</td>
</tr>
<tr>
<td style="padding:8px;border:1px solid #e5e7eb;">输出结构化信号（雷达/记忆/交易）</td>
<td style="padding:8px;border:1px solid #e5e7eb;">执行任意操作（刷新/计算/推送）</td>
</tr>
<tr style="background:#f9fafb;">
<td style="padding:8px;border:1px solid #e5e7eb;">支持状态持久化</td>
<td style="padding:8px;border:1px solid #e5e7eb;">通常无状态</td>
</tr>
</table>"""
                },
                {
                    "name": "触发方式",
                    "content": """<table style="width:100%;border-collapse:collapse;font-size:12px;">
<tr style="background:#e0f2fe;">
<td style="padding:6px 10px;border:1px solid #bae6fd;color:#0369a1;"><strong>interval</strong></td>
<td style="padding:6px 10px;border:1px solid #bae6fd;">定时执行，按固定间隔重复运行</td>
</tr>
<tr style="background:#dcfce7;">
<td style="padding:6px 10px;border:1px solid #bbf7d0;color:#15803d;"><strong>cron</strong></td>
<td style="padding:6px 10px;border:1px solid #bbf7d0;">Cron 表达式，精确控制执行时间</td>
</tr>
<tr style="background:#ede9fe;">
<td style="padding:6px 10px;border:1px solid #ddd6fe;color:#7c3aed;"><strong>date</strong></td>
<td style="padding:6px 10px;border:1px solid #ddd6fe;">指定日期时间，只执行一次</td>
</tr>
<tr style="background:#f1f5f9;">
<td style="padding:6px 10px;border:1px solid #e2e8f0;color:#475569;"><strong>manual</strong></td>
<td style="padding:6px 10px;border:1px solid #e2e8f0;">手动触发，不自动执行</td>
</tr>
</table>"""
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
