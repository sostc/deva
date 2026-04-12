"""热点系统流式 UI - 噪音过滤面板"""

import logging

log = logging.getLogger(__name__)


def render_noise_filter_panel() -> str:
    """渲染噪音过滤面板"""
    try:
        from deva.naja.attention.orchestration.trading_center import get_trading_center
        from deva.naja.market_hotspot.tracking.history_tracker import get_history_tracker
        from deva.naja.market_hotspot.processing import get_block_noise_detector, get_noise_manager

        orchestrator = get_trading_center()
        tracker = get_history_tracker()
        stats = orchestrator.get_stats()
        noise_stats = stats.get('noise_filter', {})

        noise_detector = get_block_noise_detector()
        noise_manager = get_noise_manager()

        blacklist_patterns = []
        if noise_detector and noise_detector.config:
            blacklist_patterns = noise_detector.config.blacklist_patterns or []

        auto_blacklist = set()
        manual_blacklist = set()
        if noise_manager:
            auto_blacklist = noise_manager._auto_blacklist if hasattr(noise_manager, '_auto_blacklist') else set()
            manual_blacklist = noise_manager._manual_blacklist if hasattr(noise_manager, '_manual_blacklist') else set()

        if not noise_stats and not blacklist_patterns:
            return _render_noise_empty_state()

        filtered = noise_stats.get('filtered_count', 0)
        whitelist = noise_stats.get('whitelist_count', 0)
        blacklist = noise_stats.get('blacklist_count', 0)
        total = noise_stats.get('total_processed', 1)

        filter_rate = (filtered / max(total, 1)) * 100 if total else 0

        whitelist_stocks = noise_stats.get('whitelist_stocks', [])
        blacklist_stocks = noise_stats.get('blacklist_stocks', [])

        def format_stock_list(stocks, max_display=5):
            if not stocks:
                return "-"
            formatted = []
            for code in stocks[:max_display]:
                name = tracker.get_symbol_name(code) if tracker else code
                if name != code:
                    formatted.append(f"{code} {name[:4]}")
                else:
                    formatted.append(code)
            result = ", ".join(formatted)
            if len(stocks) > max_display:
                result += f" +{len(stocks) - max_display}"
            return result

        whitelist_display = format_stock_list(whitelist_stocks)
        blacklist_display = format_stock_list(blacklist_stocks)

        pattern_tags = ""
        for pattern in blacklist_patterns[:12]:
            pattern_tags += f'<span style="display: inline-block; padding: 1px 4px; background: rgba(251,146,60,0.15); color: #fb923c; border-radius: 3px; font-size: 8px; margin: 1px;">{pattern}</span>'
        if len(blacklist_patterns) > 12:
            pattern_tags += f'<span style="font-size: 8px; color: #64748b;">+{len(blacklist_patterns) - 12}</span>'

        noise_blocks = sorted(list(auto_blacklist | manual_blacklist))[:8]
        noise_block_tags = ""
        for block_id in noise_blocks:
            block_display = tracker.get_block_name(block_id) if tracker else block_id
            if block_display != block_id:
                noise_block_tags += f'<span style="display: inline-block; padding: 1px 4px; background: rgba(248,113,113,0.15); color: #f87171; border-radius: 3px; font-size: 8px; margin: 1px;" title="{block_id}">{block_display[:8]}</span>'
            else:
                noise_block_tags += f'<span style="display: inline-block; padding: 1px 4px; background: rgba(248,113,113,0.15); color: #f87171; border-radius: 3px; font-size: 8px; margin: 1px;">{block_id[:10]}</span>'
        if len(auto_blacklist | manual_blacklist) > 8:
            noise_block_tags += f'<span style="font-size: 8px; color: #64748b;">+{len(auto_blacklist | manual_blacklist) - 8}</span>'

    except Exception:
        return _render_noise_empty_state()

    return f"""
    <div style="
        margin-bottom: 12px;
        background: rgba(255,255,255,0.03);
        border-radius: 12px;
        padding: 14px 18px;
        border: 1px solid rgba(255,255,255,0.08);
    ">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
            <div style="font-size: 13px; font-weight: 600; color: #fb923c;">
                🔇 噪音过滤
            </div>
            <div style="font-size: 9px; color: #64748b;">
                总处理: {total:,}
            </div>
        </div>

        <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; margin-bottom: 10px;">
            <div style="text-align: center; padding: 8px; background: rgba(248,113,113,0.1); border-radius: 4px;">
                <div style="font-size: 14px; font-weight: 700; color: #f87171;">{filtered:,}</div>
                <div style="font-size: 8px; color: #64748b;">过滤数量</div>
            </div>
            <div style="text-align: center; padding: 8px; background: rgba(74,222,128,0.1); border-radius: 4px;">
                <div style="font-size: 14px; font-weight: 700; color: #4ade80;">{whitelist}</div>
                <div style="font-size: 8px; color: #64748b;">白名单</div>
            </div>
            <div style="text-align: center; padding: 8px; background: rgba(251,146,60,0.1); border-radius: 4px;">
                <div style="font-size: 14px; font-weight: 700; color: #fb923c;">{blacklist}</div>
                <div style="font-size: 8px; color: #64748b;">黑名单</div>
            </div>
            <div style="text-align: center; padding: 8px; background: rgba(168,85,247,0.1); border-radius: 4px;">
                <div style="font-size: 14px; font-weight: 700; color: #a855f7;">{filter_rate:.1f}%</div>
                <div style="font-size: 8px; color: #64748b;">过滤率</div>
            </div>
        </div>

        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 8px;">
            <div style="padding: 6px; background: rgba(74,222,128,0.05); border-radius: 4px;">
                <div style="font-size: 8px; color: #4ade80; margin-bottom: 2px;">✅ 白名单</div>
                <div style="font-size: 8px; color: #94a3b8; word-break: break-all;">{whitelist_display}</div>
            </div>
            <div style="padding: 6px; background: rgba(251,146,60,0.05); border-radius: 4px;">
                <div style="font-size: 8px; color: #fb923c; margin-bottom: 2px;">🚫 黑名单</div>
                <div style="font-size: 8px; color: #94a3b8; word-break: break-all;">{blacklist_display}</div>
            </div>
        </div>

        <div style="margin-bottom: 8px;">
            <div style="font-size: 8px; color: #a855f7; margin-bottom: 4px;">🔍 过滤模式 (题材名含以下关键词即被过滤)</div>
            <div style="padding: 4px; background: rgba(168,85,247,0.05); border-radius: 4px;">{pattern_tags or '<span style="color: #64748b; font-size: 8px;">暂无</span>'}</div>
        </div>

        <div>
            <div style="font-size: 8px; color: #f87171; margin-bottom: 4px;">🚫 噪音题材 (自动/手动)</div>
            <div style="padding: 4px; background: rgba(248,113,113,0.05); border-radius: 4px;">{noise_block_tags or '<span style="color: #64748b; font-size: 8px;">暂无</span>'}</div>
        </div>

        <div style="padding: 4px; background: rgba(255,255,255,0.02); border-radius: 4px; margin-top: 8px;">
            <div style="height: 4px; background: rgba(255,255,255,0.1); border-radius: 2px; overflow: hidden;">
                <div style="width: {min(100, filter_rate)}%; height: 100%; background: linear-gradient(90deg, #fb923c, #f97316);"></div>
            </div>
        </div>
    </div>
    """


def _render_noise_empty_state() -> str:
    """渲染噪音过滤空状态"""
    return """
    <div style="
        margin-bottom: 12px;
        background: rgba(255,255,255,0.03);
        border-radius: 12px;
        padding: 14px 18px;
        border: 1px solid rgba(255,255,255,0.08);
    ">
        <div style="font-size: 13px; font-weight: 600; color: #fb923c; margin-bottom: 10px;">
            🔇 噪音过滤
        </div>
        <div style="text-align: center; padding: 15px; color: #64748b; font-size: 11px;">
            噪音过滤系统未初始化
        </div>
    </div>
    """


