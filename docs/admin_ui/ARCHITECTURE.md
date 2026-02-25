# Deva Admin UI 架构文档

## 📖 概述

Deva Admin UI 是一个功能完整的 Web 管理界面，用于管理和监控 Deva 流处理框架的所有组件。

---

## 🏗️ 架构设计

### 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                     Admin UI 架构                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              表现层 (PyWebIO UI)                     │   │
│  ├─────────────────────────────────────────────────────┤   │
│  │  main_ui  │  monitor_ui  │  browser_ui  │  ...      │   │
│  └─────────────────────────────────────────────────────┘   │
│                            ↓                                │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              业务逻辑层                              │   │
│  ├─────────────────────────────────────────────────────┤   │
│  │  strategy_manager  │  datasource_manager  │  ...    │   │
│  └─────────────────────────────────────────────────────┘   │
│                            ↓                                │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              数据访问层                              │   │
│  ├─────────────────────────────────────────────────────┤   │
│  │  DBStream  │  Namespace  │  SQLite  │  Redis       │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 模块层次

```
Level 1: 核心 UI 层
├── main_ui.py           - 主界面、导航、认证
├── runtime.py           - 运行时管理
└── contexts.py          - 上下文管理

Level 2: 功能 UI 层
├── monitor_ui.py        - 监控界面
├── browser_ui.py        - 浏览器管理
├── config_ui.py         - 配置管理
├── follow_ui.py         - 关注管理
└── tasks.py             - 任务管理

Level 3: 策略管理层
├── strategy_panel.py    - 策略面板
├── datasource_panel.py  - 数据源面板
├── task_manager.py      - 任务管理器
└── enhanced_*           - 增强功能

Level 4: AI 功能层
├── ai_center.py         - AI 功能中心
├── ai_code_generator.py - AI 代码生成
└── llm_service.py       - LLM 服务

Level 5: 基础设施层
├── document.py          - 文档渲染
├── tables.py            - 表格处理
├── auth_routes.py       - 认证路由
└── monitor_routes.py    - 监控路由
```

---

## 📁 目录结构

```
deva/admin_ui/
├── __init__.py              # 包初始化
├── main_ui.py               # 主界面
├── runtime.py               # 运行时
├── contexts.py              # 上下文
│
├── # 核心 UI 模块
├── monitor_ui.py            # 监控界面
├── monitor_routes.py        # 监控路由
├── browser_ui.py            # 浏览器管理
├── config_ui.py             # 配置管理
├── follow_ui.py             # 关注管理
├── tasks.py                 # 任务管理
├── tables.py                # 表格处理
├── document.py              # 文档渲染
├── auth_routes.py           # 认证路由
├── llm_service.py           # LLM 服务
│
├── # AI 功能模块
├── ai_center.py             # AI 功能中心
│
└── strategy/                # 策略管理
    ├── __init__.py
    ├── base.py              # 基类
    ├── executable_unit.py   # 可执行单元
    │
    ├── # 策略管理
    ├── strategy_unit.py     # 策略单元
    ├── strategy_manager.py  # 策略管理器
    ├── strategy_panel.py    # 策略面板
    ├── enhanced_strategy_panel.py
    │
    ├── # 数据源管理
    ├── datasource.py        # 数据源
    ├── datasource_panel.py  # 数据源面板
    ├── enhanced_datasource_panel.py
    │
    ├── # 任务管理
    ├── task_unit.py         # 任务单元
    ├── task_manager.py      # 任务管理器
    ├── enhanced_task_panel.py
    ├── enhanced_task_admin.py
    │
    ├── # AI 代码生成
    ├── ai_code_generator.py          # AI 代码生成器
    ├── ai_code_generation_ui.py      # AI 代码生成 UI
    ├── ai_code_generation_dialog.py  # AI 代码生成对话框
    ├── interactive_ai_code_generator.py
    ├── ai_strategy_generator.py
    ├── task_ai_generator.py
    ├── complete_ai_workflow.py
    │
    ├── # 支持功能
    ├── logging_context.py     # 日志上下文
    ├── error_handler.py       # 错误处理
    ├── fault_tolerance.py     # 容错机制
    ├── persistence.py         # 持久化
    ├── history_db.py          # 历史数据库
    ├── result_store.py        # 结果存储
    │
    └── # 工具类
        ├── utils.py           # 工具函数
        ├── runtime.py         # 策略运行时
        ├── tradetime.py       # 交易时间
        └── stream_utils.py    # 流工具
```

---

## 🔧 核心模块说明

### 1. main_ui.py - 主界面

**功能：**
- 用户认证（Basic Auth）
- 导航菜单渲染
- 标签页管理
- 全局样式

**核心函数：**
```python
async def init_admin_ui(ctx, title)         # 初始化 Admin UI
async def render_main(ctx)                   # 渲染主界面
def create_nav_menu(ctx)                     # 创建导航菜单
async def summarize_tabs(ctx)                # 总结标签页
async def process_tabs(ctx, session)         # 处理标签页
```

**使用示例：**
```python
from deva.admin_ui.main_ui import init_admin_ui, render_main

# 初始化
await init_admin_ui(ctx, 'Deva 管理面板')

# 渲染主界面
await render_main(ctx)
```

---

### 2. strategy/strategy_manager.py - 策略管理器

**功能：**
- 策略的 CRUD 操作
- 策略状态管理
- 策略执行监控
- 血缘关系管理

**核心类：**
```python
class StrategyManager:
    def add_strategy(self, name, code)      # 添加策略
    def remove_strategy(self, name)         # 移除策略
    def get_strategy(self, name)            # 获取策略
    def list_strategies(self)               # 列出策略
    def update_strategy_state(self, name, state)  # 更新状态
```

**使用示例：**
```python
from deva.admin_ui.strategy.strategy_manager import get_strategy_manager

mgr = get_strategy_manager()

# 添加策略
mgr.add_strategy('my_strategy', code='...')

# 获取策略
strategy = mgr.get_strategy('my_strategy')

# 列出所有策略
strategies = mgr.list_strategies()
```

---

### 3. strategy/datasource.py - 数据源

**功能：**
- 数据源定义
- 数据获取逻辑
- 状态管理
- 持久化

**核心类：**
```python
class DataSource:
    def fetch_data(self)                    # 获取数据
    def start(self)                         # 启动数据源
    def stop(self)                          # 停止数据源
    def get_state(self)                     # 获取状态
    def persist(self)                       # 持久化
```

**使用示例：**
```python
from deva.admin_ui.strategy.datasource import DataSource

class MyDataSource(DataSource):
    def fetch_data(self):
        return {'data': 'value'}

ds = MyDataSource(name='my_ds')
ds.start()
```

---

### 4. ai_center.py - AI 功能中心

**功能：**
- AI 模型配置
- AI 代码生成
- 智能对话
- 功能演示

**核心函数：**
```python
def render_ai_tab_ui(ctx)                   # 渲染 AI Tab
async def show_ai_code_generator(ctx)       # 显示代码生成器
async def show_ai_chat(ctx)                 # 显示智能对话
async def show_llm_config_panel(ctx)        # 显示模型配置
```

**使用示例：**
```python
from deva.admin_ui.ai_center import render_ai_tab_ui

# 渲染 AI 功能中心
render_ai_tab_ui(ctx)
```

---

### 5. document.py - 文档渲染

**功能：**
- RST 文档渲染
- Markdown 渲染
- 文档缓存
- 模块文档扫描

**核心函数：**
```python
def render_document_ui(ctx)                 # 渲染文档 UI
def scan_document_modules()                 # 扫描文档模块
def _render_rst_to_html(rst_text)           # RST 转 HTML
def _build_document_tab(ctx, doc_info)      # 构建文档 Tab
```

---

## 🔄 数据流

### 策略管理流程

```
1. 用户创建策略
   ↓
2. StrategyPanel 接收请求
   ↓
3. StrategyManager 保存策略
   ↓
4. 持久化到 DBStream
   ↓
5. 更新 UI 显示
```

### AI 代码生成流程

```
1. 用户输入需求
   ↓
2. AI 代码生成器构建提示词
   ↓
3. 调用 LLM API
   ↓
4. 接收生成的代码
   ↓
5. 显示并允许编辑
   ↓
6. 用户确认后保存
```

### 数据源执行流程

```
1. DataSource.start()
   ↓
2. 定时执行 fetch_data()
   ↓
3. 数据发送到下游 Stream
   ↓
4. 状态更新到持久化存储
   ↓
5. UI 实时更新状态
```

---

## 🔐 安全机制

### 认证流程

```python
# 1. 检查是否已配置用户名密码
if not username or not password:
    # 显示创建账户界面
    show_create_account_ui()

# 2. Basic Auth 验证
user_name = await basic_auth(
    lambda u, p: u == username and p == password,
    secret=secret
)

# 3. 登录成功后创建会话
create_session(user_name)
```

### 权限控制

- 所有操作需要登录
- 敏感操作（删除、修改）需要确认
- API Key 等敏感信息脱敏显示

---

## 📊 性能优化

### 1. 缓存机制

```python
# 文档缓存
cache = {'data': None, 'ts': 0}
cache_ttl = 300  # 5 分钟

def scan_document_modules():
    now = time.time()
    if cache.get('data') and now - cache['ts'] < cache_ttl:
        return cache['data']  # 使用缓存
    # 重新加载
```

### 2. 异步处理

```python
# 使用 Tornado 异步
async def render_main(ctx):
    # 异步加载数据
    data = await load_data_async()
    # 渲染 UI
    render_ui(data)
```

### 3. 懒加载

```python
# 按需加载模块
def get_strategy_manager():
    from .strategy_manager import StrategyManager
    return StrategyManager()
```

---

## 🧪 测试

### 单元测试

```python
def test_strategy_manager():
    mgr = get_strategy_manager()
    
    # 测试添加策略
    mgr.add_strategy('test', 'code')
    assert 'test' in mgr.list_strategies()
    
    # 测试获取策略
    strategy = mgr.get_strategy('test')
    assert strategy is not None
```

### UI 测试

```python
def test_ai_center_ui():
    # 模拟用户操作
    ctx = create_test_context()
    
    # 测试模型配置
    show_llm_config_panel(ctx)
    
    # 测试代码生成
    await show_ai_code_generator(ctx)
```

---

## 📚 扩展开发

### 添加新 UI 模块

1. 创建模块文件：
```python
# my_feature.py
from pywebio.output import *
from pywebio.input import *

def render_my_feature(ctx):
    put_markdown("## 我的功能")
    # ... 实现逻辑
```

2. 在 main_ui.py 中添加菜单项：
```javascript
{name: '🔧 我的功能', path: '/myfeature', action: () => {
    window.location.href = '/myfeature';
}}
```

3. 在 admin.py 中注册路由：
```python
(r'/myfeature', webio_handler(my_feature, cdn=cdn))
```

---

## 🐛 调试技巧

### 1. 启用调试模式

```python
# admin.py
start_server(main, port=9999, debug=True)
```

### 2. 查看日志

```python
# 在代码中添加日志
(ctx['log'].info("调试信息"))
```

### 3. 对象检查

```python
# 使用文档 Tab 的对象检查功能
inspect_object(my_object)
```

---

## 📈 监控指标

### 系统指标

- CPU 使用率
- 内存使用率
- 请求响应时间
- 活跃连接数

### 业务指标

- 策略执行次数
- 数据源数据量
- 任务完成率
- AI 调用次数

---

**最后更新：** 2026-02-26  
**适用版本：** Deva v1.4.1+  
**维护者：** Deva 团队
