# Naja V2 Refactor Plan

> **文档状态: 部分完成 (PARTIALLY DONE)**
> 验证日期: 2026-05-14
>
> "下一阶段建议"逐项检查:
> 1. SR() 限定在组合根: **未完成** -- SR() 仍大量散布在领域模块中 (cognition 12文件24处, attention 9文件12处, bandit 10文件28处)，仅在 application/container.py 集中使用
> 2. 拆分 TradingCenter: **未完成** -- 无独立 TradingCenter 文件，仍位于 attention/orchestration/trading_center.py，decision/application/ 子目录不存在
> 3. 收敛 attention + market_hotspot: **未完成** -- attention/ 和 market_hotspot/ 仍为独立目录，未统一为决策域
> 4. 事件总线显式 mapping: **已实施** -- application/event_registrar.py 已建立 EventSubscriberRegistrar，统一管理事件订阅装配，使用显式 event class -> handler mapping
> 5. task/dictionary/bandit manager 迁移: **部分完成** -- DataSourceManager 和 StrategyManager 已迁移到 base_manager 骨架，但 TaskManager、DictionaryManager、BanditPortfolioManager 均未迁移

本轮重构先把最乱的"运行时装配层"抽出来，再统一 manager 骨架，目标是不破坏现有系统但让后续迁移有主干。

## 已落地

- 新增 `deva/naja/application/`
- 引入 `AppRuntimeConfig` 统一承接 CLI / Web 启动配置
- 引入 `AppContainer` 作为组合根，集中处理 boot、状态恢复、handler 构建、模式初始化
- `web_ui/server.py` 与 `deva/naja/__main__.py` 已切到 application 层
- `web_ui/routes.py` 拆成 `page_routes + api_routes`
- 新增 `infra/management/base_manager.py`
- `DataSourceManager`、`StrategyManager` 已切到共享 singleton/lazy-init/catalog 骨架

## 下一阶段建议

1. 把 `register.SR()` 限定在组合根、兼容层、UI 层使用
2. 拆分 `TradingCenter`，把融合规则迁到 `decision/application`
3. 收敛 `attention + market_hotspot` 为统一决策域
4. 事件总线改成显式 event class -> bus mapping，去掉自动猜测
5. 把 task/dictionary/bandit manager 继续迁到统一 manager 骨架

## 设计原则

- 运行时编排归 `application`
- 领域能力留在原模块
- 兼容优先，先换骨架再换器官
- 每步迁移都保留旧入口，避免一次性爆炸
