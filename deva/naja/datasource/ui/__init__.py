"""数据源管理 UI 包

拆分结构：
  constants.py   — 默认代码模板、工具函数
  table.py       — 列表渲染、分类/视图切换、表格构建
  detail.py      — 详情弹窗
  dialogs.py     — 编辑/创建对话框
  schedule.py    — 调度配置向导（Timer/Scheduler/Cron）
  actions.py     — 工具栏操作（启动/停止/导出）
"""

from .table import render_datasource_admin
from .detail import _show_ds_detail

__all__ = [
    "render_datasource_admin",
    "_show_ds_detail",
]
