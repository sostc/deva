# 美林时钟分层架构设计

> 创建时间：2026-04-03  
> 目标：将经济周期判断与流动性分析分离，实现清晰的双层架构

---

## 一、架构设计

### 1.1 双层架构

```
┌─────────────────────────────────────────────────────────┐
│           上层：美林时钟（经济周期判断）                   │
│  MerrillClockEngine                                      │
│  - 输入：经济增长数据 (GDP/PMI/就业) + 通胀数据 (CPI/PCE)  │
│  - 输出：周期阶段 (复苏/过热/滞胀/衰退) + 资产配置建议     │
│  - 时间尺度：季度/年度（中长期）                          │
└─────────────────────────────────────────────────────────┘
                          ↓ 指导
┌─────────────────────────────────────────────────────────┐
│           下层：流动性认知（跨市场传导）                   │
│  LiquidityCognition                                      │
│  - 输入：全球市场事件 + 周期阶段指导                      │
│  - 输出：流动性预测 + 跨市场传导信号                      │
│  - 时间尺度：日/周（短期）                                │
└─────────────────────────────────────────────────────────┘
```

### 1.2 职责分离

| 维度 | 美林时钟（上层） | 流动性认知（下层） |
|------|----------------|------------------|
| **定位** | 战略层（方向判断） | 战术层（时机把握） |
| **回答** | "现在应该超配什么资产？" | "短期资金会流向哪里？" |
| **数据源** | 宏观经济数据 | 市场舆情 + 资金流向 |
| **判断依据** | 经济增长 × 通胀 | 叙事热度 × 跨市场传导 |
| **输出** | 周期阶段 + 资产配置 | 流动性预测 + 传导概率 |
| **更新频率** | 低频（周/月） | 高频（日/周） |

---

## 二、美林时钟引擎设计

### 2.1 核心逻辑

```python
class MerrillClockPhase(Enum):
    RECOVERY = "复苏"      # 经济↑ 通胀↓ → 股票最佳
    OVERHEAT = "过热"      # 经济↑ 通胀↑ → 商品最佳
    STAGFLATION = "滞胀"   # 经济↓ 通胀↑ → 现金最佳
    RECESSION = "衰退"     # 经济↓ 通胀↓ → 债券最佳

class MerrillClockEngine:
    """
    美林时钟引擎 - 基于真实经济数据判断周期阶段
    """
    
    def on_economic_data(self, data: EconomicData):
        """接收经济数据"""
        # 1. 计算增长评分
        growth_score = self._calculate_growth_score(
            gdp=data.gdp_growth,
            pmi=data.pmi,
            employment=data.nonfarm_payrolls,
            retail=data.retail_sales
        )
        
        # 2. 计算通胀评分
        inflation_score = self._calculate_inflation_score(
            cpi=data.cpi_yoy,
            pce=data.core_pce,
            ppi=data.ppi,
            breakeven=data.tips_breakeven
        )
        
        # 3. 判断周期阶段
        phase = self._determine_phase(growth_score, inflation_score)
        
        # 4. 生成资产配置建议
        allocation = self._generate_allocation(phase)
        
        # 5. 发布信号
        self._emit_signal(phase, allocation)
    
    def _determine_phase(self, growth: float, inflation: float) -> MerrillClockPhase:
        """基于增长和通胀判断周期阶段"""
        if growth > 0 and inflation < 0:
            return MerrillClockPhase.RECOVERY    # 复苏
        elif growth > 0 and inflation > 0:
            return MerrillClockPhase.OVERHEAT    # 过热
        elif growth < 0 and inflation > 0:
            return MerrillClockPhase.STAGFLATION # 滞胀
        else:
            return MerrillClockPhase.RECESSION   # 衰退
    
    def _generate_allocation(self, phase: MerrillClockPhase) -> Dict:
        """生成资产配置建议"""
        allocations = {
            MerrillClockPhase.RECOVERY: {
                "ranking": ["股票", "债券", "商品", "现金"],
                "overweight": ["科技股", "成长股", "周期股"],
                "underweight": ["防御股", "公用事业"],
                "reason": "经济复苏，企业盈利改善，股票最佳"
            },
            MerrillClockPhase.OVERHEAT: {
                "ranking": ["商品", "股票", "现金", "债券"],
                "overweight": ["能源", "工业金属", "资源股"],
                "underweight": ["债券", "高估值成长股"],
                "reason": "经济过热，通胀上升，商品最佳"
            },
            MerrillClockPhase.STAGFLATION: {
                "ranking": ["现金", "商品", "债券", "股票"],
                "overweight": ["货币基金", "短期债券", "黄金"],
                "underweight": ["股票", "长期债券"],
                "reason": "滞胀环境，现金为王"
            },
            MerrillClockPhase.RECESSION: {
                "ranking": ["债券", "现金", "股票", "商品"],
                "overweight": ["国债", "投资级债", "防御股"],
                "underweight": ["周期股", "商品"],
                "reason": "经济衰退，债券最佳"
            },
        }
        return allocations[phase]
```

### 2.2 数据需求

```python
@dataclass
class EconomicData:
    """经济数据包"""
    timestamp: float
    
    # 经济增长指标
    gdp_growth: float          # GDP 同比增速
    pmi: float                 # 制造业 PMI
    services_pmi: float        # 服务业 PMI
    nonfarm_payrolls: float    # 非农就业人数变化
    unemployment_rate: float   # 失业率
    retail_sales: float        # 零售销售同比
    industrial_production: float  # 工业产出同比
    
    # 通胀指标
    cpi_yoy: float             # CPI 同比
    core_cpi_yoy: float        # 核心 CPI 同比
    pce_yoy: float             # PCE 同比
    core_pce_yoy: float        # 核心 PCE 同比
    ppi_yoy: float             # PPI 同比
    tips_breakeven: float      # TIPS 盈亏平衡通胀率
    
    # 金融条件（可选）
    yield_curve_spread: float  # 10Y-2Y 利差
    credit_spread: float       # 信用利差
    dollar_index: float        # 美元指数
```

### 2.3 数据来源

```python
class EconomicDataFetcher:
    """
    经济数据获取器
    
    数据源：
    1. FRED API（美联储经济数据）
    2. 统计局数据
    3. 财经日历
    """
    
    async def fetch_latest_data(self) -> EconomicData:
        """获取最新经济数据"""
        # 美国数据（FRED API）
        us_data = await self._fetch_fred_data()
        
        # 中国数据（统计局 API）
        cn_data = await self._fetch_china_data()
        
        # 市场数据（通胀预期、利差等）
        market_data = await self._fetch_market_data()
        
        return EconomicData(
            timestamp=time.time(),
            **us_data,
            **cn_data,
            **market_data
        )
```

---

## 三、流动性认知优化

### 3.1 接收周期指导

```python
class LiquidityCognition:
    """
    流动性认知 - 跨市场传导分析
    
    新增：接收美林时钟的周期阶段指导
    """
    
    def __init__(self):
        self._current_phase: Optional[MerrillClockPhase] = None
        self._phase_confidence: float = 0.0
    
    def on_clock_signal(self, phase: MerrillClockPhase, allocation: Dict):
        """接收美林时钟信号"""
        self._current_phase = phase
        self._phase_confidence = allocation.get("confidence", 0.5)
        log.info(f"[LiquidityCognition] 周期阶段更新：{phase.value}")
    
    def get_active_prediction(self, to_market: str) -> Optional[LiquidityPrediction]:
        """
        获取流动性预测（增强版）
        
        周期阶段会影响预测置信度：
        - 如果预测方向与周期建议一致 → 提高置信度
        - 如果预测方向与周期建议冲突 → 降低置信度
        """
        prediction = self._get_prediction(to_market)
        if not prediction:
            return None
        
        # 周期调整
        if self._current_phase:
            alignment = self._check_alignment(prediction, self._current_phase)
            if alignment > 0:
                # 方向一致，提高置信度
                prediction.probability *= (1.0 + 0.2 * alignment)
            else:
                # 方向冲突，降低置信度
                prediction.probability *= (1.0 - 0.1 * abs(alignment))
        
        return prediction
    
    def _check_alignment(self, prediction: LiquidityPrediction, 
                         phase: MerrillClockPhase) -> float:
        """
        检查流动性预测与周期阶段的一致性
        
        Returns:
            float: -1.0（完全冲突）到 1.0（完全一致）
        """
        # 周期阶段的资产偏好
        phase_preferences = {
            MerrillClockPhase.RECOVERY: {"stock": 1.0, "bond": 0.5, "commodity": -0.5},
            MerrillClockPhase.OVERHEAT: {"commodity": 1.0, "stock": 0.5, "cash": -0.5},
            MerrillClockPhase.STAGFLATION: {"cash": 1.0, "commodity": 0.5, "stock": -1.0},
            MerrillClockPhase.RECESSION: {"bond": 1.0, "cash": 0.5, "stock": -1.0},
        }
        
        # 预测的目标市场
        market_map = {
            "a_share": "stock",
            "us_equity": "stock",
            "treasury": "bond",
            "gold": "commodity",
            "crude": "commodity",
            "usd": "cash",
        }
        
        target = market_map.get(prediction.to_market)
        if not target:
            return 0.0
        
        preference = phase_preferences[phase].get(target, 0.0)
        
        # 预测方向 × 周期偏好
        direction_factor = 1.0 if prediction.direction == "up" else -1.0
        alignment = direction_factor * preference
        
        return alignment
```

---

## 四、协同机制

### 4.1 信号流转

```
经济数据发布 ──→ MerrillClockEngine ──→ 周期阶段信号
                                              ↓
                                        LiquidityCognition
                                              ↓
                                        流动性预测（经周期调整）
                                              ↓
                                          Attention 系统
                                              ↓
                                          策略执行
```

### 4.2 冲突处理

当短期流动性信号与中长期周期判断冲突时：

```python
def resolve_conflict(self, 
                     liquidity_signal: LiquiditySignal,
                     clock_signal: MerrillClockSignal) -> Action:
    """
    解决信号冲突
    
    原则：
    1. 周期方向 > 短期波动（战略 > 战术）
    2. 但如果短期信号极强，可能是周期转折点
    """
    if clock_signal.phase_confidence < 0.5:
        # 周期判断置信度低，以短期信号为主
        return Action.from_signal(liquidity_signal)
    
    if liquidity_signal.probability > 0.8:
        # 短期信号极强，可能是转折点，降低仓位试探
        return Action(
            direction=liquidity_signal.direction,
            size=PositionSize.SMALL,  # 小仓位试探
            reason=f"短期信号强，但与周期判断冲突，试探性建仓"
        )
    
    # 默认：遵循周期判断
    return Action.from_signal(clock_signal)
```

---

## 五、实现计划

### Phase 1: 补充数据层（1-2 天）

1. **添加经济数据关键词**
   - 经济增长指标（GDP、PMI、就业）
   - 通胀指标（CPI、PCE、PPI）
   
2. **实现数据获取器**
   - FRED API 集成
   - 财经日历数据源

### Phase 2: 实现美林时钟引擎（2-3 天）

1. **核心逻辑**
   - 增长/通胀评分计算
   - 周期阶段判断
   - 资产配置建议生成

2. **信号发布**
   - 与 InsightPool 集成
   - 供 LLM 反思使用

### Phase 3: 流动性认知优化（1-2 天）

1. **接收周期指导**
   - 订阅美林时钟信号
   - 调整预测置信度

2. **冲突处理机制**
   - 实现信号协调逻辑

### Phase 4: 测试与验证（1-2 天）

1. **回测框架**
   - 历史周期判断准确性
   - 流动性预测准确性

2. **可视化**
   - 周期阶段展示
   - 资产配置建议展示

---

## 六、预期收益

| 指标 | 当前 | 改进后 |
|------|------|--------|
| **周期判断准确性** | N/A（无真正美林时钟） | >70%（基于真实数据） |
| **流动性预测准确性** | ~60% | ~75%（经周期调整） |
| **信号冲突处理** | 无 | 有明确规则 |
| **时间尺度匹配** | 混乱（短期判断长期） | 清晰（分层处理） |

---

## 七、风险与应对

### 风险 1: 数据延迟

**问题**：经济数据发布有延迟（如非农数据次月发布）

**应对**：
- 使用高频数据代理（如周度初请失业金）
- 结合市场预期数据
- 使用 Nowcasting 技术

### 风险 2: 假信号

**问题**：单一数据点可能产生误导

**应对**：
- 多指标交叉验证
- 使用扩散指数（多个指标的综合）
- 设置置信度阈值

### 风险 3: 周期转换滞后

**问题**：周期判断可能滞后于实际转折

**应对**：
- 加入先行指标（收益率曲线倒挂、PMI 新订单）
- 设置快速转换通道（当多个指标同时转向时）

---

## 八、总结

**核心改进**：
1. ✅ **分层清晰**：美林时钟（战略）与流动性认知（战术）分离
2. ✅ **数据驱动**：基于真实经济数据，而非仅舆情
3. ✅ **时间匹配**：中长期周期 + 短期流动性，各司其职
4. ✅ **协同机制**：周期指导流动性，冲突有规则

**下一步**：
1. 确认方案
2. 开始实现 Phase 1

---

*遵循天道（真实经济数据），驾驭民心（市场舆情）*
