# Naja 架构与使用文档（2026-03-14）

本文用于系统性说明 Naja 的架构、流程、思想、使用方法与注意事项，并总结近期的结构调整与改动，方便理解与后续演进。

**目录**
1. 架构与核心思想
2. 数据流与运行流程
3. 使用方法
4. 关键模块说明
5. 注意事项
6. 之前是什么样子，现在是什么样子
7. 发生了哪些改动
8. 后续可改进方向

**架构与核心思想**
Naja 是一个“可恢复单元（RecoverableUnit）驱动的统一管理平台”，目标是把数据源、策略、任务、信号、雷达检测、记忆系统、LLM 调节统一在一个平台里。

核心思想包含以下几点：
- 可恢复与自动化：关键组件用 RecoverableUnit 抽象，支持状态恢复与自动运行。
- 数据驱动：所有结果都回流为信号与事件，并进入雷达检测与记忆系统。
- 记忆系统优先：记忆系统不再只是单一策略，而是平台级能力，作为长期与跨场景的上下文。
- 统一 UI：管理平台以 Web UI 统一入口，按模块组织能力。

**数据流与运行流程**
1. 数据源产生数据（行情、新闻、日志、文件等）。
2. 数据流进入策略系统（StrategyEntry / MultiDatasourceStrategyEntry）。
3. 策略处理后输出结果进入结果存储（ResultStore）。
4. ResultStore 同步驱动两类能力：
- RadarEngine：产生雷达事件（pattern / drift / anomaly）。
- MemoryEngine：沉淀为分层记忆、主题与注意力结构。
5. LLM 调节读取 Radar 摘要 + Memory 摘要 + 策略性能指标，生成调节建议。
6. Web UI 提供可视化与操作入口。

**使用方法**
启动与访问：
1. 启动：`python -m deva.naja`
2. 访问入口：`http://localhost:8080/`
3. 记忆系统：`/memory`
4. 雷达事件：`/radaradmin`
5. 策略管理：`/strategyadmin`
6. 数据源管理：`/dsadmin`
7. 任务管理：`/taskadmin`
8. LLM 调节：`/llmadmin`
9. 信号流：`/signaladmin`

策略注册与初始化（记忆策略）：
- 注册脚本：`/Users/spark/pycharmproject/deva/deva/naja/strategy/tools/register_memory.py`
- 运行：`python /Users/spark/pycharmproject/deva/deva/naja/strategy/tools/register_memory.py`

**关键模块说明**
- 记忆系统核心：`/Users/spark/pycharmproject/deva/deva/naja/memory/core.py`
- 记忆引擎：`/Users/spark/pycharmproject/deva/deva/naja/memory/engine.py`
- 记忆 UI：`/Users/spark/pycharmproject/deva/deva/naja/memory/ui.py`
- 雷达引擎：`/Users/spark/pycharmproject/deva/deva/naja/radar/engine.py`
- 雷达 UI：`/Users/spark/pycharmproject/deva/deva/naja/radar/ui.py`
- 策略系统：`/Users/spark/pycharmproject/deva/deva/naja/strategy/`
- 多数据源策略：`/Users/spark/pycharmproject/deva/deva/naja/strategy/multi_datasource.py`
- 结果存储：`/Users/spark/pycharmproject/deva/deva/naja/strategy/result_store.py`
- LLM 调节：`/Users/spark/pycharmproject/deva/deva/naja/llm_controller/controller.py`
- Web UI 入口：`/Users/spark/pycharmproject/deva/deva/naja/web_ui.py`

**注意事项**
- 记忆策略必须注册后才会生效，注册脚本已迁移到 `strategy/tools`。
- RadarEngine 与 MemoryEngine 都依赖 ResultStore 的回流数据，若策略未运行则无事件与记忆沉淀。
- MemoryEngine 目前复用 LobsterRadarStrategy 的内部状态与持久化结构，长期来看需要改名与清理。
- LLM 调节现在读取雷达摘要与记忆摘要，同时依赖策略性能数据。
- 记忆数据可能增长较快，长期运行需关注持久化与清理策略。

**之前是什么样子，现在是什么样子**
之前：
- “雷达”页面指向 `/lobster`，本质是龙虾思想雷达 UI。
- 记忆系统核心逻辑放在 `strategy/plugins/lobster_radar.py`，属于策略插件目录。
- 记忆 UI 在 `naja/lobster/` 下，带兼容路由与导入路径。
- ResultStore 只驱动 RadarEngine，不驱动记忆引擎。
- LLM 调节只读取 Radar 摘要。

现在：
- “记忆”页面统一入口为 `/memory`，不再保留 `/lobster`。
- 记忆核心迁移到 `naja/memory/`，成为平台级能力。
- MemoryEngine 成为独立单例，ResultStore 会同时喂给雷达与记忆。
- LLM 调节同时读取雷达摘要与记忆摘要。
- 策略运维脚本统一归档到 `strategy/tools/`。

**发生了哪些改动**
结构调整：
- `strategy/plugins/lobster_radar.py` → `memory/core.py`
- `strategy/plugins/multi_datasource_strategy.py` → `strategy/multi_datasource.py`
- 记忆 UI 移到 `memory/ui.py`
- 删除 `naja/lobster/` 兼容目录与 `/lobster` 路由

功能改动：
- ResultStore 增加对 MemoryEngine 的回流
- LLM 调节增加记忆摘要输入
- 菜单改为“记忆”入口并指向 `/memory`

工具调整：
- 注册脚本迁移为 `strategy/tools/register_memory.py`
- 旧的修复/绑定脚本已移除

**后续可能需要改进的地方**
1. 命名统一
- 记忆系统内部仍保留 “lobster” 前缀（表名、变量、日志），应统一改为 “memory”。

2. 记忆查询与接口化
- 当前 MemoryEngine 主要用于内部沉淀，建议提供统一的查询接口（按主题、时间、注意力等）。

3. 持久化与数据治理
- 记忆持久化使用单表与单 key，后续可拆分为事件索引、主题索引与长短期分区。

4. 监控与可观测性
- 为记忆与雷达增加指标与告警（写入速率、异常增长、漂移检测分布）。

5. 记忆与策略/任务的联动
- 进一步把记忆系统作为策略前置上下文或任务触发条件，而不是仅展示。

6. UI 统一化
- 记忆 UI 和其他管理页风格仍有部分独立逻辑，可逐步抽到统一组件。

7. 数据源绑定策略优化
- 多数据源绑定的交互与脚本化可整合进 UI，降低维护成本。

