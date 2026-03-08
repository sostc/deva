# Deva 智能体系统

基于 Deva 框架的多智能体交易系统，模拟古代谋士角色实现现代化的量化交易自动化系统。

## 📖 概述

这个智能体系统包含四个角色，每个角色都有明确的职责和协作关系:

### 角色分工

```
┌─────────────────────────────────────────────────────────┐
│                   智能体系统架构                         │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  刘邦 (监督者)                                          │
│  ├─ 监督所有智能体运行状态                              │
│  ├─ 系统健康监控和告警                                  │
│  └─ 协调整体系统运行                                    │
│                                                         │
│  张良 (策略师) ──────→ 韩信 (交易员) ──────→ 萧何 (风控官)│
│  ├─ 创建策略         ├─ 分析信号流       ├─ 仓位管理   │
│  ├─ 分析策略逻辑     ├─ 执行买入         ├─ 风险控制   │
│  └─ 通知韩信         └─ 请求风控检查     └─ 资金管理   │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

## 🎯 智能体职责

### 1. 张良 - 策略创建师
- **职责**: 创建新的交易策略，分析策略逻辑
- **功能**:
  - 创建策略并绑定数据源
  - 分析策略的买入/卖出条件
  - 识别策略的风控措施
  - 将策略逻辑告知韩信
- **关键方法**:
  - `create_strategy()`: 创建新策略
  - `analyze_strategy()`: 分析策略逻辑
  - `update_strategy_logic()`: 更新策略逻辑

### 2. 韩信 - 交易员
- **职责**: 启动策略实验室，分析信号并执行交易
- **功能**:
  - 启动和管理策略实验室
  - 实时监控信号流
  - 识别买入信号
  - 执行买入操作 (需风控审批)
- **关键方法**:
  - `start_strategy_lab()`: 启动策略
  - `analyze_signal_stream()`: 分析信号流
  - `execute_buy()`: 执行买入
  - `auto_trade_loop()`: 自动交易循环

### 萧何 - 风控官
- **职责**: 仓位管理、风险控制、资金管理
- **功能**:
  - 管理所有持仓
  - 计算风险指标
  - 审批交易请求
  - 监控资金使用
- **关键方法**:
  - `check_risk()`: 风控检查
  - `add_position()`: 添加持仓
  - `close_position()`: 平仓
  - `get_risk_metrics()`: 获取风险指标

### 刘邦 - 监督者
- **职责**: 监督其他智能体，总把控项目
- **功能**:
  - 注册和管理所有智能体
  - 监控系统健康状态
  - 处理异常和告警
  - 提供优化建议
- **关键方法**:
  - `register_agent()`: 注册智能体
  - `check_system_health()`: 检查系统健康
  - `get_performance_report()`: 获取性能报告
  - `optimize_system()`: 系统优化建议

## 🚀 快速开始

### 1. 创建四个智能体

```python
from deva.naja.agent import create_four_agents

# 配置参数
config = {
    'zhangliang': {'auto_analyze': True},
    'chenping': {
        'signal_analysis_interval': 5,
        'auto_trade_enabled': True
    },
    'xiaohe': {
        'total_capital': 1000000.0,
        'max_position_size': 0.2,
        'max_total_exposure': 0.8
    },
    'liubang': {
        'health_check_interval': 30
    }
}

# 创建智能体
agents = create_four_agents(config)

zhangliang = agents['张良']
chenping = agents['陈平']
xiaohe = agents['萧何']
liubang = agents['刘邦']
```

### 2. 创建策略

```python
from deva.naja.strategy import get_strategy_manager, StrategyEntry, StrategyMetadata

strategy_code = """
def process(window, context):
    if len(window) < 5:
        return None
    
    prices = [item.get('close', 0) for item in window]
    short_ma = sum(prices[-3:]) / 3
    long_ma = sum(prices[-5:]) / 5
    
    if short_ma > long_ma:
        return {
            'action': 'buy',
            'confidence': 0.8
        }
    return None
"""

strategy_mgr = get_strategy_manager()
metadata = StrategyMetadata(bound_datasource_id="my_data", window_size=5)
strategy = StrategyEntry(metadata=metadata)
strategy.set_code(strategy_code)
strategy.set_name("双均线策略")
strategy_mgr.add("双均线策略", strategy)
```

### 3. 张良分析策略

```python
# 分析策略逻辑
logic = zhangliang.analyze_strategy("双均线策略")

print(f"策略逻辑：{logic.logic_description}")
print(f"买入条件：{logic.entry_conditions}")
print(f"卖出条件：{logic.exit_conditions}")
print(f"风控措施：{logic.risk_controls}")
```

### 4. 启动智能体

```python
from deva.naja.agent import get_agent_manager

manager = get_agent_manager()

# 启动所有智能体
manager.start_all_agents()

# 韩信启动策略实验室
hanxin.start_strategy_lab("双均线策略")
```

### 5. 监控系统

```python
# 获取系统状态
status = manager.get_system_status()
print(f"智能体数量：{status['agent_count']}")

# 获取风险指标
risk_metrics = xiaohe.get_risk_metrics()
print(f"风险等级：{risk_metrics['risk_level']}")
print(f"可用资金：{risk_metrics['available_capital']}")

# 获取性能报告
report = liubang.get_performance_report()
print(f"系统健康：{report['system_health']}")
```

## 📊 智能体通信

智能体之间通过消息总线进行通信:

### 张良 → 韩信
```python
# 张良通知韩信策略逻辑
zhangliang.send_message({
    'type': 'strategy_logic_notification',
    'to': '韩信',
    'strategy_name': '双均线策略',
    'logic': {...}
})
```

### 韩信 → 萧何
```python
# 韩信请求风控检查
hanxin.send_message({
    'type': 'risk_check_request',
    'to': '萧何',
    'signal': {
        'strategy_name': '双均线策略',
        'confidence': 0.8
    }
})

# 萧何回复风控结果
xiaohe.send_message({
    'type': 'risk_check_response',
    'to': '韩信',
    'approved': True,
    'suggested_amount': 10000
})
```

### 所有智能体 → 刘邦
```python
# 智能体向刘邦报告状态
agent.send_message({
    'type': 'status_report',
    'to': '刘邦',
    'status': 'running',
    'metrics': {...}
})
```

## 🔧 配置说明

### 张良配置
```python
{
    'auto_analyze': True,  # 自动分析新策略
}
```

### 韩信配置
```python
{
    'signal_analysis_interval': 5,  # 信号分析间隔 (秒)
    'auto_trade_enabled': True,      # 启用自动交易
}
```

### 萧何配置
```python
{
    'total_capital': 1000000.0,       # 总资金
    'max_position_size': 0.2,         # 最大仓位比例
    'max_total_exposure': 0.8,        # 最大风险暴露
    'max_drawdown_limit': 0.1,        # 最大回撤限制
    'var_limit': 0.05                 # VaR 限制
}
```

### 刘邦配置
```python
{
    'health_check_interval': 30,      # 健康检查间隔 (秒)
    'alert_thresholds': {
        'error_count': 5,             # 错误数量阈值
        'max_drawdown': 0.1,          # 最大回撤
        'min_capital_ratio': 0.2      # 最小资金比例
    }
}
```

## 📝 使用示例

完整示例请参考:
- [four_agents_example.py](four_agents_example.py) - 四个智能体的完整使用示例

运行示例:
```bash
python deva/examples/agents/four_agents_example.py
```

## 🎯 最佳实践

### 1. 启动顺序
```python
# 1. 创建智能体
agents = create_four_agents()

# 2. 创建策略
create_strategy(...)

# 3. 张良分析策略
zhangliang.analyze_strategy(...)

# 4. 启动智能体
manager.start_all_agents()

# 5. 陈平启动策略
chenping.start_strategy_lab(...)
```

### 2. 风控优先
```python
# 陈平在执行交易前会自动请求萧何的风控检查
# 确保萧何配置合理的风险参数
config = {
    'xiaohe': {
        'max_position_size': 0.2,  # 单仓位不超过 20%
        'max_total_exposure': 0.8  # 总暴露不超过 80%
    }
}
```

### 3. 系统监控
```python
# 定期检查系统状态
@timer(interval=60, start=True)
def check_system():
    status = manager.get_system_status()
    health = liubang.check_system_health()
    
    if health == SystemHealth.CRITICAL:
        log.error("系统严重告警!")
        manager.stop_all_agents()
```

### 4. 异常处理
```python
try:
    strategy = zhangliang.create_strategy(...)
except Exception as e:
    log.error(f"创建策略失败：{e}")
    # 刘邦会自动记录告警
```

## 🔍 监控和调试

### 查看智能体状态
```python
for name, agent in manager.get_all_agents().items():
    print(f"{name}: {agent.state.state}")
    print(f"  错误数：{agent.state.error_count}")
    print(f"  最后操作：{agent.state.last_action_ts}")
```

### 查看系统指标
```python
metrics = liubang.get_system_metrics()
print(f"总策略数：{metrics.total_strategies}")
print(f"活跃策略：{metrics.active_strategies}")
print(f"总交易数：{metrics.total_trades}")
```

### 查看告警
```python
alerts = liubang.get_alerts()
for alert in alerts:
    print(f"[{alert['level']}] {alert['title']}: {alert['message']}")
```

## 📚 相关文档

- [Deva 核心文档](../../README.rst)
- [策略管理指南](../../docs/admin_ui/strategy_guide.md)
- [信号流文档](../signal/README.md)

## ⚠️ 注意事项

1. **风控第一**: 所有交易都必须通过萧何的风控检查
2. **顺序启动**: 先创建策略，再启动智能体
3. **监控告警**: 密切关注刘邦的系统监控和告警
4. **配置合理**: 根据实际资金情况配置萧何的风险参数
5. **日志记录**: 所有智能体的操作都会记录日志

## 🎓 学习路径

1. **入门**: 运行 `four_agents_example.py` 了解基本用法
2. **理解**: 阅读每个智能体的源代码，理解职责和实现
3. **实践**: 创建自己的策略，配置智能体参数
4. **优化**: 根据实际需求调整风控参数和监控阈值
5. **扩展**: 基于 BaseAgent 创建自定义智能体

---

**创建时间**: 2026-03-07  
**版本**: 1.0.0  
**维护者**: Deva 团队
