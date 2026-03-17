# 数据源创建 Prompts

## 基础模板

### 1. 创建数据源 - 基础版

```
你是一个专业的数据源工程师。请帮我创建一个数据源。

## 基本信息
- 数据源名称: {name}
- 数据源类型: {source_type} (custom/timer/replay/event_trigger)
- 描述: {description}

## 数据源类型说明
- custom: 自定义代码数据源，需要提供 fetch_data 函数
- timer: 定时器数据源，按固定间隔执行
- replay: 回放数据源，从历史数据回放
- event_trigger: 事件触发数据源

## 输出数据结构要求
请确保 fetch_data 返回的数据包含以下字段：

### 逐笔数据 (tick)
```python
{
    "ts": float,          # 时间戳 (必填)
    "code": str,          # 股票代码 (必填)
    "price": float,       # 价格 (必填)
    "volume": float,      # 成交量 (可选)
    "amount": float,      # 成交额 (可选)
    "direction": str,     # 买卖方向 buy/sell (可选)
}
```

### K线数据 (kline)
```python
{
    "ts": float,          # 时间戳 (必填)
    "code": str,          # 股票代码 (必填)
    "open": float,        # 开盘价 (必填)
    "high": float,        # 最高价 (必填)
    "low": float,         # 最低价 (必填)
    "close": float,       # 收盘价 (必填)
    "volume": float,      # 成交量 (可选)
    "amount": float,      # 成交额 (可选)
}
```

### 新闻数据 (news)
```python
{
    "ts": float,          # 时间戳 (必填)
    "title": str,         # 标题 (必填)
    "content": str,       # 内容 (必填)
    "source": str,        # 来源 (可选)
    "url": str,           # 链接 (可选)
}
```

## 执行配置
- 执行模式: {execution_mode} (timer/scheduler/event_trigger)
- 执行间隔: {interval} 秒 (timer 模式)
- 定时配置: {scheduler_trigger} (interval/cron/date)
- Cron表达式: {cron_expr} (scheduler 模式)

## 代码要求
1. 必须包含 fetch_data 函数
2. 函数必须返回字典或列表
3. 必须包含必填字段
4. 数据类型必须正确

## 输出格式
请直接输出可以运行的 Python 代码，不需要解释。
```

---

### 2. 创建策略 - 完整版

```
你是一个专业的策略工程师。请帮我创建一个策略。

## 策略基本信息
- 策略名称: {name}
- 策略描述: {description}
- 策略类型: {strategy_type} (legacy/river/plugin/declarative)

## 数据源信息 (输入)
策略将接收来自以下数据源的数据：

### 数据源类型: {datasource_type}
```
{datasource_fields}
```

### 数据接收格式
策略收到的数据会被包装成以下格式：
```python
{
    "_datasource_id": str,        # 数据源ID
    "_datasource_name": str,      # 数据源名称
    "_receive_time": float,       # 接收时间戳
    "data": {...}                 # 原始数据 (见上方)
}
```

### 数据访问方式
在 process 函数中：
```python
def process(data, context=None):
    # 获取原始数据
    raw = data.get("data", {})

    # 访问具体字段
    ts = raw.get("ts")
    code = raw.get("code")
    price = raw.get("price")
    # ...
```

## 输出目标 (必须明确)
- 输出目标: {handler_type}
- 必须是以下之一: radar / memory / bandit / llm

### 各目标输出格式要求

#### 1. radar (技术指标/异常检测)
```python
{
    "signal_type": str,     # 信号类型 (必填): anomaly/drift/volatility/trend
    "score": float,         # 分数 0-1 (必填)
    "value": float,         # 数值 (可选)
    "message": str,         # 说明信息 (可选)
}
```

#### 2. memory (语义分析/记忆)
```python
{
    "content": str,        # 内容 (必填): 文本内容
    "topic": str,          # 主题 (可选)
    "sentiment": float,    # 情绪 -1到1 (可选)
    "tags": list,          # 标签列表 (可选)
}
```

#### 3. bandit (交易信号)
```python
{
    "signal_type": str,    # 信号类型 (必填): BUY/SELL
    "stock_code": str,     # 股票代码 (必填)
    "stock_name": str,     # 股票名称 (可选)
    "price": float,        # 价格 (必填)
    "confidence": float,   # 置信度 0-1 (可选)
    "amount": float,       # 金额 (可选)
    "reason": str,         # 原因说明 (可选)
}
```

#### 4. llm (LLM调节)
```python
{
    # 包含以上所有字段的组合
    "signal_type": str,
    "score": float,
    "content": str,
    "stock_code": str,
    "price": float,
    "confidence": float,
    # ...
}
```

## 策略代码模板

```python
def process(data, context=None):
    # 1. 获取原始数据
    raw = data.get("data", {})

    # 2. 提取需要的字段
    ts = raw.get("ts", 0)
    code = raw.get("code", "")
    price = raw.get("price", 0)

    # 3. 实现策略逻辑
    # ... your logic here ...

    # 4. 返回符合输出格式的结果
    return {
        # 根据 handler_type 返回对应字段
    }
```

## 注意事项
1. 必填字段必须返回，否则数据会被丢弃
2. 字段类型必须正确 (float, str, list 等)
3. 值必须在合理范围内 (如 score 0-1, confidence 0-1)
4. handler_type 必须与输出格式匹配

## 输出要求
请直接输出策略代码，不需要解释。
```

---

### 3. 数据源 + 策略联合创建 Prompt

```
你是一个专业的量化系统工程师。请帮我创建完整的数据源和策略组合。

## 任务目标
创建一个数据源和一个策略，使它们能正确协作。

## 数据源规范

### 数据源类型: {datasource_type}
- tick (逐笔): ts, code, price, volume
- kline (K线): ts, code, open, high, low, close, volume
- news (新闻): ts, title, content, source

### 数据源输出格式 (必须严格遵守)
```python
{
    "ts": float,        # 时间戳
    "code": str,        # 股票代码
    # ... 根据类型添加其他字段
}
```

## 策略规范

### 输入: 来自上述数据源的数据

### 输出目标: {handler_type}
- radar: 需要 signal_type, score
- memory: 需要 content
- bandit: 需要 signal_type, stock_code, price

### 策略输出格式 (必须严格遵守)
```python
{
    # {handler_type} 所需的必填字段
}
```

## 代码要求

### 数据源代码
```python
def fetch_data():
    # 返回符合格式的数据
    return {
        "ts": time.time(),
        "code": "000001",
        # ... 其他字段
    }
```

### 策略代码
```python
def process(data, context=None):
    raw = data.get("data", {})

    # 处理数据

    return {
        # 返回符合 {handler_type} 格式的结果
    }
```

## 输出格式
请按以下格式输出：
```python
# ===== 数据源 =====
[数据源代码]

# ===== 策略 =====
[策略代码]

# ===== 说明 =====
- 数据源类型: {datasource_type}
- 策略类型: legacy
- 输出目标: {handler_type}
- 数据流: {datasource_type} → process() → {handler_type}
```

---

### 4. 完整策略配置 Prompt

```
请帮我创建一个完整的策略配置。

## 策略名称
{name}

## 策略描述
{description}

## 数据源配置
- 数据源名称: {datasource_name}
- 数据源类型: {datasource_type}
- 数据格式:
{datasource_schema}

## 策略配置

### 策略类型
{strategy_type}
- legacy: Python 函数
- river: River ML 模型
- plugin: 插件
- declarative: 声明式

### 输出目标
{handler_type}
- radar: 技术指标 (需要 signal_type, score)
- memory: 语义分析 (需要 content)
- bandit: 交易信号 (需要 signal_type, stock_code, price)
- llm: LLM调节 (需要组合字段)

### 输入数据处理
原始数据会被包装为:
```python
{
    "_datasource_id": "xxx",
    "_datasource_name": "xxx",
    "_receive_time": 1234567890.123,
    "data": {
        # 实际数据
    }
}
```

请生成完整的策略代码，确保：
1. 正确解析输入数据
2. 实现策略逻辑
3. 返回符合 {handler_type} 格式的输出
```

---

### 5. 数据契约验证 Prompt

```
请检查以下数据源和策略是否匹配。

## 数据源配置
```python
def fetch_data():
    return {datasource_output}
```

## 策略配置
```python
def process(data, context=None):
    raw = data.get("data", {})
    # 使用 raw.get("field_name") 获取字段
    return {strategy_output}
```

## 验证要求

### 1. 数据源输出检查
- [ ] 必填字段是否存在
- [ ] 字段类型是否正确
- [ ] 数据格式是否一致

### 2. 策略输入检查
- [ ] 是否正确获取 data.get("data")
- [ ] 是否正确访问 raw.get("field_name")
- [ ] 是否处理了可能的缺失字段

### 3. 策略输出检查
- [ ] 必填字段是否返回
- [ ] 字段类型是否正确
- [ ] 是否符合 {handler_type} 格式

### 4. 整体检查
- [ ] 数据源 → 策略 数据流是否顺畅
- [ ] 错误处理是否完善
- [ ] 边界情况是否考虑

请给出检查结果和修复建议。
```

---

### 6. 快速创建模板

```
创建数据源和策略，数据源类型={datasource_type}，策略输出目标={handler_type}

数据源返回: {datasource_fields}
策略返回: {handler_fields}

请按以下格式输出：
1. 数据源代码 (包含 fetch_data)
2. 策略代码 (包含 process)
```
