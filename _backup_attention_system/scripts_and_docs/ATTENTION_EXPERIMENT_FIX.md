# 注意力策略单独实验模式 - 修复说明

## 问题

之前的代码在只选择注意力策略（不选其他策略类别）时会报错：
```
所选类别下没有策略
```

## 修复内容

修改了 `deva/naja/strategy/__init__.py` 中的两处验证逻辑：

### 修复1：允许空策略类别列表

```python
# 修改前
if not target_entries:
    return {"success": False, "error": "所选类别下没有策略"}

# 修改后
if not target_entries and not include_attention:
    return {"success": False, "error": "所选类别下没有策略"}
```

### 修复2：允许只运行注意力策略

```python
# 修改前
if switched_ok <= 0:
    return {"success": False, "error": "未能切换任何策略到实验数据源"}

# 修改后
if switched_ok <= 0 and not include_attention:
    return {"success": False, "error": "未能切换任何策略到实验数据源"}
```

## 现在支持的实验模式

| 策略类别 | 注意力策略 | 结果 |
|---------|-----------|------|
| ❌ 不选 | ✅ 勾选 | ✅ **可以启动** - 只运行注意力策略 |
| ✅ 选择 | ❌ 不勾选 | ✅ 可以启动 - 只运行原有策略 |
| ✅ 选择 | ✅ 勾选 | ✅ 可以启动 - 同时运行两者 |
| ❌ 不选 | ❌ 不勾选 | ❌ 报错 - 至少选择一种 |

## 使用方式

### 只运行注意力策略

1. 打开策略管理页面 `/strategyadmin`
2. 点击"开启实验模式"
3. **不选择**任何策略类别
4. **勾选**"包含注意力策略"
5. 选择实验数据源
6. 点击"开启并启动策略"

系统会提示：
```
实验模式已开启：注意力策略 5 个
```

### 验证

```python
from deva.naja.strategy import get_strategy_manager
mgr = get_strategy_manager()
info = mgr.get_experiment_info()
print(info)
# {'active': True, 'datasource_id': 'replay_001', ...}

from naja_attention_strategies import get_strategy_manager
attn_mgr = get_strategy_manager()
print(attn_mgr.get_experiment_info())
# {'active': True, 'datasource_id': 'replay_001', 'strategy_count': 5}
```
