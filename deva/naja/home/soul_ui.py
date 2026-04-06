"""
Soul UI - 灵魂展示页面

提供灵魂详情、切换、对比等UI功能
"""

from typing import Dict, Any
from pywebio.output import put_html, put_buttons
from pywebio.session import run_async


def render_soul_card(soul: Dict[str, Any]) -> str:
    """
    渲染灵魂卡片（用于首页展示）

    Args:
        soul: 灵魂配置字典

    Returns:
        HTML字符串
    """
    if not soul:
        return '''
        <div style="padding: 20px; background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); border-radius: 16px; text-align: center;">
            <div style="font-size: 48px; margin-bottom: 10px;">🧠</div>
            <div style="color: #94a3b8;">暂无激活的灵魂</div>
            <div style="margin-top: 15px;">
                <a href="/souladmin" style="color: #00d4ff;">创建灵魂 →</a>
            </div>
        </div>
        '''

    soul_name = soul.get("soul_name", "未命名")
    direction = soul.get("direction", {})
    domains = soul.get("domains", {}).get("focused", [])
    risk = soul.get("risk_profile", {})
    keywords = soul.get("keywords", {})

    icon = direction.get("icon", "🧠")
    dynamics_weight = direction.get("dynamics_weight", 0.5)
    sentiment_weight = direction.get("sentiment_weight", 0.5)
    risk_label = risk.get("label", "")
    dynamics_count = len(keywords.get("dynamics", []))
    sentiment_count = len(keywords.get("sentiment", []))

    return f'''
    <div style="padding: 20px; background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); border-radius: 16px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
            <div style="display: flex; align-items: center; gap: 10px;">
                <span style="font-size: 28px;">{icon}</span>
                <div>
                    <div style="font-size: 18px; font-weight: 600; color: #fff;">{soul_name}</div>
                    <div style="font-size: 12px; color: #4ade80;">[激活中]</div>
                </div>
            </div>
            <div style="display: flex; gap: 8px;">
                <a href="/souladmin" style="padding: 6px 12px; background: rgba(0,212,255,0.2); border-radius: 6px; color: #00d4ff; font-size: 12px; text-decoration: none;">详情</a>
                <a href="/souladmin?action=switch" style="padding: 6px 12px; background: rgba(74,222,128,0.2); border-radius: 6px; color: #4ade80; font-size: 12px; text-decoration: none;">切换</a>
            </div>
        </div>

        <div style="font-size: 13px; color: #94a3b8; margin-bottom: 15px;">
            {soul.get("philosophy", {}).get("mission", "")}
        </div>

        <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 15px;">
            <div style="background: rgba(255,255,255,0.05); padding: 10px; border-radius: 8px; text-align: center;">
                <div style="font-size: 12px; color: #94a3b8;">供需动态权重</div>
                <div style="font-size: 18px; font-weight: 600; color: #f59e0b;">{dynamics_weight}</div>
            </div>
            <div style="background: rgba(255,255,255,0.05); padding: 10px; border-radius: 8px; text-align: center;">
                <div style="font-size: 12px; color: #94a3b8;">市场情绪权重</div>
                <div style="font-size: 18px; font-weight: 600; color: #60a5fa;">{sentiment_weight}</div>
            </div>
            <div style="background: rgba(255,255,255,0.05); padding: 10px; border-radius: 8px; text-align: center;">
                <div style="font-size: 12px; color: #94a3b8;">风险偏好</div>
                <div style="font-size: 18px; font-weight: 600; color: #f472b6;">{risk_label}</div>
            </div>
            <div style="background: rgba(255,255,255,0.05); padding: 10px; border-radius: 8px; text-align: center;">
                <div style="font-size: 12px; color: #94a3b8;">关注行业</div>
                <div style="font-size: 18px; font-weight: 600; color: #a855f7;">{len(domains)}个</div>
            </div>
        </div>

        <div style="background: rgba(255,255,255,0.05); padding: 12px; border-radius: 8px;">
            <div style="font-size: 11px; color: #94a3b8; margin-bottom: 5px;">
                关注行业: {", ".join(domains)}
            </div>
            <div style="font-size: 11px; color: #f59e0b;">
                供需动态关键词: {dynamics_count}个
            </div>
            <div style="font-size: 11px; color: #60a5fa;">
                市场情绪关键词: {sentiment_count}个
            </div>
        </div>
    </div>
    '''


def render_soul_list(all_souls: list, active_soul: Dict[str, Any]) -> str:
    """
    渲染灵魂列表

    Args:
        all_souls: 所有灵魂列表
        active_soul: 当前激活的灵魂

    Returns:
        HTML字符串
    """
    if not all_souls:
        return '''
        <div style="padding: 40px; text-align: center; background: rgba(255,255,255,0.05); border-radius: 12px;">
            <div style="font-size: 48px; margin-bottom: 15px;">🧠</div>
            <div style="color: #94a3b8; margin-bottom: 15px;">暂无灵魂</div>
            <a href="/souladmin?action=create" style="padding: 10px 20px; background: linear-gradient(135deg, #00d4ff 0%, #0099cc 100%); border-radius: 20px; color: white; text-decoration: none;">创建第一个灵魂</a>
        </div>
        '''

    cards = []
    for soul in all_souls:
        soul_id = soul.get("soul_id", "")
        soul_name = soul.get("soul_name", "未命名")
        icon = soul.get("icon", "🧠")
        is_active = soul.get("is_active", False)
        dynamics_weight = soul.get("dynamics_weight", 0)
        domains = soul.get("domains", [])
        risk_level = soul.get("risk_level", "")

        status_html = '<span style="background: #4ade80; padding: 2px 8px; border-radius: 4px; font-size: 11px; color: white;">激活中</span>' if is_active else '<span style="background: rgba(255,255,255,0.2); padding: 2px 8px; border-radius: 4px; font-size: 11px; color: #94a3b8;">未激活</span>'

        card = f'''
        <div style="background: rgba(255,255,255,0.05); padding: 20px; border-radius: 12px; margin-bottom: 10px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                <div style="display: flex; align-items: center; gap: 10px;">
                    <span style="font-size: 24px;">{icon}</span>
                    <div>
                        <div style="font-weight: 600; color: #fff;">{soul_name}</div>
                        {status_html}
                    </div>
                </div>
                <div style="display: flex; gap: 8px;">
                    <a href="/souladmin?action=show&soul={soul_id}" style="padding: 6px 12px; background: rgba(0,212,255,0.2); border-radius: 6px; color: #00d4ff; font-size: 12px; text-decoration: none;">详情</a>
                    {"<span style='padding: 6px 12px; background: rgba(255,255,255,0.1); border-radius: 6px; color: #94a3b8; font-size: 12px;'>当前激活</span>" if is_active else f"<a href='/souladmin?action=activate&soul={soul_id}' style='padding: 6px 12px; background: rgba(74,222,128,0.2); border-radius: 6px; color: #4ade80; font-size: 12px; text-decoration: none;'>激活</a>"}
                </div>
            </div>
            <div style="display: flex; gap: 20px; font-size: 12px; color: #94a3b8;">
                <span>供需动态权重: <span style="color: #f59e0b;">{dynamics_weight}</span></span>
                <span>行业: <span style="color: #a855f7;">{", ".join(domains[:3])}</span></span>
                <span>风险: <span style="color: #f472b6;">{risk_level}</span></span>
            </div>
        </div>
        '''
        cards.append(card)

    create_button = '''
    <div style="text-align: center; margin-top: 20px;">
        <a href="/souladmin?action=create" style="display: inline-block; padding: 12px 24px; background: linear-gradient(135deg, #00d4ff 0%, #0099cc 100%); border-radius: 20px; color: white; text-decoration: none; font-weight: 500;">
            + 创建新灵魂
        </a>
    </div>
    '''

    return "".join(cards) + create_button


def render_soul_list_buttons(all_souls: list, active_soul: Dict[str, Any]) -> str:
    """
    渲染灵魂列表（使用 PyWebIO 按钮）

    Args:
        all_souls: 所有灵魂列表
        active_soul: 当前激活的灵魂

    Returns:
        HTML字符串 + 按钮
    """
    if not all_souls:
        put_html('''
        <div style="padding: 40px; text-align: center; background: rgba(255,255,255,0.05); border-radius: 12px;">
            <div style="font-size: 48px; margin-bottom: 15px;">🧠</div>
            <div style="color: #94a3b8; margin-bottom: 15px;">暂无灵魂</div>
        </div>
        ''')
        return ""

    for soul in all_souls:
        soul_id = soul.get("soul_id", "")
        soul_name = soul.get("soul_name", "未命名")
        icon = soul.get("icon", "🧠")
        is_active = soul.get("is_active", False)
        dynamics_weight = soul.get("dynamics_weight", 0)
        domains = soul.get("domains", [])
        risk_level = soul.get("risk_level", "")

        status_html = '<span style="background: #4ade80; padding: 2px 8px; border-radius: 4px; font-size: 11px; color: white;">激活中</span>' if is_active else '<span style="background: rgba(255,255,255,0.2); padding: 2px 8px; border-radius: 4px; font-size: 11px; color: #94a3b8;">未激活</span>'

        card = f'''
        <div style="background: rgba(255,255,255,0.05); padding: 20px; border-radius: 12px; margin-bottom: 10px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                <div style="display: flex; align-items: center; gap: 10px;">
                    <span style="font-size: 24px;">{icon}</span>
                    <div>
                        <div style="font-weight: 600; color: #fff;">{soul_name}</div>
                        {status_html}
                    </div>
                </div>
            </div>
            <div style="display: flex; gap: 20px; font-size: 12px; color: #94a3b8; margin-bottom: 10px;">
                <span>供需动态权重: <span style="color: #f59e0b;">{dynamics_weight}</span></span>
                <span>行业: <span style="color: #a855f7;">{", ".join(domains[:3]) if domains else "无"}</span></span>
                <span>风险: <span style="color: #f472b6;">{risk_level}</span></span>
            </div>
        </div>
        '''

        from pywebio.output import put_buttons

        put_html(card)

        btn_label = "🔄 切换" if not is_active else "✓ 当前激活"
        btn_color = "success" if not is_active else "secondary"

        def make_handler(sid):
            def handler(action):
                from deva.naja.home.soul_admin import _handle_soul_action, _compare_souls
                from deva.naja.config.soul_manager import get_soul_manager
                manager = get_soul_manager()

                if action == "compare":
                    _compare_souls(manager)
                elif action.startswith("show_"):
                    _handle_soul_action("show", sid, manager)
                elif action.startswith("activate_"):
                    _handle_soul_action("activate", sid, manager)
            return handler

        put_buttons(
            [
                {"label": "👁️ 详情", "value": f"show_{soul_id}", "color": "info"},
                {"label": btn_label, "value": f"activate_{soul_id}", "color": btn_color},
                {"label": "🔍 对比", "value": "compare", "color": "warning"},
            ],
            onclick=make_handler(soul_id),
            small=True
        )
        put_html("<hr style='margin: 15px 0; border-color: rgba(255,255,255,0.1);'>")

    return ""


def render_soul_detail(soul: Dict[str, Any]) -> str:
    """
    渲染灵魂详情页

    Args:
        soul: 灵魂配置字典

    Returns:
        HTML字符串
    """
    if not soul:
        return '<div style="color: #94a3b8;">未找到该灵魂</div>'

    soul_name = soul.get("soul_name", "未命名")
    direction = soul.get("direction", {})
    domains = soul.get("domains", {})
    risk = soul.get("risk_profile", {})
    philosophy = soul.get("philosophy", {})
    keywords = soul.get("keywords", {})
    values = soul.get("values", {})
    supply_chain = soul.get("supply_chain", {})
    decision_rules = soul.get("decision_rules", {})

    icon = direction.get("icon", "🧠")
    dynamics_keywords = keywords.get("dynamics", [])
    sentiment_keywords = keywords.get("sentiment", [])

    risk_stop_loss = risk.get("stop_loss", 0)
    risk_take_profit = risk.get("take_profit", 0)

    values_html = ""
    if values.get("profiles"):
        for profile in values["profiles"]:
            profile_type = profile.get("type", "")
            profile_name = profile.get("name", "")
            profile_desc = profile.get("description", "")
            weights = profile.get("weights", {})

            values_html += f'''
            <div style="background: rgba(255,255,255,0.05); padding: 15px; border-radius: 8px; margin-bottom: 10px;">
                <div style="font-weight: 600; color: #fff; margin-bottom: 5px;">{profile_name}</div>
                <div style="font-size: 12px; color: #94a3b8; margin-bottom: 8px;">{profile_desc}</div>
                <div style="display: flex; gap: 15px; font-size: 11px;">
                    <span>基本面: <span style="color: #4ade80;">{weights.get("fundamentals_weight", 0)}</span></span>
                    <span>趋势: <span style="color: #60a5fa;">{weights.get("price_sensitivity", 0)}</span></span>
                    <span>情绪: <span style="color: #f472b6;">{weights.get("sentiment_weight", 0)}</span></span>
                    <span>供需动态: <span style="color: #f59e0b;">{weights.get("dynamics_weight", 0)}</span></span>
                </div>
            </div>
            '''

    supply_chain_html = ""
    for domain, chain in supply_chain.items():
        supply_chain_html += f'''
        <div style="margin-bottom: 15px;">
            <div style="font-weight: 600; color: #fff; margin-bottom: 10px;">🏭 {domain}</div>
        '''
        for level in ["upstream", "midstream", "downstream"]:
            if level in chain:
                level_name = chain[level].get("name", level)
                nodes = chain[level].get("nodes", [])
                dynamics_kws = chain[level].get("dynamics_keywords", [])

                nodes_str = ", ".join([n.get("name", "") for n in nodes[:3]])
                supply_chain_html += f'''
                <div style="background: rgba(255,255,255,0.03); padding: 10px; border-radius: 6px; margin-bottom: 8px;">
                    <div style="font-size: 12px; color: #94a3b8;">{level.capitalize()}: {level_name}</div>
                    <div style="font-size: 11px; color: #fff; margin: 5px 0;">{nodes_str}</div>
                    <div style="font-size: 10px; color: #f59e0b;">供需动态: {", ".join(dynamics_kws[:5])}</div>
                </div>
                '''
        supply_chain_html += "</div>"

    dynamics_str = ", ".join(dynamics_keywords[:15]) + ("..." if len(dynamics_keywords) > 15 else "")
    sentiment_str = ", ".join(sentiment_keywords[:15]) + ("..." if len(sentiment_keywords) > 15 else "")

    return f'''
    <div style="padding: 20px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
            <div style="display: flex; align-items: center; gap: 15px;">
                <span style="font-size: 48px;">{icon}</span>
                <div>
                    <div style="font-size: 24px; font-weight: 600; color: #fff;">{soul_name}</div>
                    <div style="color: #4ade80; font-size: 12px;">[激活中]</div>
                </div>
            </div>
            <div style="display: flex; gap: 10px;">
                <a href="/souladmin?action=edit&soul={soul.get('soul_id', '')}" style="padding: 8px 16px; background: rgba(0,212,255,0.2); border-radius: 6px; color: #00d4ff; text-decoration: none;">编辑</a>
                <a href="/souladmin?action=export&soul={soul.get('soul_id', '')}" style="padding: 8px 16px; background: rgba(168,85,247,0.2); border-radius: 6px; color: #a855f7; text-decoration: none;">导出</a>
                <a href="/souladmin" style="padding: 8px 16px; background: rgba(255,255,255,0.1); border-radius: 6px; color: #94a3b8; text-decoration: none;">返回</a>
            </div>
        </div>

        <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 20px; margin-bottom: 20px;">
            <div style="background: rgba(255,255,255,0.05); padding: 20px; border-radius: 12px;">
                <div style="font-size: 14px; font-weight: 600; color: #fff; margin-bottom: 15px;">🎯 使命宣言</div>
                <div style="color: #94a3b8; font-size: 13px;">{philosophy.get("mission", "")}</div>
            </div>
            <div style="background: rgba(255,255,255,0.05); padding: 20px; border-radius: 12px;">
                <div style="font-size: 14px; font-weight: 600; color: #fff; margin-bottom: 15px;">⚖️ 风险配置</div>
                <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; font-size: 12px;">
                    <div>风险偏好: <span style="color: #f472b6;">{risk.get("label", "")} ({risk.get("risk_preference", 0)})</span></div>
                    <div>时间视野: <span style="color: #60a5fa;">{risk.get("time_horizon", 0)}</span></div>
                    <div>仓位上限: <span style="color: #4ade80;">{risk.get("max_position", 0)*100:.0f}%</span></div>
                    <div>止损: <span style="color: #f43f5e;">-{risk_stop_loss*100:.0f}%</span></div>
                    <div>止盈: <span style="color: #4ade80;">+{risk_take_profit*100:.0f}%</span></div>
                </div>
            </div>
        </div>

        <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 20px; margin-bottom: 20px;">
            <div style="background: rgba(255,255,255,0.05); padding: 20px; border-radius: 12px;">
                <div style="font-size: 14px; font-weight: 600; color: #fff; margin-bottom: 10px;">
                    ⚡ 供需动态配置 <span style="color: #f59e0b; font-size: 12px;">(权重: {direction.get("dynamics_weight", 0)})</span>
                </div>
                <div style="font-size: 11px; color: #94a3b8; margin-bottom: 10px;">{philosophy.get("dynamics_definition", "")}</div>
                <div style="font-size: 11px; color: #f59e0b;">{dynamics_str}</div>
            </div>
            <div style="background: rgba(255,255,255,0.05); padding: 20px; border-radius: 12px;">
                <div style="font-size: 14px; font-weight: 600; color: #fff; margin-bottom: 10px;">
                    💓 市场情绪配置 <span style="color: #60a5fa; font-size: 12px;">(权重: {direction.get("sentiment_weight", 0)})</span>
                </div>
                <div style="font-size: 11px; color: #94a3b8; margin-bottom: 10px;">{philosophy.get("sentiment_definition", "")}</div>
                <div style="font-size: 11px; color: #60a5fa;">{sentiment_str}</div>
            </div>
        </div>

        <div style="background: rgba(255,255,255,0.05); padding: 20px; border-radius: 12px; margin-bottom: 20px;">
            <div style="font-size: 14px; font-weight: 600; color: #fff; margin-bottom: 15px;">🏭 关注行业 ({len(domains.get("focused", []))}个)</div>
            <div style="display: flex; flex-wrap: wrap; gap: 10px;">
                {"".join([f'<span style="background: rgba(168,85,247,0.2); padding: 6px 12px; border-radius: 20px; font-size: 12px; color: #a855f7;">{d}</span>' for d in domains.get("focused", [])])}
            </div>
        </div>

        <div style="background: rgba(255,255,255,0.05); padding: 20px; border-radius: 12px; margin-bottom: 20px;">
            <div style="font-size: 14px; font-weight: 600; color: #fff; margin-bottom: 15px;">🎯 价值观配置</div>
            {values_html}
        </div>

        <div style="background: rgba(255,255,255,0.05); padding: 20px; border-radius: 12px;">
            <div style="font-size: 14px; font-weight: 600; color: #fff; margin-bottom: 15px;">🔗 供应链配置 ({len(supply_chain)}个行业)</div>
            {supply_chain_html or '<div style="color: #94a3b8;">暂无供应链配置</div>'}
        </div>
    </div>
    '''


def render_soul_compare(comparison: Dict[str, Any]) -> str:
    """
    渲染灵魂对比页

    Args:
        comparison: 对比结果字典

    Returns:
        HTML字符串
    """
    if comparison.get("status") != "success":
        return f'<div style="color: #f43f5e;">{comparison.get("message", "对比失败")}</div>'

    soul1 = comparison.get("soul1", {})
    soul2 = comparison.get("soul2", {})
    diffs = comparison.get("differences", [])

    def make_row(label, val1, val2, color1="#fff", color2="#fff"):
        return f'''
        <tr>
            <td style="padding: 10px; border-bottom: 1px solid rgba(255,255,255,0.1); color: #94a3b8;">{label}</td>
            <td style="padding: 10px; border-bottom: 1px solid rgba(255,255,255,0.1); color: {color1};">{val1}</td>
            <td style="padding: 10px; border-bottom: 1px solid rgba(255,255,255,0.1); color: {color2};">{val2}</td>
        </tr>
        '''

    rows = ""
    rows += make_row("图标", soul1.get("icon", ""), soul2.get("icon", ""))
    rows += make_row("价值方向", soul1.get("direction", ""), soul2.get("direction", ""))
    rows += make_row("关注行业", f"{len(soul1.get('domains', []))}个", f"{len(soul2.get('domains', []))}个")
    rows += make_row("风险偏好", f"{soul1.get('risk_level', '')} ({soul1.get('risk_preference', 0)})", f"{soul2.get('risk_level', '')} ({soul2.get('risk_preference', 0)})")
    rows += make_row("时间视野", str(soul1.get("time_horizon", 0)), str(soul2.get("time_horizon", 0)))
    rows += make_row("仓位上限", f"{soul1.get('max_position', 0)*100:.0f}%", f"{soul2.get('max_position', 0)*100:.0f}%")
    rows += make_row("止损幅度", f"-{soul1.get('stop_loss', 0)*100:.0f}%", f"-{soul2.get('stop_loss', 0)*100:.0f}%")
    rows += make_row("止盈幅度", f"+{soul1.get('take_profit', 0)*100:.0f}%", f"+{soul2.get('take_profit', 0)*100:.0f}%", "#4ade80", "#4ade80")
    rows += make_row("天道权重", str(soul1.get("dynamics_weight", 0)), str(soul2.get("dynamics_weight", 0)), "#f59e0b", "#f59e0b")
    rows += make_row("市场情绪权重", str(soul1.get("sentiment_weight", 0)), str(soul2.get("sentiment_weight", 0)), "#60a5fa", "#60a5fa")
    rows += make_row("供需动态关键词", f"{soul1.get('dynamics_count', 0)}个", f"{soul2.get('dynamics_count', 0)}个")
    rows += make_row("市场情绪关键词", f"{soul1.get('sentiment_count', 0)}个", f"{soul2.get('sentiment_count', 0)}个")

    diff_html = ""
    if diffs:
        diff_html = f'''
        <div style="background: rgba(251,191,36,0.1); padding: 15px; border-radius: 8px; margin-bottom: 20px;">
            <div style="font-size: 14px; font-weight: 600; color: #fbbf24; margin-bottom: 10px;">⚠️ 主要差异</div>
            <ul style="margin: 0; padding-left: 20px; color: #fff; font-size: 13px;">
                {"".join([f"<li style='margin-bottom: 5px;'>{d}</li>" for d in diffs])}
            </ul>
        </div>
        '''

    return f'''
    <div style="padding: 20px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
            <div style="font-size: 20px; font-weight: 600; color: #fff;">🔍 灵魂对比</div>
            <a href="/souladmin" style="padding: 8px 16px; background: rgba(255,255,255,0.1); border-radius: 6px; color: #94a3b8; text-decoration: none;">返回</a>
        </div>

        {diff_html}

        <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; margin-bottom: 20px;">
            <div style="background: rgba(255,255,255,0.05); padding: 15px; border-radius: 12px; text-align: center;">
                <div style="font-size: 24px; margin-bottom: 5px;">{soul1.get("icon", "")}</div>
                <div style="font-weight: 600; color: #fff;">{soul1.get("name", "")}</div>
            </div>
            <div style="display: flex; align-items: center; justify-content: center;">
                <div style="font-size: 24px; color: #94a3b8;">VS</div>
            </div>
            <div style="background: rgba(255,255,255,0.05); padding: 15px; border-radius: 12px; text-align: center;">
                <div style="font-size: 24px; margin-bottom: 5px;">{soul2.get("icon", "")}</div>
                <div style="font-weight: 600; color: #fff;">{soul2.get("name", "")}</div>
            </div>
        </div>

        <div style="background: rgba(255,255,255,0.05); padding: 20px; border-radius: 12px;">
            <table style="width: 100%; border-collapse: collapse;">
                <thead>
                    <tr style="border-bottom: 2px solid rgba(255,255,255,0.2);">
                        <th style="padding: 10px; text-align: left; color: #94a3b8; font-size: 12px;">配置项</th>
                        <th style="padding: 10px; text-align: left; color: #f59e0b; font-size: 12px;">{soul1.get("name", "")}</th>
                        <th style="padding: 10px; text-align: left; color: #60a5fa; font-size: 12px;">{soul2.get("name", "")}</th>
                    </tr>
                </thead>
                <tbody>
                    {rows}
                </tbody>
            </table>
        </div>
    </div>
    '''
