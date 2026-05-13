# MEMORY.md - Long-Term Memory

> Your curated memories. Distill from daily notes. Remove when outdated.

---

## About User

### Key Context
- 用户使用 Naja 系统进行量化交易/策略运行
- 系统已从 deva 框架中逐步独立，当前版本 v1.7.0
- 用户偏好直接沟通，不需要废话

### Preferences Learned
- **发送图片**: 用户希望直接通过 iMessage 发送图片
- **iMessage 手机号**: +8618626880688（中国号码，86是国家码）
- **沟通风格**: 直接说重点，像专家顾问
- **高效时段**: 晚上
- **工作模式**: 异步沟通

### Important Dates
- 2026-03-10: 项目启动（ONBOARDING 完成）
- 2026-03-14: 记忆系统 MVP 完成
- 2026-03-17: v1.6.0 发布（Bandit/Signal/策略大幅增强）
- 2026-03-18: 智能选股策略 v2.0 完成
- 2026-04-20: SR() 收口改造 Phase 1-3 完成
- 2026-05-07: Agent 化演进（MarketCopilot、NajaAgent、API Catalog）
- 2026-05-09: v1.7.0 发布（后台服务、macOS 托盘）

---

## Lessons Learned

### 2026-03 - 记忆系统设计
- 记忆系统 MVP 已完成，包含注意力评分、主题聚类、漂移检测
- River ADWIN 用于漂移检测效果良好
- 短期记忆 1000 事件 + 主题库 50 个主题的配置合理

### 2026-03 - SR() 收口改造
- 渐进式迁移策略有效：不立即删除旧代码，保持向后兼容
- AppContainer 作为组合根的模式运行良好
- EventSubscriberRegistrar 统一管理事件订阅是正确方向
- decision/events 层可以做到完全不含 SR() 调用

### 2026-04 - 架构演进
- AdaptiveManas 类已不存在，Manas 层走了不同的演进路径
- UnifiedManas 设计方案未被采纳，ManasEngine 仍独立运行
- application 层（Agent 化）是正确的架构方向

---

## Ongoing Context

### Active Projects
- Naja 量化交易系统 v1.7.0 稳定运行
- SR() 收口改造 Phase 3+ 待完成（集成测试、bandit/radar 改造）
- Skills 体系持续扩展

### Key Decisions Made
- 采用 AppContainer 组合根模式管理依赖
- SR() 作为后备机制保留，新代码优先使用显式依赖注入
- 后台服务模式 + macOS 托盘作为主要运行方式
- Agent 化方向：MarketCopilot + NajaAgent + API Catalog

### Things to Remember
- `memory/core.py` 路径已不存在，记忆系统已被重构
- 旧路径 `/Users/spark/pycharmproject/deva/` 已不适用
- 流动性救援数据源还有 3 项待实现（Level2、VIX、媒体情绪）

---

## Relationships & People

### 老板
- 项目负责人，北京时区
- 关注量化交易系统的稳定性和实用性
- 偏好晚上工作，异步沟通

---

*Review and update periodically. Daily notes are raw; this is curated.*
