"""
Soul Manager - 多灵魂管理系统

管理多个投资哲学/灵魂方案，支持：
- 创建/删除/切换灵魂
- 导出/导入灵魂配置
- 预设模板管理

使用方式：
    from soul_manager import SoulManager

    manager = SoulManager()
    souls = manager.list_souls()
    manager.create_soul(name="激进型", philosophy={...})
    manager.activate_soul("激进型")
    manager.export_soul("激进型", "/path/to/export.json")
"""

import os
import json
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field

log = logging.getLogger(__name__)


@dataclass
class SoulProfile:
    """灵魂配置"""
    id: str
    name: str
    icon: str
    description: str
    philosophy: Dict[str, Any]
    philosophy_config: Dict[str, Any]
    created_at: float
    last_used: float
    is_active: bool = False


class SoulManager:
    """
    多灵魂管理器

    管理多个灵魂配置，支持创建、切换、导出、导入
    """

    SOULS_DIR = "/Users/spark/pycharmproject/deva/.deva/souls"
    ACTIVE_SOUL_FILE = "/Users/spark/pycharmproject/deva/.deva/active_soul.txt"

    PRESET_TEMPLATES = {
        "🚀 激进型": {
            "icon": "🚀",
            "name": "激进型",
            "description": "大机会，重仓出击",
            "philosophy": {
                "mission": "重仓出击，all in 天道！",
                "tiandao": "TOKEN消耗、大模型限流卡脖子、AI效率提升",
                "minxin": "市场行情、股价涨跌、舆论情绪",
                "direction": "creative",
                "risk_preference": 0.9,
                "time_horizon": 0.9,
                "domains": ["AI", "芯片"],
            }
        },
        "🛡️ 保守型": {
            "icon": "🛡️",
            "name": "保守型",
            "description": "熊市，不确定性高时使用",
            "philosophy": {
                "mission": "安全第一，等待确定性机会",
                "tiandao": "TOKEN消耗、大模型限流卡脖子、AI效率提升",
                "minxin": "市场行情、股价涨跌、舆论情绪",
                "direction": "creative",
                "risk_preference": 0.2,
                "time_horizon": 0.9,
                "domains": ["AI", "芯片"],
            }
        },
        "🎯 专注型": {
            "icon": "🎯",
            "name": "专注型",
            "description": "明确趋势，顺势而为",
            "philosophy": {
                "mission": "跟随趋势，精准出击",
                "tiandao": "TOKEN消耗、大模型限流卡脖子、AI效率提升",
                "minxin": "市场行情、股价涨跌、舆论情绪",
                "direction": "speculative",
                "risk_preference": 0.5,
                "time_horizon": 0.5,
                "domains": ["AI", "芯片", "新能源"],
            }
        },
        "💡 灵活型": {
            "icon": "💡",
            "name": "灵活型",
            "description": "震荡市，快速切换",
            "philosophy": {
                "mission": "灵活应对，快速切换",
                "tiandao": "TOKEN消耗、大模型限流卡脖子、AI效率提升",
                "minxin": "市场行情、股价涨跌、舆论情绪",
                "direction": "balanced",
                "risk_preference": 0.5,
                "time_horizon": 0.5,
                "domains": ["AI", "芯片", "新能源", "医药"],
            }
        },
    }

    def __init__(self):
        self.base_path = "/Users/spark/pycharmproject/deva"
        self.souls: Dict[str, SoulProfile] = {}
        self.active_soul_id: Optional[str] = None
        self._ensure_dirs()
        self._load_souls()
        self._load_active_soul()

    def _ensure_dirs(self):
        """确保目录存在"""
        os.makedirs(self.SOULS_DIR, exist_ok=True)
        os.makedirs(self.base_path + "/.deva", exist_ok=True)

    def _load_souls(self):
        """加载所有灵魂"""
        if not os.path.exists(self.SOULS_DIR):
            return

        for filename in os.listdir(self.SOULS_DIR):
            if filename.endswith(".json"):
                filepath = os.path.join(self.SOULS_DIR, filename)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    soul = SoulProfile(
                        id=data["id"],
                        name=data["name"],
                        icon=data.get("icon", "🧠"),
                        description=data.get("description", ""),
                        philosophy=data.get("philosophy", {}),
                        philosophy_config=data.get("philosophy_config", {}),
                        created_at=data.get("created_at", 0),
                        last_used=data.get("last_used", 0),
                        is_active=False,
                    )
                    self.souls[soul.id] = soul
                except Exception as e:
                    log.warning(f"加载灵魂失败 {filename}: {e}")

    def _load_active_soul(self):
        """加载激活的灵魂"""
        if os.path.exists(self.ACTIVE_SOUL_FILE):
            try:
                with open(self.ACTIVE_SOUL_FILE, "r", encoding="utf-8") as f:
                    self.active_soul_id = f.read().strip()
                if self.active_soul_id in self.souls:
                    self.souls[self.active_soul_id].is_active = True
            except Exception as e:
                log.warning(f"加载激活灵魂失败: {e}")

    def _save_soul(self, soul: SoulProfile):
        """保存灵魂到文件"""
        filepath = os.path.join(self.SOULS_DIR, f"{soul.id}.json")
        data = {
            "id": soul.id,
            "name": soul.name,
            "icon": soul.icon,
            "description": soul.description,
            "philosophy": soul.philosophy,
            "philosophy_config": soul.philosophy_config,
            "created_at": soul.created_at,
            "last_used": soul.last_used,
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _save_active_soul(self):
        """保存激活的灵魂ID"""
        with open(self.ACTIVE_SOUL_FILE, "w", encoding="utf-8") as f:
            f.write(self.active_soul_id or "")

    def list_souls(self) -> List[Dict[str, Any]]:
        """列出所有灵魂"""
        result = []
        for soul in self.souls.values():
            result.append({
                "id": soul.id,
                "name": soul.name,
                "icon": soul.icon,
                "description": soul.description,
                "is_active": soul.is_active,
                "last_used": soul.last_used,
                "philosophy": soul.philosophy,
            })
        return result

    def get_active_soul(self) -> Optional[Dict[str, Any]]:
        """获取当前激活的灵魂"""
        if not self.active_soul_id or self.active_soul_id not in self.souls:
            return None

        soul = self.souls[self.active_soul_id]
        return {
            "id": soul.id,
            "name": soul.name,
            "icon": soul.icon,
            "description": soul.description,
            "is_active": True,
            "philosophy": soul.philosophy,
            "philosophy_config": soul.philosophy_config,
        }

    def create_soul(
        self,
        name: str,
        philosophy: Dict[str, Any],
        icon: str = "🧠",
        description: str = "",
    ) -> SoulProfile:
        """
        创建新灵魂

        Args:
            name: 灵魂名称
            philosophy: 投资理念配置
            icon: 图标
            description: 描述

        Returns:
            创建的灵魂
        """
        import time
        import uuid

        soul_id = str(uuid.uuid4())[:8]

        soul = SoulProfile(
            id=soul_id,
            name=name,
            icon=icon,
            description=description,
            philosophy=philosophy,
            philosophy_config={},
            created_at=time.time(),
            last_used=time.time(),
            is_active=False,
        )

        self.souls[soul_id] = soul
        self._save_soul(soul)

        log.info(f"创建灵魂: {name} ({soul_id})")
        return soul

    def create_from_preset(self, preset_name: str) -> Optional[SoulProfile]:
        """
        从预设模板创建灵魂

        Args:
            preset_name: 预设模板名称

        Returns:
            创建的灵魂，或None
        """
        if preset_name not in self.PRESET_TEMPLATES:
            log.warning(f"未知预设模板: {preset_name}")
            return None

        template = self.PRESET_TEMPLATES[preset_name]
        return self.create_soul(
            name=template["name"],
            philosophy=template["philosophy"],
            icon=template["icon"],
            description=template["description"],
        )

    def activate_soul(self, soul_id: str) -> bool:
        """
        激活灵魂

        Args:
            soul_id: 灵魂ID或名称

        Returns:
            是否成功
        """
        import time

        if soul_id in self.souls:
            target = self.souls[soul_id]
        else:
            for soul in self.souls.values():
                if soul.name == soul_id:
                    target = soul
                    break
            else:
                log.warning(f"未找到灵魂: {soul_id}")
                return False

        for soul in self.souls.values():
            soul.is_active = False

        target.is_active = True
        target.last_used = time.time()
        self.active_soul_id = target.id

        self._save_soul(target)
        self._save_active_soul()

        log.info(f"激活灵魂: {target.name}")
        return True

    def delete_soul(self, soul_id: str) -> bool:
        """
        删除灵魂

        Args:
            soul_id: 灵魂ID或名称

        Returns:
            是否成功
        """
        if soul_id in self.souls:
            target = self.souls[soul_id]
        else:
            for soul in self.souls.values():
                if soul.name == soul_id:
                    target = soul
                    break
            else:
                log.warning(f"未找到灵魂: {soul_id}")
                return False

        if target.is_active:
            log.warning("不能删除当前激活的灵魂")
            return False

        filepath = os.path.join(self.SOULS_DIR, f"{target.id}.json")
        if os.path.exists(filepath):
            os.remove(filepath)

        del self.souls[target.id]
        log.info(f"删除灵魂: {target.name}")
        return True

    def export_soul(self, soul_id: str, filepath: str) -> bool:
        """
        导出灵魂到文件

        Args:
            soul_id: 灵魂ID或名称
            filepath: 导出路径

        Returns:
            是否成功
        """
        if soul_id in self.souls:
            soul = self.souls[soul_id]
        else:
            for soul in self.souls.values():
                if soul.name == soul_id:
                    soul = soul
                    break
            else:
                log.warning(f"未找到灵魂: {soul_id}")
                return False

        data = {
            "id": soul.id,
            "name": soul.name,
            "icon": soul.icon,
            "description": soul.description,
            "philosophy": soul.philosophy,
            "philosophy_config": soul.philosophy_config,
            "created_at": soul.created_at,
            "exported_at": __import__("time").time(),
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        log.info(f"导出灵魂: {soul.name} -> {filepath}")
        return True

    def import_soul(self, filepath: str, new_name: Optional[str] = None) -> Optional[SoulProfile]:
        """
        从文件导入灵魂

        Args:
            filepath: 导入文件路径
            new_name: 新名称（可选）

        Returns:
            导入的灵魂，或None
        """
        import time
        import uuid

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            soul_id = str(uuid.uuid4())[:8]

            soul = SoulProfile(
                id=soul_id,
                name=new_name or data["name"],
                icon=data.get("icon", "🧠"),
                description=data.get("description", ""),
                philosophy=data.get("philosophy", {}),
                philosophy_config=data.get("philosophy_config", {}),
                created_at=time.time(),
                last_used=time.time(),
                is_active=False,
            )

            self.souls[soul_id] = soul
            self._save_soul(soul)

            log.info(f"导入灵魂: {soul.name} ({soul_id})")
            return soul

        except Exception as e:
            log.error(f"导入灵魂失败: {e}")
            return None

    def apply_soul_to_system(self, soul_id: str) -> Dict[str, Any]:
        """
        将灵魂配置应用到系统

        Args:
            soul_id: 灵魂ID或名称

        Returns:
            应用结果
        """
        if soul_id in self.souls:
            soul = self.souls[soul_id]
        else:
            for s in self.souls.values():
                if s.name == soul_id:
                    soul = s
                    break
            else:
                return {"status": "error", "message": f"未找到灵魂: {soul_id}"}

        from generate_philosophy_config import PhilosophyConfigurator

        configurator = PhilosophyConfigurator()
        config = configurator.generate(soul.philosophy)

        if not soul.philosophy_config:
            soul.philosophy_config = {
                "soul": config.soul,
                "values": config.values,
                "narrative": config.narrative,
                "config": config.config,
            }
            self._save_soul(soul)

        results = configurator.apply(config)

        self.activate_soul(soul.id)

        return {
            "status": "success",
            "soul_name": soul.name,
            "results": results,
        }

    def get_preset_templates(self) -> List[Dict[str, Any]]:
        """获取预设模板列表"""
        return [
            {
                "name": name,
                "icon": template["icon"],
                "description": template["description"],
                "philosophy": template["philosophy"],
            }
            for name, template in self.PRESET_TEMPLATES.items()
        ]


def main():
    """命令行入口"""
    manager = SoulManager()

    print("🧠 灵魂管理系统")
    print("=" * 40)

    print("\n【预设模板】")
    for template in manager.get_preset_templates():
        print(f"  {template['icon']} {template['name']}: {template['description']}")

    print("\n【现有灵魂】")
    souls = manager.list_souls()
    if not souls:
        print("  (空)")
    for soul in souls:
        active = " [激活中]" if soul["is_active"] else ""
        print(f"  {soul['icon']} {soul['name']}{active}")

    print("\n【操作】")
    print("  1. 创建灵魂")
    print("  2. 从模板创建")
    print("  3. 激活灵魂")
    print("  4. 导出灵魂")
    print("  5. 导入灵魂")
    print("  6. 删除灵魂")
    print("  0. 退出")


if __name__ == "__main__":
    main()
