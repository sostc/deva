---
name: datasource-creator
description: |
  帮助用户在 Naja 平台创建和上线数据源的 Skill。
  
  当用户想要创建新数据源、添加数据源、生成数据源代码时，使用此 Skill。
  
  使用方式：
  1. 用户提供数据源的需求描述（用自然语言说明想要什么数据源）
  2. AI 分析需求，自动推断数据源的各个字段（名称、类型、配置等）
  3. 对于无法分析出的字段，询问用户选择或回答来补全
  4. AI 生成数据源的 func_code 和 data_schema
  5. 将数据源保存到数据源数据库并立即生效（无需重启 naja）
  
  支持的数据源类型：
  - timer: 定时器数据源（定时获取数据）
  - file: 文件监控数据源（监控文件变化）
  - directory: 目录监控数据源（监控目录文件变化）
  - replay: 数据回放数据源（回放历史数据）
  - custom: 自定义数据源
  
  使用场景：
  - "帮我创建一个数据源"
  - "我想添加一个新的数据源"
  - "创建一个监控日志文件的数据源"
  - "创建一个定时获取股票行情的数据源"
  - "创建一个监控目录变化的数据源"
  - 任何涉及创建、生成、添加数据源的请求
---

# Datasource Creator Skill

## 概述

此 Skill 用于帮助用户在 Naja 平台快速创建完整的数据源，并**立即生效**（无需重启 naja）。

**核心特点：**
- AI 自动分析用户需求，推断数据源配置
- 对于不确定的字段，智能询问用户补全
- 自动生成 `func_code` 和 `data_schema`
- 支持多种数据源类型：timer/file/directory/replay
- **创建后立即生效** - 直接写入数据库，naja 自动检测并加载
- 可选择是否立即启动

## 使用流程

### 第一步：收集用户需求

向用户询问：
```
请描述您想要创建的数据源（例如：
- "创建一个定时获取股票行情的数据源，每5秒获取一次"
- "创建一个监控日志文件的数据源，当有新日志时触发"
- "创建一个监控下载目录的数据源，当有新文件时通知"
- "创建一个回放历史行情数据的数据源"
）
```

### 第二步：AI 分析需求并推断配置

AI 分析用户描述，推断以下字段：

#### 1. 数据源名称 (name)
- 根据描述自动生成（如："股票行情数据源"、"日志监控数据源"）
- 如果无法确定，询问用户

#### 2. 数据源类型 (source_type)
- **timer**: 定时获取数据（如：定时爬取网页、定时读取API）
- **file**: 监控单个文件（如：监控日志文件）
- **directory**: 监控整个目录（如：监控下载目录）
- **replay**: 回放历史数据（如：回放历史行情）
- **custom**: 自定义类型

推断规则：
- 包含"定时"、"每隔"、"每X秒/分钟" → timer
- 包含"文件"、"日志文件"、"监控文件" → file
- 包含"目录"、"文件夹"、"监控目录" → directory
- 包含"回放"、"历史数据"、"重放" → replay
- 无法确定 → 询问用户

#### 3. 执行间隔 (interval)
- timer 类型：提取描述中的时间（如："每5秒" → 5.0）
- 默认：5.0秒
- 如果描述中没有明确时间，询问用户

#### 4. 执行模式 (execution_mode)
- **timer**: 固定间隔执行（默认）
- **scheduler**: 计划调度（支持 cron 表达式）
- **event_trigger**: 事件触发

推断规则：
- 包含"cron"、"定时任务" → scheduler
- 包含"事件"、"触发" → event_trigger
- 其他 → timer

#### 5. 配置文件路径或目录路径
- file 类型：提取文件路径（如："/var/log/app.log"）
- directory 类型：提取目录路径（如："/Users/Downloads"）
- 如果描述中没有路径，询问用户

#### 6. 数据源描述 (description)
- 基于用户描述自动生成

### 第三步：询问补全不确定的字段

对于无法从描述中分析出的字段，向用户询问：

**示例询问：**
```
根据您的描述，我推断出以下配置：
- 名称：股票行情数据源
- 类型：timer
- 间隔：5秒

但还有以下信息需要确认：
1. 请提供数据获取的具体逻辑（如：从哪个API获取？如何解析数据？）
2. 数据格式包含哪些字段？（如：price, volume, symbol）
3. 是否立即启动数据源？（是/否）
```

### 第四步：生成 func_code

根据确定的配置生成 `func_code`：

#### timer 类型示例：
```python
def fetch_data():
    """
    获取股票行情数据
    """
    import time
    import random
    
    # TODO: 实现数据获取逻辑
    # 示例：模拟行情数据
    data = {
        "symbol": "AAPL",
        "price": round(random.uniform(100, 200), 2),
        "volume": random.randint(1000, 10000),
        "timestamp": time.time()
    }
    
    return data
```

#### file 类型示例：
```python
def fetch_data(line):
    """
    处理日志文件中的一行
    
    Args:
        line: 文件中的一行内容
    
    Returns:
        处理后的数据，返回 None 则跳过
    """
    import time
    
    if line and line.strip():
        return {
            "content": line.strip(),
            "timestamp": time.time()
        }
    
    return None
```

#### directory 类型示例：
```python
def fetch_data(event):
    """
    处理目录变化事件
    
    Args:
        event: {
            "event": "created" | "modified" | "deleted",
            "path": "文件路径",
            "file_info": {...}
        }
    
    Returns:
        处理后的数据
    """
    import time
    
    return {
        "event_type": event.get("event"),
        "file_path": event.get("path"),
        "timestamp": time.time()
    }
```

### 第五步：生成 data_schema

根据数据格式生成 `data_schema`：

```python
{
    "type": "tick",  # 根据数据内容推断：tick/news/log/file
    "description": "股票行情数据",
    "fields": [
        {"name": "symbol", "type": "string", "description": "股票代码", "required": True},
        {"name": "price", "type": "float", "description": "价格", "required": True},
        {"name": "volume", "type": "int", "description": "成交量", "required": True},
        {"name": "timestamp", "type": "float", "description": "时间戳", "required": True}
    ],
    "example": {
        "symbol": "AAPL",
        "price": 150.5,
        "volume": 1000,
        "timestamp": 1773168000.0
    }
}
```

### 第六步：保存并立即生效

**关键：使用直接数据库写入方式，无需重启 naja**

```python
from deva import NB
import hashlib
import time

# 生成唯一ID
datasource_id = hashlib.md5(f"{name}_{time.time()}".encode()).hexdigest()[:12]

# 构建完整的数据源记录
datasource_record = {
    "metadata": {
        "id": datasource_id,
        "name": name,
        "description": description,
        "tags": tags,
        "source_type": source_type,
        "config": config,  # 包含 data_schema
        "interval": interval,
        "execution_mode": execution_mode,
        "created_at": time.time(),
        "updated_at": time.time(),
    },
    "state": {
        "status": "stopped",  # 或 "running" 如果立即启动
        "start_time": 0,
        "last_activity_ts": 0,
        "error_count": 0,
        "last_error": "",
        "last_error_ts": 0,
        "run_count": 0,
        "last_data_ts": 0,
        "total_emitted": 0,
        "pid": 0,
    },
    "func_code": func_code,
    "was_running": False  # 设置为 True 如果希望 naja 自动恢复运行
}

# 直接保存到数据库 - 立即生效，无需重启
db = NB('naja_datasources')
db[datasource_id] = datasource_record
```

**生效机制：**
1. 数据源保存到数据库后立即生效
2. naja 会自动检测新数据源并编译代码
3. 如果 `was_running` 为 `true`，naja 会自动启动它
4. 刷新 Web 界面即可看到新数据源

### 第七步：展示结果

向用户展示创建结果：
```
数据源创建成功并已生效！

【基本信息】
- 名称：股票行情数据源
- ID：abc123def456
- 类型：timer
- 描述：定时获取股票行情数据，每5秒获取一次

【配置】
- 执行间隔：5秒
- 执行模式：timer

【数据格式】
- 类型：tick
- 字段：symbol, price, volume, timestamp

【状态】
- 已保存到数据库：✅
- 已编译代码：✅
- naja 已自动加载：✅
- 当前状态：stopped（可在 Web 界面启动）

【立即生效】
数据源已立即生效，无需重启 naja！
你可以：
1. 刷新 naja Web 界面（http://localhost:8080）查看新数据源
2. 点击"启动"按钮启动数据源
3. 或者使用生成的 ID 在代码中操作：abc123def456
```

## 辅助脚本

使用 `scripts/create_datasource.py` 辅助创建数据源：

```python
# 创建 timer 类型数据源（立即生效）
datasource_id = create_datasource(
    name="股票行情数据源",
    description="定时获取股票行情",
    source_type="timer",
    interval=5.0,
    func_code="...",
    data_schema={...},
    auto_start=False  # 是否立即启动
)

# 创建 file 类型数据源（立即生效）
datasource_id = create_datasource(
    name="日志监控",
    description="监控系统日志",
    source_type="file",
    config={
        "file_path": "/var/log/app.log",
        "poll_interval": 0.1,
        "read_mode": "tail"
    },
    func_code="...",
    auto_start=False
)

# 创建 directory 类型数据源（立即生效）
datasource_id = create_datasource(
    name="下载目录监控",
    description="监控下载目录",
    source_type="directory",
    config={
        "directory_path": "/Users/Downloads",
        "poll_interval": 1.0,
        "watch_events": ["created", "modified"]
    },
    func_code="...",
    auto_start=False
)
```

## 立即生效的实现方式

### 方式1：直接数据库写入（推荐）

```python
from deva import NB

def create_datasource_immediate(name, func_code, ...):
    """创建数据源并立即生效"""
    datasource_id = generate_id(name)
    
    record = build_record(name, func_code, ...)
    
    # 直接写入数据库
    db = NB('naja_datasources')
    db[datasource_id] = record
    
    return {
        "success": True,
        "id": datasource_id,
        "message": "数据源已创建并立即生效，无需重启 naja"
    }
```

### 方式2：使用 DataSourceManager

```python
from deva.naja.datasource import get_datasource_manager

def create_datasource_via_manager(name, func_code, ...):
    """通过管理器创建数据源"""
    mgr = get_datasource_manager()
    
    result = mgr.create(
        name=name,
        func_code=func_code,
        interval=interval,
        source_type=source_type,
        ...
    )
    
    return result
```

**注意**：使用 DataSourceManager 时，如果 naja 正在运行，可能需要等待管理器实例同步。

## 注意事项

1. **立即生效**：直接写入数据库的方式可以确保数据源立即生效，无需重启 naja
2. **自动检测**：naja 会自动检测数据库中的新数据源并编译代码
3. **代码质量**：生成的代码应该包含完整的注释和错误处理
4. **数据格式**：自动生成 data_schema，便于策略使用
5. **用户确认**：在保存前让用户确认所有配置信息
6. **唯一性检查**：保存前检查名称是否已存在
7. **ID生成**：使用 `hashlib.md5(f"{name}_{time.time()}".encode()).hexdigest()[:12]`
