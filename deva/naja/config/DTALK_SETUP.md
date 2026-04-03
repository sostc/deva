# 钉钉通知配置指南

## 📱 快速配置步骤

### 方法一：通过 UI 界面配置（推荐）

1. **打开 Naja 配置管理界面**
   - 访问 Naja 系统
   - 点击"配置管理"或访问配置页面

2. **点击"📱 钉钉通知"按钮**
   - 在配置按钮列表中点击"钉钉通知"

3. **填写配置信息**
   
   **钉钉机器人 Webhook**（必填）:
   ```
   https://oapi.dingtalk.com/robot/send?access_token=你的 token
   ```
   
   **签名密钥 Secret**（可选但推荐）:
   ```
   SECxxxxxxxxxx
   ```

4. **测试发送**
   - 点击"测试发送"按钮
   - 查看钉钉群是否收到测试消息

5. **保存配置**
   - 确认测试成功后点击"保存配置"

---

### 方法二：通过代码配置

```python
from deva import config

# 配置钉钉机器人 webhook
config.set('dtalk.webhook', 'https://oapi.dingtalk.com/robot/send?access_token=xxx')

# 配置签名密钥（推荐）
config.set('dtalk.secret', 'SECxxxxxxxxxx')
```

---

## 🔧 获取钉钉机器人 Webhook

### 步骤 1：在钉钉群中添加机器人

1. 打开钉钉 PC 端或移动端
2. 进入要接收通知的群聊
3. 点击右上角"群设置"（齿轮图标）
4. 选择"智能群助手"
5. 点击"添加机器人"

### 步骤 2：选择自定义机器人

1. 在机器人列表中选择"自定义"
2. 点击"添加"

### 步骤 3：配置机器人

1. **机器人名称**: 填写"Naja 流动性预测"（或任意名称）
2. **头像**: 可选
3. **安全设置**（重要）:
   - 选择"签名"（推荐）或"自定义关键词"
   - 如果选择"签名"，会生成一个 Secret，格式为 `SECxxxxxxxxxx`
   - **复制并保存这个 Secret**，后续配置需要用到

4. **完成添加**
   - 点击"完成"
   - 复制 Webhook 地址

### 步骤 4：复制 Webhook

Webhook 地址格式：
```
https://oapi.dingtalk.com/robot/send?access_token=xxxxxxxxxx
```

---

## ✅ 验证配置

### 方法 1：UI 测试

在配置界面点击"测试发送"按钮，钉钉群应收到以下消息：

```
Naja 流动性预测系统测试
✅ 钉钉通知配置成功！

系统已正确配置，可以正常发送通知。
```

### 方法 2：运行测试脚本

```bash
cd /Users/spark/pycharmproject/deva
python deva/naja/cognition/liquidity/test_notifier.py
```

---

## 📊 通知类型

配置完成后，系统会在以下情况自动发送通知：

### 🔔 预测创建（置信度>70%）
```
🔔 流动性预测 | 美股 → A 股
📉 预测方向：DOWN
📊 置信度：85.0%
💹 源市场变化：-3.50%
⏰ 验证时间：30 分钟后
```

### ✅ 预测验证成功
```
✅ 预测验证成功 | 美股 → A 股
📉 预测方向：DOWN ✓
📊 原置信度：85.0%
💹 实际变化：-2.80%
🎯 预判准确
```

### ❌ 预测验证失败
```
❌ 预测验证失败 | 美股 → A 股
📊 原预测：DOWN (置信度 75.0%)
💹 实际变化：+1.20%
⚠️ 失败原因：direction_mismatch
```

### ⚡ 跨市场共振
```
⚡ 跨市场共振检测 | 88.0%
🌐 共振市场：美股 → A 股 → 港股
📊 共振等级：HIGH
🎯 置信度：88.0%
```

### 📊 流动性信号大幅变化
```
📊 流动性信号大幅变化 | A 股
📊 市场：A 股
🎯 当前状态：🔴 紧张 (信号值 0.35)
📈 变化幅度：↓ 46.2%
```

---

## 🔍 查看通知历史

### 在 Radar UI 中查看

1. 访问 Naja Radar 页面
2. 滚动到"流动性预测体系"面板
3. 查看"🔔 通知历史"区域

显示内容：
- 最近 5 条通知
- 通知类型图标
- 时间戳
- 严重程度
- 发送状态（✓ 已发送 / ✗ 失败）

---

## ⚠️ 常见问题

### Q1: 收不到通知？

**检查清单**：
- [ ] Webhook 地址是否正确
- [ ] Secret 是否正确配置
- [ ] 机器人是否在群中
- [ ] 网络是否连通

### Q2: 发送失败？

**查看错误信息**：
- UI 会显示具体错误
- 检查系统日志：搜索 `[LiquidityNotifier]`

**常见错误**：
- `400` - Webhook 地址错误
- `401` - Secret 签名错误
- `404` - 机器人已被删除

### Q3: 如何禁用通知？

**方法 1：通过代码**
```python
from deva.naja.cognition.liquidity import get_notifier

notifier = get_notifier()
notifier.disable()  # 禁用
notifier.enable()   # 启用
```

**方法 2：删除配置**
- 在配置界面清空 Webhook 地址
- 保存即可

---

## 📝 配置示例

### 完整配置示例

```python
from deva import config

# 基本配置
config.set('dtalk.webhook', 'https://oapi.dingtalk.com/robot/send?access_token=abc123')
config.set('dtalk.secret', 'SECxyz789')

# 验证配置
from deva.endpoints import Dtalk

test_msg = "@md@测试|这是一条测试消息"
test_msg >> Dtalk()
print("测试消息已发送")
```

---

## 🔗 相关文档

- [流动性预测系统文档](deva/naja/cognition/liquidity/README.md)
- [通知器实现](deva/naja/cognition/liquidity/notifier.py)
- [测试脚本](deva/naja/cognition/liquidity/test_notifier.py)

---

## 📞 获取帮助

如有问题，请查看：
1. 系统日志
2. 钉钉机器人管理后台
3. 测试脚本输出

祝使用愉快！🎉
