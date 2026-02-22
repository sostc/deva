from __future__ import absolute_import, division, print_function
from .browser import browser, tab, tabs
from .lambdas import _
from .pipe import *
from .search import IndexStream
from .bus import *
from .future import *
from .endpoints import *
from .when import *
from .namespace import *
from .sources import *
from .graph import *
from .compute import *
from .core import *

from .logging_adapter import setup_deva_logging
setup_deva_logging()


# from .monitor import Monitor


def sync_gpt(prompts):
    from .llm import sync_gpt as _sync_gpt
    return _sync_gpt(prompts)


async def async_gpt(prompts):
    from .llm import async_gpt as _async_gpt
    return await _async_gpt(prompts)

"""
流式计算框架 Deva - 构建智能数据管道的核心工具

基于声明式流编程范式，提供高效的数据管道构建与执行能力，特别适用于开发实时监控系统、数据分析系统等事件驱动型应用。核心定位：

■ 流计算范式 - 数据自动流动与级联计算
■ 可视化编排 - 支持拖拽式管道设计
■ 弹性扩展 - 动态添加/移除处理节点
■ 状态管理 - 带状态计算的自动持久化

核心能力架构:

1. 流式编程模型
- 声明式管道: 通过 >> 操作符构建数据流图，自动建立处理链路
- 响应式计算: 数据变更自动触发下游计算，支持级联更新
- 函数式组合: 提供 map/filter/reduce 等操作符链式组合

2. 计算原语体系
- 内置流类型:
  * DBStream: 时序数据库流(自动维护存储/时间窗口查询)
  * IndexStream: 全文检索流
  * FileLogStream: 文件日志流(滚动存储/实时追踪)

3. 事件驱动应用
- 监控系统构建:
    sensors >> anomaly_detect >> alert  # 异常检测告警
    logs >> pattern_analyze >> dashboard  # 日志实时分析
    
- 数据分析系统:
    kafka_source >> realtime_etl >> feature_store >> ml_pipeline
    db_stream.window(300).aggregate() >> report_generator

4. 高效开发实践
- 流式lambda简化:
    _ * 2 >> log  # 自动展开为 lambda x: x*2
- 异步处理集成:
    async_data | async_db_query | async_emit
- 可视化调试工具:
    stream.visualize()  # 生成流拓扑图
    stream.webview()    # Web监控面板

5. 生产级特性
- 智能背压管理: 自动缓冲控制与流速调节
- 持久化保障: 重要状态自动持久化到 DBStream
- 错误恢复: 支持异常流重试与数据重放
    DBStream('events').replay(speed=2)  # 2倍速历史回放
- 资源治理: 连接数/内存/存储的自动管控

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

▌数据采集系统
- 智能爬虫:
    BrowserCrawler(urls) 
    >> extract_data 
    >> DBStream('crawled')
    >> auto_export
- IoT数据处理:
    device_streams.merge() 
    >> deduplicate 
    >> time_window_aggregate

技术体系:

数据输入 -> 流计算层 -> 输出系统
    │           │            │
    ├─事件驱动──┼─流水线处理─┼─实时可视化
    ├─消息队列  │ 状态计算   │ 时序数据库
    └─日志文件  └─AI模型集成─┴─API服务

核心优势:
• 复杂事件处理(CEP)支持: 内置时间窗口/模式匹配等语义
• 计算存储一体化: 流处理与DBStream深度集成
• 多范式统一: 兼容同步/异步/批处理混合编程
• 生产就绪: 内置背压控制/自动扩容/故障恢复机制
"""


__version__ = '1.4.1'
