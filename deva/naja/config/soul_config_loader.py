"""
SoulConfigLoader - 灵魂配置加载器

支持：
- 从配置文件加载灵魂配置
- 回退到硬编码默认值
- 配置合并策略
- 配置验证

配置加载优先级：
1. 灵魂配置文件 (.deva/naja/config/souls/[active].json)
2. 默认配置文件 (.deva/naja/config/souls/default.json)
3. 硬编码默认值
"""

import os
import json
import logging
from typing import Dict, List, Any, Optional

log = logging.getLogger(__name__)


class SoulConfigLoader:
    """灵魂配置加载器，支持回退机制"""

    BASE_PATH = "/Users/spark/pycharmproject/deva/deva/naja/config"
    SOULS_DIR = BASE_PATH + "/souls"
    NARRATIVE_DIR = BASE_PATH + "/narrative"
    VALUES_DIR = BASE_PATH + "/values"
    SYSTEM_DIR = BASE_PATH + "/system"
    ACTIVE_FILE = SOULS_DIR + "/active.txt"

    _instance: Optional["SoulConfigLoader"] = None
    _cached_config: Optional[Dict[str, Any]] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._ensure_dirs()

    def _ensure_dirs(self):
        """确保配置目录存在"""
        os.makedirs(self.SOULS_DIR, exist_ok=True)
        os.makedirs(self.NARRATIVE_DIR, exist_ok=True)
        os.makedirs(self.VALUES_DIR, exist_ok=True)
        os.makedirs(self.SYSTEM_DIR, exist_ok=True)

    def get_active_soul_id(self) -> Optional[str]:
        """获取当前激活的灵魂ID"""
        try:
            if os.path.exists(self.ACTIVE_FILE):
                with open(self.ACTIVE_FILE, "r", encoding="utf-8") as f:
                    soul_id = f.read().strip()
                    if soul_id:
                        return soul_id
        except Exception as e:
            log.warning(f"读取激活灵魂ID失败: {e}")
        return None

    def set_active_soul_id(self, soul_id: str):
        """设置当前激活的灵魂ID"""
        try:
            with open(self.ACTIVE_FILE, "w", encoding="utf-8") as f:
                f.write(soul_id)
            self._cached_config = None
            log.info(f"激活灵魂已切换: {soul_id}")
        except Exception as e:
            log.error(f"设置激活灵魂ID失败: {e}")
            raise

    def load_soul_config(self, soul_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        加载灵魂配置

        Args:
            soul_id: 灵魂ID，不指定则加载当前激活的灵魂

        Returns:
            灵魂配置字典，加载失败返回None
        """
        if soul_id is None:
            soul_id = self.get_active_soul_id()

        if soul_id is None:
            log.warning("没有激活的灵魂配置")
            return None

        config_path = os.path.join(self.SOULS_DIR, f"{soul_id}.json")

        try:
            if not os.path.exists(config_path):
                log.warning(f"灵魂配置文件不存在: {config_path}")
                return None

            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)

            log.info(f"成功加载灵魂配置: {soul_id}")
            return config

        except json.JSONDecodeError as e:
            log.error(f"灵魂配置JSON解析失败: {config_path} - {e}")
            return None
        except Exception as e:
            log.error(f"加载灵魂配置失败: {config_path} - {e}")
            return None

    def save_soul_config(self, soul_id: str, config: Dict[str, Any]):
        """
        保存灵魂配置

        Args:
            soul_id: 灵魂ID
            config: 配置字典
        """
        config_path = os.path.join(self.SOULS_DIR, f"{soul_id}.json")

        try:
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            log.info(f"成功保存灵魂配置: {soul_id}")
        except Exception as e:
            log.error(f"保存灵魂配置失败: {config_path} - {e}")
            raise

    def load_keywords(self, soul_id: Optional[str] = None) -> Dict[str, List[str]]:
        """
        加载关键词配置

        Args:
            soul_id: 灵魂ID

        Returns:
            关键词字典，加载失败返回None触发使用默认
        """
        config = self.load_soul_config(soul_id)

        if config is None:
            return None

        if "keywords" in config:
            return config["keywords"]

        return None

    def load_values_profiles(self, soul_id: Optional[str] = None) -> Optional[List[Dict[str, Any]]]:
        """
        加载价值观配置

        Args:
            soul_id: 灵魂ID

        Returns:
            价值观配置列表，加载失败返回None
        """
        config = self.load_soul_config(soul_id)

        if config is None:
            return None

        if "values" in config and "profiles" in config["values"]:
            return config["values"]["profiles"]

        return None

    def load_supply_chain(self, soul_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        加载供应链配置

        Args:
            soul_id: 灵魂ID

        Returns:
            供应链配置字典，加载失败返回None
        """
        config = self.load_soul_config(soul_id)

        if config is None:
            return None

        return config.get("supply_chain")

    def get_full_config(self, soul_id: Optional[str] = None) -> Dict[str, Any]:
        """
        获取完整配置（用于系统初始化）

        加载失败时会记录日志但不抛出异常，返回空字典让调用方使用默认值

        Args:
            soul_id: 灵魂ID

        Returns:
            完整配置字典
        """
        config = self.load_soul_config(soul_id)

        if config is None:
            log.warning("使用空配置，系统将依赖硬编码默认值")
            return {}

        return config

    def validate_config(self, config: Dict[str, Any]) -> List[str]:
        """
        验证配置完整性

        Args:
            config: 配置字典

        Returns:
            错误列表，空列表表示配置有效
        """
        errors = []
        required_fields = ["soul_id", "soul_name", "direction", "domains", "risk_profile", "philosophy"]

        for field in required_fields:
            if field not in config:
                errors.append(f"缺少必需字段: {field}")

        if "direction" in config:
            if "type" not in config["direction"]:
                errors.append("direction缺少type字段")

        if "domains" in config:
            if "focused" not in config["domains"]:
                errors.append("domains缺少focused字段")

        return errors

    def merge_keywords(
        self,
        soul_keywords: Optional[Dict[str, List[str]]],
        default_keywords: Dict[str, List[str]],
        merge_strategy: str = "merge"
    ) -> Dict[str, List[str]]:
        """
        合并关键词配置

        Args:
            soul_keywords: 灵魂配置的关键词
            default_keywords: 默认关键词
            merge_strategy: merge=合并, replace=替换

        Returns:
            合并后的关键词字典
        """
        if soul_keywords is None:
            return default_keywords

        if merge_strategy == "replace":
            return soul_keywords

        result = dict(default_keywords)

        for category, keywords in soul_keywords.items():
            if category in result:
                result[category] = list(set(result[category] + keywords))
            else:
                result[category] = keywords

        return result

    def list_soul_ids(self) -> List[str]:
        """列出所有已保存的灵魂ID"""
        try:
            files = os.listdir(self.SOULS_DIR)
            return [f.replace(".json", "") for f in files if f.endswith(".json")]
        except Exception as e:
            log.error(f"列出灵魂失败: {e}")
            return []

    def delete_soul_config(self, soul_id: str) -> bool:
        """删除灵魂配置"""
        config_path = os.path.join(self.SOULS_DIR, f"{soul_id}.json")

        try:
            if os.path.exists(config_path):
                os.remove(config_path)
                log.info(f"删除灵魂配置: {soul_id}")

                if self.get_active_soul_id() == soul_id:
                    with open(self.ACTIVE_FILE, "w", encoding="utf-8") as f:
                        f.write("")

                return True
            return False
        except Exception as e:
            log.error(f"删除灵魂配置失败: {e}")
            return False

    def export_soul(self, soul_id: str, filepath: str) -> bool:
        """导出灵魂配置到文件"""
        config = self.load_soul_config(soul_id)

        if config is None:
            return False

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            log.info(f"导出灵魂配置: {soul_id} -> {filepath}")
            return True
        except Exception as e:
            log.error(f"导出灵魂配置失败: {e}")
            return False

    def import_soul(self, filepath: str, soul_id: Optional[str] = None) -> Optional[str]:
        """从文件导入灵魂配置"""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                config = json.load(f)

            new_soul_id = soul_id or config.get("soul_id") or os.path.basename(filepath).replace(".json", "")

            config["soul_id"] = new_soul_id

            self.save_soul_config(new_soul_id, config)
            log.info(f"导入灵魂配置: {filepath} -> {new_soul_id}")

            return new_soul_id

        except Exception as e:
            log.error(f"导入灵魂配置失败: {e}")
            return None

    def has_custom_config(self) -> bool:
        """检查是否存在自定义配置"""
        active_id = self.get_active_soul_id()
        if active_id is None:
            return False

        config_path = os.path.join(self.SOULS_DIR, f"{active_id}.json")
        return os.path.exists(config_path)


def get_config_loader() -> SoulConfigLoader:
    """获取配置加载器单例"""
    return SoulConfigLoader()
