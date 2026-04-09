"""
注意力系统诊断工具

在 Web UI 中查看注意力系统的运行状态
"""

from typing import Dict, Any
from pywebio.output import *
from pywebio.session import run_js


def _initialize_from_diagnostic():
    """从诊断页面初始化注意力系统"""
    try:
        from ..attention.trading_center import get_trading_center
        tc = get_trading_center()
        put_success("✅ 注意力系统初始化成功！")
        put_text(f"TradingCenter: {tc}")
        put_button("刷新页面", onclick=lambda: run_js("window.location.reload()"))
    except Exception as e:
        put_error(f"❌ 初始化失败: {e}")
        import traceback
        put_text(traceback.format_exc())


def render_attention_diagnostic():
    """渲染注意力系统诊断页面"""

    put_html("<h2>🔍 注意力系统诊断</h2>")

    put_html("<h3>1. TradingCenter (交易中枢) 状态</h3>")
    try:
        from ..attention.trading_center import get_trading_center
        tc = get_trading_center()

        put_success("✅ TradingCenter 已创建")

        os = tc.get_attention_os()
        kernel = os.kernel
        scheduler = os.strategy_decision_maker
        manas = kernel.get_manas_engine()

        put_text(f"AttentionOS: ✓")
        put_text(f"AttentionKernel: ✓")
        put_text(f"ManasEngine: ✓")
        put_text(f"StrategyDecisionMaker: ✓")

        harmony = tc.get_harmony()
        put_text(f"和谐强度: {harmony.get('harmony_strength', 0):.3f}")
        put_text(f"和谐状态: {harmony.get('harmony_state', 'unknown')}")
        put_text(f"应行动: {harmony.get('should_act', False)}")
        put_text(f"行动类型: {harmony.get('action_type', 'unknown')}")

    except Exception as e:
        put_error(f"❌ TradingCenter 错误: {e}")

    put_html("<h3>2. StrategyDecisionMaker (市场调度器) 状态</h3>")
    try:
        from ..attention.trading_center import get_trading_center
        tc = get_trading_center()
        scheduler = tc.attention_os.strategy_decision_maker

        freq_config = scheduler.get_frequency_config()
        put_text(f"频率等级: {freq_config.get('level', 'unknown')}")
        put_text(f"调度间隔: {freq_config.get('interval_seconds', 0):.1f} 秒")

        top_symbols = scheduler.get_top_symbols(5)
        if top_symbols:
            put_text("Top 5 股票:")
            for item in top_symbols:
                put_text(f"  {item['symbol']}: {item['weight']:.4f}")
        else:
            put_warning("⚠️ 没有计算任何个股权重")

        top_blocks = scheduler.get_top_blocks(3)
        if top_blocks:
            put_text("Top 3 题材:")
            for item in top_blocks:
                block_name = item.get('block', item.get('sector', ''))
                put_text(f"  {block_name}: {item['weight']:.4f}")

    except Exception as e:
        put_error(f"❌ StrategyDecisionMaker 错误: {e}")

    put_html("<h3>3. ManasEngine (末那识) 状态</h3>")
    try:
        from ..attention.trading_center import get_trading_center
        tc = get_trading_center()
        manas = tc.get_attention_os().kernel.get_manas_engine()

        test_output = manas.compute(
            portfolio={},
            scanner=None,
            bandit_tracker=None,
            macro_signal=0.5,
            narratives=[]
        )

        put_text(f"Manas Score: {test_output.manas_score:.3f}")
        put_text(f"Harmony Strength: {test_output.harmony_strength:.3f}")
        put_text(f"Timing Score: {test_output.timing_score:.3f}")
        put_text(f"Regime Score: {test_output.regime_score:.3f}")
        put_text(f"Confidence Score: {test_output.confidence_score:.3f}")
        put_text(f"Risk Temperature: {test_output.risk_temperature:.3f}")
        put_text(f"Action Type: {test_output.action_type.value if hasattr(test_output.action_type, 'value') else test_output.action_type}")
        put_text(f"Should Act: {test_output.should_act}")

    except Exception as e:
        put_error(f"❌ ManasEngine 错误: {e}")

    put_html("<h3>4. FirstPrinciplesMind (因果推理) 状态</h3>")
    try:
        from ..attention.trading_center import get_trading_center
        tc = get_trading_center()
        fp_mind = tc._get_first_principles_mind()

        if fp_mind is None:
            put_warning("⚠️ FirstPrinciplesMind 未初始化")
        else:
            put_success("✅ FirstPrinciplesMind 已创建")

    except Exception as e:
        put_error(f"❌ FirstPrinciplesMind 错误: {e}")

    put_html("<h3>5. AwakenedAlaya (觉醒) 状态</h3>")
    try:
        from ..attention.trading_center import get_trading_center
        tc = get_trading_center()
        alaya = tc._get_awakened_alaya()

        if alaya is None:
            put_warning("⚠️ AwakenedAlaya 未初始化")
        else:
            put_success("✅ AwakenedAlaya 已创建")

    except Exception as e:
        put_error(f"❌ AwakenedAlaya 错误: {e}")

    put_html("<h3>6. 策略管理器状态</h3>")
    try:
        from deva.naja.market_hotspot.strategies import get_strategy_manager
        manager = get_strategy_manager()

        stats = manager.get_all_stats()

        if stats['is_running']:
            put_success("🟢 策略管理器运行中")
        else:
            put_error("🔴 策略管理器已停止")

        put_text(f"总策略数: {stats['total_strategies']}")
        put_text(f"活跃策略: {stats['active_strategies']}")
        put_text(f"总信号数: {stats['total_signals_generated']}")

        if stats['total_strategies'] == 0:
            put_warning("⚠️ 没有注册任何策略！")

    except Exception as e:
        put_error(f"❌ 策略管理器错误: {e}")

    put_html("<h3>7. 历史追踪器状态</h3>")
    try:
        from deva.naja.market_hotspot.market_hotspot_history_tracker import get_history_tracker
        tracker = get_history_tracker()

        if tracker is None:
            put_warning("⚠️ 历史追踪器未初始化")
        else:
            put_success("✅ 历史追踪器已创建")

            summary = tracker.get_summary()
            put_text(f"快照数: {summary.get('snapshot_count', 0)}")
            put_text(f"变化数: {summary.get('change_count', 0)}")

    except Exception as e:
        put_error(f"❌ 历史追踪器错误: {e}")

    put_html("<hr>")
    put_button("🚀 重新初始化", onclick=lambda: _initialize_from_diagnostic(), color="primary")
    put_text("")
    put_text("诊断完成。")
