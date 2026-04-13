# Deva Admin 管理后台文档

## 概述

Deva Admin 是一个功能完整的管理系统，提供定时任务管理、数据源管理、策略管理、AI 功能中心等核心功能。模块采用分层架构设计，将核心业务逻辑与 UI 展示层清晰分离。

## 核心特性

- **模块化设计**：按功能划分为独立子模块（tasks, ai, datasource, strategy 等）
- **分层架构**：核心逻辑层、业务管理层、UI 展示层分离
- **可扩展性**：基于基类和接口的设计，易于扩展新功能
- **异步支持**：完整的 async/await 支持，适合高并发场景
- **持久化**：多后端持久化支持（内存、文件、数据库）
- **容错机制**：完善的错误处理和日志记录

## 模块结构

```
deva/admin/
├── __init__.py           # 模块初始化
├── main_ui.py            # 主页面
├── contexts.py           # 上下文构建器
├── runtime.py            # 运行时
├── utils.py              # 工具函数
├── auth_routes.py        # 认证路由
├── llm_service.py        # LLM 服务
├── ai/                   # AI 功能模块
│   ├── __init__.py
│   └── llm_service.py
├── browser/             # 浏览器模块
│   ├── __init__.py
│   └── browser_ui.py
├── common/              # 公共模块
│   ├── __init__.py
│   ├── base.py          # 基础类
│   └── recoverable.py   # 可恢复类
├── config/              # 配置模块
│   ├── __init__.py
│   └── config_ui.py
├── document/            # 文档模块
│   ├── __init__.py
│   └── document.py
├── follow/              # 关注模块
│   ├── __init__.py
│   └── follow_ui.py
├── llm/                 # LLM 模块
│   ├── __init__.py
│   ├── client.py
│   ├── config_utils.py
│   └── worker_runtime.py
├── menus/               # 菜单模块
│   ├── __init__.py
│   ├── config.py
│   └── renderer.py
├── monitor/             # 监控模块
│   ├── __init__.py
│   ├── monitor_routes.py
│   ├── monitor_ui.py
│   ├── shared_routes.py
│   └── shared_ui.py
├── stock/               # 股票模块
│   ├── __init__.py
│   └── stock.py
├── tables/              # 表格模块
│   ├── __init__.py
│   └── tables.py
└── tasks/               # 任务管理模块
    ├── __init__.py
    ├── error_handler.py
    ├── executable_unit.py
    ├── logging_context.py
    ├── persistence.py
    ├── task_admin.py
    ├── task_dialog.py
    ├── task_manager.py
    └── task_unit.py
```

## 核心模块详解

### 1. 基础架构层

**位置**：[deva/admin/common/base.py](file:///workspace/deva/admin/common/base.py)

提供所有管理器、单元类的基类，包括：

- `BaseManager`：通用管理器基类
- `BaseMetadata`：元数据基类
- `BaseState`：状态基类
- `BaseStats`：统计基类
- `BaseStatus`：状态枚举
- `StatusMixin`：状态混入类
- `CallbackMixin`：回调混入类

### 2. 可执行单元

**位置**：[deva/admin/tasks/executable_unit.py](file:///workspace/deva/admin/tasks/executable_unit.py)

策略、数据源、任务的统一基类，提供代码执行、状态管理能力。

### 3. 持久化层

**位置**：[deva/admin/tasks/persistence.py](file:///workspace/deva/admin/tasks/persistence.py)

多后端数据持久化，支持配置序列化/反序列化：

- `PersistenceManager`：持久化管理器
- `MemoryBackend`：内存后端
- `FileBackend`：文件后端
- `DatabaseBackend`：数据库后端
- `HybridBackend`：混合后端

### 4. 日志上下文

**位置**：[deva/admin/tasks/logging_context.py](file:///workspace/deva/admin/tasks/logging_context.py)

线程安全的日志上下文管理，自动携带组件信息。

### 5. 任务管理

**位置**：[deva/admin/tasks/](file:///workspace/deva/admin/tasks/)

提供完整的任务管理功能：

- `TaskUnit`：任务单元
- `TaskType`：任务类型枚举
- `TaskManager`：任务管理器
- `TaskMetadata`：任务元数据
- `TaskState`：任务状态
- `TaskStats`：任务统计

### 6. AI 功能

**位置**：[deva/admin/ai/](file:///workspace/deva/admin/ai/)

提供 AI 代码生成和辅助功能：

- `AICodeGenerator`：AI 代码生成器基类
- `StrategyAIGenerator`：策略 AI 生成器
- `DataSourceAIGenerator`：数据源 AI 生成器
- `TaskAIGenerator`：任务 AI 生成器

### 7. LLM 工作器

**位置**：[deva/admin/llm/worker_runtime.py](file:///workspace/deva/admin/llm/worker_runtime.py)

在独立线程中运行 AI 相关操作，避免阻塞主线程。

## UI 功能页面

| 页面 | 路径 | 说明 |
|------|------|------|
| 🏠 首页 | `/` | 系统概览和快捷操作 |
| ⏰ 任务管理 | `/taskadmin` | 定时任务创建和管理 |
| 📡 数据源 | `/datasourceadmin` | 数据源配置和监控 |
| 📈 策略管理 | `/strategyadmin` | 量化策略管理 |
| 🤖 AI 中心 | `/aicenter` | AI 功能中心 |
| 💾 数据库 | `/dbadmin` | 数据库管理 |
| 📊 命名流 | `/streamadmin` | 数据流监控 |
| 👁 监控 | `/monitor` | 系统监控面板 |
| ⚙️ 配置 | `/configadmin` | 系统配置 |
| 📄 文档 | `/document` | API 文档查看 |

## 使用示例

### 创建定时任务

```python
from deva.admin.tasks import TaskType, get_task_manager

manager = get_task_manager()

manager.create_task(
    name='my_task',
    task_type=TaskType.INTERVAL,
    interval=60,
    code='print("Hello")'
)

manager.start_task('my_task')
```

### 使用持久化层

```python
from deva.admin.strategy.persistence import PersistenceManager, StorageConfig

config = StorageConfig(
    backend='hybrid',
    memory_cache=True,
    file_path='./data',
    auto_save=True
)
manager = PersistenceManager(config)

manager.save_config('my_config', {'key': 'value'})
data = manager.load_config('my_config')
```

### AI 生成策略代码

```python
from deva.admin.ai import generate_strategy_code, validate_strategy_code

code = generate_strategy_code(
    data_schema={'type': 'stock', 'fields': ['open', 'close']},
    requirement='生成一个均线策略'
)

validation = validate_strategy_code(code)
```

## 相关文档

- [deva/admin/README.md](file:///workspace/deva/admin/README.md) - Admin 模块详细文档
- [deva/admin/UI_GUIDE.md](file:///workspace/deva/admin/UI_GUIDE.md) - UI 使用指南
- [CODE_WIKI.md](file:///workspace/CODE_WIKI.md) - 项目总览文档

---

**文档版本**：1.0
**最后更新**：2026-04-13
