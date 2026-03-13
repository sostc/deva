import requests
import json

# 小红书 MCP 服务地址
url = "http://localhost:18060/mcp"

# 构建请求数据 (MCP 2.0 格式)
data = {
    "version": "2.0",
    "toolcall": {
        "thought": "发布 hello world 测试帖子",
        "name": "xiaohongshu.publish_content",
        "params": {
            "content": "helloworld",
            "images": ["https://picsum.photos/600/400"],
            "is_original": True,
            "products": [],
            "title": "Hello World 测试"
        }
    }
}

# 发送请求
response = requests.post(url, json=data)

# 打印响应
print("Response status code:", response.status_code)
print("Response content:", response.text)
