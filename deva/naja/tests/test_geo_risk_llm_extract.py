"""
P5 LLM 抽取验收：缓存命中去重付费、不可重试错误熔断 1 小时、规则降级。

全部用假 LLM，不联网、不读库。
"""

import asyncio
import json

from deva.llm.errors import LLMQuotaError, LLMServiceError
from deva.naja.geo_risk.llm.extract import (
    CircuitBreaker,
    GeoRiskExtractor,
    cache_key,
    rule_extract,
)

ARTICLE = {
    "source": "fixture.operator",
    "url": "fixture://geo-risk/extract/ytl-johor",
    "title": "YTL 柔佛园区一期",
    "text": "YTL Power 在柔佛 Kulai 的 AI 数据中心开工，规划 300MW，部署 20000 张 GPU。",
}


class FakeLLM:
    """按顺序返回预设响应；Exception 则抛出。"""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    async def __call__(self, prompt):
        self.calls += 1
        item = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(item, BaseException):
            raise item
        return item


def _llm_json(**overrides):
    base = {
        "project_name": "YTL Johor AI Data Centre",
        "operator": "YTL Power",
        "country": "MY",
        "site": "Kulai, Johor",
        "capacity_mw": 300,
        "gpu_count": 20000,
        "event_type": "construction",
        "quote": "YTL Power 在柔佛 Kulai 的 AI 数据中心开工",
        "confidence": 0.86,
        "secret": "不应出现在结果里",
    }
    base.update(overrides)
    return json.dumps(base, ensure_ascii=False)


def run(coro):
    return asyncio.run(coro)


def test_llm_extract_whitelists_fields_and_caches():
    fake = FakeLLM([_llm_json()])
    extractor = GeoRiskExtractor(llm=fake)

    first = run(extractor.extract(ARTICLE))
    assert first["source"] == "llm"
    assert first["degraded"] is False
    assert first["fields"]["capacity_mw"] == 300
    assert first["fields"]["gpu_count"] == 20000
    assert first["fields"]["country"] == "MY"
    assert "secret" not in first["fields"]
    assert first["cache_key"] == cache_key(ARTICLE["url"], ARTICLE["text"])

    second = run(extractor.extract(ARTICLE))
    assert second["source"] == "cache"
    assert fake.calls == 1


def test_non_retryable_error_trips_breaker_for_one_hour():
    now = [1000.0]
    breaker = CircuitBreaker(cooldown_seconds=3600, clock=lambda: now[0])
    fake = FakeLLM([LLMQuotaError("quota", status_code=402)])
    extractor = GeoRiskExtractor(llm=fake, breaker=breaker)

    first = run(extractor.extract(ARTICLE))
    assert first["source"] == "rule"
    assert first["degraded"] is True
    assert first["error"]["kind"] == "quota"
    assert first["error"]["retryable"] is False
    assert breaker.is_open() is True
    # 降级结果不进缓存，熔断期内换一篇文章也不再调用模型
    other = dict(ARTICLE, url="fixture://geo-risk/extract/other", text="另一个项目 100MW")
    second = run(extractor.extract(other))
    assert second["skipped"] == "circuit_open"
    assert fake.calls == 1

    now[0] += 3601
    third = run(extractor.extract(other))
    assert fake.calls == 2
    assert third["skipped"] is None


def test_retryable_error_falls_back_without_tripping():
    fake = FakeLLM([LLMServiceError("boom", status_code=503), _llm_json()])
    breaker = CircuitBreaker(clock=lambda: 1000.0)
    extractor = GeoRiskExtractor(llm=fake, breaker=breaker)

    first = run(extractor.extract(ARTICLE))
    assert first["source"] == "rule"
    assert first["error"]["retryable"] is True
    assert breaker.is_open() is False

    second = run(extractor.extract(ARTICLE))
    assert second["source"] == "llm"
    assert fake.calls == 2


def test_bad_json_falls_back_without_tripping():
    fake = FakeLLM(["这不是 JSON"])
    extractor = GeoRiskExtractor(llm=fake)
    out = run(extractor.extract(ARTICLE))
    assert out["source"] == "rule"
    assert out["error"]["kind"] == "ValueError"
    assert extractor.breaker.is_open() is False


def test_rule_extract_pulls_numbers_and_keywords():
    text = "银团为柔佛数据中心提供项目融资，规模 300MW，部署 20,000 张 GPU。"
    fields = rule_extract({"text": text})
    assert fields["country"] == "MY"
    assert fields["capacity_mw"] == 300.0
    assert fields["gpu_count"] == 20000
    assert fields["event_type"] == "financing"
    assert fields["confidence"] == 0.25

    construction = rule_extract({"text": "泰国园区正式开工，规划 120MW。"})
    assert construction["country"] == "TH"
    assert construction["event_type"] == "construction"


def test_all_paths_are_json_serializable():
    fake = FakeLLM([_llm_json()])
    llm_out = run(GeoRiskExtractor(llm=fake).extract(ARTICLE))
    rule_out = run(GeoRiskExtractor(llm=FakeLLM([LLMQuotaError("q")])).extract(ARTICLE))
    json.dumps(llm_out, ensure_ascii=False)
    json.dumps(rule_out, ensure_ascii=False)
