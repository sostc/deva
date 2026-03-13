---
name: GitHub Radar
description: >
  AI PM 视角的 GitHub Intelligence Tool。
  不只展示数据，产出 PM 级别的 paradigm insight。
  底层调用本机已登录的 gh CLI + GitHub API。
version: 0.1.0
author: Kun
tags: [github, intelligence, pm-insight, trending, ecosystem-analysis]
categories: [research, developer-tools, product-intelligence]
---

# GitHub Radar

AI PM 的开源情报引擎。四种模式，一套 Layer 分析框架。

## 何时使用

- 「今天有什么值得看的」/ `--pulse` → Mode 1
- 「帮我找 [方向] 相关的 GitHub 项目」→ Mode 2
- 「监控异常信号」/ `--watch` → Mode 3
- 「分析 [repo] 的关联生态」→ Mode 4
- 任何涉及 GitHub 项目发现、趋势分析、范式判断的需求

## 文件结构

```
github-radar/
├── README.md                    # 项目文档
├── ONBOARD.md                   # Agent 冷启动指引
├── skill.md                     # Agent 执行指令
├── LICENSE                      # MIT 许可证
├── agents/
│   └── analyzer.md              # PM 洞察分析 agent 指令
├── scripts/
│   ├── gh_utils.py              # 统一 gh CLI 工具函数
│   ├── check_rate_limit.py      # API 速率检查
│   ├── fetch_star_history.py    # star 增长数据拉取
│   ├── radar_pulse.py           # Mode 1 trending 拉取
│   ├── search_repos.py          # Mode 2 搜索
│   ├── watch_signals.py         # Mode 3 异常检测
│   ├── deep_link.py             # Mode 4 关联分析
│   ├── generate_report.py       # HTML/MD 报告生成
│   └── test_oss.py              # 自动化测试（6 层 41 测试）
├── config/
│   ├── seed_list.json           # 关键开发者列表
│   └── domain_keywords.json     # 领域关键词映射
├── templates/
│   ├── radar-pulse.html         # Mode 1 报告模板
│   ├── direction-search.html    # Mode 2 报告模板
│   ├── signal-watch.html        # Mode 3 报告模板
│   └── deep-link.html           # Mode 4 报告模板
├── evals/
│   └── evals.json               # 测试用例
└── references/
    └── layer_model.md           # Layer 分类标准
```

## 依赖

| 依赖 | 要求 | 检查命令 |
|------|------|----------|
| gh CLI | >= 2.40.0，已登录 | `gh auth status` |
| Python | >= 3.9 | `python --version` |
| 额外 Python 包 | 无，仅用标准库 | — |
| API 额度 | 认证状态 5000 次/小时 | `python scripts/check_rate_limit.py` |

## 通用前置步骤

**每种模式执行前都必须先做：**

```bash
# 1. 检查 API 额度
python scripts/check_rate_limit.py
```

根据返回的 `mode` 字段决定运行策略：
- `full` → 正常执行，含 star 历史拉取
- `degraded` → 跳过 fetch_star_history.py，只用基础数据
- `minimal` → 只执行搜索脚本，不调详情 API

---

## Mode 1: 主动探索 (Radar Pulse)

**触发**：`--pulse` 或「今天有什么值得看的」

### 执行步骤

```bash
# Step 1: 检查额度
python scripts/check_rate_limit.py

# Step 2: 拉取候选
python scripts/radar_pulse.py --days 7

# Step 3: 读取 agents/analyzer.md + references/layer_model.md
#         Layer 分类 → 过滤 L1/L5 → 选 1-2 个最有 PM 价值的

# Step 4: 对精选项目拉取 star 历史（full 模式下）
python scripts/fetch_star_history.py owner/repo
```

### 过滤规则

1. 标注每个候选的 Layer
2. 移除 L1（模型本体，太底层）和 L5（wrapper/demo，噪声）
3. PM 价值加权：L2 × 1.5, L3 × 1.3, L4 × 1.0
4. 取 Top 3-5，精选 1-2 个展开

### 输出格式

```markdown
# Radar Pulse — {日期}
> L2/L3/L4 精选 | 从 {n} 个候选筛出 {m} 个 | API: {remaining}/{limit}

## 今日精选
### {repo} [L?]
> {description}
| Stars | 30d 增长 | 语言 | 创建 |
|-------|----------|------|------|
**为什么选它**：{理由}
**范式信号**：{stack 哪里在动}
**建议**：Mode 4 深挖 / 持续观察

## 其他值得一看
| Repo | Layer | Stars | 一句话 |
|------|-------|-------|--------|

## 过滤掉的
- L1: {n} 个（{代表}）
- L5: {n} 个（{代表}）
```

报告保存至：`output/radar-pulse_{date}.md`

---

## Mode 2: 重点方向搜索 (Direction Search)

**触发**：用户给出技术方向或关键词

### 执行步骤

#### Step 1: 检查额度
```bash
python scripts/check_rate_limit.py
```

#### Step 2: 关键词扩展 + Layer 1 相关性审查

1. **理解主题**：用一句话说清用户搜索的核心概念
2. **扩展关键词**：围绕主题生成 8-15 个搜索关键词，覆盖：
   - 同义表达（swarm → fleet, colony）
   - 场景限定（swarm observability, coding agent swarm）
   - 相邻概念（swarm 旁边的 coordination, monitoring）
3. **Layer 1 自审**：逐个审查，判断标准是**「搜出来的项目是否大部分在讲同一类事」**，不要求完全匹配每个词：
   - **保留**：搜出来的项目和主题是同一个话题的不同角度
   - **删除**：搜出来的项目大部分是更大的范畴，主题只是其中一小部分
   - 示例 — 主题「agent swarm」：`swarm orchestration` 保留（同话题）、`multi-agent framework` 删除（swarm 只是 multi-agent 的子集，搜出来大部分不是 swarm）
   - 示例 — 主题「Agent 和人协作」：`human-in-the-loop agent` 保留（同话题）、`AI assistant` 删除（助手 ≠ 人机协作）
4. **呈现给用户确认**：列出保留 + 删除的关键词及理由，用户确认后再搜

#### Step 3: 搜索
```bash
python scripts/search_repos.py "{主关键词}" \
  --also "{关键词2}" "{关键词3}" ... \
  --expand "{备用1}" "{备用2}" ... \
  --min-stars 20 --min-recall 50
```

#### Step 3.5: 召回不足时的动态策略

如果去重结果 < 50 个，**不要默默扩展**，而是向用户呈现当前情况并提供三个选项：

> 搜索了 {n} 个关键词，去重后只有 {m} 个结果。可能的原因和选项：
>
> **A. 该方向尚未形成独立品类** — 相关能力可能嵌在更大的框架里作为 feature 存在，而非独立项目。建议放弃搜索，这本身就是一个有价值的发现。
>
> **B. 关键词覆盖不够** — 当前关键词可能遗漏了社区常用的表达方式。我建议追加以下关键词：{列出}。确认后继续搜。
>
> **C. 用现有结果分析** — {m} 个结果虽然少，但如果质量足够，可以直接进入分析。适合快速了解方向概况。

判断倾向的依据：
- 大部分关键词返回 0 → 倾向 A（品类不存在）
- 只有主关键词有结果，扩展词无结果 → 倾向 B（表达方式没覆盖到）
- 结果少但高度相关 → 倾向 C（小品类但信号清晰）

#### Step 4: Layer 2 结果相关性分类

搜索返回原始结果后，**在分析前**对每个 repo 做相关性判断：

| 分类 | 标准 | 处理 |
|------|------|------|
| **high** | 这个项目就是在做这个主题的事 | 进入竞争格局分析 |
| **medium** | 和主题相关，但不是它的主要方向 | 视质量决定是否纳入 |
| **low** | 碰巧关键词匹配，实际在做另一件事 | 过滤掉，列入"过滤掉的项目" |

判断依据：repo 的名字 + 描述，问自己「这个项目的作者会认为自己在做{用户主题}吗？」

#### Step 5: Star 历史 + PM 分析

```bash
# 对 high/medium 中的重点项目拉取 star 增长（full 模式下）
python scripts/fetch_star_history.py owner/repo

# 读取 agents/analyzer.md 和 references/layer_model.md
# 对数据做 Layer 分类 + PM 洞察
```

### 输出结构

```
headline（一句范式级判断）
→ 值得关注（3-5 个深度分析卡片）
→ 竞争格局（按子类分表，数量取决于实际相关项目数）
→ 范式判断（蓝色边框段落）
→ 建议深挖（3-5 个，指向其他 Mode）
→ 过滤掉的（折叠，分组说明原因）
```

报告同时生成 HTML 和 MD：`output/search_{keyword}_{date}.html/.md`

---

## Mode 3: 异常信号监控 (Signal Watch)

**触发**：`--watch` 或「监控异常信号」

> **已知盲区**：当前只能检测**新项目**（90 天内创建）的增长异常。老项目突然爆发需要持久化存储做差值比较，留作后续迭代。

### 执行步骤

#### Step 1: 检查额度
```bash
python scripts/check_rate_limit.py
```

#### Step 2: 候选发现
```bash
python scripts/watch_signals.py
# 全局扫描（默认），三窗口: 7d/30d/90d
# 领域扫描: python scripts/watch_signals.py --domain ai-agent
# domain 可选: ai-agent, llm-tools, ai-infra, mcp, all(默认)
```

脚本返回候选列表（按粗速度降序），每个候选包含：
- `stars`, `forks`, `created`, `age_days`
- `rough_velocity` = stars / age_days（粗速度）
- `fork_ratio` = forks / stars（使用深度信号）

#### Step 3: 初筛 + 拉取增长曲线

1. **排除明显不相关的**：看 description，排除游戏、教程、awesome-list 等非技术项目
2. **对剩余候选拉取 star history**（full 模式下）：
```bash
python scripts/fetch_star_history.py owner/repo
```

返回的增长指标：
| 指标 | 含义 |
|------|------|
| `avg_daily_7d` / `avg_daily_30d` | 日均增长 |
| `acceleration` | 7d 日均 / 30d 日均，>1 加速中 |
| `trend_direction` | 最近 3 天均值 / 前 4 天均值，看当前趋势 |
| `consecutive_growth_days` | 连续增长天数 |
| `peak_recency` | 峰值距今天数，0=今天 |
| `burst_ratio` | 峰值日 / 7d 日均，高=spike 型 |
| `recent_7_days[]` | 每日明细，用于判断增长形态 |

#### Step 4: 增长形态判断

看 `recent_7_days[]` 的形状，判断增长属于哪种类型：

| 形态 | 特征 | PM 含义 | 信号质量 |
|------|------|---------|---------|
| **sustained** | `consecutive > 7` + `burst_ratio < 3` | 有机增长，真实需求 | 高 |
| **accelerating** | `trend_direction > 2` + `consecutive > 5` | 正在爆发，要抓住 | 最高 |
| **spike+decay** | `burst_ratio > 5` + `trend_direction < 0.5` | launch 一波流，可能是噪声 | 低 |
| **step** | 单日暴涨 + 前后平稳 | 事件驱动（大 V 转发） | 中，看后续 |

#### Step 5: 三级判断 + PM 分析

读取 `agents/analyzer.md`，对每个候选综合判断：

- **值得深挖**：sustained/accelerating 形态 + L2/L3 层
- **观察**：有增长信号但形态不明，或 step 型等后续
- **忽略**：spike+decay + L5 wrapper / 教程 / fork_ratio < 0.02

### 输出结构

```
headline（一句话总结本期最重要的信号）
→ 信号总览（表格：repo / stars / 粗速度 / 形态 / 判断）
→ 值得深挖（3-5 个深度卡片，含增长曲线数据和 PM 洞察）
→ 观察列表（表格，简要说明原因）
→ 本期忽略（折叠，列出原因）
```

报告保存至：`output/signal-watch_{date}.html`

---

## Mode 4: 深度拆解 (Deep Link)

**触发**：用户给出 repo URL 或 owner/repo 名称

### 执行步骤

```bash
# Step 1: 检查额度
python scripts/check_rate_limit.py

# Step 2: 拉取完整数据
python scripts/deep_link.py langchain-ai/langgraph
# 支持 URL 输入: python scripts/deep_link.py https://github.com/langchain-ai/langgraph

# Step 3: 拉取 star 增长曲线（full 模式下）
python scripts/fetch_star_history.py langchain-ai/langgraph

# Step 4: 读取 agents/analyzer.md + references/layer_model.md
#         生成 ecosystem map + Layer 定位 + 范式判断
```

### 输出结构

```
headline（一句有张力的判断，点明核心矛盾或最重要的信号）
→ 基础画像（表格 + spark 趋势图 + commit 分布）
→ Layer 定位（badge + 判断依据 + "为什么不是 X"）
→ 采纳深度（fork 率 / watcher 率 / issue 活跃度 — 区分"围观"和"真用"）
→ Contributor 结构（表格 + PM 解读：bus factor / 团队 vs 独立 / 企业 vs 社区）
→ Release 节奏（timeline 组件 + 产品策略解读，不只是"发了几版"）
→ Issue 构成（表格 + PM 解读。如果分类失效（>50% 未分类），
   必须手动抽样 recent_titles 做定性分析作为 fallback，不能留空白）
→ 核心创新（ASCII 对比图：传统方式 vs 这个项目的方式。
   这是 PM 理解项目价值的最快路径，每份报告必须有。）
→ Ecosystem Map（ASCII 图 + PM 解读）
→ 竞品候选（折叠 details，标注"是否直接竞品"过滤噪声）
→ 范式判断（蓝色段落，结构：
   1. 一句话范式论断
   2. 旧方式 vs 新方式的核心差异
   3. 谁可能受威胁
   4. 谁不受威胁
   注意：不加"与你的关联"，保护隐私）
→ PM 总结（summary-table：成熟度 / 可信度 / 增长性质 / PM 价值 / 风险 / 建议）
```

### 输出风格

- CSS 使用 `--bg/--surface/--border/--accent/--muted` 变量体系，与其他 mode 一致
- PM 洞察用 `.pm-box` 卡片组件（白底 + border），不用内联 `<p>`
- Layer 定位用 `.layer-box` 组件，含 badge + 原因列表 + "为什么不是 X"
- 范式判断用 `.paradigm` 组件（蓝底 + border）
- 竞品候选放 `<details>` 折叠
- 所有技术指标附白话解释（说人话原则）

报告保存至：`output/deep-link_{owner}_{repo}_{date}.html`

---

## Seed List 自定义

编辑 `config/seed_list.json` 添加或移除关注的开发者：

```json
{
  "builders": [
    {"github": "username", "note": "为什么重要"}
  ],
  "last_updated": "2026-02-18"
}
```

当前默认包含 76 个 AI 领域重要 builder/org，覆盖 lab、agent-framework、coding-agent、inference、platform 等 17 个分类。
