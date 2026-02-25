# Deva AI 功能中心使用指南

## 📖 概述

Deva AI 功能中心是一个集成在 Admin UI 中的统一 AI 功能体验界面，提供模型配置、代码生成、智能对话和功能演示等功能。

---

## 🚀 快速开始

### 启动 Admin UI

```bash
python -m deva.admin
```

### 访问 AI 功能中心

1. 浏览器访问：`http://127.0.0.1:9999`
2. 登录 Admin UI
3. 点击导航栏的 **🤖 AI** 菜单

---

## 🎯 功能模块

### 1. 🤖 模型配置

**功能说明：**
配置和管理 LLM 模型连接信息。

**支持的模型：**
- Kimi（月之暗面）
- DeepSeek（深度求索）
- Qwen（通义千问）
- GPT（OpenAI）

**配置步骤：**
1. 点击 **🤖 模型配置** Tab
2. 点击要配置的模型对应的 **配置** 按钮
3. 填写配置信息：
   - API Key（必填）
   - Base URL（可选）
   - 模型名称（可选）
4. 点击 **💾 保存**

**测试连接：**
- 点击 **🧪 测试 Kimi** 或 **🧪 测试 DeepSeek** 按钮
- 查看连接测试结果

**配置示例：**

```python
# Kimi 配置
{
    "api_key": "sk-xxxxxxxx",
    "base_url": "https://api.moonshot.cn/v1",
    "model": "moonshot-v1-8k"
}

# DeepSeek 配置
{
    "api_key": "sk-xxxxxxxx",
    "base_url": "https://api.deepseek.com/v1",
    "model": "deepseek-chat"
}
```

---

### 2. 💻 代码生成

**功能说明：**
使用 AI 自动生成 Deva 代码，支持策略、数据源和任务。

#### 2.1 生成量化策略

**步骤：**
1. 点击 **💻 代码生成** Tab
2. 点击 **📊 生成量化策略** 按钮
3. 填写策略需求：
   - 策略名称（例如：双均线策略）
   - 策略描述（详细描述策略逻辑）
   - 输入数据（例如：股票 K 线数据）
   - 输出格式（例如：交易信号）
4. 点击 **🤖 生成代码**
5. 查看生成的代码，可选择：
   - ✅ 使用此代码（保存到策略管理器）
   - 📋 复制代码
   - 🔄 重新生成

**示例需求：**
```
策略名称：双均线策略
策略描述：当 5 日均线上穿 20 日均线时买入，下穿时卖出
输入数据：股票 K 线数据（包含收盘价）
输出格式：交易信号（buy/sell/hold）
```

**生成的代码示例：**
```python
from deva import StrategyUnit

class MovingAverageStrategy(StrategyUnit):
    """双均线策略"""
    
    def process(self, data):
        """
        处理数据并生成交易信号
        
        Args:
            data: 包含收盘价的字典 {'close': [...]}
        
        Returns:
            交易信号：'buy', 'sell', 或 'hold'
        """
        try:
            close_prices = data.get('close', [])
            
            if len(close_prices) < 20:
                return 'hold'
            
            # 计算均线
            ma5 = sum(close_prices[-5:]) / 5
            ma20 = sum(close_prices[-20:]) / 20
            
            # 生成信号
            if ma5 > ma20:
                return 'buy'
            elif ma5 < ma20:
                return 'sell'
            else:
                return 'hold'
                
        except Exception as e:
            self.log.error(f'策略执行错误：{e}')
            return 'hold'
```

#### 2.2 生成数据源

**步骤：**
1. 点击 **📈 生成数据源** 按钮
2. 填写数据源需求：
   - 数据源名称
   - 数据源描述
   - 数据类型
   - 更新频率
3. 点击 **🤖 生成代码**
4. 保存或复制生成的代码

**示例需求：**
```
数据源名称：股票实时数据
数据源描述：从 Yahoo Finance 获取股票实时行情数据
数据类型：dict
更新频率：5 秒
```

#### 2.3 生成任务

**步骤：**
1. 点击 **⚙️ 生成任务** 按钮
2. 填写任务需求：
   - 任务名称
   - 任务描述
   - 执行时间
3. 点击 **🤖 生成代码**
4. 保存或复制生成的代码

**示例需求：**
```
任务名称：每日数据备份
任务描述：每天凌晨备份数据库数据
执行时间：每天 00:00
```

---

### 3. 💬 智能对话

**功能说明：**
与 AI 进行智能对话，解答问题、提供建议等。

**使用方法：**
1. 点击 **💬 智能对话** Tab
2. 在输入框中输入问题
3. 点击 **📤 发送**
4. 查看 AI 回复

**对话示例：**
```
👤 你：如何使用 Deva 创建一个定时器？

🤖 AI：在 Deva 中创建定时器非常简单，以下是示例代码：

from deva import timer, log, Deva

# 每隔 1 秒执行一次
timer(interval=1, func=lambda: "tick", start=True) >> log

Deva.run()

这样就可以每秒输出一次"tick"了。
```

**功能特点：**
- 支持多轮对话（保留最近 5 条历史）
- 自动显示对话历史
- 支持各种编程问题

---

### 4. 🎯 功能演示

**功能说明：**
体验 Deva 的各种 AI 功能。

#### 4.1 文章摘要

**功能：** 自动生成文章摘要

**步骤：**
1. 点击 **📝 文章摘要** 按钮
2. 粘贴文章内容
3. 点击 **🤖 生成摘要**
4. 查看生成的摘要

**示例：**
```
原文：（一篇 1000 字的文章）

摘要：本文介绍了 Deva 流式处理框架的核心功能和使用方法，
包括 Stream、Timer、Bus 等组件，以及如何构建实时数据处理管道。
```

#### 4.2 链接提取

**功能：** 从 HTML 中智能提取重要链接

**步骤：**
1. 点击 **🔗 链接提取** 按钮
2. 粘贴 HTML 代码
3. 点击 **🤖 提取链接**
4. 查看提取的链接（JSON 格式）

**示例输出：**
```json
{
  "important_links": [
    {"title": "最新文章", "url": "https://example.com/latest"},
    {"title": "热门话题", "url": "https://example.com/trending"},
    {"title": "关于我们", "url": "https://example.com/about"}
  ]
}
```

#### 4.3 数据分析

**功能：** AI 分析数据趋势和洞察

**步骤：**
1. 点击 **📊 数据分析** 按钮
2. 粘贴数据（CSV、JSON 等格式）
3. 点击 **🤖 分析数据**
4. 查看分析结果

**示例输入：**
```csv
date,sales,profit
2024-01,10000,2000
2024-02,12000,2400
2024-03,15000,3000
```

**示例输出：**
```
数据分析结果：

1. 销售趋势：
   - 销售额逐月增长，3 个月增长率达 50%
   - 2 月环比增长 20%，3 月环比增长 25%

2. 利润分析：
   - 利润率保持在 20%，表现稳定
   - 3 月利润达到最高的 3000

3. 建议：
   - 继续保持当前增长势头
   - 考虑在 Q2 加大营销投入
```

#### 4.4 新闻翻译

**功能：** 自动翻译外文新闻

**步骤：**
1. 点击 **🌐 新闻翻译** 按钮
2. 粘贴要翻译的文本
3. 选择目标语言
4. 点击 **🤖 翻译**
5. 查看翻译结果

**支持的语言：**
- 中文
- 英文
- 日文
- 韩文
- 法文
- 德文
- 等（取决于模型能力）

---

## 🔧 高级配置

### 自定义模型配置

**添加新模型：**

```python
from deva import NB

llm_config = NB('llm_config', key_mode='explicit')

# 添加新模型配置
llm_config.upsert('custom_model', {
    'api_key': 'your-api-key',
    'base_url': 'https://api.custom-model.com/v1',
    'model': 'custom-model-name'
})
```

### 代码生成模板

**自定义策略模板：**

在 AI 生成代码时，可以在描述中指定模板要求：

```
请使用以下模板生成策略：
1. 类名使用驼峰命名
2. 必须包含错误处理
3. 添加详细注释
4. 实现日志记录
```

---

## ⚠️ 注意事项

### API Key 安全

- ⚠️ **不要** 在公开场合分享 API Key
- ✅ 使用环境变量存储敏感信息
- ✅ 定期更换 API Key

### 使用限制

- 不同模型有不同的调用限制
- 注意查看 API 文档了解配额
- 合理使用避免超额

### 代码审查

- AI 生成的代码需要人工审查
- 测试后再部署到生产环境
- 注意代码安全和性能

---

## 🐛 常见问题

### Q: 配置保存后找不到？

**A:** 配置保存在 `NB('llm_config')` 中，确保：
1. 使用相同的 Python 环境
2. 没有清除缓存
3. 检查配置文件路径

### Q: 代码生成失败？

**A:** 可能原因：
1. 模型未配置或配置错误
2. 网络连接问题
3. API Key 无效或余额不足

**解决方案：**
1. 检查模型配置
2. 测试连接
3. 查看 API 余额

### Q: 对话历史丢失？

**A:** 对话历史保存在会话中：
1. 刷新页面会清空历史
2. 关闭浏览器会清空历史
3. 历史只保留最近 5 条

### Q: 功能演示报错？

**A:** 检查：
1. 模型是否已配置
2. 输入内容格式是否正确
3. 网络连接是否正常

---

## 📚 相关资源

### 内部文档

- [AI_CODE_GENERATION_SYSTEM.md](deva/admin_ui/strategy/AI_CODE_GENERATION_SYSTEM.md)
- [ENHANCED_LOGGING_GUIDE.md](deva/admin_ui/strategy/ENHANCED_LOGGING_GUIDE.md)

### 外部资源

- [Kimi API 文档](https://platform.moonshot.cn/docs)
- [DeepSeek API 文档](https://platform.deepseek.com/docs)
- [通义千问 API 文档](https://help.aliyun.com/zh/dashscope)
- [OpenAI API 文档](https://platform.openai.com/docs)

---

## 🎯 最佳实践

### 1. 模型选择

- **代码生成**：推荐使用 Kimi 或 DeepSeek
- **智能对话**：推荐使用 GPT-4 或 Qwen
- **翻译任务**：推荐使用专业翻译模型

### 2. 提示词优化

**好的提示词：**
```
请生成一个 Deva 数据源代码，要求：
1. 从 Twitter API 获取实时推文
2. 过滤包含特定关键词的推文
3. 每 10 秒更新一次
4. 返回格式：{'tweets': [...]}
```

**不好的提示词：**
```
生成一个数据源
```

### 3. 代码审查清单

- [ ] 语法正确
- [ ] 逻辑清晰
- [ ] 错误处理完善
- [ ] 性能合理
- [ ] 安全性检查

---

**最后更新：** 2026-02-26  
**适用版本：** Deva v1.4.1+  
**维护者：** Deva 团队
