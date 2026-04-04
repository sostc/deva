"""
RiskManager - 风险系统/风险管理/风控

别名/关键词: 风险管理、风控、risk manager、仓位风险

觉醒系统的风控层，保护资产安全

核心能力：
1. PositionRiskMonitor: 持仓风险监控
2. MarketRiskDetector: 市场风险检测
3. RiskControlRules: 风控规则
4. AttentionOS 集成：动态风控阈值
"""

import time
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum

log = logging.getLogger(__name__)


class RiskLevel(Enum):
    """风险等级"""
    SAFE = "safe"           # 安全
    CAUTION = "caution"     # 谨慎
    WARNING = "warning"     # 警告
    DANGER = "danger"       # 危险
    CRITICAL = "critical"   # 极度危险


class RiskType(Enum):
    """风险类型"""
    SINGLE_POSITION = "single_position"     # 单票风险
    TOTAL_POSITION = "total_position"       # 总体仓位
    VOLATILITY = "volatility"               # 波动风险
    LIQUIDITY = "liquidity"                 # 流动性风险
    CONCENTRATION = "concentration"         # 集中度风险
    CORRELATION = "correlation"             # 相关性风险


@dataclass
class RiskAlert:
    """风险警报"""
    risk_type: RiskType
    level: RiskLevel
    description: str
    symbol: Optional[str]
    metrics: Dict[str, float]
    timestamp: float
    recommended_action: str


@dataclass
class RiskMetrics:
    """风险指标"""
    total_exposure: float          # 总敞口
    max_single_position: float     # 最大单票敞口
    volatility_score: float        # 波动率得分
    liquidity_score: float         # 流动性得分
    correlation_score: float      # 相关性得分
    overall_risk_score: float      # 综合风险得分
    risk_level: RiskLevel          # 风险等级


class PositionRiskMonitor:
    """
    持仓风险监控器
    """

    def __init__(self, max_single_position: float = 0.2):
        self.max_single_position = max_single_position
        self._position_history: List[Dict] = []

    def monitor(
        self,
        positions: Dict[str, Dict],
        total_assets: float
    ) -> List[RiskAlert]:
        """
        监控持仓风险

        Args:
            positions: 持仓字典 {symbol: {quantity, cost, current_price}}
            total_assets: 总资产

        Returns:
            风险警报列表
        """
        alerts = []

        if not positions:
            return alerts

        for symbol, pos in positions.items():
            alert = self._check_single_position(symbol, pos, total_assets)
            if alert:
                alerts.append(alert)

        total_alert = self._check_total_exposure(positions, total_assets)
        if total_alert:
            alerts.append(total_alert)

        concentration_alert = self._check_concentration(positions, total_assets)
        if concentration_alert:
            alerts.append(concentration_alert)

        return alerts

    def _check_single_position(
        self,
        symbol: str,
        position: Dict,
        total_assets: float
    ) -> Optional[RiskAlert]:
        """检查单票风险"""
        quantity = position.get("quantity", 0)
        cost = position.get("cost", 0)
        current_price = position.get("current_price", cost)

        if cost <= 0 or quantity <= 0:
            return None

        position_value = quantity * current_price
        exposure = position_value / total_assets if total_assets > 0 else 0

        if exposure > self.max_single_position:
            return RiskAlert(
                risk_type=RiskType.SINGLE_POSITION,
                level=RiskLevel.WARNING if exposure < 0.3 else RiskLevel.DANGER,
                description=f"{symbol} 仓位过重: {exposure:.1%}",
                symbol=symbol,
                metrics={"exposure": exposure, "threshold": self.max_single_position},
                timestamp=time.time(),
                recommended_action=f"建议减仓至 {self.max_single_position:.0%} 以内"
            )

        return None

    def _check_total_exposure(
        self,
        positions: Dict[str, Dict],
        total_assets: float
    ) -> Optional[RiskAlert]:
        """检查总敞口"""
        total_value = 0
        for pos in positions.values():
            qty = pos.get("quantity", 0)
            price = pos.get("current_price", pos.get("cost", 0))
            total_value += qty * price

        exposure = total_value / total_assets if total_assets > 0 else 0

        if exposure > 0.9:
            return RiskAlert(
                risk_type=RiskType.TOTAL_POSITION,
                level=RiskLevel.CRITICAL,
                description=f"总仓位过高: {exposure:.1%}",
                symbol=None,
                metrics={"total_exposure": exposure},
                timestamp=time.time(),
                recommended_action="建议立即降仓，保持 30-50% 现金"
            )
        elif exposure > 0.7:
            return RiskAlert(
                risk_type=RiskType.TOTAL_POSITION,
                level=RiskLevel.WARNING,
                description=f"总仓位偏高: {exposure:.1%}",
                symbol=None,
                metrics={"total_exposure": exposure},
                timestamp=time.time(),
                recommended_action="考虑适当降仓"
            )

        return None

    def _check_concentration(
        self,
        positions: Dict[str, Dict],
        total_assets: float
    ) -> Optional[RiskAlert]:
        """检查集中度风险"""
        if len(positions) < 3:
            return RiskAlert(
                risk_type=RiskType.CONCENTRATION,
                level=RiskLevel.CAUTION,
                description=f"持仓过于集中: 仅 {len(positions)} 只股票",
                symbol=None,
                metrics={"position_count": len(positions), "recommended": 5},
                timestamp=time.time(),
                recommended_action="建议分散至 5 只以上股票"
            )

        return None


class MarketRiskDetector:
    """
    市场风险检测器
    """

    def __init__(self):
        self._market_shocks: List[Dict] = []

    def detect(
        self,
        market_data: Dict[str, Any],
        market_state: Dict[str, Any]
    ) -> List[RiskAlert]:
        """
        检测市场风险

        Args:
            market_data: 市场数据
            market_state: 市场状态

        Returns:
            风险警报列表
        """
        alerts = []

        volatility_alert = self._check_volatility(market_data)
        if volatility_alert:
            alerts.append(volatility_alert)

        trend_alert = self._check_trend_risk(market_state)
        if trend_alert:
            alerts.append(trend_alert)

        breadth_alert = self._check_breadth_risk(market_state)
        if breadth_alert:
            alerts.append(breadth_alert)

        return alerts

    def _check_volatility(self, market_data: Dict[str, Any]) -> Optional[RiskAlert]:
        """检查波动率风险"""
        volatility = market_data.get("market_volatility", 0)

        if volatility > 2.5:
            return RiskAlert(
                risk_type=RiskType.VOLATILITY,
                level=RiskLevel.CRITICAL,
                description=f"市场波动率极高: {volatility:.1f}",
                symbol=None,
                metrics={"volatility": volatility, "threshold": 2.5},
                timestamp=time.time(),
                recommended_action="建议清仓或极低仓位运行"
            )
        elif volatility > 2.0:
            return RiskAlert(
                risk_type=RiskType.VOLATILITY,
                level=RiskLevel.WARNING,
                description=f"市场波动率偏高: {volatility:.1f}",
                symbol=None,
                metrics={"volatility": volatility, "threshold": 2.0},
                timestamp=time.time(),
                recommended_action="建议降低仓位至 30% 以内"
            )

        return None

    def _check_trend_risk(self, market_state: Dict[str, Any]) -> Optional[RiskAlert]:
        """检查趋势风险"""
        trend_strength = market_state.get("trend_strength", 0)

        if abs(trend_strength) > 0.8:
            return RiskAlert(
                risk_type=RiskType.VOLATILITY,
                level=RiskLevel.CAUTION,
                description=f"趋势强度极高: {trend_strength:.1%}",
                symbol=None,
                metrics={"trend_strength": trend_strength},
                timestamp=time.time(),
                recommended_action="注意趋势反转风险"
            )

        return None

    def _check_breadth_risk(self, market_state: Dict[str, Any]) -> Optional[RiskAlert]:
        """检查广度风险"""
        breadth = market_state.get("market_breadth", 0)

        if abs(breadth) > 0.6:
            return RiskAlert(
                risk_type=RiskType.VOLATILITY,
                level=RiskLevel.WARNING,
                description=f"市场广度极端: {breadth:.1%}",
                symbol=None,
                metrics={"breadth": breadth},
                timestamp=time.time(),
                recommended_action="市场可能即将反转"
            )

        return None


class RiskControlRules:
    """
    风控规则引擎
    """

    def __init__(self):
        self._rules: List[Dict] = self._init_default_rules()

    def _init_default_rules(self) -> List[Dict]:
        """初始化默认规则"""
        return [
            {
                "name": "单票仓位上限",
                "type": RiskType.SINGLE_POSITION,
                "threshold": 0.2,
                "action": "warn"
            },
            {
                "name": "总仓位上限",
                "type": RiskType.TOTAL_POSITION,
                "threshold": 0.8,
                "action": "force_close"
            },
            {
                "name": "日亏损止损",
                "type": RiskType.VOLATILITY,
                "threshold": 0.05,
                "action": "stop"
            }
        ]

    def check_rules(
        self,
        positions: Dict[str, Dict],
        market_data: Dict[str, Any],
        daily_pnl: float
    ) -> List[RiskAlert]:
        """检查风控规则"""
        alerts = []

        for rule in self._rules:
            alert = self._evaluate_rule(rule, positions, market_data, daily_pnl)
            if alert:
                alerts.append(alert)

        return alerts

    def _evaluate_rule(
        self,
        rule: Dict,
        positions: Dict[str, Dict],
        market_data: Dict[str, Any],
        daily_pnl: float
    ) -> Optional[RiskAlert]:
        """评估单条规则"""
        rule_type = rule["type"]

        if rule_type == RiskType.SINGLE_POSITION and positions:
            max_exposure = max(
                (pos.get("quantity", 0) * pos.get("current_price", 0)) / market_data.get("total_assets", 1)
                for pos in positions.values()
            )
            if max_exposure > rule["threshold"]:
                return RiskAlert(
                    risk_type=rule_type,
                    level=RiskLevel.WARNING,
                    description=f"{rule['name']}: {max_exposure:.1%} > {rule['threshold']:.0%}",
                    symbol=None,
                    metrics={"exposure": max_exposure, "threshold": rule["threshold"]},
                    timestamp=time.time(),
                    recommended_action=self._get_action_text(rule["action"])
                )

        elif rule_type == RiskType.VOLATILITY:
            if abs(daily_pnl) > rule["threshold"]:
                return RiskAlert(
                    risk_type=rule_type,
                    level=RiskLevel.CRITICAL,
                    description=f"{rule['name']}: 亏损 {abs(daily_pnl):.1%}",
                    symbol=None,
                    metrics={"daily_pnl": daily_pnl, "threshold": rule["threshold"]},
                    timestamp=time.time(),
                    recommended_action=self._get_action_text(rule["action"])
                )

        return None

    def _get_action_text(self, action: str) -> str:
        """获取动作文本"""
        action_map = {
            "warn": "警告：注意风险",
            "force_close": "强制平仓",
            "stop": "停止交易"
        }
        return action_map.get(action, "注意风险")


class RiskManager:
    """
    风险管理器（觉醒系统的风控层）

    整合持仓监控、市场检测、风控规则
    支持 AttentionOS 集成：动态风控阈值
    """

    def __init__(self):
        self.position_monitor = PositionRiskMonitor()
        self.market_detector = MarketRiskDetector()
        self.rules_engine = RiskControlRules()
        self._alert_history: List[RiskAlert] = []
        
        # AttentionOS 集成
        self._attention_cache: Dict[str, Any] = {}
        self._attention_cache_ts: float = 0.0
        self._attention_cache_ttl: float = 5.0  # 缓存有效期（秒）
    
    def _get_attention_context(self) -> Dict[str, Any]:
        """获取 AttentionOS 上下文（带缓存）"""
        now = time.time()
        
        if now - self._attention_cache_ts < self._attention_cache_ttl and self._attention_cache:
            return self._attention_cache
        
        try:
            from deva.naja.attention.attention_os import get_attention_os
            aos = get_attention_os()
            kernel = aos.get_kernel()
            
            risk_temp = getattr(kernel.get_latest_output(), 'risk_temperature', 1.0)
            harmony = kernel.get_harmony()
            
            self._attention_cache = {
                "risk_temperature": risk_temp,
                "harmony_state": harmony.get("state", "neutral"),
                "harmony_strength": harmony.get("strength", 0.5),
                "focus_symbols": list(kernel.get_focus_weights().keys())[:5],
            }
            self._attention_cache_ts = now
            
        except Exception as e:
            log.warning(f"[RiskManager] 获取 AttentionOS 上下文失败: {e}")
            self._attention_cache = {
                "risk_temperature": 1.0,
                "harmony_state": "neutral",
                "harmony_strength": 0.5,
                "focus_symbols": [],
            }
        
        return self._attention_cache
    
    def _get_adaptive_thresholds(self, context: Dict[str, Any]) -> Dict[str, float]:
        """根据 AttentionOS 上下文计算自适应风控阈值
        
        - 高风险（risk_temp > 1.3）：收紧阈值，更保守
        - 低风险（risk_temp < 0.8）：放宽阈值，更激进
        - 和谐状态好：适度放宽
        - 和谐状态差：收紧
        """
        risk_temp = context.get("risk_temperature", 1.0)
        harmony_strength = context.get("harmony_strength", 0.5)
        
        # 基础缩放因子
        base_scale = 1.0
        
        # 风险温度调整
        if risk_temp > 1.5:
            base_scale *= 0.6  # 极度高风险，收紧 40%
        elif risk_temp > 1.3:
            base_scale *= 0.75  # 高风险，收紧 25%
        elif risk_temp < 0.7:
            base_scale *= 1.2  # 低风险，放宽 20%
        elif risk_temp < 0.85:
            base_scale *= 1.1  # 较低风险，放宽 10%
        
        # 和谐状态调整（只在非极端情况下生效）
        if 0.7 <= risk_temp <= 1.3:
            if harmony_strength > 0.7:
                base_scale *= 1.05  # 和谐，放宽 5%
            elif harmony_strength < 0.3:
                base_scale *= 0.9  # 不和谐，收紧 10%
        
        return {
            "single_position_scale": base_scale,
            "total_exposure_scale": base_scale,
            "volatility_scale": base_scale,
            "stop_loss_scale": base_scale if risk_temp > 1.3 else 1.0,
        }

    def assess_risk(
        self,
        positions: Dict[str, Dict],
        market_data: Dict[str, Any],
        market_state: Dict[str, Any],
        total_assets: float,
        daily_pnl: float = 0
    ) -> RiskMetrics:
        """
        评估风险（AttentionOS 感知）

        Returns:
            风险指标
        """
        # 获取 AttentionOS 上下文
        attn_context = self._get_attention_context()
        thresholds = self._get_adaptive_thresholds(attn_context)
        
        alerts = []

        # 持仓监控（使用自适应阈值）
        position_alerts = self._monitor_with_thresholds(
            positions, total_assets, thresholds
        )
        alerts.extend(position_alerts)

        # 市场检测（使用自适应阈值）
        market_alerts = self._detect_with_thresholds(
            market_data, market_state, thresholds
        )
        alerts.extend(market_alerts)

        # 规则检查
        rule_alerts = self.rules_engine.check_rules(
            positions, {"total_assets": total_assets, **market_data}, daily_pnl
        )
        alerts.extend(rule_alerts)

        self._alert_history.extend(alerts)
        if len(self._alert_history) > 100:
            self._alert_history = self._alert_history[-100:]

        overall_score = self._calculate_overall_score(alerts)

        # 记录 AttentionOS 影响
        risk_temp = attn_context["risk_temperature"]
        log.info(f"[RiskManager] 风险评估: score={overall_score:.2f}, "
                f"risk_temp={risk_temp:.2f}, harmony={attn_context['harmony_state']}, "
                f"threshold_scale={thresholds['single_position_scale']:.2f}")

        return RiskMetrics(
            total_exposure=self._calculate_total_exposure(positions),
            max_single_position=self._calculate_max_single(positions, total_assets),
            volatility_score=market_data.get("market_volatility", 1.0) / 3.0,
            liquidity_score=market_data.get("liquidity_score", 0.8),
            correlation_score=0.5,
            overall_risk_score=overall_score,
            risk_level=self._score_to_level(overall_score)
        )
    
    def _monitor_with_thresholds(
        self,
        positions: Dict[str, Dict],
        total_assets: float,
        thresholds: Dict[str, float]
    ) -> List[RiskAlert]:
        """使用自适应阈值监控持仓"""
        alerts = []
        
        if not positions:
            return alerts
        
        scale = thresholds.get("single_position_scale", 1.0)
        # 动态调整单票上限
        dynamic_max = self.position_monitor.max_single_position * scale
        
        for symbol, pos in positions.items():
            alert = self._check_single_position_with_threshold(
                symbol, pos, total_assets, dynamic_max
            )
            if alert:
                alerts.append(alert)
        
        total_scale = thresholds.get("total_exposure_scale", 1.0)
        total_alert = self._check_total_exposure_with_threshold(
            positions, total_assets, total_scale
        )
        if total_alert:
            alerts.append(total_alert)
        
        return alerts
    
    def _check_single_position_with_threshold(
        self,
        symbol: str,
        position: Dict,
        total_assets: float,
        dynamic_max: float
    ) -> Optional[RiskAlert]:
        """检查单票风险（带动态阈值）"""
        quantity = position.get("quantity", 0)
        cost = position.get("cost", 0)
        current_price = position.get("current_price", cost)
        
        if cost <= 0 or quantity <= 0:
            return None
        
        position_value = quantity * current_price
        exposure = position_value / total_assets if total_assets > 0 else 0
        
        if exposure > dynamic_max:
            return RiskAlert(
                risk_type=RiskType.SINGLE_POSITION,
                level=RiskLevel.WARNING if exposure < 0.3 else RiskLevel.DANGER,
                description=f"{symbol} 仓位过重（Attention调整后）: {exposure:.1%}",
                symbol=symbol,
                metrics={"exposure": exposure, "threshold": dynamic_max, "attention_adjusted": True},
                timestamp=time.time(),
                recommended_action=f"建议减仓至 {dynamic_max:.0%} 以内"
            )
        
        return None
    
    def _check_total_exposure_with_threshold(
        self,
        positions: Dict[str, Dict],
        total_assets: float,
        scale: float
    ) -> Optional[RiskAlert]:
        """检查总敞口（带动态阈值）"""
        total_value = sum(
            pos.get("quantity", 0) * pos.get("current_price", pos.get("cost", 0))
            for pos in positions.values()
        )
        
        exposure = total_value / total_assets if total_assets > 0 else 0
        
        # 动态阈值
        critical_threshold = 0.9 * scale
        warning_threshold = 0.7 * scale
        
        if exposure > critical_threshold:
            return RiskAlert(
                risk_type=RiskType.TOTAL_POSITION,
                level=RiskLevel.CRITICAL,
                description=f"总仓位过高（Attention调整后）: {exposure:.1%}",
                symbol=None,
                metrics={"total_exposure": exposure, "threshold": critical_threshold},
                timestamp=time.time(),
                recommended_action="建议立即降仓，保持 30-50% 现金"
            )
        elif exposure > warning_threshold:
            return RiskAlert(
                risk_type=RiskType.TOTAL_POSITION,
                level=RiskLevel.WARNING,
                description=f"总仓位偏高（Attention调整后）: {exposure:.1%}",
                symbol=None,
                metrics={"total_exposure": exposure, "threshold": warning_threshold},
                timestamp=time.time(),
                recommended_action="考虑适当降仓"
            )
        
        return None
    
    def _detect_with_thresholds(
        self,
        market_data: Dict[str, Any],
        market_state: Dict[str, Any],
        thresholds: Dict[str, float]
    ) -> List[RiskAlert]:
        """使用自适应阈值检测市场风险"""
        alerts = []
        vol_scale = thresholds.get("volatility_scale", 1.0)
        
        # 动态调整波动率阈值
        volatility = market_data.get("market_volatility", 0)
        
        # 高风险时，收紧波动率阈值
        critical_vol = 2.5 / vol_scale if vol_scale < 1 else 2.5
        warning_vol = 2.0 / vol_scale if vol_scale < 1 else 2.0
        
        if volatility > critical_vol:
            alerts.append(RiskAlert(
                risk_type=RiskType.VOLATILITY,
                level=RiskLevel.CRITICAL,
                description=f"市场波动率极高（Attention调整）: {volatility:.1f}",
                symbol=None,
                metrics={"volatility": volatility, "threshold": critical_vol, "attention_adjusted": True},
                timestamp=time.time(),
                recommended_action="建议清仓或极低仓位运行"
            ))
        elif volatility > warning_vol:
            alerts.append(RiskAlert(
                risk_type=RiskType.VOLATILITY,
                level=RiskLevel.WARNING,
                description=f"市场波动率偏高（Attention调整）: {volatility:.1f}",
                symbol=None,
                metrics={"volatility": volatility, "threshold": warning_vol, "attention_adjusted": True},
                timestamp=time.time(),
                recommended_action="建议降低仓位至 30% 以内"
            ))
        
        # 趋势和广度检查（保持原有逻辑）
        trend_alert = self.market_detector._check_trend_risk(market_state)
        if trend_alert:
            alerts.append(trend_alert)
        
        breadth_alert = self.market_detector._check_breadth_risk(market_state)
        if breadth_alert:
            alerts.append(breadth_alert)
        
        return alerts

    def _calculate_total_exposure(self, positions: Dict[str, Dict]) -> float:
        """计算总敞口"""
        return sum(
            pos.get("quantity", 0) * pos.get("current_price", 0)
            for pos in positions.values()
        )

    def _calculate_max_single(self, positions: Dict[str, Dict], total: float) -> float:
        """计算最大单票"""
        if not positions or total <= 0:
            return 0
        return max(
            pos.get("quantity", 0) * pos.get("current_price", 0) / total
            for pos in positions.values()
        )

    def _calculate_overall_score(self, alerts: List[RiskAlert]) -> float:
        """计算综合风险得分"""
        if not alerts:
            return 0.2

        level_scores = {
            RiskLevel.SAFE: 0,
            RiskLevel.CAUTION: 0.2,
            RiskLevel.WARNING: 0.5,
            RiskLevel.DANGER: 0.7,
            RiskLevel.CRITICAL: 1.0
        }

        max_score = max(level_scores[a.level] for a in alerts)
        return max_score

    def _score_to_level(self, score: float) -> RiskLevel:
        """得分转等级"""
        if score < 0.2:
            return RiskLevel.SAFE
        elif score < 0.4:
            return RiskLevel.CAUTION
        elif score < 0.6:
            return RiskLevel.WARNING
        elif score < 0.8:
            return RiskLevel.DANGER
        else:
            return RiskLevel.CRITICAL

    def get_recent_alerts(self) -> List[RiskAlert]:
        """获取最近警报"""
        return list(self._alert_history[-10:])

    def get_alert_summary(self) -> Dict[str, Any]:
        """获取警报摘要"""
        if not self._alert_history:
            return {"total": 0, "by_level": {}, "by_type": {}}

        by_level = {}
        by_type = {}

        for a in self._alert_history:
            by_level[a.level.value] = by_level.get(a.level.value, 0) + 1
            by_type[a.risk_type.value] = by_type.get(a.risk_type.value, 0) + 1

        return {
            "total": len(self._alert_history),
            "by_level": by_level,
            "by_type": by_type
        }