# Naja / deva 核心性能优化报告

> 生成时间：2026-10-10
> 方法：对 `deva/core/`、领域核心层（decision / attention / cognition / signal / bandit / radar / market_hotspot）、并发与存储层做只读静态分析，关键结论均已回到源码核对行号。
> 状态：**评估报告**。具体修复进展见文末「修复进展」表。

---

## 0. 一句话结论

核心链路的问题不是「算法复杂度失控」，而是**热路径上反复做重活**：每次事件都落库、每条记录都提交事务、每次推送都全量重算、持锁执行下游回调。这类问题单点改动小、收益直接，适合逐条收敛。

---

## 1. 热点地图（按架构层）

| 架构层 | 主要文件 | 热点特征 |
|--------|----------|----------|
| Web UI / SSE 推送 | `web_ui/routes.py`、`market_hotspot/push_center.py` | 每次推送全量重算；同步 handler 阻塞 IOLoop |
| 事件总线 | `events/trading_bus.py`、`events/cognitive_bus.py` | 持锁同步分发所有 handler；锁内落盘 |
| 领域核心 | `decision/`、`attention/kernel/`、`cognition/`、`bandit/` | 每事件落库；O(n²) 遍历；热路径反射/import |
| 存储层 | `core/store.py`、`utils/sqlitedict.py` | 每条写必 commit；len() 全表 COUNT；无界队列 |

---

## 2. P0 热点（优先处理）

### P0-1 · 叙事追踪每条事件都落库
- **位置**：`deva/naja/cognition/narrative/tracker.py:591`
- **代码**：
  ```python
  def ingest_event(self, event):
      ...
      external_results = self._process_external_narratives(event, now_ts, attention)
      value_results = self._process_value_signals(event, now_ts)
      self.save_state()          # ← 每条事件一次全量落库
      return results
  ```
- **问题**：`save_state()`（同文件 `523-546`）内含 `from deva import NB`、全量 `sorted(...)` 与整表写入。任何进入叙事追踪的事件都会触发一次完整 DB 写。
- **影响**：交易时段高频事件的写放大主来源。
- **建议**：脏标记 + 节流（最短间隔或按时间窗）落库；`NB` 句柄在 `__init__` 建一次复用；退出时强制 flush。

### P0-2 · DBStream 每次写都提交事务
- **位置**：`deva/core/store.py:253-276`
- **代码**：
  ```python
  def append(self, value, key=None):
      store_key = time.time() if key is None else key
      self.db.update({store_key: value})
      self.db.commit()          # ← 每条一次事务提交（阻塞等待写入线程确认）
      self._mark_time_index_dirty()
      self._check_size_limit()  # ← 有 maxsize 时 len(self.db) 全表 COUNT
      return store_key
  ```
  `upsert` / `bulk_update` 同构。
- **更正（实施时复核）**：
  - 全项目**没有任何表设置 `maxsize`**，因此 `_check_size_limit()` 在 `if not self.maxsize` 处即返回，「每次 COUNT 全表」当前**不触发**。
  - 底层 `SqliteMultithread` 已设 `PRAGMA synchronous=OFF`，本就未做 fsync，所以 commit 的成本不是磁盘同步，而是 `commit(blocking=True)` 每次的**线程往返**（`select_one('--commit--')` 等写入线程确认）。
- **影响**：写入吞吐被每个写的线程往返 + 事务边界主导，而非 fsync。
- **建议**：写路径改非阻塞提交（`commit(blocking=False)`），顺序性由写入线程 FIFO 队列保证；`persist()`/`close()` 保持阻塞。

### P0-3 · 同步 handler 阻塞 Tornado IOLoop
- **位置**：`deva/naja/web_ui/routes.py:407`（`Jin10ImportantNewsHandler.get`）与 `447-456`
- **代码**：
  ```python
  def get(self):                                  # ← 同步 handler，跑在 IOLoop 线程
      ...
      response = requests.get(                    # ← 阻塞调用，最长 timeout=5s
          "https://www.jin10.com/flash_newest.js",
          headers={...}, timeout=5,
      )
  ```
- **问题**：Tornado 同步 handler 在事件循环线程执行；一次请求即可阻塞全站所有请求最长 5 秒。
- **影响**：托盘菜单/页面点击造成整站卡顿。
- **建议**：改 `async def get` + `AsyncHTTPClient`，或把阻塞逻辑丢进 executor。

### P0-4 · 市场热点 payload 每推送全量重算
- **位置**：`deva/naja/web_ui/routes.py:311-327`（`MarketHotspotStreamHandler`）+ `_market_hotspot_payload()` 定义在 `66-249`
- **问题**：每个 SSE 连接、每次推送都重新执行 `_market_hotspot_payload()`（多次 `sorted()`、逐 symbol `get_stock_name`）。`push_center._push_interval` 字段已定义（`push_center.py:91`）但 `push()`（`118-149`）未用于节流。
- **影响**：多标签页 CPU 成倍；高频热点事件下 JSON 序列化 + 全量重算成瓶颈。
- **建议**：payload 在 `push_center` 侧计算一次并缓存，SSE 仅序列化发送；按 `_push_interval` 做推送合并。

### P0-5 · 事件总线持锁同步分发
- **位置**：`deva/naja/events/trading_bus.py:136-166`
- **问题**：`with self._lock:` 内完成订阅者遍历 + 同步 `sub.callback(event)`（`trading_bus.py:326`），且持久化 `_persist_event` 也在锁内。
- **影响**：任一慢 handler（尤其撞上 P0-2 的 DB 写）阻塞所有发布者；临界区被拉长。
- **建议**：锁内只快照待通知订阅者列表，锁外执行回调；持久化移出锁外。
- **更正（实施时复核）**：`cognitive_bus.py` 的两个通道（dataclass 通道 `248-274`、认知通道 `_publish_cognitive` `412-434`）**本来就是「锁内快照 + 锁外回调」**，无需改动。真正有问题的是 `trading_bus`。

---

## 3. P1 热点

| 项 | 位置 | 问题 | 建议 |
|----|------|------|------|
| P1-1 | `attention/kernel/manas_engine.py:757,770,1491` | 同一轮 `compute()` 调 `portfolio.get_summary()` 3 次 | ✅ 已修：取一次向下传参 |
| P1-2 | `bandit/market_data_bus.py:508,526` | 每次请求新建 `ThreadPoolExecutor` + `aiohttp.ClientSession` | ⚠️ **复核不改**：`ClientSession` 与创建它的 event loop 绑定，而 `_do_fetch_sync` 走 `asyncio.run`（新 loop）、`_trigger_async_fetch` 走 `create_task`（当前 loop），跨 loop 复用会抛 "attached to a different loop"；`ThreadPoolExecutor(max_workers=1)` 仅用于 sync 回退路径、创建开销小。风险 > 收益，**不改** |
| P1-3 | `bandit/market_data_bus.py:416-422` | 逐条 quote 写 DB | ✅ 已修：聚合为单次 `bulk_update`（原为每条一次 `upsert`） |
| P1-4 | `market_hotspot/tracking/history_tracker.py:631-661` | 快照变更检测 O(板块×个股) + 每板块排序 | ✅ 已修：循环提升（实测调用数 4053 → 386） |
| P1-5 | `state/system/wake_sync_handlers.py:218-290,347-357` | `async def` 内跑阻塞 `requests`（最多 100×15s）+ 每条 `sleep(0.5)` | ✅ 已修：`asyncio.to_thread` + `Semaphore(4)` 并发 + 节流 0.5s→0.05s |
| P1-6 | `tasks/manager.py:526+` | 启动恢复同步 `run_once()` 补作业（含网络） | ✅ 已修：收集待补任务后交单个后台 daemon 线程**串行**执行（保序、不阻塞启动） |
| P1-7 | `bandit/optimizer.py:624` | `_get_arm_score` 每个 arm 全量 `sum(pull_count)` → O(n²) | ✅ 已修：预计算 total_pulls 传入 |
| P1-8 | `market_hotspot/data/realtime_fetcher.py`（379/409/456/679/748） | 热路径 `SR('hotspot_system')` 单例查找 | ✅ 已修：新增 `_hotspot_ref()` 缓存引用 |
| P1-9 | `attention/kernel/manas_engine.py:1107,1136,1194` | 每次事件重建字典/常量列表 | ✅ 已修：`_RISK_LEVEL_SCORES` / `_AI_COMPUTE_KEYWORDS_LOWER` 提为模块常量（关键词预 lower，省去每轮 `kw.lower()`）+ 删冗余局部 `import time` |

---

## 4. 内存无界增长（长跑必查）

| 位置 | 结构 | 风险 |
|------|------|------|
| `cognition/narrative/tracker.py` | `_value_signals` 只 append（消费方只用最近 72h） | ✅ 已修：新增 `_prune_value_signals()` + 阈值化摊还调用，并同步重建 `_value_signal_index` |
| `cognition/narrative/tracker.py` | `_graph_edges` 无上限 | ✅ 已修：超 `narrative_graph_max_edges`（默认 20000）时按权重保留最高的半数 |
| `cognition/narrative/tracker.py` | `_recent_hits` 无 maxlen | ✅ 已修：补 `maxlen=50000` 兜底（原本已有按时间窗 `popleft` 裁剪） |
| `radar/engine.py:207-211` | 三个 dict 只增不减 + `_drift_detectors` 惰性建后不清 | ⚠️ **原判断过重**：`_pattern_hits` 每个 key 的 deque 已按时间窗 `popleft`，且三个 dict / `_drift_detectors` 的 key 空间分别被「策略×信号类型」「strategy_id」限定，属有限小集合，不是持续增长项。**不改** |
| `signal/stream.py:41` | `_CACHE_MAX_AGE_SECONDS = 60*60*24*365*10`（10 年） | ⚠️ **原判断过重**：该值只是 TTL，缓存实际由 `max_len=cache_max_size`（默认 100）约束（`Stream.start_cache` → `ExpiringDict(max_len=...)`），不存在按时间累积。**不改** |
| `utils/sqlitedict.py:418` | 每表一个线程 + 无界 `Queue` | ⚠️ **复核不改**：消费线程是专职串行 SQL 线程（`synchronous=OFF`，处理快），正常负载下队列不积压；改有界会把风险从「内存增长」转移到「写入方阻塞」（可能卡 UI 线程），需按真实负载决定，**暂不动** |
| `bandit/signal_listener.py:616-626` | 去重表超限时全量排序重建 | ✅ 已修：`_mark_processed` 改为按插入序（dict 天然有序）裁掉最早若干条，去掉 `sorted` 全量排序；保留条数与旧实现 `sorted(...)[-maxp//2:]` 完全一致（即 `ceil(maxp/2)`） |
| `state/system/system_state.py:203-230` | `record_task_execution` 声称批量写但末尾立即 `_save_unsafe()` | ✅ 已修：改为与 `record_active` 一致的节流（仅在距上次落盘 ≥ `BATCH_WRITE_INTERVAL` 时同步写），其余交给后台批量写线程；`shutdown()` 仍兜底 flush |

---

## 5. 核心框架（`deva/core/`）微优化

| 位置 | 问题 | 建议 |
|------|------|------|
| `core/core.py:720-739` `Stream._emit` | 函数体内 `import time`；每事件 `list(self.downstreams)` 拷贝 + 多次建 list | import 提到模块顶部；结果惰性收集 |
| `core/core.py:1226` `Sink.wrapper_function` | 每事件 `inspect.signature(func)` | `__init__` 预算 `has_params` |
| `core/core.py:1217` `Sink.__init__` | 每次实例化 `inspect.signature(Stream)` | 提为模块常量 |
| `core/bus.py:432-454` | 未带 sender 的 `bus.emit` 全量 `inspect.stack()` | ✅ 已修：改 `sys._getframe` 手工遍历（语义等价，实测 **99.7x** 加速） |
| `core/namespace.py:90-95` | `Namespace.create` 每次重建构造函数 dict + 抢全局 RLock | 提为模块常量；命中走无锁快路径 |
| `core/sources.py:37-83` | 每个 HTTP 请求重建 4 层 Pipe + 4 个闭包 | ✅ 已修：改普通函数顺序调用（**并修活一条此前必然报错的死路径**，见 §7.4） |
| `core/compute/ops.py:351,666` | `combine_latest`/`zip_latest` 每事件 `list.index()` O(n) | ⚠️ **复核不改**：`upstreams` 是构造参数，实际只有 2–5 个，`.index()` 在常数量级小列表上不构成瓶颈；改映射还需处理 `upstreams` 动态变化，收益微、风险> 收益，**不改** |
| `core/compute/ops.py:470-486` `unique` | list 分支 `in/remove/insert(0)` O(n)；dict 分支两次 `str(y)` | ⚠️ **实测后不改**：`hashable=False` 分支改 `deque` 的隔离实测为「变更快 3–112x、但成员查询慢 1.5–2.2x」，端到端在 `maxsize≤10` 时 deque 快 1.3–1.7x、在 `maxsize≥100` 时 list 快 1.2–1.7x，**结果混合且该分支在本仓库实际未被调用** → 不改（详见 §5.1） |

### 5.1 `unique(hashable=False)` 为何最终不改（实测记录）

隔离测量（`maxsize=1000` / `N=1e5`）：

| 操作 | deque | list | 结论 |
|------|-------|------|------|
| 仅「插入 + 淘汰」（`appendleft` vs `insert(0)+del`） | 0.032s | 3.53s | deque 快 **112x** |
| 仅「成员查询」（`in`） | 0.85s | 0.39s | list 快 **2.2x** |

端到端（`N=5e4`，`distinct = maxsize×3`）：

| maxsize | deque / list 耗时比 |
|---------|---------------------|
| 1 | **0.58x**（deque 快） |
| 10 | **0.78x**（deque 快） |
| 100 | 1.66x（list 快） |
| 1000 | 1.17x（list 快） |

即：**小上限（窗口小、成员查询便宜）deque 占优；大上限（成员查询主导）list 占优**。加上该分支在本仓库无任何调用点，属「收益方向不确定」的改动，按「无明确收益就不动」原则**保持原样**。

---

## 6. 已做得好的（改造时可参照）

- `deva/naja/__init__.py` PEP 562 惰性导出（省 ~0.79s import）。
- `application/container.py` `_load_persistent_managers` 4 线程并行加载。
- `state/system/system_state.py:189-201` `record_active` 的批量写入。
- `signal/processor.py:21-25` 正则模块级预编译。

---

## 7. 顺带发现的 bug（已全部修复 ✅）

### 7.1 `StrategySignalEvent` schema 缺字段 —— 影响面最大的一处

| 位置 | 问题 | 状态 |
|------|------|------|
| `events/trading_events.py` `StrategySignalEvent` | 缺 `importance` / `market` 字段，但 `trading_bus.publish_strategy_signal()` 与 **`bus_bridge.py` 的 4 个转换器**都按这两个字段构造事件 → 一调用就 `TypeError` | ✅ 已修 |

**根因**：不是调用方写错，而是事件 schema 少了两个字段——总线的 `_get_event_importance()` / `getattr(event, 'market')` 过滤逻辑早就期望它们存在。因此修法是**在源头补字段**，而不是删调用方参数：

- `StrategySignalEvent` 新增 `importance: float = 0.5` / `market: str = "CN"`，`to_dict()` 同步输出。
- 新增 `__post_init__` 归一化 `direction`：支持 `"buy"` / `"买入"` / `None` / 枚举，转成 `SignalDirection`（原先传字符串会让 `to_dict()`、`is_buy` 直接崩）。
- `current_price` 类型标注修正为 `Optional[float]`（所有生产方都传 `None`）。
- `events/trading_bus.py`：`publish_strategy_signal` 用 `SignalDirection.from_str` 解析方向；`publish_trade_decision` 用 `DecisionResult.from_str`（容错，不再因 `"APPROVED"` 大小写抛 `ValueError`）。

**修复收益**：复活的不只是那个「死代码」快捷方法，而是**整条认知 → 交易桥接**（`bus_bridge` 的叙事/时机/共振/风险 4 个转换器），并让总线的 `min_importance` / `markets` 过滤对策略信号真正生效。

**验证**：`scripts/verify/verify_trading_event_schema.py` —— 6 组断言（构造、方向归一化、默认值、快捷方法、**重要性/市场过滤真的生效**、决策事件）全通过。

### 7.2 其余零散 bug

| 位置 | 问题 | 状态 |
|------|------|------|
| `bandit/signal_listener.py:604` | `['price','close','current','last',' Price']` 中 `' Price'` 带前导空格，永不匹配 | ✅ 改为 `'Price'` |
| `attention/kernel/kernel.py:705` | `process_with_feedback()` 引用 `self._unified_manas`，但 `__init__` 从未定义 → 带 `pnl_pct` 反馈时必然 `AttributeError` | ✅ 在 `__init__` 显式声明 `self._unified_manas = None`（预留扩展点，行为不变） |
| `cognition/narrative/tracker.py:2217` | 关键词元组中 `"block"` 重复 | ✅ 去重 |
| `cognition/narrative/tracker.py:821,1089` | 两个同名 `detect_value_signals`，后者覆盖前者（**两份实现逐字节相同**，前者是死副本） | ✅ 删除死副本（兼容别名 `detect_tiandao_signals` 不受影响） |
| `state/system/system_state.py:203-230` | `record_task_execution` 声称批量写，末尾仍 `_save_unsafe()` 立即落盘 | ⏳ 未改（属写策略，需确认意图） |

**验证**：`scripts/verify/verify_misc_bugfixes.py` —— 4 组断言全通过。

### 7.3 循环导入（既有问题，已修 ✅）

```
market_hotspot/__init__.py
 └─ integration/__init__.py → integration/market_hotspot_system.py
     └─ data/__init__.py:12 → data/global_market_futures.py:172
         └─ bandit/__init__.py → bandit/runner.py → radar/__init__.py
             └─ radar/global_market_scanner.py:45 → 回到 data.global_market_futures ⇒ ImportError
```

在**全新解释器里单独 import `deva.naja.market_hotspot.data` 必然失败**；只有当 `bandit`（或 `radar`）先被导入时才正常。生产启动顺序恰好满足，所以从未暴露（已用 `git stash` 对照 **HEAD 原始版本，失败现象完全一致**）。

**修法（已实施）**：断点选在 `radar/__init__.py:47` —— 该行是全项目**唯一**模块级导入 `global_market_scanner` 的地方，而 radar 其余 eager 成员（`engine` / `trading_clock` / `news_fetcher` / `senses` / `global_market_config` / `openrouter_monitor`）**都不依赖它**。因此把 `GlobalMarketScanner` / `MarketAlert` / `MarketVolatilityTracker` / `ScanConfig` / `get_global_market_scanner` 改为 **PEP 562 惰性导出**（与 `deva/naja/__init__.py` 同一模板）：`from ..radar.trading_clock import ...` 触发 `radar/__init__.py` 时不再拉 `global_market_scanner`，环即断开；`from deva.naja.radar import GlobalMarketScanner` 仍照常可用。

**验证**：`scripts/verify/verify_radar_circular_import.py` —— 11 种导入顺序（含原先必然失败的首个 case、正反双向、惰性导出后再导入 market_hotspot）全部通过。

### 7.4 `sources.py` HTTP 编解码引用不存在的 `P.map`（死路径，已修 ✅）

`deva/core/sources.py:37-83` 的 `_decode_http_body` / `_encode_http_body` 原实现写成：

```python
from .pipe import P
...
return body >> P.map(try_dill_loads) >> P.map(...) >> ...
```

但 `deva/core/pipe.py` 里**根本不存在 `map` 这个名字**（`P` 是 `Pipe` 实例，只提供 `__ror__` / `__rrshift__`；也没有 `def map`）。即 **`P.map` 一访问就 `AttributeError`**——而这两个函数是 `from_http_request`（`Handler._loads`）与 `TCPStream` 的请求体编解码入口，也就是说这条 HTTP 请求体解码路径此前**从未真正跑通**。

**修法（已实施）**：按原意图直译为顺序解码函数（dill → bytes 解码 → json →（可选）DataFrame），不再构造 Pipe 链，也不必每次请求定义 4 个闭包。

**验证**：`scripts/verify/verify_sources_http_codec.py` —— 先固化旧实现 `P.map` 缺失必然报错的事实；再对 11 组输入核对 decode 语义、7 组 encode 语义与 DataFrame 分支；并测单次调用 ~3.5µs。

**同源问题（一并修）**：

- `deva/core/sources.py:261` `from_textfile._fetch_data` 同样写着 `parts >> P.map(lambda part: part + self.delimiter) >> ls` —— 只要读到完整一行就 `AttributeError`，即 `from_textfile` 这条流也是死的。已直译为列表推导。
- `deva/core/core.py:117-124` 的模块文档示例 `from deva import P` + `P.map/P.filter/P.reduce` 三处**全错**（`deva` 未导出 `P`；pipe 里既没有 `map`/`filter`/`reduce`，`P` 也不支持属性访问，helper 只能直接 `import`）。已改写为可运行的 `from deva.core.pipe import pmap, pfilter, sum as pipe_sum` 版本（实测 `data >> pmap(...) >> pfilter(...) >> pipe_sum` 可用）。

> 口径说明：`P` 是 `Pipe` 的**实例**（`@Pipe def P(func)`），只有 `__ror__` / `__rrshift__` 等管道运算，**不支持 `P.xxx` 属性访问**；可用 helper 是模块级名字（`pmap` / `pfilter` / `uniq` / `dedup` / `ls` / `sum` …），需 `from deva.core.pipe import <name>` 后直接当管道用。


---

## 8. 修复进展

| 编号 | 项目 | 状态 | 说明 |
|------|------|------|------|
| P0-3 | 同步 handler 阻塞 IOLoop | ✅ 已完成 | `web_ui/routes.py` `Jin10ImportantNewsHandler.get` 改 `async`；内存快路径 `_read_cached_news()` 直接读缓存，仅在缓存不可用时把阻塞抓取 `run_in_executor` 丢线程池。验证：编译通过；`inspect.iscoroutinefunction(get) is True`；模块可正常导入 |
| P0-2 | DBStream 写提交 | ✅ 已完成 | `core/store.py` 新增类常量 `WRITE_COMMIT_BLOCKING = False`，`append/upsert/bulk_update` 改非阻塞提交；`persist()/close()` 仍阻塞。验证：冒烟测试（读写回读、persist 后跨连接读取、删除、maxsize 淘汰）全通过 |
| P0-5 | 总线锁内执行回调 | ✅ 已完成 | `events/trading_bus.py` 锁内只做去重 + 订阅者快照，回调与持久化移到锁外；`_deliver_event` 改为接收快照并本地累加模块统计后加锁合并。验证：投递/去重/统计/异常隔离/**重入无死锁** 全通过。`cognitive_bus` 复核后无需改动 |
| P0-1 | 叙事追踪落库节流 | ✅ 已完成 | `cognition/narrative/tracker.py` 新增 `_maybe_save_state()`（按 `narrative_persist_interval_seconds`，默认 3s 节流）+ 脏标记 `_pending_persist`；`ingest_event` 改调它；`save_state()` 保持强制写，退出路径 `AttentionOS.persist_state()` 仍会兜底。验证：节流 4 个用例全通过 |
| P0-4 | 热点 payload 缓存 | ✅ 已完成 | `web_ui/routes.py` 新增 `_market_hotspot_payload_cached()`（TTL 1.0s，与 push_center 最小推送间隔对齐），SSE 与 API 两个调用点均改用它，N 个连接/请求收敛为 1 次重算 |
| P1-1 | manas 三次 get_summary | ✅ 已完成 | `attention/kernel/manas_engine.py` `ManasEngine.compute` 取一次 `portfolio_summary` 下传；`RiskEngine.compute` / `_get_cash_ratio` / `_get_drawdown` 增加可选 `summary` 参数（向后兼容），`portfolio_loss` 复用同一份 |
| P1-7 | optimizer O(n²) | ✅ 已完成 | `bandit/optimizer.py` `_get_arm_score` 增加可选 `total_pulls` 参数，调用处预计算一次，消除每个 arm 的全量重求和 |
| 微优化 | `deva/core` 热路径 | ✅ 已完成 | `core.py`：`Stream._emit` 去掉函数内 `import time`（提模块级）；`Sink.__init__` 的 `inspect.signature(Stream)` 提为模块常量 `_STREAM_INIT_PARAMS`；`sink.wrapper_function` 的签名解析改为惰性缓存一次。`namespace.py`：构造函数映射提为模块常量 `_CONSTRUCTORS`。验证：sink 无参/带参/流参数、map→sink 链路、命名空间缓存与错误路径全通过 |
| P1-4 | history_tracker O(板块×个股) | ✅ 已完成 | `market_hotspot/tracking/history_tracker.py` `_detect_changes`：个股变化计算只依赖 `symbol_weights`、**与 block 无关**，原先却放在 block 循环内 → 每个板块全量重扫。已提到循环外只算一次（每块给一份 `list()` 浅拷贝隔离）。验证：`verify_history_tracker_hoist.py` —— 54 个事件的 `top_symbols` 与独立参考实现逐一相同；`get_symbol_name` 调用 **4053 → 386 次**（20 板块 × 193 变化个股） |
| P1-8 | realtime_fetcher 热路径 SR() | ✅ 已完成 | `market_hotspot/data/realtime_fetcher.py` 新增 `_hotspot_ref()`：优先复用构造时已解析的 `_hotspot_system_inner`，否则惰性查单例并按非空缓存。5 处热路径（`_fetch_and_sync_cn` / `_process_cn_hotspot` / `_fetch_and_sync_us` / `_get_market_context` / `_fetch_and_process_market`）全部切换。`SR()` 每次都加锁（`SingletonRegistry.get` 走 `with self._lock`），批次级调用收益明显。验证：20k 次调用 0.0012s；优先/回退两条路径均正确 |
| P1-5 | 唤醒同步 async 内阻塞 requests | ✅ 已完成 | `state/system/wake_sync_handlers.py`：`fetch_news_list_async` 的分页 POST、`fetch_news_detail_async` 的 GET 改走 `asyncio.to_thread`（不再卡事件循环）；`main_async` 的逐条串行详情抓取改为 `asyncio.gather` + `Semaphore(4)` 并发；逐条 `sleep(0.5)` 改为常量 `WAKE_SYNC_PUBLISH_THROTTLE_SECONDS = 0.05`（**发布仍保持顺序**，因为下游认知处理对时序敏感）。100 条新闻的纯等待从 50s 降到 5s，详情抓取并发化 |
| 内存 | 叙事追踪无界增长 | ✅ 已完成 | 见 §4 三行（`_value_signals` 摊还裁剪、`_graph_edges` 权重裁剪、`_recent_hits` maxlen）。验证：`verify_narrative_memory_bounds.py` 7 组断言全通过（含索引一致性、不误删、高权重边保留） |
| Bug | `StrategySignalEvent` schema | ✅ 已完成 | 见 §7.1。验证：`verify_trading_event_schema.py` |
| Bug | 4 处零散 bug | ✅ 已完成 | 见 §7.2。验证：`verify_misc_bugfixes.py` |
| P1-6 | 启动期同步补作业 | ✅ 已完成 | `tasks/manager.py` `_catchup_missed_cron_tasks` 原先 4 个分支内联同步 `entry.run_once()`（任务体常含网络请求），改为先收集到 `to_catchup`，循环结束后交 `_dispatch_catchup_tasks()` 由**单个后台 daemon 线程串行**执行（保序、异常隔离、不阻塞启动）。验证：`verify_task_catchup_async.py`（提交 0.1ms 返回、后台确实执行、串行保序、单条异常不影响后续） |
| P1-3 | 逐条 quote 写 DB | ✅ 已完成 | `bandit/market_data_bus.py` `_persist_quotes_to_db` 由逐条 `upsert` 改为单次 `bulk_update`。验证：`verify_market_data_bus_bulk.py`（300 条读回一致、空输入、批量与逐条结果一致） |
| P1-9 | manas 每事件重建常量 | ✅ 已完成 | `attention/kernel/manas_engine.py` 提模块级 `_RISK_LEVEL_SCORES` / `_AI_COMPUTE_KEYWORDS_LOWER`（预 lower，省去每轮 `kw.lower()`）+ 删冗余局部 `import time`。验证：`verify_manas_constants.py`（常量内容一致、6 组样例命中计数一致、状态更新正常） |
| 微优化 | `deva/core/bus.py` inspect.stack | ✅ 已完成 | `_infer_sender_from_stack` 由 `inspect.stack()`（逐帧读取源码上下文）改为 `sys._getframe` 手工遍历。验证：`verify_bus_sender_inference.py`（语义等价，**99.7x** 加速） |
| Bug | 循环导入（radar ↔ market_hotspot ↔ bandit） | ✅ 已完成 | 见 §7.3。`radar/__init__.py` 的 `global_market_scanner` 改 PEP 562 惰性导出。验证：`verify_radar_circular_import.py`（11 种导入顺序） |
| 复核 | `ops.py` list.index / `market_data_bus` session 复用 / `sqlitedict` 无界 Queue | ⚠️ 复核后**不改** | 理由见 §3（P1-2）、§4、§5 —— 均属「风险 > 收益」或「原判断过重」，已在报告就地注明 |
| Bug | `P.map` 死路径（3 处） | ✅ 已完成 | 见 §7.4。`_decode_http_body` / `_encode_http_body` / `from_textfile._fetch_data` 一调用即 `AttributeError`（pipe 无 `map`），均改为直译；`core.py` 文档示例同步订正。验证：`verify_sources_http_codec.py`（固化旧 bug + 11 decode + 7 encode + `_fetch_data` 语义） |
| 其他 | `signal_listener` 去重表超限全量排序 | ✅ 已完成 | `_mark_processed` 去掉 `sorted`，改按插入序裁剪；保留条数与旧实现一致（`ceil(maxp/2)`）。验证：`verify_signal_dedup_eviction.py`（6 组上限逐条对照、200k 次吞吐 283 万/秒） |
| 其他 | `system_state.record_task_execution` 立即落盘 | ✅ 已完成 | 改为与 `record_active` 一致：仅置脏，距上次落盘 ≥ `BATCH_WRITE_INTERVAL`(60s) 才同步写，其余交后台线程；`shutdown()` 兜底。验证：`verify_system_state_throttle.py`（2000 次记录 → 落盘 0 次） |
| 复核 | `ops.unique` 非可哈希分支改 deque | ⚠️ 实测后**不改** | 隔离实测「变更快 112x / 成员查询慢 2.2x」；端到端小上限 deque 快、大上限 list 快，且该分支无调用点 → 保持原样（详见 §5.1） |

> 已改动文件（累计）：`deva/core/store.py`、`deva/core/core.py`、`deva/core/namespace.py`、`deva/core/bus.py`、`deva/core/sources.py`、`deva/naja/web_ui/routes.py`、`deva/naja/events/trading_bus.py`、`deva/naja/events/trading_events.py`、`deva/naja/attention/kernel/manas_engine.py`、`deva/naja/attention/kernel/kernel.py`、`deva/naja/cognition/narrative/tracker.py`、`deva/naja/bandit/optimizer.py`、`deva/naja/bandit/signal_listener.py`、`deva/naja/bandit/market_data_bus.py`、`deva/naja/tasks/manager.py`、`deva/naja/radar/__init__.py`、`deva/naja/state/system/wake_sync_handlers.py`、`deva/naja/state/system/system_state.py`、`deva/naja/market_hotspot/tracking/history_tracker.py`、`deva/naja/market_hotspot/data/realtime_fetcher.py`。全部通过 `py_compile`，并各有针对性回归脚本落在 `scripts/verify/`。

> **回归脚本统一跑法**（必须用干净环境，否则会被 WorkBuddy 注入的 shim 干扰）：
> ```bash
> env -i HOME="$HOME" USER="$USER" PATH=/usr/bin:/bin:/usr/sbin:/sbin TMPDIR="$TMPDIR" \
>   python3.13 scripts/verify/verify_xxx.py
> ```
> 注：`verify_*` 脚本均自包含；`verify_history_tracker_hoist.py` 内的 `import deva.naja.bandit` 现已是普通依赖（循环导入已于本轮修复，见 §7.3）。


