"""
V2 增强系统配置示例

如何在 Naja 中启用 V2 增强功能：

方式 1: 通过环境变量启用
--------------------------------
import os
os.environ['NAJA_V2_ENABLED'] = '1'
os.environ['NAJA_V2_MODULES'] = 'predictive,budget,feedback'

方式 2: 在 attention_config.py 中配置
--------------------------------
from deva.naja.attention_v2_config import V2_CONFIG

# 在 load_config() 中返回 V2_CONFIG

方式 3: 运行时启用
--------------------------------
from deva.naja.attention_integration import get_attention_integration

integration = get_attention_integration()

# 检查是否有 v2_system
if integration.v2_system:
    print("V2 系统已启用")
    
    # 启用/禁用模块
    integration.v2_system.enable_module('propagation')
    integration.v2_system.disable_module('strategy_learning')
"""

from typing import Dict, Any


V2_CONFIG_DEFAULT: Dict[str, Any] = {
    'enable_predictive': True,
    'enable_feedback': True,
    'enable_budget': True,
    'enable_propagation': False,
    'enable_strategy_learning': False,
}


V2_CONFIG_FULL: Dict[str, Any] = {
    'enable_predictive': True,
    'enable_feedback': True,
    'enable_budget': True,
    'enable_propagation': True,
    'enable_strategy_learning': True,
}


V2_CONFIG_MINIMAL: Dict[str, Any] = {
    'enable_predictive': True,
    'enable_feedback': False,
    'enable_budget': True,
    'enable_propagation': False,
    'enable_strategy_learning': False,
}


def get_v2_config_from_env() -> Dict[str, Any]:
    """从环境变量获取 V2 配置"""
    import os
    
    v2_enabled = os.environ.get('NAJA_V2_ENABLED', '0') == '1'
    
    if not v2_enabled:
        return {}
    
    config = V2_CONFIG_DEFAULT.copy()
    
    modules_env = os.environ.get('NAJA_V2_MODULES', '')
    if modules_env:
        modules = modules_env.split(',')
        config['enable_predictive'] = 'predictive' in modules
        config['enable_feedback'] = 'feedback' in modules
        config['enable_budget'] = 'budget' in modules
        config['enable_propagation'] = 'propagation' in modules
        config['enable_strategy_learning'] = 'strategy_learning' in modules
    
    return config


def print_v2_status(integration) -> None:
    """打印 V2 系统状态"""
    if not hasattr(integration, 'v2_system') or not integration.v2_system:
        print("V2 增强系统未启用")
        return
    
    v2 = integration.v2_system
    summary = v2.get_v2_summary()
    
    print("\n" + "="*50)
    print("🚀 V2 增强系统状态")
    print("="*50)
    
    enabled = summary.get('v2_enabled_modules', {})
    for key, is_enabled in enabled.items():
        emoji = "✅" if is_enabled else "❌"
        print(f"  {emoji} {key}")
    
    if 'budget_summary' in summary:
        budget = summary['budget_summary']
        print(f"\n💰 预算系统:")
        print(f"  系统负载: {summary.get('system_load', 0) * 100:.1f}%")
        print(f"  高频 symbols: {budget.get('tier1_count', 0)}")
        print(f"  中频 symbols: {budget.get('tier2_count', 0)}")
        print(f"  低频 symbols: {budget.get('tier3_count', 0)}")
    
    print("="*50 + "\n")
