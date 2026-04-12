"""首页统计卡片"""

from deva.naja.register import SR


def render_stats_cards(ctx: dict, ds_stats: dict, task_stats: dict,
                       strategy_stats: dict, dict_stats: dict):
    """渲染9宫格统计卡片"""

    # 获取高级统计数据
    try:
        from deva.naja.attention.orchestration.trading_center import get_trading_center
        from deva.naja.radar import get_radar_engine
        from deva.naja.cognition.core import get_cognition_system

        tc = get_trading_center()
        os = tc.get_attention_os()
        orch_stats = {"registered_strategies": 0}
        try:
            orch_stats["registered_strategies"] = len(os.market_scheduler._symbol_weights)
        except Exception:
            pass

        radar = get_radar_engine()
        radar_events = radar.get_recent_events(limit=100) if hasattr(radar, 'get_recent_events') else []

        bandit = SR('bandit_runner')
        bandit_stats = bandit.get_stats() if hasattr(bandit, 'get_stats') else {}

        cognition = get_cognition_system()
        cognition_stats = cognition.get_stats() if hasattr(cognition, 'get_stats') else {}

        attention_total = orch_stats.get('registered_strategies', 0)
        radar_count = len(radar_events)
        bandit_actions = bandit_stats.get('total_actions', 0) if isinstance(bandit_stats, dict) else 0
        cognition_signals = cognition_stats.get('signals_processed', 0) if isinstance(cognition_stats, dict) else 0

    except Exception:
        attention_total = ds_stats.get('total', 0)
        radar_count = 0
        bandit_actions = 0
        cognition_signals = 0

    # 获取 wisdom 统计
    wisdom_trigger_count = 0
    wisdom_last_focus = "-"
    try:
        connector = SR('connector')
        w_stats = connector.get_wisdom_stats()
        wisdom_trigger_count = w_stats.get("trigger_count", 0)
        wisdom_last_focus = w_stats.get("last_focus", "-") or "-"
    except Exception:
        pass

    ctx["put_html"](f"""
    <div style="display: grid; grid-template-columns: repeat(5, 1fr); gap: 15px; margin: 20px 0;">
        <div style="background: linear-gradient(135deg, #1a3a5c 0%, #0d2137 100%); border-radius: 12px; padding: 20px; text-align: center; transition: transform 0.2s; cursor: pointer;" onmouseover="this.style.transform='scale(1.05)'" onmouseout="this.style.transform='scale(1)'">
            <div style="font-size: 32px; font-weight: 700; color: #00d4ff;">{attention_total}</div>
            <div style="font-size: 14px; color: #fff; margin-top: 8px;">🧠 注意力策略</div>
            <div style="font-size: 11px; color: #94a3b8; margin-top: 5px;">聚焦核心问题，Query驱动优先级</div>
        </div>
        <div style="background: linear-gradient(135deg, #3a2a1a 0%, #2a1a0d 100%); border-radius: 12px; padding: 20px; text-align: center; transition: transform 0.2s; cursor: pointer;" onmouseover="this.style.transform='scale(1.05)'" onmouseout="this.style.transform='scale(1)'">
            <div style="font-size: 32px; font-weight: 700; color: #f59e0b;">{radar_count}</div>
            <div style="font-size: 14px; color: #fff; margin-top: 8px;">📡 雷达事件</div>
            <div style="font-size: 11px; color: #94a3b8; margin-top: 5px;">发现市场异常，感知风险信号</div>
        </div>
        <div style="background: linear-gradient(135deg, #3a1a2a 0%, #2a0d1a 100%); border-radius: 12px; padding: 20px; text-align: center; transition: transform 0.2s; cursor: pointer;" onmouseover="this.style.transform='scale(1.05)'" onmouseout="this.style.transform='scale(1)'">
            <div style="font-size: 32px; font-weight: 700; color: #f43f5e;">{bandit_actions}</div>
            <div style="font-size: 14px; color: #fff; margin-top: 8px;">🎰 Bandit决策</div>
            <div style="font-size: 11px; color: #94a3b8; margin-top: 5px;">交易闭环优化，持续学习反馈</div>
        </div>
        <div style="background: linear-gradient(135deg, #2a1a3a 0%, #1a0d2a 100%); border-radius: 12px; padding: 20px; text-align: center; transition: transform 0.2s; cursor: pointer;" onmouseover="this.style.transform='scale(1.05)'" onmouseout="this.style.transform='scale(1)'">
            <div style="font-size: 32px; font-weight: 700; color: #8b5cf6;">{cognition_signals}</div>
            <div style="font-size: 14px; color: #fff; margin-top: 8px;">🧩 认知信号</div>
            <div style="font-size: 11px; color: #94a3b8; margin-top: 5px;">跨信号共振，验证投资判断</div>
        </div>
        <!-- Wisdom 智慧系统卡片 -->
        <div style="background: linear-gradient(135deg, #667eea 0%, #f093fb 100%); border-radius: 12px; padding: 20px; text-align: center; transition: transform 0.2s; cursor: pointer;" onmouseover="this.style.transform='scale(1.05)'" onmouseout="this.style.transform='scale(1)'">
            <div style="font-size: 32px; font-weight: 700; color: #fff;">{wisdom_trigger_count}</div>
            <div style="font-size: 14px; color: #fff; margin-top: 8px;">📚 智慧陪伴</div>
            <div style="font-size: 11px; color: rgba(255,255,255,0.85); margin-top: 5px;">{'已触发' if wisdom_trigger_count > 0 else '静默中'}</div>
            <div style="font-size: 10px; color: rgba(255,255,255,0.7); margin-top: 3px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{wisdom_last_focus}</div>
        </div>
        <div style="background: linear-gradient(135deg, #1a3a3a 0%, #0d2727 100%); border-radius: 12px; padding: 20px; text-align: center; transition: transform 0.2s; cursor: pointer;" onmouseover="this.style.transform='scale(1.05)'" onmouseout="this.style.transform='scale(1)'">
            <div style="font-size: 32px; font-weight: 700; color: #667eea;">{ds_stats['total']}</div>
            <div style="font-size: 14px; color: #fff; margin-top: 8px;">📡 数据源</div>
            <div style="font-size: 11px; color: #94a3b8; margin-top: 5px;">实时/定时采集，数据驱动</div>
        </div>
        <div style="background: linear-gradient(135deg, #3a1a3a 0%, #2a0d2a 100%); border-radius: 12px; padding: 20px; text-align: center; transition: transform 0.2s; cursor: pointer;" onmouseover="this.style.transform='scale(1.05)'" onmouseout="this.style.transform='scale(1)'">
            <div style="font-size: 32px; font-weight: 700; color: #f093fb;">{task_stats['total']}</div>
            <div style="font-size: 14px; color: #fff; margin-top: 8px;">⏰ 任务</div>
            <div style="font-size: 11px; color: #94a3b8; margin-top: 5px;">定时调度执行，自动运行</div>
        </div>
        <div style="background: linear-gradient(135deg, #1a3a4a 0%, #0d2a3a 100%); border-radius: 12px; padding: 20px; text-align: center; transition: transform 0.2s; cursor: pointer;" onmouseover="this.style.transform='scale(1.05)'" onmouseout="this.style.transform='scale(1)'">
            <div style="font-size: 32px; font-weight: 700; color: #4facfe;">{strategy_stats['total']}</div>
            <div style="font-size: 14px; color: #fff; margin-top: 8px;">📊 策略</div>
            <div style="font-size: 11px; color: #94a3b8; margin-top: 5px;">处理与决策，执行交易</div>
        </div>
        <div style="background: linear-gradient(135deg, #1a3a1a 0%, #0d2a0d 100%); border-radius: 12px; padding: 20px; text-align: center; transition: transform 0.2s; cursor: pointer;" onmouseover="this.style.transform='scale(1.05)'" onmouseout="this.style.transform='scale(1)'">
            <div style="font-size: 32px; font-weight: 700; color: #43e97b;">{dict_stats['total']}</div>
            <div style="font-size: 14px; color: #fff; margin-top: 8px;">📚 字典</div>
            <div style="font-size: 11px; color: #94a3b8; margin-top: 5px;">参考数据，配置管理</div>
        </div>
    </div>
    """)
