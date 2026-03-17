# Admin UI 管理后台指南

> 基于最新代码结构（2026-03-17）

## 概述

Admin UI 是基于 PyWebIO 的 Web 管理后台，提供任务、数据源、策略、配置等管理功能。

## 核心模块

```
deva/admin_ui/
├── 核心模块（不依赖 UI）
│   ├── common/          # 基础类和接口
│   ├── strategy/        # 策略基类、可执行单元
│   │   ├── base.py
│   │   ├── executable_unit.py
│   │   ├── persistence.py
│   │   ├── logging_context.py
│   │   ├── result_store.py
│   │   ├── utils.py
│   │   ├── tradetime.py
│   │   └── error_handler.py
│   └── llm/
│       ├── worker_runtime.py
│       └── config_utils.py
│
├── 业务模块
│   ├── tasks/           # 任务管理
│   ├── ai/              # AI 功能
│   ├── datasource/      # 数据源管理
│   └── strategy/        # 策略管理
│
└── UI 模块
    ├── main_ui.py       # 主页面
    ├── contexts.py       # 上下文
    ├── menus/           # 菜单
    ├── monitor/         # 监控
    ├── config/          # 配置
    └── ...
```

## 主要页面

| 路径 | 功能 |
|------|------|
| `/` | 首页 |
| `/taskadmin` | 任务管理 |
| `/datasourceadmin` | 数据源管理 |
| `/strategyadmin` | 策略管理 |
| `/aicenter` | AI 中心 |
| `/dbadmin` | 数据库管理 |
| `/streamadmin` | 数据流监控 |
| `/monitor` | 系统监控 |
| `/configadmin` | 系统配置 |

## 核心库使用

### 任务管理

```python
from deva.admin_ui.tasks import TaskType, get_task_manager

manager = get_task_manager()
manager.create_task(name='my_task', task_type=TaskType.INTERVAL, interval=60)
```

### 数据源管理

```python
from deva.admin_ui.datasource import get_ds_manager, create_timer_source

ds_manager = get_ds_manager()
source = create_timer_source(source_id='my_source', interval=60, code='...')
```

### 策略管理

```python
from deva.admin_ui.strategy import get_manager

strategy_manager = get_manager()
```

### 持久化

```python
from deva.admin_ui.strategy.persistence import PersistenceManager, StorageConfig

config = StorageConfig(backend='hybrid', memory_cache=True)
pm = PersistenceManager(config)
```

## 相关文档

- [ARCHITECTURE.md](ARCHITECTURE.md)
- [QUICKSTART.md](QUICKSTART.md)
- [task_guide.md](task_guide.md)
- [datasource_guide.md](datasource_guide.md)
- [strategy_guide.md](strategy_guide.md)
