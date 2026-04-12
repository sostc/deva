"""
Soul Admin - 灵魂管理页面
"""

from pywebio import config
from pywebio.output import put_html, put_buttons, put_markdown, put_table, put_button, popup, close_popup, toast
from pywebio.input import select, input_group, input, textarea, checkbox

import logging

log = logging.getLogger(__name__)


def render_soul_admin():
    """渲染灵魂管理页面"""
    try:
        from deva.naja.config.soul_manager import get_soul_manager
        manager = get_soul_manager()
    except Exception as e:
        log.error(f"加载SoulManager失败: {e}")
        put_html('<div style="color: #f43f5e;">配置模块加载失败</div>')
        return

    status = manager.get_status()
    active_soul = status.get("active_soul")
    all_souls = manager.list_souls()
    presets = manager.get_preset_templates()

    put_markdown("# 🧠 灵魂管理中心")

    if not active_soul:
        put_html('''
        <div style="padding: 30px; background: linear-gradient(135deg, rgba(251,191,36,0.1) 0%, rgba(251,191,36,0.05) 100%); border-radius: 12px; border: 1px solid rgba(251,191,36,0.3); margin-bottom: 20px;">
            <div style="font-size: 18px; color: #fbbf24; margin-bottom: 10px;">⚠️ 尚未创建灵魂</div>
            <div style="color: #94a3b8; font-size: 13px;">系统当前使用硬编码的默认配置。创建一个灵魂来定制你的投资哲学。</div>
        </div>
        ''')

    put_html('<div style="margin-bottom: 30px;">')

    put_markdown("## 🚀 当前灵魂")

    if active_soul:
        from .soul_ui import render_soul_card
        put_html(render_soul_card(active_soul))
    else:
        put_html('''
        <div style="padding: 40px; text-align: center; background: rgba(255,255,255,0.05); border-radius: 12px;">
            <div style="font-size: 48px; margin-bottom: 15px;">🧠</div>
            <div style="color: #94a3b8;">暂无激活的灵魂</div>
        </div>
        ''')

    put_html("</div>")

    put_markdown("## 📋 所有灵魂")

    from .soul_ui import render_soul_list_buttons
    put_html(render_soul_list_buttons(all_souls, active_soul))

    put_markdown("## ⚙️ 快速创建")

    preset_buttons = []
    for preset in presets:
        preset_buttons.append({
            "label": f"{preset['icon']} {preset['name']}",
            "value": preset["name"],
            "color": "primary" if "激进" in preset["name"] else "success" if "保守" in preset["name"] else "info"
        })
    preset_buttons.append({"label": "✨ 自定义创建", "value": "custom", "color": "warning"})

    put_buttons(preset_buttons, onclick=lambda v: _handle_create_action(v, manager), group=True)

    put_markdown("## 💡 说明")

    put_html('''
    <div style="background: rgba(255,255,255,0.05); padding: 20px; border-radius: 12px; margin-top: 15px; font-size: 13px; color: #94a3b8;">
        <p style="margin-bottom: 10px;"><strong style="color: #fff;">🧠 什么是灵魂？</strong></p>
        <p style="margin-bottom: 10px;">灵魂是你的投资哲学配置，包含：使命宣言、关注行业、天道民心权重、风险偏好、供应链配置等。</p>

        <p style="margin-bottom: 10px;"><strong style="color: #fff;">🔄 灵魂切换</strong></p>
        <p style="margin-bottom: 10px;">有持仓时切换灵魂，已有持仓按原灵魂管理，新仓位按新灵魂。推荐选择下个交易日生效。</p>

        <p style="margin-bottom: 10px;"><strong style="color: #fff;">📦 配置回退</strong></p>
        <p>如果没有找到灵魂配置文件，系统会使用硬编码的默认配置，确保系统正常运行。</p>
    </div>
    ''')


def _handle_create_action(action, manager):
    """处理创建操作"""
    if action == "custom":
        _show_create_soul_popup(manager)
    else:
        _create_from_preset(action, manager)


def _show_create_soul_popup(manager):
    """显示创建灵魂表单"""
    put_markdown("# 🌟 创建新灵魂")
    put_html('<div style="background: rgba(0,212,255,0.1); padding: 15px; border-radius: 8px; margin-bottom: 20px; color: #94a3b8;">请填写以下配置来创建你的投资灵魂</div>')

    form = input_group("🧠 投资灵魂配置", [
        input("灵魂名称", name="name", placeholder="例如：🚀 我的赛道投资型", required=True, value="🚀 我的灵魂"),
        select("价值方向", name="direction", options=[
            ("🚀 赛道投资（推荐）- 天道权重0.9", "creative"),
            ("💧 流动性投资 - 天道权重0.5", "speculative"),
        ], value="creative"),
        checkbox("关注行业", name="domains", options=[
            ("🤖 AI/人工智能", "AI"),
            ("💾 芯片/半导体", "芯片"),
            ("⚡ 新能源", "新能源"),
            ("💊 医药/生物医药", "医药"),
            ("📱 华为产业链", "华为"),
            ("🌐 全球宏观", "全球宏观"),
            ("🏭 工业制造", "工业"),
            ("🏠 消费", "消费"),
        ], value=["AI", "芯片", "新能源"]),
        select("风险偏好", name="risk_level", options=[
            ("🛡️ 稳健型 - 仓位15%, 止损5%, 止盈20%", "conservative"),
            ("⚖️ 均衡型 - 仓位20%, 止损8%, 止盈30%", "moderate"),
            ("🚀 进取型 - 仓位30%, 止损10%, 止盈50%", "aggressive"),
        ], value="aggressive"),
        textarea("自定义理念（可选）", name="custom_notes", placeholder="例如：重点关注算力短缺问题，长期持有优质AI公司...", rows=3, value=""),
    ])

    if not form:
        toast("已取消创建", color="warning")
        render_soul_admin()
        return

    name = form.get("name", "🚀 我的灵魂")
    direction = form.get("direction", "creative")
    domains = form.get("domains", ["AI"])
    risk_level = form.get("risk_level", "moderate")
    custom_notes = form.get("custom_notes", "")

    if not domains:
        toast("至少需要选择一个关注行业", color="error")
        _show_create_soul_popup(manager)
        return

    from deva.naja.config.soul_generator import get_generator

    generator = get_generator()
    soul = generator.generate(
        name=name,
        direction=direction,
        domains=domains,
        risk_level=risk_level,
        custom_notes=custom_notes
    )

    result = generator.apply(soul)

    if result.get("status") == "success":
        toast(f"🎉 灵魂「{name}」创建成功！", color="success")
    else:
        toast(f"创建失败: {result.get('message', '未知错误')}", color="error")

    render_soul_admin()


def _create_from_preset(preset_name, manager):
    """从预设模板创建"""
    toast(f"正在从「{preset_name}」创建...", color="info")

    try:
        result = manager.create_from_preset(preset_name)
        if result.get("status") == "success":
            toast(f"🎉 灵魂「{preset_name}」创建成功！", color="success")
            render_soul_admin()
        else:
            toast(f"创建失败: {result.get('message', '未知错误')}", color="error")
    except Exception as e:
        toast(f"创建失败: {str(e)}", color="error")


def _handle_soul_action(action, soul_id, manager):
    """处理灵魂操作"""
    if action == "show":
        _show_soul_detail(soul_id, manager)
    elif action == "activate":
        _activate_soul(soul_id, manager)
    elif action == "compare":
        _compare_souls(manager)


def _show_soul_detail(soul_id, manager):
    """显示灵魂详情"""
    soul = manager.get_soul(soul_id)
    if not soul:
        toast("未找到该灵魂", color="error")
        return

    from .soul_ui import render_soul_detail
    popup(
        f"🧠 {soul.get('soul_name', '灵魂详情')}",
        [
            put_html(render_soul_detail(soul)),
            [put_buttons(["关闭"], onclick=lambda: close_popup())]
        ],
        size="large"
    )


def _activate_soul(soul_id, manager):
    """激活灵魂"""
    soul = manager.get_soul(soul_id)
    if not soul:
        toast("未找到该灵魂", color="error")
        return

    result = manager.activate_soul(soul.get("soul_name", ""))
    if result.get("status") == "success":
        toast(f"✅ 已激活「{soul.get('soul_name')}」", color="success")
        render_soul_admin()
    else:
        toast(f"激活失败: {result.get('message', '未知错误')}", color="error")


def _compare_souls(manager):
    """对比灵魂"""
    souls = manager.list_souls()
    if len(souls) < 2:
        toast("需要至少2个灵魂才能对比", color="warning")
        return

    comparison = manager.compare_souls(souls[0].get("soul_name", ""), souls[1].get("soul_name", ""))
    from .soul_ui import render_soul_compare
    popup(
        "🔍 灵魂对比",
        [
            put_html(render_soul_compare(comparison)),
            [put_buttons(["关闭"], onclick=lambda: close_popup())]
        ],
        size="large"
    )


@config(title="灵魂管理 - Naja")
def soul_admin_page():
    """灵魂管理页面入口"""
    render_soul_admin()