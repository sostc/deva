"""
MerrillClockEngine - 美林时钟引擎/经济周期判断

别名/关键词：美林时钟、经济周期、Merrill Lynch Clock、investment clock

核心功能：
1. 基于真实经济数据判断周期阶段（复苏/过热/滞胀/衰退）
2. 生成资产配置建议
3. 提供周期信号供流动性认知使用

时间尺度：中长期（季度/年度）
数据源：经济增长数据（GDP/PMI/就业）+ 通胀数据（CPI/PCE/PPI）
"""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)


class MerrillClockPhase(Enum):
    """美林时钟四阶段"""
    RECOVERY = "复苏"       # 经济↑ 通胀↓ → 股票最佳
    OVERHEAT = "过热"       # 经济↑ 通胀↑ → 商品最佳
    STAGFLATION = "滞胀"    # 经济↓ 通胀↑ → 现金最佳
    RECESSION = "衰退"      # 经济↓ 通胀↓ → 债券最佳


@dataclass
class EconomicData:
    """
    经济数据包
    
    包含判断经济周期所需的核心指标
    """
    timestamp: float
    
    # 经济增长指标（标准化为同比/环比增速）
    gdp_growth: Optional[float] = None          # GDP 同比增速（%）
    pmi: Optional[float] = None                 # 制造业 PMI（50 为荣枯线）
    services_pmi: Optional[float] = None        # 服务业 PMI
    nonfarm_payrolls: Optional[float] = None    # 非农就业人数变化（千人）
    unemployment_rate: Optional[float] = None   # 失业率（%）
    retail_sales: Optional[float] = None        # 零售销售同比（%）
    industrial_production: Optional[float] = None  # 工业产出同比（%）
    
    # 通胀指标
    cpi_yoy: Optional[float] = None             # CPI 同比（%）
    core_cpi_yoy: Optional[float] = None        # 核心 CPI 同比（%）
    pce_yoy: Optional[float] = None             # PCE 同比（%）
    core_pce_yoy: Optional[float] = None        # 核心 PCE 同比（%）
    ppi_yoy: Optional[float] = None             # PPI 同比（%）
    tips_breakeven: Optional[float] = None      # TIPS 盈亏平衡通胀率（%）
    
    # 金融条件（可选）
    yield_curve_spread: Optional[float] = None  # 10Y-2Y 利差（bps）
    credit_spread: Optional[float] = None       # 信用利差（bps）
    dollar_index: Optional[float] = None        # 美元指数


@dataclass
class PhaseSignal:
    """
    周期阶段信号
    
    美林时钟引擎的输出
    """
    phase: MerrillClockPhase
    confidence: float              # 置信度 0-1
    growth_score: float            # 增长评分 -1 到 1
    inflation_score: float         # 通胀评分 -1 到 1
    timestamp: float
    
    # 资产配置建议
    asset_ranking: List[str]       # 资产偏好排序（从优到劣）
    overweight: List[str]          # 建议超配
    underweight: List[str]         # 建议低配
    reason: str                    # 判断理由
    
    # 经济数据摘要
    data_summary: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "phase": self.phase.value,
            "confidence": round(self.confidence, 3),
            "growth_score": round(self.growth_score, 3),
            "inflation_score": round(self.inflation_score, 3),
            "timestamp": self.timestamp,
            "asset_ranking": self.asset_ranking,
            "overweight": self.overweight,
            "underweight": self.underweight,
            "reason": self.reason,
            "data_summary": self.data_summary,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PhaseSignal":
        """从字典恢复 PhaseSignal"""
        phase = MerrillClockPhase(data["phase"])
        return cls(
            phase=phase,
            confidence=float(data["confidence"]),
            growth_score=float(data["growth_score"]),
            inflation_score=float(data["inflation_score"]),
            timestamp=float(data["timestamp"]),
            asset_ranking=data.get("asset_ranking", []),
            overweight=data.get("overweight", []),
            underweight=data.get("underweight", []),
            reason=data.get("reason", ""),
            data_summary=data.get("data_summary", {}),
        )


class MerrillClockEngine:
    """
    美林时钟引擎
    
    基于真实经济数据判断经济周期阶段，并生成资产配置建议
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        cfg = config or {}
        
        # 配置参数
        self._growth_threshold = float(cfg.get("growth_threshold", 0.0))
        self._inflation_threshold = float(cfg.get("inflation_threshold", 0.0))
        self._confidence_min = float(cfg.get("confidence_min", 0.3))
        
        # 指标权重
        self._growth_weights = cfg.get("growth_weights", {
            "gdp": 0.3,
            "pmi": 0.2,
            "employment": 0.2,
            "retail": 0.15,
            "industrial": 0.15,
        })
        
        self._inflation_weights = cfg.get("inflation_weights", {
            "cpi": 0.3,
            "pce": 0.3,
            "ppi": 0.2,
            "tips": 0.2,
        })
        
        # 状态
        self._current_phase: Optional[MerrillClockPhase] = None
        self._current_signal: Optional[PhaseSignal] = None
        self._last_update: float = 0.0
        
        # 历史记录
        self._history: List[PhaseSignal] = []
        self._max_history = 100
        
        log.info("[MerrillClockEngine] 初始化完成")
    
    def on_economic_data(self, data: EconomicData) -> Optional[PhaseSignal]:
        """
        接收经济数据并判断周期阶段
        
        Args:
            data: 经济数据包
            
        Returns:
            PhaseSignal: 周期阶段信号（如果数据不足则返回 None）
        """
        log.debug(f"[MerrillClockEngine] 接收经济数据：{data.timestamp}")
        
        # 1. 计算增长评分
        growth_score = self._calculate_growth_score(data)
        
        # 2. 计算通胀评分
        inflation_score = self._calculate_inflation_score(data)
        
        # 3. 检查数据质量
        data_quality = self._check_data_quality(data)
        if data_quality < self._confidence_min:
            log.warning(f"[MerrillClockEngine] 数据质量不足：{data_quality:.2f}")
            return None
        
        # 4. 判断周期阶段
        phase = self._determine_phase(growth_score, inflation_score)
        
        # 5. 计算置信度
        confidence = self._calculate_confidence(growth_score, inflation_score, data_quality)
        
        # 6. 生成资产配置建议
        allocation = self._generate_allocation(phase, confidence)
        
        # 7. 创建信号
        signal = PhaseSignal(
            phase=phase,
            confidence=confidence,
            growth_score=growth_score,
            inflation_score=inflation_score,
            timestamp=time.time(),
            asset_ranking=allocation["ranking"],
            overweight=allocation["overweight"],
            underweight=allocation["underweight"],
            reason=allocation["reason"],
            data_summary=self._summarize_data(data),
        )
        
        # 8. 更新状态
        self._current_phase = phase
        self._current_signal = signal
        self._last_update = time.time()
        
        # 9. 记录历史
        self._history.append(signal)
        if len(self._history) > self._max_history:
            self._history.pop(0)
        
        log.info(f"[MerrillClockEngine] 周期阶段：{phase.value}, 置信度：{confidence:.2f}")
        
        # 10. 发布信号（供流动性认知使用）
        self._emit_signal(signal)
        
        return signal
    
    def _calculate_growth_score(self, data: EconomicData) -> float:
        """
        计算经济增长评分
        
        Returns:
            float: -1（严重放缓）到 1（强劲增长）
        """
        scores = []
        weights = []
        
        # GDP 增速（如果有）
        if data.gdp_growth is not None:
            # 标准化：假设潜在增速 2-3%，>3% 为强劲，<1% 为放缓
            score = (data.gdp_growth - 2.0) / 2.0
            scores.append(max(-1, min(1, score)))
            weights.append(self._growth_weights["gdp"])
        
        # PMI（如果有）
        if data.pmi is not None:
            # 标准化：50 为荣枯线，>55 强劲，<45 收缩
            score = (data.pmi - 50.0) / 10.0
            scores.append(max(-1, min(1, score)))
            weights.append(self._growth_weights["pmi"])
        
        # 就业数据（如果有）
        if data.nonfarm_payrolls is not None or data.unemployment_rate is not None:
            if data.nonfarm_payrolls is not None:
                # 非农：>200k 强劲，<50k 疲软
                score = (data.nonfarm_payrolls - 100) / 150
                scores.append(max(-1, min(1, score)))
            if data.unemployment_rate is not None:
                # 失业率：<4% 强劲，>6% 疲软
                score = (5.0 - data.unemployment_rate) / 2.0
                scores.append(max(-1, min(1, score)))
            weights.append(self._growth_weights["employment"])
        
        # 零售销售（如果有）
        if data.retail_sales is not None:
            # 零售：>5% 强劲，<1% 疲软
            score = (data.retail_sales - 3.0) / 3.0
            scores.append(max(-1, min(1, score)))
            weights.append(self._growth_weights["retail"])
        
        # 工业产出（如果有）
        if data.industrial_production is not None:
            score = data.industrial_production / 3.0
            scores.append(max(-1, min(1, score)))
            weights.append(self._growth_weights["industrial"])
        
        if not scores:
            return 0.0
        
        # 加权平均
        total_weight = sum(weights[:len(scores)])
        if total_weight == 0:
            return 0.0
        
        weighted_score = sum(s * w for s, w in zip(scores, weights[:len(scores)]))
        return weighted_score / total_weight
    
    def _calculate_inflation_score(self, data: EconomicData) -> float:
        """
        计算通胀评分
        
        Returns:
            float: -1（通缩）到 1（高通胀）
        """
        scores = []
        weights = []
        
        # CPI（如果有）
        if data.cpi_yoy is not None:
            # 标准化：假设目标 2%，>3% 高通胀，<1% 通缩风险
            score = (data.cpi_yoy - 2.0) / 1.5
            scores.append(max(-1, min(1, score)))
            weights.append(self._inflation_weights["cpi"])
        
        # PCE（如果有）
        if data.pce_yoy is not None or data.core_pce_yoy is not None:
            pce = data.core_pce_yoy if data.core_pce_yoy is not None else data.pce_yoy
            # 美联储目标 2%，>3% 高，<1% 低
            score = (pce - 2.0) / 1.5
            scores.append(max(-1, min(1, score)))
            weights.append(self._inflation_weights["pce"])
        
        # PPI（如果有）
        if data.ppi_yoy is not None:
            score = (data.ppi_yoy - 2.5) / 2.0
            scores.append(max(-1, min(1, score)))
            weights.append(self._inflation_weights["ppi"])
        
        # TIPS 盈亏平衡（如果有）
        if data.tips_breakeven is not None:
            # 假设平衡通胀预期 2.5%
            score = (data.tips_breakeven - 2.5) / 1.0
            scores.append(max(-1, min(1, score)))
            weights.append(self._inflation_weights["tips"])
        
        if not scores:
            return 0.0
        
        # 加权平均
        total_weight = sum(weights[:len(scores)])
        if total_weight == 0:
            return 0.0
        
        weighted_score = sum(s * w for s, w in zip(scores, weights[:len(scores)]))
        return weighted_score / total_weight
    
    def _determine_phase(self, growth_score: float, inflation_score: float) -> MerrillClockPhase:
        """
        基于增长和通胀评分判断周期阶段
        
        美林时钟四象限：
        - 复苏：增长↑ 通胀↓
        - 过热：增长↑ 通胀↑
        - 滞胀：增长↓ 通胀↑
        - 衰退：增长↓ 通胀↓
        """
        if growth_score > self._growth_threshold and inflation_score < self._inflation_threshold:
            return MerrillClockPhase.RECOVERY    # 复苏
        elif growth_score > self._growth_threshold and inflation_score >= self._inflation_threshold:
            return MerrillClockPhase.OVERHEAT    # 过热
        elif growth_score <= self._growth_threshold and inflation_score >= self._inflation_threshold:
            return MerrillClockPhase.STAGFLATION # 滞胀
        else:
            return MerrillClockPhase.RECESSION   # 衰退
    
    def _calculate_confidence(self, growth_score: float, inflation_score: float, 
                             data_quality: float) -> float:
        """
        计算置信度
        
        考虑因素：
        1. 数据质量（数据完整性）
        2. 信号强度（增长和通胀评分的绝对值）
        3. 历史一致性（与历史判断是否一致）
        """
        # 数据质量权重 40%
        quality_component = data_quality * 0.4
        
        # 信号强度权重 40%
        signal_strength = (abs(growth_score) + abs(inflation_score)) / 2
        strength_component = min(1.0, signal_strength) * 0.4
        
        # 历史一致性权重 20%
        consistency_component = 0.2
        if self._current_phase and len(self._history) > 0:
            last_phase = self._history[-1].phase
            if last_phase == self._current_phase:
                consistency_component = 0.2  # 一致，满分
            else:
                # 不一致，根据变化幅度打折
                consistency_component = 0.1
        
        return quality_component + strength_component + consistency_component
    
    def _check_data_quality(self, data: EconomicData) -> float:
        """
        检查数据质量（完整性）
        
        Returns:
            float: 0-1，1 表示数据最完整
        """
        required_fields = [
            data.gdp_growth, data.pmi, data.cpi_yoy, data.pce_yoy,
            data.nonfarm_payrolls, data.retail_sales
        ]
        
        available = sum(1 for f in required_fields if f is not None)
        return available / len(required_fields)
    
    def _generate_allocation(self, phase: MerrillClockPhase, 
                            confidence: float) -> Dict[str, Any]:
        """
        生成资产配置建议
        
        基于美林时钟经典理论：
        - 复苏：股票 > 债券 > 现金 > 商品
        - 过热：商品 > 股票 > 现金 > 债券
        - 滞胀：现金 > 商品 > 债券 > 股票
        - 衰退：债券 > 现金 > 股票 > 商品
        """
        allocations = {
            MerrillClockPhase.RECOVERY: {
                "ranking": ["股票", "债券", "现金", "商品"],
                "overweight": ["科技股", "成长股", "周期股", "创业板"],
                "underweight": ["防御股", "公用事业", "必需消费"],
                "reason": "经济复苏，企业盈利改善，股票最佳；债券受益于低通胀"
            },
            MerrillClockPhase.OVERHEAT: {
                "ranking": ["商品", "股票", "现金", "债券"],
                "overweight": ["能源", "工业金属", "资源股", "大宗商品"],
                "underweight": ["债券", "高估值成长股", "公用事业"],
                "reason": "经济过热，通胀上升，商品最佳；股票分化，周期股优于成长股"
            },
            MerrillClockPhase.STAGFLATION: {
                "ranking": ["现金", "商品", "债券", "股票"],
                "overweight": ["货币基金", "短期债券", "黄金", "能源"],
                "underweight": ["股票", "长期债券", "高收益债"],
                "reason": "滞胀环境，现金为王；黄金抗通胀，股票债券双杀"
            },
            MerrillClockPhase.RECESSION: {
                "ranking": ["债券", "现金", "股票", "商品"],
                "overweight": ["国债", "投资级债", "防御股", "必需消费"],
                "underweight": ["周期股", "商品", "高收益债", "金融股"],
                "reason": "经济衰退，债券最佳；降息预期利好债券，股票防御为主"
            },
        }
        
        allocation = allocations[phase]
        
        # 根据置信度调整语气
        if confidence < 0.5:
            allocation["reason"] += f"（置信度较低：{confidence:.0%}，建议谨慎）"
        
        return allocation
    
    def _summarize_data(self, data: EconomicData) -> Dict[str, Any]:
        """生成经济数据摘要"""
        summary = {}
        
        if data.gdp_growth is not None:
            summary["GDP"] = f"{data.gdp_growth:.1f}%"
        if data.pmi is not None:
            summary["PMI"] = f"{data.pmi:.1f}"
        if data.cpi_yoy is not None:
            summary["CPI"] = f"{data.cpi_yoy:.1f}%"
        if data.pce_yoy is not None:
            summary["PCE"] = f"{data.pce_yoy:.1f}%"
        if data.nonfarm_payrolls is not None:
            summary["非农"] = f"{data.nonfarm_payrolls}k"
        if data.unemployment_rate is not None:
            summary["失业率"] = f"{data.unemployment_rate:.1f}%"
        
        return summary
    
    def _emit_signal(self, signal: PhaseSignal) -> None:
        """
        发布周期信号
        
        信号存储在 MerrillClockEngine._current_signal 中，
        需要读取的模块直接调用 get_merrill_clock_engine().get_current_signal()
        即可获取当前最新信号。
        """
        # 存储到 NB 供持久化查询
        try:
            from deva import NB
            db = NB("naja_merrill_clock_latest")
            db["latest"] = signal.to_dict()
            log.debug(f"[MerrillClockEngine] 信号已存储到 NB：{signal.phase.value}")
        except Exception as e:
            log.debug(f"[MerrillClockEngine] 信号存储失败（非致命）：{e}")
    
    def get_current_phase(self) -> Optional[MerrillClockPhase]:
        """获取当前周期阶段"""
        return self._current_phase
    
    def get_current_signal(self) -> Optional[PhaseSignal]:
        """获取当前信号（优先内存，兜底 NB 持久化）"""
        # 优先返回内存中的信号
        if self._current_signal is not None:
            return self._current_signal

        # 兜底：从 NB 读取持久化的信号
        try:
            from deva import NB
            db = NB("naja_merrill_clock_latest")
            data = db.get("latest")
            if data:
                signal = PhaseSignal.from_dict(data)
                # 恢复到内存
                self._current_signal = signal
                self._current_phase = signal.phase
                log.debug(f"[MerrillClockEngine] 从 NB 恢复信号：{signal.phase.value}")
                return signal
        except Exception:
            pass

        return None
    
    def get_history(self, limit: int = 10) -> List[PhaseSignal]:
        """获取历史记录"""
        return self._history[-limit:]
    
    def get_summary(self) -> Dict[str, Any]:
        """获取摘要信息"""
        if not self._current_signal:
            return {
                "status": "no_data",
                "message": "暂无经济数据",
            }
        
        return {
            "status": "active",
            "phase": self._current_phase.value,
            "confidence": round(self._current_signal.confidence, 3),
            "growth_score": round(self._current_signal.growth_score, 3),
            "inflation_score": round(self._current_signal.inflation_score, 3),
            "asset_ranking": self._current_signal.asset_ranking,
            "last_update": self._last_update,
            "history_count": len(self._history),
        }


# 单例管理
_merrill_clock_engine: Optional[MerrillClockEngine] = None


def get_merrill_clock_engine() -> MerrillClockEngine:
    """获取美林时钟引擎单例"""
    global _merrill_clock_engine
    if _merrill_clock_engine is None:
        _merrill_clock_engine = MerrillClockEngine()
    return _merrill_clock_engine


def initialize_merrill_clock(config: Optional[Dict[str, Any]] = None) -> MerrillClockEngine:
    """初始化美林时钟引擎"""
    global _merrill_clock_engine
    _merrill_clock_engine = MerrillClockEngine(config)
    return _merrill_clock_engine
