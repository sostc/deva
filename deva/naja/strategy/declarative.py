"""Declarative strategy engine and registries."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

import base64
import hashlib
import pickle
import time

from deva import NB


@dataclass
class PipelineContext:
    data: Any
    features: Dict[str, Any]


class FeatureRegistry:
    _features: Dict[str, Callable[[PipelineContext, Dict[str, Any]], Any]] = {}

    @classmethod
    def register(cls, name: str, func: Callable[[PipelineContext, Dict[str, Any]], Any]) -> None:
        cls._features[str(name)] = func

    @classmethod
    def get(cls, name: str) -> Callable[[PipelineContext, Dict[str, Any]], Any]:
        return cls._features[name]


class ModelRegistry:
    _models: Dict[str, Callable[..., Any]] = {}

    @classmethod
    def register(cls, name: str, factory: Callable[..., Any]) -> None:
        cls._models[str(name)] = factory

    @classmethod
    def create(cls, name: str, params: Dict[str, Any]) -> Any:
        if name not in cls._models:
            raise ValueError(f"未知模型类型: {name}")
        return cls._models[name](**(params or {}))


class LogicRegistry:
    _logics: Dict[str, Callable[[Any, Dict[str, Any]], Any]] = {}

    @classmethod
    def register(cls, name: str, func: Callable[[Any, Dict[str, Any]], Any]) -> None:
        cls._logics[str(name)] = func

    @classmethod
    def apply(cls, name: str, prediction: Any, config: Dict[str, Any]) -> Any:
        if name not in cls._logics:
            raise ValueError(f"未知逻辑类型: {name}")
        return cls._logics[name](prediction, config or {})


class PluginRegistry:
    _plugins: Dict[str, Any] = {}

    @classmethod
    def get(cls, plugin_path: str) -> Any:
        key = str(plugin_path)
        if key in cls._plugins:
            return cls._plugins[key]

        module_path = key
        if "." not in key:
            module_path = f"deva.naja.strategy.{key}"

        module = importlib.import_module(module_path)
        plugin = getattr(module, "Plugin", None)
        if plugin is not None:
            plugin = plugin()
        cls._plugins[key] = plugin or module
        return cls._plugins[key]


class StrategyEngine:
    """Declarative strategy execution engine."""

    def __init__(self):
        self._code_cache: Dict[str, Callable[..., Any]] = {}
        self._state_cache: Dict[str, Dict[str, Any]] = {}
        self._persist_stats: Dict[str, Dict[str, Any]] = {}
        self._state_db = NB("naja_strategy_runtime_state")

    def run(self, strategy: Dict[str, Any], data: Any, model_state: Any) -> Tuple[Any, Any]:
        pipeline = strategy.get("pipeline") or []
        model_cfg = strategy.get("model") or {}
        params = strategy.get("params") or {}
        logic = strategy.get("logic") or {}
        plugin = strategy.get("plugin")
        label_key = strategy.get("label_key", "label")

        features = self.run_pipeline(pipeline, data)
        model_state = self.load_model(model_cfg, params, model_state)

        prediction = None
        if hasattr(model_state, "predict_one"):
            prediction = model_state.predict_one(features)
        elif callable(model_state):
            prediction = model_state(features)

        label = data.get(label_key) if isinstance(data, dict) else None
        if label is not None and hasattr(model_state, "learn_one"):
            model_state.learn_one(features, label)

        if plugin:
            plugin_obj = PluginRegistry.get(plugin)
            if hasattr(plugin_obj, "run"):
                return plugin_obj.run(data=data, features=features, model=model_state, prediction=prediction), model_state
            if hasattr(plugin_obj, "apply_logic"):
                return plugin_obj.apply_logic(prediction, data=data, features=features), model_state

        logic_type = str(logic.get("type", "") or "").strip().lower()
        if logic_type == "python":
            signal = self._run_python_logic(strategy, logic, data, features, model_state, prediction)
        else:
            signal = self.apply_logic(logic, prediction)
        return signal, model_state

    def run_pipeline(self, pipeline: List[Dict[str, Any]], data: Any) -> Dict[str, Any]:
        features: Dict[str, Any] = {}
        context = PipelineContext(data=data, features=features)

        for step in pipeline:
            step_type = str(step.get("type", "feature") or "feature").strip().lower()
            if step_type == "feature":
                name = str(step.get("name", "") or "").strip()
                if not name:
                    continue
                func = FeatureRegistry.get(name)
                value = func(context, step)
                if isinstance(value, dict):
                    features.update(value)
                else:
                    alias = step.get("as") or name
                    features[str(alias)] = value
            elif step_type == "scale":
                factor = float(step.get("factor", 1.0))
                for key, value in list(features.items()):
                    if isinstance(value, (int, float)):
                        features[key] = value * factor
            elif step_type == "select":
                keys = step.get("keys") or []
                features = {k: features.get(k) for k in keys if k in features}
                context.features = features
        return features

    def load_model(self, model_cfg: Dict[str, Any], params: Dict[str, Any], model_state: Any) -> Any:
        model_type = str(model_cfg.get("type", "") or "").strip()
        if not model_type:
            return model_state
        if model_state is not None and getattr(model_state, "__model_type__", "") == model_type:
            return model_state

        model = ModelRegistry.create(model_type, params or {})
        setattr(model, "__model_type__", model_type)
        return model

    def apply_logic(self, logic_cfg: Dict[str, Any], prediction: Any) -> Any:
        logic_type = str(logic_cfg.get("type", "") or "").strip()
        if not logic_type:
            return prediction
        return LogicRegistry.apply(logic_type, prediction, logic_cfg)

    def _run_python_logic(
        self,
        strategy: Dict[str, Any],
        logic_cfg: Dict[str, Any],
        data: Any,
        features: Dict[str, Any],
        model_state: Any,
        prediction: Any,
    ) -> Any:
        code = logic_cfg.get("code") or strategy.get("code") or ""
        if not code:
            return prediction

        strategy_id = str(strategy.get("strategy_id") or "")
        params = strategy.get("params") or {}
        state_cfg = strategy.get("state_persist", True)
        state_interval = float(strategy.get("state_persist_interval", 300) or 300)
        state_every_n = int(strategy.get("state_persist_every_n", 200) or 200)

        func = self._code_cache.get(code)
        if func is None:
            scope: Dict[str, Any] = {}
            
            COMMON_HELPERS = '''
def _f(v, d=0.0):
    try:
        return float(v)
    except Exception:
        return d

def _rows(data):
    import pandas as pd
    try:
        if isinstance(data, pd.DataFrame):
            return data.to_dict("records")
    except Exception:
        pass
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        return data
    return []

def _sym(row):
    return str(row.get("code") or row.get("symbol") or row.get("ts_code") or "").strip()

def _price(row):
    for k in ("current", "now", "price", "last", "close", "open", "high", "low"):
        if k in row:
            p = _f(row.get(k), 0.0)
            if p > 0:
                return p
    return 0.0

def _first_multi(v, default="unknown"):
    if v is None:
        return default
    text = str(v).strip()
    if not text or text.lower() in {"nan", "none", "null", "unknown"}:
        return default
    for sep in ["|", ",", "，", ";", "；"]:
        text = text.replace(sep, "|")
    vals = list(dict.fromkeys(x.strip() for x in text.split("|") if x.strip()))
    return vals[0] if vals else default

def _split_multi(v):
    if v is None:
        return []
    text = str(v).strip()
    if not text or text.lower() in {"nan", "none", "null", "unknown"}:
        return []
    for sep in ["|", ",", "，", ";", "；"]:
        text = text.replace(sep, "|")
    return list(dict.fromkeys(x.strip() for x in text.split("|") if x.strip()))
'''
            exec(COMMON_HELPERS, scope)
            exec(code, scope)
            func = scope.get("process") or scope.get("apply")
            if not callable(func):
                raise ValueError("python logic 需要提供 process 或 apply 函数")
            self._code_cache[code] = func

        globals_scope = func.__globals__
        if params is not None:
            globals_scope["PARAMS"] = params

        if strategy_id and "_STATE" in globals_scope:
            self._ensure_state_loaded(strategy_id, globals_scope, code)

        context = {
            "features": features,
            "prediction": prediction,
            "model": model_state,
            "strategy": strategy,
            "params": params,
        }
        try:
            result = func(data, context)
        except TypeError:
            result = func(data)

        if strategy_id and "_STATE" in globals_scope and state_cfg:
            self._maybe_persist_state(strategy_id, globals_scope, code, state_interval, state_every_n)

        return result

    def _state_key(self, strategy_id: str, code: str) -> str:
        code_hash = hashlib.md5(code.encode("utf-8")).hexdigest()[:8]
        return f"{strategy_id}:{code_hash}"

    def _ensure_state_loaded(self, strategy_id: str, scope: Dict[str, Any], code: str) -> None:
        key = self._state_key(strategy_id, code)
        if key in self._state_cache:
            scope["_STATE"] = self._state_cache[key]
            return
        payload = self._state_db.get(key)
        if isinstance(payload, dict) and payload.get("state_bin"):
            try:
                raw = base64.b64decode(payload["state_bin"])
                state = pickle.loads(raw)
                if isinstance(state, dict):
                    scope["_STATE"] = state
                    self._state_cache[key] = state
                    return
            except Exception:
                pass
        state = scope.get("_STATE")
        if isinstance(state, dict):
            self._state_cache[key] = state

    def _maybe_persist_state(
        self,
        strategy_id: str,
        scope: Dict[str, Any],
        code: str,
        interval: float,
        every_n: int,
    ) -> None:
        key = self._state_key(strategy_id, code)
        stats = self._persist_stats.setdefault(key, {"last_ts": 0.0, "count": 0})
        stats["count"] += 1
        now = time.time()
        if stats["count"] % max(1, every_n) != 0 and now - stats["last_ts"] < interval:
            return
        self._persist_state(strategy_id, scope, code)
        stats["last_ts"] = now

    def _persist_state(self, strategy_id: str, scope: Dict[str, Any], code: str) -> None:
        state = scope.get("_STATE")
        if not isinstance(state, dict):
            return
        try:
            raw = pickle.dumps(state)
            payload = {
                "strategy_id": strategy_id,
                "updated_at": time.time(),
                "state_bin": base64.b64encode(raw).decode("ascii"),
            }
            self._state_db[self._state_key(strategy_id, code)] = payload
            self._state_cache[self._state_key(strategy_id, code)] = state
        except Exception:
            return

    def persist_state_now(self, strategy: Dict[str, Any], code: str) -> None:
        strategy_id = str(strategy.get("strategy_id") or "")
        if not strategy_id:
            return
        func = self._code_cache.get(code)
        if func is None:
            return
        scope = func.__globals__
        self._persist_state(strategy_id, scope, code)


def _feature_identity(ctx: PipelineContext, _step: Dict[str, Any]) -> Any:
    if isinstance(ctx.data, dict):
        return ctx.data
    return {"value": ctx.data}


def _feature_field(ctx: PipelineContext, step: Dict[str, Any]) -> Any:
    field = step.get("field") or step.get("name")
    if isinstance(ctx.data, dict) and field in ctx.data:
        return ctx.data.get(field)
    return None


def _feature_price_change(ctx: PipelineContext, _step: Dict[str, Any]) -> Any:
    data = ctx.data if isinstance(ctx.data, dict) else {}
    if "price_change" in data:
        return data.get("price_change")
    price = data.get("price")
    prev = data.get("prev_price")
    if price is None or prev is None:
        return None
    return price - prev


def _feature_volume_spike(ctx: PipelineContext, _step: Dict[str, Any]) -> Any:
    data = ctx.data if isinstance(ctx.data, dict) else {}
    if "volume_spike" in data:
        return data.get("volume_spike")
    volume = data.get("volume")
    avg = data.get("avg_volume")
    if volume is None or avg in (None, 0):
        return None
    return volume / avg


def _logic_threshold(prediction: Any, cfg: Dict[str, Any]) -> Dict[str, Any]:
    buy = float(cfg.get("buy", 0.7))
    sell = float(cfg.get("sell", 0.3))

    value = prediction
    if isinstance(prediction, dict):
        value = prediction.get("score")
        if value is None:
            value = prediction.get("proba")
        if value is None:
            value = prediction.get("signal")

    if value is None:
        return {"signal": None, "signal_type": "threshold"}

    signal = "hold"
    if value >= buy:
        signal = "buy"
    elif value <= sell:
        signal = "sell"
    return {"signal": signal, "signal_type": "threshold", "score": value}


def _register_default_models():
    try:
        from river import linear_model, ensemble
    except Exception:
        return

    ModelRegistry.register("logistic_regression", linear_model.LogisticRegression)
    if hasattr(ensemble, "AdaptiveRandomForestClassifier"):
        ModelRegistry.register("adaptive_forest", ensemble.AdaptiveRandomForestClassifier)


FeatureRegistry.register("identity", _feature_identity)
FeatureRegistry.register("field", _feature_field)
FeatureRegistry.register("price_change", _feature_price_change)
FeatureRegistry.register("volume_spike", _feature_volume_spike)

LogicRegistry.register("threshold", _logic_threshold)

_register_default_models()
