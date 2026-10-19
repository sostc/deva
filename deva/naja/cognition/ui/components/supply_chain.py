"""Supply Chain 入口卡 —— 供应链-叙事联动的**跳转入口**

2026-10-19：这块内容搬去了 ``/supplychain`` 页（``attention/ui/supply_chain/
linkage.py``）。搬走的理由：``/supplychain`` 原本只有静态知识图谱，缺的正
是「叙事这一侧现在发生了什么」；它是供应链视图的另一半，不是认知层的一个
结论，放在认知页「深度分析」里属于放错家。

这里保留一张 46px 的入口卡，带实时的叙事/股票/事件计数：
**搬走不等于够不着** —— 否则用户只会看到这块内容凭空消失。
"""

from pywebio.output import put_html

from .layout import jump_card


def render_supply_chain(ui):
    counts = None
    try:
        from deva.naja.cognition import get_supply_chain_linker

        summary = get_supply_chain_linker().get_supply_chain_summary() or {}
        counts = (
            f"{summary.get('total_narratives', 0)} 叙事 · "
            f"{summary.get('total_stocks_mapped', 0)} 股票 · "
            f"{summary.get('recent_events_count', 0)} 事件"
        )
    except Exception:
        # 拿不到就只留跳转，不编造计数
        counts = ""

    put_html(jump_card(
        icon="🔗",
        title="供应链-叙事联动",
        desc="最热叙事与最近风险事件已并入供应链页（与静态知识图谱同页）",
        href="/supplychain",
        meta=counts,
    ))
