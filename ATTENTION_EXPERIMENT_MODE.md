# 注意力系统实验模式

## 概述

注意力策略系统现在支持实验模式，可以与原有策略体系一起切换到历史行情回放数据源进行回测实验。

## 实验模式集成

### 与原有实验模式的关系

```
原有策略实验模式启动
    ↓
start_experiment(datasource_id)
    ↓
    ├─→ 原有策略切换到实验数据源
    └─→ 注意力策略切换到实验数据源 ✅ 新增
    ↓
所有策略（原有 + 注意力）都使用同一实验数据源
```

### 启动实验模式

在 Web UI 的策略页面启动实验模式：

1. 访问 `/strategyadmin`
2. 选择策略类别
3. 选择实验数据源（如历史行情回放）
4. 点击"启动实验"

**注意**：注意力策略会自动跟随原有策略一起切换到实验数据源，无需额外操作。

### 实验模式行为

当实验模式启动时：

1. **原有策略**：
   - 保存当前配置快照
   - 切换到实验数据源
   - 继续执行策略逻辑

2. **注意力策略**（新增）：
   - 保存当前状态快照
   - 注册到调度中心
   - 接收实验数据源的数据
   - 正常计算注意力并生成信号

3. **信号输出**：
   - 所有信号（原有 + 注意力）都发送到信号流
   - Bandit 可以接收所有买入/卖出信号
   - 在 `/signaladmin` 页面可以查看所有信号

## 技术实现

### 修改的文件

| 文件 | 修改内容 |
|------|---------|
| `naja_attention_strategies/strategy_manager.py` | 添加实验模式支持方法 |
| `deva/naja/strategy/__init__.py` | 启动/停止实验模式时调用注意力策略 |
| `deva/naja/attention_orchestrator.py` | 添加数据源注册/注销方法 |
| `deva/naja/attention/ui.py` | 显示实验模式状态 |

### 核心方法

#### 1. 启动实验模式

```python
# naja_attention_strategies/strategy_manager.py

def start_experiment(self, datasource_id: str) -> dict:
    """启动实验模式"""
    # 1. 检查数据源是否存在
    # 2. 保存当前状态快照
    # 3. 切换到实验模式
    # 4. 注册实验数据源到调度中心
    
    self._experiment_mode = True
    self._experiment_datasource_id = datasource_id
    
    orchestrator.register_datasource(datasource_id)
```

#### 2. 停止实验模式

```python
def stop_experiment(self) -> dict:
    """停止实验模式"""
    # 1. 恢复实验前的状态
    # 2. 从调度中心注销实验数据源
    # 3. 清理实验状态
    
    self._experiment_mode = False
    self._experiment_datasource_id = None
    
    orchestrator.unregister_datasource(datasource_id)
```

#### 3. 原有策略与注意力策略的联动

```python
# deva/naja/strategy/__init__.py

def start_experiment(self, categories, datasource_id):
    # ... 原有策略切换到实验数据源 ...
    
    # 启动注意力策略的实验模式
    from naja_attention_strategies import get_strategy_manager
    attention_manager = get_strategy_manager()
    attention_manager.start_experiment(datasource_id)

def stop_experiment(self):
    # ... 原有策略恢复 ...
    
    # 停止注意力策略的实验模式
    attention_manager.stop_experiment()
```

## 使用流程

### 1. 准备实验环境

确保历史行情回放数据源已配置：

```python
# 在 naja Web UI 中配置
数据源名称: 历史行情回放
数据源类型: replay
数据文件: /path/to/historical_data.csv
```

### 2. 启动实验模式

**方式一：Web UI**

1. 打开 `/strategyadmin`
2. 选择要实验的策略类别
3. 选择"历史行情回放"数据源
4. 点击"启动实验"

**方式二：代码**

```python
from deva.naja.strategy import get_strategy_manager

strategy_mgr = get_strategy_manager()
result = strategy_mgr.start_experiment(
    categories=["默认"],
    datasource_id="historical_replay_001"
)

if result["success"]:
    print(f"实验模式已启动: {result['datasource_name']}")
    print(f"原有策略: {result['target_count']} 个")
    print(f"注意力策略: 5 个")  # 自动启动
```

### 3. 监控实验

在实验运行期间，可以查看：

- **注意力系统页面** `/attentionadmin`
  - 显示"🧪 实验模式运行中"横幅
  - 实时显示注意力变化
  - 查看策略执行状态

- **信号流页面** `/signaladmin`
  - 查看所有策略生成的信号
  - 注意力策略信号带有 `[注意力]` 前缀

- **Bandit 页面** `/banditadmin`
  - 查看虚拟持仓
  - 查看交易历史

### 4. 停止实验模式

**方式一：Web UI**

1. 打开 `/strategyadmin`
2. 点击"停止实验"

**方式二：代码**

```python
result = strategy_mgr.stop_experiment()
if result["success"]:
    print("实验模式已停止")
    print(f"原有策略已恢复: {result['restored_bind_count']} 个")
    print(f"注意力策略已恢复")
```

## 实验模式状态

### 获取实验信息

```python
from naja_attention_strategies import get_strategy_manager

manager = get_strategy_manager()
info = manager.get_experiment_info()

print(f"实验模式: {'运行中' if info['active'] else '未启动'}")
print(f"数据源: {info.get('datasource_id', 'N/A')}")
print(f"策略数: {info.get('strategy_count', 0)}")
```

### 检查是否处于实验模式

```python
if manager.is_experiment_mode():
    print("当前处于实验模式")
else:
    print("当前处于正常模式")
```

## 注意事项

1. **自动联动**：启动/停止原有策略的实验模式时，注意力策略会自动跟随

2. **状态恢复**：停止实验时，所有策略（原有 + 注意力）都会恢复到实验前的状态

3. **信号隔离**：实验期间产生的信号与正常运行的信号在同一个信号流中，但可以通过元数据区分

4. **数据源要求**：实验数据源需要是 `replay` 类型（历史行情回放）

5. **性能考虑**：实验模式运行期间，注意力系统正常计算，不会额外增加性能开销

## 故障排查

### 实验模式启动失败

```python
# 检查错误信息
result = manager.start_experiment(datasource_id)
if not result["success"]:
    print(f"错误: {result['error']}")
```

常见错误：
- `实验模式已启动，请先关闭` - 需要先停止当前实验
- `数据源 xxx 不存在` - 数据源ID错误

### 注意力策略未收到数据

1. 检查实验模式是否真正启动：
   ```python
   print(manager.get_experiment_info())
   ```

2. 检查数据源是否运行：
   ```python
   from deva.naja.datasource import get_datasource_manager
   ds_mgr = get_datasource_manager()
   ds = ds_mgr.get(datasource_id)
   print(f"数据源运行状态: {ds.is_running}")
   ```

3. 检查调度中心是否注册了数据源：
   ```python
   from deva.naja.attention_orchestrator import get_orchestrator
   orch = get_orchestrator()
   print(f"注册的数据源: {list(orch._datasources.keys())}")
   ```

## 总结

✅ **无缝集成**：注意力策略自动跟随原有策略进入实验模式
✅ **状态恢复**：停止实验时自动恢复所有策略状态
✅ **统一监控**：在注意力系统页面查看实验模式状态
✅ **信号统一**：所有信号都发送到信号流，便于分析
