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

    function getImportanceColor(priority) {
        if (priority >= 0.7) return { color: '#dc3545', level: 'critical' };
        if (priority >= 0.5) return { color: '#fd7e14', level: 'high' };
        if (priority >= 0.3) return { color: '#ffc107', level: 'medium' };
        return { color: '#17a2b8', level: 'low' };
    }

    function formatTime(ts) {
        var d = new Date(ts * 1000);
        return d.getHours().toString().padStart(2, '0') + ':' + d.getMinutes().toString().padStart(2, '0') + ':' + d.getSeconds().toString().padStart(2, '0');
    }

    function escapeHtml(str) {
        if (!str) return '';
        return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    function updateSignalStream(data) {
        var container = document.getElementById('signal-stream-container');
        if (!container || !data.signals) return;

        var filters = {};
        document.querySelectorAll('.signal-filter').forEach(function(cb) {
            filters[cb.value] = cb.checked;
        });

        var html = '';
        data.signals.slice(0, 15).forEach(function(signal) {
            var priority = signal.priority || 0.5;
            var info = getImportanceColor(priority);
            var color = info.color;
            var level = info.level;

            var icon = signal.icon || '📊';
            var strategyName = escapeHtml(signal.strategy_name || 'Unknown');
            var timeStr = formatTime(signal.ts || signal.timestamp || 0);
            var summary = escapeHtml(signal.output_full ? signal.output_full.summary : (signal.summary || ''));

            if (summary.indexOf('0 个信号') >= 0) return;

            var highlights = signal.output_full ? signal.output_full.highlights : [];
            var highlightsStr = highlights.slice(0, 4).join(' | ');

            var borderWidth = level === 'critical' ? '4px' : (level === 'high' ? '3px' : '2px');
            var bgStyle = 'background:linear-gradient(135deg,' + color + '11,' + color + '22);';

            html += '<div class="signal-item" data-importance="' + level + '" onclick="toggleSignalExpand(this)" style="display:flex;flex-direction:column;padding:0;margin:6px 0;' + bgStyle + 'border-radius:10px;border-left:' + borderWidth + ' solid ' + color + ';box-shadow:0 2px 8px rgba(0,0,0,0.06);cursor:pointer;">';
            html += '<div class="signal-header" style="display:flex;align-items:stretch;">';
            html += '<div style="display:flex;align-items:center;justify-content:center;padding:0 12px;"><div style="font-size:24px;">' + icon + '</div></div>';
            html += '<div style="flex:1;padding:10px 12px 10px 0;min-width:0;">';
            html += '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">';
            html += '<div style="display:flex;align-items:center;gap:8px;"><span style="font-weight:600;color:#333;font-size:14px;">' + strategyName.substring(0, 14) + '</span><span style="display:inline-block;padding:1px 6px;border-radius:10px;font-size:10px;background:' + color + '22;color:' + color + ';">' + level.toUpperCase() + '</span></div>';
            html += '<div style="display:flex;align-items:center;gap:6px;"><span style="font-size:11px;color:#999;white-space:nowrap;">' + timeStr + '</span><span class="expand-icon" style="font-size:10px;color:#999;transition:transform 0.2s;">▼</span></div>';
            html += '</div>';
            html += '<div style="font-size:13px;color:#333;font-weight:500;margin-bottom:2px;">' + summary + '</div>';
            if (highlightsStr) {
                html += '<div style="font-size:11px;color:#666;margin-top:4px;">' + escapeHtml(highlightsStr) + '</div>';
            }
            html += '</div></div></div>';
        });

        container.innerHTML = html;
    }

    function init() {
        connect();
        var checkboxes = document.querySelectorAll('.signal-filter');
        checkboxes.forEach(function(cb) {
            cb.addEventListener('change', function() {
                var items = document.querySelectorAll('.signal-item');
                var filters = {};
                document.querySelectorAll('.signal-filter').forEach(function(c) {
                    filters[c.value] = c.checked;
                });
                items.forEach(function(item) {
                    var importance = item.getAttribute('data-importance');
                    item.style.display = filters[importance] ? '' : 'none';
                });
            });
        });
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

        ctx["put_html"]("""
        <style>
            .signal-item:hover { box-shadow: 0 4px 16px rgba(0,0,0,0.12) !important; }
            .signal-item.expanded .expand-icon { transform: rotate(180deg); }
            .signal-detail { animation: fadeIn 0.2s ease; }
            .signal-item.hidden { display: none !important; }
            @keyframes fadeIn {
                from { opacity: 0; }
                to { opacity: 1; }
            }
        </style>
        <div style="margin:16px 0 12px 0;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">
            <div style="font-size:15px;font-weight:600;color:#333;">🔥 实时信号流</div>
            <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
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
            <div style="padding:20px;text-align:center;color:#999;background:#f9f9f9;border-radius:8px;">📡 等待信号数据...</div>
        </div>
        <script>
        function toggleSignalExpand(el) {
            var detail = el.querySelector('.signal-detail');
            var isExpanded = detail && detail.style.display !== 'none';

            document.querySelectorAll('.signal-item.expanded').forEach(function(item) {
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
        """)
