# 策略创建 Prompts

## 基础模板

### 1. 雷达策略 (radar)

```
创建雷达策略。

## 策略名称
{name}

## 数据源信息
- 类型: {datasource_type}
- 字段: {datasource_fields}

## 输出目标: radar

## radar 输出格式 (严格遵守)
```python
{
    "signal_type": str,     # 信号类型 (必填)
                            # 可选: anomaly, drift, volatility, trend, burst, etc.
    "score": float,         # 分数 0-1 (必填)
    "value": float,        # 数值 (可选)
    "message": str,        # 说明信息 (可选)
}
```

## 策略逻辑要求
1. 分析输入数据
2. 计算 signal_type 和 score
3. 可选: 添加 value 和 message

## 代码模板
```python
def process(data, context=None):
    raw = data.get("data", {})

    # 获取数据
    price = raw.get("price", 0)
    volume = raw.get("volume", 0)

    # 策略逻辑
    is_anomaly = price > threshold

    return {
        "signal_type": "anomaly",    # 或 drift/volatility/trend
        "score": 0.8,                # 0-1 之间
        "value": price,
        "message": "检测到异常" if is_anomaly else "正常"
    }
```

请输出策略代码。
```

---

### 2. 记忆策略 (memory)

```
创建记忆策略。

## 策略名称
{name}

## 数据源信息
- 类型: {datasource_type}
- 字段: {datasource_fields}

## 输出目标: memory

## memory 输出格式 (严格遵守)
```python
{
    "content": str,        # 内容 (必填)
    "topic": str,          # 主题 (可选)
    "sentiment": float,    # 情绪 -1到1 (可选)
    "tags": list,          # 标签列表 (可选)
}
```

## 策略逻辑要求
1. 从输入数据提取内容
2. 分析主题、情绪
3. 生成标签

## 代码模板
```python
def process(data, context=None):
    raw = data.get("data", {})

    # 获取内容
    title = raw.get("title", "")
    content = raw.get("content", "")

    # 策略逻辑
    topic = extract_topic(content)
    sentiment = analyze_sentiment(content)

    return {
        "content": content,
        "topic": topic,
        "sentiment": sentiment,
        "tags": ["tag1", "tag2"]
    }
```

请输出策略代码。
```

---

### 3. 交易策略 (bandit)

```
创建交易策略。

## 策略名称
{name}

## 数据源信息
- 类型: {datasource_type}
- 字段: {datasource_fields}

## 输出目标: bandit

## bandit 输出格式 (严格遵守)
```python
{
    "signal_type": str,    # BUY/SELL (必填)
    "stock_code": str,     # 股票代码 (必填)
    "stock_name": str,     # 股票名称 (可选)
    "price": float,        # 价格 (必填)
    "confidence": float,   # 置信度 0-1 (可选)
    "amount": float,       # 金额 (可选)
    "reason": str,        # 原因说明 (可选)
}
```

## 策略逻辑要求
1. 分析数据生成交易信号
2. 确定 signal_type (BUY/SELL)
3. 确定 stock_code 和 price
4. 计算 confidence

## 代码模板
```python
def process(data, context=None):
    raw = data.get("data", {})

    # 获取数据
    code = raw.get("code", "")
    price = raw.get("price", 0)

    # 策略逻辑
    signal = "BUY" if condition else "SELL"
    confidence = 0.8

    return {
        "signal_type": signal,
        "stock_code": code,
        "price": price,
        "confidence": confidence,
        "reason": f"信号强度: {confidence}"
    }
```

请输出策略代码。
```

---

### 4. LLM 调节策略 (llm)

```
创建 LLM 调节策略。

## 策略名称
{name}

## 数据源信息
- 类型: {datasource_type}
- 字段: {datasource_fields}

## 输出目标: llm

## llm 输出格式 (严格遵守)
必须包含组合字段，用于 LLM 分析：
```python
{
    # 雷达字段
    "signal_type": str,
    "score": float,

    # 记忆字段
    "content": str,
    "topic": str,

    # 交易字段
    "stock_code": str,
    "price": float,
    "confidence": float,
}
```

## 策略逻辑要求
1. 综合分析各种数据
2. 生成多维度输出
3. 供 LLM 进行参数调节

## 代码模板
```python
def process(data, context=None):
    raw = data.get("data", {})

    # 各种分析
    radar_signal = analyze_radar(raw)
    memory_content = analyze_memory(raw)
    bandit_signal = analyze_bandit(raw)

    return {
        # 雷达
        "signal_type": radar_signal.get("type"),
        "score": radar_signal.get("score"),

        # 记忆
        "content": memory_content.get("text"),
        "topic": memory_content.get("topic"),

        # 交易
        "stock_code": bandit_signal.get("code"),
        "price": bandit_signal.get("price"),
        "confidence": bandit_signal.get("confidence"),
    }
```

请输出策略代码。
```

---

### 5. 异常检测策略模板

```
创建异常检测策略。

## 数据源: tick (逐笔数据)
```python
{
    "ts": float,      # 时间戳
    "code": str,      # 股票代码
    "price": float,   # 价格
    "volume": float,  # 成交量
}
```

## 输出: radar
```python
{
    "signal_type": "anomaly",  # 固定
    "score": float,            # 0-1, 异常程度
    "value": float,            # 当前价格
    "message": str,           # 说明
}
```

## 策略代码
```python
def process(data, context=None):
    raw = data.get("data", {})

    price = raw.get("price", 0)
    volume = raw.get("volume", 0)

    # 简单异常检测: 价格波动超过阈值
    threshold = 0.1
    is_anomaly = abs(price - 10.0) > threshold

    return {
        "signal_type": "anomaly",
        "score": 1.0 if is_anomaly else 0.0,
        "value": price,
        "message": "异常" if is_anomaly else "正常"
    }
```
```

---

### 6. 趋势检测策略模板

```
创建趋势检测策略。

## 数据源: kline (K线数据)
```python
{
    "ts": float,      # 时间戳
    "code": str,      # 股票代码
    "open": float,    # 开盘价
    "high": float,   # 最高价
    "low": float,    # 最低价
    "close": float,  # 收盘价
    "volume": float, # 成交量
}
```

## 输出: radar
```python
{
    "signal_type": "trend",  # 固定
    "score": float,          # 0-1, 趋势强度
    "value": float,          # 涨跌幅
}
```

## 策略代码
```python
def process(data, context=None):
    raw = data.get("data", {})

    open_price = raw.get("open", 0)
    close_price = raw.get("close", 0)

    # 计算涨跌幅
    change_pct = (close_price - open_price) / open_price * 100 if open_price > 0 else 0

    # 趋势判断
    if change_pct > 2:
        signal_type = "uptrend"
        score = min(1.0, change_pct / 5)
    elif change_pct < -2:
        signal_type = "downtrend"
        score = min(1.0, abs(change_pct) / 5)
    else:
        signal_type = "sideways"
        score = 0.3

    return {
        "signal_type": signal_type,
        "score": score,
        "value": change_pct
    }
```
```

---

### 7. 新闻分析策略模板

```
创建新闻分析策略。

## 数据源: news (新闻数据)
```python
{
    "ts": float,      # 时间戳
    "title": str,     # 标题
    "content": str,   # 内容
    "source": str,    # 来源
}
```

## 输出: memory
```python
{
    "content": str,      # 内容 (必填)
    "topic": str,        # 主题
    "sentiment": float,  # 情绪 -1到1
    "tags": list,        # 标签
}
```

## 策略代码
```python
def process(data, context=None):
    raw = data.get("data", {})

    title = raw.get("title", "")
    content = raw.get("content", "")

    # 简单分析
    keywords_positive = ["利好", "上涨", "增长", "盈利"]
    keywords_negative = ["利空", "下跌", "亏损", "风险"]

    sentiment = 0.0
    for kw in keywords_positive:
        if kw in content:
            sentiment += 0.2
    for kw in keywords_negative:
        if kw in content:
            sentiment -= 0.2

    # 提取主题
    topics = ["业绩", "政策", "并购", "分红"]
    found_topics = [t for t in topics if t in content]

    return {
        "content": title + " " + content[:100],
        "topic": found_topics[0] if found_topics else "其他",
        "sentiment": max(-1.0, min(1.0, sentiment)),
        "tags": found_topics
    }
```
```

---

### 8. 买卖信号策略模板

```
创建买卖信号策略。

## 数据源: tick + kline 组合
```python
{
    "ts": float,
    "code": str,
    "price": float,
    "volume": float,
    "ma5": float,   # 5日均线
    "ma20": float,  # 20日均线
}
```

## 输出: bandit
```python
{
    "signal_type": "BUY"/"SELL",  # 必填
    "stock_code": str,              # 必填
    "price": float,                 # 必填
    "confidence": float,            # 0-1
    "reason": str,
}
```

## 策略代码
```python
def process(data, context=None):
    raw = data.get("data", {})

    code = raw.get("code", "")
    price = raw.get("price", 0)
    ma5 = raw.get("ma5", price)
    ma20 = raw.get("ma20", price)

    # 金叉/死叉策略
    if ma5 > ma20 * 1.02:
        signal = "BUY"
        confidence = min(1.0, (ma5 - ma20) / ma20 * 10)
        reason = "金叉突破"
    elif ma5 < ma20 * 0.98:
        signal = "SELL"
        confidence = min(1.0, (ma20 - ma5) / ma20 * 10)
        reason = "死叉跌破"
    else:
        signal = "BUY"
        confidence = 0.3
        reason = "观望"

    return {
        "signal_type": signal,
        "stock_code": code,
        "price": price,
        "confidence": confidence,
        "reason": reason
    }
```
