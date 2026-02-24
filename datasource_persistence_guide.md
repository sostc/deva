# 数据源状态持久化使用指南

## 概述

数据源状态持久化系统提供了完整的状态保存、恢复和管理功能，确保程序重启后能够恢复之前的运行状态。

## 核心功能

### 1. 自动状态保存

数据源在以下情况下会自动保存状态到数据库：

- **启动时**：保存运行状态、进程ID、时间戳
- **停止时**：保存停止状态和相关统计信息
- **出错时**：保存错误状态和错误信息
- **数据更新时**：保存最新数据和元数据
- **代码变更时**：保存代码版本历史

### 2. 状态恢复机制

程序重启时自动执行：

- 从数据库加载所有数据源配置
- 恢复之前的运行状态
- 验证状态一致性
- 自动启动之前运行的数据源

### 3. 代码版本管理

- 每次代码更新自动保存版本历史
- 支持代码回滚和版本对比
- 完整的变更记录和时间戳

## 使用示例

### 基本使用

```python
from deva.admin_ui.strategy.datasource import DataSource, DataSourceManager, DataSourceType

# 创建数据源管理器
manager = DataSourceManager()

# 创建定时数据源
source = DataSource(
    name="my_data_source",
    source_type=DataSourceType.TIMER,
    description="我的数据源",
    data_func_code='''
import pandas as pd
import time

def fetch_data():
    return pd.DataFrame({
        'timestamp': [time.time()],
        'value': [42]
    })
''',
    interval=5.0,
    auto_start=False
)

# 注册数据源（自动保存到数据库）
manager.register(source)

# 启动数据源（自动保存运行状态）
source.start()

# 停止数据源（自动保存停止状态）
source.stop()
```

### 程序重启恢复

```python
# 程序重启时，自动恢复之前的状态
manager = DataSourceManager()

# 从数据库加载所有数据源
loaded_count = manager.load_from_db()
print(f"加载了 {loaded_count} 个数据源")

# 恢复之前运行的数据源
restore_result = manager.restore_running_states()
print(f"恢复了 {restore_result['restored_count']} 个数据源")
```

### 代码版本管理

```python
# 更新数据获取代码
new_code = '''
import pandas as pd

def fetch_data():
    return pd.DataFrame({
        'timestamp': [pd.Timestamp.now()],
        'value': [100],
        'status': ['updated']
    })
'''

result = source.update_data_func_code(new_code)
print(f"代码更新结果: {result}")

# 获取代码版本历史
versions = source.get_code_versions(5)
for version in versions:
    print(f"版本时间: {version['timestamp']}")
```

### 状态监控

```python
# 获取完整状态摘要
summary = source.get_full_state_summary()
print(f"数据源状态: {summary['current_status']}")
print(f"运行统计: {summary['current_stats']}")
print(f"错误计数: {summary['current_stats']['error_count']}")

# 获取保存的运行状态
saved_state = source.get_saved_running_state()
print(f"保存的运行状态: {saved_state['is_running']}")

# 获取保存的最新数据
saved_data = source.get_saved_latest_data()
print(f"最新数据时间: {saved_data['timestamp']}")
```

### 状态导出导入

```python
# 导出完整状态（用于备份）
export_data = source.export_state(include_data=True, include_code=True)
print(f"导出状态包含 {len(export_data)} 个字段")

# 导入状态（用于恢复或迁移）
new_source = DataSource(name="restored_source")
import_result = new_source.import_state(export_data, merge=False)
print(f"状态导入结果: {import_result}")
```

## 数据库结构

### 主要数据表

1. **data_sources**: 主数据源配置表
   - 数据源元数据、状态、统计信息
   - 依赖关系、配置参数

2. **data_source_states**: 运行状态表
   - 实时运行状态、进程ID
   - 最后更新时间、错误信息

3. **data_source_latest_data**: 最新数据表
   - 最新获取的数据内容
   - 数据类型、时间戳、大小

4. **data_source_code_versions**: 代码版本表
   - 代码变更历史
   - 版本对比、回滚支持

### 状态保存时机

| 操作 | 保存内容 | 数据库表 |
|------|----------|----------|
| 启动 | 运行状态、PID、时间戳 | data_source_states |
| 停止 | 停止状态、统计信息 | data_sources, data_source_states |
| 错误 | 错误信息、错误计数 | data_sources, data_source_states |
| 数据更新 | 最新数据、元数据 | data_source_latest_data |
| 代码更新 | 代码版本、变更历史 | data_source_code_versions |

## 错误处理

### 自动错误恢复

```python
# 数据源在出错时会自动：
# 1. 记录错误信息到状态
# 2. 增加错误计数
# 3. 保存错误状态到数据库
# 4. 继续尝试运行（根据配置）

# 检查错误状态
if source.state.status == "error":
    print(f"错误信息: {source.state.last_error}")
    print(f"错误计数: {source.state.error_count}")
    
    # 可以尝试重启
    source.stop()
    source.start()
```

### 状态一致性检查

```python
# 程序重启时会进行状态一致性检查
restore_result = manager.restore_running_states()

for result in restore_result['results']:
    if not result['success']:
        print(f"恢复失败: {result['error']}")
        if result.get('skipped'):
            print("状态检查跳过恢复")
```

## 最佳实践

### 1. 代码规范

- 数据获取函数必须命名为 `fetch_data`
- 函数必须返回有效数据或 `None`
- 包含必要的错误处理
- 添加适当的文档字符串

### 2. 状态监控

- 定期检查数据源状态
- 监控错误计数和频率
- 关注数据更新频率
- 及时处理异常状态

### 3. 备份策略

- 定期导出重要数据源状态
- 保存关键配置和代码版本
- 测试状态恢复流程
- 建立灾难恢复计划

### 4. 性能优化

- 合理设置数据保存间隔
- 控制状态历史数据大小
- 定期清理过期状态数据
- 优化数据库查询性能

## 故障排除

### 常见问题

1. **状态未保存**
   - 检查数据库连接
   - 确认自动保存配置
   - 查看错误日志

2. **状态恢复失败**
   - 验证状态数据完整性
   - 检查依赖关系
   - 确认代码版本兼容性

3. **代码更新失败**
   - 验证代码语法正确性
   - 确保包含 `fetch_data` 函数
   - 检查函数返回值类型

### 调试工具

```python
# 获取完整状态信息
debug_info = source.get_full_state_summary()
print(f"调试信息: {debug_info}")

# 检查保存的运行状态
saved_state = source.get_saved_running_state()
print(f"保存状态: {saved_state}")

# 查看最近的数据
recent_data = source.get_recent_data(5)
print(f"最近数据: {len(recent_data)} 条")
```

## 总结

数据源状态持久化系统提供了：

- ✅ **完整的状态保存**：运行状态、代码、数据、错误信息
- ✅ **自动状态恢复**：程序重启后自动恢复运行
- ✅ **代码版本管理**：支持代码回滚和版本追踪
- ✅ **错误处理机制**：自动错误记录和状态保存
- ✅ **状态导出导入**：支持备份、迁移和恢复
- ✅ **实时监控**：提供完整的状态监控和调试功能

这套系统确保了数据源的高可用性和可靠性，为生产环境提供了坚实的状态管理基础。