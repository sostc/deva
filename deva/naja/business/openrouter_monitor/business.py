"""
OpenRouter 监控 - 业务模块主类

协调各层次的工作，提供对外接口
"""

import asyncio
from typing import Dict, Optional, List
from datetime import datetime

from .感知层.data_fetcher import OpenRouterDataFetcher
from .认知层.trend_analyzer import OpenRouterTrendAnalyzer
from .决策层.decision import OpenRouterDecisionMaker
from .觉醒层.awakening import OpenRouterAwakening
from .事件总线集成.event_bus import OpenRouterEventBus
from .manas集成.manas_integration import OpenRouterManasIntegration

TREND_TABLE = "openrouter_trend"


class OpenRouterMonitor:
    """OpenRouter 监控业务模块"""

    def __init__(self):
        """初始化 OpenRouter 监控模块"""
        self.data_fetcher = OpenRouterDataFetcher()
        self.trend_analyzer = OpenRouterTrendAnalyzer()
        self.decision_maker = OpenRouterDecisionMaker()
        self.awakening = OpenRouterAwakening()
        self.event_bus = OpenRouterEventBus()
        self.manas_integration = OpenRouterManasIntegration()

    async def refresh_openrouter_data(self) -> Optional[Dict]:
        """刷新 OpenRouter 数据并返回趋势分析结果

        供外部调用的主要接口
        """
        print("[OpenRouter] 开始获取数据...")

        weekly_data = await self.data_fetcher.fetch_weekly_data()
        if not weekly_data:
            print("[OpenRouter] 数据获取失败")
            return None

        print(f"[OpenRouter] 获取到 {len(weekly_data)} 周数据")

        trend_data = self.trend_analyzer.analyze_trend(weekly_data)

        self.save_trend_data(trend_data, weekly_data)

        self._update_radar_thread(trend_data)

        # 发布事件到事件总线
        self.event_bus.publish_ai_compute_trend(trend_data)

        # 更新 Manas 配置
        self.manas_integration.update_manas_config(trend_data)

        # 发送到雷达（如果需要）
        if trend_data.get("alert_level") in ["warning", "critical"]:
            self.send_to_radar(trend_data)

        return trend_data

    def save_trend_data(self, trend_data: Dict, weekly_data: List[Dict]):
        """保存趋势数据到 NB 表"""
        try:
            from deva import NB

            db = NB(TREND_TABLE)

            save_data = {
                "timestamp": datetime.now().isoformat(),
                "trend": trend_data,
                "weekly_history": [
                    {
                        "date": w["date"],
                        "total": w["total"],
                        "total_formatted": self.trend_analyzer.format_tokens(w["total"])
                    }
                    for w in weekly_data[-10:]
                ],
                "raw_data": weekly_data[-4:] if len(weekly_data) >= 4 else weekly_data
            }

            db["latest"] = save_data
            db["trend"] = trend_data

            print(f"[OpenRouter] 数据已保存到 {TREND_TABLE} 表")

        except Exception as e:
            print(f"[OpenRouter] 数据保存失败: {e}")

    def send_to_radar(self, trend_data: Dict):
        """发送事件到雷达"""
        try:
            from deva.naja.radar.engine import get_radar_engine

            radar = get_radar_engine()
            if not radar:
                return

            score_map = {
                "critical": 0.9,
                "warning": 0.7,
                "attention": 0.5,
                "normal": 0.3
            }

            radar.ingest_result({
                "event_type": "openrouter_trend",
                "score": score_map.get(trend_data.get("alert_level", "normal"), 0.5),
                "message": f"{trend_data.get('message', '')}\n{trend_data.get('recommendation', '')}",
                "payload": trend_data,
                "signal_type": "openrouter_trend",
                "strategy_id": "openrouter_monitor",
                "strategy_name": "OpenRouter TOKEN 监控"
            })

            print(f"[OpenRouter] 雷达事件已发送")

        except Exception as e:
            print(f"[OpenRouter] 雷达发送失败: {e}")

    def _update_radar_thread(self, trend_data: Dict) -> None:
        """更新雷达监控脉络"""
        try:
            from deva.naja.radar.engine import RadarThread, get_radar_engine

            radar = get_radar_engine()

            thread = RadarThread(
                thread_id="openrouter_token",
                name="OpenRouter TOKEN 监控",
                description="全球 AI 算力 TOKEN 消耗趋势",
                category="AI算力",
                update_frequency="每周",
                update_interval_seconds=604800.0,
                last_update_ts=datetime.now().timestamp(),
                last_status=trend_data.get("message", ""),
                alert_level=trend_data.get("alert_level", "normal"),
                score=trend_data.get("strength", 0) * 100,
                icon="🤖",
                thread_type="consumer",
            )

            radar.register_thread(thread)

        except Exception as e:
            print(f"[OpenRouter] 脉络更新失败: {e}")

    def get_openrouter_trend(self) -> Optional[Dict]:
        """获取缓存的 OpenRouter 趋势数据

        供其他模块查询使用
        """
        try:
            from deva import NB

            db = NB(TREND_TABLE)
            trend = db.get("trend")

            if trend:
                print(f"[OpenRouter] 从缓存获取趋势数据: {trend.get('message', '')[:50]}...")
            else:
                print("[OpenRouter] 缓存中无数据")

            return trend

        except Exception as e:
            print(f"[OpenRouter] 获取缓存失败: {e}")
            return None

    def get_openrouter_full_data(self) -> Optional[Dict]:
        """获取完整的 OpenRouter 数据（包含历史）"""
        try:
            from deva import NB

            db = NB(TREND_TABLE)
            data = db.get("latest")

            if data:
                print(f"[OpenRouter] 获取完整数据: {data.get('timestamp', '')}")
            else:
                print("[OpenRouter] 缓存中无数据")

            return data

        except Exception as e:
            print(f"[OpenRouter] 获取缓存失败: {e}")
            return None

    def get_ai_compute_trend(self) -> Optional[Dict]:
        """获取 AI算力趋势信号（供认知系统使用）

        这个函数返回完整的趋势背景信息，不只是异常告警。
        用于识别"基本面强但价格弱"的背离机会。

        Returns:
            {
                "signal_type": "ai_compute_trend",
                "cumulative_growth": 2.15,      # 累计增长率 (215%)
                "weekly_growth": 0.08,          # 周环比增长率
                "weekly_growth_rate": 0.15,      # 周环比变化率
                "total_tokens": 1_500_000_000_000,
                "trend_direction": "rising",     # rising / falling / stable
                "alert_level": "normal",         # 异常检测
                "is_abnormal": False,
                "related_blocks": ["AI算力", "半导体"],
                "related_symbols": ["NVDA", "AMD", "台积电"],
                "timestamp": ...,
                "message": "...",
                "recommendation": "...",
                "base_strength": 0.85,          # 基础算力需求强度 (0-1)
                "is_incomplete_week": False
            }
        """
        try:
            from deva import NB

            db = NB(TREND_TABLE)
            data = db.get("latest")
            trend = db.get("trend")

            if not data or not trend:
                return None

            weekly_history = data.get("weekly_history", [])

            cumulative_growth = 0.0
            if len(weekly_history) >= 2:
                oldest_total = weekly_history[0]["total"]
                latest_total = weekly_history[-1]["total"]
                if oldest_total > 0:
                    cumulative_growth = (latest_total - oldest_total) / oldest_total

            weekly_growth = trend.get("latest_change", 0) / 100.0
            weekly_growth_rate = trend.get("acceleration", 0) / 100.0

            direction = trend.get("direction", "unknown")
            trend_direction_map = {
                "strong_up": "rising",
                "up": "rising",
                "down": "falling",
                "strong_down": "falling",
                "unknown": "stable"
            }
            trend_direction = trend_direction_map.get(direction, "stable")

            base_strength = trend.get("strength", 0.5)

            return {
                "signal_type": "ai_compute_trend",
                "cumulative_growth": round(cumulative_growth, 3),
                "weekly_growth": round(weekly_growth, 4),
                "weekly_growth_rate": round(weekly_growth_rate, 4),
                "total_tokens": trend.get("latest_total", 0),
                "trend_direction": trend_direction,
                "alert_level": trend.get("alert_level", "normal"),
                "is_abnormal": trend.get("is_anomaly", False),
                "related_blocks": ["AI算力", "半导体", "芯片"],
                "related_symbols": ["NVDA", "AMD", "TSLA", "台积电", "SMCI"],
                "timestamp": data.get("timestamp"),
                "message": trend.get("message", ""),
                "recommendation": trend.get("recommendation", ""),
                "base_strength": round(base_strength, 3),
                "is_incomplete_week": trend.get("is_incomplete_week", False),
                "data_weeks": trend.get("data_weeks", 0)
            }

        except Exception as e:
            print(f"[OpenRouter] get_ai_compute_trend 失败: {e}")
            return None

    def scheduled_openrouter_check(self):
        """调度任务：每周一执行"""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(self.refresh_openrouter_data())
            loop.close()

            if result:
                print(f"[OpenRouter Scheduler] 检查完成: {result.get('message', '')}")
            else:
                print(f"[OpenRouter Scheduler] 检查失败")

        except Exception as e:
            print(f"[OpenRouter Scheduler] 执行失败: {e}")


# 全局实例
_openrouter_monitor_instance = None


def get_openrouter_monitor() -> OpenRouterMonitor:
    """获取 OpenRouter 监控实例"""
    global _openrouter_monitor_instance
    if _openrouter_monitor_instance is None:
        _openrouter_monitor_instance = OpenRouterMonitor()
    return _openrouter_monitor_instance


# 向后兼容的函数
def get_ai_compute_trend() -> Optional[Dict]:
    """向后兼容：获取 AI 算力趋势"""
    return get_openrouter_monitor().get_ai_compute_trend()


def get_openrouter_trend() -> Optional[Dict]:
    """向后兼容：获取 OpenRouter 趋势"""
    return get_openrouter_monitor().get_openrouter_trend()


def get_openrouter_full_data() -> Optional[Dict]:
    """向后兼容：获取完整的 OpenRouter 数据"""
    return get_openrouter_monitor().get_openrouter_full_data()


def scheduled_openrouter_check():
    """向后兼容：调度任务"""
    get_openrouter_monitor().scheduled_openrouter_check()
