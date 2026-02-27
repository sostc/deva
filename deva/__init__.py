from __future__ import absolute_import, division, print_function
from .browser import browser, tab, tabs
from .lambdas import _
from .core.pipe import *
from .core.bus import *
from .endpoints import *
from .core.when import *
from .namespace import *
from .core.sources import *
from .core.compute import *
from .core.core import *
from .core.core import setup_deva_logging
from .core.utils.ioloop import get_io_loop
from .config import config, get_config, ConfigManager

setup_deva_logging()


def __getattr__(name):
    if name == "IndexStream":
        from .search import IndexStream as _IndexStream
        globals()["IndexStream"] = _IndexStream
        return _IndexStream
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

def sync_gpt(prompts):
    from .ai_platform.llm import sync_gpt as _sync_gpt
    return _sync_gpt(prompts)


async def async_gpt(prompts):
    from .ai_platform.llm import async_gpt as _async_gpt
    return await _async_gpt(prompts)

"""
Deva - 智能数据处理平台

Deva 采用分层架构设计，由两个核心平台组成：

1. 底层：异步实时流计算平台 (deva/core/)
   - 提供高性能的数据流处理能力
   - 支持异步事件驱动的流计算
   - 内置丰富的流操作符和数据源
   - 实现数据的实时处理和状态管理

2. 上层：AI 数据运算和策略定制平台 (deva/ai_platform/)
   - 整合 LLM 和 AI 相关功能
   - 提供可视化 UI 体验界面
   - 支持智能代码生成和策略定制
   - 实现 AI 辅助的数据分析和处理

核心能力架构:

【底层平台】
1. 流式编程模型
- 声明式管道: 通过 >> 操作符构建数据流图，自动建立处理链路
- 响应式计算: 数据变更自动触发下游计算，支持级联更新
- 函数式组合: 提供 map/filter/reduce 等操作符链式组合

2. 计算原语体系
- 内置流类型:
  * DBStream: 时序数据库流(自动维护存储/时间窗口查询)
  * IndexStream: 全文检索流
  * FileLogStream: 文件日志流(滚动存储/实时追踪)

3. 生产级特性
- 智能背压管理: 自动缓冲控制与流速调节
- 持久化保障: 重要状态自动持久化到 DBStream
- 错误恢复: 支持异常流重试与数据重放
- 资源治理: 连接数/内存/存储的自动管控

【上层平台】
1. AI 智能功能
- AI 智能对话: 与 AI 进行多轮对话，解答问题、提供建议
- AI 代码生成: 生成 Python/Deva 代码、策略、数据源和任务
- AI 文本处理: 摘要、翻译、润色等文本处理功能

2. 可视化管理界面
- 策略管理: 可视化策略编辑和执行
- 数据源管理: 统一管理各类数据源
- 任务管理: 任务调度和监控
- AI 工作室: 集成 AI 功能的综合工作环境

3. 策略定制
- 量化交易策略: 基于技术指标的自动交易策略
- 数据处理策略: 自定义数据处理流程
- 监控告警策略: 基于规则的异常检测和告警

典型应用场景:

▌智能监控系统
- 设备指标实时分析: 
    sensors.window(60).mean() >> threshold_check >> alert
- 日志异常检测:
    log_stream.map(parse) >> detect_errors >> ops_center

▌实时分析管道
- 流式ETL:
    kafka_source >> clean >> transform >> feature_store
- 交互式分析:
    (browser.inputs 
     >> feature_extract 
     >> model.predict 
     >> visualize)

▌AI 辅助开发
- 代码生成: 通过自然语言描述生成 Deva 代码
- 策略优化: 利用 AI 分析和优化现有策略
- 数据洞察: 通过 AI 分析发现数据中的模式和异常

技术体系:

数据输入 -> 底层流计算平台 -> 上层AI平台 -> 输出系统
    │              │                │              │
    ├─事件驱动──────┼─流水线处理────┼─AI模型集成───┼─实时可视化
    ├─消息队列      │ 状态计算       │ 智能分析     │ 时序数据库
    └─日志文件      └─存储管理       └─策略定制     └─API服务

核心优势:
• 分层架构: 底层流计算与上层AI功能分离，便于独立演进
• 高性能: 异步事件驱动设计，支持高并发数据流处理
• 智能能力: 集成 LLM 提供 AI 辅助功能
• 可视化: 提供直观的 Web 界面进行管理和操作
• 可扩展: 模块化设计，支持自定义扩展和插件
"""


__version__ = '1.5.0'
