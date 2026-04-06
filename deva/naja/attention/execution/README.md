# Execution 层 - 交易执行层

## 用途
负责交易指令的执行，包括信号执行、仓位管理等。

## 待迁移文件
```
trading_center.py     # 交易中心
signal_executor.py    # 信号执行器
focus_manager.py      # 焦点管理
liquidity_manager.py  # 流动性管理
portfolio.py          # 组合管理
price_monitor.py      # 价格监控
```

## 核心能力
- 信号到订单的转换
- 仓位管理
- 流动性管理
