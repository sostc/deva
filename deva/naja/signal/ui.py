"""
信号流模块 UI

提供实时信号流的展示和管理功能
使用 SSE 实时推送
"""

from datetime import datetime
from pywebio.output import use_scope, put_html

from .processor import get_signal_type, get_signal_detail, generate_expanded_content


def _signal_stream_client_js() -> str:
    """生成信号流 SSE 客户端 JS"""
    return '''
(function() {
    console.log('[Signal] 信号流 JS 执行');

    var source = null;
    var autoRefresh = true;

    function connect() {
        if (source) return;
        console.log('[Signal] 连接 SSE...');
        source = new EventSource('/api/signal/stream');

        source.onopen = function() {
            console.log('[Signal] SSE 连接已打开');
        };

        source.onmessage = function(event) {
            console.log('[Signal] onmessage 触发');
            if (!autoRefresh) return;
            try {
                var data = JSON.parse(event.data);
                console.log('[Signal] 收到数据:', data);
                updateSignalStream(data);
            } catch (e) {
                console.error('[Signal] 解析失败:', e);
            }
        };

        source.onerror = function(error) {
            console.error('[Signal] SSE 错误:', error);
        };
    }

    window.toggleSignalAutoRefresh = function(enabled) {
        autoRefresh = enabled;
        console.log('[Signal] 自动刷新:', enabled);
    };

    function getBusBadge(busType) {
        if (busType === 'cognitive') {
            return '<span style="display:inline-block;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:600;background:#6366f120;color:#6366f1;">🧠 认知</span>';
        } else if (busType === 'trading') {
            return '<span style="display:inline-block;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:600;background:#f59e0b20;color:#f59e0b;">💰 交易</span>';
        } else if (busType === 'hotspot') {
            return '<span style="display:inline-block;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:600;background:#ef444420;color:#ef4444;">🔥 热点</span>';
        } else if (busType === 'news') {
            return '<span style="display:inline-block;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:600;background:#3b82f620;color:#3b82f6;">📰 新闻</span>';
        }
        return '';
    }

    function getEventIcon(busType) {
        if (busType === 'hotspot') return '🔥';
        if (busType === 'news') return '📰';
        if (busType === 'trading') return '💰';
        if (busType === 'cognitive') return '🧠';
        return '📡';
    }

    function getImportanceColor(priority) {
        if (priority >= 0.7) return { color: '#dc3545', level: 'critical' };
        if (priority >= 0.5) return { color: '#fd7e14', level: 'high' };
        if (priority >= 0.3) return { color: '#ffc107', level: 'medium' };
        return { color: '#17a2b8', level: 'low' };
    }

    function formatTime(ts) {
        var d = new Date(ts * 1000);
        return d.getHours().toString().padStart(2, '0') + ':' + 
               d.getMinutes().toString().padStart(2, '0') + ':' + 
               d.getSeconds().toString().padStart(2, '0');
    }

    function escapeHtml(str) {
        if (!str) return '';
        return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    function formatEventData(data) {
        try {
            return JSON.stringify(data, null, 2);
        } catch (e) {
            return String(data);
        }
    }

    var displayedSignalIds = new Set();
    var displayedEventTimestamps = new Set();
    var isInitialLoad = true;

    function updateSignalStream(data) {
        var container = document.getElementById('signal-stream-container');
        if (!container) return;
        if (!data || typeof data !== 'object') return;

        if (isInitialLoad) {
            var allItems = [];
            
            if (Array.isArray(data.signals)) {
                data.signals.forEach(function(signal) {
                    allItems.push({
                        type: 'signal',
                        data: signal,
                        timestamp: signal.ts || signal.timestamp || 0
                    });
                });
            }
            
            if (Array.isArray(data.events)) {
                data.events.forEach(function(event) {
                    allItems.push({
                        type: 'event',
                        data: event,
                        timestamp: event.timestamp || 0
                    });
                });
            }
            
            allItems.sort(function(a, b) {
                return b.timestamp - a.timestamp;
            });
            
            allItems = allItems.slice(0, 30);
            
            var html = '';
            allItems.forEach(function(item) {
                if (item.type === 'signal') {
                    displayedSignalIds.add(item.data.id);
                    html += renderSignalItem(item.data);
                } else {
                    var ts = item.data.timestamp || 0;
                    displayedEventTimestamps.add(ts);
                    html += renderBusEventItem(item.data);
                }
            });
            
            if (!html) {
                html = '<div style="padding:20px;text-align:center;color:#999;background:#f9f9f9;border-radius:8px;">📡 等待数据...</div>';
            }
            container.innerHTML = html;
            
            isInitialLoad = false;
            
            initFilters();
        } else {
            var hasNewContent = false;
            var newItemsHtml = '';

            if (Array.isArray(data.signals)) {
                data.signals.forEach(function(signal) {
                    if (!displayedSignalIds.has(signal.id)) {
                        displayedSignalIds.add(signal.id);
                        newItemsHtml += renderSignalItem(signal);
                        hasNewContent = true;
                    }
                });
            }

            if (Array.isArray(data.events)) {
                data.events.forEach(function(event) {
                    var ts = event.timestamp || 0;
                    if (!displayedEventTimestamps.has(ts)) {
                        displayedEventTimestamps.add(ts);
                        newItemsHtml += renderBusEventItem(event);
                        hasNewContent = true;
                    }
                });
            }

            if (hasNewContent && newItemsHtml) {
                var existingContent = container.innerHTML;
                var emptyPlaceholder = '<div style="padding:20px;text-align:center;color:#999;background:#f9f9f9;border-radius:8px;">📡 等待数据...</div>';
                if (existingContent.indexOf(emptyPlaceholder) >= 0) {
                    existingContent = '';
                }
                container.innerHTML = newItemsHtml + existingContent;

                var items = container.querySelectorAll('.signal-item, .bus-event');
                if (items.length > 30) {
                    var itemsToRemove = Array.from(items).slice(30);
                    itemsToRemove.forEach(function(item) {
                        item.remove();
                    });
                }
                
                initFilters();
            }
        }
    }

    function renderSignalItem(signal) {
        try {
            if (!signal) return '';
            
            var priority = signal.priority || 0.5;
            var info = getImportanceColor(priority);
            var color = info.color;
            var level = info.level;

            var icon = signal.icon || '📊';
            var strategyName = escapeHtml(signal.strategy_name || 'Unknown');
            var timeStr = formatTime(signal.ts || signal.timestamp || 0);
            
            var outputFull = signal.output_full;
            var summary = '';
            var highlights = [];
            
            if (outputFull && typeof outputFull === 'object') {
                summary = escapeHtml(outputFull.summary || (signal.summary || ''));
                highlights = Array.isArray(outputFull.highlights) ? outputFull.highlights : [];
            } else {
                summary = escapeHtml(signal.summary || '');
            }

            if (summary.indexOf('0 个信号') >= 0) return '';

            var highlightsStr = highlights.slice(0, 4).join(' | ');

            var borderWidth = level === 'critical' ? '4px' : (level === 'high' ? '3px' : '2px');
            var bgStyle = 'background:linear-gradient(135deg,' + color + '11,' + color + '22);';

            var signalId = signal.id || '';
            var html = '<div class="signal-item" data-importance="' + level + '" data-type="signal" data-id="' + signalId + '" onclick="toggleSignalExpand(this)" style="display:flex;flex-direction:column;padding:0;margin:6px 0;' + bgStyle + 'border-radius:10px;border-left:' + borderWidth + ' solid ' + color + ';box-shadow:0 2px 8px rgba(0,0,0,0.06);cursor:pointer;">';
            html += '<div class="signal-header" style="display:flex;align-items:stretch;">';
            html += '<div style="display:flex;align-items:center;justify-content:center;padding:0 12px;"><div style="font-size:24px;">' + icon + '</div></div>';
            html += '<div style="flex:1;padding:10px 12px 10px 0;min-width:0;">';
            html += '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">';
            html += '<div style="display:flex;align-items:center;gap:8px;"><span style="font-weight:600;color:#333;font-size:14px;">' + strategyName.substring(0, 14) + '</span><span style="display:inline-block;padding:2px 6px;border-radius:10px;font-size:10px;background:' + color + '22;color:' + color + ';">' + level.toUpperCase() + '</span></div>';
            html += '<div style="display:flex;align-items:center;gap:6px;"><span style="font-size:11px;color:#999;white-space:nowrap;">' + timeStr + '</span><span class="expand-icon" style="font-size:10px;color:#999;transition:transform 0.2s;">▼</span></div>';
            html += '</div>';
            html += '<div style="font-size:13px;color:#333;font-weight:500;margin-bottom:2px;">' + summary + '</div>';
            if (highlightsStr) {
                html += '<div style="font-size:11px;color:#666;margin-top:4px;">' + escapeHtml(highlightsStr) + '</div>';
            }
            html += '</div></div>';
            
            // 展开详情
            var detailHtml = '<div class="signal-detail" style="display:none;padding:12px;border-top:1px solid #eee;background:rgba(255,255,255,0.5);border-radius:0 0 10px 10px;">';
            if (outputFull && typeof outputFull === 'object') {
                if (outputFull.symbol) {
                    detailHtml += '<div style="margin-bottom:8px;"><span style="color:#666;font-size:12px;">股票:</span> <span style="font-weight:600;color:#333;">' + escapeHtml(outputFull.symbol) + '</span></div>';
                }
                if (outputFull.type) {
                    detailHtml += '<div style="margin-bottom:8px;"><span style="color:#666;font-size:12px;">信号:</span> <span style="font-weight:600;color:' + (outputFull.type === 'buy' ? '#e67e22' : '#e74c3c') + ';">' + escapeHtml(outputFull.type.toUpperCase()) + '</span></div>';
                }
                if (outputFull.confidence !== undefined) {
                    detailHtml += '<div style="margin-bottom:8px;"><span style="color:#666;font-size:12px;">置信度:</span> <span style="color:#333;">' + (outputFull.confidence * 100).toFixed(1) + '%</span></div>';
                }
                if (highlights.length > 0) {
                    detailHtml += '<div style="margin-bottom:8px;"><span style="color:#666;font-size:12px;">亮点:</span> <span style="color:#333;">' + escapeHtml(highlights.join(' | ')) + '</span></div>';
                }
            }
            if (signal.metadata) {
                var meta = typeof signal.metadata === 'object' ? signal.metadata : JSON.parse(signal.metadata);
                if (meta && meta.scope) {
                    detailHtml += '<div style="margin-bottom:8px;"><span style="color:#666;font-size:12px;">范围:</span> <span style="color:#333;">' + escapeHtml(meta.scope) + '</span></div>';
                }
            }
            detailHtml += '</div>';
            html += detailHtml;
            
            html += '</div>';
            return html;
        } catch (e) {
            console.error('Error rendering signal item:', e, signal);
            return '';
        }
    }

    function renderBusEventItem(event) {
        try {
            var importanceInfo = getImportanceColor(event.importance || 0.5);
            var color = importanceInfo.color;
            var level = importanceInfo.level;
            var busType = event.bus_type || 'cognitive';

            var borderWidth = level === 'critical' ? '4px' : (level === 'high' ? '3px' : '2px');
            var bgStyle = 'background:linear-gradient(135deg,' + color + '11,' + color + '22);';
            var icon = getEventIcon(busType);

            var html = '<div class="bus-event" data-importance="' + level + '" data-type="' + busType + '" onclick="toggleSignalExpand(this)" style="display:flex;flex-direction:column;padding:0;margin:6px 0;' + bgStyle + 'border-radius:10px;border-left:' + borderWidth + ' solid ' + color + ';box-shadow:0 2px 8px rgba(0,0,0,0.06);cursor:pointer;">';
            html += '<div class="signal-header" style="display:flex;align-items:stretch;">';
            html += '<div style="display:flex;align-items:center;justify-content:center;padding:0 12px;"><div style="font-size:24px;">' + icon + '</div></div>';
            html += '<div style="flex:1;padding:10px 12px 10px 0;min-width:0;">';
            html += '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;flex-wrap:wrap;gap:8px;">';
            html += '<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">';
            html += getBusBadge(busType);
            html += '<span style="font-weight:600;color:#333;font-size:14px;">' + escapeHtml(event.event_type || 'Event') + '</span>';
            if (event.symbol) {
                html += '<span style="font-size:12px;color:#666;">🎯 ' + escapeHtml(event.symbol) + '</span>';
            }
            if (event.block && busType === 'hotspot') {
                html += '<span style="font-size:12px;color:#666;">📊 ' + escapeHtml(event.block) + '</span>';
            }
            html += '</div>';
            html += '<div style="display:flex;align-items:center;gap:6px;"><span style="font-size:11px;color:#999;white-space:nowrap;">' + formatTime(event.timestamp || 0) + '</span><span class="expand-icon" style="font-size:10px;color:#999;transition:transform 0.2s;">▼</span></div>';
            html += '</div>';
            if (event.summary) {
                html += '<div style="font-size:13px;color:#333;font-weight:500;margin-bottom:2px;">' + escapeHtml(event.summary) + '</div>';
            }
            if (busType === 'news' && event.sentiment_str) {
                html += '<div style="font-size:11px;color:#666;">情绪: ' + escapeHtml(event.sentiment_str) + '</div>';
            }
            if (busType === 'news' && event.topics && event.topics.length > 0) {
                var topicsStr = event.topics.slice(0, 5).map(function(t) { return '#' + escapeHtml(t); }).join(' ');
                html += '<div style="font-size:11px;color:#3b82f6;margin-top:4px;">' + topicsStr + '</div>';
            }
            if (busType === 'hotspot' && event.title) {
                html += '<div style="font-size:11px;color:#ef4444;margin-top:4px;">' + escapeHtml(event.title) + '</div>';
            }
            html += '</div></div>';

            // 展开后的详情
            html += '<div class="signal-detail" style="display:none;padding:12px 12px 12px 56px;border-top:1px solid rgba(0,0,0,0.1);">';
            html += '<pre style="background:#f9fafb;padding:10px;border-radius:8px;font-size:11px;overflow-x:auto;margin:0;color:#374151;">' + escapeHtml(formatEventData(event.data || event)) + '</pre>';
            html += '</div>';
            html += '</div>';
            return html;
        } catch (e) {
            console.error('Error rendering bus event:', e, event);
            return '';
        }
    }

    function applyFilters() {
        var items = document.querySelectorAll('.signal-item, .bus-event');
        var importanceFilters = {};
        var typeFilters = {};
        
        document.querySelectorAll('.signal-filter').forEach(function(c) {
            importanceFilters[c.value] = c.checked;
        });
        document.querySelectorAll('.type-filter').forEach(function(c) {
            typeFilters[c.value] = c.checked;
        });
        
        items.forEach(function(item) {
            var importance = item.getAttribute('data-importance');
            var itemType = item.getAttribute('data-type');
            
            var importanceMatch = importanceFilters[importance];
            var typeMatch = typeFilters[itemType];
            
            if (typeMatch === undefined) {
                typeMatch = true;
            }
            
            if (importanceMatch && typeMatch) {
                item.style.display = '';
            } else {
                item.style.display = 'none';
            }
        });
    }

    function initFilters() {
        var checkboxes = document.querySelectorAll('.signal-filter, .type-filter');
        checkboxes.forEach(function(cb) {
            cb.removeEventListener('change', applyFilters);
            cb.addEventListener('change', applyFilters);
        });
    }

    function init() {
        connect();
        initFilters();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
'''


async def render_signal_page(ctx: dict):
    """渲染信号流页面"""
    with use_scope("signal_stream", clear=True):
        ctx["put_html"](f"<script>{_signal_stream_client_js()}</script>")

        ctx["put_html"]('''
        <style>
            .signal-item:hover, .bus-event:hover { box-shadow: 0 4px 16px rgba(0,0,0,0.12) !important; }
            .signal-item.expanded .expand-icon, .bus-event.expanded .expand-icon { transform: rotate(180deg); }
            .signal-detail { animation: fadeIn 0.2s ease; }
            .signal-item.hidden, .bus-event.hidden { display: none !important; }
            @keyframes fadeIn {
                from { opacity: 0; }
                to { opacity: 1; }
            }
        </style>
        <div style="margin:16px 0 12px 0;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">
            <div style="font-size:15px;font-weight:600;color:#333;">🔥 实时信号流</div>
            <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
                <label style="display:flex;align-items:center;gap:4px;cursor:pointer;font-size:11px;">
                    <input type="checkbox" class="type-filter" value="signal" checked style="cursor:pointer;">
                    <span style="padding:2px 6px;background:#6b728022;color:#6b7280;border-radius:4px;">📊 信号</span>
                </label>
                <label style="display:flex;align-items:center;gap:4px;cursor:pointer;font-size:11px;">
                    <input type="checkbox" class="type-filter" value="news" checked style="cursor:pointer;">
                    <span style="padding:2px 6px;background:#3b82f622;color:#3b82f6;border-radius:4px;">📰 新闻</span>
                </label>
                <label style="display:flex;align-items:center;gap:4px;cursor:pointer;font-size:11px;">
                    <input type="checkbox" class="type-filter" value="hotspot" checked style="cursor:pointer;">
                    <span style="padding:2px 6px;background:#ef444422;color:#ef4444;border-radius:4px;">🔥 热点</span>
                </label>
                <label style="display:flex;align-items:center;gap:4px;cursor:pointer;font-size:11px;">
                    <input type="checkbox" class="type-filter" value="trading" checked style="cursor:pointer;">
                    <span style="padding:2px 6px;background:#f59e0b22;color:#f59e0b;border-radius:4px;">💰 交易</span>
                </label>
                <label style="display:flex;align-items:center;gap:4px;cursor:pointer;font-size:11px;">
                    <input type="checkbox" class="type-filter" value="cognitive" checked style="cursor:pointer;">
                    <span style="padding:2px 6px;background:#6366f122;color:#6366f1;border-radius:4px;">🧠 认知</span>
                </label>
                <div style="width:1px;height:16px;background:#e5e7eb;margin:0 4px;"></div>
                <label style="display:flex;align-items:center;gap:4px;cursor:pointer;font-size:11px;">
                    <input type="checkbox" class="signal-filter" value="critical" checked style="cursor:pointer;">
                    <span style="padding:2px 6px;background:#dc354522;color:#dc3545;border-radius:4px;">🔴 重要</span>
                </label>
                <label style="display:flex;align-items:center;gap:4px;cursor:pointer;font-size:11px;">
                    <input type="checkbox" class="signal-filter" value="high" checked style="cursor:pointer;">
                    <span style="padding:2px 6px;background:#fd7e1422;color:#fd7e14;border-radius:4px;">🟠 关注</span>
                </label>
                <label style="display:flex;align-items:center;gap:4px;cursor:pointer;font-size:11px;">
                    <input type="checkbox" class="signal-filter" value="medium" checked style="cursor:pointer;">
                    <span style="padding:2px 6px;background:#ffc10722;color:#ffc107;border-radius:4px;">🟡 中等</span>
                </label>
                <label style="display:flex;align-items:center;gap:4px;cursor:pointer;font-size:11px;">
                    <input type="checkbox" class="signal-filter" value="low" checked style="cursor:pointer;">
                    <span style="padding:2px 6px;background:#17a2b822;color:#17a2b8;border-radius:4px;">🔵 普通</span>
                </label>
                <label style="display:flex;align-items:center;gap:4px;cursor:pointer;font-size:11px;margin-left:12px;">
                    <input type="checkbox" id="auto_refresh_checkbox" checked onchange="window.toggleSignalAutoRefresh(this.checked)" style="cursor:pointer;">
                    <span style="font-size:11px;color:#666;">🔄 自动刷新</span>
                </label>
            </div>
        </div>
        <div id="signal-stream-container" style="padding:4px;background:#f5f7fa;border-radius:12px;">
            <div style="padding:20px;text-align:center;color:#999;background:#f9f9f9;border-radius:8px;">📡 等待数据...</div>
        </div>
        <script>
        function toggleSignalExpand(el) {
            var detail = el.querySelector('.signal-detail');
            var isExpanded = detail && detail.style.display !== 'none';

            document.querySelectorAll('.signal-item.expanded, .bus-event.expanded').forEach(function(item) {
                if (item !== el) {
                    item.classList.remove('expanded');
                    var d = item.querySelector('.signal-detail');
                    if (d) d.style.display = 'none';
                }
            });

            if (!detail) return;

            if (isExpanded) {
                detail.style.display = 'none';
                el.classList.remove('expanded');
            } else {
                detail.style.display = 'block';
                el.classList.add('expanded');
            }
        }
        </script>
        ''')
