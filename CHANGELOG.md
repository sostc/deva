# 变更日志

本文档记录 Deva 项目的所有重要变更。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [未发布]

### 新增
- 完整的文档体系（快速开始、安装指南、使用手册、最佳实践、故障排查、API 参考、术语表）
- Admin UI 文档中心集成（25 个文档 Tab）
- 文件组织自动化工具（organize_files.py）
- 版本管理工具（scripts/version.py）

### 修复
- 数据源列表页自动刷新功能
- 任务管理面板 UI 问题
- 文档 RST 渲染问题

### 变更
- 重构项目文件结构（根目录从 60+ 文件精简到 19 个）
- 优化文档渲染性能
- 改进测试组织结构

### 移除
- 根目录临时报告文件
- 根目录散乱的测试文件
- 根目录工具脚本

## [1.4.3] - 2026-02-27

### 修复
- requirements.txt - 补全缺失的依赖项（从 6 个扩展到 20+ 个）
- setup.py - 内联依赖列表，添加版本约束
- README.rst - 移除 PyPI 不支持的 Sphinx toctree 指令

### 变更
- python_requires: '>=3.5' -> '>=3.8'
- 添加 'dev' extras_require（开发依赖）
- 从 git 跟踪中移除 build/ 和 dist/ 目录

## [1.4.2] - 2026-02-27

### 变更
- deva/sources.py - 使用 Pipe 模式重构 HTTP 编解码逻辑
  - `_decode_http_body` - 使用 `P.map` 链式调用重构解码逻辑
  - `_encode_http_body` - 使用 `P.map` 重构编码逻辑
  - `from_textfile.get_data` - 使用 Pipe 和 `ls` 重构数据分割

### 文档
- 规整文档结构，将根目录报告文件移动到 docs/ 子目录
  - docs/reports/admin_ui/ - Admin UI 相关报告
  - docs/reports/ai/ - AI 相关报告
  - docs/guides/ai/ - AI 相关指南
  - docs/reports/ - 通用报告

## [1.4.1] - 2026-02-26

### 新增
- 任务管理功能（TaskManager, TaskUnit）
- AI 代码生成系统（InteractiveCodeGenerator, AICodeGenerationUI）
- 增强日志系统（LoggingContext, EnhancedLoggingAdapter）
- 可执行单元架构（ExecutableUnit, StrategyUnit, DataSource）

### 修复
- 数据源缓存和 start 状态问题
- 数据源数字跳动显示问题
- 数据源排序功能
- 数据源持久化问题
- UI 组件性能问题

### 变更
- Admin UI 重构（增强任务面板、策略面板）
- 数据源面板增强（编辑、详情、状态管理）
- 优化 Bus 消息总线实现

## [1.4.0] - 2026-02-15

### 新增
- 任务管理模块（deva.admin_ui.strategy.task_*）
- AI 代码生成对话框
- 错误处理和容错机制（SafeProcessor, AlertConfig）
- 上下文管理器（contexts.py）

### 修复
- 修复 Kimi API 配置问题
- 修复 Admin 模块路由问题

### 变更
- 优化 Admin 界面布局
- 改进定时器异步支持

## [1.3.0] - 2026-01-20

### 新增
- 策略管理增强（StrategyManager, StrategyUnit）
- 数据源管理增强（DataSourceManager）
- 运行时管理（RuntimeUnit）
- 持久化存储（persistence.py）

### 修复
- 修复数据源显示问题
- 修复 Bus 跨进程通信问题

## [1.2.0] - 2025-12-15

### 新增
- Admin UI 配置管理
- 浏览器自动化（browser.py）
- 全文检索增强（search.py）

### 修复
- 修复 Web 视图性能问题
- 修复定时器内存泄漏

## [1.1.0] - 2025-11-01

### 新增
- LLM 集成（deva.llm）
- GPT 响应生成
- 文章摘要功能

### 变更
- 优化 Admin 界面样式
- 改进流处理性能

## [1.0.0] - 2025-09-01

### 新增
- 完整的流处理核心（Stream, Operators）
- 消息总线（Bus, Topic）
- 定时器和调度器（timer, scheduler）
- 持久化存储（DBStream, Namespace）
- Web 可视化（PageServer, WebView）
- Admin 管理面板

### 变更
- 从实验性项目转为稳定版本
- 完整的 API 文档

### 移除
- 废弃的旧 API

## [0.3.0] - 2025-06-01

### 新增
- 基础流处理功能
- HTTP 客户端
- 文件监控

## [0.2.0] - 2025-03-01

### 新增
- 原型实现
- 基础 Stream 类
- 简单的算子

---

## 版本说明

### 语义化版本

Deva 遵循语义化版本规范：

- **主版本号（MAJOR）**：不兼容的 API 变更
- **次版本号（MINOR）**：向后兼容的功能新增
- **修订号（PATCH）**：向后兼容的问题修正

### 预发布版本

- **Alpha**：内部测试，功能不完整
- **Beta**：公开测试，功能基本完整
- **RC**：发布候选，除非发现严重问题否则不改变

### 支持政策

- **v1.x**：当前稳定版本，持续维护
- **v0.x**：历史版本，不再维护

---

## 迁移指南

### 从 v1.3 升级到 v1.4

1. **任务管理 API 变更**

```python
# 旧代码
from deva.admin import TaskManager

# 新代码
from deva.admin_ui.strategy import TaskManager, TaskUnit
```

2. **日志系统增强**

```python
# 新增导入
from deva.admin_ui.strategy.logging_context import log_strategy_event

# 使用增强的日志
log_strategy_event("INFO", "策略启动", strategy_unit=my_strategy)
```

### 从 v1.0 升级到 v1.1

1. **LLM 配置**

```python
# 新增 LLM 配置
from deva import NB

llm_config = NB('llm_config')
llm_config['kimi'] = {
    'api_key': 'your-key',
    'model': 'moonshot-v1-8k'
}
```

---

[未发布]: https://github.com/sostc/deva/compare/v1.4.1...HEAD
[1.4.1]: https://github.com/sostc/deva/compare/v1.4.0...v1.4.1
[1.4.0]: https://github.com/sostc/deva/compare/v1.3.0...v1.4.0
[1.3.0]: https://github.com/sostc/deva/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/sostc/deva/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/sostc/deva/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/sostc/deva/compare/v0.3.0...v1.0.0
[0.3.0]: https://github.com/sostc/deva/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/sostc/deva/tree/v0.2.0
