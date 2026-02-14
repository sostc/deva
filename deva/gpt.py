import time
import traceback
from .namespace import NB
from .bus import warn

try:
    from openai import OpenAI, AsyncOpenAI
except ImportError:
    OpenAI = None
    AsyncOpenAI = None



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
        self.config = NB(model_type)
        
        # 验证配置项
        required_configs = ['api_key', 'base_url', 'model']
        missing_configs = [c for c in required_configs if c not in self.config]
        
        if missing_configs:
            example_code = "from deva.namespace import NB\n\n"
            example_code += "# 配置示例:\n"
            example_code += "NB('deepseek').update({\n"
            for config in missing_configs:
                if config == 'api_key':
                    example_code += "    'api_key': 'your-api-key-here',\n"
                elif config == 'base_url':
                    example_code += "    'base_url': 'https://api.example.com/v1',\n"
                elif config == 'model':
                    example_code += "    'model': 'model-name',\n"
            example_code += "})"
            "警告: 在NB配置中缺少以下必要配置项: " + ', '.join(missing_configs) >> warn
            "请确保在其他地方正确设置这些配置项的值" >> warn
            example_code >> warn
            
        self.api_key = self.config.get('api_key')
        self.base_url = self.config.get('base_url')
        self.model = self.config.get('model')
        self.last_used_model = model_type
        
        # 初始化客户端
        self.sync_client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        self.async_client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)
    
    def sync_query(self, prompts):
        """
        同步查询大模型
        
        参数:
            prompts (str|list): 提示词，可以是字符串或字符串列表
            
        返回:
            str: 模型生成的文本
            
        异常:
            Exception: 查询失败时抛出，并自动切换模型类型
        """
        try:
            if isinstance(prompts, str):
                prompts = [prompts]
                
            messages = [{"role": "user", "content": prompt} for prompt in prompts]
            
            response = self.sync_client.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=False
            )
            print(response)
            
            return response.choices[0].message.content
        except Exception as e:
            print(f"同步查询失败: {traceback.format_exc()}")
            self._switch_model()
            raise

    async def async_query(self, prompts):
        """
        异步查询大模型
        
        参数:
            prompts (str|list): 提示词，可以是字符串或字符串列表
            
        返回:
            str: 模型生成的文本
            
        异常:
            Exception: 查询失败时抛出，并自动切换模型类型
        """
        try:
            if isinstance(prompts, str):
                prompts = [prompts]
                
            messages = [{"role": "user", "content": prompt} for prompt in prompts]
        
            completion = await self.async_client.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=False,
                max_tokens=8000
            )
            
            return completion.choices[0].message.content
        except Exception as e:
            print(f"异步查询失败: {traceback.format_exc()}")
            self._switch_model()
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
        if isinstance(prompts, str):
            prompts = [prompts]
            
        messages = [{"role": "user", "content": prompt} for prompt in prompts]
        
        completion = await self.async_client.chat.completions.create(
            model=self.model,
            messages=messages,
            stream=False,
            max_tokens=8000,
            response_format={
                'type': 'json_object'
            }
        )
        
        return completion.choices[0].message.content
    
    async def close(self):
        """关闭客户端连接，释放资源"""
        await self.async_client.close()
        self.sync_client.close()
    
    async def __aenter__(self):
        """上下文管理器入口"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口，自动关闭连接"""
        await self.close()
    
    def _switch_model(self):
        """内部方法：在模型失败时切换模型类型"""
        self.model_type = 'sambanova' if self.model_type == 'deepseek' else 'deepseek'
        self.config = NB(self.model_type)
        self.api_key = self.config['api_key']
        self.base_url = self.config['base_url']
        self.model = self.config['model']
        self.sync_client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        self.async_client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)
        self.last_used_model = self.model_type


_gpt = None


def get_gpt(model_type='deepseek'):
    global _gpt
    if _gpt is None or _gpt.model_type != model_type:
        _gpt = GPT(model_type=model_type)
    return _gpt


def sync_gpt(prompts):
    return get_gpt().sync_query(prompts)


async def async_gpt(prompts):
    return await get_gpt().async_query(prompts)


async def async_json_gpt(prompts):
    return await get_gpt().async_json_query(prompts)

async def get_gpt_response(prompt, display_func=print, flush_interval=3):
    """获取GPT的流式响应
    
    Args:
        prompt: 用户输入的提示词
        display_func: 显示内容的函数，默认为display_markdown
        flush_interval: 刷新显示的间隔时间（秒），默认为3秒
        
    Returns:
        None
    """
    start_time = time.time()
    
    # 初始化消息列表
    messages = [{"role": "user", "content": prompt}]
    
    try:
        # 创建GPT流式响应
        response = await get_gpt().async_client.chat.completions.create(
            model=NB('deepseek')['model'],
            messages=messages,
            stream=True,
            max_tokens=8192
        )
    except Exception as e:
        print(f"请求失败: {traceback.format_exc()}")
        display_func("当前请求人数过多，请稍后重试~~")
        return

    # 初始化文本缓冲区
    buffer = ""
    accumulated_text = ""
    
    async def process_chunk(chunk, buffer, accumulated_text, start_time):
        """处理单个响应块
        
        参数:
            chunk: 响应块
            buffer: 当前缓冲区
            accumulated_text: 累计文本
            start_time: 开始时间
            
        返回:
            tuple: (更新后的buffer, 更新后的accumulated_text, 更新后的start_time)
        """
        if chunk.choices[0].delta.content:
            buffer += chunk.choices[0].delta.content
            
            # 当遇到换行符且超过指定间隔时间时，显示缓冲内容
            if "\n" in chunk.choices[0].delta.content and time.time()-start_time >= flush_interval:
                buffer = buffer.strip("\n")
                if buffer:
                    accumulated_text += buffer
                    display_func(buffer)
                    start_time = time.time()
                buffer = ""
                
        # 处理最后一个未显示的块
        if buffer and not chunk.choices[0].delta.content:
            accumulated_text += buffer
            display_func(buffer)
            start_time = time.time()
            buffer = ""
            
        return buffer, accumulated_text, start_time

    async for chunk in response:
        buffer, accumulated_text, start_time = await process_chunk(
            chunk, buffer, accumulated_text, start_time
        )

if __name__ == '__main__':
    print(sync_gpt('你好哦'))
