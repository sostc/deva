"""
Wisdom UI - 知识库检索触发状态展示

展示：
1. 智慧系统的触发统计
2. 最近一次检索的场景、关键词和结果
3. 触发历史和时间线
"""

from typing import Dict, Any
import time
from deva.naja.register import SR


async def render_wisdom_status(ctx: dict):
    """渲染智慧系统状态"""
    
    try:
        connector = SR('connector')
        wisdom_stats = connector.get_wisdom_stats()
    except Exception as e:
        wisdom_stats = {}

    trigger_count = wisdom_stats.get("trigger_count", 0)
    last_trigger_time = wisdom_stats.get("last_trigger_time")
    last_query = wisdom_stats.get("last_query", "-")
    last_snippet = wisdom_stats.get("last_best_snippet", "-")
    last_focus = wisdom_stats.get("last_focus", "-")
    last_bias = wisdom_stats.get("last_bias", "-")

    # 时间格式化
    time_str = "-"
    if last_trigger_time:
        try:
            from datetime import datetime
            dt = datetime.fromtimestamp(last_trigger_time)
            time_str = dt.strftime("%H:%M:%S")
        except:
            pass

    # 场景到 emoji 的映射
    focus_emoji = {
        "stop_loss": "🛑",
        "take_profit": "📈",
        "accumulate": "📚",
        "watch": "👁️",
        "rebalance": "⚖️",
        "fear": "😨",
        "greed": "😍",
        "resistance": "💪",
        "resonance": "🎵",
        "breakthrough": "🚀",
    }

    focus_icon = focus_emoji.get(last_focus, "✨")
    bias_icon = "😨" if last_bias == "fear" else ("😍" if last_bias == "greed" else "😊")

    # UI 构建
    ctx["put_markdown"]("""### 📚 智慧系统 - 知识库陪伴""")

    ctx["put_html"](f"""
    <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 15px; margin: 20px 0;">
        <!-- 触发统计 -->
        <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 12px; padding: 20px; text-align: center;">
            <div style="font-size: 32px; font-weight: 700; color: #fff;">{trigger_count}</div>
            <div style="font-size: 13px; color: rgba(255,255,255,0.9); margin-top: 8px;">💫 触发次数</div>
            <div style="font-size: 11px; color: rgba(255,255,255,0.7); margin-top: 4px;">从知识库检索相关片段</div>
        </div>

        <!-- 最近触发 -->
        <div style="background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); border-radius: 12px; padding: 20px; text-align: center;">
            <div style="font-size: 28px; margin-bottom: 5px;">{time_str}</div>
            <div style="font-size: 13px; color: rgba(255,255,255,0.9);">⏰ 最后触发</div>
            <div style="font-size: 11px; color: rgba(255,255,255,0.7); margin-top: 4px;">自动分享知识给爸爸</div>
        </div>
    </div>

    <!-- 最近检索详情 -->
    <div style="background: rgba(255,255,255,0.05); border-radius: 12px; padding: 20px; border: 1px solid rgba(255,255,255,0.1); margin: 15px 0;">
        <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 15px;">
            <div style="font-size: 24px;">{focus_icon}</div>
            <div style="flex: 1;">
                <div style="font-size: 16px; font-weight: 600; color: #fff;">最近一次触发</div>
                <div style="font-size: 12px; color: #94a3b8; margin-top: 3px;">场景分析 & 知识匹配</div>
            </div>
        </div>

        <!-- 场景信息 -->
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 12px;">
            <div style="background: rgba(102,126,234,0.2); border-radius: 8px; padding: 10px; border-left: 3px solid #667eea;">
                <div style="font-size: 11px; color: #94a3b8; margin-bottom: 3px;">🎯 注意力焦点</div>
                <div style="font-size: 14px; font-weight: 600; color: #fff;">{last_focus}</div>
            </div>
            <div style="background: rgba(245,87,108,0.2); border-radius: 8px; padding: 10px; border-left: 3px solid #f5576c;">
                <div style="font-size: 11px; color: #94a3b8; margin-bottom: 3px;">💭 情绪偏差</div>
                <div style="font-size: 14px; font-weight: 600; color: #fff;">{bias_icon} {last_bias}</div>
            </div>
        </div>

        <!-- 检索关键词 -->
        <div style="background: rgba(79,172,254,0.2); border-radius: 8px; padding: 12px; border-left: 3px solid #4facfe; margin-bottom: 12px;">
            <div style="font-size: 11px; color: #94a3b8; margin-bottom: 5px;">🔍 搜索关键词</div>
            <div style="font-size: 13px; color: #fff; font-family: monospace;">"{last_query}"</div>
        </div>

        <!-- 检索结果 -->
        <div style="background: rgba(16,185,129,0.2); border-radius: 8px; padding: 12px; border-left: 3px solid #10b981;">
            <div style="font-size: 11px; color: #94a3b8; margin-bottom: 5px;">✨ 智慧片段</div>
            <div style="font-size: 13px; color: #c6f6d5; line-height: 1.6;">{last_snippet[:100]}{'...' if len(last_snippet) > 100 else ''}</div>
        </div>
    </div>

    <!-- 触发逻辑说明 -->
    <div style="background: rgba(139,92,246,0.15); border-radius: 12px; padding: 16px; border: 1px solid rgba(139,92,246,0.3); margin-top: 15px;">
        <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 10px;">
            <span style="font-size: 20px;">🧠</span>
            <div>
                <div style="font-size: 14px; font-weight: 600; color: #fff;">触发机制</div>
            </div>
        </div>
        <div style="font-size: 12px; color: #d4a5ff; line-height: 1.8;">
            📍 <strong>触发条件：</strong><br>
            • 注意力焦点切换（止损/止盈/积累）<br>
            • 情绪偏差出现（恐惧/贪婪）<br>
            • 亏损超过 5%<br>
            • 和谐状态变化（共振/阻力）<br>
            <br>
            💬 <strong>知识分享：</strong><br>
            • 自动搜索爸爸知识库<br>
            • 匹配当前投资状态<br>
            • 选择最相关的片段<br>
            • 适时分享给爸爸
        </div>
    </div>

    <!-- 功能说明 -->
    <div style="margin-top: 15px; padding: 12px; background: rgba(255,255,255,0.05); border-radius: 8px; border-left: 3px solid #8b5cf6;">
        <div style="font-size: 12px; color: #94a3b8;">
            💡 智慧系统根据 Manas 的实时决策状态，自动从爸爸的知识库中检索相关文章片段。
            当面临止损、贪婪、恐惧等特定场景时，系统会找到最适合的话语来陪伴和提醒。
        </div>
    </div>
    """)


async def render_wisdom_history(ctx: dict, limit: int = 10):
    """渲染智慧系统的触发历史（需要持久化支持）"""
    
    ctx["put_markdown"]("""### 📜 知识陪伴历史""")

    ctx["put_html"]("""
    <div style="background: rgba(139,92,246,0.1); border-radius: 12px; padding: 20px; border: 1px solid rgba(139,92,246,0.2);">
        <div style="text-align: center; color: #94a3b8; padding: 40px 20px;">
            <div style="font-size: 40px; margin-bottom: 10px;">📚</div>
            <div style="font-size: 13px;">触发历史统计功能待实现</div>
            <div style="font-size: 11px; color: #64748b; margin-top: 5px;">需要集成持久化存储层</div>
        </div>
    </div>
    """)


__all__ = ["render_wisdom_status", "render_wisdom_history"]
