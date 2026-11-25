# realtime_tick_5s（id=e626eecd0b86）核查与修复

- 核查：2026-10-21 13:44（A 股盘中）
- 修复与验证：2026-10-21 13:50 – 14:27
- 最终状态：**已修复并验证通过，数据源正在稳定产出真实行情**

---

## 一、核查结论（13:44）

**异常。数据源自昨晚 21:08 停止后就没再被拉起，整天一条都没跑。**

| 字段 | 值 |
|---|---|
| status | `stopped` |
| run_count / total_emitted | **0 / 0** |
| last_data_ts | **0（从未产出）** |
| error_count | 229，`last_error='fetch_data 返回 None'` @ 10-20 16:05 |
| last_skip_ts | 2026-10-20 21:08:43（非 A 股交易时段 closed） |
| 运行时接口 | `total=5 / running=0 / stopped=5 / error=4` |

今天 9019 行日志里，`DataSourceEntry` 相关 **0 行**。

---

## 二、四个根因（按发现顺序）

### 1. 短重启把「组件状态恢复」一起跳过了（核心）

`WakeOrchestrator.wake()` 原写法：

```python
if sleep_hours < 1.0 and last_active is not None and has_jin10_cache:
    return {"action": "skipped", ...}     # ← _recover_components() 在这之后
```

昨晚 23:47 停服 → 23:50 重启（只停 3 分钟，休眠 0.08h）→ 直接 return
→ 5 个数据源一个都没拉起，而 NB 里它们的 `was_running` 全是 True。

**「要不要补历史数据」和「上次在跑的东西要不要重新拉起来」是两件事**，共用一个阈值就会出这种事故。

### 2. 批量设计根本跑不完

- 候选宇宙按板块**硬枚举**约 5 万个代码（北交所一项 3 万个，实际挂牌 <300 只），97% 打空号；
- 800 个/批 × 63 批 **串行** await，而执行层给整轮只有 30s（`future.result(timeout=30)`）→ 必超时。

### 3. `_worker_loop` 把失败载荷当数据 emit（假绿）

只看 `data is not None`，于是 `{"success": False, "error": "TimeoutError..."}` 被当正常产出：
`total_emitted` 涨、`last_data_ts` 刷新、页面显示「刚刚有数据」。

### 4. 实现内嵌在配置里

400 行代码躺在 NB 的 `func_code` 字段（以及 YAML），不能 review、不能被守卫覆盖。

---

## 三、修复清单

| # | 文件 | 改动 |
|---|---|---|
| 1 | `deva/naja/application/wake_orchestrator.py` | `_recover_components()` 提到 skip 判断之前，无条件执行；休眠时长只决定补不补数据 |
| 2 | `deva/naja/datasource/entry.py` | `_worker_loop` 补上 `{"success": False}` / `None` 的失败语义（不 emit、不刷新 `last_data_ts`、不覆盖 `latest_data`） |
| 3 | `deva/naja/datasource/realtime_tick.py`（新建） | 唯一实现：并发抓取（Semaphore 12）+ 有效宇宙自收敛 + 单请求 10s / 整轮 25s 预算 + 三态语义 |
| 4 | `deva/config/datasources/realtime_tick_5s.yaml` | 400 行 → 27 行转发薄壳 |
| 5 | NB `func_code` | 同步为转发薄壳（12238 → 912 字符） |
| 6 | `scripts/verify/verify_wake_restore_not_skipped.py`（新建） | 钉「短休眠也必须恢复」 |
| 7 | `scripts/verify/verify_realtime_tick_source.py`（新建） | 钉三态语义 / 并发 / 宇宙收敛 / 过滤 / 交易时段判据 / session 复用 |

---

## 四、过程中踩到的坑（都是会再踩的）

1. **只改 NB 没用**：服务启动时从 `deva/config/datasources/*.yaml` 加载并**写回 NB**，
   连续两次把我的改动打回旧版。**要改就改 YAML。**
2. **只 kill 主进程不够**：`start_tray.py` 是独立进程、持有 NB 条目副本，照样写回旧值。
   两个都要 kill。SIGTERM 常常不响应（等了 2 分钟），直接 `-9`。
3. **`market_phase` 没有 `"trading"` 这个值**：合法值只有 `morning/afternoon/lunch/closed`。
   我第一版写成 `phase == "trading"` → 下午盘（afternoon）天天被判成非交易时段 skip。
   正确判据是 `is_trading()` / `TRADING_PHASES`。
4. **aiohttp session 绑 event loop**：换 loop 不重建 → 首轮抓到 9722 条，之后每轮全空
   （全部请求异常被 `except: return {}` 吞成「这批空」）。
5. 守卫第一版没 patch `wake_sync_manager`，一跑就注册 6 个真实组件 + 起 Playwright 抓金十。
   **凡是碰到输出口的依赖，守卫里一律换成替身。**

---

## 五、验证结果（14:26 实查）

| 指标 | 修复前 | 修复后 |
|---|---|---|
| status | stopped | **running** |
| running / stopped（全部数据源） | 0 / 5 | **5 / 0** |
| total_emitted | 0 | **165,209**（持续增长） |
| last_data_ts | 0（从未） | **14:26:26**（实时） |
| 每轮代码量 | ~50,000（97% 空号） | **5,659**（自收敛后） |

抓取日志样例（真实行情）：

```
[RealtimeTick] cached 模式：候选 5659 → 有数据 5659 → 过滤后 …
  {'code': 'sh600000', 'name': '浦发银行', 'now': 9.65, 'p_change': -0.01127}
  {'code': 'sh600004', 'name': '白云机场', 'now': 7.75, 'p_change': -0.005135}
  {'code': 'sh600006', 'name': '东风股份', 'now': 5.19, 'p_change':  0.003868}
```

守卫：`verify_wake_restore_not_skipped` ✅（注入 1/1）、
`verify_realtime_tick_source` ✅（注入 3/3）。

---

## 六、收尾（14:30 – 14:50，用户确认后执行）

### 1. 降频：interval 5s → 15s

`deva/config/datasources/realtime_tick_5s.yaml` 的 **两处** `interval_seconds`
（`metadata.` 与 `parameters.`）都改成 `15.0`，description 同步改为「盘中实时行情(15秒)」。

依据（14:32 实测）：轮周期 6.0s、每轮打 5659 个真实代码 ≈ **940 req/s**，
对 `hq.sinajs.cn` 过于激进；一轮实际耗时只有 1~2s，放到 15s 后请求压力降为 1/3。

### 2. 清理

项目根目录那个空 `nb.sqlite`（+ `-shm`/`-wal`）已移到 `/tmp/nb-sqlite-removed-20261021/`（可逆）。

### 3. 重启：14:55:31 执行（用户要求立即执行）

原本挂在 15:05 收盘后，用户要求提前，于是把定时任务撤销后手动执行：
停主进程（SIGTERM 2 秒干净退出）+ 停 tray → 确认进程消失、8080 端口释放 →
`launchctl kickstart` → 等 115 秒 → 验证。

| 验证项 | 结果 |
|---|---|
| 5 个数据源 | **running 5 / stopped 0** |
| 条目 interval | **15.0**（YAML 已生效） |
| 实测轮周期 | **18.0s**（15s 间隔 + 一轮约 3s） |
| emit | 1,486,857 → 1,525,730（持续增长） |
| error_count | **384 → 384，不涨** |
| 收盘切换 | 最后一轮数据 **14:59:48** → **15:00:17** 转 skip「非 A 股交易时段（当前 closed）」 |

最后一行是本次修复的关键反证：下午盘被正确识别为盘中（不再像 `== "trading"` 那版被误判收盘），
收盘后走 skip 分支而**不是**错误分支（`error_count` 没动）。

### 4. 清单探针已生效

`fetch_data` 挂 `@probe(KIND_DATASOURCE, "ds:realtime_tick_5s", ...)` 后，
首页数据源卡能统计到它（否则 `verify_fleet_registry_completeness` 会红）。

### 4. 稳定态证据（14:32）

- `run_count=100`，`total_emitted=476,185`，`last_data_ts=14:32:20`（与取样时刻差 5s）
- `last_error_ts=14:23:20` 之后连续 9 分钟零错误；`error_count=384` 是历史累计（修复前 229 + session bug 期间）
- `naja_market_data_bus` 仅 5,762 行 → 按代码**覆盖写**而非追加，数据量不会失控，NB 稳定 64MB

---

## 七、连带的两个「新增文件没守规矩」问题（全量守卫抓到，已修）

| 守卫 | 违约 | 修法 |
|---|---|---|
| `verify_fleet_registry_completeness` | 新取数模块 `realtime_tick.py` 没登记，首页清单永远看不到它 | `fetch_data` 挂 `@probe(KIND_DATASOURCE, "ds:realtime_tick_5s", "盘中实时行情（新浪全 A 股）", cadence="15s")` |
| `verify_guard_db_isolation` | 新守卫 `verify_realtime_tick_source.py` 碰 NB 却没隔离 | 顶部 `from guard_sandbox import isolate_guard_db` + `isolate_guard_db()` |

顺带把假 `deva` 替身补成**同构**的（含 `deva.naja.infra.observability.fleet_registry`），
否则模块顶层 import 探针会直接 `ModuleNotFoundError`，守卫还没开始测就死。

### 顺手修掉一个「假红」守卫

`verify_guard_db_isolation` 第③项原来比对整个 `accounts` 的 md5。但 Naja 服务在跑时
会自己刷新账户现金/市值，指纹在两次快照之间就漂了 → 盘中随机报「生产库被污染」，
而现场证据是 `新增账户 []`（根本没多账户）。

**假红比没守卫更危险**（真红时没人信）。判据改为**账户 key 集合**：
- 真污染（T 守卫写进测试账户）→ 集合变 → 仍然红（负向注入 1/1 抓到）
- 服务刷新现金 → 指纹变但集合不变 → 打印「数值漂移，不是守卫污染」，不误报

---

## 八、其余数据源

5 个数据源全部 running。`下载目录监控`（Broken pipe，2026-04）、
`OpenRouter`（Failed to fetch，10-20）是各自的老问题，与本次无关。
