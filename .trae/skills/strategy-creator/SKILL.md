---
name: strategy-creator
description: |
  帮助用户在 Naja 平台快速创建和上线策略的 Skill。
  
  当用户想要创建新策略、添加策略、生成策略代码时，使用此 Skill。
  
  使用方式：
  1. 用户选择要绑定的数据源（从数据源数据库中列出供用户多选）
  2. 用户选择要绑定的数据字典（可选，可多选，从字典数据库中列出）
  3. 用户说明策略的处理方式（用自然语言描述）
  4. AI 自动生成策略名称、描述、计算模式等所有字段
  5. AI 根据数据源和数据字典的数据格式，整合后生成策略执行代码
  6. 将策略保存到策略数据库并上线
  
  策略字段模板基于现有的 river 策略，包含完整的 metadata、state、func_code 结构。
  
  使用场景：
  - "帮我创建一个策略"
  - "我想添加一个新的策略"
  - "生成一个监控行情的策略"
  - "创建一个处理新闻数据的策略"
  - "帮我上线一个策略"
  - 任何涉及创建、生成、添加策略的请求
---

# Strategy Creator Skill

## 概述

此 Skill 用于帮助用户在 Naja 平台快速创建完整的策略，支持数据源和数据字典的整合。

**核心特点：**
- AI 自动生成策略名称、描述、计算模式等所有字段
- 用户只需选择数据源、数据字典（可选）和说明处理逻辑
- 自动整合数据源和数据字典的数据格式
- 基于 river 策略模板生成完整的策略结构
- 自动识别数据格式并生成相应的处理代码

## 使用流程

### 第一步：展示可用数据源

1. 从 `naja_datasources` 数据库中读取所有可用数据源
2. 向用户展示数据源列表：
   ```
   可用数据源：
   1. [timer] 财经新闻模拟源 - 模拟财经新闻数据
   2. [file] 系统日志监控 - 监控系统日志文件
   3. [tick] realtime_quant_5s - 实时行情数据
   ...
   ```
3. 让用户选择要绑定的数据源（支持多选，输入序号，用逗号分隔）

### 第二步：展示可用数据字典（可选）

1. 从 `naja_dictionary_entries` 数据库中读取所有可用数据字典
2. 向用户展示数据字典列表：
   ```
   可用数据字典（可选，可多选）：
   0. 不绑定数据字典
   1. [stock_market] snowball_stock_dict - 通过雪球 MCP 服务获取市场所有个股和基本面表
   2. [stock_basic_block] stock_block_dict_pytdx - 股票板块数据字典
   ...
   ```
3. 让用户选择要绑定的数据字典（支持多选或跳过，输入序号，用逗号分隔）

### 第三步：询问策略处理逻辑

向用户询问：
```
请描述您想要的策略处理方式（例如：
- "当股票价格超过100元时发出警报"
- "监控新闻中出现'上涨'、'下跌'关键词"
- "计算5分钟滑动窗口的平均价格"
- "结合股票基本面数据筛选优质股票"
）
```

### 第四步：AI 自动生成策略

AI 根据以下信息自动生成完整策略：

1. **分析数据源格式**：
   - 读取用户选择的数据源的 `func_code`，了解数据格式
   - 识别数据源类型（tick/news/log/file等）
   - 提取数据字段（price/title/content等）

2. **分析数据字典格式**：
   - 读取用户选择的数据字典的 `func_code`，了解数据格式
   - 识别字典类型（stock_market/stock_basic_block等）
   - 提取字典字段（code/name/industry/blockname等）

3. **整合数据格式**：
   - 将数据源字段和数据字典字段整合
   - 生成交集字段（如 symbol/code）用于数据关联
   - 创建整合后的数据模型

4. **自动生成策略字段**：
   - **名称**：根据处理逻辑自动生成
   - **描述**：根据数据源、字典和处理逻辑自动生成
   - **计算模式**：根据逻辑自动选择（record/window）
   - **窗口参数**：window 模式下自动生成
   - **类别**：根据数据源类型自动分类
   - **标签**：自动生成相关标签
   - **dictionary_profile_ids**：绑定的数据字典ID列表

5. **生成策略代码**：
   - 基于 river 策略模板生成 `func_code`
   - 包含 `process` 函数，处理整合后的数据
   - 根据整合后的数据格式提取相应字段
   - 支持数据字典的查询和关联
   - 返回标准化的结果格式

### 第五步：展示生成的策略

向用户展示生成的策略概要：
```
策略已生成！

【基本信息】
- 名称：价格监控策略
- 描述：基于 realtime_quant_5s 数据源和 snowball_stock_dict 数据字典的价格监控策略。当股票价格超过100元时发出警报
- 计算模式：record
- 绑定数据源：realtime_quant_5s
- 绑定数据字典：snowball_stock_dict

【数据格式整合】
数据源字段：price, volume, symbol, timestamp
数据字典字段：code, name, industry, blockname
关联字段：symbol ↔ code

【生成的代码】
```python
def process(data, context=None):
    # 策略逻辑...
```

是否保存并上线此策略？（是/否）
```

### 第六步：保存并上线

用户确认后，保存策略到数据库：
1. 生成策略ID（使用 uuid）
2. 按照 river 策略模板构建完整的策略字典
3. 保存到 `naja_strategies` 数据库
4. 告知用户策略ID和上线状态

## 策略模板结构

基于 river 策略的完整模板：

```python
{
    "metadata": {
        "id": "策略ID",
        "name": "策略名称",
        "description": "策略描述",
        "tags": [],
        "bound_datasource_id": "单数据源ID（兼容）",
        "bound_datasource_ids": ["多数据源ID列表"],
        "dictionary_profile_ids": ["数据字典ID列表"],  # 新增
        "compute_mode": "record/window",
        "window_size": 5,
        "window_type": "sliding/timed",
        "window_interval": "10s",
        "window_return_partial": false,
        "max_history_count": 300,
        "diagram_info": {
            "icon": "📊",
            "color": "#3498DB",
            "description": "策略描述",
            "formula": "计算公式",
            "logic": ["步骤1", "步骤2"],
            "output": "输出格式",
            "river_metaphor": {  # 河流比喻（可选但推荐）
                "title": "🌊 河流比喻",
                "description": "将策略比作河流中的生物或现象",
                "elements": {...},
                "process": [...]
            }
        },
        "category": "类别",
        "created_at": 时间戳,
        "updated_at": 时间戳
    },
    "state": {...},
    "func_code": "策略代码字符串",
    "was_running": false
}
```

## 代码生成规则

### 1. 数据源字段映射

**行情数据 (tick)**：
- price, volume, symbol, timestamp

**新闻数据 (news)**：
- title, content, timestamp, type

**日志数据 (log)**：
- content, timestamp

**文件数据 (file)**：
- file_path, event_type, timestamp

### 2. 数据字典字段映射

**股票市场字典 (stock_market)**：
- stock_list: code, name, industry
- fundamentals: stock_code, 财务指标...

**股票板块字典 (stock_basic_block)**：
- code, name, industry, blockname

### 3. 数据整合逻辑

当同时绑定数据源和数据字典时，生成数据整合代码：

```python
def process(data, context=None):
    # 获取数据源信息
    raw_data = data.get("data", {})
    datasource_name = data.get("_datasource_name", "unknown")
    
    # 提取数据源字段
    symbol = raw_data.get("symbol", "")
    price = raw_data.get("price", 0)
    
    # 查询数据字典
    from deva import NB
    dict_data = NB('naja_dictionary_payloads').get('字典ID:latest', {})
    
    # 关联数据（以 symbol/code 为关联字段）
    matched_info = None
    if dict_data and symbol:
        for item in dict_data.get('data', []):
            if item.get('code') == symbol or item.get('symbol') == symbol:
                matched_info = item
                break
    
    # 整合后的数据
    integrated_data = {
        "symbol": symbol,
        "price": price,
        "name": matched_info.get('name', '') if matched_info else '',
        "industry": matched_info.get('industry', '') if matched_info else '',
        "blockname": matched_info.get('blockname', '') if matched_info else '',
    }
    
    # 用户自定义处理逻辑...
```

### 4. 返回格式标准化

```python
return {
    "signal": "信号标识",
    "data": 整合后的数据,
    "source": datasource_name,
    "timestamp": time.time()
}
```

### 5. diagram_info 生成规则（重要）

**必须生成完整的 diagram_info，包含河流比喻！**

#### 基本结构（推荐：使用 principle 字段）

参考 `river_交易行为痕迹聚类` 策略的结构：

```python
{
    "icon": "📊",  # 根据策略类型选择图标
    "color": "#3498DB",  # 根据策略类型选择颜色
    "description": "策略功能描述",
    "formula": "策略计算公式或逻辑表达式",
    "logic": ["步骤1", "步骤2", "步骤3"],
    "output": "输出数据格式",
    "principle": {
        "title": "🌊 河流比喻：标题",
        "core_concept": "核心概念描述，将策略比作河流中的生物或现象",
        "five_dimensions": {
            "向_维度1": {
                "description": "维度描述",
                "implementation": "实现方式",
                "metrics": ["指标1", "指标2"],
                "interpretation": "解读方式"
            },
            "速_维度2": { ... },
            "弹_维度3": { ... },
            "深_维度4": { ... },
            "波_维度5": { ... }
        },
        "learning_mechanism": "学习机制说明",
        "output_meaning": "输出含义说明"
    }
}
```

**注意：** 前端渲染使用 `principle` 字段，不是 `river_metaphor` 字段！

#### 五个维度说明

所有策略都应该包含五个维度（向/速/弹/深/波）：

| 维度 | 含义 | 对应策略方面 |
|------|------|-------------|
| **向** | 方向/趋势 | 数据流的方向、主题演变 |
| **速** | 速度/节奏 | 数据频率、处理速度 |
| **弹** | 弹性/冲击 | 高注意力事件、异常检测 |
| **深** | 深度/结构 | 记忆层级、数据深度 |
| **波** | 波动/模式 | 信号模式、周期性变化 |

#### 旧结构（不推荐，但兼容）

```python
{
    ...
    "river_metaphor": {
        "title": "🌊 河流比喻",
        "description": "...",
        "elements": { ... },
        "process": [ ... ]
    }
}
```

#### 图标映射表

根据策略类型选择图标：
- 📊 通用/分析类策略
- 📈 价格/行情类策略
- 📰 新闻/文本类策略
- 📝 日志/监控类策略
- 🦞 流式学习类策略（如龙虾思想雷达）
- 🤖 智能/AI类策略
- 💰 财务/基本面类策略
- 🏢 板块/行业类策略

#### 颜色映射表

- `#3498DB` 蓝色 - 通用/分析
- `#E74C3C` 红色 - 价格/行情/警报
- `#2ECC71` 绿色 - 增长/正面
- `#F39C12` 橙色 - 新闻/文本
- `#9B59B6` 紫色 - 智能/AI
- `#1ABC9C` 青色 - 监控/日志

#### 河流比喻生成规则

**必须根据策略特点生成相应的河流比喻！**

**示例 1：价格监控策略（使用 principle 字段）**
```python
"principle": {
    "title": "🌊 河流比喻：渔夫在行情河流中钓鱼",
    "core_concept": "像渔夫在河边观察水流，用鱼竿感知鱼群（价格）的动向。实时监控价格变化，识别突破机会。",
    "five_dimensions": {
        "向_价格趋势": {
            "description": "价格变动的方向和趋势",
            "implementation": "通过价格序列计算趋势",
            "metrics": ["price_direction - 价格方向", "trend_strength - 趋势强度"],
            "interpretation": "向上趋势 = 水流向前，可能上涨；向下趋势 = 水流后退，可能下跌"
        },
        "速_价格变化速度": {
            "description": "价格变化的节奏和速度",
            "implementation": "通过价格变化率计算",
            "metrics": ["price_velocity - 价格速度", "change_frequency - 变化频率"],
            "interpretation": "快速变化 = 急流，可能突破；缓慢变化 = 缓流，可能盘整"
        },
        "弹_价格突破": {
            "description": "价格突破阈值的冲击力",
            "implementation": "通过阈值检测",
            "metrics": ["breakout_strength - 突破强度", "threshold_distance - 阈值距离"],
            "interpretation": "突破阈值 = 漩涡，触发信号；未突破 = 平缓水流，继续观察"
        },
        "深_价格记忆": {
            "description": "历史价格数据的深度",
            "implementation": "通过历史数据存储",
            "metrics": ["history_depth - 历史深度", "support_resistance - 支撑阻力位"],
            "interpretation": "深层历史 = 河床石头，形成支撑阻力；浅层历史 = 水面波纹，短期波动"
        },
        "波_价格波动模式": {
            "description": "价格波动的周期性模式",
            "implementation": "通过波动率分析",
            "metrics": ["volatility - 波动率", "wave_pattern - 波纹模式"],
            "interpretation": "高波动 = 波涛汹涌，机会多；低波动 = 平静湖面，机会少"
        }
    },
    "learning_mechanism": "实时监控价格数据，通过阈值检测识别突破机会，halflife=0.5 平衡响应速度和稳定性",
    "output_meaning": "信号表示价格突破事件：PRICE_BREAKOUT（价格突破）/ PRICE_ALERT（价格警报）"
}
```

**示例 2：新闻监控策略（使用 principle 字段）**
```python
"principle": {
    "title": "🌊 河流比喻：水獭在信息河流中收集新闻",
    "core_concept": "像水獭在河面收集漂浮的树叶（新闻），筛选有价值的信息。实时分析新闻流，识别热点事件。",
    "five_dimensions": {
        "向_新闻流向": {
            "description": "新闻主题的演变方向",
            "implementation": "通过主题追踪",
            "metrics": ["topic_direction - 主题方向", "sentiment_trend - 情感趋势"],
            "interpretation": "正面情感 = 顺流，利好；负面情感 = 逆流，利空"
        },
        "速_新闻流速": {
            "description": "新闻发布的频率和密度",
            "implementation": "通过新闻频率计算",
            "metrics": ["news_frequency - 新闻频率", "burst_rate - 爆发率"],
            "interpretation": "高频新闻 = 急流，热点事件；低频新闻 = 缓流，平静期"
        },
        "弹_热点冲击": {
            "description": "热点新闻的冲击力",
            "implementation": "通过关键词匹配和情感分析",
            "metrics": ["keyword_match - 关键词匹配度", "sentiment_spike - 情感峰值"],
            "interpretation": "高匹配度 = 漩涡，重要新闻；低匹配度 = 普通水流，一般新闻"
        },
        "深_新闻记忆": {
            "description": "历史新闻数据的深度",
            "implementation": "通过新闻存储和索引",
            "metrics": ["news_history - 新闻历史", "topic_persistence - 主题持久度"],
            "interpretation": "持久主题 = 河床石头，长期关注；短暂主题 = 水面落叶，短期热点"
        },
        "波_新闻传播": {
            "description": "新闻传播的模式和范围",
            "implementation": "通过传播分析",
            "metrics": ["spread_range - 传播范围", "influence_score - 影响力分数"],
            "interpretation": "广泛传播 = 大波浪，重要事件；有限传播 = 小波纹，局部事件"
        }
    },
    "learning_mechanism": "实时接收新闻数据，通过关键词匹配和情感分析识别热点，halflife=0.3 快速响应新闻变化",
    "output_meaning": "信号表示新闻热点事件：NEWS_HOT（热点新闻）/ SENTIMENT_ALERT（情感警报）"
}
```

**示例 3：龙虾思想雷达（参考，使用 principle 字段）**
```python
"principle": {
    "title": "🌊 河流比喻：龙虾在信息河流中感知水流",
    "core_concept": "想象一条信息河流，龙虾在河底用触角感知水流的变化。实时分析数据流，动态生成主题信号和注意力信号，就像龙虾感知河流中的水流变化、漩涡和暗流。",
    "five_dimensions": {
        "向_水流方向": {
            "description": "数据流的方向和趋势",
            "implementation": "通过主题分析判断",
            "metrics": ["topic_direction - 主题演变方向", "topic_velocity - 主题变化速度"],
            "interpretation": "稳定方向 = 成熟主题，像稳定河流；快速变化 = 新兴主题，像湍急水流"
        },
        "速_水流速度": {
            "description": "数据流的节奏和速度",
            "implementation": "通过数据频率和密度判断",
            "metrics": ["data_frequency - 数据频率", "topic_growth_rate - 主题增长率"],
            "interpretation": "高频率 + 稳定增长 = 热门主题，像急流；低频率 = 冷门主题，像缓流"
        },
        "弹_水流冲击": {
            "description": "高注意力事件的冲击力",
            "implementation": "通过 attention_level 衡量",
            "metrics": ["attention_level - 注意力等级", "attention_spike - 注意力峰值"],
            "interpretation": "高 attention_level = 热点事件，像漩涡；低 attention_level = 普通事件，像平缓水流"
        },
        "深_河床结构": {
            "description": "分层记忆结构的深度",
            "implementation": "通过记忆层级判断",
            "metrics": ["memory_depth - 记忆深度", "topic_persistence - 主题持久度"],
            "interpretation": "深层记忆 = 持久主题，像河床石头；浅层记忆 = 临时主题，像水面落叶"
        },
        "波_水流波纹": {
            "description": "数据流产生的波纹模式",
            "implementation": "通过信号类型和频率判断",
            "metrics": ["signal_frequency - 信号频率", "topic_diversity - 主题多样性"],
            "interpretation": "频繁信号 + 多样主题 = 活跃市场，像波涛汹涌；稀少信号 = 平静市场，像平静湖面"
        }
    },
    "learning_mechanism": "流式学习实时更新分层记忆，halflife=0.5 平衡响应速度和稳定性，周期性自我反思优化记忆结构，通过主题演变和注意力检测生成信号",
    "output_meaning": "信号表示识别出的水流变化：TOPIC_EMERGE（新水流分支）/ TOPIC_GROW（水流增强）/ HIGH_ATTENTION（漩涡热点）/ TREND_SHIFT（水流改向）"
}
```

#### 生成原则

1. **必须使用 principle 字段**：所有策略都应该使用 principle 字段存储河流比喻（不是 river_metaphor）
2. **必须包含 five_dimensions**：所有策略都应该包含五个维度（向/速/弹/深/波）
3. **贴合策略特点**：根据策略的功能和数据源类型设计比喻
4. **形象生动**：使用容易理解的生物和场景
5. **维度对应**：确保五个维度与策略的不同方面一一对应
   - 向 → 方向/趋势
   - 速 → 速度/节奏
   - 弹 → 弹性/冲击/异常
   - 深 → 深度/结构/记忆
   - 波 → 波动/模式/周期

#### 注意事项

⚠️ **重要**：前端渲染使用 `principle` 字段，不是 `river_metaphor` 字段！

- `principle` 字段包含：title, core_concept, five_dimensions, learning_mechanism, output_meaning
- `river_metaphor` 是旧结构，虽然兼容但不推荐新策略使用
- 所有新创建的策略都应该使用 `principle` 字段

## 用户交互示例

**示例 1：价格监控 + 基本面筛选**

用户输入：
```
选择数据源：3 (realtime_quant_5s)
选择数据字典：1 (snowball_stock_dict)
处理方式：当股票价格超过100元且市盈率低于20时发出警报
```

AI 生成：
- 名称：优质股票价格监控策略
- 描述：基于 realtime_quant_5s 数据源和 snowball_stock_dict 数据字典...
- 代码：整合行情数据和基本面数据，关联 symbol 和 code

**示例 2：板块监控策略**

用户输入：
```
选择数据源：3 (realtime_quant_5s)
选择数据字典：2 (stock_block_dict_pytdx)
处理方式：监控科技板块的股票价格变动
```

AI 生成：
- 名称：科技板块价格监控策略
- 代码：整合行情数据和板块数据，筛选 blockname 包含"科技"的股票

## 辅助脚本

使用 `scripts/create_strategy.py` 辅助生成策略：

```python
# 获取所有数据源
datasources = get_all_datasources()

# 获取所有数据字典
dictionaries = get_all_dictionaries()

# 分析数据格式
datasource_formats = analyze_datasource_formats(datasource_ids)
dictionary_formats = analyze_dictionary_formats(dictionary_ids)

# 整合数据格式
integrated_format = integrate_data_formats(datasource_formats, dictionary_formats)

# 生成策略代码
func_code = generate_process_code(
    compute_mode="record",
    integrated_format=integrated_format,
    user_logic="当股票价格超过100元时报警"
)

# 保存策略
strategy_id = save_strategy_to_db(strategy_record)
```

## 注意事项

1. **数据格式识别**：自动分析数据源和数据字典的返回格式
2. **数据关联**：自动识别关联字段（symbol/code/name等）
3. **字典查询**：在 process 函数中使用 NB 查询字典数据
4. **性能考虑**：避免每次处理都全量查询字典，可考虑缓存
5. **代码质量**：生成的代码包含完整注释和错误处理

## 输出目标配置

创建策略时需要配置输出目标，策略会根据输出目标返回不同格式的数据：

### 四种输出目标

| 目标 | 用途 | 必需字段 | 可选字段 |
|------|------|----------|----------|
| **💰 信号流** | 存储所有策略结果 | 无（任意格式） | 无 |
| **📡 雷达** | 技术信号 | signal_type, score | value, message |
| **🧠 记忆** | 叙事记忆 | content | topic, sentiment |
| **🎰 Bandit** | 交易执行 | signal_type(BUY/SELL), stock_code, price | confidence, amount, reason |

### 输出结构规范示例

**雷达 (技术信号)：**
```python
return {
    "signal_type": "fast_anomaly",  # 必填：信号类型
    "score": 8.5,                    # 必填：评分
    "value": 100,                    # 可选：数值
    "message": "价格突破"             # 可选：消息
}
```

**记忆 (叙事)：**
```python
return {
    "content": "AI芯片板块持续火热",  # 必填：叙事内容
    "topic": "科技",                  # 可选：主题
    "sentiment": "positive"          # 可选：情感
}
```

**Bandit (交易)：**
```python
return {
    "signal_type": "BUY",            # 必填：BUY/SELL
    "stock_code": "000001",          # 必填：股票代码
    "price": 12.50,                 # 必填：价格
    "confidence": 0.85,              # 可选：置信度
    "amount": 10000,                 # 可选：金额
    "reason": "放量突破"             # 可选：原因
}
```

### 默认配置

新创建的策略默认开启：**信号流、雷达、记忆**
- Bandit 交易需要手动开启

### 信号类型参考

常见的 signal_type 值：
- `fast_anomaly` - 快速异动
- `volume_breakout` - 放量突破
- `trend_analysis` - 市场气候
- `block_leader` - 板块龙头
- `contrarian` - 逆势信号
