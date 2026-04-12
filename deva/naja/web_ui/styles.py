"""全局样式 — Layer 0（CSS 变量定义源）

所有颜色值统一使用 Tailwind 色系，与 market_hotspot/ui_components/styles.py
中的 Python 常量保持一致。改主题只需改这里的 :root 变量。

层级关系：
  Layer 0: web_ui/styles.py        — CSS 变量（本文件）
  Layer 1: common/ui_style.py      — Python 端公共组件样式 + 工具函数
  Layer 2: market_hotspot/ui_components/styles.py — 业务层样式常量
"""

from pywebio.output import put_html


def apply_global_styles():
    """应用全局 CSS 变量和基础样式（Layer 0）"""
    put_html("""
    <style>
        :root {
            /* ── 语义色（Tailwind 色系）── */
            --primary-color: #3b82f6;
            --primary-hover: #1d4ed8;
            --success-color: #22c55e;
            --success-dark: #16a34a;
            --danger-color: #ef4444;
            --danger-dark: #dc2626;
            --warning-color: #f59e0b;
            --warning-dark: #b45309;
            --info-color: #3b82f6;
            --purple-color: #8b5cf6;

            /* ── 文字 ── */
            --text-color: #1e293b;
            --text-secondary: #64748b;
            --text-muted: #94a3b8;

            /* ── 背景 / 边框 ── */
            --bg-color: #f8fafc;
            --bg-subtle: #f1f5f9;
            --border-color: #e2e8f0;
        }

        .stats-card {
            display: inline-block;
            padding: 15px 25px;
            margin: 5px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border-radius: 12px;
            text-align: center;
            min-width: 100px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }

        .stats-value {
            font-size: 28px;
            font-weight: bold;
        }

        .stats-label {
            font-size: 12px;
            opacity: 0.9;
            margin-top: 4px;
        }

        .status-running {
            color: var(--success-color);
            font-weight: 600;
        }

        .status-stopped {
            color: var(--text-muted);
        }

        .status-error {
            color: var(--danger-color);
            font-weight: 600;
        }

        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 16px;
            background: white;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }

        th {
            background: var(--bg-color);
            padding: 12px 16px;
            text-align: left;
            font-weight: 600;
            color: var(--text-color);
            border-bottom: 2px solid var(--border-color);
        }

        td {
            padding: 12px 16px;
            border-bottom: 1px solid var(--border-color);
        }

        tr:hover {
            background: var(--bg-color);
        }

        .detail-section {
            margin: 16px 0;
            padding: 16px;
            background: var(--bg-color);
            border-radius: 8px;
        }

        .detail-title {
            font-size: 16px;
            font-weight: 600;
            color: var(--text-color);
            margin-bottom: 12px;
            padding-bottom: 8px;
            border-bottom: 1px solid var(--border-color);
        }
    </style>
    """)


