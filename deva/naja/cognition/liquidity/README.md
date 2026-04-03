# 流动性预测通知功能

## 功能概述

全球流动性预测系统现已集成钉钉通知功能，在关键节点自动发送提醒，并在 UI 上展示详细状态和历史记录。

## 核心功能

### 1. 钉钉通知

系统会在以下关键节点自动发送钉钉通知：

#### 🔔 预测创建通知
- **触发条件**: 置信度 > 0.7
- **通知内容**: 
  - 预测方向（上涨/下跌）
  - 置信度
  - 源市场变化
  - 验证时间

#### ✅ 预测验证成功通知
- **触发条件**: 预测正确且原置信度 > 0.7
- **通知内容**:
  - 预测方向验证
  - 实际变化幅度
  - 模型验证成功

#### ❌ 预测验证失败通知
- **触发条件**: 预测错误
- **通知内容**:
  - 原预测信息
  - 实际变化
  - 失败原因

#### ⚡ 跨市场共振检测
- **触发条件**: 置信度 > 0.7
- **通知内容**:
  - 共振市场列表
  - 共振等级
  - 置信度

#### 📊 流动性信号大幅变化
- **触发条件**: 变化幅度 > 30%
- **通知内容**:
  - 当前状态（紧张/中性/宽松）
  - 变化幅度
  - 原信号值和新信号值

### 2. UI 展示

#### Radar UI 流动性预测面板

访问路径：`Naja Radar` → `流动性预测体系`

展示内容：
- **预测区域**: 各市场流动性预测（A 股、港股、美股、期货）
- **验证区域**: 预测验证状态和次数
- **共振检测**: 行情与舆论的共振情况
- **主题扩散**: 主题热度与传染概率
- **通知历史**: 最近 5 条通知记录
  - 通知类型图标
  - 时间戳
  - 严重程度
  - 发送状态

## 配置说明

### 钉钉机器人配置

需要在系统中配置钉钉机器人：

```python
from deva import config

# 配置钉钉机器人 webhook
config.set('dtalk.webhook', 'https://oapi.dingtalk.com/robot/send?access_token=xxx')

# 配置签名密钥（可选，建议配置）
config.set('dtalk.secret', 'SECxxxxxxxxxx')
```

### 通知开关

通知器默认启用，可通过代码控制：

```python
from deva.naja.cognition.liquidity import get_notifier

notifier = get_notifier()

# 禁用通知
notifier.disable()

# 启用通知
notifier.enable()

# 检查状态
if notifier.is_enabled():
    print("通知已启用")
```

## 使用示例

### 手动发送通知

```python
from deva.naja.cognition.liquidity import get_notifier

notifier = get_notifier()

# 发送预测创建通知
notifier.send_prediction_created(
    from_market="us_equity",
    to_market="a_share",
    direction="down",
    probability=0.85,
    source_change=-3.5,
    verify_minutes=30,
)

# 发送共振检测通知
notifier.send_resonance_detected(
    markets=["us_equity", "a_share"],
    resonance_level="high",
    confidence=0.88,
)
```

### 查询通知历史

```python
from deva.naja.cognition.liquidity import get_notifier

notifier = get_notifier()

# 获取最近 10 条通知
notifications = notifier.get_recent_notifications(limit=10)

for n in notifications:
    print(f"{n['time_str']} - {n['title']}")
    print(f"  类型：{n['type']}")
    print(f"  严重程度：{n['severity']}")
    print(f"  已发送：{'是' if n['sent'] else '否'}")
```

### 查询统计信息

```python
stats = notifier.get_stats()
print(f"总发送数：{stats['total_sent']}")
print(f"总失败数：{stats['total_failed']}")
print(f"历史记录数：{stats['history_count']}")
print(f"按类型统计：{stats['by_type']}")
```

## 通知阈值说明

| 通知类型 | 触发阈值 | 严重程度 |
|---------|---------|---------|
| 预测创建 | 置信度 > 0.7 | 高 (>0.85) / 中 |
| 预测验证成功 | 置信度 > 0.7 | 高 |
| 预测验证失败 | 任意置信度 | 高 |
| 共振检测 | 置信度 > 0.7 | 高 (>0.85) / 中 |
| 信号变化 | 变化 > 30% | 高 (>50%) / 中 |

## 通知历史记录

- **保存数量**: 最近 20 条（可配置）
- **展示数量**: UI 显示最近 5 条
- **自动清理**: 超出数量限制时自动删除最早的记录

## 测试

运行测试脚本验证功能：

```bash
cd /Users/spark/pycharmproject/deva
python deva/naja/cognition/liquidity/test_notifier.py
```

## 文件结构

```
deva/naja/cognition/liquidity/
├── notifier.py              # 通知器核心实现
├── liquidity_cognition.py   # 流动性认知系统（已集成通知）
├── test_notifier.py         # 测试脚本
└── README.md                # 本文档
```

## 注意事项

1. **钉钉配置**: 确保正确配置 webhook 和 secret，否则通知发送会失败
2. **网络连通**: 确保服务器能访问钉钉 API 服务器
3. **频率控制**: 钉钉机器人有频率限制，避免过于频繁发送
4. **通知过滤**: 系统已内置阈值过滤，避免发送过多低价值通知

## 故障排查

### 通知未发送

1. 检查钉钉配置是否正确
2. 检查通知器是否启用：`notifier.is_enabled()`
3. 查看日志：搜索 `[LiquidityNotifier]` 相关日志

### UI 无通知历史

1. 确认通知已触发（查看日志）
2. 刷新 Radar UI 页面
3. 检查浏览器控制台是否有错误

### 发送失败

1. 检查网络连接
2. 验证 webhook URL 是否有效
3. 检查 secret 是否正确
4. 查看日志中的详细错误信息

## 更新日志

### v1.0 - 2026-04-03
- ✅ 创建 LiquidityNotifier 通知器
- ✅ 集成到 PredictionTracker
- ✅ 增强 Radar UI 展示通知历史
- ✅ 支持 5 种通知类型
- ✅ 通知历史记录管理
