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

### 2. 韩信 - 交易员
- **职责**: 启动策略实验室，分析信号并执行交易
- **功能**:
  - 启动和管理策略实验室
  - 实时监控信号流
  - 识别买入信号
  - 执行买入操作 (需风控审批)

### 3. 萧何 - 风控官
- **职责**: 仓位管理、风险控制、资金管理
- **功能**:
  - 管理所有持仓
  - 计算风险指标
  - 审批交易请求
  - 监控资金使用

### 4. 刘邦 - 监督者
- **职责**: 监督其他智能体，总把控项目
- **功能**:
  - 注册和管理所有智能体
  - 监控系统健康状态
  - 处理异常和告警
  - 提供优化建议

## 🚀 快速开始

### 1. 创建四个智能体

```python
from deva.naja.agent import create_four_agents

# 配置参数
config = {
    'zhangliang': {'auto_analyze': True},
    'hanxin': {
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
hanxin = agents['韩信']
xiaohe = agents['萧何']
liubang = agents['刘邦']
```

### 2. 启动智能体

```python
from deva.naja.agent import get_agent_manager

manager = get_agent_manager()
manager.start_all_agents()

# 韩信启动策略实验室
hanxin.start_strategy_lab("双均线策略")
```

### 3. 监控系统

```python
# 获取系统状态
status = manager.get_system_status()

# 获取风险指标
risk_metrics = xiaohe.get_risk_metrics()

# 获取性能报告
report = liubang.get_performance_report()
```

## 📚 相关文档

- [Deva 核心文档](../../README.rst)
- [策略管理指南](../../docs/admin_ui/strategy_guide.md)

## ⚠️ 注意事项

1. **风控第一**: 所有交易都必须通过萧何的风控检查
2. **顺序启动**: 先创建策略，再启动智能体
3. **监控告警**: 密切关注刘邦的系统监控和告警
4. **配置合理**: 根据实际资金情况配置萧何的风险参数

---

**创建时间**: 2026-03-07  
**更新时间**: 2026-03-17
