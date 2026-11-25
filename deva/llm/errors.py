"""
LLM 调用异常：按 HTTP 状态码分类，不做任何文案匹配

调用方据此判断「能不能重试」，而不是去猜 RuntimeError 里写了什么：

    LLMQuotaError      402 配额/余额不足       不可重试
    LLMAuthError       401/403 鉴权失败        不可重试
    LLMConfigError     本地缺配置              不可重试
    LLMRequestError    其他 4xx 请求错误       不可重试
    LLMRateLimitError  429 限流                可重试（退避后）
    LLMServiceError    5xx / 连接失败 / 未知   可重试
    LLMTimeoutError    超时                    可重试
    LLMResponseError   返回空响应              可重试

分类函数只接收状态码；provider_message 仅用于展示与日志，**不参与分类**。
"""

from __future__ import annotations

from typing import Optional


class LLMError(Exception):
    """所有 LLM 调用失败的基类。"""

    kind = "llm_error"
    retryable = False

    def __init__(
        self,
        message: str,
        *,
        status_code: Optional[int] = None,
        provider_message: str = "",
    ):
        super().__init__(message)
        self.status_code = status_code
        self.provider_message = provider_message

    def __str__(self) -> str:
        base = super().__str__()
        if self.status_code is not None and str(self.status_code) not in base:
            return f"{base} (HTTP {self.status_code})"
        return base


class LLMQuotaError(LLMError):
    """配额/余额不足（402）——充钱之前重试永远不会成功。"""

    kind = "quota"
    retryable = False


class LLMAuthError(LLMError):
    """密钥无效/无权限（401/403）。"""

    kind = "auth"
    retryable = False


class LLMConfigError(LLMError):
    """本地模型配置缺失，还没发请求就失败。"""

    kind = "config"
    retryable = False


class LLMRequestError(LLMError):
    """其他 4xx：请求参数/模型名等错误，重试无意义。"""

    kind = "request"
    retryable = False


class LLMRateLimitError(LLMError):
    kind = "rate_limit"
    retryable = True


class LLMServiceError(LLMError):
    kind = "service"
    retryable = True


class LLMTimeoutError(LLMError):
    kind = "timeout"
    retryable = True


class LLMResponseError(LLMError):
    """服务端返回空响应/空 choices。"""

    kind = "response"
    retryable = True


def from_api_status(status_code: Optional[int], provider_message: str = "") -> LLMError:
    """把 HTTP 状态码映射成异常实例。只接收状态码，不解析 provider_message。"""
    status = status_code
    if status == 402:
        return LLMQuotaError("LLM 配额/余额不足，请充值后再试", status_code=status,
                             provider_message=provider_message)
    if status in (401, 403):
        return LLMAuthError("LLM 鉴权失败：密钥无效或没有权限", status_code=status,
                            provider_message=provider_message)
    if status == 429:
        return LLMRateLimitError("LLM 请求被限流，请退避后重试", status_code=status,
                                 provider_message=provider_message)
    if status == 408:
        return LLMTimeoutError("LLM 请求超时", status_code=status,
                               provider_message=provider_message)
    if status is not None and 400 <= status < 500:
        return LLMRequestError(f"LLM 请求错误（HTTP {status}）", status_code=status,
                               provider_message=provider_message)
    return LLMServiceError(f"LLM 服务不可用（HTTP {status}）", status_code=status,
                           provider_message=provider_message)


def is_non_retryable(exc: BaseException) -> bool:
    """调用方判据：True = 重试也不会成功，应停止/熔断。"""
    return isinstance(exc, LLMError) and not exc.retryable


_FRIENDLY = {
    "quota": "API 余额不足，请充值后重试",
    "auth": "API 密钥无效或已过期，请检查配置",
    "config": "模型配置缺失，请先完成配置",
    "request": "模型请求参数有误",
    "rate_limit": "请求过于频繁，请稍后重试",
    "service": "模型服务暂时不可用，请稍后重试",
    "timeout": "模型请求超时，请稍后重试",
    "response": "模型返回空内容，请稍后重试",
}


def friendly_message(exc: BaseException) -> str:
    """给 UI/日志用的中文提示；非 LLMError 保持原始异常描述。"""
    if isinstance(exc, LLMError):
        return _FRIENDLY.get(exc.kind, str(exc))
    return f"请求失败: {type(exc).__name__}: {exc}"
