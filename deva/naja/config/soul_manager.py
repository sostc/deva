"""
SoulManager - 多灵魂管理系统

管理多个投资哲学/灵魂方案，支持：
- 创建/删除/切换灵魂
- 导出/导入灵魂配置
- 灵魂对比
- 配置应用

使用方式：
    from deva.naja.config.soul_manager import SoulManager
from deva.naja.register import SR

    manager = SoulManager()
    souls = manager.list_souls()
    manager.create_soul(name="激进型", philosophy={...})
    manager.activate_soul("激进型")
    manager.switch_soul("激进型")
    manager.export_soul("激进型", "/path/to/export.json")
"""

import os
import json
import time
import logging
from typing import Dict, List, Any, Optional

from .soul_config_loader import SoulConfigLoader
from .soul_generator import SoulGenerator

log = logging.getLogger(__name__)


class SoulManager:
    """
    多灵魂管理器

    管理多个灵魂配置，支持创建、切换、导出、导入、对比
    """

    PRESET_TEMPLATES = {
        "🚀 激进型": {
            "icon": "🚀",
            "name": "激进型",
            "description": "大机会，重仓出击",
            "direction": "creative",
            "risk_level": "aggressive",
            "domains": ["AI", "芯片"],
        },
        "🛡️ 保守型": {
            "icon": "🛡️",
            "name": "保守型",
            "description": "熊市，不确定性高时使用",
            "direction": "creative",
            "risk_level": "conservative",
            "domains": ["AI", "芯片"],
        },
        "🎯 专注型": {
            "icon": "🎯",
            "name": "专注型",
            "description": "明确趋势，顺势而为",
            "direction": "speculative",
            "risk_level": "moderate",
            "domains": ["AI", "芯片", "新能源"],
        },
        "💡 灵活型": {
            "icon": "💡",
            "name": "灵活型",
            "description": "震荡市，快速切换",
            "direction": "creative",
            "risk_level": "moderate",
            "domains": ["AI", "芯片", "新能源", "医药"],
        },
    }

    def __init__(self):
        self.config_loader = SoulConfigLoader()
        self.generator = SoulGenerator()

    def list_souls(self) -> List[Dict[str, Any]]:
        """列出所有灵魂"""
        souls = []

        soul_ids = self.config_loader.list_soul_ids()
        active_id = self.config_loader.get_active_soul_id()

        for soul_id in soul_ids:
            config = self.config_loader.load_soul_config(soul_id)
            if config:
                souls.append({
                    "soul_id": config.get("soul_id"),
                    "soul_name": config.get("soul_name"),
                    "icon": config.get("direction", {}).get("icon", "🧠"),
                    "description": config.get("philosophy", {}).get("mission", ""),
                    "direction": config.get("direction", {}).get("label", ""),
                    "domains": config.get("domains", {}).get("focused", []),
                    "risk_level": config.get("risk_profile", {}).get("level", ""),
                    "tiandao_weight": config.get("direction", {}).get("tiandao_weight", 0.5),
                    "minxin_weight": config.get("direction", {}).get("minxin_weight", 0.5),
                    "is_active": soul_id == active_id if active_id else False,
                    "created_at": config.get("created_at", ""),
                })

        return souls

    def get_active_soul(self) -> Optional[Dict[str, Any]]:
        """获取当前激活的灵魂"""
        active_id = self.config_loader.get_active_soul_id()

        if not active_id:
            return None

        config = self.config_loader.load_soul_config(active_id)

        if not config:
            return None

        return {
            "soul_id": config.get("soul_id"),
            "soul_name": config.get("soul_name"),
            "icon": config.get("direction", {}).get("icon", "🧠"),
            "direction": config.get("direction", {}),
            "domains": config.get("domains", {}),
            "risk_profile": config.get("risk_profile", {}),
            "philosophy": config.get("philosophy", {}),
            "keywords": config.get("keywords", {}),
            "values": config.get("values", {}),
            "supply_chain": config.get("supply_chain", {}),
            "decision_rules": config.get("decision_rules", {}),
            "is_active": True,
        }

    def get_soul(self, name: str) -> Optional[Dict[str, Any]]:
        """获取指定灵魂"""
        soul_ids = self.config_loader.list_soul_ids()

        for soul_id in soul_ids:
            config = self.config_loader.load_soul_config(soul_id)
            if config and config.get("soul_name") == name:
                return config

            if soul_id == name or soul_id.replace("_", " ") == name.replace("_", " "):
                return config

        return None

    def create_soul(
        self,
        name: str,
        direction: str = "creative",
        domains: List[str] = None,
        risk_level: str = "moderate",
        custom_notes: str = "",
    ) -> Dict[str, Any]:
        """
        创建新灵魂

        Args:
            name: 灵魂名称
            direction: 价值方向
            domains: 关注行业
            risk_level: 风险等级
            custom_notes: 自定义理念

        Returns:
            创建结果
        """
        soul = self.generator.generate(
            name=name,
            direction=direction,
            domains=domains,
            risk_level=risk_level,
            custom_notes=custom_notes,
        )

        soul_id = self.generator.save(soul)

        return {
            "status": "success",
            "soul_id": soul_id,
            "soul_name": name,
            "message": f"灵魂 '{name}' 创建成功",
        }

    def create_from_preset(self, preset_name: str, name: str = None) -> Dict[str, Any]:
        """
        从预设模板创建灵魂

        Args:
            preset_name: 预设模板名称
            name: 自定义名称

        Returns:
            创建结果
        """
        if preset_name not in self.PRESET_TEMPLATES:
            return {
                "status": "error",
                "message": f"未知预设模板: {preset_name}",
            }

        template = self.PRESET_TEMPLATES[preset_name]

        return self.create_soul(
            name=name or template["name"],
            direction=template["direction"],
            domains=template["domains"],
            risk_level=template["risk_level"],
        )

    def activate_soul(self, name: str) -> Dict[str, Any]:
        """
        激活灵魂（只激活，不应用配置）

        Args:
            name: 灵魂名称或ID

        Returns:
            激活结果
        """
        soul = self.get_soul(name)

        if not soul:
            return {
                "status": "error",
                "message": f"未找到灵魂: {name}",
            }

        soul_id = soul.get("soul_id")
        self.config_loader.set_active_soul_id(soul_id)

        return {
            "status": "success",
            "soul_name": soul.get("soul_name"),
            "message": f"灵魂 '{soul.get('soul_name')}' 已激活",
        }

    def switch_soul(self, name: str, immediate: bool = True) -> Dict[str, Any]:
        """
        切换灵魂（有持仓检测）

        Args:
            name: 灵魂名称或ID
            immediate: 是否立即生效（有持仓时建议false）

        Returns:
            切换结果
        """
        soul = self.get_soul(name)

        if not soul:
            return {
                "status": "error",
                "message": f"未找到灵魂: {name}",
            }

        has_positions = self._check_positions()

        if has_positions and immediate:
            return {
                "status": "warning",
                "soul_name": soul.get("soul_name"),
                "message": "检测到持仓，建议选择下个交易日生效",
                "has_positions": True,
                "suggest_delay": True,
            }

        soul_id = soul.get("soul_id")
        self.config_loader.set_active_soul_id(soul_id)

        return {
            "status": "success",
            "soul_name": soul.get("soul_name"),
            "message": f"灵魂 '{soul.get('soul_name')}' 已切换" + ("" if immediate else "（下个交易日生效）"),
            "has_positions": has_positions,
        }

    def _check_positions(self) -> bool:
        """检查是否有持仓"""
        try:
            runner = SR('bandit_runner')
            if runner and hasattr(runner, "get_positions"):
                positions = runner.get_positions()
                return len(positions) > 0
        except Exception:
            pass
        return False

    def delete_soul(self, name: str) -> Dict[str, Any]:
        """
        删除灵魂

        Args:
            name: 灵魂名称或ID

        Returns:
            删除结果
        """
        soul = self.get_soul(name)

        if not soul:
            return {
                "status": "error",
                "message": f"未找到灵魂: {name}",
            }

        if soul.get("is_active"):
            return {
                "status": "error",
                "message": "不能删除当前激活的灵魂，请先切换到其他灵魂",
            }

        soul_id = soul.get("soul_id")
        self.config_loader.delete_soul_config(soul_id)

        return {
            "status": "success",
            "message": f"灵魂 '{soul.get('soul_name')}' 已删除",
        }

    def export_soul(self, name: str, filepath: str = None) -> Dict[str, Any]:
        """
        导出灵魂

        Args:
            name: 灵魂名称或ID
            filepath: 导出路径

        Returns:
            导出结果
        """
        soul = self.get_soul(name)

        if not soul:
            return {
                "status": "error",
                "message": f"未找到灵魂: {name}",
            }

        if filepath is None:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            soul_name = soul.get("soul_name", "soul").replace(" ", "_")
            filepath = f"./soul_{soul_name}_{timestamp}.json"

        success = self.config_loader.export_soul(soul.get("soul_id"), filepath)

        if success:
            return {
                "status": "success",
                "filepath": filepath,
                "message": f"灵魂已导出到: {filepath}",
            }
        else:
            return {
                "status": "error",
                "message": "导出失败",
            }

    def import_soul(self, filepath: str, name: str = None) -> Dict[str, Any]:
        """
        导入灵魂

        Args:
            filepath: 导入文件路径
            name: 新名称

        Returns:
            导入结果
        """
        new_soul_id = self.config_loader.import_soul(filepath, name)

        if new_soul_id:
            return {
                "status": "success",
                "soul_id": new_soul_id,
                "message": f"灵魂已导入: {new_soul_id}",
            }
        else:
            return {
                "status": "error",
                "message": "导入失败，请检查文件格式",
            }

    def compare_souls(self, name1: str, name2: str) -> Dict[str, Any]:
        """
        对比两个灵魂

        Args:
            name1: 灵魂1名称
            name2: 灵魂2名称

        Returns:
            对比结果
        """
        soul1 = self.get_soul(name1)
        soul2 = self.get_soul(name2)

        if not soul1:
            return {"status": "error", "message": f"未找到灵魂: {name1}"}
        if not soul2:
            return {"status": "error", "message": f"未找到灵魂: {name2}"}

        comparison = {
            "status": "success",
            "soul1": {
                "name": soul1.get("soul_name"),
                "icon": soul1.get("direction", {}).get("icon", "🧠"),
                "direction": soul1.get("direction", {}).get("label", ""),
                "domains": soul1.get("domains", {}).get("focused", []),
                "risk_level": soul1.get("risk_profile", {}).get("level", ""),
                "risk_preference": soul1.get("risk_profile", {}).get("risk_preference", 0),
                "time_horizon": soul1.get("risk_profile", {}).get("time_horizon", 0),
                "max_position": soul1.get("risk_profile", {}).get("max_position", 0),
                "stop_loss": soul1.get("risk_profile", {}).get("stop_loss", 0),
                "take_profit": soul1.get("risk_profile", {}).get("take_profit", 0),
                "tiandao_weight": soul1.get("direction", {}).get("tiandao_weight", 0),
                "minxin_weight": soul1.get("direction", {}).get("minxin_weight", 0),
                "tiandao_count": len(soul1.get("keywords", {}).get("tiandao", [])),
                "minxin_count": len(soul1.get("keywords", {}).get("minxin", [])),
                "principles": soul1.get("values", {}).get("profiles", [{}])[0].get("principles", []) if soul1.get("values", {}).get("profiles") else [],
            },
            "soul2": {
                "name": soul2.get("soul_name"),
                "icon": soul2.get("direction", {}).get("icon", "🧠"),
                "direction": soul2.get("direction", {}).get("label", ""),
                "domains": soul2.get("domains", {}).get("focused", []),
                "risk_level": soul2.get("risk_profile", {}).get("level", ""),
                "risk_preference": soul2.get("risk_profile", {}).get("risk_preference", 0),
                "time_horizon": soul2.get("risk_profile", {}).get("time_horizon", 0),
                "max_position": soul2.get("risk_profile", {}).get("max_position", 0),
                "stop_loss": soul2.get("risk_profile", {}).get("stop_loss", 0),
                "take_profit": soul2.get("risk_profile", {}).get("take_profit", 0),
                "tiandao_weight": soul2.get("direction", {}).get("tiandao_weight", 0),
                "minxin_weight": soul2.get("direction", {}).get("minxin_weight", 0),
                "tiandao_count": len(soul2.get("keywords", {}).get("tiandao", [])),
                "minxin_count": len(soul2.get("keywords", {}).get("minxin", [])),
                "principles": soul2.get("values", {}).get("profiles", [{}])[0].get("principles", []) if soul2.get("values", {}).get("profiles") else [],
            },
            "differences": self._compute_differences(soul1, soul2),
        }

        return comparison

    def _compute_differences(self, soul1: Dict, soul2: Dict) -> List[str]:
        """计算两个灵魂的差异"""
        diffs = []

        s1_direction = soul1.get("direction", {})
        s2_direction = soul2.get("direction", {})

        if s1_direction.get("type") != s2_direction.get("type"):
            diffs.append(f"价值方向: {s1_direction.get('label')} → {s2_direction.get('label')}")

        s1_domains = set(soul1.get("domains", {}).get("focused", []))
        s2_domains = set(soul2.get("domains", {}).get("focused", []))
        if s1_domains != s2_domains:
            diffs.append(f"关注行业: {', '.join(s1_domains)} → {', '.join(s2_domains)}")

        s1_risk = soul1.get("risk_profile", {}).get("risk_preference", 0)
        s2_risk = soul2.get("risk_profile", {}).get("risk_preference", 0)
        if abs(s1_risk - s2_risk) > 0.1:
            diffs.append(f"风险偏好: {s1_risk} → {s2_risk}")

        s1_tiandao = s1_direction.get("tiandao_weight", 0)
        s2_tiandao = s2_direction.get("tiandao_weight", 0)
        if abs(s1_tiandao - s2_tiandao) > 0.1:
            diffs.append(f"天道权重: {s1_tiandao} → {s2_tiandao}")

        s1_minxin = s1_direction.get("minxin_weight", 0)
        s2_minxin = s2_direction.get("minxin_weight", 0)
        if abs(s1_minxin - s2_minxin) > 0.1:
            diffs.append(f"民心权重: {s1_minxin} → {s2_minxin}")

        s1_position = soul1.get("risk_profile", {}).get("max_position", 0)
        s2_position = soul2.get("risk_profile", {}).get("max_position", 0)
        if abs(s1_position - s2_position) > 0.05:
            diffs.append(f"仓位上限: {s1_position*100:.0f}% → {s2_position*100:.0f}%")

        s1_stop = soul1.get("risk_profile", {}).get("stop_loss", 0)
        s2_stop = soul2.get("risk_profile", {}).get("stop_loss", 0)
        if abs(s1_stop - s2_stop) > 0.01:
            diffs.append(f"止损幅度: {s1_stop*100:.0f}% → {s2_stop*100:.0f}%")

        return diffs

    def get_preset_templates(self) -> List[Dict[str, Any]]:
        """获取预设模板列表"""
        return [
            {
                "name": name,
                "icon": template["icon"],
                "description": template["description"],
                "direction": template["direction"],
                "risk_level": template["risk_level"],
                "domains": template["domains"],
            }
            for name, template in self.PRESET_TEMPLATES.items()
        ]

    def get_status(self) -> Dict[str, Any]:
        """获取系统状态"""
        active_soul = self.get_active_soul()
        all_souls = self.list_souls()

        return {
            "has_active": active_soul is not None,
            "active_soul": active_soul,
            "total_souls": len(all_souls),
            "has_custom_config": self.config_loader.has_custom_config(),
        }


def get_soul_manager() -> SoulManager:
    """获取灵魂管理器单例"""
    return SoulManager()
