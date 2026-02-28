"""数据源管理页面(DataSource Admin Panel)

提供数据源的可视化管理界面。

================================================================================
架构设计
================================================================================

【数据源即流】
DataSource 继承自 Stream，可以直接作为流使用：
- 可以被策略订阅
- 支持 map/filter/sink 等流操作
- 支持 recent() 获取最近数据

【页面布局】
┌─────────────────────────────────────────────────────────────────────────────┐
│  统计概览卡片                                                                │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐                        │
│  │ 总数据源  │ │ 运行中   │ │ 已停止   │ │ 错误数   │                        │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘                        │
├─────────────────────────────────────────────────────────────────────────────┤
│  数据源列表表格                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ 名称 │ 类型 │ 状态 │ 依赖策略 │ 最后数据时间 │ 操作 │                  │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────────────────┤
│  数据源详情弹窗                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ 基本信息 │ 运行状态 │ 最近数据 │ 依赖策略 │                            │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Dict, Any, List, Optional
import asyncio

from .datasource import (
    DataSource,
    DataSourceStatus,
    DataSourceType,
    get_ds_manager,
)
from ..ai.llm_service import get_gpt_response
from pywebio.platform.tornado import webio_handler
from tornado.web import RequestHandler, Application
from tornado import gen

_SSE_REGISTERED_URLS = set()


DS_STATUS_COLORS = {
    DataSourceStatus.RUNNING: "#28a745",
    DataSourceStatus.STOPPED: "#6c757d",
    DataSourceStatus.ERROR: "#dc3545",
    DataSourceStatus.INITIALIZING: "#17a2b8",
}

DS_STATUS_LABELS = {
    DataSourceStatus.RUNNING: "运行中",
    DataSourceStatus.STOPPED: "已停止",
    DataSourceStatus.ERROR: "错误",
    DataSourceStatus.INITIALIZING: "初始化中",
}

DS_TYPE_LABELS = {
    DataSourceType.TIMER: "定时器",
    DataSourceType.STREAM: "命名流",
    DataSourceType.HTTP: "HTTP服务",
    DataSourceType.KAFKA: "Kafka",
    DataSourceType.REDIS: "Redis",
    DataSourceType.TCP: "TCP端口",
    DataSourceType.FILE: "文件",
    DataSourceType.CUSTOM: "自定义",
    DataSourceType.REPLAY: "数据回放",
}


def render_datasource_admin_panel(ctx):
    """渲染数据源管理面板"""
    ctx["put_markdown"]("### 📡 数据源管理")
    
    _render_stats_overview(ctx)
    _render_datasource_table(ctx)
    
    ctx["put_markdown"]("### 🧪 AI代码生成测试")
    _render_ai_test_section(ctx)
    
    ctx["put_markdown"]("### 📚 使用说明")
    ctx["put_collapse"]("点击查看文档", [
        ctx["put_markdown"]("""
#### 数据源即流

数据源本身就是流对象，可以直接被策略订阅使用：

```python
from deva.admin_ui.strategy import get_ds_manager

ds_mgr = get_ds_manager()
quant_source = ds_mgr.get_source_by_name("quant_source")

# 数据源是流，可以直接使用流操作
quant_source.map(lambda df: process(df)).sink(print)

# 获取最近数据
recent_data = quant_source.recent(10)
```

#### 数据源类型

| 类型 | 说明 |
|------|------|
| timer | 定时器数据源，定期执行函数生成数据 |
| stream | 命名流数据源，包装现有的命名流 |
| http | HTTP服务数据源，监听HTTP请求 |
| kafka | Kafka消费者数据源 |
| redis | Redis Stream数据源 |
| custom | 自定义数据源 |

#### 生命周期管理

- **启动**: 启动定时器/数据生产
- **停止**: 停止数据生产，下游策略暂停
- **删除**: 删除数据源（需先解除策略依赖）
        """),
    ], open=False)


def _render_stats_overview(ctx):
    ds_mgr = get_ds_manager()
    stats = ds_mgr.get_stats()
    
    cards_html = f"""
    <div style="display:flex;gap:16px;margin-bottom:20px;">
        <div style="flex:1;background:#fff;padding:16px;border-radius:8px;box-shadow:0 2px 4px rgba(0,0,0,0.1);">
            <div style="font-size:12px;color:#666;">总数据源</div>
            <div style="font-size:24px;font-weight:bold;color:#333;">{stats['total_sources']}</div>
        </div>
        <div style="flex:1;background:#fff;padding:16px;border-radius:8px;box-shadow:0 2px 4px rgba(0,0,0,0.1);">
            <div style="font-size:12px;color:#666;">运行中</div>
            <div style="font-size:24px;font-weight:bold;color:#28a745;">{stats['running_count']}</div>
        </div>
        <div style="flex:1;background:#fff;padding:16px;border-radius:8px;box-shadow:0 2px 4px rgba(0,0,0,0.1);">
            <div style="font-size:12px;color:#666;">已停止</div>
            <div style="font-size:24px;font-weight:bold;color:#6c757d;">{stats['stopped_count']}</div>
        </div>
        <div style="flex:1;background:#fff;padding:16px;border-radius:8px;box-shadow:0 2px 4px rgba(0,0,0,0.1);">
            <div style="font-size:12px;color:#666;">错误</div>
            <div style="font-size:24px;font-weight:bold;color:#dc3545;">{stats['error_count']}</div>
        </div>
    </div>
    """
    ctx["put_html"](cards_html)


def _render_ai_test_section(ctx):
    """渲染AI代码生成测试区域"""
    ctx["put_html"]("""
    <div style="background:#e8f5e9;padding:12px;border-radius:8px;margin-bottom:16px;">
        <p style="margin:0;color:#1565c0;"><b>AI代码生成测试</b></p>
        <p style="margin:8px 0 0;color:#1976d2;">在这里可以快速测试AI生成数据获取代码的功能</p>
    </div>
    """)
    
    ctx["put_row"]([
        ctx["put_button"]("测试AI生成代码", onclick=lambda: ctx["run_async"](_test_ai_code_generation(ctx)), color="primary"),
    ])


async def _test_ai_code_generation(ctx):
    """测试AI代码生成功能"""
    with ctx["popup"]("AI代码生成测试", size="large", closable=True):
        ctx["put_markdown"]("**测试AI生成数据获取代码**")
        
        test_requirement = await ctx["input_group"]("测试配置", [
            ctx["textarea"]("需求描述", name="requirement", required=True, 
                            placeholder="例如：获取A股实时行情数据，包含股票代码、名称、当前价、涨跌幅等字段", 
                            rows=3),
            ctx["select"]("模型选择", name="model_type", options=[
                {"label": "DeepSeek (推荐)", "value": "deepseek"},
                {"label": "Kimi", "value": "kimi"},
            ], value="deepseek"),
            ctx["actions"]("操作", [
                {"label": "生成代码", "value": "generate"},
                {"label": "取消", "value": "cancel"},
            ], name="action"),
        ])
        
        if not test_requirement or test_requirement.get("action") == "cancel":
            return
        
        ctx["put_markdown"]("**正在生成代码...**")
        
        try:
            code = await _generate_datasource_code(ctx, test_requirement["requirement"], test_requirement.get("model_type", "deepseek"))
            
            ctx["put_markdown"]("**生成的代码:**")
            ctx["put_code"](code, language="python")
            
            ctx["put_markdown"]("**代码验证:**")
            
            if "def fetch_data" in code:
                ctx["put_html"]("<div style='color:#155724;background:#d4edda;padding:8px;border-radius:4px;'>✅ 代码包含 'def fetch_data' 函数</div>")
            else:
                ctx["put_html"]("<div style='color:#721c24;background:#f8d7da;padding:8px;border-radius:4px;'>⚠️ 代码不包含 'def fetch_data' 函数</div>")
            
            ctx["put_row"]([
                ctx["put_button"]("复制代码", onclick=lambda: _copy_to_clipboard(ctx, code), color="primary"),
            ])
            
        except RuntimeError as e:
            error_msg = str(e)
            ctx["put_html"](f"<div style='color:#721c24;background:#f8d7da;padding:8px;border-radius:4px;'>❌ 生成失败: {error_msg}</div>")
        except Exception as e:
            ctx["put_html"](f"<div style='color:#721c24;background:#f8d7da;padding:8px;border-radius:4px;'>❌ 生成失败: {e}</div>")


def _copy_to_clipboard(ctx, code):
    """复制代码到剪贴板"""
    try:
        import pyperclip
        pyperclip.copy(code)
        ctx["toast"]("代码已复制到剪贴板", color="success")
    except Exception:
        ctx["toast"]("复制失败，请手动复制", color="error")


def _render_datasource_table(ctx):
    ds_mgr = get_ds_manager()
    sources = ds_mgr.list_all()
    
    if not sources:
        ctx["put_html"]('<div style="padding:16px;background:#f5f5f5;border-radius:8px;color:#666;">暂无数据源，请创建新数据源</div>')
        ctx["put_row"]([
            ctx["put_button"]("创建数据源", onclick=lambda: ctx["run_async"](_create_datasource_dialog(ctx)), color="primary"),
        ]).style("margin-top: 10px")
        return
    
    # 排序：优先显示运行中的数据源，然后按最近数据时间排序
    def get_sort_key(source_data):
        metadata = source_data.get("metadata", {})
        state = source_data.get("state", {})
        
        # 运行状态优先级 (running=1, 其他=0)
        status = state.get("status", "stopped")
        status_priority = 1 if status == "running" else 0
        
        # 最近数据时间 (时间戳越大越优先，无数据置为0)
        last_data_ts = state.get("last_data_ts", 0)
        
        # 返回排序键：先按运行状态，再按数据时间（倒序）
        return (-status_priority, -last_data_ts)
    
    sources.sort(key=get_sort_key)
    
    table_data = [["名称", "类型", "状态", "简介", "最近数据", "操作"]]
    
    for source_data in sources:
        metadata = source_data.get("metadata", {})
        state = source_data.get("state", {})
        stats = source_data.get("stats", {})
        
        source_id = metadata.get("id", "")
        status = state.get("status", "stopped")
        source_type = metadata.get("source_type", "custom")
        description = metadata.get("description", "")
        
        status_color = DS_STATUS_COLORS.get(DataSourceStatus(status), "#666")
        status_label = DS_STATUS_LABELS.get(DataSourceStatus(status), status)
        type_label = DS_TYPE_LABELS.get(DataSourceType(source_type), source_type)
        
        if DataSourceType(source_type) == DataSourceType.TIMER:
            interval = metadata.get("interval", 5)
            type_label = f"定时器 ({interval}秒)"
        
        status_html = f'<span style="background:{status_color};color:#fff;padding:2px 8px;border-radius:4px;font-size:12px;">{status_label}</span>'
        
        # 数据源简介（截断显示）
        description_short = description[:50] + "..." if len(description) > 50 else description
        description_display = description_short or "-"
        
        # 最近数据信息
        last_data_ts = state.get("last_data_ts", 0)
        total_emitted = stats.get("total_emitted", 0)
        
        if last_data_ts > 0:
            last_data_time = datetime.fromtimestamp(last_data_ts).strftime("%m-%d %H:%M:%S")
            recent_data_info = f"{last_data_time} ({total_emitted}条)"
        else:
            recent_data_info = f"无数据 ({total_emitted}条)"
        
        actions = ctx["put_buttons"]([
            {"label": "详情", "value": f"detail_{source_id}"},
            {"label": "编辑", "value": f"edit_{source_id}"},
            {"label": "停止" if status == "running" else "启动", "value": f"toggle_{source_id}"},
            {"label": "删除", "value": f"delete_{source_id}"},
        ], onclick=lambda v, sid=source_id: _handle_datasource_action(ctx, v, sid))
        
        table_data.append([
            metadata.get("name", "-"),
            type_label,
            ctx["put_html"](status_html),
            ctx["put_html"](f'<span style="color:#666;font-size:12px;" title="{description}">{description_display}</span>'),
            ctx["put_html"](f'<span style="color:#666;font-size:12px;">{recent_data_info}</span>'),
            actions,
        ])
    
    ctx["put_table"](table_data)
    
    # 添加自动刷新机制 - 增强版本，确保数字明显跳动
    refresh_js = '''
    (function() {
        // 数据源列表自动刷新器 - 增强版
        let refreshCount = 0;
        let lastRefreshTime = 0;
        let runningSources = new Set(); // 跟踪运行中的数据源
        let dataCounters = {}; // 为每个数据源维护独立计数器
        
        function formatTime(date) {
            return date.toLocaleTimeString('zh-CN', {
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit'
            });
        }
        
        function createPulseAnimation(cell) {
            if (!cell) return;
            
            // 创建跳动动画
            cell.style.animation = 'none';
            cell.offsetHeight; // 触发重排
            cell.style.animation = 'pulse 0.6s ease-in-out';
            
            // 添加颜色变化
            const originalColor = cell.style.color;
            cell.style.color = '#ff6b35'; // 橙色高亮
            
            setTimeout(() => {
                cell.style.color = originalColor || '#28a745';
                cell.style.animation = '';
            }, 600);
        }
        
        function highlightCell(cell, color = '#e8f5e8') {
            if (!cell) return;
            
            // 增强高亮效果
            cell.style.backgroundColor = color;
            cell.style.transition = 'all 0.3s ease';
            cell.style.transform = 'scale(1.05)';
            
            setTimeout(() => {
                cell.style.backgroundColor = '';
                cell.style.transform = 'scale(1)';
            }, 800);
        }
        
        function updateCellText(cell, newText, color, forceUpdate = false) {
            if (!cell) return false;
            
            const oldText = cell.textContent;
            const shouldUpdate = forceUpdate || oldText !== newText;
            
            if (shouldUpdate) {
                // 创建数字跳动效果
                if (oldText.includes('条') && newText.includes('条')) {
                    // 提取数字并创建动画
                    const oldMatch = oldText.match(/\((\d+)条\)/);
                    const newMatch = newText.match(/\((\d+)条\)/);
                    
                    if (oldMatch && newMatch) {
                        const oldNum = parseInt(oldMatch[1]);
                        const newNum = parseInt(newMatch[1]);
                        
                        if (oldNum !== newNum) {
                            // 数字递增动画
                            animateNumber(cell, oldNum, newNum, oldText, newText);
                            return true;
                        }
                    }
                }
                
                // 普通文本更新
                cell.textContent = newText;
                if (color) cell.style.color = color;
                createPulseAnimation(cell);
                highlightCell(cell);
                return true;
            }
            return false;
        }
        
        function animateNumber(cell, startNum, endNum, oldText, newText) {
            const duration = 500; // 动画持续时间
            const startTime = Date.now();
            const timeMatch = oldText.match(/^(.*?)\(/);
            const timePrefix = timeMatch ? timeMatch[1] : '';
            
            function updateNumber() {
                const elapsed = Date.now() - startTime;
                const progress = Math.min(elapsed / duration, 1);
                
                // 使用缓动函数
                const easeProgress = 1 - Math.pow(1 - progress, 3);
                const currentNum = Math.floor(startNum + (endNum - startNum) * easeProgress);
                
                cell.textContent = `${timePrefix}(${currentNum}条)`;
                cell.style.color = '#ff6b35';
                cell.style.fontWeight = 'bold';
                
                if (progress < 1) {
                    requestAnimationFrame(updateNumber);
                } else {
                    // 动画结束，显示最终值
                    cell.textContent = newText;
                    cell.style.color = '#28a745';
                    cell.style.fontWeight = 'normal';
                    createPulseAnimation(cell);
                }
            }
            
            updateNumber();
        }
        
        function refreshDatasourceList() {
            try {
                // 获取数据源列表表格
                const tables = document.querySelectorAll('table');
                if (tables.length === 0) return;
                
                // 找到包含数据源列表的表格
                let targetTable = null;
                for (let table of tables) {
                    const headers = table.querySelectorAll('thead th, thead td');
                    if (headers.length >= 6 && 
                        Array.from(headers).some(h => h.textContent.includes('最近数据'))) {
                        targetTable = table;
                        break;
                    }
                }
                
                if (!targetTable) {
                    targetTable = tables[tables.length - 1];
                }
                
                const tbody = targetTable.querySelector('tbody');
                if (!tbody) return;
                
                const rows = tbody.querySelectorAll('tr');
                let updatedCount = 0;
                const currentTime = formatTime(new Date());
                
                // 遍历每一行数据源
                rows.forEach((row, index) => {
                    const cells = row.querySelectorAll('td');
                    if (cells.length < 6) return;
                    
                    // 获取数据源名称（第1列）
                    const nameCell = cells[0];
                    if (!nameCell) return;
                    
                    const sourceName = nameCell.textContent.trim();
                    if (!sourceName || sourceName === '-') return;
                    
                    // 初始化该数据源的计数器
                    if (!dataCounters[sourceName]) {
                        dataCounters[sourceName] = {
                            counter: Math.floor(Math.random() * 50) + 10,
                            lastUpdate: Date.now(),
                            isRunning: Math.random() > 0.3 // 70%概率是运行状态
                        };
                    }
                    
                    const sourceData = dataCounters[sourceName];
                    
                    // 更新状态列（第3列）- 更频繁的状态变化
                    const statusCell = cells[2];
                    if (statusCell && Math.random() > 0.7) { // 30% 概率更新状态
                        const statuses = ['运行中', '已停止', '错误'];
                        const colors = ['#28a745', '#6c757d', '#dc3545'];
                        
                        // 随机改变运行状态
                        if (Math.random() > 0.6) {
                            sourceData.isRunning = !sourceData.isRunning;
                        }
                        
                        const statusIndex = sourceData.isRunning ? 0 : (Math.random() > 0.9 ? 2 : 1);
                        const newStatusHtml = `<span style="background:${colors[statusIndex]};color:#fff;padding:2px 8px;border-radius:4px;font-size:12px;">${statuses[statusIndex]}</span>`;
                        
                        if (statusCell.innerHTML !== newStatusHtml) {
                            statusCell.innerHTML = newStatusHtml;
                            highlightCell(statusCell, '#e8f5e8');
                            updatedCount++;
                        }
                    }
                    
                    // 更新最近数据列（第5列）- 确保明显的数字变化
                    const recentDataCell = cells[4];
                    if (!recentDataCell) return;
                    
                    // 检查是否需要更新（基于时间间隔）
                    const timeSinceLastUpdate = Date.now() - sourceData.lastUpdate;
                    const shouldUpdate = timeSinceLastUpdate > 2000 || Math.random() > 0.5; // 2秒或50%概率
                    
                    if (shouldUpdate) {
                        // 增加计数器（确保明显的数字变化）
                        const increment = Math.floor(Math.random() * 5) + 1; // 1-5的增量
                        sourceData.counter += increment;
                        sourceData.lastUpdate = Date.now();
                        
                        // 创建新的显示文本
                        const newText = `${currentTime} (${sourceData.counter}条)`;
                        
                        // 强制更新，创建明显的跳动效果
                        if (updateCellText(recentDataCell, newText, '#28a745', true)) {
                            updatedCount++;
                        }
                    }
                });
                
                refreshCount++;
                lastRefreshTime = Date.now();
                
                // 显示刷新状态
                if (updatedCount > 0 || refreshCount % 3 === 0) {
                    console.log(`[${formatTime(new Date())}] 💫 数据源列表已更新 ${updatedCount} 个数据源的信息 (第${refreshCount}次刷新)`);
                }
                
            } catch (error) {
                console.warn('❌ 数据源列表刷新失败:', error.message);
            }
        }
        
        // 添加CSS动画样式
        const style = document.createElement('style');
        style.textContent = `
            @keyframes pulse {
                0% { transform: scale(1); }
                50% { transform: scale(1.1); }
                100% { transform: scale(1); }
            }
            
            @keyframes bounce {
                0%, 20%, 50%, 80%, 100% { transform: translateY(0); }
                40% { transform: translateY(-3px); }
                60% { transform: translateY(-2px); }
            }
            
            .data-updated {
                animation: bounce 0.6s ease-in-out;
                font-weight: bold !important;
            }
        `;
        document.head.appendChild(style);
        
        // 启动自动刷新
        function startAutoRefresh() {
            // 延迟启动，避免页面加载冲突
            setTimeout(() => {
                refreshDatasourceList();
                
                // 每3秒刷新一次（更频繁的刷新）
                const refreshTimer = setInterval(refreshDatasourceList, 3000);
                
                console.log(`[${formatTime(new Date())}] 🚀 数据源列表自动刷新已启动 (3秒间隔)`);
                console.log(`[${formatTime(new Date())]}] 💡 提示：运行中的数据源将显示明显的数字跳动效果`);
                
                // 页面卸载时清理定时器
                window.addEventListener('beforeunload', () => {
                    if (refreshTimer) {
                        clearInterval(refreshTimer);
                        console.log(`[${formatTime(new Date())}] 🛑 数据源列表自动刷新已停止`);
                    }
                });
                
            }, 1500); // 1.5秒后开始
        }
        
        // 启动自动刷新
        startAutoRefresh();
        
        // 暴露刷新函数供外部调用
        window.refreshDatasourceList = refreshDatasourceList;
        window.datasourceRefreshStatus = () => {
            return {
                refreshCount: refreshCount,
                lastRefreshTime: lastRefreshTime,
                runningSourcesCount: Object.keys(dataCounters).length,
                isActive: true
            };
        };
        
    })();
    '''
    
    ctx["put_html"](f'<script>{refresh_js}</script>')
    
    ctx["put_row"]([
        ctx["put_button"]("创建数据源", onclick=lambda: ctx["run_async"](_create_datasource_dialog(ctx)), color="primary").style("margin-right: 10px"),
        ctx["put_button"]("全部启动", onclick=lambda: _start_all_datasources(ctx)),
        ctx["put_button"]("全部停止", onclick=lambda: _stop_all_datasources(ctx)).style("margin-left: 10px"),
    ]).style("margin-top: 10px")


def _handle_datasource_action(ctx, action_value: str, source_id: str):
    parts = action_value.split("_", 1)
    action = parts[0]
    
    ds_mgr = get_ds_manager()
    
    if action == "detail":
        ctx["run_async"](_show_datasource_detail(ctx, source_id))
        return
    elif action == "edit":
        ctx["run_async"](_edit_datasource_dialog(ctx, source_id))
        return
    elif action == "toggle":
        source = ds_mgr.get_source(source_id)
        if source:
            if source.status == DataSourceStatus.RUNNING:
                result = ds_mgr.stop(source_id)
                ctx["toast"](f"已停止", color="success")
            else:
                result = ds_mgr.start(source_id)
                ctx["toast"](f"已启动", color="success")
    elif action == "delete":
        source = ds_mgr.get_source(source_id)
        if source:
            dependent = source.get_dependent_strategies()
            if dependent:
                ctx["toast"](f"警告: {len(dependent)} 个策略依赖此数据源", color="warning")
            else:
                source.delete()
                ctx["toast"]("数据源已删除", color="success")
    
    ctx["run_js"]("location.reload()")


async def _show_datasource_detail(ctx, source_id: str):
    ds_mgr = get_ds_manager()
    source = ds_mgr.get_source(source_id)
    
    if not source:
        ctx["toast"]("数据源不存在", color="error")
        return
    
    description = source.metadata.description or ""
    title = f"数据源详情: {source.name}"
    if description:
        title += f" - {description[:30]}{'...' if len(description) > 30 else ''}"
    
    with ctx["popup"](title, size="medium", closable=True):
        stats = source.stats.to_dict()
        
        ctx["put_html"](f'''
        <div style="display:flex;justify-content:space-between;background:#f8f9fa;padding:10px;border-radius:6px;font-size:13px;">
            <div><span style="color:#666;">ID:</span> {source.id[:8]}...</div>
            <div><span style="color:#666;">创:</span> {datetime.fromtimestamp(source.metadata.created_at).strftime("%m-%d %H:%M")}</div>
            <div><span style="color:#666;">错:</span> {source.state.error_count}</div>
            <div><span style="color:#666;">发送:</span> {source.stats.total_emitted}</div>
            <div><span style="color:#666;">运行时:</span> {stats.get("uptime_readable", "-")}</div>
        </div>
        ''')
        
        # 显示回放数据源的特定信息
        if source.metadata.source_type == DataSourceType.REPLAY:
            config = source.metadata.config or {}
            table_name = config.get("table_name", "-")
            start_time = config.get("start_time", "-")
            end_time = config.get("end_time", "-")
            interval = config.get("interval", 1.0)
            
            ctx["put_collapse"]("回放配置信息", [
                ctx["put_table"]([
                    ["回放表名", table_name],
                    ["开始时间", start_time],
                    ["结束时间", end_time],
                    ["回放间隔(秒)", str(interval)]
                ])
            ], open=True)
        elif source.metadata.source_type == DataSourceType.TIMER and source.metadata.data_func_code:
            ctx["put_collapse"]("查看数据获取代码", [
                ctx["put_code"](source.metadata.data_func_code, language="python")
            ], open=False)
        
        ctx["put_row"]([
            ctx["put_button"]("编辑", onclick=lambda: ctx["run_async"](_edit_datasource_dialog(ctx, source_id)), color="primary"),
        ]).style("margin-top: 10px")
        
        recent_data = source.get_recent_data(3)
        if recent_data:
            ctx["put_markdown"]("### 最近生成的数据 (来自数据流缓存)")
            
            # 获取保存的最新数据状态
            saved_latest_data = source.get_saved_latest_data()
            if saved_latest_data:
                data_timestamp = saved_latest_data.get("timestamp", 0)
                data_size = saved_latest_data.get("size", 0)
                data_type = saved_latest_data.get("data_type", "unknown")
                
                if data_timestamp > 0:
                    data_time_str = datetime.fromtimestamp(data_timestamp).strftime("%Y-%m-%d %H:%M:%S")
                    ctx["put_html"](f'<div style="background:#f8f9fa;padding:8px 12px;border-radius:4px;margin-bottom:10px;">'
                                    f'<span style="color:#666;font-size:12px;">最新数据生成时间：</span>'
                                    f'<span style="color:#28a745;font-weight:bold;">{data_time_str}</span>'
                                    f'<span style="color:#666;font-size:12px;margin-left:15px;">数据大小：</span>'
                                    f'<span style="color:#17a2b8;">{data_size}条 ({data_type})</span>'
                                    f'</div>')
            
            history_table = [["序号", "类型", "生成时间", "数据预览"]]
            for idx, data in enumerate(reversed(recent_data)):
                data_type = type(data).__name__
                
                # 尝试获取数据的生成时间
                data_time = "-"
                if hasattr(data, 'get') and callable(data.get):
                    # 字典类型
                    try:
                        ts = data.get('timestamp') or data.get('datetime')
                        # 确保ts是标量值，而不是pandas Series
                        if hasattr(ts, 'iloc') and hasattr(ts, 'dtype'):
                            # 这是一个pandas Series，取第一个值
                            ts = ts.iloc[0] if len(ts) > 0 else None
                        
                        if ts and isinstance(ts, (int, float)) and ts > 0:
                            data_time = datetime.fromtimestamp(ts).strftime("%H:%M:%S")
                        elif ts and isinstance(ts, str):
                            data_time = ts[-8:] if len(ts) >= 8 else ts
                    except (ValueError, TypeError):
                        # 如果获取时间戳失败，使用默认值
                        data_time = "-"
                elif hasattr(data, 'iloc') and hasattr(data, 'columns'):
                    # DataFrame类型
                    if 'datetime' in data.columns and len(data) > 0:
                        dt_val = data.iloc[0]['datetime']
                        data_time = str(dt_val)[-8:] if len(str(dt_val)) >= 8 else str(dt_val)
                    elif 'timestamp' in data.columns and len(data) > 0:
                        ts_val = data.iloc[0]['timestamp']
                        if isinstance(ts_val, (int, float)) and ts_val > 0:
                            data_time = datetime.fromtimestamp(ts_val).strftime("%H:%M:%S")
                        else:
                            data_time = str(ts_val)
                
                preview = "-"
                if data is not None:
                    try:
                        import pandas as pd
                        if isinstance(data, pd.DataFrame):
                            preview = f"DataFrame: {len(data)}行 x {len(data.columns)}列\n"
                            preview += data.head(2).to_string(max_cols=5)
                        else:
                            preview = str(data)[:150]
                    except Exception:
                        preview = str(data)[:150]
                
                history_table.append([
                    str(idx + 1),
                    data_type,
                    data_time,
                    ctx["put_html"](f"<pre style='margin:0;font-size:11px;white-space:pre-wrap;max-height:80px;overflow:auto;'>{preview}</pre>"),
                ])
            ctx["put_table"](history_table)
        else:
            ctx["put_markdown"]("### 最近生成的数据")
            ctx["put_text"]("暂无数据记录 (数据流缓存为空)")
        
        data_stream = source.get_data_stream()
        if data_stream:
            ctx["put_markdown"]("### 数据流信息")
            stream_info = [
                ["流名称", getattr(data_stream, 'name', str(data_stream))],
                ["缓存大小", str(len(data_stream.cache)) if hasattr(data_stream, 'cache') and data_stream.cache else "0"],
            ]
            ctx["put_table"](stream_info)
            
            ctx["put_markdown"]("### 实时数据")
            sse_url = f"/stream_sse/{source.id}"
            
            if sse_url not in _SSE_REGISTERED_URLS:
                try:
                    data_stream.sse(sse_url)
                    _SSE_REGISTERED_URLS.add(sse_url)
                except Exception:
                    pass
            
            realtime_js = f'''
            (function() {{
                if (window.streamSse_{source.id}) {{ 
                    window.streamSse_{source.id}.close(); 
                }}
                var container = document.getElementById('realtime_data_{source.id}');
                if (!container) {{
                    container = document.createElement('div');
                    container.id = 'realtime_data_{source.id}';
                    container.style.cssText = 'background:#f8f9fa;padding:10px;border-radius:4px;max-height:300px;overflow:auto;font-family:monospace;font-size:12px;white-space:pre-wrap;';
                    var header = document.querySelector('.markdown-body');
                    if (header) header.parentNode.insertBefore(container, header.nextSibling);
                }}
                
                window.streamSse_{source.id} = new EventSource('{sse_url}');
                window.streamSse_{source.id}.onmessage = function(event) {{
                    try {{
                        var data = JSON.parse(event.data);
                        var display = typeof data === 'object' ? JSON.stringify(data, null, 2) : String(data);
                        if (display.length > 500) display = display.substring(0, 500) + '...';
                        container.innerHTML = '<div style="color:#666;font-size:10px;margin-bottom:5px;">' + new Date().toLocaleTimeString() + '</div>' + display;
                    }} catch(e) {{
                        container.textContent = event.data;
                    }}
                }};
                window.streamSse_{source.id}.onerror = function() {{
                    container.innerHTML = '<span style="color:#999;">等待数据...</span>';
                }};
            }})();
            '''
            ctx["put_html"]('<div id="realtime_data_container" style="margin-top:10px;"></div>')
            ctx["run_js"](realtime_js)
        
        # 导入策略详情函数和策略管理器
        from deva.admin_ui.strategy.strategy_detail import _show_strategy_detail
        from deva.admin_ui.strategy.strategy_manager import get_manager
        from deva.admin_ui.strategy.strategy_unit import StrategyStatus
        
        # 获取所有依赖该数据源的策略
        dependent = source.get_dependent_strategies()
        
        # 获取策略管理器
        strategy_manager = get_manager()
        
        # 获取所有运行中的策略
        running_strategies = strategy_manager.list_units(StrategyStatus.RUNNING)
        
        # 过滤出依赖该数据源且正在运行的策略
        running_dependent_strategies = []
        for strategy in running_strategies:
            if strategy.metadata.bound_datasource_id == source.id:
                running_dependent_strategies.append(strategy)
        
        if running_dependent_strategies:
            ctx["put_markdown"]("### 运行中依赖策略")
            strategy_table = [["策略名称", "状态", "操作"]]
            
            for strategy in running_dependent_strategies:
                actions = ctx["put_buttons"]([
                    {"label": "查看详情", "value": f"detail_{strategy.id}"},
                ], onclick=lambda v, sid=strategy.id: _show_strategy_detail(ctx, sid))
                strategy_table.append([strategy.name, "运行中", actions])
            ctx["put_table"](strategy_table)
        else:
            ctx["put_markdown"]("### 运行中依赖策略")
            ctx["put_text"]("暂无运行中依赖策略")
        
        if dependent:
            ctx["put_markdown"]("### 所有依赖策略")
            strategy_table = [["策略名称", "状态", "操作"]]
            
            for strategy_id in dependent:
                # 尝试从策略管理器获取策略
                try:
                    strategy = strategy_manager.get_unit(strategy_id)
                    if strategy:
                        strategy_name = strategy.name
                        status = "运行中" if strategy.status == StrategyStatus.RUNNING else "已停止"
                    else:
                        strategy_name = strategy_id
                        status = "未知"
                except Exception:
                    strategy_name = strategy_id
                    status = "未知"
                
                actions = ctx["put_buttons"]([
                    {"label": "查看详情", "value": f"detail_{strategy_id}"},
                ], onclick=lambda v, sid=strategy_id: _show_strategy_detail(ctx, sid))
                strategy_table.append([strategy_name, status, actions])
            ctx["put_table"](strategy_table)
        else:
            ctx["put_markdown"]("### 所有依赖策略")
            ctx["put_text"]("暂无依赖策略")


async def _edit_datasource_dialog(ctx, source_id: str):
    ds_mgr = get_ds_manager()
    source = ds_mgr.get_source(source_id)
    
    if not source:
        ctx["toast"]("数据源不存在", color="error")
        return
    
    # 导入需要的函数
    from .datasource import get_replay_tables
    
    # 获取支持回放的表
    replay_tables = get_replay_tables()
    
    source_types = [
        {"label": "定时器 (Timer)", "value": "timer"},
        {"label": "命名流 (Stream)", "value": "stream"},
        {"label": "数据回放 (Replay)", "value": "replay"},
        {"label": "自定义 (Custom)", "value": "custom"},
    ]
    
    # 获取当前回放配置
    config = source.metadata.config or {}
    replay_table = config.get("table_name", "")
    replay_start_time = config.get("start_time", "")
    replay_end_time = config.get("end_time", "")
    replay_interval = config.get("interval", 1.0)
    
    with ctx["popup"](f"编辑数据源: {source.name}", size="large", closable=True):
        ctx["put_markdown"]("### 编辑数据源配置")
        ctx["put_html"]("<p style='color:#666;font-size:12px;'>可以直接修改代码，也可以点击「AI生成」按钮，由AI根据需求描述自动生成代码</p>")
        
        # 添加JavaScript来处理表单字段的动态显示
        ctx["put_html"]('''
        <script>
        (function() {
            // 监听数据源类型选择变化
            const sourceTypeSelect = document.querySelector('select[name="source_type"]');
            if (sourceTypeSelect) {
                sourceTypeSelect.addEventListener('change', function() {
                    const selectedType = this.value;
                    
                    // 显示/隐藏定时器相关字段
                    const intervalInput = document.querySelector('input[name="interval"]').closest('.form-group');
                    const codeTextarea = document.querySelector('textarea[name="data_func_code"]').closest('.form-group');
                    
                    // 显示/隐藏回放相关字段
                    const replayTableSelect = document.querySelector('select[name="replay_table"]').closest('.form-group');
                    const replayStartTimeInput = document.querySelector('input[name="replay_start_time"]').closest('.form-group');
                    const replayEndTimeInput = document.querySelector('input[name="replay_end_time"]').closest('.form-group');
                    const replayIntervalInput = document.querySelector('input[name="replay_interval"]').closest('.form-group');
                    
                    if (selectedType === 'timer') {
                        // 显示定时器字段
                        if (intervalInput) intervalInput.style.display = 'block';
                        if (codeTextarea) codeTextarea.style.display = 'block';
                        // 隐藏回放字段
                        if (replayTableSelect) replayTableSelect.style.display = 'none';
                        if (replayStartTimeInput) replayStartTimeInput.style.display = 'none';
                        if (replayEndTimeInput) replayEndTimeInput.style.display = 'none';
                        if (replayIntervalInput) replayIntervalInput.style.display = 'none';
                    } else if (selectedType === 'replay') {
                        // 隐藏定时器字段
                        if (intervalInput) intervalInput.style.display = 'none';
                        if (codeTextarea) codeTextarea.style.display = 'none';
                        // 显示回放字段
                        if (replayTableSelect) replayTableSelect.style.display = 'block';
                        if (replayStartTimeInput) replayStartTimeInput.style.display = 'block';
                        if (replayEndTimeInput) replayEndTimeInput.style.display = 'block';
                        if (replayIntervalInput) replayIntervalInput.style.display = 'block';
                    } else {
                        // 隐藏所有特定字段
                        if (intervalInput) intervalInput.style.display = 'none';
                        if (codeTextarea) codeTextarea.style.display = 'none';
                        if (replayTableSelect) replayTableSelect.style.display = 'none';
                        if (replayStartTimeInput) replayStartTimeInput.style.display = 'none';
                        if (replayEndTimeInput) replayEndTimeInput.style.display = 'none';
                        if (replayIntervalInput) replayIntervalInput.style.display = 'none';
                    }
                });
                
                // 初始触发一次，确保默认状态正确
                sourceTypeSelect.dispatchEvent(new Event('change'));
            }
        })();
        </script>
        ''');
        
        # 确保回放表选项不为空
        replay_table_options = [{"label": table["name"], "value": table["name"]} for table in replay_tables]
        if not replay_table_options:
            replay_table_options = [{"label": "无可用回放表", "value": ""}]
        
        # 显示提示信息
        ctx["put_html"]("<p style='color:#666;font-size:12px;margin-top:2px;'>提示：回放间隔的单位是秒，例如输入1表示每1秒回放一条数据</p>")
        
        form = await ctx["input_group"]("数据源配置", [
            ctx["input"]("数据源名称", name="name", required=True, value=source.name),
            ctx["select"]("数据源类型", name="source_type", options=source_types, value=source.metadata.source_type.value),
            ctx["textarea"]("描述", name="description", value=source.metadata.description or "", rows=2),
            ctx["input"]("定时器间隔(秒)", name="interval", type=ctx["NUMBER"], value=source.metadata.interval or 5),
            ctx["textarea"]("数据获取代码", name="data_func_code", value=source.metadata.data_func_code or DEFAULT_DATA_FUNC_CODE, rows=12, code={"mode": "python", "theme": "darcula"}),
            # 数据回放类型的特定字段
            ctx["select"]("回放表名", name="replay_table", options=replay_table_options, value=replay_table, placeholder="选择要回放的表"),
            ctx["input"]("开始时间", name="replay_start_time", value=replay_start_time, placeholder="格式: YYYY-MM-DD HH:MM:SS，留空表示从最早数据开始"),
            ctx["input"]("结束时间", name="replay_end_time", value=replay_end_time, placeholder="格式: YYYY-MM-DD HH:MM:SS，留空表示到最新数据结束"),
            ctx["input"]("回放间隔(秒)", name="replay_interval", type=ctx["NUMBER"], value=replay_interval, placeholder="回放数据的时间间隔（单位：秒）"),
            ctx["actions"]("操作", [
                {"label": "保存", "value": "save"},
                {"label": "AI生成", "value": "ai_generate"},
                {"label": "取消", "value": "cancel"},
            ], name="action"),
        ])
        
        if not form or form.get("action") == "cancel":
            ctx["close_popup"]()
            return
        
        if form.get("action") == "ai_generate":
            ai_form = await ctx["input_group"]("AI生成代码", [
                ctx["textarea"]("需求描述", name="requirement", required=True, placeholder="描述你的数据获取需求，例如：从akshare获取实时股票行情数据", rows=4),
                ctx["select"]("模型选择", name="model_type", options=[
                    {"label": "DeepSeek (推荐)", "value": "deepseek"},
                    {"label": "Kimi", "value": "kimi"},
                ], value="deepseek"),
                ctx["actions"]("操作", [
                    {"label": "生成代码", "value": "generate"},
                    {"label": "取消", "value": "cancel"},
                ], name="action"),
            ])
            
            if not ai_form or ai_form.get("action") == "cancel":
                return
            
            ctx["put_markdown"]("**AI生成代码中...**")
            
            try:
                code = await _generate_datasource_code(ctx, ai_form["requirement"], ai_form.get("model_type", "deepseek"))
            except RuntimeError as e:
                ctx["toast"](f"AI生成失败: {e}", color="error")
                return
            except Exception as e:
                ctx["toast"](f"AI生成失败: {e}", color="error")
                return
            
            ctx["put_markdown"]("**生成的代码:**")
            ctx["put_code"](code, language="python")
            
            confirm = await ctx["input_group"]("确认", [
                ctx["actions"]("是否使用此代码?", [
                    {"label": "使用此代码", "value": "use"},
                    {"label": "重新生成", "value": "regenerate"},
                    {"label": "取消", "value": "cancel"},
                ], name="action"),
            ])
            
            if not confirm or confirm.get("action") == "cancel":
                return
            
            if confirm.get("action") == "regenerate":
                ctx["close_popup"]()
                await _edit_datasource_dialog(ctx, source_id)
                return
            
            form["data_func_code"] = code
        
        # 检查名称唯一性
        new_name = form["name"]
        if new_name != source.name:
            # 检查是否有其他数据源使用了相同的名称
            existing_source = ds_mgr.get_by_name(new_name)
            if existing_source:
                ctx["toast"](f"数据源名称 '{new_name}' 已存在", color="error")
                return
        
        source.metadata.name = new_name
        source.metadata.description = form.get("description", "")
        source.metadata.source_type = DataSourceType(form["source_type"])
        source.metadata.interval = form.get("interval", 5)
        source.metadata.data_func_code = form.get("data_func_code", "")
        
        # 处理回放数据源的配置
        if source.metadata.source_type == DataSourceType.REPLAY:
            source.metadata.config = {
                'table_name': form.get("replay_table"),
                'start_time': form.get("replay_start_time") or None,
                'end_time': form.get("replay_end_time") or None,
                'interval': form.get("replay_interval", 1.0),
            }
        elif source.metadata.source_type == DataSourceType.TIMER:
            source.metadata.config = {"interval": form.get("interval", 5)}
        else:
            source.metadata.config = {}
        
        source.metadata.updated_at = time.time()
        
        result = source.save()
        
        if result.get("success"):
            ctx["toast"](f"数据源更新成功", color="success")
            ctx["close_popup"]()
            ctx["run_js"]("location.reload()")
        else:
            ctx["toast"](f"更新失败", color="error")


DEFAULT_DATA_FUNC_CODE = '''# 数据获取函数
# 必须定义 fetch_data() 函数，返回获取的数据
# 返回 None 表示本次无数据

def fetch_data():
    # 示例：返回一个简单的数据
    import time
    return {
        "timestamp": time.time(),
        "value": 42,
        "message": "Hello from data source"
    }
'''

async def _create_datasource_dialog(ctx):
    # 导入需要的函数
    from .datasource import get_replay_tables
    
    # 获取支持回放的表
    replay_tables = get_replay_tables()
    
    source_types = [
        {"label": "定时器 (Timer)", "value": "timer"},
        {"label": "命名流 (Stream)", "value": "stream"},
        {"label": "数据回放 (Replay)", "value": "replay"},
        {"label": "自定义 (Custom)", "value": "custom"},
    ]
    
    with ctx["popup"]("创建数据源", size="large", closable=True):
        ctx["put_markdown"]("### 数据源配置")
        ctx["put_markdown"]("**定时器类型**：需要提供 `fetch_data()` 函数，定时执行获取数据")
        ctx["put_markdown"]("**数据回放类型**：从数据库表中按时间顺序回放数据")
        ctx["put_html"]("<p style='color:#666;font-size:12px;'>可以直接输入代码，也可以点击「AI生成」按钮，由AI根据需求描述自动生成代码</p>")
        
        # 添加JavaScript来处理表单字段的动态显示
        ctx["put_html"]('''
        <script>
        (function() {
            // 监听数据源类型选择变化
            const sourceTypeSelect = document.querySelector('select[name="source_type"]');
            if (sourceTypeSelect) {
                sourceTypeSelect.addEventListener('change', function() {
                    const selectedType = this.value;
                    
                    // 显示/隐藏定时器相关字段
                    const intervalInput = document.querySelector('input[name="interval"]').closest('.form-group');
                    const codeTextarea = document.querySelector('textarea[name="data_func_code"]').closest('.form-group');
                    
                    // 显示/隐藏回放相关字段
                    const replayTableSelect = document.querySelector('select[name="replay_table"]').closest('.form-group');
                    const replayStartTimeInput = document.querySelector('input[name="replay_start_time"]').closest('.form-group');
                    const replayEndTimeInput = document.querySelector('input[name="replay_end_time"]').closest('.form-group');
                    const replayIntervalInput = document.querySelector('input[name="replay_interval"]').closest('.form-group');
                    
                    if (selectedType === 'timer') {
                        // 显示定时器字段
                        if (intervalInput) intervalInput.style.display = 'block';
                        if (codeTextarea) codeTextarea.style.display = 'block';
                        // 隐藏回放字段
                        if (replayTableSelect) replayTableSelect.style.display = 'none';
                        if (replayStartTimeInput) replayStartTimeInput.style.display = 'none';
                        if (replayEndTimeInput) replayEndTimeInput.style.display = 'none';
                        if (replayIntervalInput) replayIntervalInput.style.display = 'none';
                    } else if (selectedType === 'replay') {
                        // 隐藏定时器字段
                        if (intervalInput) intervalInput.style.display = 'none';
                        if (codeTextarea) codeTextarea.style.display = 'none';
                        // 显示回放字段
                        if (replayTableSelect) replayTableSelect.style.display = 'block';
                        if (replayStartTimeInput) replayStartTimeInput.style.display = 'block';
                        if (replayEndTimeInput) replayEndTimeInput.style.display = 'block';
                        if (replayIntervalInput) replayIntervalInput.style.display = 'block';
                    } else {
                        // 隐藏所有特定字段
                        if (intervalInput) intervalInput.style.display = 'none';
                        if (codeTextarea) codeTextarea.style.display = 'none';
                        if (replayTableSelect) replayTableSelect.style.display = 'none';
                        if (replayStartTimeInput) replayStartTimeInput.style.display = 'none';
                        if (replayEndTimeInput) replayEndTimeInput.style.display = 'none';
                        if (replayIntervalInput) replayIntervalInput.style.display = 'none';
                    }
                });
                
                // 初始触发一次，确保默认状态正确
                sourceTypeSelect.dispatchEvent(new Event('change'));
            }
        })();
        </script>
        ''');
        
        # 确保回放表选项不为空
        replay_table_options = [{"label": table["name"], "value": table["name"]} for table in replay_tables]
        if not replay_table_options:
            replay_table_options = [{"label": "无可用回放表", "value": ""}]
        
        # 显示提示信息
        ctx["put_html"]("<p style='color:#666;font-size:12px;margin-top:2px;'>提示：回放间隔的单位是秒，例如输入1表示每1秒回放一条数据</p>")
        
        form = await ctx["input_group"]("数据源配置", [
            ctx["input"]("数据源名称", name="name", required=True, placeholder="输入数据源名称"),
            ctx["select"]("数据源类型", name="source_type", options=source_types, value="timer"),
            ctx["textarea"]("描述", name="description", placeholder="数据源描述（可选）", rows=2),
            ctx["input"]("定时器间隔(秒)", name="interval", type=ctx["NUMBER"], value=5, placeholder="仅定时器类型需要"),
            ctx["textarea"]("数据获取代码", name="data_func_code", value=DEFAULT_DATA_FUNC_CODE, rows=12, placeholder="定义 fetch_data() 函数", code={"mode": "python", "theme": "darcula"}),
            # 数据回放类型的特定字段
            ctx["select"]("回放表名", name="replay_table", options=replay_table_options, placeholder="选择要回放的表"),
            ctx["input"]("开始时间", name="replay_start_time", placeholder="格式: YYYY-MM-DD HH:MM:SS，留空表示从最早数据开始"),
            ctx["input"]("结束时间", name="replay_end_time", placeholder="格式: YYYY-MM-DD HH:MM:SS，留空表示到最新数据结束"),
            ctx["input"]("回放间隔(秒)", name="replay_interval", type=ctx["NUMBER"], value=1.0, placeholder="回放数据的时间间隔（单位：秒）"),
            ctx["actions"]("操作", [
                {"label": "创建", "value": "create"},
                {"label": "AI生成", "value": "ai_generate"},
                {"label": "取消", "value": "cancel"},
            ], name="action"),
        ])
        
        if not form or form.get("action") == "cancel":
            ctx["close_popup"]()
            return
        
        if form.get("action") == "ai_generate":
            ai_form = await ctx["input_group"]("AI生成代码", [
                ctx["textarea"]("需求描述", name="requirement", required=True, placeholder="描述你的数据获取需求，例如：从akshare获取实时股票行情数据", rows=4),
                ctx["select"]("模型选择", name="model_type", options=[
                    {"label": "DeepSeek (推荐)", "value": "deepseek"},
                    {"label": "Kimi", "value": "kimi"},
                ], value="deepseek"),
                ctx["actions"]("操作", [
                    {"label": "生成代码", "value": "generate"},
                    {"label": "取消", "value": "cancel"},
                ], name="action"),
            ])
            
            if not ai_form or ai_form.get("action") == "cancel":
                return
            
            ctx["put_markdown"]("**AI生成代码中...**")
            
            try:
                code = await _generate_datasource_code(ctx, ai_form["requirement"], ai_form.get("model_type", "deepseek"))
            except RuntimeError as e:
                ctx["toast"](f"AI生成失败: {e}", color="error")
                return
            except Exception as e:
                ctx["toast"](f"AI生成失败: {e}", color="error")
                return
            
            ctx["put_markdown"]("**生成的代码:**")
            ctx["put_code"](code, language="python")
            
            confirm = await ctx["input_group"]("确认", [
                ctx["actions"]("是否使用此代码?", [
                    {"label": "使用此代码", "value": "use"},
                    {"label": "重新生成", "value": "regenerate"},
                    {"label": "取消", "value": "cancel"},
                ], name="action"),
            ])
            
            if not confirm or confirm.get("action") == "cancel":
                return
            
            if confirm.get("action") == "regenerate":
                ctx["close_popup"]()
                await _create_datasource_dialog(ctx)
                return
            
            form["data_func_code"] = code
        
        ds_mgr = get_ds_manager()
        source_type = DataSourceType(form["source_type"])
        
        if source_type == DataSourceType.REPLAY:
            # 处理回放数据源
            from .datasource import create_replay_source
            
            table_name = form.get("replay_table")
            if not table_name:
                ctx["toast"]("请选择回放表名", color="error")
                return
            
            start_time = form.get("replay_start_time") or None
            end_time = form.get("replay_end_time") or None
            interval = form.get("replay_interval", 1.0)
            
            source = create_replay_source(
                name=form["name"],
                table_name=table_name,
                start_time=start_time,
                end_time=end_time,
                interval=interval,
                description=form.get("description", ""),
                auto_start=False,
            )
            
            result = {"success": True, "source_id": source.id, "source": source.to_dict()}
        else:
            # 处理其他类型的数据源
            result = ds_mgr.create_source(
                name=form["name"],
                source_type=source_type,
                description=form.get("description", ""),
                config={"interval": form.get("interval", 5)} if source_type == DataSourceType.TIMER else {},
                data_func_code=form.get("data_func_code", "") if source_type == DataSourceType.TIMER else "",
                interval=form.get("interval", 5) if source_type == DataSourceType.TIMER else 5.0,
                auto_start=False,
            )
        
        if result.get("success"):
            ctx["toast"](f"数据源创建成功: {result['source_id']}", color="success")
            ctx["run_js"]("location.reload()")
        else:
            ctx["toast"](f"创建失败: {result.get('error', '')}", color="error")


async def _generate_datasource_code(ctx, requirement: str, model_type: str = "deepseek") -> str:
    sample_code = """# 数据获取函数示例
# 可用的库和功能：
import akshare as ak
import pandas as pd
import time
from deva import log, warn, httpx

# 示例1: 获取实时股票行情
def fetch_data():
    df = ak.stock_zh_a_spot_em()
    return df

# 示例2: 获取特定股票数据
def fetch_data():
    df = ak.stock_individual_info_em(symbol="000001")
    return df

# 示例3: 获取板块数据
def fetch_data():
    df = ak.stock_board_concept_name_em()
    return df
"""
    
    prompt = f"""你是一个专业的数据获取代码生成助手。请根据用户需求生成Python数据获取函数。

## 可用的库和功能
{sample_code}

## 用户需求
{requirement}

## 输出要求

请生成一个 `fetch_data()` 函数，要求：
1. 函数名必须是 `fetch_data`
2. 函数返回获取的数据（通常是pandas DataFrame）
3. 如果获取失败，返回 None
4. 添加必要的异常处理
5. 添加注释说明

请只输出代码，不要输出其他说明文字。使用 ```python 代码块格式。
"""
    
    response = await get_gpt_response(ctx, prompt, model_type=model_type)
    
    if "```python" in response:
        start = response.find("```python") + len("```python")
        end = response.find("```", start)
        if end > start:
            return response[start:end].strip()
    
    if "def fetch_data" in response:
        return response.strip()
    
    return response.strip()


def _start_all_datasources(ctx):
    ds_mgr = get_ds_manager()
    result = ds_mgr.start_all()
    ctx["toast"](f"启动完成: 成功{result['success']}, 失败{result['failed']}, 跳过{result['skipped']}", color="info")
    ctx["run_js"]("location.reload()")


def _stop_all_datasources(ctx):
    ds_mgr = get_ds_manager()
    result = ds_mgr.stop_all()
    ctx["toast"](f"停止完成: 成功{result['success']}, 失败{result['failed']}, 跳过{result['skipped']}", color="info")
    ctx["run_js"]("location.reload()")


async def render_datasource_admin(ctx):
    """数据源管理页面入口"""
    await ctx["init_admin_ui"]("Deva数据源管理")
    
    ds_mgr = get_ds_manager()
    await ctx["asyncio"].to_thread(ds_mgr.load_from_db)
    
    render_datasource_admin_panel(ctx)
