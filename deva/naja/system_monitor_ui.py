"""系统监控 UI 组件"""

from typing import Dict, Any
import time
from deva.naja.register import SR


def render_status_badge(status: str) -> str:
    """渲染状态徽章"""
    badges = {
        "healthy": "🟢",
        "warning": "🟡",
        "error": "🔴",
        "dead": "⚫",
        "unknown": "⚪",
    }
    return badges.get(status, "⚪")


def render_time_ago(timestamp: float) -> str:
    """渲染时间差"""
    seconds = time.time() - timestamp
    if seconds < 60:
        return f"{int(seconds)}s前"
    elif seconds < 3600:
        return f"{int(seconds/60)}m前"
    else:
        return f"{int(seconds/3600)}h前"


def render_health_cards(overall_status: Dict[str, Any]) -> str:
    """渲染健康状态卡片"""
    modules = overall_status.get("modules", [])
    
    # 按状态分组
    healthy = [m for m in modules if m["status"] == "healthy"]
    warning = [m for m in modules if m["status"] == "warning"]
    error = [m for m in modules if m["status"] in ("error", "dead")]
    unknown = [m for m in modules if m["status"] == "unknown"]
    
    cards_html = ""
    
    # 错误模块 - 红色
    for m in error:
        cards_html += f"""
        <div style="background: linear-gradient(135deg, #dc2626 0%, #991b1b 100%); border-radius: 8px; padding: 12px 15px; margin: 5px 0; display: flex; align-items: center; gap: 10px;">
            <span style="font-size: 18px;">{render_status_badge(m['status'])}</span>
            <div style="flex: 1;">
                <div style="color: #fff; font-weight: 600; font-size: 13px;">{m['name']}</div>
                <div style="color: #fca5a5; font-size: 11px;">{m['info']}</div>
            </div>
            <div style="color: #fca5a5; font-size: 10px;">{render_time_ago(m['last_seen'])}</div>
        </div>"""
    
    # 警告模块 - 黄色
    for m in warning:
        cards_html += f"""
        <div style="background: linear-gradient(135deg, #f59e0b 0%, #b45309 100%); border-radius: 8px; padding: 12px 15px; margin: 5px 0; display: flex; align-items: center; gap: 10px;">
            <span style="font-size: 18px;">{render_status_badge(m['status'])}</span>
            <div style="flex: 1;">
                <div style="color: #fff; font-weight: 600; font-size: 13px;">{m['name']}</div>
                <div style="color: #fef3c7; font-size: 11px;">{m['info']}</div>
            </div>
            <div style="color: #fef3c7; font-size: 10px;">{render_time_ago(m['last_seen'])}</div>
        </div>"""
    
    # 健康模块 - 绿色
    for m in healthy:
        cards_html += f"""
        <div style="background: linear-gradient(135deg, #059669 0%, #047857 100%); border-radius: 8px; padding: 12px 15px; margin: 5px 0; display: flex; align-items: center; gap: 10px;">
            <span style="font-size: 18px;">{render_status_badge(m['status'])}</span>
            <div style="flex: 1;">
                <div style="color: #fff; font-weight: 600; font-size: 13px;">{m['name']}</div>
                <div style="color: #a7f3d0; font-size: 11px;">{m['info']}</div>
            </div>
            <div style="color: #a7f3d0; font-size: 10px;">{render_time_ago(m['last_seen'])}</div>
        </div>"""
    
    # 未知模块 - 灰色
    for m in unknown:
        cards_html += f"""
        <div style="background: linear-gradient(135deg, #6b7280 0%, #4b5563 100%); border-radius: 8px; padding: 12px 15px; margin: 5px 0; display: flex; align-items: center; gap: 10px;">
            <span style="font-size: 18px;">{render_status_badge(m['status'])}</span>
            <div style="flex: 1;">
                <div style="color: #fff; font-weight: 600; font-size: 13px;">{m['name']}</div>
                <div style="color: #d1d5db; font-size: 11px;">{m['info']}</div>
            </div>
            <div style="color: #d1d5db; font-size: 10px;">{render_time_ago(m['last_seen'])}</div>
        </div>"""
    
    return cards_html


def render_summary_bar(overall_status: Dict[str, Any]) -> str:
    """渲染顶部摘要栏"""
    return f"""
    <div style="display: flex; gap: 15px; margin-bottom: 15px; padding: 10px; background: rgba(30, 41, 59, 0.8); border-radius: 8px;">
        <div style="flex: 1; text-align: center;">
            <div style="font-size: 20px; font-weight: 700; color: #4ade80;">{overall_status['healthy']}</div>
            <div style="font-size: 11px; color: #94a3b8;">正常</div>
        </div>
        <div style="flex: 1; text-align: center;">
            <div style="font-size: 20px; font-weight: 700; color: #fbbf24;">{overall_status['warning']}</div>
            <div style="font-size: 11px; color: #94a3b8;">警告</div>
        </div>
        <div style="flex: 1; text-align: center;">
            <div style="font-size: 20px; font-weight: 700; color: #f87171;">{overall_status['error']}</div>
            <div style="font-size: 11px; color: #94a3b8;">异常</div>
        </div>
        <div style="flex: 1; text-align: center;">
            <div style="font-size: 20px; font-weight: 700; color: #60a5fa;">{overall_status['total']}</div>
            <div style="font-size: 11px; color: #94a3b8;">总模块</div>
        </div>
        <div style="flex: 2; text-align: center; background: rgba(0,0,0,0.3); border-radius: 6px; padding: 5px;">
            <div style="font-size: 16px; font-weight: 600;">{overall_status['overall']}</div>
            <div style="font-size: 10px; color: #94a3b8;">系统状态</div>
        </div>
    </div>"""


def render_monitor_panel() -> str:
    """渲染完整监控面板 HTML"""
    try:
        # 避免循环导入，直接在函数内导入
        import sys
        import os
        
        # 尝试导入系统监控
        try:
            from deva.naja.system_monitor import SystemMonitor
        except ImportError:
            # deva 模块未初始化，返回空状态
            status = {
                "overall": "⚪ 待启动",
                "healthy": 0,
                "warning": 0,
                "error": 0,
                "total": 10,
                "modules": [
                    {"name": "🧠 注意力中枢", "key": "orchestrator", "status": "unknown", "last_seen": 0, "delay": 0, "info": "系统未启动"},
                    {"name": "📡 雷达引擎", "key": "radar", "status": "unknown", "last_seen": 0, "delay": 0, "info": "系统未启动"},
                    {"name": "🎰 Bandit决策", "key": "bandit", "status": "unknown", "last_seen": 0, "delay": 0, "info": "系统未启动"},
                    {"name": "📚 智慧陪伴", "key": "wisdom", "status": "unknown", "last_seen": 0, "delay": 0, "info": "系统未启动"},
                    {"name": "👁️ 末那识", "key": "manas", "status": "unknown", "last_seen": 0, "delay": 0, "info": "系统未启动"},
                    {"name": "✨ 阿那亚", "key": "alaya", "status": "unknown", "last_seen": 0, "delay": 0, "info": "系统未启动"},
                    {"name": "📡 数据源", "key": "data_source", "status": "unknown", "last_seen": 0, "delay": 0, "info": "系统未启动"},
                    {"name": "📊 策略", "key": "strategy", "status": "unknown", "last_seen": 0, "delay": 0, "info": "系统未启动"},
                    {"name": "⏰ 任务", "key": "task", "status": "unknown", "last_seen": 0, "delay": 0, "info": "系统未启动"},
                    {"name": "🧩 认知系统", "key": "cognition", "status": "unknown", "last_seen": 0, "delay": 0, "info": "系统未启动"},
                ]
            }
            return f"""
            <div style="background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); border-radius: 12px; padding: 20px; margin: 20px 0;">
                <div style="color: #fff; font-size: 16px; font-weight: 600; margin-bottom: 15px;">
                    🔍 系统健康监控
                </div>
                {render_summary_bar(status)}
                <div style="max-height: 400px; overflow-y: auto;">
                    {render_health_cards(status)}
                </div>
            </div>"""
        
        monitor = SR('system_monitor')
        status = monitor.get_overall_status()
        
        return f"""
        <div style="background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); border-radius: 12px; padding: 20px; margin: 20px 0;">
            <div style="color: #fff; font-size: 16px; font-weight: 600; margin-bottom: 15px;">
                🔍 系统健康监控
            </div>
            {render_summary_bar(status)}
            <div style="max-height: 400px; overflow-y: auto;">
                {render_health_cards(status)}
            </div>
        </div>"""
    except Exception as e:
        return f"""
        <div style="background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); border-radius: 12px; padding: 20px; margin: 20px 0;">
            <div style="color: #f87171; font-size: 14px;">⚠️ 监控系统加载失败: {str(e)[:100]}</div>
        </div>"""
