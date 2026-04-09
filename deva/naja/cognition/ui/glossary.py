"""
认知系统名词解释页面
"""

from pywebio.output import put_html
from pywebio.session import set_env, run_js

from ...common.ui_theme import get_nav_menu_js


def cognition_glossary_page():
    """认知系统名词解释页面"""
    set_env(title="Naja - 认知名词解释", output_animation=False)
    run_js(get_nav_menu_js())

    put_html("""
    <div style="background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); border-radius: 14px; padding: 20px 24px; margin-bottom: 16px; box-shadow: 0 4px 20px rgba(15, 23, 42, 0.25); border: 1px solid #334155;">
        <div style="display: flex; align-items: center; gap: 12px;">
            <span style="font-size: 32px;">📖</span>
            <div>
                <div style="font-size: 20px; font-weight: 700; color: #f1f5f9;">认知系统名词解释</div>
                <div style="font-size: 12px; color: #64748b; margin-top: 4px;">快速理解认知系统的核心概念</div>
            </div>
        </div>
    </div>
    """)

    glossary_items = [
        {
            "category": "📥 输入层",
            "items": [
                {"term": "新闻事件", "desc": "从金十数据等来源获取的外部新闻，经过 TextImportanceScorer 处理后进入认知系统"},
                {"term": "市场注意力", "desc": "GlobalAttentionEngine 计算的市场整体关注度，反映市场活跃程度"},
                {"term": "行情数据", "desc": "实时价格、成交量、题材涨跌等市场数据"},
            ]
        },
        {
            "category": "🧠 认知层",
            "items": [
                {"term": "NarrativeTracker", "desc": "叙事追踪器，同时追踪外部叙事(world_narrative)和供需动态(value_market_summary)"},
                {"term": "WorldNarrativeTracker", "desc": "外部叙事追踪，检测AI、芯片、新能源等外部热点主题"},
                {"term": "SupplyDemandNarrativeTracker", "desc": "供需叙事追踪，检测限流、瓶颈、效率突破等供需变化"},
                {"term": "Dynamics(动态)", "desc": "供需动态信号，代表我们认定的真正重要变化"},
                {"term": "Sentiment(情绪)", "desc": "市场情绪信号，代表市场当前关注的话题/情绪，仅作参考"},
                {"term": "CrossSignalAnalyzer", "desc": "共振检测器，检测新闻×注意力、时间共振、叙事共振等"},
                {"term": "InsightPool", "desc": "洞察池，存储和管理认知系统生成的洞察"},
            ]
        },
        {
            "category": "🧘 Manas 层",
            "items": [
                {"term": "ManasEngine", "desc": "末那识决策引擎，是系统的决策中枢"},
                {"term": "TimingEngine", "desc": "时机引擎，判断现在是否能动手（天时）"},
                {"term": "AwakeningLevel", "desc": "觉醒等级：dormant(沉睡) → awakening(觉醒中) → illuminated(光照) → enlightened(般若)"},
            ]
        },
    ]

    for category_data in glossary_items:
        category = category_data["category"]
        items = category_data["items"]

        items_html = ""
        for item in items:
            items_html += f"""
            <div style="margin-bottom: 12px; padding: 10px; background: rgba(0,0,0,0.2); border-radius: 8px;">
                <div style="font-size: 13px; font-weight: 600; color: #0ea5e9; margin-bottom: 4px;">{item["term"]}</div>
                <div style="font-size: 12px; color: #94a3b8;">{item["desc"]}</div>
            </div>
            """

        put_html(f"""
        <div style="background: rgba(15, 23, 42, 0.6); border-radius: 12px; padding: 16px; border: 1px solid #334155; margin-bottom: 16px;">
            <div style="font-size: 15px; font-weight: 600; color: #f1f5f9; margin-bottom: 12px;">{category}</div>
            {items_html}
        </div>
        """)