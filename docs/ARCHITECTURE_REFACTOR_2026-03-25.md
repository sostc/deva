# 系统流式改造与注意力内核增强

> 本文档记录 2026-03-25 的核心架构改造

## 概览

| 改造项 | 文件 | 核心理念 |
|--------|------|----------|
| ResultStore 流式改造 | `result_store.py` | 一切皆流，无物永驻 |
| QueryState 深度集成 | `state.py`, `center.py` | 注意力内核驱动 |
| 持仓系统接入 | `center.py` | 计算轻盈 |
| BanditAutoRunner 事件驱动 | `runner.py` | 事件驱动替代轮询 |
| SignalStream 注意力路由 | `stream.py`, `result_store.py` | 动态路由替代广播 |

---

## 1. ResultStore 流式改造

### 问题
- 批量写入 SQLite，架构复杂
- 有界队列阻塞上游
- 不需要存储，只需错误分析

### 改造
- **移除**：SQLite 存储、写入队列、后台批量线程
- **新增**：JSON Lines 日志文件（按天切分）

### 文件
- `deva/naja/strategy/result_store.py`

### 架构对比

```
旧: save() → Queue(10000) → 批量线程 → SQLite
新: save() → SignalStream → Radar/Cognition
              └→ JSON Lines 日志 (按天)
```

### 日志文件格式

```json
{"id": "abc123", "strategy_id": "xxx", "ts": 1741234567.123, "success": false, "error": "...", ...}
```

### 日志路径
```
~/.deva/naja_logs/results/naja_results_YYYY-MM-DD.log
```

---

## 2. QueryState 深度集成

### 问题
- QueryState 定义了字段但从未更新
- 市场状态、风险偏好、注意力焦点未参与计算

### 改造
新增三个市场状态计算方法：

| 方法 | 功能 |
|------|------|
| `_detect_and_update_regime()` | 检测市场状态（trend_up/down/neutral/mixed） |
| `_calculate_and_update_risk_bias()` | 根据波动率计算风险偏好 |
| `_derive_and_update_attention_focus()` | 从板块表现推导注意力焦点 |

### 文件
- `deva/naja/attention/kernel/state.py` - 新增 `update_from_market()`
- `deva/naja/attention/center.py` - 调用 QueryState 更新

### 市场状态类型
- `trend_up` - 强势上涨（上涨家数 > 40%，平均涨幅 > 1%）
- `trend_down` - 强势下跌
- `weak_trend_up` - 弱势上涨
- `weak_trend_down` - 弱势下跌
- `neutral` - 横盘震荡
- `mixed` - 多空分歧

### 风险偏好计算
```python
combined_risk = volatility * 0.4 + volume_intensity * 0.3 + max_change * 0.3
risk_bias = 1.0 - np.clip(combined_risk, 0, 1)
risk_bias = np.clip(risk_bias, 0.1, 0.9)
```

### 数据流
```
市场数据 → _update_attention() → QueryState.update_from_market()
                                      │
                                      ├→ market_regime
                                      ├→ risk_bias
                                      └→ attention_focus
```

---

## 3. 持仓系统接入 QueryState

### 问题
- 持仓状态未参与注意力计算
- 已持仓股票未降低优先级
- 亏损时未自动调整风险偏好

### 改造
- 从 VirtualPortfolio 同步持仓状态
- 亏损时自动降低风险偏好
- 已持仓股票降低优先级

### 文件
- `deva/naja/attention/center.py` - 新增 `_update_portfolio_state()`

### 同步的持仓信息
```python
{
    "held_symbols": [...],           # 已持仓股票列表
    "total_return": 2.5,            # 持仓总收益率
    "profit_loss": 1000.0,          # 浮动盈亏
    "position_count": 3,             # 持仓数量
    "available_capital": 50000.0,    # 可用资金
    "concentration": 0.3,           # 仓位集中度
    "exposed_sectors": [...],        # 暴露的板块
}
```

### 风险调整规则
```python
if portfolio_return < -5%:   risk_bias *= 0.7   # 大幅降低
if portfolio_return < -2%:  risk_bias *= 0.85  # 适度降低
if portfolio_return > 10%:  risk_bias = min(risk_bias * 1.1, 0.95)
if concentration > 50%:     risk_bias *= 0.8    # 仓位集中降低
```

### 持仓过滤
```python
if symbol in held_symbols:
    priority *= 0.3
    tags.append("already_held")
```

---

## 4. BanditAutoRunner 事件驱动改造

### 问题
- 定时轮询 `wait(10)`，无论市场是否变化都执行
- 响应延迟最大 10 秒
- 轮询思维残留

### 改造
- 订阅 `TRADING_CLOCK_STREAM`
- 根据 phase 变化触发动作
- 使用 Timer 替代固定间隔轮询

### 文件
- `deva/naja/bandit/runner.py`

### 事件处理

```
phase_change 事件:
├─ pre_market  → 盘前准备，安排延迟选择
├─ trading     → 交易开始，立即选择 + 定时调节
├─ lunch       → 午休开始，取消定时器
├─ post_market → 收盘，执行日终调节
└─ closed      → 休市，停止所有定时器
```

### 实验模式处理
| 场景 | 实盘模式 | 实验模式 |
|------|----------|----------|
| 调节间隔 | 300s | 60s |
| 盘前 | 不提前选择 | 提前5分钟安排 |
| 午休 | 取消定时器 | 取消 + 中期检查 |

### 架构对比

```
旧架构（轮询）:
while True:
    if time_ok:
        if interval_passed:
            _do_select()
            _do_adjust()
    sleep(10)

新架构（事件驱动）:
TRADING_CLOCK_STREAM
    │
    ▼
_on_trading_clock_event(signal)
    │
    ├── pre_market → _on_pre_market
    ├── trading → _on_trading_start
    ├── lunch → _cancel_timers
    ├── post_market → _do_adjust
    └── closed → _cancel_timers
```

---

## 5. SignalStream 注意力感知路由

### 问题
- 广播式分发，所有下游收到所有信号
- 信号质量不一致，未区分优先级
- 低活跃度时期大量噪音信号

### 改造
- 根据 QueryState 动态计算信号优先级
- 分级路由：high/medium/low priority stream

### 文件
- `deva/naja/strategy/result_store.py` - StrategyResult 增加 priority 字段
- `deva/naja/signal/stream.py` - 注意力感知路由
- `deva/naja/attention/center.py` - 同步 QueryState 到 SignalStream

### StrategyResult 新增字段
```python
priority: float = 0.5              # 信号优先级 [0, 1]
attention_score: float = 0.0       # 注意力分数
matches_attention_focus: bool      # 是否匹配注意力焦点
matches_held_symbol: bool          # 是否已持仓
tags: List[str]                   # 标签列表
```

### StrategyResult 新增方法
```python
def get_symbol(self) -> str         # 提取股票代码
def get_sector(self) -> str        # 提取板块信息
def get_score(self) -> float       # 提取信号分数
def compute_priority(query_state)  # 根据 QueryState 计算优先级
```

### 优先级计算
```python
base_score = get_score()

# 持仓惩罚
if symbol in held_symbols:
    priority *= 0.3

# 注意力焦点加成
if symbol/sector in attention_focus:
    priority *= (1 + weight * 0.5)

# 市场状态加成
if regime in (trend_up, trend_down):
    priority *= 1.2

# 全局注意力
if global_attention < 0.3:
    priority *= 0.7
```

### 分级流

| 流 | 阈值 | 下游示例 |
|----|------|----------|
| high_priority | >= 0.7 | AttentionStrategies |
| medium_priority | 0.3~0.7 | BanditOptimizer |
| low_priority | < 0.3 | (降级处理) |

### 下游订阅示例
```python
# 高优先级策略只关心重要信号
high_stream = signal_stream.get_high_priority_stream()
AttentionStrategies.subscribe(high_stream)

# 其他下游仍然订阅全部
signal_stream.subscribe(SignalListener())
signal_stream.subscribe(BanditOptimizer())
```

### 数据流
```
                    ┌─────────────────────────────────┐
                    │   AttentionOrchestrator           │
                    │   (center.py)                    │
                    └─────────────────┬─────────────────┘
                                      │
                    ┌─────────────────┴─────────────────┐
                    │                                   │
                    ▼                                   ▼
        ┌───────────────────────┐        ┌────────────────────────┐
        │ QueryState             │        │ SignalStream            │
        │ - attention_focus      │ ──────▶│ set_query_state()      │
        │ - portfolio_state      │        │                         │
        │ - market_regime        │        │ _compute_priority()     │
        └───────────────────────┘        └────────────┬─────────────┘
                                                     │
                              ┌──────────────────────┼──────────────────────┐
                              │                      │                      │
                              ▼                      ▼                      ▼
                    ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
                    │ High Priority   │    │ Medium Priority │    │ Low Priority    │
                    │ (>= 0.7)       │    │ (0.3 ~ 0.7)    │    │ (< 0.3)        │
                    └─────────────────┘    └─────────────────┘    └─────────────────┘
```

---

## 改造文件清单

```
deva/naja/
├── attention/
│   ├── center.py              [改造] QueryState 更新、持仓同步、SignalStream 同步
│   └── kernel/
│       └── state.py           [改造] 新增 update_from_market()
├── bandit/
│   └── runner.py              [改造] 事件驱动架构
├── signal/
│   └── stream.py              [改造] 注意力感知路由
└── strategy/
    └── result_store.py        [改造] 流式存储 + priority 字段
```

---

## 核心理念落地

| 理念 | 落地 |
|------|------|
| **一切皆流** | SignalStream 替代 SQLite、ResultStore 日志流式写入 |
| **注意力内核** | QueryState 深度集成市场/持仓状态、SignalStream 优先级路由 |
| **计算轻盈** | 事件驱动替代轮询、定时器替代后台线程 |
| **存储轻盈** | JSON Lines 日志替代 SQLite、按天切分自动过期 |

---

## 改造后系统运行详解

### 一、完整运行流程

#### 1.1 系统启动阶段

```
系统启动
    │
    ├── 1. TradingClock 初始化
    │       │
    │       └── 开始发布 current_state + 监听 phase_change
    │
    ├── 2. AttentionOrchestrator 初始化
    │       │
    │       ├── QueryState 初始化（空状态）
    │       └── 订阅 TRADING_CLOCK_STREAM
    │
    ├── 3. SignalStream 初始化
    │       │
    │       └── 订阅 AttentionOrchestrator 的输出
    │
    ├── 4. BanditAutoRunner 初始化
    │       │
    │       ├── 订阅 TRADING_CLOCK_STREAM
    │       └── 查询策略管理器判断实验模式
    │
    └── 5. ResultStore 初始化
            │
            └── 从日志文件恢复最近缓存
```

#### 1.2 交易时段 - 每个 Tick 的数据流

```
市场数据 Tick (比如每 10 秒)
    │
    ├── TradingClock 判定当前 phase
    │       │
    │       └── 发布 phase_change (如果变化了)
    │
    │   [BanditAutoRunner 收到事件]
    │       │
    │       ├── phase == trading? → _do_select()
    │       └── phase == closed? → _cancel_timers()
    │
    └── AttentionOrchestrator._update_attention()
            │
            ├── 第一步：噪音过滤
            │       └→ data = _noise_filter(data)
            │
            ├── 第二步：更新 QueryState
            │       │
            │       ├── _attention_query_state.update_from_market()
            │       │       │
            │       │       ├── _detect_market_regime() → market_regime
            │       │       ├── _calculate_risk_bias() → risk_bias
            │       │       └── _derive_attention_focus() → attention_focus
            │       │
            │       ├── _update_portfolio_state()
            │       │       └── 从 VirtualPortfolio 同步 held_symbols, concentration
            │       │
            │       └── _update_signal_stream_query_state()
            │               └── SignalStream.set_query_state(query_state)
            │
            ├── 第三步：通过 AttentionKernel 处理
            │       │
            │       └── result = _attention_kernel.process(query_state, events)
            │
            ├── 第四步：过滤高注意力股票
            │       │
            │       └── _filter_by_attention(data)
            │               │
            │               ├── 高注意力股票筛选
            │               └── 排除 held_symbols (已持仓)
            │
            └── 第五步：输出
                    │
                    ├── _emit_to_intelligence_system()
                    ├── _emit_to_strategies()
                    └── _emit_to_output()
```

#### 1.3 策略执行流程

```
策略被选中执行 (通过 BanditAutoRunner 或手动触发)
    │
    ├── 1. 策略执行
    │       │
    │       └── strategy.execute(input_data)
    │
    ├── 2. ResultStore.save()
    │       │
    │       ├── 构造 StrategyResult
    │       │
    │       ├── _send_to_signal_stream(result)
    │       │       │
    │       │       └── SignalStream.update(result)
    │       │               │
    │       │               ├── compute_priority(query_state)  # 使用最新 QueryState
    │       │               │       │
    │       │               │       ├── 持仓惩罚
    │       │               │       ├── 注意力焦点加成
    │       │               │       ├── 市场状态加成
    │       │               │       └── 全局注意力调整
    │       │               │
    │       │               └── _emit(result) → 下游收到
    │       │
    │       ├── _send_to_downstream()
    │       │       │
    │       │       ├── RadarEngine.ingest_result()  # 如果应该发送
    │       │       ├── InsightEngine.ingest_signal()  # 如果应该发送
    │       │       └── BanditOptimizer.update_reward()  # 如果应该发送
    │       │
    │       ├── _write_log()  # JSON Lines 写入日志文件
    │       │
    │       └── _update_cache()  # 更新内存缓存
    │
    └── 3. 返回结果
```

#### 1.4 分级信号处理

```
SignalStream 收到 StrategyResult
    │
    ├── priority >= 0.7 (HIGH)
    │       │
    │       └── → AttentionStrategies.subscribe(high_priority_stream)
    │               └── 立即处理
    │
    ├── 0.3 <= priority < 0.7 (MEDIUM)
    │       │
    │       └── → BanditOptimizer.subscribe(medium_priority_stream)
    │               └── 正常处理
    │
    └── priority < 0.3 (LOW)
            │
            └── → (降级处理或丢弃)
```

---

### 二、改造前后对比

#### 2.1 数据流对比

```
【改造前】

市场 Tick ──┬──▶ AttentionOrchestrator ──▶ (忽略市场状态)
            │
            ├──▶ RadarEngine ──▶ (批量处理)
            │
            ├──▶ Strategy.execute() ──▶ ResultStore ──▶ SQLite
            │                                    │
            │                              (阻塞等待批量写入)
            │
            ├──▶ SignalStream ──▶ (广播给所有下游)
            │
            └──▶ BanditAutoRunner
                     │
                     └── while True: sleep(10) → _tick()

【改造后】

市场 Tick ──┬──▶ TradingClock ──▶ phase_change 事件
            │
            ├──▶ BanditAutoRunner ──▶ 收到事件 → 执行对应动作
            │
            └──▶ AttentionOrchestrator
                     │
                     ├── QueryState.update_from_market()
                     │       ├── market_regime
                     │       ├── risk_bias
                     │       └── attention_focus
                     │
                     ├── _update_portfolio_state()
                     │       └── held_symbols, concentration
                     │
                     ├── _update_signal_stream_query_state()
                     │       └── SignalStream 获得最新 QueryState
                     │
                     └── ▶ SignalStream (优先级已计算)

策略执行 ──▶ ResultStore.save()
                 │
                 ├─▶ SignalStream.update(result)
                 │       └─▶ compute_priority(query_state) ──▶ 分级路由
                 │
                 ├─▶ RadarEngine / CognitionEngine (根据配置发送)
                 │
                 ├─▶ JSON Lines 日志 (顺序写，无阻塞)
                 │
                 └─▶ 内存缓存 (最近200条)
```

#### 2.2 关键差异

| 维度 | 改造前 | 改造后 |
|------|--------|--------|
| **市场状态感知** | 无 | QueryState 实时更新 |
| **风险偏好** | 固定 0.5 | 动态计算 + 持仓影响 |
| **注意力焦点** | 无 | 实时跟踪强势板块 |
| **信号分发** | 广播式 | 优先级分级 |
| **策略选择触发** | 定时轮询 (10秒) | 事件驱动 (立即) |
| **结果存储** | SQLite 批量写入 | JSON Lines 顺序写 |
| **持仓影响** | 无 | 降低优先级 + 调整风险 |
| **实验模式** | 统一处理 | 独立间隔 |

---

### 三、改造带来的好处

#### 3.1 系统响应更快

| 场景 | 之前 | 之后 |
|------|------|------|
| 时段变化后响应 | 最多等待 10 秒 | < 1 秒 |

```
之前：trading 开始 → wait(10) → _tick() 才执行选择
之后：phase_change 事件 → _on_trading_start() → 立即执行
```

#### 3.2 信号质量更高

| 场景 | 之前 | 之后 |
|------|------|------|
| 持有亏损持仓 | 继续追高 | 已持仓股票 priority *= 0.3 |
| 低活跃市场 | 全量噪音信号 | global_attention < 0.3 时 priority *= 0.7 |
| 强势板块信号 | 等同处理 | 匹配 attention_focus 时 priority 加成 |
| 趋势市场 | 等同处理 | regime=trend 时 priority *= 1.2 |

#### 3.3 资源消耗更低

| 资源 | 之前 | 之后 |
|------|------|------|
| CPU | 持续轮询 + 批量处理 | 事件触发 + 流式处理 |
| 内存 | SQLite 连接 + 索引 | 内存缓存 + 无索引 |
| 磁盘 IO | SQLite 随机写 | JSON 顺序写 |
| 响应延迟 | 10秒最大 | < 1秒 |

#### 3.4 架构更简洁

| 之前 | 之后 |
|------|------|
| SQLite 数据库 | JSON Lines 文件 |
| 写入队列 + 后台线程 | 顺序写，无阻塞 |
| 定时轮询 | 事件驱动 |
| 广播分发 | 优先级路由 |

#### 3.5 可追踪性更强

```json
日志文件格式:
{"ts": 1741234567.123, "strategy_id": "xxx", "priority": 0.85, "tags": ["attention_focus", "trend_up"], ...}

可以分析:
- 哪些信号被标记为 attention_focus
- 哪些信号因为 held_symbols 被降低优先级
- 不同 market_regime 下的信号分布
```

---

### 四、潜在的坏处/风险

#### 4.1 复杂度增加

| 风险 | 说明 | 缓解 |
|------|------|------|
| QueryState 计算错误 | market_regime / risk_bias 计算可能有偏差 | 可调参数，待观察 |
| 优先级计算不准确 | 权重系数可能需要调优 | 记录日志，观察分布 |
| 事件丢失 | TRADING_CLOCK_STREAM 事件可能丢失 | 保留轮询作为 fallback |

#### 4.2 优先级调优需要时间

```python
# 现在的系数是经验值，需要观察调整
priority *= (1 + focus_weight * 0.5)  # 0.5 是经验值
risk_bias *= 0.7  # 0.7 是经验值
```

**建议**：先运行一段时间，观察信号分布，再调优。

#### 4.3 低优先级信号可能被忽略

```
场景：某个重要信号因为市场状态被标记为 low priority

可能后果：
- 高注意力策略错过了这个信号
- 系统错过了交易机会
```

**缓解**：low priority 只是降低优先级，不完全丢弃

#### 4.4 持仓状态同步延迟

```
持仓变化 → VirtualPortfolio 更新 → _update_portfolio_state() 同步
                                        ↓
                               最大延迟一个 Tick
```

**风险**：如果 Tick 间隔长（10秒），可能短暂出现"已卖出但还认为持有"的情况

**缓解**：这个延迟对于低频信号来说通常可接受

#### 4.5 实验模式切换

```
实盘 → 实验模式（或反向）
    │
    └→ adjust_interval 从 300s 切换到 60s

可能问题：调节频率突变可能影响系统行为
```

**缓解**：需要手动切换，用户应该知道自己在做什么

#### 4.6 日志文件膨胀

```
JSON Lines 持续写入

问题：
- 文件可能很大
- 查询变慢
```

**缓解**：
1. 按天切分，自然归档
2. 超过一定大小可以 gzip 压缩
3. 定期清理（比如只保留 7 天）

---

### 五、整体评价

#### 好处总结

| 类别 | 具体好处 |
|------|----------|
| **性能** | 事件驱动响应快、资源消耗低、写入无阻塞 |
| **质量** | 优先级路由、持仓过滤、市场状态感知 |
| **简洁** | 移除 SQLite、移除后台线程、架构更清晰 |
| **可追踪** | JSON Lines 格式、标签丰富 |

#### 坏处/风险总结

| 类别 | 具体风险 |
|------|----------|
| **复杂度** | 参数调优需要时间 |
| **延迟** | 持仓同步最多一个 Tick |
| **膨胀** | 日志文件需要管理 |
| **调试** | 事件驱动比轮询难追踪 |

#### 适合场景

| 场景 | 适合度 |
|------|--------|
| 实时交易 | ⭐⭐⭐⭐⭐ 事件驱动响应快 |
| 回测/实验 | ⭐⭐⭐⭐⭐ 可调间隔 |
| 低频信号处理 | ⭐⭐⭐⭐ 优先级路由有效 |
| 高频信号处理 | ⭐⭐⭐ 需要观察优先级计算开销 |

---

## 后续优化建议

1. **RadarEngine** - Scanner 链式流式处理
2. **CognitionEngine** - 增量持久化替代定期批处理
3. **DataSource 管理** - 根据注意力状态动态调整数据源优先级
4. **Strategy Runtime** - 高注意力信号触发时优先调度相关策略
5. **Bandit Optimizer** - 结合注意力状态调整探索/利用平衡

---

*文档生成时间: 2026-03-25*
