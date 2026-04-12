"""全局样式"""

from pywebio.output import put_html

from .theme import get_request_theme


def apply_global_styles():
    """应用全局样式"""
    put_html("""
    <style>
        :root {
            --primary-color: #3b82f6;
            --primary-hover: #2563eb;
            --success-color: #28a745;
            --danger-color: #dc3545;
            --warning-color: #ffc107;
            --text-color: #1e293b;
            --text-muted: #64748b;
            --bg-color: #f8fafc;
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


