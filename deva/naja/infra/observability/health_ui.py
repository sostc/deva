"""统一系统健康监控 UI

将系统健康、性能监控、循环审计、调优监控等功能整合到一个统一的页面中。
"""

import html as _html
from typing import Any, List, Optional, Sequence

from .health import get_health_check_manager, HealthStatus
from .system_monitor_ui import render_monitor_panel
from .performance_ui import render_performance_page
from .loop_audit_ui import render_loop_audit_page


# ── tab 切换 ──────────────────────────────────────────────────────────
#
# 走 run_js 而不是把 <script> 塞进 put_html：put_html 的内容由前端以 DOM
# 片段方式插入，片段里的 <script> 是否被执行取决于插入手法（innerHTML /
# insertAdjacentHTML 都不执行），run_js 是前端 eval，确定一定执行。
_TAB_JS = """
window.showTab = function (tabId, event) {
    var root = document.getElementById('tab-content');
    if (root) {
        root.querySelectorAll(':scope > div').forEach(function (d) {
            d.style.display = 'none';
        });
    }
    var target = document.getElementById(tabId);
    if (target) { target.style.display = 'block'; }

    var bar = document.getElementById('health-tab-bar');
    if (bar) {
        bar.querySelectorAll('button').forEach(function (btn) {
            btn.style.background = '#f1f5f9';
            btn.style.color = '#64748b';
        });
    }
    if (event && event.target) {
        event.target.style.background = '#ffffff';
        event.target.style.color = '#374151';
    }
};
"""


def _markdown_to_html(md: str) -> str:
    """把 markdown 转成 HTML，供缓冲渲染用。

    PyWebIO 的 put_markdown 是在浏览器端用 marked.js 渲染的；缓冲渲染需要
    在 Python 侧先转成 HTML 才能拼进同一份文档，这里用 Python 的 markdown
    库取近似结果（本站只用到标题、粗体这类基本语法）。没装该库时退化成
    转义纯文本，不让整块面板因为少个依赖挂掉。
    """
    text = md.strip("\n")
    if not text:
        return ""
    try:
        import markdown as _md  # type: ignore

        return _md.markdown(text, extensions=["extra"])
    except Exception:
        return f"<pre>{_html.escape(text)}</pre>"


def _table_to_html(tdata: Sequence[Sequence[Any]], header: Optional[Sequence[Any]] = None) -> str:
    """把 put_table 的行列数据渲染成 HTML 表格。"""
    border = "border: 1px solid #e5e7eb; padding: 8px 12px; text-align: left;"
    parts = [
        '<table style="width: 100%; border-collapse: collapse; '
        'margin: 8px 0 16px 0; font-size: 13px; color: #374151;">'
    ]
    if header:
        cells = "".join(f'<th style="{border} background: #f9fafb;">{_html.escape(str(c))}</th>' for c in header)
        parts.append(f"<thead><tr>{cells}</tr></thead>")
    body_rows = []
    for row in tdata:
        cells = "".join(f'<td style="{border}">{_html.escape(str(c))}</td>' for c in row)
        body_rows.append(f"<tr>{cells}</tr>")
    parts.append(f"<tbody>{''.join(body_rows)}</tbody></table>")
    return "".join(parts)


class BufferedRenderContext:
    """把整份仪表盘拼成一个完整 HTML 后再一次性输出。

    PyWebIO 的每次 put_html 都作为**独立 DOM 片段**插入，片段里若有未闭合
    标签，浏览器解析时会自动补闭合。health_ui 原本把 `<div id="tab-content">`
    和 `<div id="overview">` 拆在两次调用里、且都不闭合，于是两个容器都被
    建成空壳立刻收口，后面的面板内容全掉到外面成了 tab-content 的兄弟节点
    —— tab 按钮只是在几个空 div 上切 display，视觉上就是五个区块纵向堆叠、
   页面被拉得极长。

    把面板产出的片段全部攒起来、最后合成一份结构良好的 HTML 只调一次
    put_html，标签配对关系就不会被打断。performance_ui / loop_audit_ui 内部
    那些跨调用拆标签的写法也随之一起被拼好。

    非输出类调用（init_naja_ui、run_js 等）直接透传给真实上下文。
    """

    _BUFFERED = ("put_html", "put_text", "put_markdown", "put_table")

    def __init__(self, real_ctx: dict):
        self._real = real_ctx
        self._parts: List[str] = []

    # ── dict 兼容：让既有 `ctx["xxx"]` 写法不用改 ─────────────────────
    def __contains__(self, key: str) -> bool:
        return key in self._real

    def keys(self):
        return self._real.keys()

    def __iter__(self):
        return iter(self._real)

    def get(self, key: str, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def __getitem__(self, key: str):
        if key in self._BUFFERED:
            return getattr(self, "_buf_" + key)
        try:
            return self._real[key]
        except KeyError:
            raise KeyError(f"渲染上下文里没有 {key!r}") from None

    # ── 被缓冲的输出方法 ──────────────────────────────────────────────
    def _buf_put_html(self, content: Any, *_args, **_kwargs) -> None:
        self._parts.append("" if content is None else str(content))

    def _buf_put_text(self, *args, **_kwargs) -> None:
        self._parts.append(f"<div>{_html.escape(' '.join(str(a) for a in args))}</div>")

    def _buf_put_markdown(self, mdcontent: str, *_args, **_kwargs) -> None:
        self._parts.append(_markdown_to_html(str(mdcontent)))

    def _buf_put_table(self, tdata, header=None, *_args, **_kwargs) -> None:
        self._parts.append(_table_to_html(tdata or (), header))

    # ── 输出 ──────────────────────────────────────────────────────────
    @property
    def buffered_html(self) -> str:
        """当前攒下来的完整 HTML 片段（调试 / 断言用）。"""
        return "".join(self._parts)

    def flush(self) -> None:
        """把攒下来的内容一次性输出。"""
        if self._parts:
            self._real["put_html"](self.buffered_html)
            self._parts.clear()


def _render_health_check_panel(ctx: dict):
    """渲染健康检查面板"""
    try:
        manager = get_health_check_manager()
        overall = manager.get_overall_status()
        reports = manager.check_all()
        
        status_icon = {
            HealthStatus.HEALTHY: "✅",
            HealthStatus.DEGRADED: "⚠️",
            HealthStatus.UNHEALTHY: "❌",
            HealthStatus.UNKNOWN: "❓"
        }.get(overall.status, "❓")
        
        status_color = {
            HealthStatus.HEALTHY: "#16a34a",
            HealthStatus.DEGRADED: "#f59e0b",
            HealthStatus.UNHEALTHY: "#dc2626",
            HealthStatus.UNKNOWN: "#64748b"
        }.get(overall.status, "#64748b")
        
        ctx["put_html"](f"""
        <div style="margin: 24px 0;">
            <h2 style="font-size: 20px; font-weight: 700; color: #1e293b; margin-bottom: 16px;">
                🩺 健康检查中心
            </h2>
        </div>
        """)
        
        # 总体状态卡片
        ctx["put_html"](f"""
        <div style="padding: 20px; border-radius: 12px; background: linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%); border: 1px solid #cbd5e1; margin-bottom: 24px;">
            <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 12px;">
                <span style="font-size: 24px;">{status_icon}</span>
                <div>
                    <div style="font-size: 16px; font-weight: 600; color: {status_color};">{overall.status.value.upper()}</div>
                    <div style="font-size: 13px; color: #64748b;">{overall.message}</div>
                </div>
            </div>
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 12px;">
                <div style="text-align: center; padding: 8px;">
                    <div style="font-size: 18px; font-weight: 700; color: #16a34a;">{overall.details.get('healthy', 0)}</div>
                    <div style="font-size: 11px; color: #64748b;">健康</div>
                </div>
                <div style="text-align: center; padding: 8px;">
                    <div style="font-size: 18px; font-weight: 700; color: #f59e0b;">{overall.details.get('degraded', 0)}</div>
                    <div style="font-size: 11px; color: #64748b;">降级</div>
                </div>
                <div style="text-align: center; padding: 8px;">
                    <div style="font-size: 18px; font-weight: 700; color: #dc2626;">{overall.details.get('unhealthy', 0)}</div>
                    <div style="font-size: 11px; color: #64748b;">不健康</div>
                </div>
                <div style="text-align: center; padding: 8px;">
                    <div style="font-size: 18px; font-weight: 700; color: #3b82f6;">{overall.details.get('total', 0)}</div>
                    <div style="font-size: 11px; color: #64748b;">总组件</div>
                </div>
            </div>
        </div>
        """)
        
        # 组件健康状态列表
        if reports:
            ctx["put_html"]("""
            <div style="margin-bottom: 24px;">
                <h3 style="font-size: 16px; font-weight: 600; color: #374151; margin-bottom: 12px;">组件健康状态</h3>
            </div>
            """)
            
            rows = []
            for component, report in reports.items():
                icon = status_icon = {
                    HealthStatus.HEALTHY: "✅",
                    HealthStatus.DEGRADED: "⚠️",
                    HealthStatus.UNHEALTHY: "❌",
                    HealthStatus.UNKNOWN: "❓"
                }.get(report.status, "❓")
                
                color = status_color = {
                    HealthStatus.HEALTHY: "#16a34a",
                    HealthStatus.DEGRADED: "#f59e0b",
                    HealthStatus.UNHEALTHY: "#dc2626",
                    HealthStatus.UNKNOWN: "#64748b"
                }.get(report.status, "#64748b")
                
                row = f"""
                <div style="display: flex; align-items: center; padding: 12px 16px; border-bottom: 1px solid #f3f4f6; gap: 12px;">
                    <div style="font-size: 18px;">{icon}</div>
                    <div style="flex: 1;">
                        <div style="font-weight: 600; color: #1f2937;">{component}</div>
                        <div style="font-size: 12px; color: #64748b; margin-top: 2px;">{report.message}</div>
                    </div>
                    <div style="font-size: 13px; font-weight: 600; color: {color};">{report.status.value}</div>
                </div>
                """
                rows.append(row)
            
            ctx["put_html"](f"""
            <div style="border-radius: 12px; border: 1px solid #e5e7eb; overflow: hidden;">
                <div style="padding: 12px 16px; background: #f9fafb; border-bottom: 1px solid #e5e7eb;">
                    <span style="font-weight: 600; color: #374151;">组件状态</span>
                </div>
                <div style="max-height: 300px; overflow-y: auto;">
                    {''.join(rows)}
                </div>
            </div>
            """)
    except Exception as e:
        ctx["put_html"](f"""
        <div style="padding: 20px; border-radius: 12px; background: #fef2f2; border: 1px solid #fecaca; margin-bottom: 24px;">
            <div style="color: #dc2626; font-size: 14px;">⚠️ 健康检查加载失败: {str(e)[:100]}</div>
        </div>
        """)


async def render_health_dashboard(ctx: dict):
    """渲染统一健康监控仪表盘

    面板内容必须拼成**一份** HTML 再输出 —— 原因与 tab 容器的嵌套结构有关，
    见 BufferedRenderContext 的 docstring。因此这里全程对缓冲上下文渲染，
    init_naja_ui（页面框架）除外，它要先于内容出现在页面上。
    """
    await ctx["init_naja_ui"]("系统健康")

    buf = BufferedRenderContext(ctx)

    # 顶部导航标签
    buf["put_html"]("""
    <div style="margin-bottom: 24px;">
        <div id="health-tab-bar" style="display: flex; gap: 4px; background: #f1f5f9; padding: 4px; border-radius: 8px;">
            <button onclick="showTab('overview', event)" style="flex: 1; padding: 8px 16px; border: none; border-radius: 6px; background: #ffffff; font-weight: 600; color: #374151; cursor: pointer;">总览</button>
            <button onclick="showTab('system', event)" style="flex: 1; padding: 8px 16px; border: none; border-radius: 6px; background: #f1f5f9; color: #64748b; cursor: pointer;">系统监控</button>
            <button onclick="showTab('performance', event)" style="flex: 1; padding: 8px 16px; border: none; border-radius: 6px; background: #f1f5f9; color: #64748b; cursor: pointer;">性能监控</button>
            <button onclick="showTab('loop', event)" style="flex: 1; padding: 8px 16px; border: none; border-radius: 6px; background: #f1f5f9; color: #64748b; cursor: pointer;">循环审计</button>
            <button onclick="showTab('tuning', event)" style="flex: 1; padding: 8px 16px; border: none; border-radius: 6px; background: #f1f5f9; color: #64748b; cursor: pointer;">调优监控</button>
        </div>
    </div>

    <div id="tab-content">
        <div id="overview" style="display: block;">
    """)

    # 总览标签内容
    _render_health_check_panel(buf)
    
    # 系统健康摘要（从原 system_page 复制）
    from datetime import datetime as _dt
    from deva.naja.strategy.result_store import get_result_store
    from deva.naja.market_hotspot.integration import get_market_hotspot_integration
    from deva.naja.application.container import get_last_boot_report
    
    def _format_ts(ts: float) -> str:
        if not ts:
            return "未写入"
        return _dt.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    
    def _status_color(level: str) -> str:
        if level == "critical":
            return "#dc2626"
        if level == "warning":
            return "#f59e0b"
        return "#16a34a"
    
    def _status_label(level: str) -> str:
        if level == "critical":
            return "严重"
        if level == "warning":
            return "告警"
        return "正常"
    
    def _get_write_level(seconds_since_write) -> str:
        if seconds_since_write is None:
            return "warning"
        if seconds_since_write > 900:
            return "critical"
        if seconds_since_write > 300:
            return "warning"
        return "ok"
    
    result_store = get_result_store()
    health = result_store.get_health_summary()
    
    last_write_time = health.get("last_write_time", 0) or 0
    seconds_since_write = health.get("seconds_since_write")
    write_level = _get_write_level(seconds_since_write)
    write_color = _status_color(write_level)
    
    attention_report = {"status": "not_initialized"}
    try:
        attention_report = get_market_hotspot_integration().get_hotspot_report()
    except Exception:
        pass
    
    status_badge = f"<span style='padding:2px 8px;border-radius:10px;background:{write_color};color:#fff;font-size:12px;'>{_status_label(write_level)}</span>"
    seconds_text = f"{seconds_since_write:.0f}s" if seconds_since_write is not None else "未写入"
    
    buf["put_html"](f"""
    <div style="margin: 10px 0 16px 0; padding: 14px; border-radius: 12px; background: #0f172a; color: #e2e8f0;">
        <div style="display: flex; align-items: center; gap: 10px;">
            <div style="width: 10px; height: 10px; border-radius: 50%; background: {write_color};"></div>
            <div style="font-size: 15px; font-weight: 600;">系统健康摘要</div>
        </div>
        <div style="margin-top: 10px; font-size: 12px; color: #94a3b8;">
            阈值说明：绿色 ≤ 300s，橙色 300-900s，红色 &gt; 900s
        </div>
    </div>
    """)
    
    buf["put_html"](f"""
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px;margin-bottom:14px;">
        <div style="padding:12px;border-radius:10px;background:#111827;">
            <div style="font-size:12px;color:#94a3b8;">结果存储</div>
            <div style="margin-top:6px;font-size:14px;">状态: {status_badge}</div>
            <div style="margin-top:6px;font-size:12px;color:#9ca3af;">最近写入: {_format_ts(last_write_time)}</div>
            <div style="margin-top:4px;font-size:12px;color:#9ca3af;">间隔: {seconds_text}</div>
            <div style="margin-top:4px;font-size:12px;color:#9ca3af;">队列: {health.get('write_queue_size', 0)} | 失败: {health.get('failed_writes', 0)}</div>
        </div>
        <div style="padding:12px;border-radius:10px;background:#111827;">
            <div style="font-size:12px;color:#94a3b8;">注意力系统</div>
            <div style="margin-top:6px;font-size:14px;">状态: {attention_report.get('status', 'unknown')}</div>
            <div style="margin-top:4px;font-size:12px;color:#9ca3af;">快照: {attention_report.get('processed_snapshots', 0)}</div>
            <div style="margin-top:4px;font-size:12px;color:#9ca3af;">全局注意力: {attention_report.get('global_attention', 0):.3f}</div>
        </div>
    </div>
    """)
    
    boot_report = get_last_boot_report()
    if boot_report:
        buf["put_markdown"]("### 系统启动报告")
        summary_rows = [
            ["启动成功", "是" if boot_report.get("success") else "否"],
            ["阶段", boot_report.get("stage", "unknown")],
            ["耗时(ms)", f"{boot_report.get('duration_ms', 0):.1f}"],
            ["消息", boot_report.get("message", "")],
        ]
        buf["put_table"](summary_rows, header=["项目", "值"])

    buf["put_html"]("""
        </div>
        <div id="system" style="display: none;">
    """)

    # 系统监控标签内容
    buf["put_html"](render_monitor_panel())

    buf["put_html"]("""
        </div>
        <div id="performance" style="display: none;">
    """)

    # 性能监控标签内容
    await render_performance_page(buf)

    buf["put_html"]("""
        </div>
        <div id="loop" style="display: none;">
    """)

    # 循环审计标签内容
    await render_loop_audit_page(buf)

    buf["put_html"]("""
        </div>
        <div id="tuning" style="display: none;">
    """)

    # 调优监控标签内容
    try:
        from deva.naja.attention.ui.auto_tuning_monitor import (
            render_tuning_monitor_panel,
            render_frequency_monitor_panel,
            render_datasource_tuning_panel,
        )
        buf["put_html"](render_tuning_monitor_panel())
        buf["put_html"](render_frequency_monitor_panel())
        buf["put_html"](render_datasource_tuning_panel())
    except Exception as e:
        buf["put_html"](f"""
        <div style="padding: 20px; border-radius: 12px; background: #fef2f2; border: 1px solid #fecaca; margin: 24px;">
            <div style="color: #dc2626; font-size: 14px;">⚠️ 调优监控加载失败: {_html.escape(str(e)[:100])}</div>
        </div>
        """)

    # 收口：tab-content 里五个容器到此全部闭合
    buf["put_html"]("""
        </div>
    </div>
    """)

    # 整份文档拼好后一次性输出，保证 tab 容器的嵌套关系不被 PyWebIO 的
    # 独立片段插入打断；tab 切换函数<｜hy_place▁holder▁no▁813｜> run_js 定义。
    buf.flush()
    ctx["run_js"](_TAB_JS)


async def health_dashboard_page():
    """健康监控仪表盘页面"""
    from deva.naja.web_ui.ui_base import _ctx
    ctx = _ctx()
    await render_health_dashboard(ctx)
