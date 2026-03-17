"""Strategy runtime adapters and registry."""

from __future__ import annotations

import importlib
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Type

from .declarative import StrategyEngine


class BaseStrategy(ABC):
    """统一策略接口。"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self._config = config or {}
        self._entry = None

    def attach_entry(self, entry: Any) -> None:
        """绑定策略条目（可选）。"""
        self._entry = entry

    def init(self, config: Dict[str, Any]) -> None:
        """初始化策略。"""
        self._config = config or {}

    @abstractmethod
    def on_data(self, data: Any) -> None:
        """处理输入数据。"""

    @abstractmethod
    def get_signal(self) -> Any:
        """返回策略信号。"""

    def update_params(self, params: Dict[str, Any]) -> None:
        """更新策略参数。"""
        self._config.update(params or {})

    def reset(self) -> None:
        """重置策略状态。"""
        return None

    def on_start(self) -> None:
        """策略启动回调。"""
        return None

    def on_stop(self) -> None:
        """策略停止回调。"""
        return None

    def close(self) -> None:
        """关闭策略。"""
        return None


class LegacyStrategyAdapter(BaseStrategy):
    """旧策略适配器（调用已有 process 函数）。"""

    def __init__(self, process_func, config: Optional[Dict[str, Any]] = None):
        super().__init__(config=config)
        self._process = process_func
        self._last_result = None

    def on_data(self, data: Any) -> None:
        self._last_result = self._process(data)

    def get_signal(self) -> Any:
        return self._last_result


class RiverStrategyAdapter(BaseStrategy):
    """River 策略适配器（最小通用版本）。

    支持:
    - 单条预测: on_data() -> predict_one()
    - 批量预测: on_batch() -> predict_many()
    - 在线学习: learn_one()
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config=config)
        self._model = None
        self._pred = None
        self._preds = None
        self._feature_key = "features"
        self._label_key = "label"
        self._learn_on_label = True
        self._signal_type = "river"
        self._init_from_config()

    def _init_from_config(self) -> None:
        cfg = self._config or {}
        self._feature_key = cfg.get("feature_key", self._feature_key)
        self._label_key = cfg.get("label_key", self._label_key)
        self._learn_on_label = bool(cfg.get("learn_on_label", True))
        self._signal_type = cfg.get("signal_type", self._signal_type)

        if cfg.get("model") is not None:
            self._model = cfg.get("model")
            return

        model_path = cfg.get("model_path", "")
        model_params = cfg.get("model_params", {})
        if model_path:
            module_path, _, class_name = model_path.rpartition(".")
            if not module_path:
                raise ValueError("model_path 需要包含模块路径")
            module = importlib.import_module(module_path)
            cls = getattr(module, class_name)
            self._model = cls(**(model_params or {}))
            return

        raise ValueError("RiverStrategyAdapter 缺少 model 或 model_path 配置")

    def init(self, config: Dict[str, Any]) -> None:
        self._config = config or {}
        self._init_from_config()

    def on_data(self, data: Any) -> None:
        if self._model is None:
            return
        if isinstance(data, dict):
            x = data.get(self._feature_key, data)
            y = data.get(self._label_key)
        else:
            x = data
            y = None

        if hasattr(self._model, "predict_one"):
            self._pred = self._model.predict_one(x)
        else:
            self._pred = None

        if y is not None and self._learn_on_label and hasattr(self._model, "learn_one"):
            self._model.learn_one(x, y)

    def on_batch(self, data_list: List[Any]) -> None:
        """批量处理数据

        Args:
            data_list: 数据列表
        """
        if self._model is None:
            return

        if not hasattr(self._model, "predict_many"):
            for data in data_list:
                self.on_data(data)
            return

        features_list = []
        labels_list = []

        for data in data_list:
            if isinstance(data, dict):
                x = data.get(self._feature_key, data)
                y = data.get(self._label_key)
            else:
                x = data
                y = None
            features_list.append(x)
            if y is not None:
                labels_list.append(y)

        self._preds = self._model.predict_many(features_list)

        if self._learn_on_label and labels_list and hasattr(self._model, "learn_many"):
            self._model.learn_many(features_list, labels_list)

    def get_signal(self) -> Any:
        if self._preds is not None:
            return {
                "signals": self._preds,
                "signal_type": self._signal_type,
                "batch_size": len(self._preds) if isinstance(self._preds, list) else 1,
            }
        if isinstance(self._pred, dict):
            return self._pred
        return {
            "signal": self._pred,
            "signal_type": self._signal_type,
        }

    def reset(self) -> None:
        self._pred = None
        self._preds = None
        self._init_from_config()

    def update_params(self, params: Dict[str, Any]) -> None:
        self._config.update(params or {})
        self._init_from_config()


class PluginStrategyAdapter(BaseStrategy):
    """插件策略适配器，通过类路径加载实现。"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config=config)
        self._impl = None
        self._last_result = None
        self._load_impl()

    def _load_impl(self) -> None:
        cfg = self._config or {}
        class_path = str(cfg.get("class_path", "") or "").strip()
        if not class_path:
            raise ValueError("PluginStrategyAdapter 缺少 class_path 配置")

        module_path, _, class_name = class_path.rpartition(".")
        if not module_path:
            raise ValueError("class_path 需要包含模块路径")
        module = importlib.import_module(module_path)
        cls = getattr(module, class_name)
        self._impl = cls(**(cfg.get("init_args", {}) or {}))

        if isinstance(self._impl, BaseStrategy):
            return
        if hasattr(self._impl, "init"):
            self._impl.init(cfg)

    def init(self, config: Dict[str, Any]) -> None:
        self._config = config or {}
        self._load_impl()

    def on_data(self, data: Any) -> None:
        if self._impl is None:
            return
        if hasattr(self._impl, "on_data"):
            self._last_result = self._impl.on_data(data)
            return
        if isinstance(data, list) and hasattr(self._impl, "on_window"):
            self._last_result = self._impl.on_window(data)
            return
        if hasattr(self._impl, "on_record"):
            self._last_result = self._impl.on_record(data)

    def get_signal(self) -> Any:
        if self._impl is None:
            return None
        if hasattr(self._impl, "get_signal"):
            return self._impl.get_signal()
        return self._last_result

    def update_params(self, params: Dict[str, Any]) -> None:
        if self._impl is None:
            return
        if hasattr(self._impl, "update_params"):
            self._impl.update_params(params)

    def reset(self) -> None:
        if self._impl is None:
            return
        if hasattr(self._impl, "reset"):
            self._impl.reset()

    def on_start(self) -> None:
        if self._impl is None:
            return
        if hasattr(self._impl, "on_start"):
            self._impl.on_start()

    def on_stop(self) -> None:
        if self._impl is None:
            return
        if hasattr(self._impl, "on_stop"):
            self._impl.on_stop()

    def close(self) -> None:
        if self._impl is None:
            return
        if hasattr(self._impl, "close"):
            self._impl.close()
        if hasattr(self._impl, "on_stop"):
            self._impl.on_stop()


class StrategyRegistry:
    """策略注册表。"""

    _types: Dict[str, Type[BaseStrategy]] = {}

    @classmethod
    def register(cls, strategy_type: str, adapter_cls: Type[BaseStrategy]) -> None:
        if not strategy_type:
            raise ValueError("strategy_type 不能为空")
        cls._types[strategy_type] = adapter_cls

    @classmethod
    def create(cls, strategy_type: str, config: Optional[Dict[str, Any]] = None, entry: Any = None) -> BaseStrategy:
        adapter_cls = cls._types.get(strategy_type)
        if adapter_cls is None:
            raise ValueError(f"未注册的策略类型: {strategy_type}")
        adapter = adapter_cls(config=config or {})
        if hasattr(adapter, "attach_entry") and entry is not None:
            adapter.attach_entry(entry)
        return adapter


StrategyRegistry.register("river", RiverStrategyAdapter)
StrategyRegistry.register("plugin", PluginStrategyAdapter)


class DeclarativeStrategyAdapter(BaseStrategy):
    """配置驱动的策略适配器。"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config=config)
        self._engine = StrategyEngine()
        self._model_state = None
        self._last_signal = None
        self._entry_id = ""

    def init(self, config: Dict[str, Any]) -> None:
        self._config = config or {}
        self._model_state = None
        self._last_signal = None

    def on_data(self, data: Any) -> None:
        config = dict(self._config or {})
        if self._entry is not None:
            self._entry_id = getattr(self._entry, "id", "") or ""
            config.setdefault("strategy_id", self._entry_id)
            config.setdefault("strategy_name", getattr(self._entry, "name", ""))
        signal, model_state = self._engine.run(config, data, self._model_state)
        self._model_state = model_state
        self._last_signal = signal

    def get_signal(self) -> Any:
        return self._last_signal

    def update_params(self, params: Dict[str, Any]) -> None:
        self._config = self._config or {}
        config_params = dict(self._config.get("params", {}) or {})
        config_params.update(params or {})
        self._config["params"] = config_params
        self._model_state = None

    def reset(self) -> None:
        self._model_state = None
        self._last_signal = None

    def close(self) -> None:
        if not self._config:
            return
        if not self._entry_id:
            return
        logic = self._config.get("logic") or {}
        if str(logic.get("type", "")).lower() != "python":
            return
        code = logic.get("code") or self._config.get("code") or ""
        if not code:
            return
        config = dict(self._config or {})
        config.setdefault("strategy_id", self._entry_id)
        self._engine.persist_state_now(config, code)


StrategyRegistry.register("declarative", DeclarativeStrategyAdapter)
