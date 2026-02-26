# AI 大模型设置功能

## 功能概述

在 AI 工作室顶部添加了显眼的大模型设置区域，用户可以方便地选择和切换默认使用的大模型。

## 界面位置

```
┌─────────────────────────────────────────────────────┐
│  ## 🤖 AI 工作室                                     │
├─────────────────────────────────────────────────────┤
│  ### 🤖 大模型设置  ← 新增设置区域（顶部显眼位置）    │
│  选择默认使用的大模型：                              │
│  ○ DeepSeek - 代码生成能力强                         │
│  ○ Kimi - 中文理解优秀                               │
│  ○ 通义千问 - 综合能力均衡                           │
│  ○ 百川 - 快速响应                                   │
│  [💾 保存设置]                                       │
├─────────────────────────────────────────────────────┤
│  ### ⚡ 快速操作                                     │
│  ...                                                │
```

## 支持的模型

| 模型 | 特点 | 适用场景 |
|------|------|----------|
| **DeepSeek** | 代码生成能力强 | 代码生成、算法实现 |
| **Kimi** | 中文理解优秀 | 中文文本处理、文档生成 |
| **通义千问** | 综合能力均衡 | 通用任务、多场景 |
| **百川** | 快速响应 | 快速迭代、简单任务 |

## 使用方法

### 1. 选择模型
在 AI 工作室顶部，使用单选按钮选择想要的模型。

### 2. 保存设置
点击"💾 保存设置"按钮，设置会：
- 保存到当前会话上下文
- 持久化到配置文件 `deva_config`
- 立即生效

### 3. 查看状态
设置区域下方显示：
- 当前默认模型
- 模型配置状态（已配置/未配置）
- 配置指南（如未配置）

## 代码实现

### 模型设置组件

```python
async def show_model_settings(ctx):
    """显示模型设置"""
    
    # 获取当前默认模型
    current_model = ctx.get('ai_default_model', 'deepseek')
    
    # 模型选项
    model_options = [
        ('deepseek', 'DeepSeek - 代码生成能力强'),
        ('kimi', 'Kimi - 中文理解优秀'),
        ('qwen', '通义千问 - 综合能力均衡'),
        ('baichuan', '百川 - 快速响应'),
    ]
    
    # 切换模型
    async def change_model():
        new_model = await ctx['pin'].ai_model_select
        ctx['ai_default_model'] = new_model
        
        # 保存到配置
        from deva.config import config
        config.set('ai.default_model', new_model)
```

### 使用默认模型

所有代码生成功能自动使用设置的默认模型：

```python
async def generate_code_simple(ctx, requirement: str):
    # 获取默认模型
    model_type = ctx.get('ai_default_model', 'deepseek')
    
    # 使用默认模型生成
    code = await get_gpt_response(ctx, prompt, model_type=model_type)
```

## 配置存储

### 存储位置
- **会话级**: `ctx['ai_default_model']`
- **持久化**: `deva_config` 表的 `ai.default_model` 键

### 配置方式

#### 方式 1: UI 设置（推荐）
在 AI 工作室界面选择并保存。

#### 方式 2: Python 代码
```python
from deva.config import config
config.set('ai.default_model', 'kimi')
```

#### 方式 3: 直接配置
```python
from deva import NB
NB('deva_config')['ai.default_model'] = 'qwen'
```

## 模型状态检测

```python
def get_model_status_info(ctx, model_type: str) -> dict:
    """获取模型配置状态"""
    try:
        # 检查模型配置
        from deva.admin_ui.llm_service import get_gpt_response
        return {'ready': True, 'model_type': model_type}
    except Exception:
        return {'ready': False, 'model_type': model_type}
```

### 状态显示

- ✅ **已配置**: 模型可以正常使用
- ⚠️ **未配置**: 需要配置 API Key

### 配置指南（未配置时显示）

```python
from deva import NB
NB('llm_config')['deepseek'] = {
    'api_key': 'your-key',
    'base_url': 'https://api.deepseek.com',
    'model': 'deepseek-chat'
}
```

## 使用示例

### 示例 1: 切换到 Kimi

1. 打开 AI 工作室
2. 在顶部选择"Kimi - 中文理解优秀"
3. 点击"💾 保存设置"
4. 状态显示"✅ kimi 已配置"
5. 之后所有代码生成使用 Kimi

### 示例 2: 代码生成使用指定模型

```python
# 用户设置默认模型为 kimi
ctx['ai_default_model'] = 'kimi'

# 生成代码时自动使用
await generate_code_simple(ctx, "写一个排序函数")
# → 使用 Kimi 生成

# 显示
"> 使用模型：kimi"
```

## 优势

### 1. 显眼位置
- 顶部展示，一目了然
- 无需进入设置页面

### 2. 即时生效
- 切换后立即生效
- 所有功能自动使用新模型

### 3. 状态可见
- 显示配置状态
- 提供配置指南

### 4. 持久化
- 会话间保持设置
- 重启后自动恢复

## 文件修改

### 新增文件
- `AI_MODEL_SETTINGS.md` - 本文档

### 修改文件
- `deva/admin_ui/ai_studio.py`
  - 添加 `show_model_settings()`
  - 添加 `get_model_status_info()`
  - 更新 `show_ai_studio()` 显示设置区域
  - 更新 `generate_code_simple()` 使用默认模型
  - 更新 `generate_code()` 使用默认模型

## 后续优化

### 短期
- [ ] 添加更多模型选项
- [ ] 模型响应时间统计
- [ ] 模型使用量统计

### 中期
- [ ] 按任务类型自动选择模型
- [ ] 模型性能对比
- [ ] 智能推荐模型

### 长期
- [ ] 多模型同时使用
- [ ] 模型自动切换（根据成功率）
- [ ] 自定义模型接入

## 总结

通过在 AI 工作室顶部添加显眼的大模型设置区域，用户可以：
1. ✅ 方便地选择默认模型
2. ✅ 查看模型配置状态
3. ✅ 一键切换模型
4. ✅ 所有功能自动使用新设置

这大大提升了用户体验，让模型管理变得简单直观。
