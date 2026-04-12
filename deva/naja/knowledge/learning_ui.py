"""
Learning Layer UI - 学习层用户界面

提供知识状态查看和手动干预功能
采用深色主题风格，与认知页面一致
"""

import json
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path

from .knowledge_store import KnowledgeStore, KnowledgeEntry, KnowledgeState, get_knowledge_store
from .state_manager import KnowledgeStateManager, get_state_manager
from .cognition_interface import CognitionInterface, get_cognition_interface


class LearningUI:
    """
    学习层 UI 模块

    功能：
    1. 查看知识状态统计
    2. 查看知识列表（按状态分类）
    3. 手动干预知识状态
    4. 查看冷静期信息
    5. 查看状态转换历史
    """

    THEME = {
        "bg_gradient": "linear-gradient(135deg, #0f172a 0%, #1e293b 100%)",
        "card_bg": "rgba(30, 41, 59, 0.5)",
        "card_border": "rgba(148, 163, 184, 0.1)",
        "text_primary": "#e2e8f0",
        "text_secondary": "#94a3b8",
        "text_muted": "#64748b",
        "accent": "#f59e0b",
        "accent_bg": "rgba(245, 158, 11, 0.1)",
        "success": "#10b981",
        "success_bg": "rgba(16, 185, 129, 0.1)",
        "info": "#3b82f6",
        "info_bg": "rgba(59, 130, 246, 0.1)",
        "warning": "#f59e0b",
        "warning_bg": "rgba(245, 158, 11, 0.1)",
        "danger": "#ef4444",
        "danger_bg": "rgba(239, 68, 68, 0.1)",
    }

    def __init__(self,
                 store: Optional[KnowledgeStore] = None,
                 state_manager: Optional[KnowledgeStateManager] = None,
                 cognition_interface: Optional[CognitionInterface] = None):
        self.store = store or get_knowledge_store()
        self.state_manager = state_manager or get_state_manager()
        self.cognition_interface = cognition_interface or get_cognition_interface()

    def render_dashboard(self) -> str:
        """渲染知识管理仪表板"""
        stats = self.store.get_stats()
        summary = self.cognition_interface.get_knowledge_summary()
        t = self.THEME

        html = f"""
<div style="background: {t['bg_gradient']}; min-height: 100vh; padding: 24px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: {t['text_primary']};">

    <!-- 标题区 -->
    <div style="background: {t['card_bg']}; border: 1px solid {t['card_border']}; border-radius: 12px; padding: 20px 24px; margin-bottom: 20px; box-shadow: 0 4px 20px rgba(15, 23, 42, 0.25);">
        <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 8px;">
            <span style="font-size: 24px;">📚</span>
            <h1 style="margin: 0; font-size: 20px; font-weight: 600; color: {t['accent']};">学习层 - 知识管理</h1>
        </div>
        <p style="margin: 0; font-size: 13px; color: {t['text_muted']};">外部知识的学习状态与手动干预 · 冷静期机制确保知识质量</p>
    </div>

    <!-- 统计卡片 -->
    <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 20px;">
        <a href="/learning/list" style="background: {t['card_bg']}; border: 1px solid {t['accent']}; border-radius: 12px; padding: 20px; box-shadow: 0 4px 20px rgba(15, 23, 42, 0.25); text-decoration: none; cursor: pointer; transition: transform 0.2s, box-shadow 0.2s;">
            <div style="font-size: 12px; color: {t['text_muted']}; margin-bottom: 8px;">总知识数</div>
            <div style="font-size: 32px; font-weight: 700; color: {t['accent']};">{stats['total']}</div>
            <div style="font-size: 11px; color: {t['text_muted']}; margin-top: 8px;">点击查看详情 →</div>
        </a>
        <div style="background: {t['card_bg']}; border: 1px solid {t['success_bg']}; border-radius: 12px; padding: 20px; box-shadow: 0 4px 20px rgba(15, 23, 42, 0.25);">
            <div style="font-size: 12px; color: {t['text_muted']}; margin-bottom: 8px;">正式参与</div>
            <div style="font-size: 32px; font-weight: 700; color: {t['success']};">{stats['by_state'].get('qualified', 0)}</div>
        </div>
        <div style="background: {t['card_bg']}; border: 1px solid {t['info_bg']}; border-radius: 12px; padding: 20px; box-shadow: 0 4px 20px rgba(15, 23, 42, 0.25);">
            <div style="font-size: 12px; color: {t['text_muted']}; margin-bottom: 8px;">验证中</div>
            <div style="font-size: 32px; font-weight: 700; color: {t['info']};">{stats['by_state'].get('validating', 0)}</div>
        </div>
        <div style="background: {t['card_bg']}; border: 1px solid {t['card_border']}; border-radius: 12px; padding: 20px; box-shadow: 0 4px 20px rgba(15, 23, 42, 0.25);">
            <div style="font-size: 12px; color: {t['text_muted']}; margin-bottom: 8px;">观察中</div>
            <div style="font-size: 32px; font-weight: 700; color: {t['text_secondary']};">{stats['by_state'].get('observing', 0)}</div>
        </div>
    </div>

    <!-- 状态说明 & 影响链条 -->
    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 20px;">
        <!-- 状态说明 -->
        <div style="background: {t['card_bg']}; border: 1px solid {t['card_border']}; border-radius: 12px; padding: 20px; box-shadow: 0 4px 20px rgba(15, 23, 42, 0.25);">
            <div style="font-size: 14px; font-weight: 600; color: {t['text_primary']}; margin-bottom: 16px;">📖 状态说明</div>
            <div style="display: flex; flex-direction: column; gap: 12px;">
                <div style="display: flex; align-items: center; gap: 10px;">
                    <span style="background: {t['text_muted']}; padding: 4px 10px; border-radius: 6px; font-size: 11px; color: {t['text_primary']};">观察期</span>
                    <span style="color: {t['text_secondary']}; font-size: 12px;">7天冷静期，积累初始证据</span>
                </div>
                <div style="display: flex; align-items: center; gap: 10px;">
                    <span style="background: {t['info']}; padding: 4px 10px; border-radius: 6px; font-size: 11px; color: white;">验证中</span>
                    <span style="color: {t['text_secondary']}; font-size: 12px;">7天验证，多源证据积累</span>
                </div>
                <div style="display: flex; align-items: center; gap: 10px;">
                    <span style="background: {t['success']}; padding: 4px 10px; border-radius: 6px; font-size: 11px; color: white;">正式</span>
                    <span style="color: {t['text_secondary']}; font-size: 12px;">参与决策，影响注意力</span>
                </div>
                <div style="display: flex; align-items: center; gap: 10px;">
                    <span style="background: {t['danger']}; padding: 4px 10px; border-radius: 6px; font-size: 11px; color: white;">过期</span>
                    <span style="color: {t['text_secondary']}; font-size: 12px;">60天无更新，自动过期</span>
                </div>
            </div>
        </div>

        <!-- 影响链条 -->
        <div style="background: {t['card_bg']}; border: 1px solid {t['card_border']}; border-radius: 12px; padding: 20px; box-shadow: 0 4px 20px rgba(15, 23, 42, 0.25);">
            <div style="font-size: 14px; font-weight: 600; color: {t['text_primary']}; margin-bottom: 16px;">🔗 影响链条</div>
            <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap; font-size: 11px;">
                <span style="color: {t['text_secondary']};">外部学习</span>
                <span style="color: {t['text_muted']};">→</span>
                <span style="background: {t['text_muted']}; padding: 4px 10px; border-radius: 6px; color: {t['text_primary']};">观察期(7天)</span>
                <span style="color: {t['text_muted']};">→</span>
                <span style="background: {t['info']}; padding: 4px 10px; border-radius: 6px; color: white;">验证期(7天)</span>
                <span style="color: {t['text_muted']};">→</span>
                <span style="background: {t['success']}; padding: 4px 10px; border-radius: 6px; color: white;">正式参与</span>
                <span style="color: {t['text_muted']};">→</span>
                <span style="background: {t['accent_bg']}; padding: 4px 10px; border-radius: 6px; color: {t['accent']};">注意力系统</span>
                <span style="color: {t['text_muted']};">→</span>
                <span style="color: {t['text_secondary']};">行情/新闻</span>
            </div>
        </div>
    </div>

    <!-- 分类统计 -->
    <div style="background: {t['card_bg']}; border: 1px solid {t['card_border']}; border-radius: 12px; padding: 20px; box-shadow: 0 4px 20px rgba(15, 23, 42, 0.25);">
        <div style="font-size: 14px; font-weight: 600; color: {t['text_primary']}; margin-bottom: 16px;">📊 分类统计</div>
        <div style="display: flex; flex-wrap: wrap; gap: 10px;">
"""

        categories = stats.get('by_category', {})
        if categories:
            for category, count in categories.items():
                html += f'<span style="background: {t["accent_bg"]}; padding: 6px 14px; border-radius: 20px; font-size: 12px; color: {t["accent"]};">{category}: {count}</span>'
        else:
            html += f'<span style="color: {t["text_muted"]}; font-size: 12px;">暂无分类数据</span>'

        html += """
        </div>
    </div>
</div>

<script>
// PyWebIO 知识操作 API
async function handleKnowledgeAction(action, entryId, note = '') {
    try {
        const response = await fetch('/api/knowledge/action', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({action, entry_id: entryId, note})
        });
        const result = await response.json();
        if (result.success) {
            alert('操作成功: ' + result.message);
            location.reload();
        } else {
            alert('操作失败: ' + result.message);
        }
    } catch (e) {
        alert('请求失败: ' + e.message);
    }
}

// 兼容旧调用方式
function handleAction(action, entryId, note = '') {
    handleKnowledgeAction(action, entryId, note);
}
</script>
"""
        return html

    def render_knowledge_list(self,
                             status_filter: Optional[str] = None,
                             category_filter: Optional[str] = None,
                             search_query: Optional[str] = None) -> str:
        """渲染知识列表"""
        entries = self.store.get_all()

        if status_filter:
            entries = [e for e in entries if e.status == status_filter]
        if category_filter:
            entries = [e for e in entries if e.category == category_filter]
        if search_query:
            query = search_query.lower()
            entries = [e for e in entries if query in e.cause.lower() or query in e.effect.lower()]

        entries = sorted(entries, key=lambda x: x.extracted_at, reverse=True)
        t = self.THEME

        status_colors = {
            'observing': (t['text_muted'], 'rgba(100, 116, 139, 0.2)'),
            'validating': (t['info'], t['info_bg']),
            'qualified': (t['success'], t['success_bg']),
            'expired': (t['danger'], t['danger_bg']),
        }

        html = f"""
<div style="background: {t['bg_gradient']}; min-height: 100vh; padding: 24px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: {t['text_primary']};">

    <!-- 标题 -->
    <div style="background: {t['card_bg']}; border: 1px solid {t['card_border']}; border-radius: 12px; padding: 20px 24px; margin-bottom: 20px; box-shadow: 0 4px 20px rgba(15, 23, 42, 0.25);">
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <div>
                <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 4px;">
                    <span style="font-size: 24px;">📋</span>
                    <h1 style="margin: 0; font-size: 20px; font-weight: 600; color: {t['accent']};">知识列表</h1>
                </div>
                <p style="margin: 0; font-size: 13px; color: {t['text_muted']};">共 {len(entries)} 条知识</p>
            </div>
            <div style="display: flex; gap: 8px;">
                <a href="/learning" style="background: {t['card_bg']}; border: 1px solid {t['card_border']}; padding: 8px 16px; border-radius: 8px; color: {t['text_secondary']}; text-decoration: none; font-size: 12px;">← 返回仪表板</a>
                <a href="/learning/history" style="background: {t['accent_bg']}; border: 1px solid {t['accent']}; padding: 8px 16px; border-radius: 8px; color: {t['accent']}; text-decoration: none; font-size: 12px;">📜 转换历史</a>
            </div>
        </div>
    </div>

    <!-- 筛选标签 -->
    <div style="display: flex; gap: 10px; margin-bottom: 20px; flex-wrap: wrap;">
        <a href="/learning/list" style="background: {'transparent' if status_filter else t['accent_bg']}; border: 1px solid {'transparent' if status_filter else t['accent']}; padding: 6px 14px; border-radius: 20px; color: {t['accent'] if not status_filter else t['text_secondary']}; text-decoration: none; font-size: 12px;">全部</a>
        <a href="/learning/list?status=observing" style="background: {t['accent_bg'] if status_filter == 'observing' else 'transparent'}; border: 1px solid {t['accent'] if status_filter == 'observing' else t['card_border']}; padding: 6px 14px; border-radius: 20px; color: {t['text_secondary']}; text-decoration: none; font-size: 12px;">观察期</a>
        <a href="/learning/list?status=validating" style="background: {t['info_bg'] if status_filter == 'validating' else 'transparent'}; border: 1px solid {t['info'] if status_filter == 'validating' else t['card_border']}; padding: 6px 14px; border-radius: 20px; color: {t['info'] if status_filter == 'validating' else t['text_secondary']}; text-decoration: none; font-size: 12px;">验证中</a>
        <a href="/learning/list?status=qualified" style="background: {t['success_bg'] if status_filter == 'qualified' else 'transparent'}; border: 1px solid {t['success'] if status_filter == 'qualified' else t['card_border']}; padding: 6px 14px; border-radius: 20px; color: {t['success'] if status_filter == 'qualified' else t['text_secondary']}; text-decoration: none; font-size: 12px;">正式</a>
        <a href="/learning/list?status=expired" style="background: {t['danger_bg'] if status_filter == 'expired' else 'transparent'}; border: 1px solid {t['danger'] if status_filter == 'expired' else t['card_border']}; padding: 6px 14px; border-radius: 20px; color: {t['danger'] if status_filter == 'expired' else t['text_secondary']}; text-decoration: none; font-size: 12px;">过期</a>
    </div>

    <!-- 知识列表 -->
    <div style="display: flex; flex-direction: column; gap: 12px;">
"""

        if not entries:
            html += f'''
                <div style="background: {t['card_bg']}; border: 1px solid {t['card_border']}; border-radius: 12px; padding: 60px; text-align: center; color: {t['text_muted']};">暂无知识</div>
'''
        else:
            for entry in entries:
                status_color, status_bg = status_colors.get(entry.status, (t['text_muted'], 'rgba(100,116,139,0.2)'))
                cooldown = self.state_manager.get_cooldown_info(entry.id)

                extracted_date = entry.extracted_at[:10] if entry.extracted_at else ""
                source_label = "📰 来源" if entry.source else ""

                html += f"""
        <div style="background: {t['card_bg']}; border: 1px solid {t['card_border']}; border-radius: 12px; padding: 20px; box-shadow: 0 4px 20px rgba(15, 23, 42, 0.25);">
            <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px;">
                <div style="flex: 1;">
                    <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 10px;">
                        <span style="background: {status_bg}; padding: 4px 10px; border-radius: 6px; font-size: 11px; color: {status_color};">{entry.status.upper()}</span>
                        <span style="background: {t['accent_bg']}; padding: 4px 10px; border-radius: 6px; font-size: 11px; color: {t['accent']};">{entry.category}</span>
                        {"<span style='background: rgba(245,158,11,0.2); padding: 4px 10px; border-radius: 6px; font-size: 11px; color: #f59e0b;'>手动</span>" if entry.manual_override else ""}
                    </div>
                    <div style="font-size: 13px; color: {t['text_secondary']}; margin-bottom: 4px;">
                        <span style="color: {t['text_muted']};">{source_label}</span> <span style="color: {t['info']};">{entry.source}</span> · {extracted_date}
                    </div>
                    <div style="font-size: 14px; color: {t['text_primary']}; margin-bottom: 6px;">
                        <strong>原因：</strong>{entry.cause}
                    </div>
                    <div style="font-size: 14px; color: {t['accent']}; margin-bottom: 6px;">
                        <strong>结果：</strong>{entry.effect}
                    </div>
                    {"<div style='font-size: 12px; color: " + t['text_muted'] + "; margin-bottom: 6px; padding: 8px; background: rgba(30,41,59,0.3); border-radius: 6px; border-left: 3px solid " + t['info'] + ";'>📄 " + entry.original_title[:80] + ("..." if len(entry.original_title) > 80 else "") + "</div>" if entry.original_title else ""}
                    <div style="font-size: 11px; color: {t['text_muted']};">
                        证据: {entry.evidence_count} | 置信度: {entry.adjusted_confidence:.2f}
                    </div>
                </div>
                <div style="text-align: right; font-size: 11px; color: {t['text_muted']};">
                    <a href="/learning/detail?entry_id={entry.id}" style="background: {t['accent_bg']}; border: 1px solid {t['accent']}; padding: 6px 12px; border-radius: 6px; color: {t['accent']}; text-decoration: none; font-size: 11px; display: inline-block; margin-bottom: 8px;">🔍 详情</a>
"""

                if entry.status == "qualified":
                    html += f'<div style="color: {t["success"]}; margin-top: 4px;">✓ 已正式参与</div>'
                elif cooldown and entry.status in ['observing', 'validating']:
                    html += f'<div style="color: {t["info"]}; margin-top: 4px;">冷静期剩余: {cooldown["remaining_days"]}天</div>'

                html += """
                </div>
            </div>
"""

                if entry.manual_override and entry.manual_note:
                    html += f'<div style="font-size: 11px; color: {t["accent"]}; margin-top: 10px; padding: 10px; background: {t["accent_bg"]}; border-radius: 8px;">📝 手动干预: {entry.manual_note}</div>'

                html += """
            <div style="display: flex; gap: 8px; margin-top: 16px; padding-top: 16px; border-top: 1px solid rgba(148, 163, 184, 0.1);">
"""

                if entry.status in ['observing', 'validating']:
                    html += f'''
                <button onclick="handleAction('force_qualify', '{entry.id}')" style="background: {t['success']}; border: none; padding: 8px 16px; border-radius: 8px; color: white; font-size: 12px; cursor: pointer;">✓ 强制通过</button>
                <button onclick="handleAction('mark_expired', '{entry.id}')" style="background: {t['danger']}; border: none; padding: 8px 16px; border-radius: 8px; color: white; font-size: 12px; cursor: pointer;">✕ 标记过期</button>
'''
                elif entry.status == 'qualified':
                    html += f'''
                <button onclick="handleAction('reset_to_observation', '{entry.id}')" style="background: {t['text_muted']}; border: none; padding: 8px 16px; border-radius: 8px; color: white; font-size: 12px; cursor: pointer;">重置到观察期</button>
'''
                elif entry.status == 'expired':
                    html += f'''
                <button onclick="handleAction('reset_to_observation', '{entry.id}')" style="background: {t['info']}; border: none; padding: 8px 16px; border-radius: 8px; color: white; font-size: 12px; cursor: pointer;">重新学习</button>
'''

                html += """
            </div>
        </div>
"""

        html += """
    </div>
</div>

<script>
async function handleKnowledgeAction(action, entryId, note = '') {
    try {
        const response = await fetch('/api/knowledge/action', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({action, entry_id: entryId, note})
        });
        const result = await response.json();
        if (result.success) {
            alert('操作成功: ' + result.message);
            location.reload();
        } else {
            alert('操作失败: ' + result.message);
        }
    } catch (e) {
        alert('请求失败: ' + e.message);
    }
}
function handleAction(action, entryId, note = '') {
    handleKnowledgeAction(action, entryId, note);
}
</script>
"""
        return html

    def render_transition_history(self, limit: int = 50) -> str:
        """渲染状态转换历史"""
        history = self.state_manager.get_transition_history()[:limit]
        t = self.THEME

        html = f"""
<div style="background: {t['bg_gradient']}; min-height: 100vh; padding: 24px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: {t['text_primary']};">

    <!-- 标题 -->
    <div style="background: {t['card_bg']}; border: 1px solid {t['card_border']}; border-radius: 12px; padding: 20px 24px; margin-bottom: 20px; box-shadow: 0 4px 20px rgba(15, 23, 42, 0.25);">
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <div>
                <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 4px;">
                    <span style="font-size: 24px;">📜</span>
                    <h1 style="margin: 0; font-size: 20px; font-weight: 600; color: {t['accent']};">状态转换历史</h1>
                </div>
                <p style="margin: 0; font-size: 13px; color: {t['text_muted']};">共 {len(history)} 条记录</p>
            </div>
            <a href="/learning" style="background: {t['card_bg']}; border: 1px solid {t['card_border']}; padding: 8px 16px; border-radius: 8px; color: {t['text_secondary']}; text-decoration: none; font-size: 12px;">← 返回仪表板</a>
        </div>
    </div>

    <!-- 历史列表 -->
    <div style="display: flex; flex-direction: column; gap: 10px;">
"""

        if not history:
            html += f'''
        <div style="background: {t['card_bg']}; border: 1px solid {t['card_border']}; border-radius: 12px; padding: 60px; text-align: center; color: {t['text_muted']};">暂无转换记录</div>
'''
        else:
            for log in reversed(history):
                type_color = t['accent'] if log['transition_type'] == 'manual' else t['text_muted']
                type_label = '手动' if log['transition_type'] == 'manual' else '自动'

                html += f"""
        <div style="background: {t['card_bg']}; border: 1px solid {t['card_border']}; border-radius: 10px; padding: 16px 20px;">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div style="display: flex; align-items: center; gap: 12px;">
                    <span style="background: {t['danger_bg']}; padding: 4px 10px; border-radius: 6px; font-size: 11px; color: {t['danger']};">{log['from_state']}</span>
                    <span style="color: {t['text_muted']};">→</span>
                    <span style="background: {t['success_bg']}; padding: 4px 10px; border-radius: 6px; font-size: 11px; color: {t['success']};">{log['to_state']}</span>
                    <span style="background: {type_color}20; padding: 4px 10px; border-radius: 6px; font-size: 11px; color: {type_color};">{type_label}</span>
                </div>
                <div style="color: {t['text_muted']}; font-size: 11px;">{log['timestamp'][:16]}</div>
            </div>
            <div style="margin-top: 10px; color: {t['text_secondary']}; font-size: 12px;">{log['reason']}</div>
            {f"<div style='margin-top: 6px; color: {t['accent']}; font-size: 11px;'>📝 {log['manual_note']}</div>" if log.get('manual_note') else ""}
        </div>
"""

        html += """
    </div>
</div>
"""
        return html

    def render_knowledge_detail(self, entry_id: str) -> str:
        """渲染知识详情页面"""
        entry = self.store.get(entry_id)
        if not entry:
            return f"""
<div style="background: {self.THEME['bg_gradient']}; min-height: 100vh; padding: 24px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: {self.THEME['text_primary']};">
    <div style="background: {self.THEME['card_bg']}; border: 1px solid {self.THEME['card_border']}; border-radius: 12px; padding: 60px; text-align: center; color: {self.THEME['danger']};">
        <div style="font-size: 48px; margin-bottom: 16px;">❌</div>
        <div style="font-size: 18px; margin-bottom: 8px;">知识不存在</div>
        <div style="font-size: 14px; color: {self.THEME['text_muted']};">ID: {entry_id}</div>
        <a href="/learning/list" style="display: inline-block; margin-top: 24px; background: {self.THEME['accent_bg']}; border: 1px solid {self.THEME['accent']}; padding: 10px 20px; border-radius: 8px; color: {self.THEME['accent']}; text-decoration: none;">← 返回列表</a>
    </div>
</div>
"""

        t = self.THEME
        cooldown = self.state_manager.get_cooldown_info(entry.id)
        transition_history = self.state_manager.get_transition_history(entry.id)

        status_colors = {
            'observing': (t['text_muted'], 'rgba(100, 116, 139, 0.2)'),
            'validating': (t['info'], t['info_bg']),
            'qualified': (t['success'], t['success_bg']),
            'expired': (t['danger'], t['danger_bg']),
        }
        status_color, status_bg = status_colors.get(entry.status, (t['text_muted'], 'rgba(100,116,139,0.2)'))

        html = f"""
<div style="background: {t['bg_gradient']}; min-height: 100vh; padding: 24px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: {t['text_primary']};">

    <!-- 标题区 -->
    <div style="background: {t['card_bg']}; border: 1px solid {t['card_border']}; border-radius: 12px; padding: 20px 24px; margin-bottom: 20px; box-shadow: 0 4px 20px rgba(15, 23, 42, 0.25);">
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <div>
                <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 4px;">
                    <span style="font-size: 24px;">🔍</span>
                    <h1 style="margin: 0; font-size: 20px; font-weight: 600; color: {t['accent']};">知识详情</h1>
                </div>
                <p style="margin: 0; font-size: 13px; color: {t['text_muted']};">ID: {entry.id}</p>
            </div>
            <div style="display: flex; gap: 8px;">
                <a href="/learning/list" style="background: {t['card_bg']}; border: 1px solid {t['card_border']}; padding: 8px 16px; border-radius: 8px; color: {t['text_secondary']}; text-decoration: none; font-size: 12px;">← 返回列表</a>
            </div>
        </div>
    </div>

    <!-- 基本信息卡片 -->
    <div style="background: {t['card_bg']}; border: 1px solid {t['card_border']}; border-radius: 12px; padding: 20px; margin-bottom: 16px; box-shadow: 0 4px 20px rgba(15, 23, 42, 0.25);">
        <div style="font-size: 14px; font-weight: 600; color: {t['text_primary']}; margin-bottom: 16px;">📋 基本信息</div>
        <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px;">
            <div>
                <div style="font-size: 11px; color: {t['text_muted']}; margin-bottom: 4px;">状态</div>
                <span style="background: {status_bg}; padding: 4px 12px; border-radius: 6px; font-size: 12px; color: {status_color}; font-weight: 600;">{entry.status.upper()}</span>
                {"<span style='background: rgba(245,158,11,0.2); padding: 4px 8px; border-radius: 4px; font-size: 11px; color: #f59e0b; margin-left: 8px;'>手动干预</span>" if entry.manual_override else ""}
            </div>
            <div>
                <div style="font-size: 11px; color: {t['text_muted']}; margin-bottom: 4px;">分类</div>
                <span style="background: {t['accent_bg']}; padding: 4px 12px; border-radius: 6px; font-size: 12px; color: {t['accent']};">{entry.category}</span>
            </div>
            <div>
                <div style="font-size: 11px; color: {t['text_muted']}; margin-bottom: 4px;">置信度</div>
                <div style="font-size: 18px; font-weight: 600; color: {t['text_primary']};">{entry.adjusted_confidence:.3f}</div>
            </div>
            <div>
                <div style="font-size: 11px; color: {t['text_muted']}; margin-bottom: 4px;">证据数量</div>
                <div style="font-size: 18px; font-weight: 600; color: {t['text_primary']};">{entry.evidence_count}</div>
            </div>
            <div>
                <div style="font-size: 11px; color: {t['text_muted']}; margin-bottom: 4px;">提取时间</div>
                <div style="font-size: 13px; color: {t['text_secondary']};">{entry.extracted_at[:19].replace('T', ' ')}</div>
            </div>
            <div>
                <div style="font-size: 11px; color: {t['text_muted']}; margin-bottom: 4px;">最后更新</div>
                <div style="font-size: 13px; color: {t['text_secondary']};">{entry.last_updated[:19].replace('T', ' ') if entry.last_updated else 'N/A'}</div>
            </div>
        </div>
    </div>

    <!-- 来源信息卡片 -->
    <div style="background: {t['card_bg']}; border: 1px solid {t['card_border']}; border-radius: 12px; padding: 20px; margin-bottom: 16px; box-shadow: 0 4px 20px rgba(15, 23, 42, 0.25);">
        <div style="font-size: 14px; font-weight: 600; color: {t['text_primary']}; margin-bottom: 16px;">📰 来源信息</div>
        <div style="display: grid; grid-template-columns: 1fr 2fr; gap: 16px;">
            <div>
                <div style="font-size: 11px; color: {t['text_muted']}; margin-bottom: 4px;">来源媒体</div>
                <div style="font-size: 14px; color: {t['info']}; font-weight: 500;">{entry.source or '未知'}</div>
            </div>
            <div>
                <div style="font-size: 11px; color: {t['text_muted']}; margin-bottom: 4px;">原始标题</div>
                <div style="font-size: 13px; color: {t['text_secondary']}; line-height: 1.5;">{entry.original_title or '无'}</div>
            </div>
        </div>
    </div>

    <!-- 因果关系卡片 -->
    <div style="background: {t['card_bg']}; border: 1px solid {t['card_border']}; border-radius: 12px; padding: 20px; margin-bottom: 16px; box-shadow: 0 4px 20px rgba(15, 23, 42, 0.25);">
        <div style="font-size: 14px; font-weight: 600; color: {t['text_primary']}; margin-bottom: 16px;">🔗 因果关系</div>
        <div style="background: rgba(30,41,59,0.5); border-radius: 8px; padding: 16px; margin-bottom: 12px;">
            <div style="font-size: 11px; color: {t['text_muted']}; margin-bottom: 8px;">原因 (Cause)</div>
            <div style="font-size: 14px; color: {t['text_primary']}; line-height: 1.6;">{entry.cause}</div>
        </div>
        <div style="text-align: center; color: {t['text_muted']}; font-size: 20px; margin: 8px 0;">↓</div>
        <div style="background: rgba(245,158,11,0.1); border-radius: 8px; padding: 16px; border-left: 3px solid {t['accent']};">
            <div style="font-size: 11px; color: {t['text_muted']}; margin-bottom: 8px;">结果 (Effect)</div>
            <div style="font-size: 14px; color: {t['accent']}; line-height: 1.6;">{entry.effect}</div>
        </div>
    </div>

    <!-- 冷静期信息卡片 -->
"""

        if cooldown and entry.status in ['observing', 'validating']:
            html += f"""
    <div style="background: {t['card_bg']}; border: 1px solid {t['info_bg']}; border-radius: 12px; padding: 20px; margin-bottom: 16px; box-shadow: 0 4px 20px rgba(15, 23, 42, 0.25);">
        <div style="font-size: 14px; font-weight: 600; color: {t['text_primary']}; margin-bottom: 16px;">⏳ 冷静期信息</div>
        <div style="display: flex; gap: 24px;">
            <div>
                <div style="font-size: 11px; color: {t['text_muted']}; margin-bottom: 4px;">剩余天数</div>
                <div style="font-size: 24px; font-weight: 700; color: {t['info']};">{cooldown['remaining_days']} 天</div>
            </div>
            <div style="flex: 1;">
                <div style="font-size: 11px; color: {t['text_muted']}; margin-bottom: 8px;">状态说明</div>
"""
            for reason in cooldown.get('reasons', []):
                html += f"<div style='font-size: 12px; color: {t['text_secondary']}; margin-bottom: 4px;'>• {reason}</div>"
            html += """
            </div>
        </div>
    </div>
"""

        if entry.manual_override and entry.manual_note:
            html += f"""
    <!-- 手动干预说明 -->
    <div style="background: {t['accent_bg']}; border: 1px solid {t['accent']}; border-radius: 12px; padding: 20px; margin-bottom: 16px;">
        <div style="font-size: 14px; font-weight: 600; color: {t['accent']}; margin-bottom: 12px;">📝 手动干预记录</div>
        <div style="font-size: 13px; color: {t['text_secondary']};">{entry.manual_note}</div>
    </div>
"""

        html += f"""
    <!-- 状态转换历史 -->
    <div style="background: {t['card_bg']}; border: 1px solid {t['card_border']}; border-radius: 12px; padding: 20px; margin-bottom: 16px; box-shadow: 0 4px 20px rgba(15, 23, 42, 0.25);">
        <div style="font-size: 14px; font-weight: 600; color: {t['text_primary']}; margin-bottom: 16px;">📜 状态转换历史</div>
"""
        if not transition_history:
            html += f'<div style="color: {t["text_muted"]}; font-size: 13px; text-align: center; padding: 20px;">暂无转换记录</div>'
        else:
            for log in reversed(transition_history):
                type_color = t['accent'] if log['transition_type'] == 'manual' else t['text_muted']
                type_label = '手动' if log['transition_type'] == 'manual' else '自动'
                html += f"""
        <div style="background: rgba(30,41,59,0.3); border-radius: 8px; padding: 12px 16px; margin-bottom: 8px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                <div style="display: flex; align-items: center; gap: 10px;">
                    <span style="background: {t['danger_bg']}; padding: 3px 8px; border-radius: 4px; font-size: 10px; color: {t['danger']};">{log['from_state']}</span>
                    <span style="color: {t['text_muted']};">→</span>
                    <span style="background: {t['success_bg']}; padding: 3px 8px; border-radius: 4px; font-size: 10px; color: {t['success']};">{log['to_state']}</span>
                    <span style="background: {type_color}20; padding: 3px 8px; border-radius: 4px; font-size: 10px; color: {type_color};">{type_label}</span>
                </div>
                <div style="color: {t['text_muted']}; font-size: 11px;">{log['timestamp'][:16].replace('T', ' ')}</div>
            </div>
            <div style="color: {t['text_secondary']}; font-size: 12px;">{log['reason']}</div>
            {f"<div style='color: {t['accent']}; font-size: 11px; margin-top: 4px;'>📝 {log.get('manual_note', '')}</div>" if log.get('manual_note') else ""}
        </div>
"""

        html += """
    </div>

    <!-- 操作按钮 -->
    <div style="background: """ + t['card_bg'] + """; border: 1px solid """ + t['card_border'] + """; border-radius: 12px; padding: 20px; box-shadow: 0 4px 20px rgba(15, 23, 42, 0.25);">
        <div style="font-size: 14px; font-weight: 600; color: """ + t['text_primary'] + """; margin-bottom: 16px;">⚡ 操作</div>
        <div style="display: flex; gap: 12px; flex-wrap: wrap;">
"""
        if entry.status in ['observing', 'validating']:
            html += f'''
            <button onclick="handleAction('force_qualify', '{entry.id}')" style="background: {t['success']}; border: none; padding: 10px 20px; border-radius: 8px; color: white; font-size: 13px; cursor: pointer;">✓ 强制通过</button>
            <button onclick="handleAction('mark_expired', '{entry.id}')" style="background: {t['danger']}; border: none; padding: 10px 20px; border-radius: 8px; color: white; font-size: 13px; cursor: pointer;">✕ 标记过期</button>
'''
        elif entry.status == 'qualified':
            html += f'''
            <button onclick="handleAction('reset_to_observation', '{entry.id}')" style="background: {t['text_muted']}; border: none; padding: 10px 20px; border-radius: 8px; color: white; font-size: 13px; cursor: pointer;">重置到观察期</button>
'''
        elif entry.status == 'expired':
            html += f'''
            <button onclick="handleAction('reset_to_observation', '{entry.id}')" style="background: {t['info']}; border: none; padding: 10px 20px; border-radius: 8px; color: white; font-size: 13px; cursor: pointer;">重新学习</button>
'''
        html += """
        </div>
    </div>
</div>

<script>
async function handleKnowledgeAction(action, entryId, note = '') {
    try {
        const response = await fetch('/api/knowledge/action', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({action, entry_id: entryId, note})
        });
        const result = await response.json();
        if (result.success) {
            alert('操作成功: ' + result.message);
            location.reload();
        } else {
            alert('操作失败: ' + result.message);
        }
    } catch (e) {
        alert('请求失败: ' + e.message);
    }
}
function handleAction(action, entryId, note = '') {
    handleKnowledgeAction(action, entryId, note);
}
</script>
"""
        return html

    def handle_action(self, action: str, entry_id: str, note: str = "") -> Dict[str, Any]:
        """处理用户操作（全部为手动操作）"""
        entry = self.store.get(entry_id)
        if not entry:
            return {"success": False, "message": f"知识 {entry_id} 不存在"}

        if action == "force_qualify":
            success = self.state_manager.transition(
                entry_id,
                KnowledgeState.QUALIFIED,
                reason="手动强制通过",
                manual_note=note,
                is_manual=True
            )
            if success:
                self.cognition_interface.inject_causality(entry_id)
            return {
                "success": success,
                "message": "已强制通过" if success else "操作失败"
            }

        elif action == "mark_expired":
            success = self.state_manager.transition(
                entry_id,
                KnowledgeState.EXPIRED,
                reason="手动标记过期",
                manual_note=note,
                is_manual=True
            )
            return {
                "success": success,
                "message": "已标记过期" if success else "操作失败"
            }

        elif action == "reset_to_observation":
            success = self.state_manager.reset_to_observation(entry_id, note)
            return {
                "success": success,
                "message": "已重置到观察期" if success else "操作失败"
            }

        else:
            return {"success": False, "message": f"未知操作: {action}"}


_learning_ui: Optional[LearningUI] = None


def get_learning_ui() -> LearningUI:
    global _learning_ui
    if _learning_ui is None:
        _learning_ui = LearningUI()
    return _learning_ui