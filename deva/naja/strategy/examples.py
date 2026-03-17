"""策略配置示例

展示每种策略类型的完整配置示例和使用方式。

使用方式:
    from deva.naja.strategy.examples import (
        get_legacy_example,
        get_river_example,
        get_plugin_example,
        get_declarative_example,
        get_all_examples,
    )
"""

from typing import Any, Dict


def get_legacy_example() -> Dict[str, Any]:
    """Legacy 类型示例 - 兼容旧版 process 函数

    适用于: 快速迁移旧策略代码
    """
    return {
        "strategy_type": "legacy",
        "strategy_name": "simple_ma_strategy",
        "strategy_id": "legacy_001",
        "description": "简单移动平均策略",
        "config": {
            "process_func": "my_module.process_function",
            "window": 20,
        },
    }


def get_river_example() -> Dict[str, Any]:
    """River 类型示例 - River ML 模型策略

    适用于: 在线机器学习、异常检测、漂移检测
    """
    return {
        "strategy_type": "river",
        "strategy_name": "anomaly_detection",
        "strategy_id": "river_001",
        "description": "基于 River 的实时异常检测",
        "config": {
            "model_path": "river.anomaly.HalfSpaceTrees",
            "model_params": {
                "n_trees": 10,
                "height": 8,
                "window_size": 1000,
                "seed": 42,
            },
            "feature_key": "features",
            "label_key": "label",
            "learn_on_label": True,
            "signal_type": "anomaly",
        },
    }


def get_river_batch_example() -> Dict[str, Any]:
    """River 批量预测示例

    适用于: 批量数据处理、离线分析
    """
    return {
        "strategy_type": "river",
        "strategy_name": "batch_prediction",
        "strategy_id": "river_batch_001",
        "description": "批量预测示例",
        "config": {
            "model_path": "river.forest.ARFClassifier",
            "model_params": {
                "n_estimators": 10,
                "seed": 42,
            },
            "feature_key": "features",
            "label_key": "label",
            "learn_on_label": True,
            "signal_type": "classification",
        },
    }


def get_plugin_example() -> Dict[str, Any]:
    """Plugin 类型示例 - 插件式策略

    适用于: 自定义复杂逻辑、需要状态管理
    """
    return {
        "strategy_type": "plugin",
        "strategy_name": "memory_strategy",
        "strategy_id": "plugin_001",
        "description": "记忆系统策略",
        "config": {
            "class_path": "deva.naja.memory.core.MemoryStrategy",
            "init_args": {
                "capacity": 10000,
                "window": 100,
                "enable_auto_save": True,
                "save_interval": 300,
            },
        },
    }


def get_plugin_custom_example() -> Dict[str, Any]:
    """Plugin 自定义插件示例

    适用于: 用户自定义策略
    """
    return {
        "strategy_type": "plugin",
        "strategy_name": "custom_strategy",
        "strategy_id": "plugin_custom_001",
        "description": "自定义策略示例",
        "config": {
            "class_path": "my_app.strategies.MyCustomStrategy",
            "init_args": {
                "threshold": 0.75,
                "mode": "strict",
                "debug": True,
            },
        },
    }


def get_declarative_example() -> Dict[str, Any]:
    """Declarative 类型示例 - 声明式策略

    适用于: 需要特征处理 + 模型 + 逻辑组合的复杂场景
    """
    return {
        "strategy_type": "declarative",
        "strategy_name": "composite_strategy",
        "strategy_id": "declarative_001",
        "description": "组合式策略示例",
        "config": {
            "pipeline": {
                "steps": [
                    {"type": "select", "fields": ["price", "volume", "amount"]},
                    {"type": "normalize", "method": "zscore"},
                    {"type": "window", "size": 20, "agg": "mean"},
                ],
            },
            "model": {
                "type": "adaptive_forest",
                "params": {
                    "n_estimators": 10,
                    "max_depth": 5,
                },
            },
            "params": {
                "threshold": 0.7,
                "min_confidence": 0.6,
            },
            "logic": {
                "type": "python",
                "code": """
def process(data, features, model, prediction):
    signal = prediction.get("score", 0)
    if signal > params.threshold:
        return {"action": "buy", "confidence": signal}
    elif signal < -params.threshold:
        return {"action": "sell", "confidence": abs(signal)}
    return {"action": "hold", "confidence": 0}
""",
            },
            "state_persist": True,
            "state_persist_interval": 300,
        },
    }


def get_declarative_with_plugin_example() -> Dict[str, Any]:
    """Declarative 带插件示例

    适用于: 需要结合插件逻辑的场景
    """
    return {
        "strategy_type": "declarative",
        "strategy_name": "plugin_combo_strategy",
        "strategy_id": "declarative_plugin_001",
        "description": "声明式 + 插件组合策略",
        "config": {
            "pipeline": {
                "steps": [
                    {"type": "select", "fields": ["open", "high", "low", "close", "volume"]},
                    {"type": "technical_indicators", "indicators": ["ma5", "ma20", "rsi"]},
                ],
            },
            "model": {
                "type": "trend_classifier",
                "params": {"lookback": 10},
            },
            "plugin": "trend_detector",
            "logic": {
                "type": "python",
                "code": """
def apply_logic(prediction, data, features):
    trend = prediction.get("trend", "sideways")
    strength = prediction.get("strength", 0)

    if trend == "up" and strength > 0.7:
        return {"signal": "long", "strength": strength}
    elif trend == "down" and strength > 0.7:
        return {"signal": "short", "strength": strength}
    return {"signal": "neutral", "strength": 0}
""",
            },
        },
    }


def get_all_examples() -> Dict[str, Dict[str, Any]]:
    """获取所有示例"""
    return {
        "legacy": get_legacy_example(),
        "river": get_river_example(),
        "river_batch": get_river_batch_example(),
        "plugin": get_plugin_example(),
        "plugin_custom": get_plugin_custom_example(),
        "declarative": get_declarative_example(),
        "declarative_with_plugin": get_declarative_with_plugin_example(),
    }


def print_example(example: Dict[str, Any]) -> None:
    """打印示例配置"""
    import json

    print(json.dumps(example, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    examples = get_all_examples()
    for name, example in examples.items():
        print(f"\n{'='*50}")
        print(f"示例: {name}")
        print("=" * 50)
        print_example(example)
