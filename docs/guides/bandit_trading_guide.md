# Bandit 自适应交易系统

> 基于最新代码结构（2026-03-24）

## 概述

Bandit 自适应交易系统是 Naja 平台的策略自适应模块，基于 Multi-armed Bandit 算法实现策略的在线选择和参数调节。系统与 LLM Controller 架构一致，支持相同的动作类型。

## 核心思想

传统量化交易选一个策略后回测上线，但市场变化会导致策略失效。Bandit 的思想不同：

- **多个策略同时存在**
- **动态选择**
- **根据收益不断调整权重**

这像赌徒拉老虎机一样：不知道哪台会中奖，只能一次次拉，再从回报中学习。

## 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    Bandit 自适应交易系统                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  市场数据流                                                     │
│      ↓                                                          │
│  ┌─────────────────┐                                           │
│  │ SignalListener  │ ← 监听信号流，识别股票                     │
│  └────────┬────────┘                                           │
│           ↓                                                     │
│  ┌─────────────────┐                                           │
│  │VirtualPortfolio │ ← 虚拟持仓管理                             │
│  └────────┬────────┘                                           │
│           ↓                                                     │
│  ┌─────────────────┐                                           │
│  │MarketObserver   │ ← 市场数据观察，更新价格                  │
│  └────────┬────────┘                                           │
│           ↓                                                     │
│  ┌─────────────────┐                                           │
│  │ 检查止盈止损    │                                             │
│  └────────┬────────┘                                           │
│           ↓                                                     │
│  ┌─────────────────┐                                           │
│  │BanditTracker   │ ← 计算收益                                 │
│  └────────┬────────┘                                           │
│           ↓                                                     │
│  ┌─────────────────┐                                           │
│  │BanditOptimizer  │ ← 更新策略权重 + 调节参数                  │
│  └─────────────────┘                                           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## 模块说明

### 1. SignalListener (信号监听器)

监听信号流，提取股票信息：

```python
from deva.naja.bandit import get_signal_listener

listener = get_signal_listener()
listener.set_min_confidence(0.6)  # 设置最小置信度
listener.start()  # 启动监听
```

功能：
- 实时获取信号流中的新信号
- 识别信号中的股票信息（代码、名称、价格）
- 过滤低置信度信号
- 触发虚拟持仓创建

### 2. VirtualPortfolio (虚拟持仓)

管理虚拟股票的买入和卖出：

```python
from deva.naja.bandit import get_virtual_portfolio

portfolio = get_virtual_portfolio()

# 虚拟买入
position = portfolio.open_position(
    strategy_id='strategy_1',
    strategy_name='趋势策略',
    stock_code='000001',
    stock_name='平安银行',
    price=10.0,
    amount=10000,  # 买入金额
    stop_loss_pct=-5.0,  # 止损 5%
    take_profit_pct=10.0  # 止盈 10%
)

# 更新价格
portfolio.update_price('000001', 10.5)

# 平仓
portfolio.close_position(position_id, exit_price=11.0, reason='TAKE_PROFIT')
```

功能：
- 虚拟买入持仓
- 持仓价格更新
- 止盈止损检查
- 资金管理

### 3. MarketDataObserver (市场观察器)

从数据源获取实时价格：

```python
from deva.naja.bandit import get_market_observer

observer = get_market_observer()
observer.track_stock('000001')  # 跟踪股票
observer.start()  # 启动观察
```

功能：
- 跟踪持仓中的股票
- 定期获取最新价格
- 触发持仓价格更新

### 4. BanditOptimizer (Bandit 优化器)

Multi-armed Bandit 算法实现：

```python
from deva.naja.bandit import get_bandit_optimizer

optimizer = get_bandit_optimizer()

# 选择策略
result = optimizer.select_strategy(['strategy_a', 'strategy_b', 'strategy_c'])
print(result['selected'])  # 选中的策略

# 更新收益
optimizer.update_reward('strategy_a', 5.0)  # 5% 收益

# 触发参数调节
optimizer.review_and_adjust()
```

支持的算法：
- **ε-greedy**: 90% 用最好的策略，10% 随机探索
- **UCB**: 考虑收益 + 不确定性
- **Thompson Sampling**: 基于概率分布采样（推荐）

支持的动作（与 LLM Controller 一致）：
- `update_params`: 更新策略参数
- `update_strategy`: 更新策略配置
- `reset`: 重置策略状态
- `start`: 启动策略
- `stop`: 停止策略
- `restart`: 重启策略

### 5. AdaptiveCycle (自适应循环控制器)

串联所有组件：

```python
from deva.naja.bandit import get_adaptive_cycle

cycle = get_adaptive_cycle()
cycle.start()  # 启动完整循环
```

完整流程：
1. SignalListener 监听信号流
2. 识别股票，创建虚拟持仓
3. MarketDataObserver 更新价格
4. 检查止盈止损，触发平仓
5. BanditTracker 计算收益
6. BanditOptimizer 更新策略

## 双层调节架构

```
┌──────────────────────────────────────┐
│     Bandit (高频/实时)               │
│  • 秒级响应                         │
│  • 持仓收益 → 调整权重              │
│  • 自动选择最优策略                  │
└──────────────────────────────────────┘
              ↓
┌──────────────────────────────────────┐
│   LLM Controller (低频/周期)         │
│  • 分钟/小时级                       │
│  • Radar + Cognition + Bandit Stats │
│  • 深度分析、策略重组                │
└──────────────────────────────────────┘
```

## 数据存储

使用 SQLite 存储：

| 表名 | 用途 |
|------|------|
| `naja_bandit_stats` | Bandit 策略统计 |
| `naja_bandit_decisions` | Bandit 决策记录 |
| `naja_bandit_actions` | Bandit 动作记录 |
| `naja_bandit_position_rewards` | 持仓收益记录 |
| `naja_bandit_virtual_portfolio` | 虚拟持仓 |
| `naja_bandit_signal_config` | 信号监听配置 |
| `naja_bandit_adaptive_config` | 自适应循环配置 |

## UI 界面

访问地址：`http://localhost:8080/banditadmin`

功能：
- 启动/停止自适应循环
- 查看当前虚拟持仓
- 查看历史平仓记录
- Bandit 策略统计
- 手动操作（选择策略、触发调节、清空持仓）

## 使用示例

### 完整启动

```python
from deva.naja.bandit import get_adaptive_cycle

# 启动自适应交易
cycle = get_adaptive_cycle()
cycle.start()

# 查看状态
print(cycle.get_status())

# 查看持仓
print(cycle.get_positions())

# 查看历史
print(cycle.get_history(limit=20))
```

## 配置选项

### 信号监听

```python
listener = get_signal_listener()
listener.set_poll_interval(2.0)  # 轮询间隔
listener.set_min_confidence(0.5)  # 最小置信度
```

### 虚拟持仓

```python
portfolio = get_virtual_portfolio()
portfolio.set_capital(1000000)  # 总资金
portfolio.set_max_position_pct(0.2)  # 单笔持仓上限 20%
portfolio.set_max_total_pct(0.8)  # 总持仓上限 80%
```

### Bandit 算法

```python
optimizer = get_bandit_optimizer()
optimizer.set_algorithm('thompson')  # 设置算法
optimizer.set_epsilon(0.1)  # epsilon-greedy 参数
optimizer.set_c(1.96)  # UCB 参数
```

## 奖励函数

支持多种奖励计算方式：

| 类型 | 说明 |
|------|------|
| `basic` | 收益率 |
| `sharpe_like` | 收益 / 持仓时间（类夏普比率） |
| `time_weighted` | 收益率 * 时间权重 |
| `risk_adjusted` | 风险调整收益 |

```python
tracker = get_bandit_tracker()
tracker.set_reward_type('sharpe_like')
```

## 注意事项

1. 虚拟持仓仅用于策略验证，不涉及真实交易
2. 建议先用 dry_run 模式测试
3. 关注市场变化，适时调整止盈止损参数
4. Bandit 需要足够的样本才能发挥作用

## 文件结构

```
deva/naja/bandit/
├── __init__.py              # 模块入口
├── optimizer.py              # Bandit 核心算法
├── tracker.py                # 持仓收益追踪
├── runner.py                 # 自动运行器
├── signal_listener.py        # 信号监听器
├── virtual_portfolio.py     # 虚拟持仓管理
├── market_observer.py        # 市场数据观察器
├── adaptive_cycle.py        # 自适应循环控制器
└── ui.py                   # UI 界面
```
