"""
OpenRouter 监控 - Manas 集成

与 Manas 系统集成，处理 Manas 系统的交互
"""

from typing import Dict, Optional


class OpenRouterManasIntegration:
    """OpenRouter Manas 集成模块"""

    def __init__(self):
        self.manas_system = None
        self._initialize_manas()

    def _initialize_manas(self):
        """初始化 Manas 系统"""
        try:
            # 从 attention/kernel 目录导入 ManasEngine
            from deva.naja.attention.kernel.manas_engine import ManasEngine
            self.manas_system = ManasEngine()
        except Exception as e:
            print(f"[OpenRouter Manas] 初始化 Manas 系统失败: {e}")

    def update_manas_config(self, trend_data: Dict):
        """更新 Manas 系统配置

        Args:
            trend_data: 趋势分析结果
        """
        if not self.manas_system or not trend_data:
            return

        try:
            # 基于趋势数据更新 Manas 系统状态
            # ManasEngine 通过供应链状态来管理 AI 算力趋势
            direction = trend_data.get("direction", "unknown")
            strength = trend_data.get("strength", 0)
            alert_level = trend_data.get("alert_level", "normal")

            # 构建 AI 算力趋势信息
            ai_compute_trend = "up" if direction in ["up", "strong_up"] else "down" if direction in ["down", "strong_down"] else "neutral"
            ai_compute_strength = strength

            # 更新 ManasEngine 的供应链状态
            # 注意：ManasEngine 通过事件驱动方式更新状态
            # 这里我们直接更新内部状态
            if hasattr(self.manas_system, '_supply_chain_state'):
                self.manas_system._supply_chain_state.update({
                    "ai_compute_trend": ai_compute_trend,
                    "ai_compute_strength": ai_compute_strength
                })
                print(f"[OpenRouter Manas] 更新 Manas AI 算力趋势: {ai_compute_trend} - {ai_compute_strength:.2f}")

        except Exception as e:
            print(f"[OpenRouter Manas] 更新 Manas 配置失败: {e}")

    def get_manas_insights(self) -> Optional[Dict]:
        """获取 Manas 系统的洞察

        Returns:
            Manas 系统的洞察
        """
        if not self.manas_system:
            return None

        try:
            # 从 ManasEngine 获取 AI 算力相关的洞察
            # 通过访问供应链状态获取信息
            if hasattr(self.manas_system, '_supply_chain_state'):
                supply_chain_state = self.manas_system._supply_chain_state
                return {
                    "ai_compute_trend": supply_chain_state.get("ai_compute_trend", "neutral"),
                    "ai_compute_strength": supply_chain_state.get("ai_compute_strength", 0.5),
                    "narrative_risk": supply_chain_state.get("narrative_risk", 0.5),
                    "hot_narratives": supply_chain_state.get("hot_narratives", []),
                    "risk_level": supply_chain_state.get("risk_level", "LOW")
                }
            return None
        except Exception as e:
            print(f"[OpenRouter Manas] 获取 Manas 洞察失败: {e}")
            return None
