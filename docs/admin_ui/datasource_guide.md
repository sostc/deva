# Deva 数据源管理指南

## 📖 概述

Deva 数据源管理系统提供统一的数据采集、处理和分发功能，支持多种数据源类型和 AI 代码生成。

---

## 🏗️ 架构设计

### 核心组件

```
┌─────────────────────────────────────────────────────────┐
│                数据源管理架构                            │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │  DataSourcePanel (数据源面板 - UI 层)             │   │
│  ├─────────────────────────────────────────────────┤   │
│  │  - 数据源列表                                    │   │
│  │  - 数据源详情                                    │   │
│  │  - 数据源编辑                                    │   │
│  └─────────────────────────────────────────────────┘   │
│                            ↓                            │
│  ┌─────────────────────────────────────────────────┐   │
│  │  DataSourceManager (数据源管理器)                │   │
│  ├─────────────────────────────────────────────────┤   │
│  │  - CRUD 操作                                     │   │
│  │  - 状态管理                                      │   │
│  │  - 血缘关系                                      │   │
│  └─────────────────────────────────────────────────┘   │
│                            ↓                            │
│  ┌─────────────────────────────────────────────────┐   │
│  │  DataSource (数据源基类)                         │   │
│  ├─────────────────────────────────────────────────┤   │
│  │  - fetch_data()                                  │   │
│  │  - start() / stop()                              │   │
│  │  - persist()                                     │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## 🚀 快速开始

### 1. 访问数据源管理

```
1. 启动 Admin: `python -m deva.admin`
2. 访问：`http://127.0.0.1:9999`
3. 点击 **📡 数据源** 菜单
```

### 2. 创建第一个数据源

**方法 1：手动创建**

```python
from deva.admin_ui.datasource import DataSource

class TimerDataSource(DataSource):
    """定时器数据源"""
    
    def fetch_data(self):
        import time
        return {
            'timestamp': time.time(),
            'datetime': time.strftime('%Y-%m-%d %H:%M:%S')
        }
```

**方法 2：AI 生成**

```
1. 点击 **🤖 AI 生成数据源**
2. 填写需求：
   - 名称：股票数据源
   - 描述：从 Yahoo Finance 获取股票数据
   - 数据类型：dict
   - 更新频率：5 秒
3. 点击 **生成代码**
4. 审查并保存
```

---

## 📋 数据源类型

### 1. Timer 数据源

定时执行，返回固定数据。

```python
class TimerDataSource(DataSource):
    def fetch_data(self):
        return {'count': self.counter}
```

### 2. HTTP 数据源

从 HTTP API 获取数据。

```python
class HTTPDataSource(DataSource):
    def fetch_data(self):
        import requests
        response = requests.get('https://api.example.com/data')
        return response.json()
```

### 3. 文件数据源

从文件读取数据。

```python
class FileDataSource(DataSource):
    def fetch_data(self):
        with open('data.txt', 'r') as f:
            return f.read()
```

### 4. 数据库数据源

从数据库查询数据。

```python
class DatabaseDataSource(DataSource):
    def fetch_data(self):
        import sqlite3
        conn = sqlite3.connect('data.db')
        df = pd.read_sql('SELECT * FROM table', conn)
        return df.to_dict()
```

---

## 🤖 AI 代码生成

### 支持的数据源类型

1. **API 数据源**
   - REST API
   - GraphQL
   - WebSocket

2. **文件数据源**
   - CSV 文件
   - JSON 文件
   - Excel 文件

3. **数据库数据源**
   - SQLite
   - MySQL
   - PostgreSQL

4. **消息队列**
   - Kafka
   - Redis Stream
   - RabbitMQ

### AI 生成示例

**输入需求：**
```
数据源名称：天气数据源
数据源描述：从 OpenWeatherMap API 获取天气数据
数据类型：dict
更新频率：60 秒
```

**生成的代码：**
```python
from deva.admin_ui.datasource import DataSource
import requests

class WeatherDataSource(DataSource):
    """天气数据源"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.api_key = 'your_api_key'
        self.city = 'Beijing'
    
    def fetch_data(self):
        """
        获取天气数据
        
        Returns:
            dict: 包含温度、湿度等信息
        """
        try:
            url = f'http://api.openweathermap.org/data/2.5/weather'
            params = {
                'q': self.city,
                'appid': self.api_key,
                'units': 'metric'
            }
            
            response = requests.get(url, params=params)
            data = response.json()
            
            return {
                'temperature': data['main']['temp'],
                'humidity': data['main']['humidity'],
                'description': data['weather'][0]['description'],
                'timestamp': time.time()
            }
            
        except Exception as e:
            self.log.error(f'获取天气数据失败：{e}')
            return None
```

---

## 💾 持久化

### 数据源配置存储

```python
from deva import NB

# 获取数据源存储
datasource_store = NB('datasource_store', key_mode='explicit')

# 保存数据源配置
datasource_store.upsert('weather_ds', {
    'name': 'weather_ds',
    'type': 'http',
    'code': '...',
    'config': {
        'url': 'http://api.openweathermap.org',
        'interval': 60
    },
    'created_at': '2026-02-26'
})

# 获取数据源配置
config = datasource_store['weather_ds']

# 列出所有数据源
datasources = list(datasource_store.keys())
```

### 数据持久化

```python
from deva import DBStream

# 创建数据存储
data_store = DBStream('weather_data.db', 'weather')

# 保存数据
data_store.append({
    'temperature': 25.5,
    'humidity': 60,
    'timestamp': time.time()
})

# 查询数据
for data in data_store[:100]:
    print(data)
```

---

## 📊 监控指标

### 实时指标

- **运行状态**：运行中/已停止
- **数据频率**：每秒数据量
- **响应时间**：平均获取数据时间
- **成功率**：成功获取数据比例

### 统计指标

- **总数据量**：采集的数据总量
- **成功次数**：成功获取数据次数
- **失败次数**：失败次数
- **平均响应时间**：平均每次获取的时间

---

## 🔧 高级功能

### 1. 数据源血缘关系

```python
# 查看数据源的上下游
from deva.admin_ui.datasource import get_ds_manager as get_datasource_manager

mgr = get_datasource_manager()

# 获取数据源信息
ds_info = mgr.get_datasource('weather_ds')

# 查看使用该数据源的策略
strategies = ds_info.get('downstream_strategies', [])
print(f"使用该数据源的策略：{strategies}")
```

### 2. 数据源版本管理

```python
# 保存版本
mgr.save_version('weather_ds', version='1.0.0', comment='初始版本')

# 查看版本历史
versions = mgr.get_versions('weather_ds')

# 回滚
mgr.rollback('weather_ds', version='1.0.0')
```

---

## ⚠️ 最佳实践

### 1. 错误处理

```python
class MyDataSource(DataSource):
    def fetch_data(self):
        try:
            # 获取数据
            data = self.get_data()
            return data
        except requests.Timeout:
            self.log.error('请求超时')
            return None
        except Exception as e:
            self.log.error(f'获取数据失败：{e}', exc_info=True)
            return None
```

### 2. 数据验证

```python
def fetch_data(self):
    data = self.get_data()
    
    # 验证数据格式
    if not isinstance(data, dict):
        self.log.error('数据格式错误')
        return None
    
    # 验证必要字段
    required_fields = ['temperature', 'humidity']
    for field in required_fields:
        if field not in data:
            self.log.error(f'缺少字段：{field}')
            return None
    
    return data
```

### 3. 性能优化

```python
# 使用缓存
from functools import lru_cache

class MyDataSource(DataSource):
    @lru_cache(maxsize=100)
    def get_cached_data(self, key):
        return self.fetch_from_api(key)
    
    def fetch_data(self):
        return self.get_cached_data('weather')
```

---

## 🐛 故障排查

### 问题 1：数据源无法启动

**可能原因：**
- 代码有语法错误
- 缺少必要的导入
- 配置参数错误

**解决方案：**
```python
# 1. 检查代码语法
python -m py_compile datasource.py

# 2. 检查导入
from deva.admin_ui.datasource import DataSource

# 3. 检查配置
# 在 Admin UI 中查看数据源配置
```

### 问题 2：数据获取失败

**可能原因：**
- 网络连接问题
- API 密钥无效
- 数据格式错误

**解决方案：**
```python
# 添加详细日志
def fetch_data(self):
    self.log.info('开始获取数据')
    
    try:
        data = self.get_data()
        self.log.info(f'获取到数据：{data}')
        return data
    except Exception as e:
        self.log.error(f'获取数据失败：{e}', exc_info=True)
        raise
```

---

## 📚 相关文档

- [策略管理](strategy_guide.md) - 策略管理
- [任务管理](task_guide.md) - 任务管理
- [AI 功能](ai_center_guide.md) - AI 代码生成

---

**最后更新：** 2026-02-26  
**适用版本：** Deva v1.4.1+
