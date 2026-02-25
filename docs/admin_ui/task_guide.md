# Deva 任务管理指南

## 📖 概述

Deva 任务管理系统提供定时任务的创建、调度、监控和管理功能，支持 CRON 表达式和多种触发方式。

---

## 🚀 快速开始

### 1. 访问任务管理

```
1. 启动 Admin: `python -m deva.admin`
2. 访问：`http://127.0.0.1:9999`
3. 点击 **⏰ 任务** 菜单
```

### 2. 创建第一个任务

**方法 1：手动创建**

```python
from deva.admin_ui.strategy.task_unit import TaskUnit

class BackupTask(TaskUnit):
    """备份任务"""
    
    def execute(self):
        """执行备份逻辑"""
        self.backup_database()
        self.log.info('备份完成')
    
    def backup_database(self):
        # 备份逻辑
        pass
```

**方法 2：AI 生成**

```
1. 点击 **🤖 AI 生成任务**
2. 填写需求：
   - 任务名称：每日备份
   - 任务描述：每天凌晨备份数据库
   - 执行时间：每天 00:00
3. 点击 **生成代码**
4. 审查并保存
```

---

## 📋 任务类型

### 1. 定时任务

按固定间隔执行。

```python
from deva import timer

# 每 5 秒执行一次
timer(interval=5, func=lambda: "tick", start=True) >> log
```

### 2. CRON 任务

按 CRON 表达式执行。

```python
from deva import Stream

scheduler = Stream.scheduler()

# 每天 9 点执行
scheduler.add_job(
    func=daily_report,
    cron='0 9 * * *'
)
```

### 3. 一次性任务

只执行一次。

```python
# 延迟执行
import asyncio

async def delayed_task():
    await asyncio.sleep(10)
    print('执行任务')
```

---

## 🤖 AI 代码生成

### 支持的任务类型

1. **数据备份**
   - 数据库备份
   - 文件备份
   - 配置备份

2. **数据同步**
   - 数据库同步
   - 文件同步
   - API 同步

3. **报表生成**
   - 日报
   - 周报
   - 月报

4. **系统维护**
   - 清理缓存
   - 清理日志
   - 健康检查

### AI 生成示例

**输入需求：**
```
任务名称：数据清理任务
任务描述：清理 30 天前的旧数据
执行时间：每天凌晨 2 点
```

**生成的代码：**
```python
from deva.admin_ui.strategy.task_unit import TaskUnit
from datetime import datetime, timedelta

class DataCleanupTask(TaskUnit):
    """数据清理任务"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.retention_days = 30
    
    def execute(self):
        """
        执行数据清理
        """
        try:
            self.log.info('开始清理旧数据')
            
            # 计算清理日期
            cutoff_date = datetime.now() - timedelta(days=self.retention_days)
            
            # 清理数据库
            self.cleanup_database(cutoff_date)
            
            # 清理文件
            self.cleanup_files(cutoff_date)
            
            self.log.info(f'清理完成，删除了 30 天前的数据')
            
        except Exception as e:
            self.log.error(f'清理任务失败：{e}', exc_info=True)
            raise
    
    def cleanup_database(self, cutoff_date):
        """清理数据库中的旧数据"""
        import sqlite3
        
        conn = sqlite3.connect('data.db')
        cursor = conn.cursor()
        
        # 删除旧数据
        cursor.execute(
            'DELETE FROM data WHERE timestamp < ?',
            (cutoff_date.timestamp(),)
        )
        
        conn.commit()
        conn.close()
        
        self.log.info(f'数据库清理完成')
    
    def cleanup_files(self, cutoff_date):
        """清理旧文件"""
        import os
        from pathlib import Path
        
        data_dir = Path('data')
        cleaned = 0
        
        for file in data_dir.glob('*.dat'):
            mtime = datetime.fromtimestamp(file.stat().st_mtime)
            if mtime < cutoff_date:
                file.unlink()
                cleaned += 1
        
        self.log.info(f'清理了 {cleaned} 个文件')
```

---

## ⏰ 任务调度

### CRON 表达式

```
* * * * *
│ │ │ │ │
│ │ │ │ └─ 星期 (0-6, 0=周日)
│ │ │ └─── 月份 (1-12)
│ │ └───── 日期 (1-31)
│ └─────── 小时 (0-23)
└───────── 分钟 (0-59)
```

### 常用示例

```python
# 每分钟执行一次
* * * * *

# 每小时执行一次
0 * * * *

# 每天 9 点执行
0 9 * * *

# 每周一 9 点执行
0 9 * * 1

# 每月 1 号执行
0 0 1 * *
```

---

## 💾 持久化

### 任务配置存储

```python
from deva import NB

# 获取任务存储
task_store = NB('task_store', key_mode='explicit')

# 保存任务配置
task_store.upsert('backup_task', {
    'name': 'backup_task',
    'type': 'cron',
    'code': '...',
    'schedule': '0 2 * * *',
    'enabled': True,
    'created_at': '2026-02-26'
})

# 获取任务配置
config = task_store['backup_task']

# 列出所有任务
tasks = list(task_store.keys())
```

### 执行历史

```python
from deva.admin_ui.strategy.history_db import TaskHistoryDB

# 创建历史数据库
history_db = TaskHistoryDB('task_history.db')

# 保存执行历史
history_db.save_execution({
    'task_name': 'backup_task',
    'timestamp': '2026-02-26 02:00:00',
    'status': 'success',
    'duration': 5.2,
    'output': '备份完成'
})

# 查询历史
history = history_db.query('backup_task', limit=100)
```

---

## 📊 监控指标

### 实时指标

- **执行状态**：运行中/已停止
- **下次执行时间**：距离下次执行的时间
- **当前执行**：正在执行的任务

### 统计指标

- **总执行次数**：任务启动以来的执行次数
- **成功次数**：成功执行的次数
- **失败次数**：失败的次数
- **平均执行时间**：平均每次执行的时间
- **成功率**：成功执行比例

---

## 🔧 高级功能

### 1. 任务依赖

```python
# 设置任务依赖
mgr.add_task('task_a', code_a)
mgr.add_task('task_b', code_b)

# task_b 在 task_a 之后执行
mgr.add_dependency('task_b', 'task_a')
```

### 2. 任务分组

```python
# 创建任务组
mgr.create_group('daily_tasks')

# 添加任务到组
mgr.add_task_to_group('backup_task', 'daily_tasks')

# 执行组中的所有任务
mgr.execute_group('daily_tasks')
```

### 3. 任务重试

```python
class RetryTask(TaskUnit):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.max_retries = 3
    
    def execute(self):
        for i in range(self.max_retries):
            try:
                return self.do_work()
            except Exception as e:
                if i == self.max_retries - 1:
                    raise
                self.log.warning(f'重试 {i+1}/{self.max_retries}')
```

---

## ⚠️ 最佳实践

### 1. 错误处理

```python
class MyTask(TaskUnit):
    def execute(self):
        try:
            self.do_work()
        except Exception as e:
            self.log.error(f'任务执行失败：{e}', exc_info=True)
            # 发送告警
            self.send_alert(e)
            # 重试或放弃
            raise
```

### 2. 日志记录

```python
def execute(self):
    self.log.info('任务开始执行')
    
    start_time = time.time()
    
    try:
        result = self.do_work()
        duration = time.time() - start_time
        
        self.log.info(f'任务执行成功，耗时 {duration:.2f}秒')
        return result
        
    except Exception as e:
        duration = time.time() - start_time
        self.log.error(f'任务执行失败，耗时 {duration:.2f}秒：{e}')
        raise
```

### 3. 资源管理

```python
def execute(self):
    # 使用上下文管理器
    with self.get_resource() as resource:
        return self.do_work(resource)
    
    # 资源会自动释放
```

---

## 🐛 故障排查

### 问题 1：任务不执行

**可能原因：**
- 任务未启动
- 调度器未运行
- 时间配置错误

**解决方案：**
```python
# 1. 检查任务状态
# 在 Admin UI 中查看任务状态

# 2. 检查调度器
scheduler = Stream.scheduler()
scheduler.start()

# 3. 检查时间配置
# 确认 CRON 表达式正确
```

### 问题 2：任务执行失败

**可能原因：**
- 代码错误
- 资源不足
- 依赖服务不可用

**解决方案：**
```python
# 添加详细日志
def execute(self):
    self.log.info('任务开始')
    
    try:
        self.log.info('执行步骤 1')
        step1_result = self.step1()
        
        self.log.info('执行步骤 2')
        step2_result = self.step2(step1_result)
        
        self.log.info('任务完成')
        return step2_result
        
    except Exception as e:
        self.log.error(f'任务失败：{e}', exc_info=True)
        raise
```

---

## 📚 相关文档

- [策略管理](strategy_guide.md) - 策略管理
- [数据源管理](datasource_guide.md) - 数据源管理
- [AI 功能](ai_center_guide.md) - AI 代码生成

---

**最后更新：** 2026-02-26  
**适用版本：** Deva v1.4.1+
