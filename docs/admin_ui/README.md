# Deva Admin UI 文档中心

## 📖 欢迎使用 Deva Admin UI 文档

Deva Admin UI 是一个功能完整的 Web 管理界面，用于管理和监控 Deva 流处理框架。

---

## 🚀 快速开始

### 5 分钟上手

1. **启动 Admin**
   ```bash
   python -m deva.admin
   ```

2. **访问界面**
   - 浏览器访问：`http://127.0.0.1:9999`
   - 首次使用创建管理员账户

3. **开始使用**
   - 📈 创建策略
   - 📡 配置数据源
   - ⏰ 设置任务
   - 🤖 体验 AI 功能

👉 [快速开始指南](QUICKSTART.md)

---

## 📚 文档目录

### 入门指南

| 文档 | 说明 | 适合人群 |
|------|------|---------|
| [快速开始](QUICKSTART.md) | 5 分钟上手 Admin UI | 所有用户 |
| [架构文档](ARCHITECTURE.md) | Admin UI 架构设计 | 开发者 |
| [功能概览](FEATURES.md) | 功能模块介绍 | 所有用户 |

### 功能模块指南

| 文档 | 说明 | 适合场景 |
|------|------|---------|
| [策略管理](strategy_guide.md) | 量化策略全生命周期管理 | 量化交易 |
| [数据源管理](datasource_guide.md) | 数据源配置和管理 | 数据采集 |
| [任务管理](task_guide.md) | 定时任务调度管理 | 任务调度 |
| [AI 功能中心](ai_center_guide.md) | AI 代码生成和对话 | 所有用户 |
| [监控中心](monitor_guide.md) | 系统监控和告警 | 运维监控 |
| [浏览器管理](browser_guide.md) | 浏览器自动化 | 网页采集 |

### 开发指南

| 文档 | 说明 | 适合人群 |
|------|------|---------|
| [扩展开发](extending.md) | 如何扩展 Admin UI | 开发者 |
| [API 参考](api_reference.md) | 完整 API 文档 | 开发者 |
| [最佳实践](best_practices.md) | 开发最佳实践 | 开发者 |

### 故障排查

| 文档 | 说明 |
|------|------|
| [常见问题](faq.md) | 常见问题解答 |
| [故障排查](troubleshooting.md) | 故障排查指南 |
| [错误代码](error_codes.md) | 错误代码说明 |

---

## 🎯 按场景查找文档

### 场景 1：我是新手，第一次使用

**推荐阅读顺序：**
1. [快速开始](QUICKSTART.md) - 了解基本操作
2. [功能概览](FEATURES.md) - 了解有哪些功能
3. [策略管理](strategy_guide.md) - 尝试创建第一个策略

### 场景 2：我要创建量化策略

**推荐阅读：**
1. [策略管理指南](strategy_guide.md) - 完整策略管理流程
2. [AI 代码生成](ai_center_guide.md) - 使用 AI 生成策略代码
3. [策略最佳实践](best_practices.md#策略编写) - 学习最佳实践

### 场景 3：我要配置数据源

**推荐阅读：**
1. [数据源管理指南](datasource_guide.md) - 数据源配置详解
2. [AI 代码生成](ai_center_guide.md) - 使用 AI 生成数据源代码
3. [数据源示例](examples.md#数据源) - 查看示例代码

### 场景 4：我要设置定时任务

**推荐阅读：**
1. [任务管理指南](task_guide.md) - 任务管理详解
2. [任务调度示例](examples.md#任务) - 查看示例代码

### 场景 5：我想使用 AI 功能

**推荐阅读：**
1. [AI 功能中心指南](ai_center_guide.md) - AI 功能详解
2. [AI 代码生成](ai_center_guide.md#代码生成) - 学习代码生成
3. [智能对话](ai_center_guide.md#智能对话) - 体验智能对话

### 场景 6：我是开发者，要扩展功能

**推荐阅读：**
1. [架构文档](ARCHITECTURE.md) - 了解整体架构
2. [扩展开发指南](extending.md) - 学习如何扩展
3. [API 参考](api_reference.md) - 查看 API 文档

---

## 📋 导航菜单说明

| 菜单 | 路径 | 功能说明 | 相关文档 |
|------|------|---------|---------|
| 🏠 首页 | `/` | 系统概览 | [快速开始](QUICKSTART.md) |
| ⭐ 关注 | `/followadmin` | 关注的内容 | [功能概览](FEATURES.md) |
| 🌐 浏览器 | `/browseradmin` | 浏览器管理 | [浏览器指南](browser_guide.md) |
| 💾 数据库 | `/dbadmin` | 数据库管理 | [API 参考](api_reference.md) |
| 🚌 Bus | `/busadmin` | 消息总线 | [架构文档](ARCHITECTURE.md) |
| 📊 命名流 | `/streamadmin` | 流管理 | [架构文档](ARCHITECTURE.md) |
| 📡 数据源 | `/datasourceadmin` | 数据源管理 | [数据源指南](datasource_guide.md) |
| 📈 策略 | `/strategyadmin` | 策略管理 | [策略指南](strategy_guide.md) |
| 👁 监控 | `/monitor` | 系统监控 | [监控指南](monitor_guide.md) |
| ⏰ 任务 | `/taskadmin` | 任务管理 | [任务指南](task_guide.md) |
| ⚙️ 配置 | `/configadmin` | 系统配置 | [API 参考](api_reference.md) |
| 📄 文档 | `/document` | 文档中心 | - |
| 🤖 AI | `/aicenter` | AI 功能 | [AI 功能指南](ai_center_guide.md) |

---

## 🔧 常用操作速查

### 创建策略

```
1. 点击 📈 策略
2. 点击 ➕ 创建策略
3. 填写策略信息
4. 保存并启动
```

### 配置数据源

```
1. 点击 📡 数据源
2. 点击 ➕ 创建数据源
3. 配置参数
4. 保存并启动
```

### 使用 AI 生成代码

```
1. 点击 🤖 AI
2. 配置 AI 模型（首次使用）
3. 选择代码生成类型
4. 填写需求描述
5. 生成并审查代码
6. 保存代码
```

### 查看监控

```
1. 点击 👁 监控
2. 查看系统指标
3. 查看日志
4. 设置告警
```

---

## 📚 示例代码

### 策略示例

```python
from deva import StrategyUnit

class MovingAverageStrategy(StrategyUnit):
    """双均线策略"""
    
    def process(self, data):
        close = data.get('close', [])
        if len(close) < 20:
            return 'hold'
        
        ma5 = sum(close[-5:]) / 5
        ma20 = sum(close[-20:]) / 20
        
        if ma5 > ma20:
            return 'buy'
        elif ma5 < ma20:
            return 'sell'
        else:
            return 'hold'
```

### 数据源示例

```python
from deva.admin_ui.strategy.datasource import DataSource

class PriceDataSource(DataSource):
    """价格数据源"""
    
    def fetch_data(self):
        return {
            'close': [100, 102, 101, 103, 105],
            'volume': [1000, 1200, 1100, 1300, 1400]
        }
```

### 任务示例

```python
from deva.admin_ui.strategy.task_unit import TaskUnit

class BackupTask(TaskUnit):
    """备份任务"""
    
    def execute(self):
        # 执行备份逻辑
        self.backup_database()
        self.log.info('备份完成')
```

---

## 🐛 常见问题

### Q: 如何启动 Admin UI？

**A:** 
```bash
python -m deva.admin
```
然后访问 `http://127.0.0.1:9999`

### Q: 忘记密码怎么办？

**A:** 
删除配置文件重新创建：
```bash
rm -rf ~/.deva/config
python -m deva.admin
```

### Q: AI 功能无法使用？

**A:** 
1. 检查是否配置了 AI 模型
2. 测试连接是否正常
3. 查看 API Key 是否有效

### Q: 策略无法启动？

**A:** 
1. 检查策略代码语法
2. 查看日志中的错误信息
3. 确认数据源已启动

更多问题请查看 [常见问题](faq.md)

---

## 📞 获取帮助

### 文档资源

- [完整文档](/document) - Admin UI 内置文档
- [GitHub](https://github.com/sostc/deva) - 项目主页
- [Issues](https://github.com/sostc/deva/issues) - 问题反馈

### 社区支持

- 提交 Issue
- 参与讨论
- 查看 Wiki

---

## 📈 更新日志

### v1.4.1 (2026-02-26)

**新增：**
- 🤖 AI 功能中心
- 📝 AI 代码生成
- 💬 智能对话
- 📊 增强策略管理

**改进：**
- 优化 UI 界面
- 提升性能
- 修复已知问题

[查看完整变更日志](../../CHANGELOG.md)

---

**最后更新：** 2026-02-26  
**适用版本：** Deva v1.4.1+  
**维护者：** Deva 团队
