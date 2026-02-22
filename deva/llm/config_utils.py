"""Helpers for validating and guiding NB-backed LLM configuration."""

from __future__ import annotations


REQUIRED_MODEL_CONFIGS = ("api_key", "base_url", "model")

_MODEL_HINTS = {
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
    },
    "kimi": {
        "base_url": "https://api.moonshot.cn/v1",
        "model": "moonshot-v1-8k",
    },
    "sambanova": {
        "base_url": "https://api.sambanova.ai/v1",
        "model": "Meta-Llama-3.1-70B-Instruct",
    },
}


def _is_blank(value):
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return False


def get_model_config_status(NB, model_type):
    """Return NB config object and its missing required keys."""
    config = NB(model_type)
    missing = [k for k in REQUIRED_MODEL_CONFIGS if _is_blank(config.get(k))]
    return {
        "model_type": model_type,
        "config": config,
        "missing": missing,
        "ready": not missing,
    }


def build_model_config_example(model_type, missing=None):
    """Build a runnable code snippet to configure missing model fields."""
    missing = list(missing or REQUIRED_MODEL_CONFIGS)
    hints = _MODEL_HINTS.get(model_type, {})
    lines = ["from deva.namespace import NB", "", f"NB('{model_type}').update({{"]
    for name in missing:
        if name == "api_key":
            value = "your-api-key-here"
        elif name == "base_url":
            value = hints.get("base_url", "https://api.example.com/v1")
        elif name == "model":
            value = hints.get("model", "model-name")
        else:
            value = "your-value"
        lines.append(f"    '{name}': '{value}',")
    lines.append("})")
    return "\n".join(lines)


def build_model_config_message(model_type, missing):
    missing_text = ", ".join(missing)
    return f"模型 {model_type} 缺少必要配置项: {missing_text}。"

