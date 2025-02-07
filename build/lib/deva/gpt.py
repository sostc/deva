import time
import traceback
from openai import OpenAI,AsyncOpenAI
from deva.namespace import NB
from deva import warn


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
        
        # 验证必要的配置项
        required_configs = ['api_key', 'base_url', 'model']
        missing_configs = []
        for config in required_configs:
            if config not in self.config:
                missing_configs.append(config)
        
        if missing_configs:
            # 生成配置示例代码
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
            
        # 设置默认值为None
        self.api_key = self.config.get('api_key')
        self.base_url = self.config.get('base_url')
        self.model = self.config.get('model')
        self.last_used_model = model_type  # 记录最后使用的模型
        
        # 初始化同步和异步客户端
        self.sync_client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        self.async_client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)
        """
        初始化GPT类，默认使用deepseek模型，可以选择sambanova
        
        参数:
            model_type: 模型类型，默认为'deepseek'
        """
        self.model_type = model_type
        # 从对应类型的数据库获取配置
        self.config = NB(model_type)
        
        # 验证必要的配置项
        required_configs = ['api_key', 'base_url', 'model']
        for config in required_configs:
            if config not in self.config:
                raise ValueError(f"缺少必要的配置项: {config}")
        
        self.api_key = self.config['api_key']
        self.base_url = self.config['base_url']
        self.model = self.config['model']
        
        # 初始化同步和异步客户端
        self.sync_client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        self.async_client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)
    
    def sync_query(self, prompts):
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
            # 尝试切换模型类型
            if self.model_type == 'deepseek':
                self.model_type = 'sambanova'
            else:
                self.model_type = 'deepseek'
            self.config = NB(self.model_type)
            self.api_key = self.config['api_key']
            self.base_url = self.config['base_url']
            self.model = self.config['model']
            self.sync_client = OpenAI(api_key=self.api_key, base_url=self.base_url)
            self.async_client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)
            self.last_used_model = self.model_type  # 更新最后使用的模型
            raise

    async def async_query(self, prompts):
        try:
            # 异常处理
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
            # 尝试切换模型类型
            if self.model_type == 'deepseek':
                self.model_type = 'sambanova'
            else:
                self.model_type = 'deepseek'
            self.config = NB(self.model_type)
            self.api_key = self.config['api_key']
            self.base_url = self.config['base_url']
            self.model = self.config['model']
            self.sync_client = OpenAI(api_key=self.api_key, base_url=self.base_url)
            self.async_client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)
            self.last_used_model = self.model_type  # 更新最后使用的模型
            raise
            
        
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
    
    async def close(self):
        """关闭客户端连接"""
        await self.async_client.close()
        self.sync_client.close()
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

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

if __name__ == '__main__':
    print(sync_gpt('你好哦'))