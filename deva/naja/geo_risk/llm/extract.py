"""
LLM 抽取：文章 → 项目/运营商/容量/事件类型

三条硬约束（对应报告 §6）：
1. LLM 只做抽取，不做评级、不做判断；
2. 不可重试错误（402/鉴权/配置）→ 熔断 1 小时，期间不再调用；
3. 任何 LLM 失败都退回规则模板，日更不能因为模型不可用而中断。

缓存键 = prompt 版本 + 文章 url + 正文摘要；同一篇文章不重复付费。
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import time
from collections import OrderedDict
from typing import Any, Awaitable, Callable, Dict, Optional

from deva.llm.errors import LLMError

PROMPT_VERSION = "geo-risk-extract-v1"

ALLOWED_COUNTRIES = {"SG", "MY", "TH", "ID", "VN"}
ALLOWED_EVENTS = (
    "financing", "commissioning", "construction", "expansion", "policy", "other",
)
FIELD_NAMES = (
    "project_name", "operator", "country", "site", "capacity_mw", "gpu_count",
    "event_type", "quote", "confidence",
)

PROMPT_TEMPLATE = """你是信息抽取器，只从给定文本里抽取结构化字段，不做推断、不做投资判断。

只输出一个 JSON 对象，字段固定为：
{{
  "project_name": 字符串或 null,
  "operator": 字符串或 null,
  "country": "SG"|"MY"|"TH"|"ID"|"VN" 或 null,
  "site": 字符串或 null,
  "capacity_mw": 数字或 null,
  "gpu_count": 整数或 null,
  "event_type": "financing"|"commissioning"|"construction"|"expansion"|"policy"|"other",
  "quote": 支撑上述字段的原文短句,
  "confidence": 0 到 1 的数字
}}

来源: {source}
链接: {url}
标题: {title}
正文:
{text}
"""

_COUNTRY_WORDS = (
    ("SG", ("singapore", "新加坡")),
    ("MY", ("malaysia", "马来西亚", "johor", "柔佛")),
    ("TH", ("thailand", "泰国")),
    ("ID", ("indonesia", "印度尼西亚", "印尼", "batam", "巴淡")),
    ("VN", ("vietnam", "越南")),
)

_EVENT_WORDS = (
    ("financing", ("融资", "贷款", "授信", "financing", "syndicat", "loan")),
    ("commissioning", ("投运", "投产", "commission", "go-live")),
    ("construction", ("开工", "动工", "在建", "construction", "groundbreak")),
    ("expansion", ("扩容", "扩建", "expansion")),
    ("policy", ("bis", "出口管制", "export control", "管制", "entity list")),
)


class CircuitBreaker:
    """不可重试错误后熔断 1 小时；时钟可注入，便于测试。"""

    def __init__(self, cooldown_seconds: float = 3600.0,
                 clock: Callable[[], float] = time.time):
        self.cooldown_seconds = float(cooldown_seconds)
        self._clock = clock
        self._open_until = 0.0
        self.reason = ""

    def trip(self, reason: str) -> None:
        self._open_until = self._clock() + self.cooldown_seconds
        self.reason = reason

    def is_open(self) -> bool:
        return self._clock() < self._open_until

    def state(self) -> Dict[str, Any]:
        return {
            "open": self.is_open(),
            "reason": self.reason if self.is_open() else "",
            "open_until": round(self._open_until, 2),
        }


def cache_key(url: str, text: str) -> str:
    payload = f"{PROMPT_VERSION}\n{url}\n{text}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _clean_str(value: Any, limit: int = 200) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text[:limit] if text else None


def _clean_float(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return round(number, 2) if number >= 0 else None


def _clean_int(value: Any) -> Optional[int]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if number >= 0 else None


def _clean_fields(raw: Dict[str, Any]) -> Dict[str, Any]:
    """只保留白名单字段并做类型收敛；LLM 多吐的键一律丢弃。"""
    country = (_clean_str(raw.get("country")) or "").upper()
    event_type = (_clean_str(raw.get("event_type")) or "other").lower()
    confidence = _clean_float(raw.get("confidence"))
    if confidence is None or confidence > 1.0:
        confidence = 0.7
    return {
        "project_name": _clean_str(raw.get("project_name")),
        "operator": _clean_str(raw.get("operator")),
        "country": country if country in ALLOWED_COUNTRIES else None,
        "site": _clean_str(raw.get("site")),
        "capacity_mw": _clean_float(raw.get("capacity_mw")),
        "gpu_count": _clean_int(raw.get("gpu_count")),
        "event_type": event_type if event_type in ALLOWED_EVENTS else "other",
        "quote": _clean_str(raw.get("quote"), 500),
        "confidence": round(confidence, 3),
    }


def _parse_json(text: str) -> Dict[str, Any]:
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("LLM 输出不是 JSON")
        data = json.loads(cleaned[start:end + 1])
    if not isinstance(data, dict):
        raise ValueError("LLM 输出不是 JSON 对象")
    return data


def rule_extract(article: Dict[str, Any]) -> Dict[str, Any]:
    """不依赖模型的规则抽取：只认文本里露出来的数字和关键词。"""
    text = str(article.get("text") or "")
    lower = text.lower()

    capacity = None
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:mw|兆瓦)", lower)
    if match:
        capacity = round(float(match.group(1)), 2)

    gpu_count = None
    match = re.search(r"([\d,]{1,12})\s*(?:张\s*)?(?:gpus?|accelerators?|卡)", lower)
    if match:
        gpu_count = int(match.group(1).replace(",", ""))

    country = None
    for code, words in _COUNTRY_WORDS:
        if any(w in lower for w in words):
            country = code
            break

    event_type = "other"
    for name, words in _EVENT_WORDS:
        if any(w in lower for w in words):
            event_type = name
            break

    return {
        "project_name": None,
        "operator": None,
        "country": country,
        "site": None,
        "capacity_mw": capacity,
        "gpu_count": gpu_count,
        "event_type": event_type,
        "quote": text.strip()[:300] or None,
        "confidence": 0.25,
    }


class GeoRiskExtractor:
    """带缓存、熔断和规则降级的抽取器。

    Args:
        llm: 异步可调用对象 ``llm(prompt) -> str``；默认用 ``deva.llm`` 的 JSON 查询。
        breaker: 熔断器；默认 1 小时。
        cache_size: 内存缓存条数上限（同一篇文章不重复调用模型）。
    """

    def __init__(
        self,
        llm: Optional[Callable[[str], Awaitable[str]]] = None,
        breaker: Optional[CircuitBreaker] = None,
        cache_size: int = 256,
    ):
        self._llm = llm
        self.breaker = breaker or CircuitBreaker()
        self._cache: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
        self._cache_size = max(1, int(cache_size))

    async def _call_llm(self, prompt: str) -> str:
        if self._llm is not None:
            return await self._llm(prompt)
        from deva.llm import get_gpt
        return await get_gpt().async_json_query(prompt)

    def _cache_get(self, key: str) -> Optional[Dict[str, Any]]:
        if key not in self._cache:
            return None
        self._cache.move_to_end(key)
        cached = copy.deepcopy(self._cache[key])
        cached["source"] = "cache"
        cached["degraded"] = False
        return cached

    def _cache_put(self, key: str, value: Dict[str, Any]) -> None:
        self._cache[key] = copy.deepcopy(value)
        while len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)

    def _fallback(self, article: Dict[str, Any], key: str, *,
                  error: Optional[Dict[str, Any]] = None,
                  skipped: Optional[str] = None) -> Dict[str, Any]:
        result = {
            "fields": rule_extract(article),
            "source": "rule",
            "degraded": True,
            "confidence": 0.25,
            "cache_key": key,
            "error": error,
            "skipped": skipped,
            "breaker": self.breaker.state(),
        }
        return result

    async def extract(self, article: Dict[str, Any]) -> Dict[str, Any]:
        """抽取一篇文章。LLM 不可用时必定返回规则结果，绝不抛给日更任务。"""
        text = str(article.get("text") or "")
        url = str(article.get("url") or "")
        key = cache_key(url, text)

        cached = self._cache_get(key)
        if cached is not None:
            return cached

        if self.breaker.is_open():
            return self._fallback(article, key, skipped="circuit_open")

        prompt = PROMPT_TEMPLATE.format(
            source=article.get("source") or "",
            url=url,
            title=article.get("title") or "",
            text=text[:6000],
        )
        try:
            raw_text = await self._call_llm(prompt)
            fields = _clean_fields(_parse_json(raw_text))
        except LLMError as exc:
            if not exc.retryable:
                self.breaker.trip(f"{exc.kind}: {exc}")
            return self._fallback(article, key, error={
                "kind": exc.kind,
                "retryable": exc.retryable,
                "message": str(exc),
            })
        except Exception as exc:
            return self._fallback(article, key, error={
                "kind": type(exc).__name__,
                "retryable": True,
                "message": str(exc),
            })

        result = {
            "fields": fields,
            "source": "llm",
            "degraded": False,
            "confidence": fields["confidence"],
            "cache_key": key,
            "error": None,
            "skipped": None,
            "breaker": self.breaker.state(),
        }
        self._cache_put(key, result)
        return result
