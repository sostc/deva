# Deva 策略管理指南

## 📖 概述

Deva 策略管理系统提供完整的量化策略生命周期管理，包括策略创建、编辑、执行、监控和回测。

---

## 🏗️ 架构设计

### 核心组件

```
┌─────────────────────────────────────────────────────────┐
│                   策略管理架构                           │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │  StrategyPanel (策略面板 - UI 层)                 │   │
│  ├─────────────────────────────────────────────────┤   │
│  │  - 策略列表                                      │   │
│  │  - 策略详情                                      │   │
│  │  - 策略编辑                                      │   │
│  └─────────────────────────────────────────────────┘   │
│                            ↓                            │
│  ┌─────────────────────────────────────────────────┐   │
│  │  StrategyManager (策略管理器 - 业务逻辑层)        │   │
│  ├─────────────────────────────────────────────────┤   │
│  │  - CRUD 操作                                     │   │
│  │  - 状态管理                                      │   │
│  │  - 血缘关系                                      │   │
│  └─────────────────────────────────────────────────┘   │
│                            ↓                            │
│  ┌─────────────────────────────────────────────────┐   │
│  │  StrategyUnit (策略单元 - 执行层)                │   │
│  ├─────────────────────────────────────────────────┤   │
│  │  - 策略执行                                      │   │
│  │  - 错误处理                                      │   │
│  │  - 日志记录                                      │   │
│  └─────────────────────────────────────────────────┘   │
│                            ↓                            │
│  ┌─────────────────────────────────────────────────┐   │
│  │  Persistence (持久化层)                          │   │
│  ├─────────────────────────────────────────────────┤   │
│  │  - DBStream 存储                                 │   │
│  │  - 历史数据库                                    │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## 🚀 快速开始

### 1. 访问策略管理

```
1. 启动 Admin: `python -m deva.admin`
2. 访问：`http://127.0.0.1:9999`
3. 点击 **📈 策略** 菜单
```

### 2. 创建第一个策略

**方法 1：手动创建**

```
1. 点击 **➕ 创建策略**
2. 填写策略信息：
   - 名称：双均线策略
   - 代码：
```python
from deva import StrategyUnit

class MovingAverageStrategy(StrategyUnit):
    """双均线策略"""
    
    def process(self, data):
        close = data.get('close', [])
        if len(close) < 20:
            return 'hold'
        
        ma5 = sum(close[-5:]) / 5
        ma20 = sum(close[-20:]) / 20
        
        if ma5 > ma20:
            return 'buy'
        elif ma5 < ma20:
            return 'sell'
        else:
            return 'hold'
```
3. 点击 **保存**
4. 启动策略

**方法 2：AI 生成**

```
1. 点击 **🤖 AI 生成策略**
2. 填写需求：
   - 名称：双均线策略
   - 描述：当 5 日均线上穿 20 日均线时买入，下穿时卖出
   - 输入数据：股票 K 线数据
   - 输出格式：交易信号（buy/sell/hold）
3. 点击 **生成代码**
4. 审查生成的代码
5. 确认后保存
```

---

## 📋 策略管理功能

### 1. 策略列表

**功能：**
- 查看所有策略
- 策略状态（运行中/已停止）
- 策略描述
- 创建时间
- 最后更新时间

**操作：**
- 启动/停止策略
- 编辑策略代码
- 查看策略详情
- 删除策略

### 2. 策略详情

**显示信息：**
- 策略名称
- 策略代码
- 策略描述
- 输入数据源
- 输出数据流
- 执行状态
- 执行统计（执行次数、成功率等）

### 3. 策略编辑

**支持功能：**
- 代码编辑（语法高亮）
- 代码验证
- 版本历史
- 代码对比

### 4. 策略执行

**执行流程：**
```
1. 用户点击启动
2. StrategyManager 创建 StrategyUnit
3. 连接输入数据源
4. 开始执行 process() 方法
5. 输出结果到下游
6. 状态实时更新
```

---

## 🤖 AI 代码生成

### 支持的策略类型

1. **技术指标策略**
   - 均线策略
   - MACD 策略
   - RSI 策略
   - KDJ 策略

2. **统计套利策略**
   - 配对交易
   - 均值回归
   - 动量策略

3. **机器学习策略**
   - 分类预测
   - 回归预测
   - 聚类分析

### AI 生成示例

**输入需求：**
```
策略名称：MACD 策略
策略描述：使用 MACD 指标生成交易信号，金叉买入，死叉卖出
输入数据：股票 K 线数据（包含收盘价）
输出格式：交易信号（buy/sell/hold）
```

**生成的代码：**
```python
from deva import StrategyUnit
import pandas as pd

class MACDStrategy(StrategyUnit):
    """MACD 策略"""
    
    def process(self, data):
        """
        计算 MACD 并生成交易信号
        
        Args:
            data: 包含收盘价的字典 {'close': [...]}
        
        Returns:
            交易信号：'buy', 'sell', 或 'hold'
        """
        try:
            close = pd.Series(data.get('close', []))
            
            if len(close) < 26:
                return 'hold'
            
            # 计算 EMA
            ema12 = close.ewm(span=12).mean()
            ema26 = close.ewm(span=26).mean()
            
            # 计算 DIF
            dif = ema12 - ema26
            
            # 计算 DEA
            dea = dif.ewm(span=9).mean()
            
            # 计算 MACD 柱
            macd = 2 * (dif - dea)
            
            # 生成信号
            if macd.iloc[-1] > 0 and macd.iloc[-2] <= 0:
                return 'buy'  # 金叉
            elif macd.iloc[-1] < 0 and macd.iloc[-2] >= 0:
                return 'sell'  # 死叉
            else:
                return 'hold'
                
        except Exception as e:
            self.log.error(f'策略执行错误：{e}')
            return 'hold'
```

---

## 💾 持久化

### 策略存储

```python
from deva import NB

# 获取策略存储
strategy_store = NB('strategy_store', key_mode='explicit')

# 保存策略
strategy_store.upsert('my_strategy', {
    'name': 'my_strategy',
    'code': '...',
    'description': '策略描述',
    'created_at': '2026-02-26',
    'updated_at': '2026-02-26'
})

# 获取策略
strategy = strategy_store['my_strategy']

# 列出所有策略
strategies = list(strategy_store.keys())
```

### 状态持久化

```python
# 策略状态自动保存
state = {
    'status': 'running',
    'last_executed': '2026-02-26 10:00:00',
    'executed_count': 100,
    'success_count': 98,
    'error_count': 2
}

# 保存到状态存储
state_store = NB('strategy_state')
state_store.upsert('my_strategy', state)
```

### 历史数据

```python
from deva.admin.strategy.history_db import StrategyHistoryDB

# 创建历史数据库
history_db = StrategyHistoryDB('strategy_history.db')

# 保存执行历史
history_db.save_execution({
    'strategy_name': 'my_strategy',
    'timestamp': '2026-02-26 10:00:00',
    'input_data': {...},
    'output_data': 'buy',
    'execution_time': 0.05
})

# 查询历史
history = history_db.query('my_strategy', limit=100)
```

---

## 📊 监控指标

### 实时指标

- **执行状态**：运行中/已停止
- **执行频率**：每秒执行次数
- **成功率**：成功执行比例
- **响应时间**：平均执行时间

### 统计指标

- **总执行次数**：策略启动以来的执行次数
- **成功次数**：成功执行的次数
- **失败次数**：失败的次数
- **平均响应时间**：平均每次执行的时间

### 业务指标

- **收益率**：策略的收益率
- **夏普比率**：风险调整后收益
- **最大回撤**：最大亏损幅度
- **胜率**：盈利交易比例

---

## 🔧 高级功能

### 1. 策略血缘关系

```python
# 查看策略的上下游
from deva.admin.strategy.strategy_manager import get_strategy_manager

mgr = get_strategy_manager()

# 获取策略信息
strategy_info = mgr.get_strategy('my_strategy')

# 查看上游数据源
upstream = strategy_info.get('upstream_datasources', [])
print(f"上游数据源：{upstream}")

# 查看下游策略
downstream = strategy_info.get('downstream_strategies', [])
print(f"下游策略：{downstream}")
```

### 2. 策略版本管理

```python
# 保存策略版本
mgr.save_version('my_strategy', version='1.0.0', comment='初始版本')

# 查看版本历史
versions = mgr.get_versions('my_strategy')

# 回滚到指定版本
mgr.rollback('my_strategy', version='1.0.0')
```

### 3. 策略模板

```python
# 使用模板创建策略
template = mgr.get_template('moving_average')
new_strategy = mgr.create_from_template(template, {
    'name': 'my_ma_strategy',
    'short_window': 5,
    'long_window': 20
})
```

---

## ⚠️ 最佳实践

### 1. 策略编写

**推荐：**
```python
class MyStrategy(StrategyUnit):
    def process(self, data):
        # 1. 数据验证
        if not data or 'close' not in data:
            return 'hold'
        
        # 2. 异常处理
        try:
            # 策略逻辑
            signal = self.calculate_signal(data)
            return signal
        except Exception as e:
            self.log.error(f'策略错误：{e}')
            return 'hold'
```

**不推荐：**
```python
class MyStrategy(StrategyUnit):
    def process(self, data):
        # 没有异常处理
        close = data['close']  # 可能抛出 KeyError
        # ...
```

### 2. 日志记录

```python
class MyStrategy(StrategyUnit):
    def process(self, data):
        self.log.info(f'收到数据：{len(data.get("close", []))} 条')
        
        signal = self.calculate_signal(data)
        
        self.log.info(f'生成信号：{signal}')
        return signal
```

### 3. 性能优化

```python
# 使用缓存
from functools import lru_cache

class MyStrategy(StrategyUnit):
    @lru_cache(maxsize=100)
    def calculate_indicator(self, data_tuple):
        # 计算指标
        return indicator
    
    def process(self, data):
        data_tuple = tuple(data['close'])
        indicator = self.calculate_indicator(data_tuple)
        return 'buy' if indicator > 0 else 'sell'
```

---

## 🐛 故障排查

### 问题 1：策略无法启动

**可能原因：**
- 代码有语法错误
- 缺少必要的导入
- 数据源未启动

**解决方案：**
```python
# 1. 检查代码语法
python -m py_compile strategy.py

# 2. 检查导入
from deva import StrategyUnit  # 确保导入正确

# 3. 检查数据源
# 在 Admin UI 中查看数据源状态
```

### 问题 2：策略执行失败

**可能原因：**
- 数据格式不正确
- 计算逻辑错误
- 除零错误

**解决方案：**
```python
# 添加详细的日志
def process(self, data):
    self.log.info(f'输入数据：{data}')
    
    try:
        result = self.calculate(data)
        self.log.info(f'计算结果：{result}')
        return result
    except Exception as e:
        self.log.error(f'执行失败：{e}', exc_info=True)
        raise
```

---

## 📚 相关文档

- [数据源管理](datasource_guide.md) - 数据源配置
- [任务管理](task_guide.md) - 任务调度
- [AI 功能](ai_center_guide.md) - AI 代码生成
- [架构文档](ARCHITECTURE.md) - 整体架构

---

**最后更新：** 2026-02-26  
**适用版本：** Deva v1.4.1+
