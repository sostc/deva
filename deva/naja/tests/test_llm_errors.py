"""
LLM 异常契约：状态码分类、重试判定、友好提示。

不依赖 openai SDK，可在任何测试里直接导入。
"""

import pytest

from deva.llm.errors import (
    LLMAuthError,
    LLMConfigError,
    LLMError,
    LLMQuotaError,
    LLMRateLimitError,
    LLMRequestError,
    LLMResponseError,
    LLMServiceError,
    LLMTimeoutError,
    friendly_message,
    from_api_status,
    is_non_retryable,
)


@pytest.mark.parametrize("status,cls,retryable", [
    (402, LLMQuotaError, False),
    (401, LLMAuthError, False),
    (403, LLMAuthError, False),
    (400, LLMRequestError, False),
    (404, LLMRequestError, False),
    (429, LLMRateLimitError, True),
    (408, LLMTimeoutError, True),
    (500, LLMServiceError, True),
    (503, LLMServiceError, True),
])
def test_status_maps_to_typed_error(status, cls, retryable):
    exc = from_api_status(status)
    assert type(exc) is cls
    assert exc.status_code == status
    assert exc.retryable is retryable
    assert str(status) in str(exc)


def test_classification_never_uses_provider_text():
    # 400 + "Insufficient Balance" 仍是不可重试的请求错误，而不是配额错误
    exc = from_api_status(400, "Insufficient Balance")
    assert isinstance(exc, LLMRequestError)
    assert not isinstance(exc, LLMQuotaError)
    assert exc.provider_message == "Insufficient Balance"


def test_unknown_status_is_retryable_service_error():
    exc = from_api_status(None)
    assert isinstance(exc, LLMServiceError)
    assert exc.retryable is True
    assert exc.status_code is None


def test_config_and_response_errors():
    assert isinstance(LLMConfigError("缺配置"), LLMError)
    assert LLMConfigError("缺配置").retryable is False
    assert LLMResponseError("空响应").retryable is True


def test_is_non_retryable_and_friendly_message():
    assert is_non_retryable(LLMQuotaError("quota"))
    assert is_non_retryable(LLMAuthError("auth"))
    assert not is_non_retryable(LLMRateLimitError("rate"))
    assert not is_non_retryable(ValueError("plain"))

    assert "余额" in friendly_message(LLMQuotaError("quota"))
    assert "密钥" in friendly_message(LLMAuthError("auth"))
    assert "配置" in friendly_message(LLMConfigError("config"))
    assert "超时" in friendly_message(LLMTimeoutError("timeout"))
    assert friendly_message(ValueError("x")).startswith("请求失败")
