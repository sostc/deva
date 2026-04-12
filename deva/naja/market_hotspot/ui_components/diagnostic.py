"""
市场热点系统诊断工具

在 Web UI 中查看市场热点系统的运行状态
"""

from typing import Dict, Any
from pywebio.output import *
from pywebio.session import run_js

from deva.naja.register import SR


def _initialize_from_diagnostic():
    """从诊断页面初始化热点系统"""
    try:
        from deva.naja.market_hotspot.integration import get_market_hotspot_integration
        integration = get_market_hotspot_integration()
        put_success("✅ 市场热点系统初始化成功！")
        put_text(f"MarketHotspotIntegration: {integration}")
        put_button("刷新页面", onclick=lambda: run_js("window.location.reload()"))
    except Exception as e:
        put_error(f"❌ 初始化失败: {e}")
        import traceback
        put_text(traceback.format_exc())


def render_hotspot_diagnostic():
    """渲染市场热点系统诊断页面"""

    put_html("<h2>🔍 市场热点系统诊断</h2>")

    put_html("<h3>1. 市场热点核心状态</h3>")
    try:
        from deva.naja.market_hotspot.integration import get_market_hotspot_integration
        integration = get_market_hotspot_integration()

        if integration and integration.hotspot_system:
            put_success("✅ 市场热点系统已初始化")
            hs = integration.hotspot_system

            status = hs.get_system_status()
            put_text(f"处理次数: {status.get('processing_count', 0)}")
            put_text(f"全局热点: {status.get('global_hotspot', 0):.3f}")
            put_text(f"A股股票: {status.get('cn_symbols', 0)} 只")
            put_text(f"美股股票: {status.get('us_symbols', 0)} 只")

            if hasattr(hs, 'weight_pool'):
                weight_pool = hs.weight_pool
                all_weights = weight_pool.get_all_weights()
                put_text(f"权重数量: {len(all_weights)}")
        else:
            put_warning("⚠️ 市场热点系统未初始化")

    except Exception as e:
        put_error(f"❌ 市场热点核心错误: {e}")

    put_html("<h3>2. 权重池状态</h3>")
    try:
        from deva.naja.market_hotspot.integration import get_market_hotspot_integration
        integration = get_market_hotspot_integration()

        if integration and integration.hotspot_system and hasattr(integration.hotspot_system, 'weight_pool'):
            weight_pool = integration.hotspot_system.weight_pool
            all_weights = weight_pool.get_all_weights()

            if all_weights:
                top_symbols = sorted(all_weights.items(), key=lambda x: x[1], reverse=True)[:5]
                put_text("Top 5 股票权重:")
                for sym, wgt in top_symbols:
                    put_text(f"  {sym}: {wgt:.4f}")
            else:
                put_info("⏳ 权重池暂无数据...")
        else:
            put_warning("⚠️ 权重池未初始化")

    except Exception as e:
        put_error(f"❌ 权重池错误: {e}")

    put_html("<h3>3. 历史追踪器状态</h3>")
    try:
        from deva.naja.market_hotspot.tracking.history_tracker import get_history_tracker
        tracker = get_history_tracker()

        if tracker is None:
            put_warning("⚠️ 历史追踪器未初始化")
        else:
            put_success("✅ 历史追踪器已创建")

            summary = tracker.get_summary()
            put_text(f"快照数: {summary.get('snapshot_count', 0)}")
            put_text(f"变化数: {summary.get('change_count', 0)}")

            if summary.get('snapshot_count', 0) > 0:
                top_blocks = summary.get('top_hotspot_blocks', [])[:3]
                if top_blocks:
                    put_text("Top 3 热点题材:")
                    for block_name, weight in top_blocks:
                        put_text(f"  {block_name}: {weight:.4f}")

    except Exception as e:
        put_error(f"❌ 历史追踪器错误: {e}")

    put_html("<h3>4. 数据获取器状态</h3>")
    try:
        from deva.naja.market_hotspot.data.async_fetcher import get_data_fetcher
        fetcher = get_data_fetcher()

        if fetcher:
            put_success("✅ 数据获取器已初始化")
            stats = fetcher.get_stats()
            put_text(f"CN 活跃: {stats.get('cn_active', False)}")
            put_text(f"US 活跃: {stats.get('us_active', False)}")
            put_text(f"处理股票数: {stats.get('processed_count', 0)}")
        else:
            put_warning("⚠️ 数据获取器未初始化")

    except Exception as e:
        put_error(f"❌ 数据获取器错误: {e}")

    put_html("<h3>5. 热点传播引擎状态</h3>")
    try:
        from deva.naja.market_hotspot.intelligence import HotspotPropagation
        if HotspotPropagation:
            put_success("✅ 热点传播引擎已加载")
        else:
            put_warning("⚠️ 热点传播引擎未初始化")
    except Exception as e:
        put_warning(f"⚠️ 热点传播引擎: {e}")

    put_html("<hr>")
    put_button("🚀 重新初始化", onclick=lambda: _initialize_from_diagnostic(), color="primary")
    put_text("")
    put_text("诊断完成。")
