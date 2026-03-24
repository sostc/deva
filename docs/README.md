# Deva 文档中心

> 最后更新：2026-03-17

## 📦 项目概览

**Deva** 是一个智能量化与数据处理平台，包含以下核心组件：

| 组件 | 说明 | 路径 |
|------|------|------|
| **Deva Core** | 核心引擎（消息总线、管道、数据源、调度） | `deva/core/` |
| **Admin UI** | Web 管理后台（PyWebIO） | `deva/admin/` |
| **Naja** | 量化交易平台 | `deva/naja/` |
| **Skills** | 用户技能（OpenClaw） | `skills/` |
| **Trae Skills** | Trae IDE 集成技能 | `.trae/skills/` |
| **CLI** | 命令行工具 | `cli/` |

---

## 📚 文档目录

### 🚀 快速入门

- [安装指南](guides/installation.md) - 环境配置与启动
- [快速开始](guides/quickstart.md) - 5 分钟入门

### 🏗️ 架构与核心

- [Naja 架构总览](guides/naja_architecture.md) - Naja 量化平台架构 ⭐
- [核心引擎](core/README.md) - Deva 核心组件说明
- [数据流与调度](guides/dataflow_scheduling.md) - 数据流、事件、调度机制

### 📡 Naja 量化平台

| 模块 | 说明 | 文档 |
|------|------|------|
| 策略系统 | River 策略、多数据源、信号处理 | [策略指南](naja/strategy_guide.md) |
| 数据源 | 数据源创建与管理 | [数据源指南](naja/datasource_guide.md) |
| 认知系统 | 认知中枢、叙事追踪、跨信号分析 | [认知系统](naja/cognition_guide.md) |
| 注意力系统 | 注意力调度、策略管理、预算分配 | [注意力系统](naja/attention_guide.md) |
| 雷达检测 | 模式检测、异常检测、漂移检测 | [雷达系统](naja/radar_guide.md) |
| Bandit 交易 | 自适应交易、虚拟组合 | [Bandit 交易](naja/bandit_guide.md) |
| LLM 调节 | 模型控制、性能优化 | [LLM 调节](naja/llm_controller_guide.md) |
| 性能监控 | 锁监控、存储监控 | [性能监控](naja/performance_guide.md) |

### 🖥️ Admin UI 管理后台

- [Admin UI 架构](admin/ARCHITECTURE.md)
- [Admin UI 快速指南](admin/QUICKSTART.md)
- [任务管理](admin/task_guide.md)
- [数据源管理](admin/datasource_guide.md)
- [策略管理](admin/strategy_guide.md)

### 🧠 Skills 技能系统

#### OpenClaw 用户技能

| 技能 | 说明 | 路径 |
|------|------|------|
| **proactive-agent** | 主动式 AI Agent 架构 | `skills/proactive-agent/` |
| **self-improving-agent** | 自改进 Agent | `skills/self-improving-agent/` |
| **github-trend-observer** | GitHub 趋势追踪 | `skills/github-trend-observer/` |
| **agent-browser** | 浏览器自动化 | `skills/agent-browser/` |
| **stock-info-explorer** | 股票信息探索 | `skills/stock-info-explorer/` |
| **tavily-search** | Tavily 搜索 | `skills/tavily-search/` |
| **xiaohongshu-mcp** | 小红书 MCP | `skills/xiaohongshu-mcp/` |

#### Trae IDE 集成技能

| 技能 | 说明 | 路径 |
|------|------|------|
| **strategy-creator** | 策略创建器（自然语言生成策略） | `.trae/skills/strategy-creator/` ⭐ |
| **datasource-creator** | 数据源创建器 | `.trae/skills/datasource-creator/` ⭐ |
| **river-market-insight** | 市场洞察（概念漂移检测） | `.trae/skills/river-market-insight/` |
| **skill-creator** | 技能创建与优化 | `.trae/skills/skill-creator/` |
| **stock-tick-analyzer** | 股票分笔数据分析 | `.trae/skills/stock-tick-analyzer/` |
| **xueqiu_mcp** | 雪球 MCP 数据查询 | `.trae/skills/xueqiu_mcp/` |
| **ye-wang-pan-duan** | 野王股票分析 | `.trae/skills/ye-wang-pan-duan/` |
| **video-downloader** | 视频下载 | `.trae/skills/video-downloader/` |
| **skills-sh** | Skills.sh 集成 | `.trae/skills/skills-sh/` |

### 💻 CLI 与工具

- [CLI 使用指南](cli/README.md) - 命令行工具说明
- [技能商店](cli/skills_store.md) - 技能安装与管理

### 🛠️ 运维脚本

- [运维脚本说明](scripts/README.md)
- [数据源管理脚本](scripts/datasource_scripts.md)
- [策略验证脚本](scripts/verification_scripts.md)

### 📋 最佳实践

- [数据字典 + 数据源 + 策略 E2E](guides/dictionary_enrichment_datasource_strategy_e2e.md) ⭐
- [实时行情量化策略工作流](guides/realtime_quant_strategy_workflow_guide.md)
- [Bandit 交易指南](guides/bandit_trading_guide.md)

---

## 🔗 快速导航

### 启动 Naja 平台

```bash
python -m deva.naja
```

访问 http://localhost:8080/

### 主要页面

| 页面 | 路径 | 说明 |
|------|------|------|
| 🏠 首页 | `/` | 系统概览 |
| ⏰ 任务管理 | `/taskadmin` | 定时任务 |
| 📡 数据源 | `/dsadmin` | 数据源配置 |
| 📈 策略管理 | `/strategyadmin` | 量化策略 |
| 🧠 认知系统 | `/cognition` | 认知中枢 |
| 🧩 注意力系统 | `/attentionadmin` | 注意力调度 |
| 📡 雷达事件 | `/radaradmin` | 雷达检测 |
| 🤖 Bandit | `/banditadmin` | 自适应交易 |
| ⚙️ 配置 | `/configadmin` | 系统配置 |

---

## 📝 文档规范

1. 使用 Markdown 格式
2. 文件名使用小写，单词间用下划线分隔
3. 在对应的分类目录下创建
4. 更新本索引文件

---

## 📞 相关链接

- [NAJA_OVERVIEW.md](NAJA_OVERVIEW.md) - Naja 架构详细说明
- [CHANGELOG.md](../CHANGELOG.md) - 版本变更日志
