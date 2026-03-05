# 信号流模块拆分计划

## 目标
将信号流功能从策略模块拆分到独立的 signal 模块，与策略、数据源、任务、字典并列，并在 naja 的 tab 中显示。

## 当前结构分析

### 现有模块
```
deva/naja/
├── datasource/    # 数据源模块
├── tasks/         # 任务模块
├── strategy/      # 策略模块（包含信号流代码）
├── dictionary/    # 字典模块
├── tables/        # 数据表模块
├── config/        # 配置模块
└── web_ui.py      # Web 路由
```

### 信号流相关代码位置
在 `deva/naja/strategy/ui.py` 中：
- `_render_signal_stream_content()` - 渲染信号流内容
- `_auto_insert_new_signals()` - 自动插入新信号
- `_insert_signal_item()` - 插入单个信号
- `_get_signal_type()` - 获取信号类型
- `_get_signal_detail()` - 获取信号详情
- `_generate_expanded_content()` - 生成展开内容
- `_delete_result_with_confirm()` - 删除结果
- `_handle_result_action()` - 处理结果操作
- `_shown_signal_ids` - 已显示信号 ID 集合
- `_auto_refresh_enabled` - 自动刷新控制

## 实施步骤

### 步骤 1: 创建 signal 模块目录结构
```
deva/naja/signal/
├── __init__.py    # 模块导出
└── ui.py          # 信号流 UI 代码
```

### 步骤 2: 创建 signal/__init__.py
- 导出必要的函数
- 保持与其他模块一致的风格

### 步骤 3: 创建 signal/ui.py
从 `strategy/ui.py` 迁移信号流相关代码：
- 所有信号流渲染函数
- 全局变量（_shown_signal_ids, _auto_refresh_enabled）
- 新建 `render_signal_page()` 作为页面入口

### 步骤 4: 更新 strategy/ui.py
- 移除迁移到 signal 模块的代码
- 保留策略管理相关的 UI 代码

### 步骤 5: 更新 naja/__init__.py
- 添加 signal 模块的导出

### 步骤 6: 更新 web_ui.py
- 添加信号流 tab：`{"name": "📡 信号流", "path": "/signaladmin"}`
- 添加 `signaladmin()` 路由处理函数
- 更新 `create_handlers()` 添加路由
- 更新主页导航和快速导航卡片

## 文件变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `deva/naja/signal/__init__.py` | 新建 | 模块导出 |
| `deva/naja/signal/ui.py` | 新建 | 信号流 UI |
| `deva/naja/strategy/ui.py` | 修改 | 移除信号流代码 |
| `deva/naja/__init__.py` | 修改 | 添加 signal 导出 |
| `deva/naja/web_ui.py` | 修改 | 添加信号流 tab |

## 注意事项

1. **依赖关系**：signal 模块依赖 `result_store`，需要正确导入
2. **全局变量**：`_shown_signal_ids` 等变量迁移后需要确保正确初始化
3. **导入路径**：更新所有引用信号流函数的地方
