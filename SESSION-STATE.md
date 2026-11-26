# SESSION-STATE.md - Active Working Memory

**Last Updated:** 2026-11-26
**Current Task:** 结构性行情重定价收口（分类口径 / 自身分位）→ SR() 收口收尾

> 本文件只写「现在真实的状态」。过期的里程碑不留在正文里 —— 留在 `CHANGELOG.md`。
> 每条未完成项都必须带**可验证的现状**（文件 / 函数 / 实测数字），否则下一个人
> 会重新发现一遍同样的问题。

---

## 项目状态

**系统名称**: Naja 量化交易系统
**当前版本**: v1.8.0（代码已远超 tag，见 CHANGELOG 未发布段）
**运行状态**: ✅ 常驻（`python -m deva.naja --port=8080 --host=0.0.0.0` + `scripts/start_tray.py`）
**最近一次实测**（2026-11-26）：热点策略 14 个已挂接、虚拟组合 20 个持仓、
`~/.naja/logs/naja.log` 持续写入、每日复盘 iMessage/DTalk 推送成功。

---

## 自 v1.8.0 以来的关键落地（都已入库）

- **SR() 收口 Phase 3**：`AppContainer` 显式装配，`decision/`、`events/` 已无 SR()；
  `infra/registry` 保留为读状态入口。
- **FleetRegistry**（`infra/observability/fleet_registry.py`）：首页数据源/策略卡片
  改为「登记册 + 探针 + 声明式清单」单一口径，四态（running/stopped/unknown/skipped）
  不许合并；`verify_fleet_registry_completeness.py` 扫 23 个用网络库的模块。
- **真实 PE 重定价**（`structural_growth/`）：`pe_classifier` / `pe_bands` /
  `repricing` / `repricing_service` 四层，PE 走新浪 gb_，财报走 SEC XBRL，
  页面上有重定价卡。
- **基本面层**（`fundamental/`）：季频财报落地仓 + 打分 + 估值分位，
  `verify_fundamental_store.py` / `verify_fundamental_scoring.py` 守着。
- **做T（T-rotation）**：分批建仓 + 大环境闸门，基本面接进「抄底许可」。
- **守望台**：观测面、阈值同源、问询落库、执行腿已接通。
- **geo_risk**：模块已下线删除（`afde9949`）。

---

## 待完善功能

### 1. 结构性行情重定价 —— 还差三块（P1）

- [ ] **分类仍吃年度 4 期**：`repricing_service._classify()` 走
      `structural_growth/financial_data_fetcher`（`_extract_annual`，只有 4 期），
      `pe_classifier.MIN_PERIODS=4 / IDEAL_PERIODS=8` 永远达不到理想样本，
      AMD(174x) / TSLA(306x) 因此被判成周期股。
      **现成材料**：`fundamental/points.py:us_series()` 已产出季度间隔的 TTM 序列（约 20 期）。
- [ ] **自身历史分位没接进重定价**：`pe_bands.py` 只有全池横截面分位（文件头自己
      写明「池子整体高估时测不出」）；`fundamental/valuation.py:build()` 已能算
      `pe_percentile`（富途日线 + TTM EPS，3~5 年），但页面和 API 都没用它。
- [ ] **S0–S4 状态机没有价格输入**：`valuation_state.py` 只看基本面；`entry_window`
      九宫格已实现且已接（`repricing.py:_ENTRY_GRID`），但阶段来自观察池，不是价格驱动。

### 2. SR() 收口 Phase 4 —— bandit / radar

- [ ] `bandit/`：15 处 SR() / 8 个文件；`radar/`：4 处 / 2 个文件。
      **真正的二次实例风险**在 `register.py` 的裸 `Class()` 工厂：
      `adaptive_cycle`、`bandit_runner` 会造出「从未 start()」的第二实例，
      取到哪个取决于 import 顺序（FleetRegistry 已因此改用模块级 getter）。
      启动日志里的 `单例 virtual_portfolio 已注册，将被覆盖` 是同一类症状。

### 3. 流动性救援剩余数据源

- [ ] Level2、VIX、媒体情绪 —— 三个数据源尚未接入。

### 4. 统一 Manas

- [ ] `ManasEngine` 仍独立运行，未与 AttentionOS 合并。

### 5. 系统集成测试

- [ ] 单模块守卫 100+ 条已齐，但「装配后整机跑一轮」的集成测试仍缺。

### 6. 运行期已知问题（有日志证据，未修）

- [ ] **做T 份额守恒被破坏**（2026-11-26 香港 00700 四次）：
      `开始前 2300.00 → 现在 2000/2100/2200`，`bandit/t_rotation.py` 报 ERROR。
- [ ] `LLMReflection` 每几小时撞一次 HTTP 402（配额），无退避/熔断。
- [ ] 启动期 10 分钟内出现 5 次进程重启（14:33–14:43，2026-11-26），原因未查。

---

## 核心架构

```
application/     ← 装配与应用层（AppContainer、Agent、MarketCopilot、API Catalog）
    ↓
attention/       ← 注意力系统（OS、Kernel、Values、Manas）
cognition/       ← 认知系统（Bridge、Engine、Narrative）
radar/           ← 雷达系统（Engine、全球扫描、新闻获取）
structural_growth/ ← 产业研究 S0–S4 + PE 重定价
fundamental/     ← 个股季频财报 + 估值分位（决策数据底座）
    ↓
strategy/        ← 策略系统
signal/          ← 信号系统（调度、处理、推送）
bandit/          ← Bandit 交易系统（做T、虚拟组合、守望台）
risk/            ← 风险管理
    ↓
web_ui/          ← Web UI（页面只读 facade / query service，不深入核心对象）
infra/           ← 基础设施（daemon、tray、registry、observability）
```

分层红线见 `docs/naja/naja_architecture_baseline.md`；SR() 使用策略见
`docs/naja/sr_usage_policy.md`。

---

## 验证方式

```bash
# 全量守卫（严格档，推荐）
env -u PYTHONPATH TMPDIR=$(mktemp -d) \
    /opt/homebrew/opt/python@3.13/bin/python3.13 scripts/verify/run_all_guards.py

# 只看失败
... run_all_guards.py --quiet
```

重启/启动：`bin/naja -s start|stop|restart|status`（后台模式）。
Web：`http://localhost:8080`；托盘：`python deva/naja/scripts/start_tray.py`。
