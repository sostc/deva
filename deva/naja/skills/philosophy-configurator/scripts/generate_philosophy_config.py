"""
Philosophy Configurator - 理念配置生成器

将用户的投资哲学（天道民心、价值观、愿景使命）自动转化为Naja智慧系统的完整配置体系。

使用方式：
    from scripts.generate_philosophy_config import PhilosophyConfigurator

    configurator = PhilosophyConfigurator()

    # 用户理念输入
    philosophy = {
        "mission": "遵循天道，驾驭民心",
        "tiandao": "TOKEN消耗、算力短缺、技术突破",
        "minxin": "股价涨跌、舆论情绪",
        "direction": "creative",
        "risk_preference": 0.6,
        "time_horizon": 0.7,
        "domains": ["AI", "芯片"],
    }

    # 生成配置
    config = configurator.generate(philosophy)

    # 应用到系统
    configurator.apply(config)

    # 验证
    result = configurator.verify()
"""

import os
import json
import time
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field

log = logging.getLogger(__name__)


@dataclass
class PhilosophyInput:
    """用户理念输入"""
    mission: str = "遵循天道，驾驭民心"
    tiandao: str = "TOKEN消耗、大模型限流卡脖子、AI效率提升"
    minxin: str = "市场行情、股价涨跌、舆论情绪"
    direction: str = "creative"
    risk_preference: float = 0.5
    time_horizon: float = 0.5
    domains: List[str] = field(default_factory=lambda: ["AI", "芯片"])
    custom_principles: List[str] = field(default_factory=list)


@dataclass
class PhilosophyConfig:
    """生成的理念配置"""
    soul: Dict[str, Any]
    values: Dict[str, Any]
    narrative: Dict[str, Any]
    config: Dict[str, Any]


class PhilosophyConfigurator:
    """
    理念配置生成器

    将用户理念转化为完整的系统配置
    """

    def __init__(self):
        self.base_path = "/Users/spark/pycharmproject/deva"
        self.config = None

    def generate(self, philosophy: Dict[str, Any]) -> PhilosophyConfig:
        """
        根据用户理念生成配置

        Args:
            philosophy: 用户理念字典，包含:
                - mission: 核心使命
                - tiandao: 天道定义
                - minxin: 民心定义
                - direction: 投资方向 (creative/speculative)
                - risk_preference: 风险偏好 (0-1)
                - time_horizon: 时间视野 (0-1)
                - domains: 关注领域列表
                - custom_principles: 自定义原则列表

        Returns:
            PhilosophyConfig: 生成的完整配置
        """
        log.info("开始生成理念配置...")

        input_data = PhilosophyInput(
            mission=philosophy.get("mission", "遵循天道，驾驭民心"),
            tiandao=philosophy.get("tiandao", "TOKEN消耗、大模型限流卡脖子、AI效率提升"),
            minxin=philosophy.get("minxin", "市场行情、股价涨跌、舆论情绪"),
            direction=philosophy.get("direction", "creative"),
            risk_preference=philosophy.get("risk_preference", 0.5),
            time_horizon=philosophy.get("time_horizon", 0.5),
            domains=philosophy.get("domains", ["AI", "芯片"]),
            custom_principles=philosophy.get("custom_principles", []),
        )

        soul_config = self._generate_soul_config(input_data)
        values_config = self._generate_values_config(input_data)
        narrative_config = self._generate_narrative_config(input_data)
        detail_config = self._generate_detail_config(input_data)

        self.config = PhilosophyConfig(
            soul=soul_config,
            values=values_config,
            narrative=narrative_config,
            config=detail_config,
        )

        log.info("理念配置生成完成")
        return self.config

    def _generate_soul_config(self, input_data: PhilosophyInput) -> Dict[str, Any]:
        """生成SOUL.md配置"""
        return {
            "mission": input_data.mission,
            "tiandao": input_data.tiandao,
            "minxin": input_data.minxin,
            "principles": input_data.custom_principles or [
                "质量 > 速度 - 严谨的方案胜过草率的答案",
                "预判 > 响应 - 提前准备，不等催促",
                "记录 > 记忆 - 所有重要信息写入文件",
                "自动化 > 手动 - 朝着理想状态努力",
                "安全 > 便利 - 保护数据和系统",
            ],
            "judgment_criteria": [
                "供给不足 + 技术突破 = 天道支持，继续投入",
                "供给过剩 + 效率停滞 = 天道不支持，考虑退出",
            ],
            "daily_reflection": "我的行动是否遵循天道？是否在驾驭民心而不是被民心驾驭？",
        }

    def _generate_values_config(self, input_data: PhilosophyInput) -> Dict[str, Any]:
        """生成价值观配置"""
        is_creative = input_data.direction == "creative"
        risk = input_data.risk_preference
        time_horizon = input_data.time_horizon

        if is_creative:
            core_weight = 0.9
            spec_weight = 0.3
        else:
            core_weight = 0.5
            spec_weight = 0.7

        return {
            "active_default": "growth" if is_creative else "trend",
            "profiles": [
                {
                    "name": "天道投资",
                    "value_type": "growth",
                    "description": f"{input_data.mission}。投资真正推动AI发展的方向。",
                    "investment_direction": "creative",
                    "weights": {
                        "price_sensitivity": 0.3,
                        "volume_sensitivity": 0.3,
                        "sentiment_weight": 0.2,
                        "liquidity_weight": 0.3,
                        "fundamentals_weight": 0.9,
                    },
                    "preferences": {
                        "risk_preference": risk,
                        "time_horizon": time_horizon,
                        "concentration": 0.6,
                    },
                    "principles": input_data.custom_principles or [
                        "遵循天道，驾驭民心",
                        "投资真正推动AI发展的方向",
                        "天道支持则持有，天道不支持则退出",
                    ],
                },
                {
                    "name": "价值投资",
                    "value_type": "value",
                    "description": "均值回归，价格终究合理。安全边际是第一原则。",
                    "investment_direction": "creative",
                    "weights": {
                        "price_sensitivity": 0.4,
                        "volume_sensitivity": 0.3,
                        "sentiment_weight": 0.3,
                        "liquidity_weight": 0.3,
                        "fundamentals_weight": 0.8,
                    },
                    "preferences": {
                        "risk_preference": max(0.1, risk - 0.2),
                        "time_horizon": min(1.0, time_horizon + 0.2),
                        "concentration": 0.4,
                    },
                    "principles": [
                        "价格终将回归价值",
                        "不要追高",
                        "安全边际是第一原则",
                    ],
                },
                {
                    "name": "趋势追踪",
                    "value_type": "trend",
                    "description": "顺势而为，追涨杀跌。趋势是你的朋友。",
                    "investment_direction": "speculative",
                    "weights": {
                        "price_sensitivity": 0.8,
                        "volume_sensitivity": 0.6,
                        "sentiment_weight": 0.4,
                        "liquidity_weight": 0.3,
                        "fundamentals_weight": 0.2,
                    },
                    "preferences": {
                        "risk_preference": min(1.0, risk + 0.1),
                        "time_horizon": max(0.0, time_horizon - 0.4),
                        "concentration": 0.5,
                    },
                    "principles": [
                        "趋势一旦形成，不会轻易改变",
                        "不要逆势而行",
                        "让利润奔跑",
                    ],
                },
            ],
        }

    def _generate_narrative_config(self, input_data: PhilosophyInput) -> Dict[str, Any]:
        """生成叙事追踪配置（天道/民心关键词）"""
        tiandao_keywords = self._expand_tiandao_keywords(input_data)
        minxin_keywords = self._expand_minxin_keywords(input_data)
        domain_keywords = self._expand_domain_keywords(input_data.domains)

        return {
            "tiandao_keywords": tiandao_keywords,
            "minxin_keywords": minxin_keywords,
            "domain_keywords": domain_keywords,
            "scoring_rules": {
                "tiandao_heavy": True,
                "minxin_reference_only": True,
                "decision_mode": "tiandao_first",
            },
        }

    def _expand_tiandao_keywords(self, input_data: PhilosophyInput) -> List[str]:
        """扩展天道关键词"""
        base_keywords = [
            "限流", "限速", "token不够", "算力告急", "API排队",
            "token消耗", "算力短缺", "GPU排队", "算力不足",
            "API限流", "ChatGPT限流", "Claude限流", "Gemini限流",
            "模型服务不可用", "服务器过载", "负载过高",
            "卡脖子", "产能不足", "良品率", "HBM缺货",
            "EUV产能", "先进封装产能", "CoWoS满载", "封装排队",
            "晶圆厂产能满", "产能告急", "设备交付延迟",
            "性能提升", "成本下降", "新一代", "突破", "效率提升",
            "推理加速", "训练成本下降", "功耗降低", "算力翻倍",
            "新架构", "技术创新", "技术路线突破",
            "渗透率", "落地", "商业化", "盈利", "行业AI化",
            "AI改造", "降本增效", "收入增长",
            "付费转化", "用户增长", "API调用量增长",
        ]

        additional = []
        tiandao_input = input_data.tiandao.lower()
        if "gpu" in tiandao_input or "算力" in tiandao_input:
            additional.extend(["英伟达", "AMD", "GPU需求", "HBM", "先进封装"])
        if "token" in tiandao_input or "llm" in tiandao_input:
            additional.extend(["大模型", "LLM", "上下文窗口", "推理成本"])
        if "效率" in tiandao_input or "成本" in tiandao_input:
            additional.extend(["推理效率", "训练效率", "单位成本"])

        return list(set(base_keywords + additional))

    def _expand_minxin_keywords(self, input_data: PhilosophyInput) -> List[str]:
        """扩展民心关键词"""
        return [
            "上涨", "下跌", "大涨", "大跌", "暴涨", "暴跌",
            "牛市", "熊市", "反弹", "回调", "震荡",
            "资金流入", "资金流出", "净流入", "净流出",
            "市场认为", "分析师称", "机构表示", "情绪乐观",
            "情绪悲观", "恐慌", "贪婪", "风险偏好",
            "避险", "风险情绪", "市场信心",
            "热门", "热搜", "刷屏", "引爆", "疯狂",
            "泡沫", "投机", "炒作", "概念股",
        ]

    def _expand_domain_keywords(self, domains: List[str]) -> Dict[str, List[str]]:
        """扩展领域关键词"""
        domain_map = {
            "AI": [
                "AI", "AIGC", "人工智能", "大模型", "多模态", "生成式",
                "GPT", "ChatGPT", "Sora", "算力", "智能体", "Agent",
                "LLM", "RAG", "向量数据库", "Embedding",
                "OpenAI", "Anthropic", "Claude", "Gemini",
                "文心一言", "通义千问", "Kimi", "豆包",
                "昇腾", "昆仑", "寒武纪", "燧原",
            ],
            "芯片": [
                "芯片", "半导体", "集成电路", "晶圆", "光刻", "GPU", "CPU",
                "HBM", "DRAM", "NAND", "SoC", "ASIC", "FPGA",
                "英伟达", "AMD", "英特尔", "高通", "联发科",
                "台积电", "三星", "中芯国际", "华虹半导体",
            ],
            "新能源": [
                "新能源", "光伏", "风电", "储能", "锂电", "电池",
                "电动车", "逆变器", "宁德时代", "比亚迪",
                "隆基绿能", "通威股份", "阳光电源",
            ],
            "医药": [
                "医药", "生物医药", "创新药", "疫苗", "医疗器械",
                "创新药", "恒瑞医药", "百济神州", "君实生物",
            ],
            "华为": [
                "华为", "昇腾", "鸿蒙", "HarmonyOS", "麒麟芯片",
                "鲲鹏", "昇思", "华为云", "问界",
            ],
        }

        result = {}
        for domain in domains:
            if domain in domain_map:
                result[domain] = domain_map[domain]
            else:
                result[domain] = [domain]

        for domain, keywords in domain_map.items():
            if domain not in result:
                result[domain] = keywords

        return result

    def _generate_detail_config(self, input_data: PhilosophyInput) -> Dict[str, Any]:
        """生成详细配置"""
        return {
            "regime_compatibility": {
                "trend_up": ["trend", "momentum", "liquidity", "growth"],
                "weak_trend_up": ["trend", "momentum"],
                "neutral": ["value", "liquidity", "balanced", "growth"],
                "mixed": ["contrarian", "liquidity", "balanced", "liquidity_rescue", "growth"],
                "weak_trend_down": ["contrarian", "momentum", "liquidity_rescue"],
                "trend_down": ["contrarian", "momentum", "liquidity_rescue"],
            },
            "decision_rules": {
                "tiandao_threshold": 0.5,
                "minxin_threshold": 0.3,
                "minxin_as_reference": True,
                "action_on_tiandao_strong": "hold_or_buy",
                "action_on_tiandao_weak": "reduce_or_avoid",
            },
        }

    def apply(self, config: Optional[PhilosophyConfig] = None) -> Dict[str, Any]:
        """
        将配置应用到系统中

        Args:
            config: 要应用的配置，默认使用上次生成的配置

        Returns:
            应用结果字典
        """
        if config is None:
            config = self.config

        if config is None:
            raise ValueError("没有可应用的配置，请先调用 generate()")

        results = {}

        results["soul"] = self._apply_soul_config(config.soul)
        results["values"] = self._apply_values_config(config.values)
        results["narrative"] = self._apply_narrative_config(config.narrative)

        return results

    def _apply_soul_config(self, soul_config: Dict[str, Any]) -> Dict[str, Any]:
        """应用SOUL配置"""
        soul_path = os.path.join(self.base_path, "SOUL.md")

        content = f"""# SOUL.md - 我是谁

> {soul_config['mission']}

## 我的行事风格

**专业严谨** - 像专家顾问一样思考，提供经过验证的建议

**高效直接** - 只说重点，不废话，尊重异步沟通偏好

**主动预判** - 在高效时段前准备好所需材料

**不屈不挠** - 尝试多种方法解决问题，不轻易放弃

## 我的原则

"""

        for i, principle in enumerate(soul_config['principles'], 1):
            content += f"{i}. **{principle}**\n"

        content += f"""
## 我的使命

**{soul_config['mission']}**

天道：{soul_config['tiandao']}——这些是客观规律，是真相，最终会胜出。

民心：{soul_config['minxin']}——随时在变，可参考但不做决策依据。

判断标准：
- {soul_config['judgment_criteria'][0]}
- {soul_config['judgment_criteria'][1]}

每天思考：{soul_config['daily_reflection']}

---

*天道大于民心 - 为老板服务*
"""

        with open(soul_path, "w", encoding="utf-8") as f:
            f.write(content)

        return {"status": "success", "path": soul_path}

    def _apply_values_config(self, values_config: Dict[str, Any]) -> Dict[str, Any]:
        """应用价值观配置"""
        types_path = os.path.join(self.base_path, "deva/naja/attention/values/types.py")
        profile_path = os.path.join(self.base_path, "deva/naja/attention/values/profile.py")

        self._update_growth_type_description(types_path, values_config["profiles"][0])

        self._update_default_profiles(profile_path, values_config["profiles"])

        return {
            "status": "success",
            "updated_profiles": len(values_config["profiles"]),
        }

    def _update_growth_type_description(self, types_path: str, growth_profile: Dict[str, Any]):
        """更新growth类型的描述"""
        with open(types_path, "r", encoding="utf-8") as f:
            content = f.read()

        old_growth_desc = '"growth": "🚀 天道投资：遵循天道，驾驭民心。投资真正推动AI发展的方向——TOKEN供需失衡（限流/卡脖子）代表供给不足，技术突破代表效率提升。民心（股价/舆论）只作参考。天道支持则持有，天道不支持则退出。"'

        new_growth_desc = f'"growth": "🚀 {growth_profile["description"]}"'

        content = content.replace(old_growth_desc, new_growth_desc)

        with open(types_path, "w", encoding="utf-8") as f:
            f.write(content)

    def _update_default_profiles(self, profile_path: str, profiles: List[Dict[str, Any]]):
        """更新默认价值观配置"""
        with open(profile_path, "r", encoding="utf-8") as f:
            content = f.read()

        for profile in profiles:
            if profile["value_type"] == "growth":
                old_growth = 'ValueProfile(\n            name="成长投资",'
                new_growth = f'ValueProfile(\n            name="{profile["name"]}",'
                content = content.replace(old_growth, new_growth)

        with open(profile_path, "w", encoding="utf-8") as f:
            f.write(content)

    def _apply_narrative_config(self, narrative_config: Dict[str, Any]) -> Dict[str, Any]:
        """应用叙事追踪配置"""
        narrative_path = os.path.join(self.base_path, "deva/naja/cognition/narrative_tracker.py")

        with open(narrative_path, "r", encoding="utf-8") as f:
            content = f.read()

        tiandao_keywords = narrative_config["tiandao_keywords"]
        minxin_keywords = narrative_config["minxin_keywords"]

        keyword_items = ", ".join('"' + k + '"' for k in tiandao_keywords[:10])
        tiandao_str = '    "天道": [\n        "限流", "限速", "token不够", "算力告急", "API排队",'
        tiandao_new = f'    "天道": [\n        {keyword_items},'

        content = content.replace(tiandao_str, tiandao_new)

        with open(narrative_path, "w", encoding="utf-8") as f:
            f.write(content)

        return {
            "status": "success",
            "tiandao_keywords_count": len(tiandao_keywords),
            "minxin_keywords_count": len(minxin_keywords),
        }

    def verify(self) -> Dict[str, Any]:
        """验证配置是否正确应用"""
        results = {}

        soul_path = os.path.join(self.base_path, "SOUL.md")
        results["soul"] = os.path.exists(soul_path)

        try:
            from deva.naja.attention.values.system import get_value_system
            vs = get_value_system()
            results["value_system"] = vs is not None
            results["active_type"] = vs.get_active_value_type()
        except Exception as e:
            results["value_system"] = False
            results["error"] = str(e)

        try:
            from deva.naja.cognition.narrative import NarrativeTracker
            results["narrative_tracker"] = True
        except Exception as e:
            results["narrative_tracker"] = False
            results["error"] = str(e)

        return results

    def export_config(self, config: Optional[PhilosophyConfig] = None) -> str:
        """导出配置为JSON字符串"""
        if config is None:
            config = self.config

        if config is None:
            raise ValueError("没有可导出的配置")

        return json.dumps({
            "soul": config.soul,
            "values": config.values,
            "narrative": config.narrative,
            "config": config.config,
        }, ensure_ascii=False, indent=2)

    def save_to_file(self, filepath: str, config: Optional[PhilosophyConfig] = None):
        """保存配置到文件"""
        json_str = self.export_config(config)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(json_str)

    def load_from_file(self, filepath: str) -> PhilosophyConfig:
        """从文件加载配置"""
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        return PhilosophyConfig(
            soul=data["soul"],
            values=data["values"],
            narrative=data["narrative"],
            config=data.get("config", {}),
        )


def main():
    """命令行入口"""
    configurator = PhilosophyConfigurator()

    philosophy = {
        "mission": "遵循天道，驾驭民心",
        "tiandao": "TOKEN消耗、大模型限流卡脖子、AI效率提升",
        "minxin": "市场行情、股价涨跌、舆论情绪",
        "direction": "creative",
        "risk_preference": 0.6,
        "time_horizon": 0.7,
        "domains": ["AI", "芯片"],
    }

    print("生成理念配置...")
    config = configurator.generate(philosophy)

    print("\n生成的配置预览：")
    print(f"使命：{config.soul['mission']}")
    print(f"天道关键词数：{len(config.narrative['tiandao_keywords'])}")
    print(f"民心关键词数：{len(config.narrative['minxin_keywords'])}")
    print(f"价值观数量：{len(config.values['profiles'])}")

    print("\n应用配置到系统...")
    results = configurator.apply(config)
    print(f"应用结果：{results}")

    print("\n验证配置...")
    verify_result = configurator.verify()
    print(f"验证结果：{verify_result}")


if __name__ == "__main__":
    main()
