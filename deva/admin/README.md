# Deva Admin 模块使用文档

## 目录

- [概述](#概述)
- [模块结构](#模块结构)
- [核心功能](#核心功能)
- [不依赖 UI 的核心库](#不依赖-ui-的核心库)
- [UI 使用指南](#ui-使用指南)
- [使用示例](#使用示例)
- [API 参考](#api-参考)
- [最佳实践](#最佳实践)

---

## 概述

Deva Admin 模块是一个功能完整的管理系统，提供定时任务管理、数据源管理、策略管理、AI 功能中心等核心功能。模块采用分层架构设计，将核心业务逻辑与 UI 展示层清晰分离。

### 核心特性

- **模块化设计**：按功能划分为独立子模块（tasks, ai, datasource, strategy 等）
- **分层架构**：核心逻辑层、业务管理层、UI 展示层分离
- **可扩展性**：基于基类和接口的设计，易于扩展新功能
- **异步支持**：完整的 async/await 支持，适合高并发场景
- **持久化**：多后端持久化支持（内存、文件、数据库）
- **容错机制**：完善的错误处理和日志记录

---

## 模块结构

```
deva/admin/
├── 核心模块（不依赖 UI）
│   ├── common/
│   │   └── base.py              # 基础类和接口定义
│   ├── strategy/
│   │   ├── base.py              # 策略基类
│   │   ├── executable_unit.py   # 可执行单元基类
│   │   ├── persistence.py       # 持久化层
│   │   ├── logging_context.py   # 日志上下文
│   │   ├── result_store.py      # 结果存储
│   │   ├── utils.py             # 工具函数
│   │   ├── tradetime.py         # 交易时间工具
│   │   └── error_handler.py     # 错误处理
│   └── llm/
│       ├── worker_runtime.py    # AI 异步工作器
│       └── config_utils.py      # LLM 配置工具
│
├── 业务模块（部分依赖 UI）
│   ├── tasks/                   # 任务管理
│   ├── ai/                      # AI 功能
│   ├── datasource/              # 数据源管理
│   └── strategy/                # 策略管理（业务层）
│
└── UI 模块（依赖 PyWebIO）
    ├── main_ui.py               # 主页面
    ├── contexts.py              # 上下文构建器
    ├── menus/                   # 菜单渲染
    ├── monitor/                 # 监控 UI
    ├── config/                  # 配置 UI
    ├── document/                # 文档 UI
    ├── tables/                  # 表格 UI
    ├── follow/                  # 关注 UI
    └── browser/                 # 浏览器 UI
```

---

## 不依赖 UI 的核心库

以下模块可以**独立使用**，无需 PyWebIO 或任何 UI 依赖：

### 1. 基础架构层 (`deva.admin.strategy.base`)

```python
from deva.admin.strategy.base import (
    BaseManager,      # 通用管理器基类
    BaseMetadata,     # 元数据基类
    BaseState,        # 状态基类
    BaseStats,        # 统计基类
    BaseStatus,       # 状态枚举
    StatusMixin,      # 状态混入类
    CallbackMixin,    # 回调混入类
)
```

**用途**：所有管理器、单元类的基类，提供生命周期管理、状态跟踪、回调机制。

**示例**：
```python
from deva.admin.strategy.base import BaseManager, BaseMetadata, BaseState

class MyMetadata(BaseMetadata):
    name: str
    version: str

class MyState(BaseState):
    is_running: bool = False
    count: int = 0

class MyManager(BaseManager):
    def _do_start(self, item):
        # 启动逻辑
        pass
    
    def _do_stop(self, item):
        # 停止逻辑
        pass
```

### 2. 可执行单元 (`deva.admin.strategy.executable_unit`)

```python
from deva.admin.strategy.executable_unit import (
    ExecutableUnit,           # 可执行单元基类
    ExecutableUnitMetadata,   # 元数据
    ExecutableUnitState,      # 状态
    ExecutableUnitStatus,     # 状态枚举
)
```

**用途**：策略、数据源、任务的统一基类，提供代码执行、状态管理能力。

### 3. 持久化层 (`deva.admin.strategy.persistence`)

```python
from deva.admin.strategy.persistence import (
    PersistenceManager,    # 持久化管理器
    MemoryBackend,         # 内存后端
    FileBackend,           # 文件后端
    DatabaseBackend,       # 数据库后端
    HybridBackend,         # 混合后端
    StorageConfig,         # 存储配置
)
```

**用途**：多后端数据持久化，支持配置序列化/反序列化。

**示例**：
```python
from deva.admin.strategy.persistence import PersistenceManager, StorageConfig

# 创建持久化管理器
config = StorageConfig(
    backend='hybrid',
    memory_cache=True,
    file_path='./data',
    auto_save=True
)
manager = PersistenceManager(config)

# 保存配置
manager.save_config('my_config', {'key': 'value'})

# 加载配置
data = manager.load_config('my_config')
```

### 4. 日志上下文 (`deva.admin.strategy.logging_context`)

```python
from deva.admin.strategy.logging_context import (
    LoggingContext,            # 日志上下文
    LoggingContextManager,     # 上下文管理器
    logging_context_manager,   # 全局上下文管理器
    strategy_log,              # 策略日志
    datasource_log,            # 数据源日志
    task_log,                  # 任务日志
    log_strategy_event,        # 记录策略事件
    log_datasource_event,      # 记录数据源事件
)
```

**用途**：线程安全的日志上下文管理，自动携带组件信息。

**示例**：
```python
from deva.admin.strategy.logging_context import LoggingContext, strategy_log

# 创建上下文
ctx = LoggingContext(component_type='strategy', component_id='my_strategy')

with ctx:
    strategy_log.info('策略启动')
    strategy_log.error('发生错误', extra={'error_code': 'E001'})
```

### 5. 结果存储 (`deva.admin.strategy.result_store`)

```python
from deva.admin.strategy.result_store import (
    StrategyResult,    # 策略结果
    ResultStore,       # 结果存储
    get_result_store,  # 获取全局存储
)
```

**用途**：策略执行结果的缓存和持久化。

**示例**：
```python
from deva.admin.strategy.result_store import get_result_store

store = get_result_store()

# 保存结果
store.save_result('my_strategy', {
    'returns': 0.05,
    'sharpe': 1.5,
    'trades': 100
})

# 查询结果
results = store.get_results('my_strategy', limit=10)
```

### 6. 工具函数 (`deva.admin.strategy.utils`)

```python
from deva.admin.strategy.utils import (
    format_pct,              # 格式化百分比
    format_duration,         # 格式化时长
    df_to_html,              # DataFrame 转 HTML
    prepare_df,              # 准备 DataFrame
    calc_block_ranking,      # 计算板块排名
    get_top_stocks_in_block, # 获取板块龙头股
    TABLE_STYLE,             # 表格样式
)
```

### 7. 交易时间工具 (`deva.admin.strategy.tradetime`)

```python
from deva.admin.strategy.tradetime import (
    is_holiday,              # 是否假日
    is_tradedate,            # 是否交易日
    is_tradetime,            # 是否交易时间
    get_next_trade_date,     # 获取下一交易日
    get_last_trade_date,     # 获取上一交易日
    when_tradetime,          # 交易时间执行
    when_tradedate,          # 交易日执行
)
```

**示例**：
```python
from deva.admin.strategy.tradetime import is_tradetime, when_tradetime

# 检查是否交易时间
if is_tradetime():
    print('当前是交易时间')

# 在交易时间执行
@when_tradetime
def my_trading_function():
    print('执行交易逻辑')
```

### 8. AI 异步工作器 (`deva.admin.llm.worker_runtime`)

```python
from deva.admin.llm.worker_runtime import (
    submit_ai_coro,         # 提交 AI 协程
    run_ai_in_worker,       # 在工作器中运行 AI
    run_sync_in_worker,     # 在工作器中同步运行
)
```

**用途**：在独立线程中运行 AI 相关操作，避免阻塞主线程。

**示例**：
```python
from deva.admin.llm.worker_runtime import run_ai_in_worker

async def call_llm_api():
    # 调用 LLM API
    return response

# 在工作器中运行
result = await run_ai_in_worker(call_llm_api())
```

### 9. LLM 配置工具 (`deva.admin.llm.config_utils`)

```python
from deva.admin.llm.config_utils import (
    get_model_config_status,      # 获取模型配置状态
    build_model_config_example,   # 构建配置示例
    build_model_config_message,   # 构建配置消息
)
```

### 10. 错误处理 (`deva.admin.strategy.error_handler`)

```python
from deva.admin.strategy.error_handler import (
    ErrorHandler,              # 错误处理器
    ErrorLevel,                # 错误级别
    ErrorCategory,             # 错误分类
    ErrorRecord,               # 错误记录
    ErrorCollector,            # 错误收集器
    get_global_error_collector,# 获取全局错误收集器
)
```

---

## UI 使用指南

详细的 UI 使用说明请参考 **[UI_GUIDE.md](UI_GUIDE.md)**。

### 快速导航

- [界面概览](UI_GUIDE.md#界面概览) - 了解界面布局
- [导航菜单](UI_GUIDE.md#导航菜单) - 所有菜单项说明
- [功能模块使用](UI_GUIDE.md#功能模块使用) - 各功能详细用法
- [快捷键](UI_GUIDE.md#快捷键) - 提高效率的快捷键
- [常见问题](UI_GUIDE.md#常见问题) - FAQ 和解决方案

### 主要功能页面

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

---

## 业务模块 API

### 任务管理 (`deva.admin.tasks`)

```python
from deva.admin.tasks import (
    # 核心类
    TaskUnit,              # 任务单元
    TaskType,              # 任务类型枚举
    TaskManager,           # 任务管理器
    TaskMetadata,          # 任务元数据
    TaskState,             # 任务状态
    TaskStats,             # 任务统计
    
    # 函数
    get_task_manager,      # 获取任务管理器
    watch_topic,           # 监视主题
    create_task,           # 创建任务
    manage_tasks,          # 管理任务
    stop_task,             # 停止任务
    start_task,            # 启动任务
    delete_task,           # 删除任务
    recover_task,          # 恢复任务
    remove_task_forever,   # 永久移除任务
)
```

**示例**：
```python
from deva.admin.tasks import TaskType, get_task_manager

# 获取任务管理器
manager = get_task_manager()

# 创建定时任务
manager.create_task(
    name='my_task',
    task_type=TaskType.INTERVAL,
    interval=60,  # 60 秒
    code='print("Hello")'
)

# 启动任务
manager.start_task('my_task')

# 停止任务
manager.stop_task('my_task')
```

### 数据源管理 (`deva.admin.datasource`)

```python
from deva.admin.datasource import (
    # 核心类
    DataSource,              # 数据源
    DataSourceStatus,        # 数据源状态
    DataSourceType,          # 数据源类型
    DataSourceManager,       # 数据源管理器
    DataSourceMetadata,      # 数据源元数据
    DataSourceState,         # 数据源状态
    
    # 函数
    get_ds_manager,          # 获取数据源管理器
    create_timer_source,     # 创建定时器数据源
    create_stream_source,    # 创建流数据源
    create_replay_source,    # 创建回放数据源
)
```

**示例**：
```python
from deva.admin.datasource import (
    get_ds_manager, 
    DataSourceType,
    create_timer_source
)

# 获取管理器
manager = get_ds_manager()

# 创建定时器数据源
source = create_timer_source(
    source_id='my_source',
    interval=60,
    code='return {"data": 123}'
)

# 启动数据源
manager.start_datasource('my_source')

# 获取数据
data = manager.get_datasource_data('my_source')
```

### AI 功能 (`deva.admin.ai`)

```python
from deva.admin.ai import (
    # AI 代码生成器
    AICodeGenerator,         # AI 代码生成器基类
    StrategyAIGenerator,     # 策略 AI 生成器
    DataSourceAIGenerator,   # 数据源 AI 生成器
    TaskAIGenerator,         # 任务 AI 生成器
    
    # AI 功能函数
    analyze_data_schema,     # 分析数据结构
    generate_strategy_code,  # 生成策略代码
    validate_strategy_code,  # 验证策略代码
    test_strategy_code,      # 测试策略代码
    get_gpt_response,        # 获取 GPT 响应
)
```

**示例**：
```python
from deva.admin.ai import (
    StrategyAIGenerator,
    generate_strategy_code
)

# 生成策略代码
code = generate_strategy_code(
    data_schema={'type': 'stock', 'fields': ['open', 'close']},
    requirement='生成一个均线策略'
)

# 验证代码
result = validate_strategy_code(code)
if result['valid']:
    print('代码验证通过')
```

### 策略管理 (`deva.admin.strategy`)

```python
from deva.admin.strategy import (
    # 核心类
    StrategyUnit,            # 策略单元
    StrategyManager,         # 策略管理器
    StrategyStatus,          # 策略状态
    StrategyMetadata,        # 策略元数据
    ExecutionState,          # 执行状态
    DataSchema,              # 数据结构
    ReplayLab,               # 回放实验室
    
    # 函数
    get_manager,             # 获取策略管理器
    get_lab,                 # 获取回放实验室
    create_strategy_unit,    # 创建策略单元
    initialize_fault_tolerance,  # 初始化容错
)
```

---

## 使用示例

### 1. 创建独立的任务管理系统

```python
from deva.admin.tasks import TaskType, get_task_manager
from deva.admin.strategy.logging_context import LoggingContext

# 获取任务管理器
task_manager = get_task_manager()

# 创建日志上下文
ctx = LoggingContext(component_type='task_system', component_id='main')

with ctx:
    # 创建定时任务
    task_manager.create_task(
        name='daily_report',
        task_type=TaskType.CRON,
        cron_expression='0 9 * * *',  # 每天 9 点
        code='''
import pandas as pd
print("生成日报表")
return {"status": "success"}
'''
    )
    
    # 创建间隔任务
    task_manager.create_task(
        name='heartbeat',
        task_type=TaskType.INTERVAL,
        interval=300,  # 5 分钟
        code='print("心跳检测")'
    )
    
    # 启动所有任务
    task_manager.start_task('daily_report')
    task_manager.start_task('heartbeat')
    
    # 查看任务状态
    stats = task_manager.get_task_stats()
    print(f"运行中任务：{stats.running_count}")
```

### 2. 创建数据源监控系统

```python
from deva.admin.datasource import (
    get_ds_manager,
    create_timer_source,
    create_stream_source,
    DataSourceType
)

# 获取数据源管理器
ds_manager = get_ds_manager()

# 创建定时器数据源（获取股票数据）
timer_source = create_timer_source(
    source_id='stock_data',
    interval=60,
    code='''
import akshare as ak
df = ak.stock_zh_a_spot_em()
return df.head(10).to_dict()
'''
)

# 创建流数据源
stream_source = create_stream_source(
    source_id='news_stream',
    stream_name='realtime_news',
    code='''
# 处理新闻流
for news in news_stream:
    yield {"title": news["title"], "time": news["time"]}
'''
)

# 启动数据源
ds_manager.start_datasource('stock_data')
ds_manager.start_datasource('news_stream')

# 监控数据源状态
for source_id in ds_manager.list_datasources():
    status = ds_manager.get_datasource_status(source_id)
    print(f"{source_id}: {status}")
```

### 3. 使用 AI 生成策略

```python
from deva.admin.ai import (
    generate_strategy_code,
    validate_strategy_code,
    test_strategy_code
)
from deva.admin.strategy import get_manager

# 定义数据结构
data_schema = {
    'type': 'stock',
    'fields': [
        {'name': 'open', 'type': 'float'},
        {'name': 'high', 'type': 'float'},
        {'name': 'low', 'type': 'float'},
        {'name': 'close', 'type': 'float'},
        {'name': 'volume', 'type': 'int'}
    ]
}

# AI 生成策略代码
requirement = '''
生成一个双均线策略：
- 使用 5 日和 20 日移动平均线
- 金叉买入，死叉卖出
- 包含止损逻辑
'''

code = generate_strategy_code(
    data_schema=data_schema,
    requirement=requirement
)

# 验证代码
validation = validate_strategy_code(code)
if not validation['valid']:
    print(f"代码验证失败：{validation['errors']}")
    exit(1)

# 测试代码
test_result = test_strategy_code(
    code=code,
    sample_data=data_schema
)
print(f"测试结果：{test_result}")

# 保存策略
strategy_manager = get_manager()
strategy_manager.create_strategy(
    name='ma_cross_strategy',
    code=code,
    metadata={
        'description': '双均线交叉策略',
        'version': '1.0.0'
    }
)
```

### 4. 使用持久化层

```python
from deva.admin.strategy.persistence import (
    PersistenceManager,
    StorageConfig
)

# 配置持久化
config = StorageConfig(
    backend='hybrid',  # 混合后端
    memory_cache=True,
    file_path='./data/store',
    auto_save=True,
    save_interval=300  # 5 分钟自动保存
)

# 创建管理器
pm = PersistenceManager(config)

# 保存配置
pm.save_config('strategy_config', {
    'name': 'my_strategy',
    'params': {'ma_short': 5, 'ma_long': 20}
})

# 加载配置
config_data = pm.load_config('strategy_config')
print(f"加载的配置：{config_data}")

# 列出所有配置
all_configs = pm.list_configs()
print(f"所有配置：{all_configs}")
```

### 5. 使用日志上下文

```python
from deva.admin.strategy.logging_context import (
    LoggingContext,
    strategy_log,
    log_strategy_event
)

# 创建策略日志上下文
ctx = LoggingContext(
    component_type='strategy',
    component_id='ma_strategy',
    extra_info={'version': '1.0.0'}
)

with ctx:
    # 记录策略事件
    log_strategy_event('START', message='策略启动')
    
    try:
        # 策略逻辑
        strategy_log.info('执行交易逻辑')
        
        # 记录指标
        strategy_log.info('指标更新', extra={
            'ma_short': 10.5,
            'ma_long': 11.2,
            'signal': 'BUY'
        })
        
    except Exception as e:
        strategy_log.error('策略执行失败', exc_info=True)
        log_strategy_event('ERROR', message=str(e))
    
    finally:
        log_strategy_event('STOP', message='策略停止')
```

---

## 最佳实践

### 1. 模块导入规范

```python
# ✅ 推荐：明确导入需要的类
from deva.admin.tasks import TaskManager, TaskType
from deva.admin.strategy.base import BaseManager

# ❌ 不推荐：导入整个模块
import deva.admin.tasks
```

### 2. 错误处理

```python
from deva.admin.strategy.error_handler import ErrorHandler, ErrorLevel

handler = ErrorHandler()

try:
    # 业务逻辑
    result = risky_operation()
except Exception as e:
    handler.handle_error(
        error=e,
        level=ErrorLevel.ERROR,
        category='BUSINESS',
        context={'operation': 'risky_operation'}
    )
```

### 3. 异步操作

```python
from deva.admin.llm.worker_runtime import run_ai_in_worker

async def my_async_function():
    # 在工作器中运行 AI 操作
    result = await run_ai_in_worker(
        call_llm_api(prompt)
    )
    return result
```

### 4. 状态管理

```python
from deva.admin.strategy.base import BaseState, BaseStatus

class MyState(BaseState):
    is_running: bool = False
    progress: float = 0.0
    last_update: float = 0.0

# 使用状态
state = MyState()
state.update_status(BaseStatus.RUNNING)
state.is_running = True
```

### 5. 数据持久化

```python
from deva.admin.strategy.persistence import PersistenceManager

# 自动保存配置
pm = PersistenceManager(auto_save=True)

# 手动保存
pm.save_config('key', data)

# 定期备份
pm.backup_all_configs()
```

---

## 附录

### A. 依赖关系图

```
┌─────────────────────────────────────────────────────┐
│                  UI 层 (PyWebIO)                     │
├─────────────────────────────────────────────────────┤
│  main_ui  │  contexts  │  menus  │  monitor  │ ...  │
└─────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────┐
│                  业务逻辑层                           │
├──────────────┬──────────────┬───────────────────────┤
│    tasks/    │  datasource/ │      strategy/        │
│   TaskManager│ DataSource   │  StrategyManager      │
└──────────────┴──────────────┴───────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────┐
│                  核心基础层                           │
├──────────────┬──────────────┬───────────────────────┤
│  base.py     │ persistence  │   logging_context     │
│  executable  │ result_store │   error_handler       │
└──────────────┴──────────────┴───────────────────────┘
```

### B. 版本信息

- **模块版本**: 1.0.0
- **Python 版本**: 3.8+
- **主要依赖**: PyWebIO, pandas, asyncio, APScheduler

### C. 相关文档

- [Deva 核心文档](../../README.rst)
- [PyWebIO 文档](https://docs.pyweb.io/)
- [APScheduler 文档](https://apscheduler.readthedocs.io/)
