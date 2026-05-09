"""
双总线事件流 UI - 整合认知总线和交易总线

提供统一的界面展示两条总线的实时事件流
"""

import time
from dataclasses import asdict
from typing import Dict, Any, List
from datetime import datetime

from pywebio.output import use_scope, put_html, put_markdown, put_row, put_text, put_code


def _dual_bus_client_js() -> str:
    """生成双总线事件流客户端 JS"""
    return '''
(function() {
    console.log('[DualBus] 双总线事件流 JS 执行');

    var source = null;
    var autoRefresh = true;
    var activeBus = 'all'; // 'all', 'cognitive', 'trading'
    var eventCounter = 0;
    var maxEvents = 100;

    function connect() {
        if (source) return;
        console.log('[DualBus] 连接 SSE...');
        source = new EventSource('/api/dual-bus/stream');

        source.onopen = function() {
            console.log('[DualBus] SSE 连接已打开');
        };

        source.onmessage = function(event) {
            console.log('[DualBus] onmessage 触发');
            if (!autoRefresh) return;
            try {
                var data = JSON.parse(event.data);
                console.log('[DualBus] 收到数据:', data);
                updateEventStream(data);
            } catch (e) {
                console.error('[DualBus] 解析失败:', e);
            }
        };

        source.onerror = function(error) {
            console.error('[DualBus] SSE 错误:', error);
        };
    }

    window.toggleAutoRefresh = function(enabled) {
        autoRefresh = enabled;
        console.log('[DualBus] 自动刷新:', enabled);
    };

    window.switchBus = function(bus) {
        activeBus = bus;
        console.log('[DualBus] 切换总线:', bus);
        
        // 更新按钮样式
        document.querySelectorAll('.bus-switch-btn').forEach(function(btn) {
            btn.classList.remove('active');
            if (btn.dataset.bus === bus) {
                btn.classList.add('active');
            }
        });
        
        // 过滤显示
        filterEvents();
    };

    window.clearEvents = function() {
        var container = document.getElementById('dual-bus-stream');
        if (container) {
            container.innerHTML = '<div style="padding:20px;text-align:center;color:#999;background:#f9f9f9;border-radius:8px;">事件流已清空，等待新事件...</div>';
        }
        eventCounter = 0;
        updateStats();
    };

    function getBusBadge(busType) {
        if (busType === 'cognitive') {
            return '<span style="display:inline-block;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:600;background:#6366f120;color:#6366f1;">🧠 认知</span>';
        } else if (busType === 'trading') {
            return '<span style="display:inline-block;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:600;background:#f59e0b20;color:#f59e0b;">💰 交易</span>';
        }
        return '';
    }

    function getImportanceColor(importance) {
        if (importance >= 0.8) return { color: '#ef4444', level: 'critical' };
        if (importance >= 0.6) return { color: '#f59e0b', level: 'high' };
        if (importance >= 0.4) return { color: '#10b981', level: 'medium' };
        return { color: '#6b7280', level: 'low' };
    }

    function formatTime(timestamp) {
        var d = new Date(timestamp * 1000);
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

    function updateEventStream(data) {
        var container = document.getElementById('dual-bus-stream');
        if (!container || !data.events) return;

        data.events.forEach(function(event) {
            // 过滤总线
            if (activeBus !== 'all' && event.bus_type !== activeBus) {
                return;
            }

            var importanceInfo = getImportanceColor(event.importance || 0.5);
            
            var eventId = 'event-' + (++eventCounter);
            
            var html = '<div id="' + eventId + '" class="bus-event" data-bus="' + event.bus_type + '" ' +
                       'style="display:flex;flex-direction:column;padding:12px;margin:8px 0;' +
                       'background:linear-gradient(135deg,' + importanceInfo.color + '10,#ffffff);' +
                       'border-radius:12px;border-left:4px solid ' + importanceInfo.color + ';' +
                       'box-shadow:0 2px 8px rgba(0,0,0,0.06);animation:slideIn 0.3s ease-out;">' +
                '<div style="display:flex;align-items:center;justify-content:space-between;gap:12px;">' +
                    '<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">' +
                        getBusBadge(event.bus_type) +
                        '<span style="font-weight:600;color:#1f2937;font-size:13px;">' + escapeHtml(event.event_type) + '</span>' +
                        '<span style="font-size:11px;color:#9ca3af;">' + formatTime(event.timestamp) + '</span>' +
                        '<span style="display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;background:' + importanceInfo.color + '15;color:' + importanceInfo.color + ';">' +
                            Math.round((event.importance || 0.5) * 100) + '%' +
                        '</span>' +
                    '</div>' +
                    '<button onclick="toggleEventExpand(\'' + eventId + '\')" ' +
                            'style="background:none;border:none;color:#9ca3af;cursor:pointer;padding:4px;">' +
                        '<span class="expand-icon">▼</span>' +
                    '</button>' +
                '</div>' +
                (event.summary ? '<div style="margin-top:8px;font-size:13px;color:#374151;">' + escapeHtml(event.summary) + '</div>' : '') +
                (event.symbol ? '<div style="margin-top:4px;font-size:12px;color:#6b7280;">🎯 ' + escapeHtml(event.symbol) + '</div>' : '') +
                '<div class="event-details" style="display:none;margin-top:12px;padding-top:12px;border-top:1px solid #e5e7eb;">' +
                    '<pre style="background:#f9fafb;padding:10px;border-radius:8px;font-size:11px;overflow-x:auto;margin:0;color:#374151;">' + 
                        escapeHtml(formatEventData(event.data)) + 
                    '</pre>' +
                '</div>' +
            '</div>';

            // 插入到顶部
            var placeholder = container.querySelector('.placeholder');
            if (placeholder) {
                placeholder.remove();
            }
            
            container.insertAdjacentHTML('afterbegin', html);
            
            // 限制数量
            var events = container.querySelectorAll('.bus-event');
            if (events.length > maxEvents) {
                events[events.length - 1].remove();
            }
        });

        updateStats();
    }

    window.toggleEventExpand = function(eventId) {
        var element = document.getElementById(eventId);
        if (!element) return;
        
        var details = element.querySelector('.event-details');
        var icon = element.querySelector('.expand-icon');
        
        if (details.style.display === 'none' || !details.style.display) {
            details.style.display = 'block';
            if (icon) icon.textContent = '▲';
        } else {
            details.style.display = 'none';
            if (icon) icon.textContent = '▼';
        }
    };

    function filterEvents() {
        var container = document.getElementById('dual-bus-stream');
        if (!container) return;
        
        var events = container.querySelectorAll('.bus-event');
        events.forEach(function(event) {
            var busType = event.dataset.bus;
            if (activeBus === 'all' || busType === activeBus) {
                event.style.display = 'flex';
            } else {
                event.style.display = 'none';
            }
        });
    }

    function updateStats() {
        var cognitiveCount = 0;
        var tradingCount = 0;
        
        var container = document.getElementById('dual-bus-stream');
        if (container) {
            var events = container.querySelectorAll('.bus-event');
            events.forEach(function(event) {
                if (event.dataset.bus === 'cognitive') cognitiveCount++;
                if (event.dataset.bus === 'trading') tradingCount++;
            });
        }
        
        var cognitiveEl = document.getElementById('cognitive-count');
        var tradingEl = document.getElementById('trading-count');
        var totalEl = document.getElementById('total-count');
        
        if (cognitiveEl) cognitiveEl.textContent = cognitiveCount;
        if (tradingEl) tradingEl.textContent = tradingCount;
        if (totalEl) totalEl.textContent = cognitiveCount + tradingCount;
    }

    function init() {
        connect();
        
        // 添加动画样式
        var style = document.createElement('style');
        style.textContent = `
            @keyframes slideIn {
                from {
                    opacity: 0;
                    transform: translateY(-10px);
                }
                to {
                    opacity: 1;
                    transform: translateY(0);
                }
            }
            .bus-switch-btn {
                transition: all 0.2s ease;
            }
            .bus-switch-btn.active {
                background: #3b82f6 !important;
                color: white !important;
            }
        `;
        document.head.appendChild(style);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
'''


async def render_dual_bus_stream(ctx: dict):
    """渲染双总线事件流页面"""
    with use_scope("dual_bus_stream", clear=True):
        ctx["put_html"](f"<script>{_dual_bus_client_js()}</script>")

        ctx["put_html"](
            """
        <div style="background:linear-gradient(135deg,#667eea08,#764ba208);padding:20px;border-radius:16px;margin-bottom:20px;">
            <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:16px;">
                <div>
                    <h2 style="margin:0;color:#1f2937;font-size:22px;">📡 双总线事件流</h2>
                    <p style="margin:8px 0 0 0;color:#6b7280;font-size:14px;">实时展示认知总线和交易总线的事件</p>
                </div>
                <div style="display:flex;gap:16px;align-items:center;">
                    <div style="text-align:center;padding:10px 20px;background:#ffffff;border-radius:12px;box-shadow:0 2px 8px rgba(0,0,0,0.06);">
                        <div style="font-size:24px;font-weight:700;color:#6366f1;" id="total-count">0</div>
                        <div style="font-size:12px;color:#6b7280;">总事件</div>
                    </div>
                    <div style="text-align:center;padding:10px 20px;background:#ffffff;border-radius:12px;box-shadow:0 2px 8px rgba(0,0,0,0.06);">
                        <div style="font-size:24px;font-weight:700;color:#6366f1;" id="cognitive-count">0</div>
                        <div style="font-size:12px;color:#6b7280;">🧠 认知</div>
                    </div>
                    <div style="text-align:center;padding:10px 20px;background:#ffffff;border-radius:12px;box-shadow:0 2px 8px rgba(0,0,0,0.06);">
                        <div style="font-size:24px;font-weight:700;color:#f59e0b;" id="trading-count">0</div>
                        <div style="font-size:12px;color:#6b7280;">💰 交易</div>
                    </div>
                </div>
            </div>
        </div>
        
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;flex-wrap:wrap;gap:12px;">
            <div style="display:flex;gap:8px;align-items:center;">
                <button class="bus-switch-btn active" data-bus="all" onclick="switchBus('all')" 
                        style="padding:8px 16px;border:none;border-radius:8px;cursor:pointer;background:#f3f4f6;color:#374151;font-weight:500;font-size:13px;">
                    全部
                </button>
                <button class="bus-switch-btn" data-bus="cognitive" onclick="switchBus('cognitive')" 
                        style="padding:8px 16px;border:none;border-radius:8px;cursor:pointer;background:#f3f4f6;color:#374151;font-weight:500;font-size:13px;">
                    🧠 认知总线
                </button>
                <button class="bus-switch-btn" data-bus="trading" onclick="switchBus('trading')" 
                        style="padding:8px 16px;border:none;border-radius:8px;cursor:pointer;background:#f3f4f6;color:#374151;font-weight:500;font-size:13px;">
                    💰 交易总线
                </button>
            </div>
            <div style="display:flex;gap:8px;align-items:center;">
                <label style="display:flex;align-items:center;gap:6px;cursor:pointer;font-size:13px;color:#6b7280;">
                    <input type="checkbox" id="auto-refresh-checkbox" checked onchange="toggleAutoRefresh(this.checked)" style="cursor:pointer;">
                    🔄 自动刷新
                </label>
                <button onclick="clearEvents()" 
                        style="padding:8px 12px;border:none;border-radius:8px;cursor:pointer;background:#fee2e2;color:#dc2626;font-weight:500;font-size:13px;">
                    🗑️ 清空
                </button>
            </div>
        </div>
        
        <div id="dual-bus-stream" style="padding:12px;background:#f9fafb;border-radius:12px;max-height:600px;overflow-y:auto;">
            <div class="placeholder" style="padding:30px;text-align:center;color:#9ca3af;background:#ffffff;border-radius:8px;">
                <div style="font-size:40px;margin-bottom:12px;">📡</div>
                <div style="font-size:16px;font-weight:500;margin-bottom:4px;">等待事件数据...</div>
                <div style="font-size:12px;color:#d1d5db;">事件将实时推送到此页面</div>
            </div>
        </div>
        """
        )
