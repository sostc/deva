# 调参模式修复笔记

**日期:** 2026-03-30
**问题:** 调参模式无法产生信号

---

## 技术问题排查

### 1. AttentionKernel 初始化参数名错误
**文件:** `deva/naja/attention/center.py` 第 233 行

**问题:** 传入 `enable_four_dimensions=False` 但 AttentionKernel 不接受此参数
```
TypeError: AttentionKernel.__init__() got an unexpected keyword argument 'enable_four_dimensions'
```

**修复:**
```python
# 之前
self._attention_kernel = AttentionKernel(encoder, multi_head, memory, enable_four_dimensions=False)

# 之后
self._attention_kernel = AttentionKernel(encoder, multi_head, memory, enable_manas=False)
```

---

### 2. 噪音过滤器不支持索引数据
**文件:** `deva/naja/attention/processing/noise_filter.py`

**问题:** 当 DataFrame 使用 `set_index('code')` 后，`df[symbol_col]` 会报 KeyError
```
KeyError: 'code'
```

**修复:** 添加 `get_symbols()` 函数正确处理 symbol_col 可能是索引名的情况：
```python
def get_symbols(df, col):
    if col in df.columns:
        return df[col].astype(str)
    elif col == df.index.name:
        return df.index.astype(str)
    else:
        return pd.Series([''] * len(df), index=df.index)
```

---

### 3. Tick噪音过滤器同样的索引问题
**文件:** `deva/naja/attention/processing/tick_filter.py` 第 435-445 行

**修复:** 同样使用 get_symbols 方式处理

---

### 4. MarketObserver 不发送数据到 AttentionCenter
**文件:** `deva/naja/bandit/market_observer.py` 第 635-651 行

**问题:** `_on_replay_data` 只更新价格，**根本不调用 AttentionCenter.process_datasource_data**

**修复:** 在 `_on_replay_data` 中添加：
```python
# 将数据发送到 AttentionCenter 进行策略处理
try:
    from deva.naja.attention.center import get_orchestrator
    orch = get_orchestrator()
    orch.process_datasource_data('lab_replay', data)
    log.info(f"[MarketObserver] Lab 模式：已发送 {len(data)} 条数据到 AttentionCenter")
except Exception as e:
    log.warning(f"[MarketObserver] 发送数据到 AttentionCenter 失败: {e}")
```

---

## 验证结果

修复后测试通过：
- 注意力系统正常初始化 ✓
- 全局注意力: 0.6570 ✓
- 产生 117 个信号 ✓
- Momentum 策略成功执行 ✓

---

## 根本原因分析

之前的"无信号"问题不是因为参数过于严格，而是由于多个技术 bug 导致注意力系统初始化失败和数据流中断：

1. AttentionKernel 初始化失败 → 注意力系统无法正常工作
2. 噪音过滤器报错 → 数据处理流程中断
3. MarketObserver 不发送数据 → 策略管理器收不到数据

---

## 下一步

技术问题已解决，现在可以专注调参了。调参器会自动：
1. 放宽参数直到产生足够信号
2. 评估信号质量
3. 持续优化直到找到盈利参数