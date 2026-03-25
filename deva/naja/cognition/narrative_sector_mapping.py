"""Narrative to Sector Mapping - 叙事主题到板块的映射配置

职责:
- 定义叙事主题到市场板块的映射关系
- 支持多对多映射（一个叙事主题可以关联多个板块）
- 提供配置开关来控制联动功能

使用场景:
- NarrativeTracker 识别叙事主题后，映射到实际的 sector_id
- CrossSignalAnalyzer 实现"舆情 → 板块轮动"的联动
"""

from typing import Dict, List

NARRATIVE_TO_SECTOR_LINK: Dict[str, List[str]] = {
    "AI": ["semiconductor", "software", "internet"],
    "芯片": ["semiconductor", "hardware"],
    "新能源": ["new_energy", "auto", "power_equipment"],
    "医药": ["pharma", "medical_device", "healthcare"],
    "华为": ["semiconductor", "consumer_electronics", "software"],
    "中美关系": ["macro", "export", "_import"],
    "地缘政治": ["macro", "defense", "energy"],
}

SECTOR_TO_NARRATIVE_REVERSE: Dict[str, List[str]] = {
    "semiconductor": ["AI", "芯片", "华为"],
    "software": ["AI", "华为"],
    "internet": ["AI"],
    "hardware": ["芯片"],
    "new_energy": ["新能源"],
    "auto": ["新能源"],
    "power_equipment": ["新能源"],
    "pharma": ["医药"],
    "medical_device": ["医药"],
    "healthcare": ["医药"],
    "consumer_electronics": ["华为"],
    "macro": ["中美关系", "地缘政治"],
    "defense": ["地缘政治"],
    "energy": ["地缘政治"],
    "export": ["中美关系"],
    "import": ["中美关系"],
}

NARRATIVE_SECTOR_LINKING_ENABLED: bool = True


def get_linked_sectors(narrative: str) -> List[str]:
    """获取叙事主题关联的板块列表"""
    if not NARRATIVE_SECTOR_LINKING_ENABLED:
        return []
    return NARRATIVE_TO_SECTOR_LINK.get(narrative, [])


def get_linked_narratives(sector: str) -> List[str]:
    """获取板块关联的叙事主题列表"""
    if not NARRATIVE_SECTOR_LINKING_ENABLED:
        return []
    return SECTOR_TO_NARRATIVE_REVERSE.get(sector, [])


def is_linking_enabled() -> bool:
    """检查联动功能是否启用"""
    return NARRATIVE_SECTOR_LINKING_ENABLED


def set_linking_enabled(enabled: bool):
    """设置联动功能开关"""
    global NARRATIVE_SECTOR_LINKING_ENABLED
    NARRATIVE_SECTOR_LINKING_ENABLED = enabled
