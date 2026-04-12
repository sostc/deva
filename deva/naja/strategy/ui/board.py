"""策略看板与自动刷新"""

from datetime import datetime

from pywebio.output import use_scope
from pywebio.session import run_async

from deva.naja.infra.ui.ui_style import apply_strategy_like_styles


# 存储已显示的策略结果 ID
_shown_strategy_result_ids = {}

# 自动刷新控制
_strategy_board_auto_refresh = True


def _set_strategy_board_auto_refresh(enabled: bool):
    """设置策略看板自动刷新状态"""
    global _strategy_board_auto_refresh
    _strategy_board_auto_refresh = enabled


def _is_strategy_board_auto_refresh_enabled() -> bool:
    """获取策略看板自动刷新状态"""
    return _strategy_board_auto_refresh


async def _auto_refresh_strategy_board(ctx: dict, strategy_id: str, strategy_name: str):
    """策略看板自动刷新后台任务"""
    import asyncio
    from pywebio.exceptions import SessionClosedException
    from ..result_store import get_result_store
    from datetime import datetime
    
    await asyncio.sleep(3)
    
    # 记录上次查询的时间戳，用于增量查询
    last_query_time = None
    
    try:
        while True:
            # 增加刷新间隔到5秒
            await asyncio.sleep(5)
            
            if not _is_strategy_board_auto_refresh_enabled():
                continue
            
            try:
                # 检查会话是否已关闭
                if not ctx.get('session'):
                    break
                    
                # 尝试获取会话状态
                if hasattr(ctx.get('session'), 'closed') and ctx['session'].closed:
                    break
                    
                store = get_result_store()
                # 只查询最新的一条结果
                all_results = store.query(strategy_id=strategy_id, limit=1)
                
                # 按时间戳排序
                all_results.sort(key=lambda x: x.ts, reverse=True)
                
                # 只处理新结果（时间戳大于上次查询时间）
                if last_query_time and all_results:
                    if all_results[0].ts <= last_query_time:
                        # 没有新结果，只更新刷新时间
                        update_time_script = '''
                        <script>
                        (function() {
                            var now = new Date();
                            var timeStr = now.toLocaleString('zh-CN');
                            var element = document.getElementById('last-refresh-time');
                            if (element) {
                                element.textContent = '上次刷新: ' + timeStr;
                            }
                        })();
                        </script>
                        '''
                        try:
                            ctx["put_html"](update_time_script, scope="strategy_board")
                        except Exception:
                            # 会话已关闭，退出循环
                            break
                        continue
                
                # 更新上次查询时间
                if all_results:
                    last_query_time = all_results[0].ts
                
                global _shown_strategy_result_ids
                if strategy_id not in _shown_strategy_result_ids:
                    _shown_strategy_result_ids[strategy_id] = set()
                
                shown_ids = _shown_strategy_result_ids[strategy_id]
                new_results = []
                for r in all_results:
                    if r.id not in shown_ids and r.success:
                        new_results.append(r)
                        shown_ids.add(r.id)
                        
                        # 限制存储的结果ID数量，防止内存泄漏
                        if len(shown_ids) > 100:
                            old_ids = list(shown_ids)[:50]
                            for oid in old_ids:
                                shown_ids.discard(oid)
                
                # 处理新结果
                for r in new_results:
                    # 使用信号处理器生成详细内容
                    from deva.naja.signal.processor import get_signal_type, get_signal_detail, generate_expanded_content
                    icon, color, signal_label, importance = get_signal_type(r)
                    signal_detail = get_signal_detail(r)
                    expanded_content = generate_expanded_content(r, signal_detail)
                    
                    time_str = datetime.fromtimestamp(r.ts).strftime("%H:%M:%S")
                    
                    # 根据重要性设置样式
                    if importance == 'critical':
                        border_width = "4px"
                        bg_style = f"background:linear-gradient(135deg,{color}11,{color}22);"
                    elif importance == 'high':
                        border_width = "3px"
                        bg_style = f"background:linear-gradient(135deg,{color}08,{color}15);"
                    elif importance == 'medium':
                        border_width = "2px"
                        bg_style = f"background:linear-gradient(135deg,{color}05,{color}10);"
                    else:
                        border_width = "2px"
                        bg_style = "background:#fff;"
                    
                    # 构建更新脚本
                    update_script = f'''
                    <script>
                    (function() {{
                        var container = document.getElementById('strategy-board-container');
                        if (!container) return;
                        
                        // 更新刷新时间
                        var now = new Date();
                        var timeStr = now.toLocaleString('zh-CN');
                        var timeElement = document.getElementById('last-refresh-time');
                        if (timeElement) {{
                            timeElement.textContent = '上次刷新: ' + timeStr;
                        }}
                        
                        // 更新卡片内容
                        container.innerHTML = `
                            <div class="strategy-board-item" style="display:flex;flex-direction:column;padding:12px;margin:6px 0;{bg_style}
                                        border-radius:10px;border-left:{border_width} solid {color};
                                        box-shadow:0 2px 8px rgba(0,0,0,0.06);transition:all 0.2s ease;">
                                <div class="board-item-header" style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
                                    <div style="display:flex;align-items:center;gap:8px;">
                                        <span style="font-weight:600;color:#333;font-size:14px;">{r.strategy_name}</span>
                                        <span style="display:inline-block;padding:1px 6px;border-radius:10px;font-size:10px;
                                                    background:{color}22;color:{color};">{signal_label}</span>
                                        <span style="display:inline-block;padding:1px 6px;border-radius:10px;font-size:10px;
                                                    background:{'#dc354522' if importance == 'critical' else '#fd7e1422' if importance == 'high' else '#ffc10722' if importance == 'medium' else '#17a2b822'};
                                                    color:{'#dc3545' if importance == 'critical' else '#fd7e14' if importance == 'high' else '#ffc107' if importance == 'medium' else '#17a2b8'};
                                                {'重要' if importance == 'critical' else '关注' if importance == 'high' else '中等' if importance == 'medium' else '普通'}
                                        </span>
                                    </div>
                                    <div style="display:flex;align-items:center;gap:6px;">
                                        <span style="font-size:11px;color:#999;white-space:nowrap;">{time_str}</span>
                                    </div>
                                </div>
                                <div style="font-size:13px;color:#333;font-weight:500;margin-bottom:8px;">
                                    {signal_detail['summary']}
                                </div>
                                {'<div style="font-size:11px;color:#666;margin-bottom:8px;">'+ ' | '.join(signal_detail['highlights'][:4]) +'</div>' if signal_detail['highlights'] else ''}
                                <div class="board-item-detail" style="display:block;padding:8px 0 4px 0;">
                                    {expanded_content}
                                </div>
                            </div>
                        `;
                    }})();
                    </script>
                    '''
                    
                    try:
                        ctx["put_html"](update_script, scope="strategy_board")
                        # 稍微延迟，避免DOM操作过于集中
                        await asyncio.sleep(0.1)
                    except Exception:
                        # 会话已关闭，退出循环
                        break
                    
            except SessionClosedException:
                # 会话已关闭，退出循环
                break
            except Exception as e:
                # 记录异常但不中断循环
                import traceback
                traceback.print_exc()
                await asyncio.sleep(1)
    finally:
        # 清理资源
        if strategy_id in _shown_strategy_result_ids:
            del _shown_strategy_result_ids[strategy_id]


async def _show_strategy_board(ctx: dict, mgr, entry_id: str):
    """显示策略看板"""
    entry = mgr.get(entry_id)
    if not entry:
        ctx["toast"]("策略不存在", color="error")
        return

    from ..result_store import get_result_store
    store = get_result_store()
    recent_results = store.query(strategy_id=entry_id, limit=1)
    
    # 按时间戳排序
    recent_results.sort(key=lambda x: x.ts, reverse=True)

    with ctx["popup"](f"{entry.name}看板", size="large", closable=True):
        apply_strategy_like_styles(ctx, scope=None, include_compact_table=False, include_category_tabs=False)
        
        # 渲染看板标题和控制栏
        ctx["put_html"]("""
        <div style="margin:16px 0 12px 0;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">
            <div style="font-size:18px;font-weight:600;color:#333;">📈 策略实时结果</div>
            <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
                <label style="display:flex;align-items:center;gap:4px;cursor:pointer;font-size:11px;">
                    <input type="checkbox" id="board_auto_refresh_checkbox" checked onchange="toggleBoardAutoRefresh(this.checked)" style="cursor:pointer;">
                    <span style="font-size:11px;color:#666;">🔄 自动刷新</span>
                </label>
                <div id="last-refresh-time" style="font-size:11px;color:#999;">上次刷新: -</div>
            </div>
        </div>
        """)
        
        if not recent_results:
            ctx["put_html"](
                '<div style="padding:20px;text-align:center;color:#999;background:#f9f9f9;border-radius:8px;">暂无执行结果</div>')
            return
        
        # 只显示最新的一条结果
        r = recent_results[0]
        if not r.success:
            ctx["put_html"](
                '<div style="padding:20px;text-align:center;color:#999;background:#f9f9f9;border-radius:8px;">暂无成功的执行结果</div>')
            return
            
        from datetime import datetime
        time_str = datetime.fromtimestamp(r.ts).strftime("%H:%M:%S")
        time_full = datetime.fromtimestamp(r.ts).strftime("%Y-%m-%d %H:%M:%S")
        
        # 使用信号处理器生成详细内容
        from deva.naja.signal.processor import get_signal_detail, generate_expanded_content
        detail = get_signal_detail(r)
        expanded_content = generate_expanded_content(r, detail)

        # 使用信号处理器获取信号类型和详细信息
        from deva.naja.signal.processor import get_signal_type, get_signal_detail
        icon, color, signal_label, importance = get_signal_type(r)
        signal_detail = get_signal_detail(r)
        
        # 根据重要性设置样式
        if importance == 'critical':
            border_width = "4px"
            bg_style = f"background:linear-gradient(135deg,{color}11,{color}22);"
        elif importance == 'high':
            border_width = "3px"
            bg_style = f"background:linear-gradient(135deg,{color}08,{color}15);"
        elif importance == 'medium':
            border_width = "2px"
            bg_style = f"background:linear-gradient(135deg,{color}05,{color}10);"
        else:
            border_width = "2px"
            bg_style = "background:#fff;"
        
        # 渲染结果容器和脚本
        signal_highlights_html = '<div style="font-size:11px;color:#666;margin-bottom:8px;">'+ ' | '.join(signal_detail['highlights'][:4]) +'</div>' if signal_detail['highlights'] else ''
        board_container = f"""
        <style>
            .strategy-board-item:hover {{ box-shadow: 0 4px 16px rgba(0,0,0,0.12) !important; }}
            .board-item-detail {{ animation: fadeIn 0.2s ease; }}
            @keyframes fadeIn {{
                from {{ opacity: 0; }}
                to {{ opacity: 1; }}
            }}
        </style>
        <script>
        function toggleBoardAutoRefresh(enabled) {{
            pywebio.run_async(function() {{
                pywebio.call('set_strategy_board_auto_refresh', [enabled]);
            }});
        }}
        
        function updateLastRefreshTime() {{
            var now = new Date();
            var timeStr = now.toLocaleString('zh-CN');
            var element = document.getElementById('last-refresh-time');
            if (element) {{
                element.textContent = '上次刷新: ' + timeStr;
            }}
        }}
        
        // 初始更新刷新时间
        updateLastRefreshTime();
        </script>
        <div id="strategy-board-container" style="padding:12px;background:#f5f7fa;border-radius:12px;">
            <div class="strategy-board-item" style="display:flex;flex-direction:column;padding:12px;margin:6px 0;{bg_style}
                        border-radius:10px;border-left:{border_width} solid {color};
                        box-shadow:0 2px 8px rgba(0,0,0,0.06);transition:all 0.2s ease;">
                <div class="board-item-header" style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
                    <div style="display:flex;align-items:center;gap:8px;">
                        <span style="font-weight:600;color:#333;font-size:14px;">{r.strategy_name}</span>
                        <span style="display:inline-block;padding:1px 6px;border-radius:10px;font-size:10px;
                                    background:{color}22;color:{color};">{signal_label}</span>
                        <span style="display:inline-block;padding:1px 6px;border-radius:10px;font-size:10px;
                                    background:{'#dc354522' if importance == 'critical' else '#fd7e1422' if importance == 'high' else '#ffc10722' if importance == 'medium' else '#17a2b822'};
                                    color:{'#dc3545' if importance == 'critical' else '#fd7e14' if importance == 'high' else '#ffc107' if importance == 'medium' else '#17a2b8'};">
                            {'重要' if importance == 'critical' else '关注' if importance == 'high' else '中等' if importance == 'medium' else '普通'}
                        </span>
                    </div>
                    <div style="display:flex;align-items:center;gap:6px;">
                        <span style="font-size:11px;color:#999;white-space:nowrap;">{time_str}</span>
                    </div>
                </div>
                <div style="font-size:13px;color:#333;font-weight:500;margin-bottom:8px;">
                    {signal_detail['summary']}
                </div>
                {signal_highlights_html}
                <div class="board-item-detail" style="display:block;padding:8px 0 4px 0;">
                    {expanded_content}
                </div>
            </div>
        </div>
        """
        
        from pywebio.output import use_scope
        with use_scope("strategy_board", clear=True):
            ctx["put_html"](board_container)
        
        # 初始化已显示的结果ID
        global _shown_strategy_result_ids
        _shown_strategy_result_ids[entry_id] = set()
        _shown_strategy_result_ids[entry_id].add(r.id)
        
        # 启动自动刷新任务
        from pywebio.session import run_async
        run_async(_auto_refresh_strategy_board(ctx, entry_id, entry.name))
