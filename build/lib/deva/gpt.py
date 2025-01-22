import time
import traceback
from openai import OpenAI,AsyncOpenAI
from deva.namespace import NB


class GPT:
    def __init__(self, model_type='deepseek'):
        """
        初始化GPT类，默认使用deepseek模型，可以选择sambanova
        
        参数:
            model_type: 模型类型，默认为'deepseek'
        """
        self.model_type = model_type
        # 从对应类型的数据库获取配置
        self.config = NB(model_type)
        self.api_key = self.config['api_key']
        self.base_url = self.config['base_url']
        self.model = self.config['model']  # 从配置中获取模型名称
        
        # 初始化同步和异步客户端
        self.sync_client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        self.async_client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)
    def sync_query(self, prompts):
        """
        同步查询大模型
        
        参数:
            prompts: 提示词列表或字符串
            
        返回:
            大模型返回的结果
        """
        if isinstance(prompts, str):
            prompts = [prompts]
            
        messages = [{"role": "user", "content": prompt} for prompt in prompts]
        
        response = self.sync_client.chat.completions.create(
            model=self.model,
            messages=messages,
            stream=False
        )
        
        return response.choices[0].message.content
        
    async def async_query(self, prompts):
        """
        异步查询大模型
        
        参数:
            prompts: 提示词列表或字符串
            
        返回:
            大模型返回的结果
        """
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
        
    async def async_json_query(self, prompts):
        """
        异步查询大模型
        
        参数:
            prompts: 提示词列表或字符串
            
        返回:
            大模型返回的结果
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

_gpt = GPT()
async_gpt = _gpt.async_query
sync_gpt = _gpt.sync_query
async_json_gpt = _gpt.async_json_query

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
        response = await _gpt.async_client.chat.completions.create(
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

