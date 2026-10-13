# 性能问题排行榜 诊断评估报告

> 日期：2026-10-14
> 输入：性能监控中心「性能问题排行榜」（7 项，TOP1 = `naja_narrative_tracker_state.write` 788.1ms 平均 / 8448.2ms 最大 / 极重）
> 结论性质：**评估报告，未改任何代码。** 所有数字均为本机实测。

---

## 一、TL;DR

1. **榜单 TOP1「存储写入 788ms」在本机无法复现。** 存储层单次写入实测为 **1.19ms 平均 / 13ms 最大**；换 WAL 后 **0.12ms**。7 个假设（I/O、锁争用、大表阻塞、payload 体积、深栈、GIL 饱和、并发）**全部被实测否掉**。
2. **排行榜的「极重」标签口径偏松**：`max >= 1000ms` 即判 SEVERE，最近 100 次里**一次尖峰**就定性；且同级别内**不排序**，所以 #4/#5/#6 的先后没有意义。
3. **但顺带确证了 3 个真实问题**（有数据、有代码位置、可立即行动）：
   - `deva_bus_clients` 累积 **8806 条僵尸注册记录**（其中 7984 条来自本机），清理逻辑因**没有调用方**而实际从未执行；
   - `quant_snapshot_5min_window` **644MB / 20929 行**，占数据库 **78%**，清理脚本是 `input()` 交互式、从不自动跑；
   - 数据库**未启用 WAL**（实测写入差 **10 倍**），且 `journal_mode=DELETE` 下读写互斥是并发场景的**放大器**。
4. **TOP2~6 全是热点策略/计算组件**（`hotspot_system` 169ms、`strategy_manager` 156ms 等）——对量化计算链路而言这个量级**不一定是 bug**，需要先分清「计算本来就贵」还是「重复计算」。

**一句话**：**不要照着这份榜单去优化**。TOP1 大概率是埋点/环境噪声，真正该修的是第 3 条里的存储膨胀与清理死代码。

---

## 二、先说榜单口径：三个会误导判断的地方

`deva/naja/infra/observability/performance_monitor.py`

| 位置 | 行为 | 后果 |
|---|---|---|
| `get_severity()` L151-162 | `max >= severe(1000)` → SEVERE；`max >= critical(500)` → CRITICAL；**否则**才看 `avg >= warning(100)` | **一次尖峰 = 极重**。榜单显示 avg/max，但定性只看 max |
| `generate_performance_reports()` L434-441 | 仅按 severity 排序，同级**保持 dict 插入顺序** | `#4/#5/#6` 的顺序是注册顺序，**不是耗时排名** |
| `PerformanceMetrics.execution_times` L51 | `deque(maxlen=100)` | 只反映**最近 100 次**调用；低频组件（如 3 秒节流一次的 tracker）的窗口可能横跨数分钟的异常时段 |

**推论**：`naja_narrative_tracker_state` 由 `_maybe_save_state()` 以 **3 秒节流**写入（`tracker.py:288`），100 个样本 ≈ **5 分钟**。如果这 5 分钟里系统恰好经历休眠 / swap / 备份 / CPU 满载，avg 会被整段拉高，而 max 会记录到挂起时长。

> ⚠️ **8.4 秒的 max 量级，最像进程被 macOS 挂起（App Nap / 睡眠 / swap），而不是磁盘慢。** 挂起时 wall-clock 照走，代码却一行没执行。这条可用「报告时间戳是否集中」来验证。

---

## 三、假设验证矩阵（每一条都做了实测）

测试对象：`~/.deva/nb.sqlite` 的**完整副本**（824.5MB），避免污染生产库。

| # | 假设 | 实验 | 结果 | 判定 |
|---|---|---|---|---|
| H1 | 单行 I/O 慢 | 300 次单行 REPLACE+commit（现状 DELETE） | avg **1.19ms** / p95 5.17 / max 13.38 | ✗ 否 |
| H2 | 多连接写锁争用 | 2 线程并发写不同表，各 150 次 | avg **0.08 / 0.34ms**，max 25ms | ✗ 否 |
| H3 | 大表全表扫描阻塞写 | 649MB 表 `COUNT(*)` × 20 与写入并发 | 写入 avg **0.09ms** / max 0.61 | ✗ 否 |
| H4 | payload 过大导致序列化慢 | 直读 `narrative_states` 真实体积 | **14,095 B**（表内仅 2 行） | ✗ 否 |
| H5 | `traceback.extract_stack()` 深栈开销 | 分别测 5 / 50 / 200 层栈 | **0.012 / 0.065 / 0.242 ms** | ✗ 否 |
| H6 | GIL 被 C 级长任务独占 | 15.4MB `json.dumps` 跑满 3 秒，同时写库 | 写入 avg **0.03ms** / max 0.59 | ✗ 否 |
| H7 | `journal_mode=DELETE` 是放大器 | 同表 DELETE vs WAL | **1.19ms → 0.12ms（10×）** | ✓ **是** |

**H5/H6 说明**：`sqlitedict.SqliteMultithread.execute()`（`sqlitedict.py:564-575`）**每次写入都调用一次 `traceback.extract_stack()`**——这是个真实但**不致命**的浪费，实测不足 0.25ms。

**存储写入链路（供对照）**
```
NB(table)[key]=value
  └─ DBStream.__setitem__        store.py:340
      └─ upsert()                store.py:266
          ├─ SqliteDict.update() → encode(dill) + executemany → SqliteMultithread.execute (入队,非阻塞)
          ├─ commit(blocking=False)   ← WRITE_COMMIT_BLOCKING=False, 已是非阻塞
          ├─ _mark_time_index_dirty()
          └─ _check_size_limit()  → `if not self.maxsize: return`  ← 默认 None，直接返回
```

---

## 四、确证的真实问题（按建议优先级）

### P1 · `deva_bus_clients` 累积 8806 条僵尸记录 —— 清理是死代码

**证据**

```
rows[deva_bus_clients] = 8806        (1.5 MB, 均值 180 B/行)
按主机名分布：
   MBA.local        7984   ← 本机，7984 个不同 PID
   192.168.0.100     378
   192.168.0.174     191
   ...（其余为各网段 IP）
```

**链路**（`deva/core/bus.py`）

```python
client_key = f"{socket.gethostname()}:{os.getpid()}"   # L193  → 每次进程启动都是新 key
self.client_ttl_seconds = 30                            # L191
def _heartbeat_loop():                                  # L238  只写，从不清理
    ... self.clients_table[self.client_key] = payload   # L234
def get_clients(...):                                   # L270
    self._remove_stale_bus_clients(...)                 # L271  ← 唯一的清理触发点
```

- 清理**唯一**通过 `get_clients()` 触发；
- 而 `get_clients()` 在 **`deva/naja/` 全目录 0 个调用方**（仅 `deva/admin/main_ui.py` 的 Bus 面板调用）；
- → **naja 常驻运行时，TTL 清理永不执行**，进程一次次启停就把表撑到 8806 行。

**放大效应**：`_remove_stale_bus_clients()` 一进来就 `list(self.clients_table.items())` 做**全表反序列化**（`bus.py:254`），若触发则逐条 `del` → `DBStream.__delitem__` **每条一次阻塞 commit**（`store.py:345-350`）。这是一次调用里最重的路径。

**健壮性缺陷（顺带发现）**：`SqliteDict.iteritems()` 是**生成器**，`decode()` 对非 pickle 行会抛异常且不降级（`sqlitedict.py:114-119`，实测踩到）→ **表里只要有 1 行异构数据，全表遍历就中断**，依赖它的清理逻辑直接失效。

**建议**（待确认）：一次性清理 + 补一个定期清理调用方 + `iteritems` 加容错。
> 一次性清理属于**删除操作**，需你确认后我再执行，并先做备份。

---

### P2 · `quant_snapshot_5min_window` 644MB，占库 78%，只增不减

```
file_size            = 824.5 MB
page_size            = 4096       journal_mode = delete   ← 非 WAL
quant_snapshot_5min_window   20929 rows   643.99 MB   avg 31.5 KB/row   ← 5 分钟一条窗口快照
naja_ds_latest_data            200 rows    96.51 MB   avg 494.1 KB/row  ← 单行近 0.5MB
naja_loop_audit              35771 rows    13.94 MB   avg   0.4 KB/row
naja_strategy_runtime_state     25 rows     9.35 MB   avg 382.8 KB/row
narrative_tracker_state          2 rows    0.014 MB
```

- 写入点：`market_hotspot/data/realtime_fetcher.py:1360` `NB("quant_snapshot_5min_window", key_mode="time")` + `append(records)`，**无 maxsize、无轮转**；
- 清理脚本 `naja/scripts/cleanup_snapshots.py` 用 `input('确认删除…')` → **交互式，不可能被定时任务执行**；
- 824MB 文件从未 VACUUM，删除只产生空闲页，文件不会自动缩小。

**建议**：给该表加**写入侧保留策略**（按时间键轮转，例如保留 N 天），而不是靠人工脚本；清理后执行一次 `VACUUM` 回收空间。

---

### P3 · 数据库未启用 WAL

- `sqlitedict.py:127` 默认 `journal_mode="DELETE"`，`DBStream` 未覆写；
- 实测同表写入：**DELETE 1.19ms → WAL 0.12ms（快 10 倍）**；
- 更重要的是 `DELETE` 模式下**写者提交需要等读者释放共享锁**，在「8806 行全表读 + 高频心跳写」这种组合下会放大抖动——这**可能**是 `deva_bus_clients.write` 267ms/2807ms 的成因（写请求与该表线程队列里的全表扫描串行），但**本次未能复现**，列为待验证。

---

### P4 · TOP2~6：热点策略链路（需区分「本该贵」还是「重复算」）

| 组件 | avg | max | 代码位置 |
|---|---|---|---|
| `hotspot_system` | 169.0ms | 2097.3ms | `market_hotspot_system.py:961`（`latency` 覆盖 **6 个 step** 全链路） |
| `hotspot_strategy_manager` | 156.6ms | 3352.8ms | `strategies/strategy_manager.py:427`（含其下所有策略） |
| `hotspot_strategy_us_momentum_surge_tracker` | 72.7ms | 1687.5ms | `strategy_manager.py:401`（单策略 `process()`） |
| `hotspot_strategy_river_early_trend` | 41.5ms | 997.5ms | 同上 |

**注意嵌套关系**：`strategy_manager`(156ms) ⊃ 各单策略(72.7/41.5ms)；`hotspot_system`(169ms) ⊃ `strategy_manager`。**它们是同一条链路上的不同切面，不是 4 个独立问题**——修一个可能同时消掉四个。

**判定要点**：约 70~170ms 对「N 只标的 × 多策略 × 每 tick」的量化计算**未必异常**。真正要查的是：**同一 tick 内是否被重复计算**（`hotspot_datasource_example.py` / `hotspot_mixin.py` 有多次进入 `hotspot_system` 的路径，值得确认是否重复 `process_snapshot`）。

---

## 五、建议动作（按「先便宜、后昂贵」排序）

**第一梯队（低风险，收益明确）**
1. 给 `deva_bus_clients` 补定期清理调用方（在 `_heartbeat_loop` 内顺带清理，5 分钟一次），并一次性清掉现有 8806 条。**顺带修 `iteritems` 的容错**，否则清理仍会被一行坏数据卡死。
2. 给 `quant_snapshot_5min_window` 加写入侧保留策略 + 跑一次 `VACUUM`。
3. 开启 `journal_mode=WAL`（`SqliteDict` 默认值或 `DBStream` 显式传入）。

**第二梯队（需先说清口径）**
4. 修正排行榜口径：`get_severity` 增加「需连续 N 次超阈」或同时看 p95；同级内**按 avg 排序**。否则榜单会持续把噪声排到 TOP1。
5. 给存储埋点增加**排队时间 vs 执行时间**的拆分（读 `SqliteMultithread.reqs.qsize()`），才能区分「自己慢」和「排队慢」。

**不要做**
- ❌ 不要因为 TOP1 就去优化 `narrative_tracker_state` 的写入路径：实测 1.19ms，且 payload 只有 14KB，没有优化空间。

---

## 六、如果一定要定位 TOP1 的 788ms

静态分析已排除全部常规成因，**只剩运行时采样一条路**：

```bash
# 在真实运行的进程上采样（不要在 agent shell 里手动 start 服务）
py-spy dump   --pid <naja_pid>            # 看一眼卡在哪
py-spy top    --pid <naja_pid>            # 实时热点
py-spy record --pid <naja_pid> -o /tmp/naja.svg -d 60   # 60 秒火焰图
```

同时建议核对报告中该条目的**时间戳分布**：若集中在某一段，优先怀疑系统休眠/挂起而非代码。

---

## 附：实测原始数据

```
### 单行写延迟（同库 824MB，表 naja_narrative_tracker_state）
DELETE-journal(现状)   avg=   1.19ms p50= 0.64 p95=  5.17 max=  13.38
WAL                    avg=   0.12ms p50= 0.06 p95=  0.22 max=   4.73

### 两连接并发写（现状 DELETE）
tracker_state   n= 150 avg= 0.08ms p95= 0.20 max=  1.09
bus_clients     n= 150 avg= 0.34ms p95= 0.43 max= 25.49

### 大表 COUNT(*) 全表扫描 与 小表写入 并发
大表 COUNT(*) 读      n=  20 avg= 1.15ms p95=22.10 max=22.10
小表写(受大表读影响)   n= 150 avg= 0.09ms p95= 0.29 max= 0.61

### GIL 饱和（主线程 3 秒 json.dumps 15.4MB）下的小表写
tracker_state write   n= 150 avg= 0.03ms p95= 0.04 max= 0.59

### traceback.extract_stack 成本
depth=   5 -> 0.012 ms/次
depth=  50 -> 0.065 ms/次
depth= 200 -> 0.242 ms/次

### 真实库表规模
rows[quant_snapshot_5min_window] = 20929   (643.99 MB, 31.5 KB/row)
rows[naja_ds_latest_data]        =   200   ( 96.51 MB, 494.1 KB/row)
rows[naja_loop_audit]            = 35771   ( 13.94 MB)
rows[naja_strategy_runtime_state]=    25   (  9.35 MB)
rows[deva_bus_clients]           =  8806   (  1.51 MB)
rows[naja_narrative_tracker_state]=    2   (  0.014 MB)
```
