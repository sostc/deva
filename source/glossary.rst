术语表
======

.. glossary::
   :sorted:

   Stream
      流。Deva 的核心概念，代表数据的流动管道。数据从源头流入，经过一系列处理算子，最终输出到目的地。

   Operator
      算子。用于对流中的数据进行处理和转换的函数，如 map、filter、reduce 等。

   Pipeline
      管道。多个算子串联形成的数据处理链路，数据依次通过每个算子进行处理。

   Event-driven
      事件驱动。一种编程范式，程序流程由事件（如消息到达、定时器触发）驱动。

   Message Bus
      消息总线。用于组件间通信的基础设施，支持发布订阅模式。

   Topic
      主题。消息总线中的消息分类，生产者将消息发布到主题，消费者订阅主题接收消息。

   Timer
      定时器。按固定间隔执行函数的机制，用于周期性任务。

   Scheduler
      调度器。按计划执行任务的机制，支持 CRON 表达式和复杂调度规则。

   DBStream
      数据库流。结合流处理和 SQLite 存储的组件，支持事件回放。

   Namespace
      命名空间。全局单例工厂，用于创建和访问命名的 Stream、Topic、DBStream 等对象。

   WebView
      Web 视图。将流数据以 Web 页面形式展示的机制，支持实时刷新。

   Sink
      接收器。数据流的终点，用于接收处理后的数据，如日志、数据库、消息队列等。

   Source
      数据源。数据流的起点，如文件、网络、定时器等。

   Window
      窗口。将流数据分组处理的机制，包括滑动窗口（sliding_window）和时间窗口（timed_window）。

   Rate Limit
      限流。控制数据流处理速度的机制，防止下游过载。

   Buffer
      缓冲。临时存储数据，积累到一定量后批量处理的机制。

   Backpressure
      背压。当下游处理不过来时，向上游传递压力信号，减缓数据流入的机制。

   Event Loop
      事件循环。持续监听和处理事件的循环机制，由 Deva.run() 启动。

   Async
      异步。非阻塞的执行模式，允许在等待 I/O 时执行其他任务。

   Future
      未来值。表示异步计算结果的占位符，稍后可以通过它获取结果。

   Coroutine
      协程。可以暂停和恢复的函数，用于编写异步代码。

   Publish-Subscribe
      发布订阅。一种消息模式，发布者将消息发送到主题，订阅者接收感兴趣主题的消息。

   Consumer Group
      消费者组。多个消费者组成的组，共同消费一个主题的消息，实现负载均衡。

   Key Mode
      键模式。DBStream 的两种数据组织方式：explicit（显式键）和 time（时间键）。

   Replay
      回放。从 DBStream 中按时间顺序重新读取历史事件的机制。

   Route
      路由。根据条件将消息分发到不同处理函数的机制。

   Endpoint
      输出端。将流数据发送到外部系统的组件，如 Kafka、Redis、邮件等。

   LLM
      大语言模型（Large Language Model）。如 GPT、Claude 等 AI 模型，Deva 提供集成接口。

   SSE
      服务器发送事件（Server-Sent Events）。一种服务器向浏览器推送实时数据的技术。

   CRON
      定时任务表达式，用于指定任务执行时间，如 "0 9 * * *" 表示每天 9 点执行。

   IPC
      进程间通信（Inter-Process Communication）。Deva 支持通过文件或 Redis 实现 IPC。

   Whoosh
      纯 Python 实现的全文检索引擎，Deva 用它实现流式全文搜索。

   Jieba
      中文分词库，Deva 用它处理中文文本的全文检索。
