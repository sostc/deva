# 快速参考 - 数据源与策略配对

## 常用配对模板

### 模板1: 异常检测流程
```
数据源: tick (逐笔)
字段: ts, code, price, volume
↓
策略: radar
输出: signal_type="anomaly", score=0-1
```

**数据源代码:**
```python
def fetch_data():
    return {
        "ts": time.time(),
        "code": "000001",
        "price": 10.5 + random.random() * 0.1,
        "volume": random.randint(100, 10000),
    }
```

**策略代码:**
```python
def process(data, context=None):
    raw = data.get("data", {})
    price = raw.get("price", 0)

    is_anomaly = price > 10.6 or price < 9.4

    return {
        "signal_type": "anomaly",
        "score": 1.0 if is_anomaly else 0.0,
        "value": price,
        "message": "异常" if is_anomaly else "正常"
    }
```

---

### 模板2: 趋势检测流程
```
数据源: kline (K线)
字段: ts, code, open, high, low, close, volume
↓
策略: radar
输出: signal_type="trend", score=0-1
```

**数据源代码:**
```python
def fetch_data():
    return {
        "ts": time.time(),
        "code": "000001",
        "open": 10.0,
        "high": 10.5,
        "low": 9.8,
        "close": 10.2,
        "volume": 1000000,
    }
```

**策略代码:**
```python
def process(data, context=None):
    raw = data.get("data", {})
    open_p = raw.get("open", 0)
    close_p = raw.get("close", 0)

    change = (close_p - open_p) / open_p * 100 if open_p > 0 else 0

    if change > 2:
        signal = "uptrend"
        score = min(1.0, change / 5)
    elif change < -2:
        signal = "downtrend"
        score = min(1.0, abs(change) / 5)
    else:
        signal = "sideways"
        score = 0.3

    return {
        "signal_type": signal,
        "score": score,
        "value": change
    }
```

---

### 模板3: 新闻分析流程
```
数据源: news (新闻)
字段: ts, title, content, source
↓
策略: memory
输出: content, topic, sentiment
```

**数据源代码:**
```python
def fetch_data():
    return {
        "ts": time.time(),
        "title": "公司业绩大幅增长",
        "content": "某公司发布财报，净利润同比增长50%",
        "source": "财经网",
    }
```

**策略代码:**
```python
def process(data, context=None):
    raw = data.get("data", {})
    content = raw.get("content", "")
    title = raw.get("title", "")

    # 简单情绪分析
    positive_words = ["增长", "盈利", "利好", "上涨"]
    negative_words = ["下跌", "亏损", "利空", "风险"]

    sentiment = 0.0
    for w in positive_words:
        if w in content:
            sentiment += 0.2
    for w in negative_words:
        if w in content:
            sentiment -= 0.2
    sentiment = max(-1.0, min(1.0, sentiment))

    # 提取主题
    topic = "业绩"
    if "并购" in content:
        topic = "并购"
    elif "政策" in content:
        topic = "政策"

    return {
        "content": title + " " + content,
        "topic": topic,
        "sentiment": sentiment,
    }
```

---

### 模板4: 交易信号流程
```
数据源: tick (逐笔) + 技术指标
字段: ts, code, price, ma5, ma20, volume
↓
策略: bandit
输出: signal_type=BUY/SELL, stock_code, price, confidence
```

**数据源代码:**
```python
def fetch_data():
    return {
        "ts": time.time(),
        "code": "000001",
        "price": 10.5,
        "ma5": 10.3,
        "ma20": 10.1,
        "volume": 50000,
    }
```

**策略代码:**
```python
def process(data, context=None):
    raw = data.get("data", {})
    code = raw.get("code", "")
    price = raw.get("price", 0)
    ma5 = raw.get("ma5", price)
    ma20 = raw.get("ma20", price)

    if ma5 > ma20 * 1.02:
        signal = "BUY"
        confidence = min(1.0, (ma5 - ma20) / ma20 * 10)
    elif ma5 < ma20 * 0.98:
        signal = "SELL"
        confidence = min(1.0, (ma20 - ma5) / ma20 * 10)
    else:
        signal = "BUY"
        confidence = 0.3

    return {
        "signal_type": signal,
        "stock_code": code,
        "price": price,
        "confidence": confidence,
    }
```

---

## 输出格式速查

| 目标 | 必填字段 | 示例 |
|------|----------|------|
| **radar** | signal_type, score | `{"signal_type": "anomaly", "score": 0.8}` |
| **memory** | content | `{"content": "新闻内容", "topic": "业绩"}` |
| **bandit** | signal_type, stock_code, price | `{"signal_type": "BUY", "stock_code": "000001", "price": 10.5}` |

---

## 常见错误检查

### 1. 数据源返回格式错误
```python
# ❌ 错误: 返回列表
return [{"price": 10}]

# ✅ 正确: 返回字典
return {"ts": time.time(), "price": 10}
```

### 2. 策略未获取原始数据
```python
# ❌ 错误: 直接使用 data
price = data.get("price")

# ✅ 正确: 先获取 data
raw = data.get("data", {})
price = raw.get("price")
```

### 3. 输出缺少必填字段
```python
# ❌ 错误: radar 缺少 score
return {"signal_type": "anomaly"}

# ✅ 正确: 包含所有必填字段
return {"signal_type": "anomaly", "score": 0.8}
```

### 4. 字段类型错误
```python
# ❌ 错误: score 是字符串
return {"signal_type": "anomaly", "score": "0.8"}

# ✅ 正确: score 是浮点数
return {"signal_type": "anomaly", "score": 0.8}
```

---

## 数据流检查清单

创建完成后，检查：

- [ ] 数据源 fetch_data 返回字典
- [ ] 数据源包含必填字段 (ts, code)
- [ ] 策略正确获取 data.get("data")
- [ ] 策略访问字段使用 raw.get("field")
- [ ] 策略返回字典
- [ ] 策略包含目标类型的必填字段
- [ ] 字段类型正确 (float, str, list)
