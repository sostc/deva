# Skills 技能系统指南

> 基于最新代码结构（2026-03-17）

## 概述

Deva 技能系统分为两类：
1. **OpenClaw 用户技能** (`skills/`) - 用户级技能
2. **Trae IDE 集成技能** (`.trae/skills/`) - IDE 集成技能

## OpenClaw 用户技能

| 技能 | 说明 | 路径 |
|------|------|------|
| **proactive-agent** | 主动式 AI Agent 架构 | `skills/proactive-agent/` |
| **self-improving-agent** | 自改进 Agent | `skills/self-improving-agent/` |
| **github-trend-observer** | GitHub 趋势追踪 | `skills/github-trend-observer/` |
| **agent-browser** | 浏览器自动化 | `skills/agent-browser/` |
| **stock-info-explorer** | 股票信息探索 | `skills/stock-info-explorer/` |
| **tavily-search** | Tavily 搜索 | `skills/tavily-search/` |
| **xiaohongshu-mcp** | 小红书 MCP | `skills/xiaohongshu-mcp/` |
| **skill-vetter** | 技能审核 | `skills/skill-vetter/` |
| **summarize** | 总结技能 | `skills/summarize/` |
| **find-skills** | 技能搜索 | `skills/find-skills/` |

## Trae IDE 集成技能

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

## 技能创建

### 使用 skill-creator

推荐使用 `skill-creator` skill 创建新技能：

```bash
# 参考 .trae/skills/skill-creator/
```

### 技能结构

```
skill-name/
├── SKILL.md           # 技能定义
├── _meta.json         # 元数据
├── scripts/           # 脚本目录
├── references/        # 参考文档
└── evals/            # 评估数据
```

## 相关文档

- [CLI 使用指南](cli/README.md)
- [skill-creator skill](../.trae/skills/skill-creator/SKILL.md)
