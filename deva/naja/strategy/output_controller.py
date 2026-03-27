"""策略结果分发控制器

允许策略主动控制结果如何分发到各个系统：
- SignalStream: 原始结果存储
- Radar: 技术指标检测  
- Memory: 语义/叙事分析
- Bandit: 交易信号

使用方式：
    # 在策略中
    self.set_output_targets({
        'signal': True,      # 发送到信号流
        'radar': True,      # 发送给雷达检测
        'memory': True,     # 发送给记忆分析
        'bandit': True,     # 作为交易信号
    })
"""

from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field
from deva import NB


OUTPUT_TARGETS_TABLE = "naja_strategy_output_targets"


@dataclass
class OutputConfig:
    """输出配置"""
    strategy_id: str
    signal: bool = True      # 发送到信号流
    radar: bool = True       # 发送到雷达
    memory: bool = True      # 发送到记忆
    bandit: bool = False     # 作为交易信号（默认关闭）
    radar_tags: List[str] = field(default_factory=list)  # 雷达标签
    memory_tags: List[str] = field(default_factory=list)  # 记忆标签


class StrategyOutputController:
    """策略输出控制器

    管理策略结果如何分发到各个系统。
    支持配置化和运行时修改。

    ================================================================================
    单例模式说明：为什么使用单例
    ================================================================================
    1. 全局输出配置：策略输出的路由配置是全局的，所有策略的结果都通过
       同一个控制器分发。如果存在多个实例，可能导致分发不一致。

    2. 状态一致性：输出配置、运行时修改等需要在全系统保持一致。

    3. 资源管理：数据库连接（NB）是系统资源，应该全局唯一。

    4. 这是流式计算系统的设计选择，不是过度工程。
    ================================================================================
    """

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._db = NB(OUTPUT_TARGETS_TABLE)
        self._configs: Dict[str, OutputConfig] = {}
        self._load_configs()
        self._initialized = True
    
    def _load_configs(self):
        """从数据库加载配置"""
        try:
            data = self._db.get("all_configs")
            if isinstance(data, dict):
                for strategy_id, config_data in data.items():
                    self._configs[strategy_id] = OutputConfig(**config_data)
        except Exception:
            pass
    
    def _save_configs(self):
        """保存配置到数据库"""
        try:
            data = {k: vars(v) for k, v in self._configs.items()}
            self._db["all_configs"] = data
        except Exception:
            pass
    
    def get_config(self, strategy_id: str) -> OutputConfig:
        """获取策略的输出配置"""
        if strategy_id not in self._configs:
            self._configs[strategy_id] = OutputConfig(strategy_id=strategy_id)
            self._save_configs()
        return self._configs[strategy_id]
    
    def set_config(self, config: OutputConfig):
        """设置策略的输出配置"""
        self._configs[config.strategy_id] = config
        self._save_configs()
    
    def update_targets(self, strategy_id: str, **targets):
        """快速更新目标系统"""
        config = self.get_config(strategy_id)
        for key, value in targets.items():
            if hasattr(config, key):
                setattr(config, key, value)
        self._save_configs()
    
    def should_send_to(self, strategy_id: str, target: str) -> bool:
        """检查是否应该发送到目标系统"""
        config = self.get_config(strategy_id)
        return getattr(config, target, False)
    
    def get_targets(self, strategy_id: str) -> Set[str]:
        """获取策略的所有目标系统"""
        config = self.get_config(strategy_id)
        targets = set()
        if config.signal:
            targets.add("signal")
        if config.radar:
            targets.add("radar")
        if config.memory:
            targets.add("memory")
        if config.bandit:
            targets.add("bandit")
        return targets


_controller: Optional[StrategyOutputController] = None


def get_output_controller() -> StrategyOutputController:
    """获取输出控制器单例"""
    global _controller
    if _controller is None:
        _controller = StrategyOutputController()
    return _controller


def get_strategy_targets(strategy_id: str) -> Set[str]:
    """便捷函数：获取策略的目标系统"""
    return get_output_controller().get_targets(strategy_id)


def should_send_to_radar(strategy_id: str) -> bool:
    """便捷函数：是否发送到雷达"""
    return get_output_controller().should_send_to(strategy_id, "radar")


def should_send_to_memory(strategy_id: str) -> bool:
    """便捷函数：是否发送到记忆"""
    return get_output_controller().should_send_to(strategy_id, "memory")


def should_send_to_bandit(strategy_id: str) -> bool:
    """便捷函数：是否作为交易信号"""
    return get_output_controller().should_send_to(strategy_id, "bandit")
