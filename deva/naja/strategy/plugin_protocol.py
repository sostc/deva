"""标准插件接口协议定义

本模块定义了策略插件的标准接口，所有插件应实现以下协议之一：
- ProtocolA: 基础数据流接口 (on_data + get_signal)
- ProtocolB: 记录级处理接口 (on_record)
- ProtocolC: 窗口级处理接口 (on_window)
- ProtocolD: 完整生命周期接口 (继承 BaseStrategy)

使用方式:
    from deva.naja.strategy.plugin_protocol import (
        ProtocolA, ProtocolB, ProtocolC, ProtocolD, PluginMetadata
    )

    class MyPlugin(ProtocolA):
        def on_data(self, data):
            ...

        def get_signal(self):
            ...

    # 注册插件
    PluginRegistry.register("my_plugin", MyPlugin)
"""

from __future__ import annotations

import inspect
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional, Protocol, runtime_checkable


class PluginMetadata:
    """插件元数据"""

    def __init__(
        self,
        name: str,
        version: str = "1.0.0",
        description: str = "",
        author: str = "",
        tags: Optional[List[str]] = None,
        config_schema: Optional[Dict] = None,
    ):
        self.name = name
        self.version = version
        self.description = description
        self.author = author
        self.tags = tags or []
        self.config_schema = config_schema or {}


@runtime_checkable
class ProtocolA(Protocol):
    """基础数据流协议

    适用于: 简单流式处理，每次输入产生一个信号输出
    场景: 实时指标计算、简单过滤、基础信号生成
    """

    def on_data(self, data: Any) -> Any:
        """处理输入数据"""
        ...

    def get_signal(self) -> Any:
        """获取当前信号"""
        ...


@runtime_checkable
class ProtocolB(Protocol):
    """记录级处理协议

    适用于: 需要逐条处理记录并返回结果的场景
    场景: 记录增强、字段转换、多输出拆分
    """

    def on_record(self, record: Dict) -> Any:
        """处理单条记录"""
        ...


@runtime_checkable
class ProtocolC(Protocol):
    """窗口级处理协议

    适用于: 需要基于窗口/批次数据进行处理的场景
    场景: 滑动窗口统计、批量异常检测、模式识别
    """

    def on_window(self, records: List[Dict]) -> Any:
        """处理窗口数据"""
        ...


@runtime_checkable
class ProtocolD(Protocol):
    """完整生命周期协议

    适用于: 需要完整生命周期管理的高级策略
    场景: 需要状态管理、参数更新、启动停止回调的复杂策略

    继承自 BaseStrategy 的所有功能
    """

    def init(self, config: Dict[str, Any]) -> None:
        """初始化策略"""
        ...

    def on_data(self, data: Any) -> None:
        """处理输入数据"""
        ...

    def get_signal(self) -> Any:
        """获取当前信号"""
        ...

    def update_params(self, params: Dict[str, Any]) -> None:
        """更新参数"""
        ...

    def reset(self) -> None:
        """重置状态"""
        ...

    def on_start(self) -> None:
        """启动回调"""
        ...

    def on_stop(self) -> None:
        """停止回调"""
        ...

    def close(self) -> None:
        """关闭资源"""
        ...


class PluginRegistry:
    """插件注册表

    提供插件的注册、发现和验证功能
    """

    _plugins: Dict[str, type] = {}
    _metadata: Dict[str, PluginMetadata] = {}

    @classmethod
    def register(
        cls,
        name: str,
        plugin_class: type,
        metadata: Optional[PluginMetadata] = None,
    ) -> None:
        """注册插件

        Args:
            name: 插件名称
            plugin_class: 插件类
            metadata: 插件元数据
        """
        cls._plugins[name] = plugin_class
        if metadata:
            cls._metadata[name] = metadata

    @classmethod
    def get(cls, name: str) -> Optional[type]:
        """获取插件类"""
        return cls._plugins.get(name)

    @classmethod
    def get_metadata(cls, name: str) -> Optional[PluginMetadata]:
        """获取插件元数据"""
        return cls._metadata.get(name)

    @classmethod
    def list_plugins(cls) -> List[str]:
        """列出所有已注册插件"""
        return list(cls._plugins.keys())

    @classmethod
    def detect_protocol(cls, plugin: Any) -> str:
        """检测插件实现的协议类型

        Args:
            plugin: 插件实例

        Returns:
            协议名称: "ProtocolA", "ProtocolB", "ProtocolC", "ProtocolD", "Unknown"
        """
        if isinstance(plugin, ProtocolD):
            return "ProtocolD"
        if isinstance(plugin, ProtocolC):
            return "ProtocolC"
        if isinstance(plugin, ProtocolB):
            return "ProtocolB"
        if isinstance(plugin, ProtocolA):
            return "ProtocolA"
        return "Unknown"

    @classmethod
    def validate_plugin(cls, plugin: Any) -> Dict[str, Any]:
        """验证插件实现的完整性

        Args:
            plugin: 插件实例

        Returns:
            验证结果: {
                "valid": bool,
                "protocol": str,
                "missing_methods": List[str],
                "warnings": List[str]
            }
        """
        result = {
            "valid": False,
            "protocol": "Unknown",
            "missing_methods": [],
            "warnings": [],
        }

        protocol = cls.detect_protocol(plugin)
        result["protocol"] = protocol

        if protocol == "Unknown":
            result["warnings"].append("插件未实现任何已知协议")
            return result

        required_methods = {
            "ProtocolA": ["on_data", "get_signal"],
            "ProtocolB": ["on_record"],
            "ProtocolC": ["on_window"],
            "ProtocolD": [
                "init",
                "on_data",
                "get_signal",
                "update_params",
                "reset",
                "on_start",
                "on_stop",
                "close",
            ],
        }

        for method in required_methods.get(protocol, []):
            if not hasattr(plugin, method):
                result["missing_methods"].append(method)

        result["valid"] = len(result["missing_methods"]) == 0
        return result


def create_plugin_metadata(
    name: str,
    version: str = "1.0.0",
    description: str = "",
    author: str = "",
    tags: Optional[List[str]] = None,
    config_schema: Optional[Dict] = None,
) -> PluginMetadata:
    """创建插件元数据的便捷函数

    Args:
        name: 插件名称
        version: 版本号
        description: 描述
        author: 作者
        tags: 标签
        config_schema: 配置 schema

    Returns:
        PluginMetadata: 插件元数据
    """
    return PluginMetadata(
        name=name,
        version=version,
        description=description,
        author=author,
        tags=tags,
        config_schema=config_schema,
    )


def implements_protocol(plugin: Any, protocol: str) -> bool:
    """检查插件是否实现指定协议

    Args:
        plugin: 插件实例
        protocol: 协议名称 ("ProtocolA", "ProtocolB", "ProtocolC", "ProtocolD")

    Returns:
        bool: 是否实现
    """
    protocol_map = {
        "ProtocolA": ProtocolA,
        "ProtocolB": ProtocolB,
        "ProtocolC": ProtocolC,
        "ProtocolD": ProtocolD,
    }
    protocol_class = protocol_map.get(protocol)
    if protocol_class is None:
        return False
    return isinstance(plugin, protocol_class)
