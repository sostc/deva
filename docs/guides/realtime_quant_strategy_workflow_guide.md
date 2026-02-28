# Deva 实时行情与窗口策略完整使用说明

## 1. 文档目标

本文给出一套可直接复用的产品使用流程：

1. 创建 5 秒执行一次的实盘行情数据源（盘中有效）。
2. 创建并落库多个策略（逐条分组窗口策略 + 30 秒板块异动策略）。
3. 完成绑定、启动、验证、排错。

适用场景：你希望在 Deva Admin UI 中完成“数据源 -> 策略 -> 窗口计算 -> 输出”的完整链路。

---

## 2. 前置条件

1. 已安装并可运行 deva 项目。
2. Admin UI 可访问（包含数据源和策略管理页面）。
3. 依赖库已安装：

```bash
pip install easyquotation pandas
```

4. 盘中判断依赖：`deva.admin_ui.strategy.tradetime` 模块可正常导入。
5. 板块补齐依赖：`NB("naja")["basic_df"]` 可用（由系统已有股票基础信息准备流程生成）。

---

## 3. 流程总览

```text
实时行情数据源(realtime_quant_5s, 5s)
    -> 策略A: symbol分组窗口(代码内维护窗口, record模式)
    -> 策略B: 30秒板块异动(sliding_window=6, window模式)
```

---

## 4. 创建 5 秒行情数据源（UI 方式）

### 4.1 UI 配置建议

1. 进入“数据源管理” -> 新建数据源。
2. 类型选择：`TIMER`。
3. 数据源名称：`realtime_quant_5s`。
4. 执行间隔：`5` 秒。
5. 粘贴以下数据源代码（必须包含 `fetch_data` 函数）：

```python
def gen_quant():
    import easyquotation
    import pandas as pd

    quotation_engine = easyquotation.use("sina")
    q1 = quotation_engine.market_snapshot(prefix=False)
    df = pd.DataFrame(q1).T
    df = df[(True ^ df["close"].isin([0]))]
    df = df[(True ^ df["now"].isin([0]))]
    df["p_change"] = (df.now - df.close) / df.close
    df["p_change"] = df.p_change.map(float)
    df["code"] = df.index
    return df


def get_realtime_quant():
    """获取实盘实时行情,非盘中时间不获取数据"""
    import datetime
    from deva.admin_ui.strategy.tradetime import is_tradedate, is_tradetime

    if is_tradedate(datetime.datetime.today()) and is_tradetime(datetime.datetime.now()):
        return gen_quant()
    return None


def fetch_data():
    return get_realtime_quant()
```

6. 保存后可在列表查看状态与最近数据。

---

## 5. 创建策略 A：symbol 分组窗口策略（record 模式）

### 5.1 设计说明

1. 使用 `record` 模式逐条接收 tick/快照。
2. 在策略代码内按 `symbol` 维护 `deque(maxlen=N)`。
3. 每个 symbol 的窗口满后输出信号。

### 5.2 UI 配置建议

1. 进入“策略管理” -> 新建策略。
2. 策略名：`symbol_group_window_signal`。
3. 绑定数据源：`realtime_quant_5s`。
4. 计算模式：`record`。
5. 粘贴以下策略代码：

```python
from collections import deque
import time

WINDOW_SIZE = 5
MIN_CHANGE = 0.01
_symbol_windows = {}


def process(data):
    if not isinstance(data, dict):
        return None

    symbol = data.get("symbol")
    if not symbol:
        return None

    try:
        price = float(data.get("price"))
    except Exception:
        return None

    ts = data.get("ts", time.time())

    w = _symbol_windows.get(symbol)
    if w is None:
        w = deque(maxlen=WINDOW_SIZE)
        _symbol_windows[symbol] = w

    w.append((ts, price))
    if len(w) < WINDOW_SIZE:
        return None

    first_ts, first_price = w[0]
    last_ts, last_price = w[-1]
    if first_price == 0:
        return None

    change_ratio = (last_price - first_price) / first_price
    if change_ratio > MIN_CHANGE:
        signal = "BUY"
    elif change_ratio < -MIN_CHANGE:
        signal = "SELL"
    else:
        signal = "HOLD"

    return {
        "symbol": symbol,
        "window_size": WINDOW_SIZE,
        "start_ts": first_ts,
        "end_ts": last_ts,
        "start_price": first_price,
        "end_price": last_price,
        "change_ratio": change_ratio,
        "signal": signal,
    }
```

说明：该策略适用于单条行情结构。如果上游是 DataFrame，请改为 DataFrame 版本。

---

## 6. 创建策略 B：30 秒板块异动策略（window + sliding）

### 6.1 设计说明

1. 数据源 5 秒一次。
2. 策略窗口大小设为 `6`，对应约 30 秒。
3. 策略逻辑取窗口首尾帧，补齐板块信息后计算板块变化 Top/Bottom。

### 6.2 UI 配置建议

1. 新建策略名：`block_change_30s`。
2. 绑定数据源：`realtime_quant_5s`。
3. 计算模式：`window`。
4. 窗口类型：`sliding`。
5. 窗口大小：`6`。
6. `window_return_partial`：`False`。
7. 粘贴策略代码：

```python
def process(data):
    """30秒内板块变化排序，输出涨幅/跌幅Top10的HTML"""
    import pandas as pd
    from deva.admin_ui.strategy.data import Stock

    if data is None:
        return None

    if not isinstance(data, (list, tuple)) or len(data) < 2:
        return None

    start_df = data[0]
    end_df = data[-1]

    if not isinstance(start_df, pd.DataFrame) or not isinstance(end_df, pd.DataFrame):
        return None
    if start_df.empty or end_df.empty:
        return None

    need_start = {"code", "now", "close"}
    need_end = {"code", "now", "p_change"}
    if not need_start.issubset(set(start_df.columns)):
        return "<p>起始窗口字段不足</p>"
    if not need_end.issubset(set(end_df.columns)):
        return "<p>结束窗口字段不足</p>"

    start = start_df[["code", "now", "close"]].copy()
    end = end_df[["code", "now", "p_change"]].copy()

    start["code"] = start["code"].astype(str)
    end["code"] = end["code"].astype(str)

    merged = end.merge(start, on="code", how="inner", suffixes=("", "_start"))
    if merged.empty:
        return "<p>暂无可用数据</p>"

    merged = merged[(merged["close"] != 0) & merged["now_start"].notna() & merged["now"].notna()]
    if merged.empty:
        return "<p>暂无有效数据</p>"

    merged["change"] = (merged["now"] - merged["now_start"]) / merged["close"]

    view_df = merged[["code", "change", "p_change"]].copy()
    view_df["change"] = pd.to_numeric(view_df["change"], errors="coerce")
    view_df["p_change"] = pd.to_numeric(view_df["p_change"], errors="coerce")
    view_df = view_df.dropna(subset=["change"])
    if view_df.empty:
        return "<p>暂无有效变化数据</p>"

    enriched = Stock.render(view_df)
    if "blockname" not in enriched.columns:
        enriched["blockname"] = "unknown"
    enriched["blockname"] = enriched["blockname"].fillna("unknown").astype(str)

    by_block = enriched[enriched["blockname"] != "unknown"]
    if by_block.empty:
        by_block = enriched

    max_html = (
        by_block.sort_values(["change"], ascending=False)
        .groupby("blockname").head(3)
        .groupby("blockname", as_index=True)
        .mean(numeric_only=True)
        .sort_values("change", ascending=False)
        .head(10)
        .to_html()
    )

    min_html = (
        by_block.sort_values(["change"], ascending=True)
        .groupby("blockname").head(3)
        .groupby("blockname", as_index=True)
        .mean(numeric_only=True)
        .sort_values("change", ascending=True)
        .head(10)
        .to_html()
    )

    return max_html + "<br>" + min_html
```

---

## 7. 启动顺序与运行建议

1. 先启动数据源 `realtime_quant_5s`。
2. 再启动策略 A 与策略 B。
3. 盘中观察输出；非交易时段 `fetch_data()` 返回 `None` 属于预期。

建议：

1. 策略 B 使用 `window_return_partial=False`，避免窗口未满时误触发。
2. 设置合理的策略历史记录上限，避免过量持久化。
3. 如果页面显示策略有输出但内容为空，优先检查字段是否满足 `code/now/close/p_change`。

---

## 8. 数据库落库校验

默认 SQLite 路径：`/Users/<your_user>/.deva/nb.sqlite`

### 8.1 校验数据源

```python
from deva import NB

db = NB("data_sources")
for k, v in db.items():
    m = v.get("metadata", {})
    if m.get("name") == "realtime_quant_5s":
        print("found", m.get("id"), m.get("source_type"), m.get("interval"))
```

### 8.2 校验策略

```python
from deva import NB

db = NB("strategy_units")
for k, v in db.items():
    m = v.get("metadata", {})
    if m.get("name") in {"symbol_group_window_signal", "block_change_30s"}:
        print(m.get("name"), m.get("id"), m.get("bound_datasource_name"), m.get("compute_mode"), m.get("window_type"), m.get("window_size"))
```

---

## 9. 常见问题与排查

### 9.1 `easyquotation` 导入失败

安装依赖：

```bash
pip install easyquotation
```

### 9.2 非盘中没有数据

这是预期行为。`get_realtime_quant()` 在非交易日或非交易时间返回 `None`。

### 9.3 板块列缺失或全为 unknown

1. 检查 `Stock.render` 依赖数据是否准备好（`NB("naja")["basic_df"]`）。
2. 检查 `code` 字段是否是 6 位股票代码字符串。

### 9.4 策略窗口无输出

1. 确认策略配置为 `window + sliding + size=6`。
2. 确认数据源间隔是 5 秒且正在输出。
3. 确认 `window_return_partial=False` 时已积累满 6 个窗口样本。

---

## 10. 最佳实践

1. 把“交易时间过滤”放在数据源侧，减少无效策略计算。
2. 把“重计算开销大”的逻辑放到窗口策略，按批次处理。
3. 输出统一结构（DataFrame 或 dict），便于下游展示与告警。
4. 任何策略升级都先在小流量数据源验证，再切换生产数据源。

