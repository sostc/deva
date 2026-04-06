"""
SoulGenerator - 灵魂生成器

根据用户选择生成完整的灵魂配置

使用方式：
    generator = SoulGenerator()
    soul = generator.generate(
        name="🚀 赛道投资型",
        direction="creative",
        domains=["AI", "芯片", "新能源"],
        risk_level="moderate",
        custom_notes=""
    )
    generator.save(soul)
"""

import time
import uuid
import logging
from typing import Dict, List, Any, Optional

from .soul_config_loader import SoulConfigLoader
from .supply_chain_templates import SUPPLY_CHAIN_TEMPLATES, expand_supply_chain_keywords
from .domain_keywords import DOMAIN_KEYWORDS, expand_domain_keywords

log = logging.getLogger(__name__)


class SoulGenerator:
    """灵魂生成器"""

    DIRECTION_TEMPLATES = {
        "creative": {
            "type": "creative",
            "label": "赛道投资",
            "description": "投资真正推动世界进步的赛道",
            "icon": "🚀",
            "tiandao_weight": 0.9,
            "minxin_weight": 0.2,
            "fundamentals_weight": 0.9,
        },
        "speculative": {
            "type": "speculative",
            "label": "流动性投资",
            "description": "为市场提供流动性，高抛低吸",
            "icon": "💧",
            "tiandao_weight": 0.5,
            "minxin_weight": 0.5,
            "fundamentals_weight": 0.4,
        },
    }

    RISK_TEMPLATES = {
        "conservative": {
            "level": "conservative",
            "label": "稳健型",
            "risk_preference": 0.2,
            "time_horizon": 0.9,
            "max_position": 0.15,
            "stop_loss": 0.05,
            "take_profit": 0.20,
        },
        "moderate": {
            "level": "moderate",
            "label": "均衡型",
            "risk_preference": 0.5,
            "time_horizon": 0.5,
            "max_position": 0.20,
            "stop_loss": 0.08,
            "take_profit": 0.30,
        },
        "aggressive": {
            "level": "aggressive",
            "label": "进取型",
            "risk_preference": 0.8,
            "time_horizon": 0.8,
            "max_position": 0.30,
            "stop_loss": 0.10,
            "take_profit": 0.50,
        },
    }

    DEFAULT_DYNAMICS_KEYWORDS = [
        "限流", "限速", "token不够", "算力告急", "API排队",
        "token消耗", "算力短缺", "GPU排队", "算力不足",
        "API限流", "ChatGPT限流", "Claude限流", "Gemini限流",
        "卡脖子", "产能不足", "良品率", "HBM缺货",
        "性能提升", "成本下降", "新一代", "突破", "效率提升",
        "推理加速", "训练成本下降", "功耗降低", "算力翻倍",
        "新架构", "技术创新", "技术路线突破",
        "渗透率", "落地", "商业化", "盈利", "行业AI化",
        "AI改造", "降本增效", "收入增长",
        "付费转化", "用户增长", "API调用量增长",
    ]

    DEFAULT_SENTIMENT_KEYWORDS = [
        "上涨", "下跌", "大涨", "大跌", "暴涨", "暴跌",
        "牛市", "熊市", "反弹", "回调", "震荡",
        "资金流入", "资金流出", "净流入", "净流出",
        "市场认为", "分析师称", "机构表示", "情绪乐观",
        "情绪悲观", "恐慌", "贪婪", "风险偏好",
        "热门", "热搜", "刷屏", "引爆", "疯狂",
        "泡沫", "投机", "炒作", "概念股",
    ]

    def __init__(self):
        self.config_loader = SoulConfigLoader()

    def generate(
        self,
        name: str,
        direction: str = "creative",
        domains: List[str] = None,
        risk_level: str = "moderate",
        dynamics_definition: str = None,
        sentiment_definition: str = None,
        custom_notes: str = "",
        custom_tiandao_keywords: List[str] = None,
        custom_minxin_keywords: List[str] = None,
    ) -> Dict[str, Any]:
        """
        生成灵魂配置

        Args:
            name: 灵魂名称
            direction: 价值方向 (creative/speculative)
            domains: 关注的行业列表
            risk_level: 风险等级 (conservative/moderate/aggressive)
            dynamics_definition: 自定义供需动态定义
            sentiment_definition: 自定义市场情绪定义
            custom_notes: 自定义理念
            custom_tiandao_keywords: 自定义天道关键词
            custom_minxin_keywords: 自定义民心关键词

        Returns:
            完整的灵魂配置字典
        """
        if domains is None:
            domains = ["AI", "芯片"]

        direction_config = self.DIRECTION_TEMPLATES.get(direction, self.DIRECTION_TEMPLATES["creative"])
        risk_config = self.RISK_TEMPLATES.get(risk_level, self.RISK_TEMPLATES["moderate"])

        supply_chain = self._generate_supply_chain(domains)
        domain_keywords = expand_domain_keywords(domains)

        dynamics_keywords = self._generate_dynamics_keywords(
            domains, custom_tiandao_keywords, supply_chain
        )
        sentiment_keywords = self._generate_sentiment_keywords(custom_minxin_keywords)

        soul_id = self._generate_soul_id(name)

        soul = {
            "soul_id": soul_id,
            "soul_name": name,
            "version": "1.0",
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),

            "direction": direction_config,
            "domains": {
                "focused": domains,
                "all_keywords": domain_keywords,
            },
            "risk_profile": risk_config,
            "philosophy": {
                "mission": f"遵循供需动态，驾驭市场情绪。{direction_config['description']}",
                "dynamics_definition": dynamics_definition or "TOKEN消耗、大模型限流卡脖子、AI效率提升",
                "sentiment_definition": sentiment_definition or "市场行情、股价涨跌、舆论情绪",
                "custom_notes": custom_notes,
            },

            "supply_chain": supply_chain,

            "keywords": {
                "dynamics": dynamics_keywords,
                "sentiment": sentiment_keywords,
                "domains": domain_keywords,
            },

            "values": self._generate_values(direction, direction_config, risk_config),

            "decision_rules": self._generate_decision_rules(direction_config),

            "position_handling": {
                "existing_positions": "keep_original",
                "new_positions": "apply_new",
            },
        }

        return soul

    def _generate_soul_id(self, name: str) -> str:
        """生成灵魂ID"""
        clean_name = name.replace(" ", "_").replace("🚀", "").replace("💧", "").replace("🛡️", "").replace("🎯", "").replace("💡", "")
        timestamp = int(time.time())
        return f"{clean_name}_{timestamp}"

    def _generate_supply_chain(self, domains: List[str]) -> Dict[str, Any]:
        """生成供应链配置"""
        supply_chain = {}

        for domain in domains:
            if domain in SUPPLY_CHAIN_TEMPLATES:
                supply_chain[domain] = SUPPLY_CHAIN_TEMPLATES[domain]

        return supply_chain

    def _generate_dynamics_keywords(
        self,
        domains: List[str],
        custom_keywords: List[str] = None,
        supply_chain: Dict[str, Any] = None,
    ) -> List[str]:
        """生成供需动态关键词"""
        keywords = list(self.DEFAULT_DYNAMICS_KEYWORDS)

        if supply_chain:
            for domain, chain in supply_chain.items():
                for level in ["upstream", "midstream", "downstream"]:
                    if level in chain:
                        keywords.extend(chain[level].get("tiandao_keywords", []))

        if custom_keywords:
            keywords.extend(custom_keywords)

        return list(set(keywords))

    def _generate_sentiment_keywords(self, custom_keywords: List[str] = None) -> List[str]:
        """生成市场情绪关键词"""
        keywords = list(self.DEFAULT_SENTIMENT_KEYWORDS)

        if custom_keywords:
            keywords.extend(custom_keywords)

        return list(set(keywords))

    def _generate_values(
        self,
        direction: str,
        direction_config: Dict[str, Any],
        risk_config: Dict[str, Any],
    ) -> Dict[str, Any]:
        """生成价值观配置"""
        if direction == "creative":
            profiles = [
                {
                    "name": "天道投资",
                    "type": "growth",
                    "description": "遵循天道，驾驭民心。投资真正推动AI发展的方向。",
                    "investment_direction": "creative",
                    "weights": {
                        "price_sensitivity": 0.3,
                        "volume_sensitivity": 0.3,
                        "sentiment_weight": direction_config["minxin_weight"],
                        "liquidity_weight": 0.3,
                        "fundamentals_weight": direction_config["fundamentals_weight"],
                        "tiandao_weight": direction_config["tiandao_weight"],
                    },
                    "preferences": {
                        "risk_preference": risk_config["risk_preference"],
                        "time_horizon": risk_config["time_horizon"],
                        "concentration": 0.6,
                    },
                    "principles": [
                        "遵循天道，驾驭民心",
                        "投资真正推动AI发展的方向",
                        "天道支持则持有，天道不支持则退出",
                    ],
                    "implemented": True,
                },
                {
                    "name": "价值投资",
                    "type": "value",
                    "description": "均值回归，价格终究合理。安全边际是第一原则。",
                    "investment_direction": "creative",
                    "weights": {
                        "price_sensitivity": 0.4,
                        "volume_sensitivity": 0.3,
                        "sentiment_weight": 0.3,
                        "liquidity_weight": 0.3,
                        "fundamentals_weight": 0.8,
                        "tiandao_weight": 0.6,
                    },
                    "preferences": {
                        "risk_preference": max(0.1, risk_config["risk_preference"] - 0.2),
                        "time_horizon": min(1.0, risk_config["time_horizon"] + 0.2),
                        "concentration": 0.4,
                    },
                    "principles": [
                        "价格终将回归价值",
                        "不要追高",
                        "安全边际是第一原则",
                    ],
                    "implemented": True,
                },
            ]
        else:
            profiles = [
                {
                    "name": "趋势追踪",
                    "type": "trend",
                    "description": "顺势而为，追涨杀跌。趋势是你的朋友。",
                    "investment_direction": "speculative",
                    "weights": {
                        "price_sensitivity": 0.8,
                        "volume_sensitivity": 0.6,
                        "sentiment_weight": 0.4,
                        "liquidity_weight": 0.3,
                        "fundamentals_weight": 0.2,
                        "tiandao_weight": 0.5,
                    },
                    "preferences": {
                        "risk_preference": min(1.0, risk_config["risk_preference"] + 0.1),
                        "time_horizon": max(0.0, risk_config["time_horizon"] - 0.4),
                        "concentration": 0.5,
                    },
                    "principles": [
                        "趋势一旦形成，不会轻易改变",
                        "不要逆势而行",
                        "让利润奔跑",
                    ],
                    "implemented": True,
                },
                {
                    "name": "流动性猎人",
                    "type": "liquidity",
                    "description": "为市场提供流动性，高抛低吸。",
                    "investment_direction": "speculative",
                    "weights": {
                        "price_sensitivity": 0.6,
                        "volume_sensitivity": 0.8,
                        "sentiment_weight": 0.3,
                        "liquidity_weight": 0.9,
                        "fundamentals_weight": 0.2,
                        "tiandao_weight": 0.4,
                    },
                    "preferences": {
                        "risk_preference": risk_config["risk_preference"],
                        "time_horizon": max(0.0, risk_config["time_horizon"] - 0.3),
                        "concentration": 0.3,
                    },
                    "principles": [
                        "钱去哪，价去哪",
                        "高抛低吸",
                        "为市场提供流动性",
                    ],
                    "implemented": True,
                },
            ]

        return {
            "profiles": profiles,
            "active_default": profiles[0]["type"] if profiles else "growth",
        }

    def _generate_decision_rules(self, direction_config: Dict[str, Any]) -> Dict[str, Any]:
        """生成决策规则"""
        tiandao_weight = direction_config["tiandao_weight"]
        minxin_weight = direction_config["minxin_weight"]

        return {
            "tiandao_threshold": 0.5,
            "minxin_threshold": 0.3,
            "minxin_as_reference": True,
            "action_rules": {
                "tiandao_strong_minxin_weak": "buy" if tiandao_weight > 0.7 else "hold",
                "tiandao_strong_minxin_strong": "hold",
                "tiandao_weak_minxin_strong": "reduce",
                "tiandao_weak_minxin_weak": "watch",
            },
            "regime_compatibility": {
                "trend_up": ["trend", "momentum", "liquidity", "growth"],
                "weak_trend_up": ["trend", "momentum"],
                "neutral": ["value", "liquidity", "balanced", "growth"],
                "mixed": ["contrarian", "liquidity", "balanced", "liquidity_rescue", "growth"],
                "weak_trend_down": ["contrarian", "momentum", "liquidity_rescue"],
                "trend_down": ["contrarian", "momentum", "liquidity_rescue"],
            },
        }

    def save(self, soul: Dict[str, Any]) -> str:
        """
        保存灵魂配置

        Args:
            soul: 灵魂配置字典

        Returns:
            灵魂ID
        """
        soul_id = soul["soul_id"]
        self.config_loader.save_soul_config(soul_id, soul)
        self.config_loader.set_active_soul_id(soul_id)
        log.info(f"灵魂已保存: {soul['soul_name']} ({soul_id})")
        return soul_id

    def apply(self, soul: Dict[str, Any]) -> Dict[str, Any]:
        """
        应用灵魂配置到系统

        Args:
            soul: 灵魂配置字典

        Returns:
            应用结果
        """
        soul_id = self.save(soul)

        return {
            "status": "success",
            "soul_id": soul_id,
            "soul_name": soul["soul_name"],
            "message": f"灵魂 '{soul['soul_name']}' 已保存并激活",
        }

    def generate_summary(self, soul: Dict[str, Any]) -> str:
        """
        生成灵魂配置摘要（用于UI展示）

        Args:
            soul: 灵魂配置字典

        Returns:
            摘要HTML
        """
        direction = soul.get("direction", {})
        domains = soul.get("domains", {}).get("focused", [])
        risk = soul.get("risk_profile", {})
        keywords = soul.get("keywords", {})
        values = soul.get("values", {})
        supply_chain = soul.get("supply_chain", {})

        tiandao_count = len(keywords.get("tiandao", []))
        minxin_count = len(keywords.get("minxin", []))
        supply_chain_count = len(supply_chain)

        domain_stats = []
        for domain in domains:
            if domain in supply_chain:
                domain_stats.append(f"{domain}: 上中下游")

        summary = f"""
        <div style="padding: 20px; background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); border-radius: 16px;">
            <h3 style="color: #fff; margin-bottom: 20px;">🚀 {soul['soul_name']}</h3>

            <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 15px;">
                <div style="background: rgba(255,255,255,0.05); padding: 15px; border-radius: 8px;">
                    <div style="color: #94a3b8; font-size: 12px;">价值方向</div>
                    <div style="color: #fff; font-weight: 600;">{direction.get('icon', '')} {direction.get('label', '')}</div>
                </div>
                <div style="background: rgba(255,255,255,0.05); padding: 15px; border-radius: 8px;">
                    <div style="color: #94a3b8; font-size: 12px;">风险偏好</div>
                    <div style="color: #fff; font-weight: 600;">{risk.get('label', '')} ({risk.get('risk_preference', 0)})</div>
                </div>
                <div style="background: rgba(255,255,255,0.05); padding: 15px; border-radius: 8px;">
                    <div style="color: #94a3b8; font-size: 12px;">天道权重</div>
                    <div style="color: #f59e0b; font-weight: 600;">{direction.get('tiandao_weight', 0)}</div>
                </div>
                <div style="background: rgba(255,255,255,0.05); padding: 15px; border-radius: 8px;">
                    <div style="color: #94a3b8; font-size: 12px;">民心权重</div>
                    <div style="color: #60a5fa; font-weight: 600;">{direction.get('minxin_weight', 0)}</div>
                </div>
            </div>

            <div style="margin-top: 15px; background: rgba(255,255,255,0.05); padding: 15px; border-radius: 8px;">
                <div style="color: #94a3b8; font-size: 12px;">关注行业</div>
                <div style="color: #fff; margin-top: 5px;">{' / '.join(domains)}</div>
            </div>

            <div style="margin-top: 15px; background: rgba(255,255,255,0.05); padding: 15px; border-radius: 8px;">
                <div style="color: #94a3b8; font-size: 12px;">天道关键词</div>
                <div style="color: #f59e0b; margin-top: 5px;">{tiandao_count}个 - {', '.join(keywords.get('tiandao', [])[:5])}...</div>
            </div>

            <div style="margin-top: 15px; background: rgba(255,255,255,0.05); padding: 15px; border-radius: 8px;">
                <div style="color: #94a3b8; font-size: 12px;">民心关键词</div>
                <div style="color: #60a5fa; margin-top: 5px;">{minxin_count}个 - {', '.join(keywords.get('minxin', [])[:5])}...</div>
            </div>

            <div style="margin-top: 15px; background: rgba(255,255,255,0.05); padding: 15px; border-radius: 8px;">
                <div style="color: #94a3b8; font-size: 12px;">供应链配置</div>
                <div style="color: #4ade80; margin-top: 5px;">{supply_chain_count}个行业</div>
            </div>
        </div>
        """

        return summary


def get_generator() -> SoulGenerator:
    """获取生成器实例"""
    return SoulGenerator()
