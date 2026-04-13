# Naja 认知模块 (Cognition) 技术文档

> **模块路径**: `deva/naja/cognition/`
> **核心定位**: Naja 系统的认知中枢，负责信号处理、注意力评分、主题追踪、叙事分析、跨信号共振检测、流动性传播和 LLM 深度反思
> **设计理念**: 流式学习 + 分层记忆 + 周期性自我反思

---

## 目录

1. [架构总览](#1-架构总览)
2. [模块结构与依赖关系](#2-模块结构与依赖关系)
3. [核心引擎层](#3-核心引擎层)
   - 3.1 [CognitionEngine — 平台级认知入口](#31-cognitionengine--平台级认知入口)
   - 3.2 [NewsMindStrategy — 认知流水线主驱动](#32-newsmindstrategy--认知流水线主驱动)
4. [语义层 (Semantic)](#4-语义层-semantic)
   - 4.1 [NewsEvent — 新闻事件数据结构](#41-newsevent--新闻事件数据结构)
   - 4.2 [AttentionScorer — 六维注意力评分器](#42-attentionscorer--六维注意力评分器)
   - 4.3 [SemanticColdStart — 语义冷启动](#43-semanticcoldstart--语义冷启动)
   - 4.4 [Topic — 主题管理](#44-topic--主题管理)
   - 4.5 [KeywordRegistry — 统一关键词注册表](#45-keywordregistry--统一关键词注册表)
5. [叙事层 (Narrative)](#5-叙事层-narrative)
   - 5.1 [NarrativeTracker — 叙事追踪器](#51-narrativetracker--叙事追踪器)
   - 5.2 [TimingNarrativeTracker — 时机叙事感知](#52-timingnarrativetracker--时机叙事感知)
   - 5.3 [NarrativeSupplyChainLinker — 叙事-供应链联动器](#53-narrativesupplychainlinker--叙事-供应链联动器)
   - 5.4 [BlockMapping — 叙事-题材映射](#54-blockmapping--叙事-题材映射)
6. [分析推理层 (Analysis)](#6-分析推理层-analysis)
   - 6.1 [CrossSignalAnalyzer — 跨信号共振分析器](#61-crosssignalanalyzer--跨信号共振分析器)
   - 6.2 [FirstPrinciplesMind — 第一性原理因果分析](#62-firstprinciplesmind--第一性原理因果分析)
   - 6.3 [SoftInfoConfidence — 软信息置信度评估](#63-softinfoconfidence--软信息置信度评估)
7. [洞察引擎层 (Insight)](#7-洞察引擎层-insight)
   - 7.1 [InsightPool + InsightEngine — 洞察池与洞察引擎](#71-insightpool--insightengine--洞察池与洞察引擎)
   - 7.2 [LLMReflectionEngine — LLM 反思引擎（慢思考）](#72-llmreflectionengine--llm-反思引擎慢思考)
8. [流动性分析层 (Liquidity)](#8-流动性分析层-liquidity)
   - 8.1 [PropagationEngine — 全球流动性传播引擎](#81-propagationengine--全球流动性传播引擎)
   - 8.2 [LiquidityPredictor — 流动性预测器](#82-liquiditypredictor--流动性预测器)
   - 8.3 [MarketNode — 市场节点](#83-marketnode--市场节点)
   - 8.4 [InfluenceEdge — 市场间影响边](#84-influenceedge--市场间影响边)
   - 8.5 [GlobalMarketConfig — 全球市场配置](#85-globalmarketconfig--全球市场配置)
9. [记忆管理 (MemoryManager)](#9-记忆管理-memorymanager)
10. [数据流入口 (Ingestion)](#10-数据流入口-ingestion)
11. [OpenRouter TOKEN 监控](#11-openrouter-token-监控)
12. [数据流全景图](#12-数据流全景图)
13. [配置参数参考](#13-配置参数参考)

---

## 1. 架构总览

认知模块采用 **"天-地-人"三层框架** 设计：

| 层次 | 对应模块 | 核心问题 |
|------|---------|---------|
| **天 (Timing)** | `timing.py` | "现在是不是该动的时候？" — 时机感知与叙事转换检测 |
| **地 (Narrative)** | `tracker.py`, `supply_chain_linker.py`, `block_mapping.py` | "炒什么？" — 题材/叙事追踪与供应链联动 |
| **人 (Cognition)** | `cross_signal_analyzer.py`, `first_principles_mind.py` | "怎么想？" — 共振检测、因果分析、矛盾检测 |
| **慢思考 (Insight)** | `llm_reflection.py` | "更深层的理解" — LLM 定期深度反思 |
| **流动性 (Liquidity)** | `propagation_engine.py`, `liquidity_predictor.py` | "资金怎么流？" — 全球流动性传播网络 |

**核心处理流水线**:

```
原始信号 → 事件转换 → 注意力门控 → 六维评分 → 主题聚类 → 叙事追踪
    → 记忆存储 → 信号生成 → 漂移检测 → 洞察输出 → LLM 反思
```

---

## 2. 模块结构与依赖关系

```
cognition/
├── __init__.py              # 模块入口，统一导出
├── core.py                  # NewsMindStrategy — 认知流水线主驱动
├── engine.py                # CognitionEngine — 平台级认知入口
├── memory_manager.py        # MemoryManager — 三层记忆管理
├── ingestion.py             # CognitionIngestion — Radar→Cognition 数据流桥梁
├── openrouter_monitor.py    # OpenRouter TOKEN 算力监控
│
├── semantic/                # 语义层
│   ├── news_event.py        #   NewsEvent — 新闻事件数据结构
│   ├── attention_scorer.py  #   AttentionScorer — 六维注意力评分器
│   ├── semantic_cold_start.py # SemanticColdStart — 语义冷启动
│   ├── topic_manager.py     #   Topic — 主题管理
│   └── keyword_registry.py  #   KeywordRegistry — 统一关键词注册表
│
├── narrative/               # 叙事层
│   ├── tracker.py           #   NarrativeTracker — 叙事追踪器
│   ├── timing.py            #   TimingNarrativeTracker — 时机叙事感知
│   ├── supply_chain_linker.py # NarrativeSupplyChainLinker — 供应链联动
│   └── block_mapping.py     #   叙事-题材映射配置
│
├── analysis/                # 分析推理层
│   ├── cross_signal_analyzer.py # CrossSignalAnalyzer — 跨信号共振分析
│   ├── first_principles_mind.py # FirstPrinciplesMind — 第一性原理因果分析
│   └── soft_info_confidence.py  # SoftInfoConfidence — 软信息置信度评估
│
├── insight/                 # 洞察引擎层
│   ├── engine.py            #   InsightPool + InsightEngine — 洞察池与引擎
│   ├── llm_reflection.py    #   LLMReflectionEngine — LLM 反思引擎
│   └── weixin_notifier.py   #   WeixinNotifier — 微信通知器
│
└── liquidity/               # 流动性分析层
    ├── propagation_engine.py    # PropagationEngine — 全球流动性传播引擎
    ├── liquidity_predictor.py   # LiquidityPredictor — 流动性预测器
    ├── market_node.py           # MarketNode — 市场节点
    ├── influence_edge.py        # InfluenceEdge — 市场间影响边
    └── global_market_config.py  # GlobalMarketConfig — 全球市场配置
```

**模块间依赖关系**:

```
CognitionEngine (平台入口)
    └── NewsMindStrategy (流水线驱动)
        ├── AttentionScorer (语义层)
        ├── MemoryManager (记忆管理)
        ├── NarrativeTracker (叙事层)
        ├── SemanticColdStart (语义层)
        ├── PropagationEngine (流动性层)
        └── River DBSTREAM/ADWIN (流式学习)

CognitionIngestion (数据流入口)
    ├── InsightPool (洞察层)
    ├── NajaEventBus (事件总线)
    └── LiquidityCognition (流动性层)

CrossSignalAnalyzer (分析层)
    ├── NarrativeBlockMapping (叙事层)
    ├── NajaEventBus (事件总线)
    └── InsightPool (洞察层)

LLMReflectionEngine (洞察层)
    ├── CognitionEngine (核心引擎)
    ├── NarrativeTracker (叙事层)
    ├── RiskManager (风险模块)
    ├── LiquidityCognition (流动性层)
    └── WisdomRetriever (知识模块)
```

---

## 3. 核心引擎层

### 3.1 CognitionEngine — 平台级认知入口

**文件**: `engine.py`

**设计模式**: 组合模式（持有 `NewsMindStrategy` 实例，而非继承）

**职责**: 作为平台级的认知输入输出入口，隔离策略细节，提供简洁的公共 API。

#### 核心方法

| 方法 | 功能 |
|------|------|
| `ingest_result(result)` | 摄入策略结果到认知系统，自动提取时间戳、策略名、输出数据，高置信度(≥0.8)或买卖信号自动标记为高重要性 |
| `process_record(record)` | 委托给内部 `NewsMindStrategy` 处理记录 |
| `summarize_for_llm(max_topics, max_events)` | 返回紧凑的认知摘要，用于 LLM prompts（含统计、热门主题、高注意力事件） |
| `get_memory_report()` | 获取完整记忆报告 |
| `save_state()` / `load_state()` | 认知状态持久化 |
| `get_liquidity_stats()` | 获取流动性预测统计（供 UI 层使用） |
| `get_liquidity_predictions()` | 获取活跃的流动性预测列表 |

#### 自动保存机制

- 启动时自动加载已保存的认知状态
- 后台线程定期保存（默认间隔 300 秒）
- 可通过 `stop_auto_save()` 停止

#### 使用示例

```python
from deva.naja.cognition import CognitionEngine

engine = CognitionEngine(config={"auto_save_interval": 600})

# 摄入策略结果
engine.ingest_result(strategy_result)

# 获取 LLM 摘要
summary = engine.summarize_for_llm(max_topics=5, max_events=5)

# 获取流动性预测
predictions = engine.get_liquidity_predictions()
```

---

### 3.2 NewsMindStrategy — 认知流水线主驱动

**文件**: `core.py`

**核心定位**: 认知系统的"心脏"，驱动完整的认知流水线。

**日志标签**: `[NewsMind]`

#### 初始化组件

| 组件 | 说明 |
|------|------|
| `AttentionScorer` | 六维注意力评分器 |
| `MemoryManager` | 三层记忆管理器 |
| `NarrativeTracker` | 叙事追踪器 |
| `River DBSTREAM` | 在线流式聚类（主题发现） |
| `River ADWIN` | 漂移检测器（叙事变化检测） |
| `SemanticColdStart` | 语义冷启动模块 |
| `PropagationEngine` | 全球流动性传播引擎 |

#### 核心处理流水线

```
process_record(record)
    │
    ├─ 1. 事件转换: record → NewsEvent
    │     └─ from_datasource_record() 自动识别类型（tick/news/log/file/text/array）
    │
    ├─ 2. 频率+重要性门控: _should_ingest_event(event)
    │     └─ 价值驱动豁免：高重要性/新话题/重大关键词/新数据源类型 → 直接放行
    │
    ├─ 3. 注意力评分: attention_scorer.score(event)
    │     └─ 六维加权评分（见 4.2 节）
    │
    ├─ 4. 主题分配: _assign_topic(event)
    │     └─ River DBSTREAM 聚类 或 余弦相似度匹配
    │
    ├─ 5. 叙事追踪: _process_narratives(event)
    │     └─ NarrativeTracker.ingest_event(event)
    │
    ├─ 6. 记忆存储
    │     ├─ 短期记忆: memory.append_short(event)
    │     └─ 中期归档: memory.archive_to_mid(event) (注意力 ≥ 动态阈值)
    │
    ├─ 7. 信号生成: _generate_signals_for_event(event, topic_id)
    │     └─ 高注意力信号 / 新主题信号 / 主题增长信号
    │
    └─ 8. 漂移检测: _check_drift(event)
          └─ River ADWIN 检测叙事漂移
```

#### 关键方法说明

**`_should_ingest_event(event)`** — 频率+重要性门控

- 基于滑动窗口的频率控制（默认 300 秒窗口，目标 30 条/分钟）
- **价值驱动豁免**：以下情况直接放行
  - 事件重要性 ≥ 0.7
  - 前 3 条新主题事件
  - 匹配重大关键词
  - 新数据源类型的首批事件

**`_simple_embedding(text, source, event_type)`** — 简化版语义编码

不依赖外部 embedding 模型，使用组合特征：
- 数据源 one-hot（10 维）
- 事件类型（3 维）
- 关键词特征
- 文本统计特征

**`process_batch(records)`** — 批量处理

- 支持去重（基于内容哈希）
- 预筛选低注意力事件
- 批量聚类优化

#### 配置参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `short_term_size` | 1000 | 短期记忆容量 |
| `topic_threshold` | 0.5 | 主题聚类阈值 |
| `attention_threshold` | 0.6 | 注意力过滤阈值 |
| `max_topics` | 50 | 最大主题数 |
| `attention_gate_base` | 0.35 | 注意力门控基础值 |
| `target_rate_per_min` | 30 | 目标处理速率 |
| `rate_window_seconds` | 300 | 频率控制窗口 |
| `max_batch_keep` | 80 | 批量处理最大保留数 |

---

## 4. 语义层 (Semantic)

### 4.1 NewsEvent — 新闻事件数据结构

**文件**: `semantic/news_event.py`

**核心数据结构**:

```python
class NewsEvent:
    id: str              # 唯一标识
    timestamp: float     # 时间戳
    source: str          # 数据源名称
    event_type: str      # 事件类型
    content: str         # 事件内容
    vector: list         # 语义向量
    meta: dict           # 元数据
    attention_score: float = 0.0  # 注意力分数
    topic_id: int = -1   # 所属主题 ID
```

**数据源类型自动识别** (`from_datasource_record`):

| 数据源前缀/类型 | 识别结果 |
|-----------------|---------|
| `tick_`, `realtime_`, `行情` | `tick` |
| `news_`, `新闻`, `快讯` | `news` |
| `log_`, `日志` | `log` |
| `file_`, `文件` | `file` |
| `text_`, `文本` | `text` |
| 含 `array` 或列表数据 | `array` |
| 其他 | `unknown` |

### 4.2 AttentionScorer — 六维注意力评分器

**文件**: `semantic/attention_scorer.py`

**评分维度与权重**:

| 维度 | 权重 | 说明 |
|------|------|------|
| **Novelty（新颖度）** | 0.20 | 基于与历史事件的余弦相似度，越新颖分数越高 |
| **Sentiment（情绪强度）** | 0.12 | 基于强烈词汇检测（暴涨、暴跌、突破等） |
| **Market（市场波动）** | 0.20 | 基于涨跌幅，极端波动得高分 |
| **Keywords（关键词）** | 0.15 | 高/中等级别关键词匹配 |
| **Velocity（传播速度）** | 0.13 | 1 小时内同类事件频率 |
| **Importance（重要性）** | 0.20 | 数据源标记的重要性评分 |

**核心方法**:

- `score(event)` → `float`: 完整评分（写入历史记录）
- `peek_score(event)` → `float`: 预评分（不写入历史，用于筛选）

### 4.3 SemanticColdStart — 语义冷启动

**文件**: `semantic/semantic_cold_start.py`

**功能**: 使用种子词构建初始语义图谱，解决冷启动问题。

**工作流程**:
1. 定义种子词（如 "AI", "芯片", "新能源"）
2. 构建 LLM prompt，请求生成语义关联图谱
3. 解析 LLM 输出，构建 `SemanticNode` 和 `SemanticEdge`
4. 节点权重 = 0.6 × 历史相关性 + 0.4 × 置信度

**数据结构**:
- `SemanticNode`: term, level, relation, confidence, weight, decay_lambda
- `SemanticEdge`: src, dst, relation, weight

### 4.4 Topic — 主题管理

**文件**: `semantic/topic_manager.py`

**核心数据结构**:

```python
class Topic:
    center: list          # 聚类中心向量
    events: deque         # 事件队列
    attention_sum: float  # 注意力总和
    event_count: int      # 事件计数
    name: str             # 主题名称（自动提取）
    keywords: list        # 关键词列表
```

**自动命名**: 根据事件内容自动提取主题名称（数据源前缀 + 关键词/内容提取）

**关键属性**:
- `avg_attention`: 平均注意力分数
- `growth_rate`: 增长率（最近 1 小时 vs 之前）

### 4.5 KeywordRegistry — 统一关键词注册表

**文件**: `semantic/keyword_registry.py`

**管理的关键词类别**:

| 类别 | 变量名 | 用途 |
|------|--------|------|
| 叙事主题关键词 | `DEFAULT_NARRATIVE_KEYWORDS` | AI、芯片、新能源、医药、华为、中美关系、地缘政治等 |
| 供需动态关键词 | `DYNAMICS_KEYWORDS` | token供需、电力供需、技术瓶颈、效率突破、AI落地 |
| 市场情绪关键词 | `SENTIMENT_KEYWORDS` | 行情涨跌、市场情绪、舆论热点 |
| 市场叙事关键词 | `MARKET_NARRATIVE_KEYWORDS` | 政策、业绩、流动性、情绪 |
| 新闻主题关键词 | `NEWS_TOPIC_KEYWORDS` | 新闻聚类，含优先级和分类标签 |

---

## 5. 叙事层 (Narrative)

### 5.1 NarrativeTracker — 叙事追踪器

**文件**: `narrative/tracker.py`

**核心定位**: 双通道架构 — 外部叙事 + 供需动态

**双通道设计**:

| 通道 | 数据结构 | 功能 |
|------|---------|------|
| 外部叙事 | `NarrativeState` | 追踪外部公共叙事热点（AI、芯片、地缘政治等） |
| 供需动态 | `ValueSignal` | 检测供需失衡信号（token供需、电力供需等） |

**核心方法**:

| 方法 | 功能 |
|------|------|
| `ingest_event(event)` | 事件处理入口，双重处理：外部叙事 + 供需动态 |
| `ingest_news_signal(signal)` | 处理 TextFocusedEvent 的叙事信号 |
| `get_world_narrative()` | 获取外部公共叙事热点（归一化热度分数） |
| `get_value_market_summary()` | 获取供需动态价值评分 |
| `get_liquidity_structure()` | 获取美林时钟四象限流动性结构 |
| `get_graph(min_weight)` | 获取叙事关系图（节点 + 边） |
| `get_linked_blocks(narrative)` | 获取叙事关联的题材列表 |

**NarrativeState 数据结构**:

```python
class NarrativeState:
    name: str               # 叙事名称
    stage: str              # 阶段（emerging/building/peak/fading）
    attention_score: float  # 注意力分数
    total_count: int        # 总事件数
    recent_count: int       # 近期事件数
    trend: str              # 趋势方向
    hits: deque             # 命中记录队列
```

### 5.2 TimingNarrativeTracker — 时机叙事感知

**文件**: `narrative/timing.py`

**核心定位**: "天"层 — 回答"现在是不是该动的时候"

**叙事类型 (TimingType)**:

| 类型 | 说明 |
|------|------|
| `POLICY` | 政策叙事（央行政策、监管变化） |
| `EARNINGS` | 业绩叙事（财报季、业绩预告） |
| `LIQUIDITY` | 流动性叙事（资金面、利率变化） |
| `SENTIMENT` | 情绪叙事（市场情绪、恐慌/贪婪） |
| `BLOCK` | 题材叙事（行业热点、概念炒作） |
| `GLOBAL` | 全球叙事（国际事件、地缘政治） |

**叙事阶段 (TimingStage)**:

```
EMERGING → BUILDING → PEAK → FADING → DEAD
 新兴       发展       高潮    衰退     消亡
```

**核心能力**:

| 能力 | 方法 | 说明 |
|------|------|------|
| 叙事追踪 | `track(market_data, news_signals, flow_data)` | 检测当前活跃叙事 |
| 转换感知 | `sense_transition(current_narratives, ...)` | 感知叙事转换（高潮期预警） |
| 冲突检测 | `detect_conflict(narratives)` | 检测叙事冲突（政策 vs 业绩、流动性 vs 情绪） |
| 综合感知 | `sense(market_data, news_signals, flow_data)` | 整合追踪+转换+冲突 |

### 5.3 NarrativeSupplyChainLinker — 叙事-供应链联动器

**文件**: `narrative/supply_chain_linker.py`

**功能**: 将叙事主题与供应链公司关联，分析新闻对供应链的影响。

**核心方法**:

| 方法 | 功能 |
|------|------|
| `get_stocks_by_narrative(narrative)` | 获取叙事关联的股票列表 |
| `analyze_news_impact(news_text, news_narratives)` | 分析新闻对供应链的影响 |
| `on_stock_risk_event(stock_code, event_description)` | 处理股票风险事件 |
| `get_related_stocks_with_weight(narrative)` | 获取关联股票及权重（考虑重要性和风险因子） |

**风险等级 (RiskLevel)**: `LOW` → `MEDIUM` → `HIGH` → `CRITICAL`

### 5.4 BlockMapping — 叙事-题材映射

**文件**: `narrative/block_mapping.py`

**功能**: 纯配置模块，定义叙事主题与题材/市场指数的映射关系。

**映射关系示例**:

| 叙事主题 | 关联题材 | 关联市场 |
|---------|---------|---------|
| AI | 半导体、软件、互联网 | 纳斯达克 |
| 芯片 | 半导体、集成电路 | — |
| 新能源 | 电力设备、光伏、储能 | — |
| 地缘政治 | 军工、黄金 | — |

---

## 6. 分析推理层 (Analysis)

### 6.1 CrossSignalAnalyzer — 跨信号共振分析器

**文件**: `analysis/cross_signal_analyzer.py`

**核心定位**: "人"层 — 检测新闻、注意力、市场之间的共振信号。

**三层分析架构**:

| 层级 | 方法 | 说明 |
|------|------|------|
| **Layer 1: 规则引擎** | `_check_immediate_resonance(news)` | 实时共振检测，基于规则加权评分 |
| **Layer 2: 统计分析** | `analyze_statistical_correlation(block_id)` | numpy corrcoef 统计相关性 |
| **Layer 3: LLM 分析** | `should_trigger_llm(resonance)` | 冷却期+阈值+信号数量判断是否触发 LLM |

**共振评分公式 (Layer 1)**:

```
resonance_score = 新闻相关性×0.3 + 注意力权重×0.4 + 新闻密度×0.1 + 情感强度×0.2
```

**共振类型 (ResonanceType)**:

| 类型 | 说明 |
|------|------|
| `TEMPORAL` | 时间共振（多信号同时出现） |
| `INTENSITY` | 强度共振（信号强度叠加） |
| `NARRATIVE` | 叙事共振（新闻与叙事主题一致） |
| `CORRELATION` | 统计相关（历史数据相关） |

**核心方法**:

| 方法 | 功能 |
|------|------|
| `ingest_news(news_signal)` | 接收新闻信号，立即检查共振 |
| `ingest_attention(snapshot)` | 接收注意力快照，检查待处理共振 |
| `ingest_market_snapshot(snapshot)` | 接收市场快照，检测宏观叙事共振 |
| `get_narrative_augmented_attention(base_attention)` | 融合叙事信号的题材注意力（叙事增强权重 30%） |
| `create_feedback(resonance, insight_text)` | 创建认知反馈（注意力调整 + 雷达调整） |

### 6.2 FirstPrinciplesMind — 第一性原理因果分析

**文件**: `analysis/first_principles_mind.py`

**核心组件**:

| 组件 | 功能 |
|------|------|
| `MarketCausalityGraph` | 市场因果图谱（添加因果边、寻找路径、找根本原因） |
| `CausalityTracker` | 因果关系追踪器 |
| `ContradictionDetector` | 矛盾检测器（语义/逻辑/数据层面） |
| `ReasoningEngine` | 推理引擎（演绎/归纳/类比/反事实） |

**推理方法 (ReasoningType)**:

| 方法 | 说明 |
|------|------|
| `deductive` | 演绎推理（从一般到特殊） |
| `inductive` | 归纳推理（从特殊到一般） |
| `analogical` | 类比推理（从已知到未知） |
| `counterfactual` | 反事实推理（"如果...会怎样"） |

**思考层次 (ThoughtLevel)**:

```
SURFACE → PATTERN → CAUSAL → FIRST_PRINCIPLES → META
 表面      模式      因果       第一性原理         元认知
```

### 6.3 SoftInfoConfidence — 软信息置信度评估

**文件**: `analysis/soft_info_confidence.py`

**设计原则**: 硬数据 = 主角（权重 70%），软信息 = 调味剂（权重 = 置信度 × 30%）

**核心公式**:

```
final_score = hard_signal × hard_weight + Σ(soft_signal_i × soft_weight_i)
```

**置信度评估维度**:

| 评估类型 | 公式 |
|---------|------|
| 叙事置信度 | 来源可靠性×0.4 + 数量×0.3 + 稳定性×0.3 |
| 情绪置信度 | 情绪强度 × 来源可靠性 |
| 跨信号置信度 | 共振数量 × 题材数量 × 来源可靠性 |

**矛盾检测**: 当硬数据与软信息方向不一致时触发告警。

---

## 7. 洞察引擎层 (Insight)

### 7.1 InsightPool + InsightEngine — 洞察池与洞察引擎

**文件**: `insight/engine.py`

**核心组件**:

| 组件 | 功能 |
|------|------|
| `InsightBuilder` | 从策略结果或热点事件构建洞察候选 |
| `InsightPool` | 洞察池管理（去重、合并、排序） |
| `UserAttentionRanker` | 用户关注度评分 |
| `InsightEngine` | 洞察引擎（注意力提示生成） |

**Insight 数据结构**:

```python
class Insight:
    id: str                # 唯一标识
    ts: float              # 时间戳
    theme: str             # 主题
    summary: str           # 摘要
    symbols: list          # 相关股票
    blocks: list           # 相关题材
    system_attention: float  # 系统注意力
    confidence: float      # 置信度
    actionability: float   # 可执行性
    novelty: float         # 新颖度
    user_score: float      # 用户关注度评分
    source: str            # 来源
    signal_type: str       # 信号类型
```

**用户关注度评分公式**:

```
user_score = 系统注意力×0.4 + 置信度×0.2 + 可执行性×0.2 + 新颖度×0.2
```

**洞察合并策略**: 同主题在时间窗口内的洞察会合并，取最大分数。

### 7.2 LLMReflectionEngine — LLM 反思引擎（慢思考）

**文件**: `insight/llm_reflection.py`

**核心定位**: 定期调用 LLM（DeepSeek 等）进行深度反思，模拟人类的"慢思考"。

**信号收集来源（11 个）**:

| # | 来源 | 说明 |
|---|------|------|
| 1 | 叙事追踪 | NarrativeTracker |
| 2 | 天道民心 | 市场情绪 |
| 3 | 市场分析 | 市场状态 |
| 4 | 波动率 | VolatilitySurface |
| 5 | 风险管理 | RiskManager |
| 6 | 流动性预测 | LiquidityCognition |
| 7 | 第一性原理 | FirstPrinciplesMind |
| 8 | 注意力 | AttentionOS |
| 9 | 共振分析 | CrossSignalAnalyzer |
| 10 | AI 算力 | OpenRouter TOKEN 趋势 |
| 11 | 交易反馈 | 交易结果反馈 |

**反思输出推送渠道**:
- 钉钉 (Dtalk)
- 微信 (WeixinNotifier)

**Reflection 数据结构**:

```python
class Reflection:
    theme: str               # 反思主题
    summary: str             # 反思摘要
    signals_count: int       # 参考信号数
    narratives: list         # 相关叙事
    symbols: list            # 相关股票
    blocks: list             # 相关题材
    confidence: float        # 置信度
    actionability: float     # 可执行性
    novelty: float           # 新颖度
    liquidity_structure: dict # 流动性结构
```

---

## 8. 流动性分析层 (Liquidity)

### 8.1 PropagationEngine — 全球流动性传播引擎

**文件**: `liquidity/propagation_engine.py`

**功能**: 模拟全球市场间的流动性传播，当一个市场发生变化时，预测并验证对其他市场的影响。

**核心工作流**:

```
市场 A 发生变化
    → update_market(A, price, volume)
    → _propagate_change(A, state)
    → 遍历 A 的影响边
    → 每条边发起传播 (InfluenceEdge.propagate)
    → 目标市场 B 接收传播信号
    → 实际变化到达时 verify_propagation(B, actual)
    → 成功 → 增强边权重；失败 → 衰减边权重
```

**核心方法**:

| 方法 | 功能 |
|------|------|
| `initialize()` | 初始化引擎，创建所有市场节点和影响边 |
| `update_market(market_id, price, volume, ...)` | 更新市场状态并触发传播 |
| `get_liquidity_structure()` | 获取当前流动性结构（所有市场状态 + 边状态） |
| `get_resonance_signals()` | 获取共振信号 |
| `decay_all_attention(rate)` | 衰减所有市场注意力 |

### 8.2 LiquidityPredictor — 流动性预测器

**文件**: `liquidity/liquidity_predictor.py`

**功能**: 基于源市场信号预测对目标市场的流动性影响。

**核心方法**:

| 方法 | 功能 |
|------|------|
| `predict_liquidity(source_market, signals, breadth_fear)` | 预测流动性影响（信号计算 → 传染概率折扣 → 定价检测 → 调整指令） |
| `verify_liquidity(target_market, actual_data)` | 验证预测（5 次验证后判断，偏差 > 0.25 则解除限制） |
| `detect_resonance(market_signal, narrative_signal, breadth_fear)` | 检测行情-舆论信号共振 |
| `predict_topic_spread(topic, us_block_change)` | 预测主题跨市场扩散 |

**流动性信号类型**:

| 类型 | 说明 |
|------|------|
| `CHINA_A` | A 股 |
| `HONG_KONG` | 港股 |
| `US` | 美股 |
| `FUTURES` | 期货 |
| `CRYPTO` | 加密货币 |

**主题-板块映射 (TOPIC_SECTOR_MAPPING)**:

| 主题 | 美股板块 | A 股板块 |
|------|---------|---------|
| 芯片 | Semiconductors | 半导体、集成电路 |
| AI | AI/ML | 人工智能、软件 |
| 新能源 | Clean Energy | 电力设备、光伏 |
| 电动车 | EV | 汽车、锂电池 |
| 云计算 | Cloud Computing | 云计算、数据中心 |

### 8.3 MarketNode — 市场节点

**文件**: `liquidity/market_node.py`

**功能**: 表示单个市场的状态，计算涨跌幅、波动率、量比、注意力分数。

**注意力级别**:

| 级别 | 阈值 | 说明 |
|------|------|------|
| `critical` | ≥ 0.8 | 极端波动 |
| `high` | ≥ 0.6 | 显著变化 |
| `medium` | ≥ 0.4 | 中等变化 |
| `low` | ≥ 0.2 | 轻微变化 |
| `dormant` | < 0.2 | 休眠状态 |

### 8.4 InfluenceEdge — 市场间影响边

**文件**: `liquidity/influence_edge.py`

**功能**: 表示两个市场之间的影响关系，支持传播发起、验证和权重自适应调整。

**核心机制**:
- 传播成功 → 增强权重（`_boost_weight`）
- 传播失败 → 衰减权重（`_decay_weight`）
- 自然衰减 → 随时间缓慢降低（`natural_decay`）
- 传播概率 = weight × confidence

### 8.5 GlobalMarketConfig — 全球市场配置

**文件**: `liquidity/global_market_config.py`

**覆盖市场（20+）**: 美股、标普、纳斯达克、道琼斯、A 股、沪深 300、港股、日经、欧股、黄金、白银、原油、天然气、铜、美元指数、欧元美元、美元人民币、比特币、以太坊、VIX、美债 10 年、中债

**影响路径 (INFLUENCE_PATHS)**: 18 条市场间影响路径，含延迟时间和强度。

---

## 9. 记忆管理 (MemoryManager)

**文件**: `memory_manager.py`

**三层记忆架构**:

| 层级 | 数据结构 | 容量 | 半衰期 | 用途 |
|------|---------|------|--------|------|
| **短期记忆** | `deque` | 1000 | 300 秒 (5 分钟) | 最近事件流，快速访问 |
| **中期记忆** | `deque` | 5000 | 3600 秒 (1 小时) | 高注意力事件归档 |
| **长期记忆** | `list` | 30 条 | 24 小时间隔 | 周期性总结 |

**记忆衰减机制**:

```
freshness = exp(-dt / half_life)
attention_score *= freshness × shield_multiplier
```

**强化保护**:
- 被强化的事件在 `reinforcement_shield`（默认 60 秒）内衰减减半
- 60-180 秒内衰减率 75%
- 超过 180 秒恢复正常衰减

**动态中期记忆阈值**:

| 市场活跃度 | 阈值调整 | 效果 |
|-----------|---------|------|
| > 0.6（活跃） | base + 0.15（最高 0.85） | 提高门槛，减少噪音 |
| < 0.3（平淡） | base - 0.2（最低 0.5） | 降低门槛，保留更多信号 |
| 其他 | base（默认 0.7） | 正常模式 |

**长期记忆归档**:
- 每 24 小时生成一次总结
- 包含：总事件数、平均注意力、Top 5 主题、事件类型分布、来源分布
- 最多保留 30 条总结

---

## 10. 数据流入口 (Ingestion)

**文件**: `ingestion.py`

**核心定位**: Radar → Cognition 统一数据流桥梁，消除 Radar 层与 Cognition 子模块的直接耦合。

**数据流路径**:

```
RadarEngine
    ↓ ingest_radar_events()
CognitionIngestion
    ├→ InsightPool.ingest_hotspot_event()      (雷达信号 → 洞察池)
    ├→ NajaEventBus.publish()                   (全球市场事件 → 总线)
    └→ LiquidityCognition.ingest()              (降级路径)
```

**核心方法**:

| 方法 | 功能 |
|------|------|
| `ingest_radar_events(events)` | 接收雷达事件列表，分发到 InsightPool |
| `ingest_market_alert(event)` | 接收全球市场事件，发布到 NajaEventBus |
| `ingest_news(news_data)` | 预留的新闻事件接口 |

---

## 11. OpenRouter TOKEN 监控

**文件**: `openrouter_monitor.py`

**功能**: 监控全球 AI 算力（OpenRouter TOKEN）消耗趋势，作为认知系统的宏观信号输入。

**工作流程**:

```
每周一 09:00 (cron)
    → fetch_weekly_data()       # 获取 OpenRouter 排行榜数据
    → analyze_trend()           # 分析趋势（上涨/下跌/加速/减速/异常）
    → save_trend_data()         # 保存到 NB 表
    → send_to_radar()           # 异常时发送雷达事件
```

**趋势分析维度**:

| 维度 | 说明 |
|------|------|
| `direction` | strong_up / up / down / strong_down / unknown |
| `strength` | 趋势强度 (0-1) |
| `acceleration` | 加速度（近 8 周平均 vs 前 8 周） |
| `is_anomaly` | 异常检测（骤降、趋势反转、波动异常） |
| `alert_level` | normal / attention / warning / critical |

**异常类型**:

| 类型 | 触发条件 |
|------|---------|
| `sudden_drop` | 最近周环比 < -20% 且 3 周均值 < -10% |
| `uptrend_reversal` | 上涨趋势中最近周环比 < -5% |
| `volatility_spike` | 近 4 周方差 > 前 4 周方差 × 3 |

**关联标的**: NVDA, AMD, TSLA, 台积电, SMCI

---

## 12. 数据流全景图

```
┌─────────────────────────────────────────────────────────────────────┐
│                        外部数据源                                    │
│  (Tick行情 / 新闻快讯 / 文本数据 / 全球市场API / OpenRouter)          │
└──────────┬──────────┬──────────┬──────────┬────────────────────────┘
           │          │          │          │
           ▼          ▼          ▼          ▼
     ┌──────────┐ ┌────────┐ ┌────────┐ ┌──────────────┐
     │  Radar   │ │  Text  │ │Strategy│ │ OpenRouter   │
     │  Engine  │ │  Pipeline│ │Results │ │  Monitor     │
     └────┬─────┘ └───┬────┘ └───┬────┘ └──────┬───────┘
          │           │          │              │
          ▼           ▼          ▼              │
     ┌──────────────────────────────────┐       │
     │     CognitionIngestion           │       │
     │  (统一数据流入口)                  │       │
     └──────────┬───────────────────────┘       │
                │                               │
                ▼                               │
     ┌──────────────────────────────────┐       │
     │     CognitionEngine              │       │
     │  (平台级认知入口)                  │       │
     └──────────┬───────────────────────┘       │
                │                               │
                ▼                               │
     ┌──────────────────────────────────┐       │
     │   NewsMindStrategy               │◄──────┘
     │   (认知流水线主驱动)               │
     │                                  │
     │  1. 事件转换 (NewsEvent)          │
     │  2. 频率门控                      │
     │  3. 注意力评分 (6维)              │
     │  4. 主题聚类 (River DBSTREAM)     │
     │  5. 叙事追踪                      │
     │  6. 记忆存储 (三层)               │
     │  7. 信号生成                      │
     │  8. 漂移检测 (ADWIN)              │
     └──┬──────┬──────┬──────┬──────────┘
        │      │      │      │
        ▼      ▼      ▼      ▼
   ┌────────┐┌──────┐┌─────┐┌──────────────┐
   │Memory  ││Narr- ││Ins- ││Propagation  │
   │Manager ││ative ││ight ││Engine        │
   │(三层)  ││Track-││Pool ││(流动性传播)   │
   │        ││er    ││     ││              │
   └────────┘└──┬───┘└──┬──┘└──────────────┘
                │      │
                ▼      ▼
     ┌─────────────────────────────┐
     │  CrossSignalAnalyzer        │
     │  (跨信号共振分析)            │
     │  Layer1: 规则引擎            │
     │  Layer2: 统计分析            │
     │  Layer3: LLM 分析           │
     └──────────┬──────────────────┘
                │
                ▼
     ┌─────────────────────────────┐
     │  LLMReflectionEngine        │
     │  (慢思考 / 深度反思)         │
     │  → 钉钉 / 微信推送          │
     └─────────────────────────────┘
```

---

## 13. 配置参数参考

### NewsMindStrategy 配置

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `short_term_size` | 1000 | 短期记忆容量 |
| `topic_threshold` | 0.5 | 主题聚类阈值 |
| `attention_threshold` | 0.6 | 注意力过滤阈值 |
| `max_topics` | 50 | 最大主题数 |
| `attention_filter_enabled` | true | 是否启用注意力过滤 |
| `attention_gate_base` | 0.35 | 注意力门控基础值 |
| `target_rate_per_min` | 30 | 目标处理速率（条/分钟） |
| `rate_window_seconds` | 300 | 频率控制窗口（秒） |
| `max_batch_keep` | 80 | 批量处理最大保留数 |
| `fading_factor` | 0.05 | River 聚类衰减因子 |
| `cleanup_interval` | 10 | River 聚类清理间隔 |

### MemoryManager 配置

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `short_term_half_life` | 300.0 | 短期记忆半衰期（秒） |
| `mid_term_half_life` | 3600.0 | 中期记忆半衰期（秒） |
| `topic_half_life` | 1800.0 | 主题半衰期（秒） |
| `mid_memory_threshold` | 0.7 | 中期记忆归档阈值 |
| `long_memory_interval` | 24 | 长期记忆归档间隔（小时） |
| `reinforcement_shield` | 60.0 | 强化保护时间（秒） |

### CognitionEngine 配置

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `auto_save_enabled` | true | 是否启用自动保存 |
| `auto_save_interval` | 300 | 自动保存间隔（秒） |
| `auto_load_on_start` | true | 启动时是否自动加载 |

---

> **文档生成时间**: 2026-04-13
> **基于代码版本**: SOStc/deva (GitHub main branch)
