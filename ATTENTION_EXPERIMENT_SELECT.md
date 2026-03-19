# 注意力策略实验模式选择

## 概述

现在启动实验模式时，可以选择是否包含注意力策略系统。这提供了更灵活的实验配置：

- **只运行原有策略**：不勾选注意力策略选项
- **只运行注意力策略**：不选择任何策略类别，只勾选注意力策略
- **同时运行两者**：选择策略类别并勾选注意力策略

## 使用方式

### 1. 打开实验模式对话框

在策略管理页面 (`/strategyadmin`) 点击"开启实验模式"按钮。

### 2. 配置实验选项

对话框现在包含以下选项：

```
🧪 开启策略实验模式

┌─────────────────────────────────────────┐
│ 策略类别（可逐项选择）                    │
│ ☑️ 默认 (10)                             │
│ ☐ 雷达 (5)                               │
│ ☐ 实验 (3)                               │
├─────────────────────────────────────────┤
│ 实验数据源                               │
│ 📁 历史行情回放 ▼                        │
├─────────────────────────────────────────┤
│ 包含注意力策略                           │
│ ☑️ 👁️ 同时运行注意力策略系统（5个策略）   │
├─────────────────────────────────────────┤
│ [开启并启动策略]  [取消]                 │
└─────────────────────────────────────────┘
```

### 3. 三种实验模式

#### 模式一：只运行原有策略

**配置**：
- 选择策略类别（如"默认"）
- **不勾选**"包含注意力策略"

**结果**：
- 只有选中的原有策略切换到实验数据源
- 注意力策略保持原有运行状态（如果有）

#### 模式二：只运行注意力策略

**配置**：
- **不选择**任何策略类别
- **勾选**"包含注意力策略"

**结果**：
- 原有策略不参与实验
- 只有注意力策略切换到实验数据源
- 适合专门测试注意力策略的效果

#### 模式三：同时运行两者（默认）

**配置**：
- 选择策略类别（如"默认"）
- **勾选**"包含注意力策略"（默认已勾选）

**结果**：
- 原有策略和注意力策略都切换到实验数据源
- 可以对比两种策略的效果
- 所有信号都进入同一个信号流

## 技术实现

### 参数传递流程

```
Web UI 对话框
    ↓
用户选择：
  - categories: ["默认"]（策略类别列表）
  - datasource_id: "replay_001"（数据源ID）
  - include_attention: true（是否包含注意力策略）
    ↓
start_experiment(categories, datasource_id, include_attention)
    ↓
    ├─→ 原有策略切换到实验数据源
    └─→ if include_attention:
            注意力策略切换到实验数据源
```

### 核心代码

#### 1. UI 层添加选项

```python
# deva/naja/strategy/ui.py

form = await ctx["input_group"]("🧪 开启策略实验模式", [
    ctx["checkbox"]("策略类别", name="categories", ...),
    ctx["select"]("实验数据源", name="datasource_id", ...),
    ctx["checkbox"]("包含注意力策略", name="include_attention", options=[
        {"label": "👁️ 同时运行注意力策略系统（5个策略）", 
         "value": True, "selected": True}
    ], value=[True]),  # 默认勾选
    ...
])

include_attention = bool(form.get("include_attention", [True]))
result = mgr.start_experiment(
    categories=categories_selected, 
    datasource_id=datasource_id, 
    include_attention=include_attention
)
```

#### 2. 策略管理器处理参数

```python
# deva/naja/strategy/__init__.py

def start_experiment(self, categories, datasource_id, include_attention=True):
    # 验证：至少选择一种策略
    if not normalized_categories and not include_attention:
        return {"success": False, "error": "请至少选择一个策略类别或启用注意力策略"}
    
    # 启动原有策略...
    
    # 根据参数决定是否启动注意力策略
    if include_attention:
        attention_manager.start_experiment(datasource_id)
    
    # 保存配置
    self._experiment_session["include_attention"] = include_attention
```

#### 3. 停止实验时的处理

```python
def stop_experiment(self):
    # 恢复原有策略...
    
    # 根据记录决定是否停止注意力策略
    include_attention = session.get("include_attention", True)
    if include_attention:
        attention_manager.stop_experiment()
```

## 使用场景

### 场景一：对比测试

**目的**：对比原有策略和注意力策略的效果

**配置**：
- 策略类别：选择原有策略
- 包含注意力策略：✅ 勾选

**分析**：
- 在信号流页面查看两种策略的信号
- 在 Bandit 页面查看虚拟持仓表现
- 对比收益率、胜率等指标

### 场景二：单独优化注意力策略

**目的**：专门调试和优化注意力策略的参数

**配置**：
- 策略类别：不选择
- 包含注意力策略：✅ 勾选

**优势**：
- 避免原有策略的干扰
- 快速迭代注意力策略配置
- 专注于注意力系统的调优

### 场景三：验证原有策略

**目的**：验证原有策略在历史数据上的表现

**配置**：
- 策略类别：选择要测试的策略
- 包含注意力策略：❌ 不勾选

**适用**：
- 原有策略的回归测试
- 新策略的初步验证
- 不需要注意力系统参与的场景

## 状态显示

### 实验模式运行中

在策略管理页面会显示：

```
🧪 实验模式运行中
数据源: 历史行情回放
原有策略: 10 个 | 注意力策略: 5 个
[停止实验]
```

### 注意力系统页面

在 `/attentionadmin` 页面会显示：

```
🧪 实验模式运行中
数据源: historical_replay_001 | 策略数: 5
```

## 注意事项

1. **至少选择一种**：必须选择至少一个策略类别或勾选注意力策略

2. **默认勾选**：注意力策略默认是勾选的，方便用户快速启动完整实验

3. **独立控制**：原有策略和注意力策略可以独立选择，互不干扰

4. **状态保存**：实验会话会记录是否包含注意力策略，停止时正确恢复

5. **信号统一**：无论选择哪种组合，所有信号都会进入同一个信号流

## 故障排查

### 提示"请至少选择一个策略类别或启用注意力策略"

**原因**：没有选择任何策略类别，也没有勾选注意力策略

**解决**：至少选择一项

### 注意力策略未启动

**检查**：
```python
from naja_attention_strategies import get_strategy_manager
manager = get_strategy_manager()
print(manager.get_experiment_info())
```

### 实验模式状态不一致

**检查原有策略实验状态**：
```python
from deva.naja.strategy import get_strategy_manager
mgr = get_strategy_manager()
print(mgr.get_experiment_info())
```

**检查注意力策略实验状态**：
```python
from naja_attention_strategies import get_strategy_manager
manager = get_strategy_manager()
print(manager.get_experiment_info())
```

## 总结

✅ **灵活选择**：可以只运行原有策略、只运行注意力策略、或同时运行两者
✅ **默认友好**：注意力策略默认勾选，方便快速启动
✅ **状态隔离**：两种策略的实验状态独立管理
✅ **统一监控**：所有信号都进入同一个信号流便于分析
