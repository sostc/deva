# 策略和数据源日志上下文增强系统

## 概述

本系统为策略和数据源的日志记录及告警提供了增强的上下文信息功能。所有日志和告警现在都会自动携带具体的策略和数据源信息，便于问题追踪和故障排查。

## 核心功能

### 1. 增强的日志上下文管理

#### 日志上下文类 (LoggingContext)
```python
@dataclass
class LoggingContext:
    strategy_id: Optional[str] = None      # 策略ID
    strategy_name: Optional[str] = None  # 策略名称
    datasource_id: Optional[str] = None    # 数据源ID
    datasource_name: Optional[str] = None # 数据源名称
    source_type: Optional[str] = None      # 数据源类型
    extra_context: Dict[str, Any] = field(default_factory=dict)  # 额外上下文
```

#### 日志上下文管理器 (LoggingContextManager)
- 使用线程本地存储管理当前线程的日志上下文
- 提供策略上下文、数据源上下文和组合上下文管理器
- 支持装饰器模式包装函数

### 2. 策略日志增强

#### 自动上下文注入
所有策略相关的日志现在都会自动包含：
- 策略ID和名称
- 绑定的数据源信息（如果存在）
- 执行状态和处理统计

#### 使用示例
```python
# 策略事件日志
log_strategy_event("INFO", "策略启动成功", strategy_unit=my_strategy)

# 手动记录策略日志
strategy_log("ERROR", "策略执行失败", strategy_id="strategy_123", strategy_name="测试策略")

# 使用装饰器
@with_strategy_logging("strategy_id", "策略名称")
def my_strategy_function(data):
    return data * 2
```

### 3. 数据源日志增强

#### 自动上下文注入
所有数据源相关的日志现在都会自动包含：
- 数据源ID和名称
- 数据源类型（timer/stream/http/kafka/redis等）
- 配置参数和状态信息

#### 使用示例
```python
# 数据源事件日志
log_datasource_event("INFO", "数据源连接成功", datasource=my_datasource)

# 手动记录数据源日志
datasource_log("WARNING", "数据源连接超时", datasource_id="ds_123", datasource_name="行情数据")

# 使用装饰器
@with_datasource_logging("datasource_id", "数据源名称", "stream")
def my_datasource_function():
    return {"data": "test"}
```

### 4. 告警系统增强

#### 告警消息格式
告警消息现在包含丰富的上下文信息：

```
[2026-02-25 19:01:04][ERROR][deva.alert.strategy.告警测试策略] [策略[告警测试策略]] 策略执行异常 | {
    "strategy_id": "be38757e16e3",
    "strategy_name": "告警测试策略", 
    "alert_id": "fa1de7f3dd87",
    "severity": "error",
    "details": {"error_type": "ValueError", "error_message": "无效参数"}
}
```

#### 钉钉告警增强
钉钉告警消息现在包含：
- 策略名称和ID
- 数据源名称和类型
- 错误类型和详细信息
- 时间戳和告警级别

示例钉钉消息：
```markdown
### 🚨 策略告警
- **策略**: 告警测试策略
- **数据源**: 告警测试数据源
- **类型**: http
- **级别**: CRITICAL
- **消息**: 数据源连接失败
- **时间**: 2026-02-25T19:01:04.220806
- **策略ID**: be38757e16e3
- **数据源ID**: fdffaaa833c1
- **错误类型**: ConnectionError
- **错误详情**: 无法连接到数据源
```

### 5. 错误处理增强

#### SafeProcessor 增强
错误记录现在包含：
- 策略和数据源上下文
- 增强的错误消息格式
- 详细的错误分类信息

#### 错误消息格式
```
[策略[策略名称]|数据源[数据源名称]] 原始错误消息
```

## 使用指南

### 基本使用

1. **策略日志记录**
```python
from deva.admin_ui.strategy.logging_context import log_strategy_event

# 在策略类中使用
class MyStrategy(StrategyUnit):
    def process(self, data):
        log_strategy_event("INFO", "开始处理数据", strategy_unit=self)
        # ... 处理逻辑 ...
        log_strategy_event("ERROR", "处理失败", strategy_unit=self)
```

2. **数据源日志记录**
```python
from deva.admin_ui.strategy.logging_context import log_datasource_event

# 在数据源类中使用
class MyDataSource(DataSource):
    def fetch_data(self):
        log_datasource_event("INFO", "开始获取数据", datasource=self)
        # ... 获取逻辑 ...
        log_datasource_event("WARNING", "获取超时", datasource=self)
```

### 高级使用

1. **组合上下文**
```python
from deva.admin_ui.strategy.logging_context import logging_context_manager

# 同时包含策略和数据源上下文
with logging_context_manager.combined_context(
    strategy_id="strategy_123",
    strategy_name="我的策略",
    datasource_id="ds_456", 
    datasource_name="我的数据源",
    source_type="stream"
):
    # 所有日志都会包含策略和数据源信息
    log_strategy_event("INFO", "策略和数据源协同工作")
```

2. **装饰器模式**
```python
from deva.admin_ui.strategy.logging_context import with_strategy_logging

@with_strategy_logging("strategy_123", "数据处理策略")
def process_data(data):
    # 函数执行期间的日志都会包含策略上下文
    return data * 2
```

### 集成现有代码

#### 策略单元集成
策略单元类已经自动集成了增强日志系统，所有内部日志都会包含策略上下文。

#### 数据源集成
数据源类已经自动集成了增强日志系统，所有内部日志都会包含数据源上下文。

#### 自定义组件
对于自定义组件，可以使用提供的日志函数：

```python
from deva.admin_ui.strategy.logging_context import (
    strategy_log, 
    datasource_log,
    create_enhanced_log_record
)

# 记录策略相关日志
strategy_log("INFO", "自定义策略消息", strategy_id="id", strategy_name="name")

# 记录数据源相关日志  
datasource_log("ERROR", "自定义数据源错误", datasource_id="id", datasource_name="name")

# 创建增强日志记录
record = create_enhanced_log_record("WARNING", "警告消息", "my.component")
record >> log  # 发送到deva日志系统
```

## 配置选项

### 环境变量
- `DEVA_LOG_LEVEL`: 设置日志级别 (DEBUG/INFO/WARNING/ERROR/CRITICAL)
- `DEVA_LOG_FORWARD_TO_LOGGING`: 是否转发到标准logging系统

### 告警配置
```python
from deva.admin_ui.strategy.fault_tolerance import AlertConfig

config = AlertConfig(
    enable_dtalk=True,              # 启用钉钉通知
    enable_log=True,                # 启用日志记录
    dtalk_threshold=3,             # 钉钉发送阈值
    dtalk_window_seconds=300,       # 时间窗口
    max_alerts_per_hour=100,       # 每小时最大告警数
    critical_immediate=True         # 关键告警立即发送
)
```

## 最佳实践

1. **一致性**: 始终使用提供的日志函数，确保上下文信息的一致性
2. **完整性**: 在创建策略和数据源时提供完整的元数据信息
3. **错误处理**: 使用SafeProcessor包装可能出错的函数
4. **监控**: 定期检查告警历史和错误统计
5. **调试**: 在开发环境中使用DEBUG级别日志获取详细信息

## 故障排查

### 常见问题

1. **上下文信息缺失**
   - 确保使用正确的日志函数
   - 检查策略和数据源是否正确初始化
   - 验证线程上下文是否正确设置

2. **告警未发送**
   - 检查钉钉配置是否正确
   - 验证告警阈值设置
   - 查看每小时告警数量限制

3. **日志格式异常**
   - 检查日志级别设置
   - 验证上下文管理器状态
   - 确认deva日志系统正常运行

### 调试技巧

1. **查看当前上下文**
```python
from deva.admin_ui.strategy.logging_context import get_logging_context

context = get_logging_context()
print(f"当前上下文: {context.to_dict()}")
```

2. **测试日志输出**
```python
from deva.admin_ui.strategy.logging_context import create_enhanced_log_record

record = create_enhanced_log_record("INFO", "测试消息")
print(f"日志记录: {record}")
```

## 总结

增强的日志和告警系统为策略和数据源的运行提供了完整的上下文信息，大大提升了问题诊断和故障排查的效率。通过自动注入策略和数据源信息，所有日志和告警都具备了可追溯性，为生产环境的稳定运行提供了有力保障。