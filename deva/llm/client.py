import threading
import time
import traceback
from openai import APIStatusError, APIConnectionError, APITimeoutError
from ..core.namespace import NB
from ..core.bus import log, warn, debug
from .worker_runtime import run_ai_in_worker, run_sync_in_worker
from .errors import (
    LLMError,
    LLMConfigError,
    LLMResponseError,
    LLMServiceError,
    LLMTimeoutError,
    friendly_message,
    from_api_status,
)
from .config_utils import (
    build_model_config_example,
    build_model_config_message,
    get_model_config_status,
)

try:
    from openai import OpenAI, AsyncOpenAI
except ImportError:
    OpenAI = None
    AsyncOpenAI = None


def _status_code(error: Exception):
    """只认数值状态码；provider 的 code 若是字符串（如 invalid_api_key）不参与分类。"""
    status = getattr(error, "status_code", None)
    if status is None:
        code = getattr(error, "code", None)
        status = code if isinstance(code, int) else None
    return status


def _provider_message(error: Exception) -> str:
    """仅用于展示/日志，不参与异常分类。"""
    response = getattr(error, "response", None)
    try:
        body = response.json() if response is not None and hasattr(response, "json") else {}
    except Exception:
        return ""
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            return str(err.get("message") or "")
    return ""



class GPT:
    """
    GPT类封装了与大型语言模型（如DeepSeek、Sambanova）的交互功能。
    提供同步和异步两种调用方式，支持普通文本和JSON格式的响应。
    
    主要功能：
    - 同步查询：sync_query()
    - 异步查询：async_query()
    - 异步JSON查询：async_json_query()
    - 自动模型切换：当某个模型失败时自动切换到备用模型
    - 资源管理：支持上下文管理器自动关闭连接
    
    属性：
    - model_type: 当前使用的模型类型（deepseek或sambanova）
    - config: 模型配置信息
    - api_key: API访问密钥
    - base_url: API基础URL
    - model: 模型名称
    - last_used_model: 最后使用的模型类型
    
    示例用法：
    1. 同步查询
    >>> gpt = GPT()
    >>> response = gpt.sync_query("你好")
    >>> print(response)
    
    2. 异步查询
    >>> async def main():
    ...     gpt = GPT()
    ...     response = await gpt.async_query("你好")
    ...     print(response)
    
    3. 使用上下文管理器
    >>> async def main():
    ...     async with GPT() as gpt:
    ...         response = await gpt.async_query("你好")
    ...         print(response)
    
    4. JSON格式查询
    >>> async def main():
    ...     gpt = GPT()
    ...     json_response = await gpt.async_json_query("返回JSON格式的天气数据")
    ...     print(json_response)
    """
    def __init__(self, model_type='deepseek'):
        """
        初始化GPT实例
        
        参数:
            model_type (str): 模型类型，默认为'deepseek'，可选'sambanova'
        
        异常:
            ValueError: 当缺少必要配置项时抛出
        """
        if OpenAI is None or AsyncOpenAI is None:
            raise ImportError(
                "openai is required for GPT features. Install with: pip install 'deva[llm]'"
            )

        self.model_type = model_type
        self.config = None
        self.api_key = None
        self.base_url = None
        self.model = None
        self._missing_configs = []
        self._load_model_config(model_type)
        self.last_used_model = model_type

    def _load_model_config(self, model_type):
        status = get_model_config_status(NB, model_type)
        self.model_type = model_type
        self.config = status["config"]
        self._missing_configs = status["missing"]
        self.api_key = self.config.get("api_key")
        base_url = self.config.get("base_url", "")
        if base_url.endswith(','):
            base_url = base_url[:-1].rstrip()
        self.base_url = base_url
        self.model = self.config.get("model")

        if status["ready"]:
            return True

        build_model_config_message(model_type, self._missing_configs) >> warn
        "请先执行以下配置代码，再重试。" >> warn
        build_model_config_example(model_type, self._missing_configs) >> warn
        return False

    def _ensure_model_ready(self):
        if not self._missing_configs:
            return
        raise LLMConfigError(
            build_model_config_message(self.model_type, self._missing_configs)
            + " 请先完成配置。"
        )
        
    async def _chat_create(self, *, messages, stream=False, max_tokens=8000, response_format=None):
        self._ensure_model_ready()
        client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)
        try:
            kwargs = dict(model=self.model, messages=messages, stream=stream, max_tokens=max_tokens)
            if response_format is not None:
                kwargs["response_format"] = response_format
            return await client.chat.completions.create(**kwargs)
        finally:
            await client.close()

    def _raise_for_api_error(self, error: APIStatusError, label: str):
        """按 HTTP 状态码抛对应异常；只有可重试错误才切换备用模型。"""
        exc = from_api_status(_status_code(error), _provider_message(error))
        {"level": "ERROR", "source": "deva.llm", "message": f"{label}: {exc}",
         "traceback": traceback.format_exc()} >> warn
        if exc.retryable:
            self._switch_model()
        raise exc from error

    def _raise_transient(self, error: BaseException, label: str, *, timeout: bool):
        exc = (LLMTimeoutError("LLM 请求超时") if timeout
               else LLMServiceError(f"LLM 连接失败: {type(error).__name__}"))
        {"level": "ERROR", "source": "deva.llm", "message": f"{label}: {exc}",
         "traceback": traceback.format_exc()} >> warn
        self._switch_model()
        raise exc from error
    
    def sync_query(self, prompts):
        """
        同步查询大模型
        
        参数:
            prompts (str|list): 提示词，可以是字符串或字符串列表
            
        返回:
            str: 模型生成的文本
            
        异常:
            LLMError 子类：配额/鉴权/配置错误不可重试，限流/服务/超时/空响应可重试。
        """
        try:
            if isinstance(prompts, str):
                prompts = [prompts]

            messages = [{"role": "user", "content": prompt} for prompt in prompts]

            import warnings
            warnings.filterwarnings("ignore", message="run_sync_in_worker.*async context", category=RuntimeWarning)
            from .worker_runtime import run_sync_in_worker
            response = run_sync_in_worker(
                self._chat_create(messages=messages, stream=False, max_tokens=8000)
            )
            {"level": "DEBUG", "source": "deva.llm", "message": "sync query response received"} >> debug

            # 检查响应是否有效
            if response is None or response.choices is None or len(response.choices) == 0:
                raise LLMResponseError("LLM 返回空响应")

            message_content = response.choices[0].message.content if response.choices[0].message else None
            if message_content is None:
                raise LLMResponseError("LLM 返回空消息内容")

            return message_content
        except APIStatusError as e:
            self._raise_for_api_error(e, "同步查询失败")
        except (TimeoutError, APITimeoutError) as e:
            self._raise_transient(e, "同步查询失败", timeout=True)
        except APIConnectionError as e:
            self._raise_transient(e, "同步查询失败", timeout=False)
        except LLMError:
            raise
        except Exception as e:
            {"level": "ERROR", "source": "deva.llm", "message": "同步查询失败", "traceback": traceback.format_exc()} >> warn
            raise

    async def async_query(self, prompts):
        """
        异步查询大模型
        
        参数:
            prompts (str|list): 提示词，可以是字符串或字符串列表
            
        返回:
            str: 模型生成的文本
            
        异常:
            LLMError 子类：配额/鉴权/配置错误不可重试，限流/服务/超时/空响应可重试。
        """
        try:
            if isinstance(prompts, str):
                prompts = [prompts]
                
            messages = [{"role": "user", "content": prompt} for prompt in prompts]
        
            completion = await run_ai_in_worker(
                self._chat_create(messages=messages, stream=False, max_tokens=8000)
            )

            if completion is None:
                raise LLMResponseError("异步查询返回结果为空")

            if not completion.choices:
                log.error(f"[LLM调用来源]\n{''.join(traceback.format_stack())}")
                log.error(f"[LLM响应详情] completion={completion}, dir={dir(completion)}")
                if hasattr(completion, 'model_dump'):
                    log.error(f"[LLM响应] model_dump={completion.model_dump()}")
                raise LLMResponseError("异步查询返回结果为空，choices 为空")

            if completion.choices[0].message is None:
                raise LLMResponseError("异步查询返回结果为空，message 为 None")

            return completion.choices[0].message.content
        except APIStatusError as e:
            self._raise_for_api_error(e, "异步查询失败")
        except (TimeoutError, APITimeoutError) as e:
            self._raise_transient(e, "异步查询失败", timeout=True)
        except APIConnectionError as e:
            self._raise_transient(e, "异步查询失败", timeout=False)
        except LLMError:
            raise
        except Exception as e:
            {"level": "ERROR", "source": "deva.llm", "message": "异步查询失败", "traceback": traceback.format_exc()} >> warn
            raise
            
    async def async_json_query(self, prompts):
        """
        异步查询大模型并返回JSON格式结果
        
        参数:
            prompts (str|list): 提示词，可以是字符串或字符串列表
            
        返回:
            str: JSON格式的模型响应
            
        示例:
        >>> response = await gpt.async_json_query("返回JSON格式的天气数据")
        >>> print(response)  # 输出: {"weather": "sunny", "temperature": 25}
        """
        try:
            if isinstance(prompts, str):
                prompts = [prompts]

            messages = [{"role": "user", "content": prompt} for prompt in prompts]

            completion = await run_ai_in_worker(
                self._chat_create(
                    messages=messages,
                    stream=False,
                    max_tokens=8000,
                    response_format={'type': 'json_object'}
                )
            )

            if completion is None or not getattr(completion, "choices", None):
                raise LLMResponseError("异步 JSON 查询返回结果为空")

            return completion.choices[0].message.content
        except APIStatusError as e:
            self._raise_for_api_error(e, "异步 JSON 查询失败")
        except (TimeoutError, APITimeoutError) as e:
            self._raise_transient(e, "异步 JSON 查询失败", timeout=True)
        except APIConnectionError as e:
            self._raise_transient(e, "异步 JSON 查询失败", timeout=False)
        except LLMError:
            raise
        except Exception as e:
            {"level": "ERROR", "source": "deva.llm", "message": "异步 JSON 查询失败", "traceback": traceback.format_exc()} >> warn
            raise
    
    async def close(self):
        """关闭客户端连接，释放资源"""
        return None
    
    async def __aenter__(self):
        """上下文管理器入口"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口，自动关闭连接"""
        await self.close()
    
    def _switch_model(self):
        """内部方法：在模型失败时切换模型类型"""
        current_model = self.model_type
        target_model = 'sambanova' if current_model == 'deepseek' else 'deepseek'
        if self._load_model_config(target_model):
            self.last_used_model = self.model_type
            return
        self._load_model_config(current_model)
        f"备用模型 {target_model} 也未完成配置，保持当前模型 {current_model}。" >> warn


_gpt = None
_gpt_lock = threading.Lock()


def get_gpt(model_type='deepseek'):
    global _gpt
    with _gpt_lock:
        if _gpt is None or _gpt.model_type != model_type:
            _gpt = GPT(model_type=model_type)
        return _gpt


def sync_gpt(prompts):
    return get_gpt().sync_query(prompts)


async def async_gpt(prompts):
    return await get_gpt().async_query(prompts)


async def async_json_gpt(prompts):
    return await get_gpt().async_json_query(prompts)

async def get_gpt_response(prompt, display_func=None, flush_interval=3):
    """获取GPT的流式响应
    
    Args:
        prompt: 用户输入的提示词
        display_func: 显示内容的函数，默认为display_markdown
        flush_interval: 刷新显示的间隔时间（秒），默认为3秒
        
    Returns:
        None
    """
    if display_func is None:
        display_func = lambda text: text >> log
    start_time = time.time()
    
    try:
        text = await get_gpt().async_query(prompt)
    except Exception as e:
        {"level": "ERROR", "source": "deva.llm", "message": f"请求失败: {e}", "traceback": traceback.format_exc()} >> warn
        display_func(friendly_message(e))
        return
    if text:
        for paragraph in str(text).split("\n"):
            if paragraph.strip():
                display_func(paragraph)

if __name__ == '__main__':
    sync_gpt('你好哦') >> log
