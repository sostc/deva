"""Public LLM API for deva."""

from .llm_parts.client import GPT
from .llm_parts import client as _client


def get_gpt(model_type='deepseek'):
    return _client.get_gpt(model_type=model_type)


def sync_gpt(prompts):
    return _client.sync_gpt(prompts)


async def async_gpt(prompts):
    return await _client.async_gpt(prompts)


async def async_json_gpt(prompts):
    return await _client.async_json_gpt(prompts)


async def get_gpt_response(prompt, display_func=print, flush_interval=3):
    return await _client.get_gpt_response(
        prompt=prompt,
        display_func=display_func,
        flush_interval=flush_interval,
    )
