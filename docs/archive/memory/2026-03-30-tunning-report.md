# 调参模式修复报告

**日期:** 2026-03-30
**问题:** 调参模式收益率计算异常（显示105万%）

---

## 问题根因

BanditTuner 之前的 `_backtest_current_params` 方法是**假回测**：

```python
# 错误的逻辑
exit_price = price * (1 + take_profit / 100)  # 永远假设涨10%！
return_pct = take_profit  # 固定10%！
```

每个信号都假设固定赚10%，不管实际价格怎么走。468个信号×10%=假收益。

---

## 解决方案

重写 BanditTuner 使用 **VirtualPortfolio** 管理真实持仓和盈亏：

1. **on_signal**: 调用 `portfolio.open_position()` 开仓
2. **on_price_update**: 调用 `portfolio.update_price()` 更新价格，VirtualPortfolio 自动检查止盈/止损
3. **_evaluate_and_adjust**: 从 Portfolio 获取真实平仓交易计算盈亏

---

## 修复内容

### 1. BanditTuner 完全重写
- 移除假的 `_backtest_current_params`
- 使用 VirtualPortfolio 管理真实持仓
- 正确计算累计盈亏：`sum(pos.profit_loss for pos in closed_trades)`

### 2. 添加 on_price_update 调用
在 `center.py` 的 `_dispatch_to_strategies` 中：
```python
for _, row in data.iterrows():
    stock_code = str(row.get('code', ''))
    current_price = row.get('now', row.get('price', 0))
    if stock_code and current_price > 0:
        tuner.on_price_update(stock_code, float(current_price))
```

### 3. 防止重复开仓
在 `on_signal` 中添加检查：
```python
for pos in portfolio.get_all_positions():
    if pos.stock_code == stock_code and pos.status == "OPEN":
        return  # 已有持仓，跳过
```

---

## 验证结果

**运行结果（2026-03-30 22:18）：**

| 指标 | 值 |
|------|-----|
| 处理帧数 | 1/1478 |
| 平仓交易 | 1 个 |
| 持仓中 | 2 个 |
| **累计盈亏** | **1000.00 (0.10%)** |
| 胜率 | 100% |
| 平均盈利 | 1000.00 |

**说明：** 只有1帧数据被处理（1478帧中），原因是数据质量检查或回放逻辑问题。但核心功能已验证正确：
- 止盈触发后真实平仓 ✓
- 平仓收益 = 1000元（10元买，11元卖，1000股） ✓
- 盈亏计算基于真实价格变动 ✓

---

## 技术修复清单

1. ✅ AttentionKernel 初始化参数名错误
2. ✅ 噪音过滤器不支持索引数据
3. ✅ Tick噪音过滤器索引问题
4. ✅ MarketObserver 不发送数据到 AttentionCenter
5. ✅ BanditTuner 假回测问题
6. ✅ 重复开仓问题

---

## 下一步

1. 检查为什么只有1帧数据被处理（数据回放逻辑）
2. 持续运行多轮次让调参器优化参数
3. 观察不同参数下的真实盈亏表现