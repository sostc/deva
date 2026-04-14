"""Cognition Bridge - 统一认知能力访问接口

提供标准化的认知能力访问接口，整合现有认知接入点，
确保 ManasEngine 和 TradingCenter 能够协调一致地使用认知能力。
"""

from typing import Dict, List, Any, Optional
from deva.naja.register import SR

# 导入持久化模块
try:
    from .persistence import get_cognitive_persistence
    PERSISTENCE_AVAILABLE = True
except ImportError:
    PERSISTENCE_AVAILABLE = False


class CognitionBridge:
    """统一认知能力访问接口"""
    
    def __init__(self):
        """初始化认知桥接器"""
        self._liquidity_analyzer = None
        self._topic_analyzer = None
        self._drift_detector = None
        self._merrill_clock = None
        self._narrative_tracker = None
        self._cross_signal_analyzer = None
        self._persistence = None
    
    def _get_persistence(self):
        """获取持久化实例"""
        if not PERSISTENCE_AVAILABLE:
            return None
        if self._persistence is None:
            self._persistence = get_cognitive_persistence()
        return self._persistence
    
    def get_liquidity_state(self) -> Dict[str, Any]:
        """获取流动性状态
        
        Returns:
            Dict[str, Any]: 流动性状态信息，包含流动性风险评估等
        """
        try:
            if self._liquidity_analyzer is None:
                from .liquidity import LiquidityAnalyzer
                self._liquidity_analyzer = LiquidityAnalyzer()
            state = self._liquidity_analyzer.get_state()
            
            # 持久化状态
            persistence = self._get_persistence()
            if persistence:
                persistence.save_state('liquidity', state, importance=0.8)
            
            return state
        except Exception as e:
            print(f"[CognitionBridge] 获取流动性状态失败: {e}")
            return {"error": str(e), "liquidity_risk": 0.5}
    
    def get_active_topics(self) -> List[Dict[str, Any]]:
        """获取活跃主题
        
        Returns:
            List[Dict[str, Any]]: 活跃主题列表，包含主题名称、热度等
        """
        try:
            if self._topic_analyzer is None:
                from .analysis import TopicAnalyzer
                self._topic_analyzer = TopicAnalyzer()
            topics = self._topic_analyzer.get_active_topics()
            
            # 持久化状态
            persistence = self._get_persistence()
            if persistence:
                persistence.save_state('topics', {"active_topics": topics}, importance=0.7)
            
            return topics
        except Exception as e:
            print(f"[CognitionBridge] 获取活跃主题失败: {e}")
            return []
    
    def get_drift_status(self) -> Dict[str, Any]:
        """获取漂移检测状态
        
        Returns:
            Dict[str, Any]: 漂移检测状态，包含漂移风险评估等
        """
        try:
            if self._drift_detector is None:
                from .analysis import DriftDetector
                self._drift_detector = DriftDetector()
            status = self._drift_detector.get_status()
            
            # 持久化状态
            persistence = self._get_persistence()
            if persistence:
                persistence.save_state('drift', status, importance=0.6)
            
            return status
        except Exception as e:
            print(f"[CognitionBridge] 获取漂移检测状态失败: {e}")
            return {"error": str(e), "drift_risk": 0.0}
    
    def get_merrill_clock_state(self) -> Dict[str, Any]:
        """获取美林时钟状态
        
        Returns:
            Dict[str, Any]: 美林时钟状态，包含经济周期阶段等
        """
        try:
            if self._merrill_clock is None:
                from .merrill_clock import MerrillClock
                self._merrill_clock = MerrillClock()
            state = self._merrill_clock.get_state()
            
            # 持久化状态
            persistence = self._get_persistence()
            if persistence:
                persistence.save_state('merrill_clock', state, importance=0.7)
            
            return state
        except Exception as e:
            print(f"[CognitionBridge] 获取美林时钟状态失败: {e}")
            return {"error": str(e), "cycle_phase": "neutral"}
    
    def get_cross_signal_analysis(self, signals: List[Dict[str, Any]]) -> Dict[str, Any]:
        """执行跨信号分析
        
        Args:
            signals: 信号列表
            
        Returns:
            Dict[str, Any]: 跨信号分析结果，包含共振检测等
        """
        try:
            if self._cross_signal_analyzer is None:
                from .analysis.cross_signal_analyzer import CrossSignalAnalyzer
                self._cross_signal_analyzer = CrossSignalAnalyzer()
            result = self._cross_signal_analyzer.analyze(signals)
            
            # 持久化状态
            persistence = self._get_persistence()
            if persistence:
                persistence.save_state('cross_signal', result, importance=0.8)
            
            return result
        except Exception as e:
            print(f"[CognitionBridge] 执行跨信号分析失败: {e}")
            return {"error": str(e), "resonance_score": 0.0}
    
    def get_current_narratives(self) -> List[str]:
        """获取当前活跃叙事
        
        Returns:
            List[str]: 活跃叙事列表
        """
        try:
            if self._narrative_tracker is None:
                from .narrative import NarrativeTracker
                self._narrative_tracker = SR('narrative_tracker') or NarrativeTracker()
            summary = self._narrative_tracker.get_summary(limit=10)
            narratives = [item["narrative"] for item in summary]
            
            # 持久化状态
            persistence = self._get_persistence()
            if persistence:
                persistence.save_state('narratives', {"current_narratives": narratives}, importance=0.9)
            
            return narratives
        except Exception as e:
            print(f"[CognitionBridge] 获取当前叙事失败: {e}")
            return []
    
    def get_first_principles_insights(self, market_state: Dict[str, Any], snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
        """获取第一性原理洞察
        
        Args:
            market_state: 市场状态
            snapshot: 市场快照
            
        Returns:
            List[Dict[str, Any]]: 第一性原理洞察列表
        """
        try:
            from .analysis.first_principles_mind import FirstPrinciplesMind
            fp_mind = FirstPrinciplesMind()
            result = fp_mind.think(market_state, snapshot)
            insights = result.get("insights", [])
            
            # 持久化状态
            persistence = self._get_persistence()
            if persistence:
                persistence.save_state('first_principles', {
                    "insights": insights,
                    "market_state": market_state,
                    "snapshot": snapshot
                }, importance=0.9)
            
            return insights
        except Exception as e:
            print(f"[CognitionBridge] 获取第一性原理洞察失败: {e}")
            return []
    
    def get_awakened_alaya_insights(self, market_data: Dict[str, Any], manas_output: Dict[str, Any], fp_insights: List[Dict[str, Any]]) -> Dict[str, Any]:
        """获取觉醒阿赖耶洞察
        
        Args:
            market_data: 市场数据
            manas_output: ManasEngine 输出
            fp_insights: 第一性原理洞察
            
        Returns:
            Dict[str, Any]: 觉醒阿赖耶洞察
        """
        try:
            from deva.naja.knowledge.alaya.awakened_alaya import AwakenedAlaya
            alaya = AwakenedAlaya()
            result = alaya.illuminate(
                market_data=market_data,
                unified_manas_output=manas_output,
                fp_insights=fp_insights
            )
            
            # 持久化状态
            persistence = self._get_persistence()
            if persistence:
                persistence.save_state('awakened_alaya', result, importance=0.8)
            
            return result
        except Exception as e:
            print(f"[CognitionBridge] 获取觉醒阿赖耶洞察失败: {e}")
            return {"awakening_level": "dormant", "recalled_patterns": []}
    
    def get_state_history(self, state_type: str, limit: int = 100) -> List[Dict[str, Any]]:
        """获取状态历史
        
        Args:
            state_type: 状态类型
            limit: 限制数量
            
        Returns:
            状态历史列表
        """
        try:
            persistence = self._get_persistence()
            if persistence:
                return persistence.get_state_history(state_type, limit)
            return []
        except Exception as e:
            print(f"[CognitionBridge] 获取状态历史失败: {e}")
            return []
    
    def get_state_changes(self, state_type: str, limit: int = 50) -> List[Dict[str, Any]]:
        """获取状态变化历史
        
        Args:
            state_type: 状态类型
            limit: 限制数量
            
        Returns:
            状态变化历史列表
        """
        try:
            persistence = self._get_persistence()
            if persistence:
                return persistence.get_state_changes(state_type, limit)
            return []
        except Exception as e:
            print(f"[CognitionBridge] 获取状态变化失败: {e}")
            return []


# 单例模式
def get_cognition_bridge() -> CognitionBridge:
    """获取认知桥接器单例"""
    from deva.naja.register import SR
    bridge = SR('cognition_bridge')
    if bridge is None:
        bridge = CognitionBridge()
        SR('cognition_bridge', bridge)
    return bridge
