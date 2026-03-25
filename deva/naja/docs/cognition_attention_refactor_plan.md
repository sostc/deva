# Cognition-Attention-Radar 重构计划

## 目标

修正 Cognition、Attention、Radar 三个模块的功能错位，实现：
1. **叙事主题 → 板块联动**：NarrativeTracker 调用 Radar/Attention 的板块数据
2. **漂移检测职责分离**：Cognition 负责话题漂移，Attention 负责市场状态漂移，Radar 负责感知层漂移
3. **信号命名规范化**：Cognition 信号以 `narrative_`/`topic_` 为前缀，Attention 信号以 `market_`/`anomaly_` 为前缀，Radar 信号以 `radar_` 为前缀
4. **Radar 定位明确化**：作为统一感知层，不做物理合并

---

## 零、Radar 职责明确化 (Phase 0)

### 0.1 问题分析

**当前状态：**
- `Radar` 模块包含 MarketScanner、NewsFetcher、TradingClock、RadarNewsProcessor 等
- Drift 检测在 Radar、Cognition、Attention 三处重复
- 模块边界模糊，缺乏明确定位

**目标状态：**
- Radar 作为**统一感知层**，负责原始信号检测
- Cognition 作为**认知层**，负责语义理解和叙事追踪
- Attention 作为**调度层**，负责资源分配和频率控制
- 职责分明，单一数据流清晰

### 0.2 三层架构

```
┌─────────────────────────────────────────────────────────┐
│                    Radar (感知层)                          │
│  - MarketScanner: 统计异常、模式识别                       │
│  - NewsFetcher: 新闻获取                                   │
│  - TradingClock: 交易时间判断 (独立保留)                   │
│  - RadarEngine: 事件分发                                   │
│                                                          │
│  Radar Signal 前缀: radar_                                │
│  radar_pattern, radar_anomaly, radar_sector_anomaly      │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│                  Cognition (认知层)                       │
│  - NewsMindStrategy: 话题聚类、三层记忆                    │
│  - NarrativeTracker: 叙事追踪、主题生命周期               │
│  - InsightEngine: 洞察生成                                │
│                                                          │
│  Cognition Signal 前缀: topic_ / narrative_             │
│  topic_emerge, topic_grow, narrative_stage_change        │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│                  Attention (调度层)                       │
│  - GlobalAttentionEngine: 市场活跃度                      │
│  - SectorAttentionEngine: 板块注意力                     │
│  - WeightPool: 个股权重                                   │
│  - FrequencyScheduler: 频率调度                           │
│                                                          │
│  Attention Signal 前缀: market_ / anomaly_              │
│  market_regime_drift, anomaly_pattern, anomaly_volume    │
└─────────────────────────────────────────────────────────┘
```

### 0.3 Drift 检测职责分工

| 模块 | 漂移类型 | 检测目标 | 输出信号 |
|------|----------|----------|----------|
| Radar | PerceptionDrift | 感知数据分布变化 (统计层面) | `radar_data_distribution_shift` |
| Cognition | NarrativeDrift | 话题关键词频率变化、叙事阶段转变 | `narrative_drift` |
| Attention | MarketRegimeDrift | 价格分布、波动率、市场状态 | `market_regime_drift` |

### 0.4 修改文件清单

| 文件 | 修改内容 |
|------|----------|
| `radar/engine.py` | 注释中明确 Radar 是"统一感知层"， Drift 信号添加 `radar_` 前缀 |
| `radar/market_scanner.py` | 添加雷达层职责注释，漂移检测重命名 |

### 0.5 实施步骤

1. **Step 1**: 更新 `radar/engine.py` 顶部注释，明确 Radar 是感知层
2. **Step 2**: 在 `MarketScanner` 中添加 `radar_drift_detector` 标识
3. **Step 3**: Radar 的漂移信号重命名为 `radar_data_distribution_shift`
4. **Step 4**: 更新 `radar/market_scanner.py` 的 signal 类型

---

## 一、叙事主题映射到板块

### 1.1 问题分析

**当前状态：**
- `NarrativeTracker` 使用硬编码的关键词列表 `DEFAULT_NARRATIVE_KEYWORDS` 来识别叙事主题
- `SectorAttentionEngine` 基于市场数据计算板块注意力
- 两者完全独立，没有联动机制

**目标状态：**
- NarrativeTracker 识别叙事主题后，映射到实际的板块（sector_id）
- 叙事主题的活跃度可以影响对应板块的注意力权重
- 实现"舆情 → 板块轮动"的联动

### 1.2 关键词 → 板块映射表

在 `cognition/` 下新增映射配置：

```python
# narrative_sector_mapping.py

NARRATIVE_TO_SECTOR_MAP = {
    "AI": {
        "sector_id": "semiconductor",
        "keywords": ["AI", "大模型", "ChatGPT", ...],
    },
    "芯片": {
        "sector_id": "semiconductor",
        "keywords": ["芯片", "半导体", "GPU", ...],
    },
    "新能源": {
        "sector_id": "new_energy",
        "keywords": ["新能源", "光伏", "锂电", ...],
    },
}

NARRATIVE_TO_SECTOR_LINK = {
    "AI": ["semiconductor", "software"],
    "芯片": ["semiconductor"],
    "新能源": ["new_energy", "auto"],
    "华为": ["semiconductor", "consumer_electronics"],
}
```

### 1.3 修改文件清单

| 文件 | 修改内容 |
|------|----------|
| `cognition/narrative_tracker.py` | 新增 `_sector_link` 引用，新增 `get_linked_sectors()` 方法 |
| `cognition/core.py` (NewsMindStrategy) | 在 `process_record` 后将叙事主题映射到板块 |
| `cognition/cross_signal_analyzer.py` | 新增 `NarrativeSectorMapper` 类，处理映射逻辑 |
| 新增 `cognition/narrative_sector_mapping.py` | 主题到板块的映射配置 |

### 1.4 实施步骤

1. **Step 1**: 创建 `narrative_sector_mapping.py` 定义映射表
2. **Step 2**: 在 `NarrativeTracker` 中添加 `_get_linked_sectors(narrative)` 方法
3. **Step 3**: 修改 `NewsMindStrategy._process_narratives()` 在生成叙事信号时附加 sector 信息
4. **Step 4**: 在 `CrossSignalAnalyzer` 中添加 `NarrativeSectorMapper` 类
5. **Step 5**: 集成到 `AttentionSystemIntegration`，实现叙事 → 板块权重联动

---

## 二、漂移检测职责分离

### 2.1 问题分析

**当前状态：**
- `NewsMindStrategy` 使用 `drift.ADWIN` 检测话题漂移
- `DualEngineCoordinator` 或 `PredictiveAttentionEngine` 也使用 `drift.ADWIN` 检测市场状态漂移
- `MarketScanner` 也做 drift 检测
- 三者混用相同的 River drift 检测器，没有明确区分

**目标状态：**
- Radar 的漂移检测专注于**感知数据分布变化**（统计层面）
- Cognition 的漂移检测专注于**话题/叙事的变化**
- Attention 的漂移检测专注于**市场统计分布的变化**

### 2.2 职责划分

| 模块 | 漂移类型 | 检测目标 | 算法 |
|------|----------|----------|------|
| Radar | PerceptionDrift | 感知数据分布变化 | ADWIN on raw data distribution |
| Cognition | NarrativeDrift | 话题关键词频率变化、叙事阶段转变 | ADWIN on keyword_hit_rate |
| Attention | MarketRegimeDrift | 价格分布、波动率、市场状态 | ADWIN on `change_pct` distribution |

### 2.3 修改文件清单

| 文件 | 修改内容 |
|------|----------|
| `radar/market_scanner.py` | Drift 检测重命名为 `radar_drift_detector`，信号 `radar_data_distribution_shift` |
| `cognition/core.py` | 重命名 `drift_detector` → `narrative_drift_detector`，添加 `detect_narrative_drift()` |
| `attention/intelligence/predictive_engine.py` | 保留 `drift_detector`，重命名为 `market_drift_detector` |
| `attention/engine/dual_engine.py` | 漂移信号重命名为 `market_regime_shift` |

### 2.4 实施步骤

1. **Step 1**: 在 `radar/market_scanner.py` 中重命名漂移检测器，明确注释其用途
2. **Step 2**: 添加 `radar_data_distribution_shift` 专用信号类型
3. **Step 3**: 在 `cognition/core.py` 中重命名漂移检测器，明确注释其用途
4. **Step 4**: 添加 `narrative_drift_signal` 专用信号类型
5. **Step 5**: 在 `attention/predictive_engine.py` 中重命名漂移检测器
6. **Step 6**: 更新信号输出格式，确保三者信号类型不冲突

---

## 三、信号命名规范化

### 3.1 问题分析

**当前状态：**
- Cognition 信号：`topic_emerge`, `topic_grow`, `topic_fade`, `high_attention`, `trend_shift`
- Attention 信号：`anomaly_signal`, `pattern_signal`
- Radar 信号：未统一前缀
- 信号类型混在一起，下游系统难以区分

**目标状态：**

| 前缀 | 来源 | 信号类型 |
|------|------|----------|
| `narrative_` | Cognition/NarrativeTracker | `narrative_stage_change`, `narrative_attention_spike` |
| `topic_` | Cognition/NewsMindStrategy | `topic_emerge`, `topic_grow`, `topic_fade` |
| `market_` | Attention/GlobalAttentionEngine | `market_attention_alert`, `market_volatility_spike` |
| `anomaly_` | Attention/DualEngine | `anomaly_pattern`, `anomaly_volume_spike` |
| `radar_` | Radar/MarketScanner | `radar_pattern`, `radar_anomaly`, `radar_sector_anomaly` |

### 3.2 修改文件清单

| 文件 | 修改内容 |
|------|----------|
| `cognition/core.py` | 信号类型 `SignalType` 添加前缀 |
| `cognition/narrative_tracker.py` | 信号类型 `narrative_stage_change` / `narrative_attention_spike` |
| `attention/engine/dual_engine.py` | 信号类型 `anomaly_signal` / `pattern_signal` → `anomaly_pattern` |
| `attention/intelligence/predictive_engine.py` | 信号类型 `market_drift_detected` |
| `attention/core/attention_engine.py` | 信号类型 `market_state_change` |
| `radar/market_scanner.py` | 信号类型统一添加 `radar_` 前缀 |

### 3.3 实施步骤

1. **Step 1**: 更新 `radar/market_scanner.py` 的信号类型前缀
2. **Step 2**: 更新 `cognition/core.py` 的 `SignalType` 枚举，添加前缀
3. **Step 3**: 更新 `cognition/narrative_tracker.py` 的事件类型
4. **Step 4**: 更新 `attention/engine/dual_engine.py` 的 `AnomalySignal`
5. **Step 5**: 更新 `attention/predictive_engine.py` 的漂移信号
6. **Step 6**: 全局搜索替换旧的信号类型名称

---

## 四、CrossSignalAnalyzer 增强

### 4.1 问题分析

`CrossSignalAnalyzer` 已经有 `NewsSignal` 和 `AttentionSnapshot` 的概念，但没有实现叙事→板块的联动。

### 4.2 增强内容

```python
class CrossSignalAnalyzer:
    def __init__(self, ...):
        self._narrative_sector_mapper = NarrativeSectorMapper()
        self._narrative_sector_resonance: Dict[str, float] = {}

    def on_narrative_signal(self, narrative: str, stage: str, score: float):
        """处理叙事信号，更新板块注意力"""
        linked_sectors = self._narrative_sector_mapper.get_linked_sectors(narrative)
        for sector_id in linked_sectors:
            self._narrative_sector_resonance[sector_id] = score

    def get_narrative_augmented_attention(self, base_attention: Dict[str, float]) -> Dict[str, float]:
        """返回融合了叙事信号的板块注意力"""
        augmented = dict(base_attention)
        for sector_id, narrative_boost in self._narrative_sector_resonance.items():
            if sector_id in augmented:
                augmented[sector_id] = augmented[sector_id] * 0.7 + narrative_boost * 0.3
            else:
                augmented[sector_id] = narrative_boost * 0.3
        return augmented
```

---

## 五、修改文件汇总

### 5.1 新增文件

| 文件路径 | 说明 |
|----------|------|
| `cognition/narrative_sector_mapping.py` | 叙事主题到板块的映射配置 |

### 5.2 修改文件

| 文件路径 | 修改类型 |
|----------|----------|
| `radar/engine.py` | 修改（注释明确定位） |
| `radar/market_scanner.py` | 修改（radar_ 前缀 + drift 重命名） |
| `cognition/narrative_tracker.py` | 修改 |
| `cognition/core.py` | 修改 |
| `cognition/cross_signal_analyzer.py` | 修改 |
| `attention/engine/dual_engine.py` | 修改 |
| `attention/intelligence/predictive_engine.py` | 修改 |
| `attention/core/attention_engine.py` | 修改 |

---

## 六、实施顺序

```
Phase 0: Radar 职责明确化 (0.5天)
├── Step 1: 更新 radar/engine.py 注释
├── Step 2: 重命名 radar drift_detector → radar_drift_detector
└── Step 3: Radar 信号添加 radar_ 前缀

Phase 1: 信号命名规范化 (1-2天)
├── Step 1: 更新 radar/market_scanner.py 信号前缀
├── Step 2: 更新 SignalType 枚举 (cognition/core.py)
├── Step 3: 更新 narrative_tracker 事件类型
├── Step 4: 更新 attention 信号类型
└── Step 5: 全局搜索替换验证

Phase 2: 漂移检测分离 (1天)
├── Step 1: 重命名 radar drift_detector
├── Step 2: 重命名 cognition drift_detector
├── Step 3: 重命名 attention drift_detector
└── Step 4: 更新相关信号

Phase 3: 叙事-板块映射 (2-3天)
├── Step 1: 创建 narrative_sector_mapping.py
├── Step 2: 实现 NarrativeSectorMapper
├── Step 3: 集成到 NarrativeTracker
├── Step 4: 集成到 CrossSignalAnalyzer
└── Step 5: 端到端测试

Phase 4: 联动测试 (1天)
├── Step 1: 验证叙事信号 → 板块注意力联动
├── Step 2: 验证信号命名规范化
└── Step 3: 验证漂移检测分离
```

---

## 七、风险与回滚

### 7.1 风险识别

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 信号类型重命名导致下游崩溃 | 高 | 保留旧信号名作为别名，逐步迁移 |
| 叙事-板块映射不准确 | 中 | 提供配置开关，可快速禁用 |
| CrossSignalAnalyzer 复杂度增加 | 低 | 保持接口向后兼容 |
| Radar 改动影响 supervisor 等系统 | 高 | 保持 RadarEngine 接口不变，只改内部命名 |

### 7.2 回滚方案

- 所有修改的文件保留 git 历史
- 信号类型保留旧名作为别名：`topic_emerge = "topic_emerge"` (向后兼容)
- 叙事-板块映射可通过配置 `narrative_sector_linking_enabled: false` 禁用
- Radar 保持原有接口，只修改内部实现和命名

---

## 八、验收标准

1. **Radar 定位明确**：
   - [ ] Radar 作为感知层的定位在代码注释中明确
   - [ ] Radar drift 信号标识为 `radar_data_distribution_shift`

2. **信号命名规范**：
   - [ ] Radar 信号全部以 `radar_` 开头
   - [ ] Cognition 信号全部以 `narrative_` 或 `topic_` 开头
   - [ ] Attention 信号全部以 `market_` 或 `anomaly_` 开头
   - [ ] 旧的信号类型名称作为别名保留

3. **漂移检测分离**：
   - [ ] Radar 的漂移信号明确标识为 `radar_data_distribution_shift`
   - [ ] Cognition 的漂移信号明确标识为 `narrative_drift`
   - [ ] Attention 的漂移信号明确标识为 `market_regime_drift`

4. **叙事-板块联动**：
   - [ ] NarrativeTracker 可获取关联的 sector_id
   - [ ] CrossSignalAnalyzer 可输出融合叙事信号的板块注意力
   - [ ] 联动可通过配置开关控制

5. **向后兼容**：
   - [ ] 现有的外部接口保持不变
   - [ ] 信号类型别名映射存在
   - [ ] RadarEngine 原有接口不变
   - [ ] 集成测试通过