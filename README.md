# Deva

智能量化与数据处理平台。

## 核心特性

- **流式处理**：基于 Stream 类的异步数据流处理框架
- **事件驱动**：基于 Tornado 的事件循环和异步处理
- **认知系统**：Naja 子系统提供市场叙事追踪、跨信号分析、洞察生成
- **注意力调度**：智能资源分配和策略优先级管理
- **雷达检测**：市场模式、异常和概念漂移检测
- **量化策略**：支持 River 策略、多数据源、信号处理
- **自适应交易**：基于多臂老虎机的 Bandit 交易系统

## 安装

```bash
pip install deva
pip3 install deva
```

## 快速启动

```bash
python -m deva.naja
```

## 文档

详细文档请查看 [Wiki](https://github.com/sostc/deva/wiki)。

## 项目结构

```
deva/
├── core/               # Deva 核心引擎
├── naja/               # Naja 量化交易平台
│   ├── application/    # 应用层
│   ├── attention/      # 注意力系统
│   ├── bandit/         # Bandit 交易
│   ├── cognition/      # 认知系统
│   ├── market_hotspot/ # 市场热点
│   ├── radar/          # 雷达系统
│   └── strategy/       # 策略系统
└── skills/             # 用户技能
```
