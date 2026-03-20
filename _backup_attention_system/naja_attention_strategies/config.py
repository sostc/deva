"""
注意力策略配置系统

提供策略配置加载、保存和管理功能
"""

import json
import os
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from pathlib import Path


@dataclass
class StrategySettings:
    """策略详细配置"""
    # 执行控制
    enabled: bool = True
    priority: int = 5
    min_global_attention: float = 0.0
    min_symbol_weight: float = 1.0
    max_positions: int = 10
    cooldown_period: float = 60.0
    
    # 自定义参数
    custom_params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AttentionStrategyConfig:
    """注意力策略系统配置"""
    version: str = "1.0.0"
    
    # 全局设置
    auto_start: bool = True
    log_signals: bool = True
    max_signal_history: int = 1000
    
    # 各策略配置
    strategies: Dict[str, StrategySettings] = field(default_factory=dict)
    
    # 默认策略参数
    default_settings: StrategySettings = field(default_factory=StrategySettings)


class ConfigManager:
    """配置管理器"""
    
    DEFAULT_CONFIG_PATH = Path.home() / ".naja" / "attention_strategies.json"
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = Path(config_path) if config_path else self.DEFAULT_CONFIG_PATH
        self.config = AttentionStrategyConfig()
        self._load_config()
    
    def _load_config(self):
        """加载配置"""
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.config = self._dict_to_config(data)
                print(f"✅ 配置已加载: {self.config_path}")
            except Exception as e:
                print(f"⚠️ 加载配置失败: {e}，使用默认配置")
                self.config = self._create_default_config()
        else:
            self.config = self._create_default_config()
            self.save_config()
    
    def _create_default_config(self) -> AttentionStrategyConfig:
        """创建默认配置"""
        config = AttentionStrategyConfig()
        
        # 全局市场监控
        config.strategies['global_sentinel'] = StrategySettings(
            enabled=True,
            priority=10,
            min_global_attention=0.0,  # 始终运行
            cooldown_period=30.0
        )
        
        # 板块轮动
        config.strategies['sector_rotation_hunter'] = StrategySettings(
            enabled=True,
            priority=8,
            min_global_attention=0.3,
            cooldown_period=300.0,
            custom_params={
                'momentum_threshold': 0.15,
                'min_sector_attention': 0.4
            }
        )
        
        # 动量突破
        config.strategies['momentum_surge_tracker'] = StrategySettings(
            enabled=True,
            priority=7,
            min_global_attention=0.4,
            min_symbol_weight=2.0,
            max_positions=20,
            cooldown_period=180.0,
            custom_params={
                'price_threshold': 0.03,
                'volume_threshold': 2.0
            }
        )
        
        # 异常模式
        config.strategies['anomaly_pattern_sniper'] = StrategySettings(
            enabled=True,
            priority=6,
            min_global_attention=0.3,
            min_symbol_weight=3.0,
            cooldown_period=300.0,
            custom_params={
                'zscore_threshold': 2.5,
                'pytorch_activation_threshold': 0.6
            }
        )
        
        # 聪明资金
        config.strategies['smart_money_flow_detector'] = StrategySettings(
            enabled=True,
            priority=7,
            min_global_attention=0.35,
            min_symbol_weight=2.5,
            cooldown_period=240.0,
            custom_params={
                'large_order_threshold': 1000000,
                'accumulation_threshold': 0.7
            }
        )
        
        return config
    
    def _dict_to_config(self, data: Dict) -> AttentionStrategyConfig:
        """字典转配置对象"""
        config = AttentionStrategyConfig(
            version=data.get('version', '1.0.0'),
            auto_start=data.get('auto_start', True),
            log_signals=data.get('log_signals', True),
            max_signal_history=data.get('max_signal_history', 1000)
        )
        
        # 加载策略配置
        for strategy_id, settings_data in data.get('strategies', {}).items():
            config.strategies[strategy_id] = StrategySettings(
                enabled=settings_data.get('enabled', True),
                priority=settings_data.get('priority', 5),
                min_global_attention=settings_data.get('min_global_attention', 0.0),
                min_symbol_weight=settings_data.get('min_symbol_weight', 1.0),
                max_positions=settings_data.get('max_positions', 10),
                cooldown_period=settings_data.get('cooldown_period', 60.0),
                custom_params=settings_data.get('custom_params', {})
            )
        
        return config
    
    def _config_to_dict(self, config: AttentionStrategyConfig) -> Dict:
        """配置对象转字典"""
        result = {
            'version': config.version,
            'auto_start': config.auto_start,
            'log_signals': config.log_signals,
            'max_signal_history': config.max_signal_history,
            'strategies': {}
        }
        
        for strategy_id, settings in config.strategies.items():
            result['strategies'][strategy_id] = {
                'enabled': settings.enabled,
                'priority': settings.priority,
                'min_global_attention': settings.min_global_attention,
                'min_symbol_weight': settings.min_symbol_weight,
                'max_positions': settings.max_positions,
                'cooldown_period': settings.cooldown_period,
                'custom_params': settings.custom_params
            }
        
        return result
    
    def save_config(self):
        """保存配置"""
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self._config_to_dict(self.config), f, indent=2, ensure_ascii=False)
            
            print(f"✅ 配置已保存: {self.config_path}")
        except Exception as e:
            print(f"❌ 保存配置失败: {e}")
    
    def get_strategy_settings(self, strategy_id: str) -> StrategySettings:
        """获取策略配置"""
        return self.config.strategies.get(strategy_id, self.config.default_settings)
    
    def update_strategy_settings(self, strategy_id: str, settings: StrategySettings):
        """更新策略配置"""
        self.config.strategies[strategy_id] = settings
        self.save_config()
    
    def enable_strategy(self, strategy_id: str) -> bool:
        """启用策略"""
        if strategy_id in self.config.strategies:
            self.config.strategies[strategy_id].enabled = True
            self.save_config()
            return True
        return False
    
    def disable_strategy(self, strategy_id: str) -> bool:
        """禁用策略"""
        if strategy_id in self.config.strategies:
            self.config.strategies[strategy_id].enabled = False
            self.save_config()
            return True
        return False


# 全局配置实例
_config_instance: Optional[ConfigManager] = None


def get_config_manager(config_path: Optional[str] = None) -> ConfigManager:
    """获取全局配置管理器"""
    global _config_instance
    
    if _config_instance is None:
        _config_instance = ConfigManager(config_path)
    
    return _config_instance
