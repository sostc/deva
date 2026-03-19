# 注意力历史追踪功能

## 概述

新增注意力历史追踪系统，可以：
1. 追踪注意力随时间的变化
2. 检测注意力转移（板块/个股）
3. 显示股票代码和名称
4. 显示板块名称

## 新增文件

### 1. `deva/naja/attention/history_tracker.py`

核心历史追踪模块，包含：

- `AttentionSnapshot` - 注意力快照
- `AttentionChange` - 注意力变化记录
- `AttentionHistoryTracker` - 历史追踪器

### 2. 修改的文件

- `deva/naja/attention_orchestrator.py` - 集成历史追踪
- `deva/naja/attention/ui.py` - 增强UI展示

## 功能特性

### 1. 注意力变化追踪

自动检测以下变化类型：

| 变化类型 | 图标 | 说明 |
|---------|------|------|
| new_hot | 🔥 | 新热门板块/股票 |
| cooled | ❄️ | 板块/股票冷却 |
| strengthen | 📈 | 注意力加强（+20%以上）|
| weaken | 📉 | 注意力减弱（-20%以上）|

### 2. 注意力转移检测

当 Top 3 板块或 Top 5 股票发生变化时，会显示转移报告：

```
🔄 注意力转移 detected

板块转移:
之前 Top 3:          现在 Top 3:
• 半导体 (0.85)      • 新能源 (0.92)
• 医药 (0.72)        • 半导体 (0.78)
• 金融 (0.65)        • 医药 (0.71)

个股转移:
之前 Top 5:          现在 Top 5:
• 000001.SZ 平安银行 • 000002.SZ 万科A
• 000858.SZ 五粮液   • 000001.SZ 平安银行
...
```

### 3. 股票和板块名称显示

#### 股票显示格式
```
1. 000001.SZ 平安银行    3.52
2. 000002.SZ 万科A       2.89
3. 600519.SH 贵州茅台    2.76
```

#### 板块显示格式
```
1. 半导体    0.852
2. 新能源    0.789
3. 医药生物  0.723
```

### 4. 历史趋势查看

可以查看板块和个股的历史趋势：

```python
from deva.naja.attention.history_tracker import get_history_tracker

tracker = get_history_tracker()

# 查看板块趋势
trend = tracker.get_sector_trend('semiconductor', n=10)
for t in trend:
    print(f"{t['datetime']}: {t['weight']:.3f}")

# 查看个股趋势
trend = tracker.get_symbol_trend('000001.SZ', n=10)
```

## 使用方式

### 注册股票名称

在数据源推送数据时自动注册：

```python
# 在 attention/ui.py 中
if 'code' in data.columns and 'name' in data.columns:
    for _, row in data.iterrows():
        tracker.register_symbol_name(row['code'], row['name'])
```

### 注册板块名称

```python
from deva.naja.attention.history_tracker import get_history_tracker

tracker = get_history_tracker()
tracker.register_sector_name('semiconductor', '半导体')
tracker.register_sector_name('new_energy', '新能源')
```

### 获取历史报告

```python
# 获取变化记录
changes = tracker.get_recent_changes(n=20)
for change in changes:
    print(f"{change.description}: {change.old_weight:.2f} -> {change.new_weight:.2f}")

# 获取转移报告
report = tracker.get_attention_shift_report()
if report['has_shift']:
    print("注意力发生转移！")
    print(f"板块转移: {report['sector_shift']}")
    print(f"个股转移: {report['symbol_shift']}")
```

## UI 展示

### 新增区域

1. **注意力转移报告** - 显示是否发生注意力转移
2. **热门板块与股票** - 显示 Top 10 板块和 Top 20 股票（带名称）
3. **注意力变化动态** - 显示最近的变化记录

### 页面布局

```
👁️ 注意力调度系统
├── 全局注意力卡片
├── 系统状态 / 策略概览
├── 频率分布 / 策略状态
├── 双引擎状态
├── 🔄 注意力转移报告 (新增)
├── 🔥 热门板块与股票 (新增 - 带名称)
├── 📈 注意力变化动态 (新增)
└── 📡 最近信号
```

## 配置

### 历史记录容量

```python
# 默认保存100个快照
tracker = AttentionHistoryTracker(max_history=100)

# 可以自定义容量
tracker = AttentionHistoryTracker(max_history=200)
```

### 变化检测阈值

在 `history_tracker.py` 中可以调整：

```python
# 板块变化阈值
if change_pct > 20:  # 加强阈值
if change_pct < -20:  # 减弱阈值

# 个股变化阈值
if abs(change_pct) > 30:  # 记录阈值
if new_weight > 2:  # 新热门阈值
```

## 数据流

```
数据源 emit 数据
    ↓
调度中心 process_datasource_data()
    ↓
_update_attention()
    ↓
    ├─→ 更新注意力系统
    └─→ 记录到历史追踪器 (record_snapshot)
            ↓
            ├─→ 保存快照
            └─→ 检测变化 (_detect_changes)
                    ↓
                    ├─→ new_hot (新热门)
                    ├─→ cooled (冷却)
                    ├─→ strengthen (加强)
                    └─→ weaken (减弱)
```

## 注意事项

1. **名称注册**：股票和板块名称需要在数据推送时注册，否则显示代码
2. **历史容量**：默认保存100个快照，超过后会自动清理旧数据
3. **变化检测**：基于权重变化百分比，阈值可调整
4. **性能影响**：历史追踪对性能影响很小，数据存储在内存中

## 示例输出

### 注意力变化动态

```
📈 注意力变化动态

🔥 新热门板块: 半导体
   SECTOR | 变化: +∞%
   0.00 → 0.85

📈 板块加强: 新能源 +35.2%
   SECTOR | 变化: +35.2%
   0.58 → 0.78

📉 板块减弱: 医药 -28.5%
   SECTOR | 变化: -28.5%
   0.72 → 0.51

🔥 新热门股: 000001.SZ 平安银行
   SYMBOL | 变化: +∞%
   0.00 → 3.52
```

### 热门板块与股票

```
🔥 热门板块与股票

📊 热门板块 Top 10          📈 热门股票 Top 20
1. 半导体        0.852      1. 000001.SZ 平安银行    3.52
2. 新能源        0.789      2. 000002.SZ 万科A       2.89
3. 医药生物      0.723      3. 600519.SH 贵州茅台    2.76
4. 金融          0.654      4. 000858.SZ 五粮液      2.54
5. 消费          0.598      5. 002415.SZ 海康威视    2.31
...
```
