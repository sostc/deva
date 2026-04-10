# TODO: 删除 attention 目录中的冗余文件（2026-04-10）

## 背景
market_hotspot 从 attention 拆分出来后，attention 目录下留下了一些冗余文件，需要清理。

---

## 1. 可安全删除的文件

### processing/ 目录（与 market_hotspot 完全重复）
| 文件 | 行数 | 原因 |
|------|------|------|
| `attention/processing/noise_filter.py` | ~320行 | 与 `market_hotspot/processing/noise_filter.py` **完全相同**（diff 无输出） |
| `attention/processing/noise_manager.py` | ~200行 | 与 `market_hotspot/processing/noise_manager.py` **完全相同** |

**注意**: `register.py` 中引用了 `attention.processing.noise_filter`，需要先改为引用 `market_hotspot.processing.noise_filter`

### strategies/ 目录（attention 版本是简化版，应该用 market_hotspot 完整版）

| attention 版本 | 行数 | market_hotspot 版本 | 行数 | 状态 |
|----------------|------|---------------------|------|------|
| `strategies/base.py` | 142行 | `strategies/base.py` | 561行 | attention 是简化版 |
| `strategies/anomaly_sniper.py` | 87行 | `strategies/anomaly_sniper.py` | 406行 | attention 是简化版 |
| `strategies/global_sentinel.py` | 73行 | `strategies/global_sentinel.py` | 262行 | attention 是简化版 |
| `strategies/momentum_tracker.py` | 76行 | `strategies/momentum_tracker.py` | 341行 | attention 是简化版 |
| `strategies/us_strategies.py` | 199行 | `strategies/us_strategies.py` | 217行 | attention 是简化版 |
| `strategies/smart_money.py` | 71行 | `strategies/smart_money_detector.py` | 377行 | attention 是简化版 |
| `strategies/liquidity_rescue.py` | 153行 | `strategies/liquidity_rescue_strategies.py` | 544行 | attention 是简化版 |
| `strategies/__init__.py` | ~50行 | `strategies/__init__.py` | 有 | 导出简化版 |

**注意**: `attention/attention_os.py` 中引用了 `attention.strategies`，需要改为引用 `market_hotspot.strategies`

### attention 独有的文件（需迁移到 market_hotspot）
| 文件 | 行数 | 状态 | 处理方式 |
|------|------|------|----------|
| `strategies/block_rotation.py` | 77行 | **可合并** - market_hotspot 没有这个文件 | 迁移到 market_hotspot/strategies/ |

**block_rotation.py 功能说明：**
- 题材轮动捕捉策略，监控题材热点变化
- 检测资金在题材间的轮动方向（inflow/outflow）
- 是 attention 独有的功能，需要保留

**迁移步骤：**
```bash
# 1. 复制到 market_hotspot
cp deva/naja/attention/strategies/block_rotation.py deva/naja/market_hotspot/strategies/

# 2. 修改 import 路径（base → market_hotspot.strategies.base）
# 3. 删除原文件
rm deva/naja/attention/strategies/block_rotation.py
```

---

## 2. 清理步骤

### Step 1: 修改引用
修改 `deva/naja/register.py`:
```python
# 原来
from .attention.processing.noise_filter import NoiseFilter
# 改为
from .market_hotspot.processing.noise_filter import NoiseFilter
```

修改 `deva/naja/attention/attention_os.py`:
```python
# 原来
from deva.naja.attention.strategies import ...
from deva.naja.attention.strategies.us_strategies import ...
# 改为
from deva.naja.market_hotspot.strategies import ...
from deva.naja.market_hotspot.strategies.us_strategies import ...
```

### Step 2: 删除冗余文件
```bash
# 删除 processing 目录中的重复文件
rm deva/naja/attention/processing/noise_filter.py
rm deva/naja/attention/processing/noise_manager.py

# 删除 strategies 目录
rm deva/naja/attention/strategies/__init__.py
rm deva/naja/attention/strategies/base.py
rm deva/naja/attention/strategies/anomaly_sniper.py
rm deva/naja/attention/strategies/global_sentinel.py
rm deva/naja/attention/strategies/momentum_tracker.py
rm deva/naja/attention/strategies/us_strategies.py
rm deva/naja/attention/strategies/smart_money.py
rm deva/naja/attention/strategies/liquidity_rescue.py
rm deva/naja/attention/strategies/block_rotation.py  # 先迁移到 market_hotspot 再删除
```

### Step 3: 验证
启动系统检查是否有导入错误：
```bash
cd /Users/spark/pycharmproject/deva && python3 -m deva.naja
```

---

## 3. 预估收益
- 删除 ~2500 行冗余代码
- 消除两套策略系统维护的困惑
- 统一使用 market_hotspot 的完整实现

---

*由虾丸标记，2026-04-10*
