# Skills 技能系统文档

## 概述

Skills 技能系统是 OpenClaw 的用户技能系统，提供可扩展的功能模块。每个技能都是一个独立的功能单元，可以被加载和使用，为系统提供各种扩展能力。

## 核心特性

- **模块化设计**：每个技能都是独立的模块，易于维护和扩展
- **可插拔架构**：技能可以动态加载和卸载
- **统一接口**：所有技能遵循统一的接口规范
- **丰富的技能库**：内置多种实用技能
- **元数据支持**：每个技能都有完整的元数据描述

## 技能目录结构

```
skills/
├── agent-browser/         # 浏览器自动化技能
├── find-skills/          # 技能搜索技能
├── github-trend-observer/ # GitHub 趋势追踪技能
├── naja-test-launcher/   # Naja 测试启动器技能
├── proactive-agent/       # 主动式 AI Agent 技能
├── self-improving-agent/  # 自改进 Agent 技能
├── skill-vetter/         # 技能审查技能
├── stock-info-explorer/   # 股票信息探索技能
├── stream_skill/         # 流处理技能
├── summarize/            # 摘要生成技能
├── tavily-search/         # Tavily 搜索技能
├── xiaohongshu-mcp/      # 小红书 MCP 技能
└── futu/                 # 富途相关技能
    ├── openapi-skills/
    │   └── futuapi/     # 富途 API 技能
    ├── install-opend/    # 安装 OpenD 技能
    └── search-skills/   # 搜索相关技能
        ├── comment-sentiment/
        ├── news-search/
        └── stock-digest/
```

## 主要技能详解

### 1. Agent Browser - 浏览器自动化

**位置**：[skills/agent-browser/](file:///workspace/skills/agent-browser/)

浏览器自动化 CLI，用于网页交互、导航、表单填写、按钮点击、截图、数据提取、Web 应用测试等。

**主要功能**：
- 网页导航和交互
- 表单填写和提交
- 按钮点击和元素操作
- 页面截图和数据提取
- Web 应用自动化测试

**相关文件**：
- [SKILL.md](file:///workspace/skills/agent-browser/SKILL.md) - 技能说明
- [CONTRIBUTING.md](file:///workspace/skills/agent-browser/CONTRIBUTING.md) - 贡献指南

### 2. GitHub Trend Observer - GitHub 趋势追踪

**位置**：[skills/github-trend-observer/](file:///workspace/skills/github-trend-observer/)

追踪 GitHub 热门项目和趋势，提供开源项目洞察。

**主要功能**：
- GitHub 趋势项目追踪
- 星标历史分析
- 雷达脉冲监控
- 信号观察
- 深度链接生成

**语言支持**：
- 中文 (cn/)
- 英文 (en/)

**相关文件**：
- [cn/skill.md](file:///workspace/skills/github-trend-observer/cn/skill.md) - 中文技能说明
- [en/skill.md](file:///workspace/skills/github-trend-observer/en/skill.md) - 英文技能说明

### 3. Proactive Agent - 主动式 AI Agent

**位置**：[skills/proactive-agent/](file:///workspace/skills/proactive-agent/)

主动式 AI Agent 架构，提供自主决策和行动能力。

**主要功能**：
- 自主决策和行动
- 心跳机制
- 灵魂配置
- 工具调用
- 用户交互

**相关文件**：
- [SKILL.md](file:///workspace/skills/proactive-agent/SKILL.md) - 技能说明
- [assets/AGENTS.md](file:///workspace/skills/proactive-agent/assets/AGENTS.md) - Agent 文档
- [assets/SOUL.md](file:///workspace/skills/proactive-agent/assets/SOUL.md) - 灵魂配置
- [assets/TOOLS.md](file:///workspace/skills/proactive-agent/assets/TOOLS.md) - 工具说明

### 4. Self-Improving Agent - 自改进 Agent

**位置**：[skills/self-improving-agent/](file:///workspace/skills/self-improving-agent/)

能够自我学习和改进的 Agent 系统。

**主要功能**：
- 自动错误检测
- 功能请求收集
- 学习记录
- 技能提取
- 钩子集成

**相关文件**：
- [SKILL.md](file:///workspace/skills/self-improving-agent/SKILL.md) - 技能说明
- [.learnings/](file:///workspace/skills/self-improving-agent/.learnings/) - 学习记录目录

### 5. Stock Info Explorer - 股票信息探索

**位置**：[skills/stock-info-explorer/](file:///workspace/skills/stock-info-explorer/)

股票信息查询和分析技能。

**主要功能**：
- 股票数据获取
- 股票信息查询
- 市场数据分析

**相关文件**：
- [SKILL.md](file:///workspace/skills/stock-info-explorer/SKILL.md) - 技能说明
- [scripts/yf.py](file:///workspace/skills/stock-info-explorer/scripts/yf.py) - Yahoo Finance 脚本

### 6. Tavily Search - Tavily 搜索

**位置**：[skills/tavily-search/](file:///workspace/skills/tavily-search/)

基于 Tavily 的搜索引擎集成。

**主要功能**：
- 网络搜索
- 内容提取
- 搜索结果处理

**相关文件**：
- [SKILL.md](file:///workspace/skills/tavily-search/SKILL.md) - 技能说明

### 7. Xiaohongshu MCP - 小红书 MCP

**位置**：[skills/xiaohongshu-mcp/](file:///workspace/skills/xiaohongshu-mcp/)

小红书平台的 MCP 集成。

**主要功能**：
- 小红书数据访问
- 内容交互
- 平台集成

**相关文件**：
- [SKILL.md](file:///workspace/skills/xiaohongshu-mcp/SKILL.md) - 技能说明
- [scripts/xhs_client.py](file:///workspace/skills/xiaohongshu-mcp/scripts/xhs_client.py) - 小红书客户端

### 8. Stream Skill - 流处理技能

**位置**：[skills/stream_skill/](file:///workspace/skills/stream_skill/)

流处理相关技能，集成 Deva 的流处理能力。

**主要功能**：
- 流数据处理
- Agent 接口
- 策略集成
- 执行引擎

**相关文件**：
- [stream_skill.py](file:///workspace/skills/stream_skill/stream_skill.py) - 主技能文件
- [agent_interface.py](file:///workspace/skills/stream_skill/agent_interface.py) - Agent 接口
- [execution_engine.py](file:///workspace/skills/stream_skill/execution_engine.py) - 执行引擎

### 9. Futu API - 富途 API 技能

**位置**：[skills/futu/openapi-skills/futuapi/](file:///workspace/skills/futu/openapi-skills/futuapi/)

富途 OpenAPI 集成，提供完整的股票交易和数据查询功能。

**主要功能**：
- 行情数据获取（K线、报价、快照等）
- 交易操作（下单、撤单、查询等）
- 实时数据推送
- 账户和组合管理

**子模块**：
- **quote/** - 行情相关功能
  - 经纪队列、资金分布、资金流向
  - 期货信息、历史K线、IPO列表
  - 市场状态、期权链、订单簿
  - 股东板块、板块列表、板块股票
  - 价格提醒、参考股票列表、复权数据
  - 实时数据、快照、股票筛选
  - 股票信息、股票报价、逐笔成交
  - 交易日、用户信息、用户证券
  - 用户证券组、窝轮、修改用户证券
  - 解析期权代码、设置价格提醒

- **subscribe/** - 订阅相关功能
  - 推送经纪队列、推送K线、推送订单簿
  - 推送报价、推送实时数据、推送逐笔成交
  - 查询订阅、订阅、取消订阅、取消所有订阅

- **trade/** - 交易相关功能
  - 撤单、获取账户现金流、获取账户
  - 获取所有组合、获取历史成交列表
  - 获取历史订单、获取保证金比例
  - 获取最大交易数量、获取订单费用
  - 获取成交列表、获取订单、获取组合
  - 修改订单、下单

**相关文件**：
- [SKILL.md](file:///workspace/skills/futu/openapi-skills/futuapi/SKILL.md) - 技能说明

## 技能开发规范

### 技能文件结构

每个技能应包含以下文件：

```
skill-name/
├── SKILL.md          # 技能说明文档
├── _meta.json        # 技能元数据
├── scripts/          # 脚本文件（可选）
├── assets/           # 资源文件（可选）
├── config/           # 配置文件（可选）
└── references/       # 参考文档（可选）
```

### 技能元数据格式

`_meta.json` 文件应包含技能的基本信息：

```json
{
  "name": "技能名称",
  "version": "1.0.0",
  "description": "技能描述",
  "author": "作者",
  "categories": ["分类1", "分类2"]
}
```

## 相关文档

- [docs/skills/README.md](file:///workspace/docs/skills/README.md) - 技能系统文档
- [CODE_WIKI.md](file:///workspace/CODE_WIKI.md) - 项目总览文档

---

**文档版本**：1.0
**最后更新**：2026-04-13
