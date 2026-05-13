# SESSION-STATE.md - Active Working Memory

**Last Updated:** 2026-05-14
**Current Task:** 系统文档整理与架构演进

---

## 项目状态

**系统名称**: Naja 量化交易系统
**版本**: v1.7.0 (2026-05-09)
**状态**: ✅ 稳定运行

---

## 最新里程碑

### v1.7.0 (2026-05-09)
- ✅ 后台服务模式 (`naja -s start/stop/reload/restart/status`)
- ✅ macOS 菜单栏托盘（实时新闻和热点板块）
- ✅ 命令行入口 `bin/naja`
- ✅ 金十重要新闻 JSON API

### v1.6.0 (2026-03-17)
- ✅ Bandit 模块大幅增强（MarketObserver、AdaptiveCycle、SignalListener、VirtualPortfolio）
- ✅ 信号处理增强（多源聚合、过滤转换）
- ✅ 策略系统增强（声明式策略、River 策略增强）
- ✅ LLM 控制器升级（对话历史、多模型）
- ✅ 字典模块（同花顺板块数据）

### SR() 收口改造 (2026-04-20)
- ✅ AppContainer 增强，组件装配逻辑
- ✅ EventSubscriberRegistrar 事件订阅管理
- ✅ AttentionOS/TradingCenter 构造注入
- ✅ 内核层（QueryState/ManasEngine/Bandit）显式依赖注入
- ✅ decision/events 已纯净（无 SR() 调用）

### Agent 化演进 (2026-05-07)
- ✅ MarketCopilot（市场值班官）
- ✅ NajaAgent（对话/技能门面）
- ✅ API Catalog（52 个端点目录）
- ✅ 通知适配器（DingTalk/iMessage）
- ✅ Skills 体系建立

---

## 核心架构

```
application/     ← 应用层（Agent、MarketCopilot、API Catalog）
    ↓
attention/       ← 注意力系统（OS、Kernel、Values、Manas）
cognition/       ← 认知系统（Bridge、Engine、Narrative）
radar/           ← 雷达系统（Engine、全球扫描、新闻获取）
    ↓
strategy/        ← 策略系统
signal/          ← 信号系统（调度、处理、推送）
bandit/          ← Bandit 交易系统
risk/            ← 风险管理
    ↓
web_ui/          ← Web UI
infra/           ← 基础设施（daemon、tray）
```

---

## 待完善功能

- [ ] SR() 收口 Phase 3+：系统集成测试
- [ ] bandit/radar 目录的 SR() 改造
- [ ] 流动性救援剩余数据源（Level2、VIX、媒体情绪）
- [ ] 统一 Manas 设计（当前 ManasEngine 仍独立运行）

---

## 使用方式

1. 启动: `naja -s start`（后台模式）或 `python -m deva.naja`（前台模式）
2. 访问: `http://localhost:8080`
3. macOS 托盘: `python deva/naja/scripts/start_tray.py`
