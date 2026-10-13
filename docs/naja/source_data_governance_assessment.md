# 源端数据治理 · 影响面评估报告

> 时间：2026-10-13
> 范围：`market_hotspot/tracking/history_tracker.py`、`market_hotspot/integration/market_hotspot_system.py`、`market_hotspot/data/realtime_fetcher.py`
> 性质：**评估，不改代码**。本文只回答「能不能修、怎么修、改了会波及谁」。
> 复现：`env -u PYTHONPATH /Users/spark/.local/bin/python3`（只读 `~/.naja/*.json`）

---

## 0. 结论摘要（TL;DR）

| # | 问题 | 判定 | 修复量级 | 建议 |
|---|---|---|---|---|
| P0 | `market` 标识错位 | **根因是跨市场快照互相比对**，不是"标识写错" | 小（1 处守卫 + 3 处口径） | **本轮修**，性价比最高 |
| P1 | `change_percent` 脏值（999 / 73613%） | 与 P0 **同源**，P0 修完天然消失大半 | 小 | 与 P0 同批修 |
| P2 | `_optimize_cn_events` 的 `>=3%` 形同虚设 | **量纲用错了**，不是阈值定低了 | 中（需重新定义"异动强度"） | 需先定口径，**可延后** |

**一句话**：P0 和 P1 是同一个 bug 的两个症状，一个守卫就能治；P2 是独立的设计缺陷，修它要动阈值语义，建议排在 P0 之后、单独一个小项。

另外发现一个**计划外**的静默失效（§5），顺手可清。

---

## 1. 现状实测（2026-10-13 盘中，可复现）

### 1.1 污染是**双向**的，且美股库基本被 A 股板块占领

```
cn_block_events.json : 500 条，466 条(93%) 中文板块名 —— 符合预期
us_block_events.json : 300 条，269 条(90%) 中文板块名 —— 不符合预期
```

| 指标 | cn | us |
|---|---|---|
| 去重 `block_name` | 211 | 140 |
| **与 cn 的交集** | — | **140 / 140 = 100%** |
| us 特征板块名（`ev`/`crypto`）在本库出现 | 有（各 2 条） | 有（各 3 条） |
| cn 特征板块名（`中特估`/`次新股`/`复合铜箔`）在本库出现 | 有 | **有**（`中特估`2、`复合铜箔`3…） |

`us` 库的去重名单里，`crypto / ev / ai_chip / cloud_ai / streaming`（蛇形英文，真美股）约 12 个，
其余 **127 个全是 A 股板块名**（`一带一路`、`中特估`、`储能`、`光伏`、`华为海思`…）。

→ 之前记的「us_event 是 cn_event 的子集」现在可以说得更准：**us 库几乎是 cn 库的一个克隆**。

### 1.2 `change_percent` 阈值通过率

| 阈值 | cn 通过率 | us 通过率 |
|---|---|---|
| `>= 3%` | **100%** | **100%** |
| `>= 10%` | 100% | 99% |
| `>= 30%` | **100%** | 99% |
| `>= 100%` | 82% | 98% |
| `>= 999%` | 13%（67 条哨兵） | **90%**（271 条哨兵） |
| 最大值 | **73 613%** | 999% |

两条独立结论：
* 阈值**完全失效**——连 `>=30%` 都 100% 通过；
* `us` 库 90% 的条目是 `999` 哨兵（权重 0→N 编码），意味着 **us 库的事件几乎全是「新进榜」**，没有一次是真正的"涨跌幅"。
  这也解释了托盘里 🇺🇸 条目的怪异感。

### 1.3 产生形态仍是「批式」

`cn` 500 条只挂在 11 个时间戳上（平均 45.5 条/批，最大 147），跨度 34.7 分钟；
`us` 300 条挂 13 个时间戳，跨度 29.4 分钟。与 `docs/naja/event_frequency_analysis.md` 一致，未变。

---

## 2. 根因分析

### 2.1 P0：跨市场快照互相比对（真根因）

**关键事实**：CN 与 US **共用同一个 `HistoryTracker` 单例**。

```python
# market_hotspot_system.py:431-449  两个市场都往同一个 tracker 里塞快照
tracker = get_history_tracker()          # 模块级单例，见 history_tracker.py:1443
tracker.record_snapshot(..., market=market)
```

`record_snapshot` 把 CN / US 快照**追加进同一个 `self.snapshots` 列表**（`history_tracker.py:437`），
下一批数据到达时，`_detect_changes(previous_snapshot, snapshot)` 拿到的 `old` / `new`
**是相邻两次推送**——而这两次推送**可能是不同市场**。

于是 `_detect_changes` 里：

```python
# history_tracker.py:629
all_blocks = set(old.block_weights.keys()) | set(new.block_weights.keys())   # ← 并集
...
# history_tracker.py:723
if old.market == 'US':        # ← 用 old 的市场分流，但 all_blocks 是两个市场的并集
    add_us_block_event(event_data)
else:
    add_cn_block_event(event_data)
```

**污染路径**（`old = US 快照`，`new = CN 快照`）：

1. `all_blocks` = US 板块 ∪ **A 股板块**；
2. 循环里 A 股板块 `new_weight > 0, old_weight == 0` → `change_pct = inf` → 编码成 `999`；
3. 分流看 `old.market == 'US'` → 真的写进 **`us_block_events.json`**；
4. 于是 `次新股` / `生物疫苗` 被打了 🇺🇸。

反向同理（`old = CN`，`new = US`）→ `ev` / `crypto` 混进 `cn` 库（实测各 2 条）。

这一条机制**同时解释了三件事**：
* us 库 90% 是中文板块名；
* us 库 90% 是 `999` 哨兵（跨市场比对时，"对方市场的板块在这个市场恒为 0"）；
* `73613%` 这种巨值（两个不同市场、量纲完全不同的权重相除）。

> 也就是说：**`old.market != new.market` 时，`_detect_changes` 的整个输出都是无意义的。**
> 之前判断的「A 股板块的 market 被写成 US」只是**症状的表述**，不是根因——
> 实际没有一处代码把 A 股标成 US，是**比对阶段把两个市场搅在了一起**。

### 2.2 P1：`change_percent` 脏值

三个叠加来源：

| 来源 | 代码 | 表现 |
|---|---|---|
| `inf` 哨兵 | `history_tracker.py:693 / 716 / 736 / 819` | `change_pct if != inf else 999` → 渲染成 `+999.0%` |
| 跨市场比对 | 同 §2.1 | `(US权重 - 0) / 0` 或两个量纲相除 → `73613%` |
| 旧基线权重极小 | `(new-old)/old*100`，`old` 可低至 1e-4 | 微小基数放大成 5 位数百分比 |

**注意**：这里的 `change_percent` 语义是**「板块权重变化 %」**，不是股票涨跌幅 %。
UI 直接渲染成 `+73613%` 是**语义层面的误导**，不只是数字难看。

### 2.3 P2：`>=3%` 过滤形同虚设

```python
# market_hotspot/ui_components/timeline/market_24h_timeline.py:212-217
for event in events:
    chg_pct = event.get('change_percent', 0)
    if abs(chg_pct) >= 3:      # 想滤掉"不显著"的异动
        filtered_events.append(event)
```

失效原因**不是阈值太低**，而是：

1. 写入端（`history_tracker.py:701`）**已经**用 `abs(change_pct) >= 3` 做过一次准入 →
   存进 JSON 的**每一条本来就 >= 3%**，读出来再过滤一次是恒真命题（实测通过率 100%）；
2. 阈值作用在「权重变化率」上，而权重是 0.00x 级别的**小数**，只要板块名次轻微挪动就是几十个百分点 →
   `>=30%` 都 100% 通过，阈值**在这个量纲上没有分辨力**。

→ 想让它真起作用，得先定义**「什么样的板块异动值得上时间线」**（例如：绝对权重从 N 名外进前列、
或个股龙一涨停、或权重变化绝对值而非百分率），这是**产品口径问题**，不是调参问题。

---

## 3. 影响面

### 3.1 直接消费方（就这 3 处，可控）

| 消费方 | 位置 | 用途 | 受污染影响 |
|---|---|---|---|
| 24h 时间线 | `ui_components/timeline/market_24h_timeline.py:148 / 345 / 1040 / 1051` | `/market` 页面 + 托盘时间线 | **是**（us 段显示 A 股板块 + 🇺🇸） |
| 服务器同步 | `state/system/server_sync_handler.py:529 / 562` | `get_cn/us_events_from_server_or_local` | **是**（污染随同步扩散到远端） |
| 托盘提示 | `infra/ui/menu_bar_tray.py` 经时间线取数 | 一级菜单条目 | **是**（配额已降到 cn2/us1 兜住体量） |

### 3.2 不会崩 —— 这是好消息

* `block_events_store.py` 全是**容错读取**：`json.load` 失败 → 清空重来；字段缺失 → `.get(k, default)`；
* `_optimize_*` 全部包在 `try/except: return []` 里；
* 落盘是 `add_*_event` 内部 `try/except` + `log.warning`。

→ 所以这个问题**从上线起就没报过错**，属于典型的「静默失效」——数据错，但链路健康。
**也意味着没有"脏数据导致崩溃"的紧迫性**，可以从容修。

### 3.3 不可逆的部分

* `us_block_events.json` / `cn_block_events.json` **历史脏数据已在盘上**（500 + 300 条，48h TTL）。
  修好代码**不会自动清洗旧数据**，须显式处理：推荐**直接删两个文件**（48h 内自然重建，
  无外部引用、无 schema 迁移成本）。**不要写迁移脚本**——投入产出不成正比。

### 3.4 会不会波及 manas / 决策链路

**不会**。已核对：

* `history_tracker` 的事件只喂 **UI 时间线 + 托盘 + server sync**；
* `manas` 的输入走 `attention/kernel/`（零 deva 依赖）与 `decision/query.py`，
  **不消费** `*_block_events.json`；
* 因此**不触碰 `verify_manas_compute_snapshot` 基线快照**，不存在打分漂移风险。

### 3.5 现有测试

* `deva/naja/tests/test_tray_focus.py`（23 条）、`test_event_router.py` —— 需回归；
* `scripts/verify/verify_tray_focus.py --strict`（7 段）—— **必修，且要加一段覆盖跨市场守卫**；
* `docs/naja/event_frequency_analysis.md` 的实测数字**会变**（us 库缩水、999 占比下降）→ 须同步更新，
  否则文档与守卫互相打脸。

---

## 4. 修复方案（按推荐顺序）

### 步骤 1（P0 核心，建议本轮做）

**在 `_detect_changes` 入口加一道市场守卫**——这是最小且最高杠杆的一改：

```python
def _detect_changes(self, old, new, timestamp_str=None):
    # 跨市场快照不可比：权重体系不同，比对结果无意义（曾导致 us/cn 库互相污染）
    if normalize_market(old.market) != normalize_market(new.market):
        return
```

配套三处口径修正：

| 位置 | 现状 | 改为 |
|---|---|---|
| `history_tracker.py:723` 分流 | `if old.market == 'US'` | `if new.market == 'US'`（且此刻两者已相等，语义清晰） |
| `history_tracker.py:629` `all_blocks` | 两快照并集 | 加守卫后天然只剩同市场，无需改 |
| `history_tracker.py:696` / `:728` | `market=old.market` / `旧日志前缀` | `new.market` |

> 已核对：`old.market` 全文只出现在 `:696` `:723` `:728` 三处，全在 `_detect_changes` 内。
> 早先本文写的 `:819` 是笔误（那是个股级 `change_percent`，与市场标识无关）。

**风险等级：低**。前置条件成立（`old.market != new.market` 时本就该跳过）——是**纯收窄**，不会产生新的错误事件。
**代价**：跨市场交替推送时，**每个市场的第一次快照不再产生事件**（因为上一条快照是另一个市场）。
考虑到事件是批式的、每次扫描 100+ 条，少一批无感。若在意，可让 tracker **按市场分列表**存快照（见步骤 3）。

### 步骤 2（P1，与步骤 1 同批）

* `999` 哨兵**保留**（渲染层 `format_change_percent()` 已能识别并显示「新进榜」，托盘/页面/文本三处共用）；
* 但**新增约定**：跨市场比对被守卫挡掉后，`999` 只会在"同市场内权重 0→N"时出现——这才是有意义的新进榜；
* 顺手在写入端加**量纲自检**：`change_pct` 超过合理上界（如 1000%）时记 `warning` 并落 `None`，
  让下次再有脏值**能被发现**（本仓已有「合法的空比异常更危险」的教训，这里同理：**不能让它继续静默**）。

### 步骤 3（可选，视步骤 1 效果决定）

**让 tracker 按市场分区**：`self._snapshots: Dict[str, List[HotspotSnapshot]]`，
`record_snapshot` 按 `market` 追加，`_detect_changes` 只与**同市场**的上一条比。
比步骤 1 更彻底（不会丢"跨市场后的第一批"），但动了 `snapshots` 这个被多处读的字段
（`save_state` / `load_state` / `get_symbol_name` 路径），**改动面明显变大**。
→ **建议先只做步骤 1，观测一天再决定要不要做步骤 3。**

### 步骤 4（P2）——✅ 已实施（2026-10-13 晚）

**根因最终定性：不是「阈值调低」，是「读取端阈值 < 写入端阈值」的数学矛盾。**

* 写入端 `history_tracker.py:747`：只有 `abs(change_percent) >= 5`（外加 新进榜/消退）才落盘；
* 读取端 `market_24h_timeline.py:216`：过滤条件却是 `abs(change_percent) >= 3`。

→ **3 < 5 ⇒ 落盘事件必然 >3 ⇒ 该过滤是恒真命题**，不可能不通过。
这在修复跨市场污染后依然成立（实测 17 条样本 `>=3` / `>=30` 通过率均 **100%**，
`>=100` 才 59%）。

**修法**：把门槛改为对齐美股分支（`_optimize_us_events` 用 `|chg| >= 20`）的
**真正有分辨力**的门槛，并抽成模块常量 `CN_EVENT_MIN_PCT`，可用环境变量
`NAJA_CN_EVENT_MIN_PCT` 覆盖。

```python
CN_EVENT_MIN_PCT = float(os.environ.get("NAJA_CN_EVENT_MIN_PCT") or 20.0)
...
if abs(chg_pct) >= CN_EVENT_MIN_PCT:      # 原为 >= 3（恒真）
    filtered_events.append(event)
```

> ⚠️ 量纲提醒（写进代码注释了）：`change_percent` 是**题材权重的相对变化率**，
> 不是股票涨跌幅——权重是 0.00x 级小数，所以它天然分布在几十~几百 %。
> 用"涨跌幅直觉"（3%/5%/10%）设阈值在这里全是错配。
> 20 这个默认值只保证「不再恒真、且与美股一致」；**正式标定仍需更多修复后真实数据**
> （当前样本仅 17 条冷启动数据，不够）。

---

## 5. 计划外发现：一处静默失效（顺手可清）

```python
# market_hotspot/data/realtime_fetcher.py:423-430
for symbol in codes:
    if symbol and len(symbol) >= 6:
        try:
            hotspot_system.register_symbol(symbol, ['A股'])
        except Exception:
            pass          # ← MarketHotspotSystem 根本没有 register_symbol 方法
```

`MarketHotspotSystem` **没有 `register_symbol`**（已核对：`register_symbol` 只存在于
`core/weight_pool.py:85`、`scheduling/frequency_scheduler.py:94`、`engine/river_engine.py:162`）。
`try/except Exception: pass` 把 `AttributeError` **每批行情吞一次**，
日志里干干净净——这正是本仓反复出现的「UI/调用写好了、注册链路没接」家族的新成员。

**影响**：A 股新符号**从未**经此路径注册（真实注册走 `initialize` 的 `symbol_block_map`）。

### ✅ 已移除（2026-10-13 晚）—— 判定为「幽灵调用」

补方法**不可取**，理由比"是死代码"更硬：

1. **符号其实已全量注册**。启动日志实测：`[MarketHotspotSystem] 已注册 6288 个个股`
   （A 股总数约 5.4k，覆盖充分）→ 运行时无须补注册。
2. **即便补上方法，也会帮倒忙**。`'A股'` **不是 block_id**（block_id 是 269 个题材名）。
   `weight_pool.register_symbol(symbol, blocks)` 对已存在符号会执行
   `self._symbol_blocks[symbol] = blocks`（`:99`）——即把**每只股票的题材映射覆盖成 `['A股']`**，
   直接摧毁全部题材归属。
   → **它「一直没生效」实际上一直在保护系统。** 这种 bug 修反而有害。

故直接删除该循环（`realtime_fetcher.py:_process_cn_hotspot`），并在代码里写清
「若将来确需运行时补注册，正确入口是 `weight_pool.register_symbol` + **真实题材 id**，
且不得覆盖已存在映射」。

---

## 6. 验收清单（修的时候照着跑）

```bash
# 0) 改前备份（可选，48h 内自然重建）
cp ~/.naja/cn_block_events.json ~/.naja/us_block_events.json /tmp/

# 1) 静态守卫：新测试 — 跨市场快照不得产生事件
#    tests/test_history_tracker_market_guard.py
#    old=US快照(含 crypto) + new=CN快照(含 次新股) → _detect_changes 后
#      · cn/us 两个 store 均无新增
#    反向同理

# 2) 回归
env -u PYTHONPATH pytest deva/naja/tests/test_tray_focus.py deva/naja/tests/test_event_router.py -q

# 3) 守卫脚本
env -u PYTHONPATH /Users/spark/.local/bin/python3 scripts/verify/verify_tray_focus.py --strict

# 4) 手动确认（次日盘中）
env -u PYTHONPATH /Users/spark/.local/bin/python3 -c "
import json,os,re
h=os.path.expanduser('~/.naja')
d=json.load(open(os.path.join(h,'us_block_events.json')))['events']
print('us 条数:',len(d),'中文名占比:',round(sum(1 for e in d if re.search(r'[\u4e00-\u9fff]',e.get('block_name','')))/max(1,len(d))*100),'%')
"
# 期望：中文名占比显著下降（理想 < 20%），999 哨兵占比下降
```

**验收标准**：
1. `us` 库中文板块名占比从 **90% → 显著下降**；
2. `cn ∩ us` 不再是 100% 子集关系；
3. 跨市场守卫测试通过，且**不产生**新事件；
4. `verify_tray_focus.py --strict` exit 0；
5. 全量单测无新增失败。

---

## 7. 明确不做

* ❌ **不写历史数据迁移脚本**——TTL 48h，删文件比写迁移便宜；
* ❌ **不在本轮改 P2 阈值**——口径未定，先拿 P0 修复后的真实数据再决策；
* ❌ **不动 `attention/kernel/` 与 `manas`**——已在 §3.4 确认无耦合，改动只会引入无关风险；
* ❌ **不引入新的 `SR()`**（遵守 `AGENTS.md` 架构规则 3）。

---

## 8. 工时与立项建议

| 项 | 内容 | 量级 |
|---|---|---|
| ① P0 守卫 + 口径修正 | §4 步骤 1 | 小（1 处守卫 + 3 处字段） |
| ② P1 量纲自检 + 文档同步 | §4 步骤 2 + §3.5 | 小 |
| ③ 新增跨市场守卫测试 | §6 第 1 项 | 小 |
| ④ P2 口径调研 | §4 步骤 4（**只调研不改**） | 中（需真实数据 + 决策） |
| ⑤ 静默失效判定 | §5（删 or 补） | 待你一句话 |

**建议**：① ② ③ 合成**一个 commit**（同源问题，一起修一起验，便于回滚）；
④ 独立小项；⑤ 待确认后并入 ① 或单开。

---

## 附：可复现的只读取数脚本

见本报告 §1 与 §6 第 4 项。所有检查均为**只读**（`json.load` + 统计），不写任何落盘数据。

---

## 附录 A：本次落地记录（2026-10-13）

步骤 1 / 2 / 3 已实施并提交（`0dca409`）：

| 改动 | 位置 |
|---|---|
| `_market_key()` 严格市场判定（**不复用** `normalize_market`，避免 `UNKNOWN` 被兜底成 `CN`） | `history_tracker.py:36` |
| `_detect_changes` 入口跨市场守卫 | `history_tracker.py:636-649` |
| 分流口径 `old.market` → `new.market` | `history_tracker.py:735 / 765 / 770` |
| 变化率量纲自检（`_CHANGE_PCT_SANE_MAX = 1000.0`，只告警不拦截） | `history_tracker.py:33 / 668 / 702 / 828 / 913` |
| 新增守卫测试（**16 条**） | `deva/naja/tests/test_history_tracker_market_guard.py` |

**验证结果**：全量单测 **365 passed**；`verify_history_tracker_hoist.py` 通过；
`verify_tray_focus.py --strict` exit 0；manas 快照 15 场景差异 **0**。

**脏数据清理**：备份至 `/tmp/naja_block_events_backup_20261013_152511/` 后，
停服务 → 删 `~/.naja/{cn,us}_block_events.json` → 重启（Naja `44845` / 托盘 `44844`），
`/api/health` 正常、`/api/tray/data` 正常返回。
（本地库为**空**属预期：盘中已收，等下一个交易日重建；详见附录 B 关于远端的那一层。）

### 未做（待定）

* **步骤 3**「tracker 按市场分区」——观测一天后再决定是否需要（步骤 1 已堵住污染）；
* **步骤 4（P2 阈值口径）**——需先拿修复后的真实数据重测通过率；
* **§5 的 `register_symbol` 静默失效**——待确认「这条路径预期有作用吗」。

---

## 附录 B：⚠️ 远端同源污染 —— 本机修复单靠自己是洗不干净的（2026-10-13 实测）

清本地数据时发现的**结构性边界**，比原先预估的影响面更大：

### B.1 事件有**两层**缓存，远端优先级更高

```
history_tracker 落盘  →  ~/.naja/{cn,us}_block_events.json          （本地库，已清）
                                    ↓ 时间线只在这里兜底
远端 ai.secsay.com:8080/api/market/timeline
                                    ↓ 客户端 HTTP 拉取后合并
                      ~/.naja/server_sync/{cn,us}_events_server.json （服务器缓存，优先读）
                                    ↓
                      market_24h_timeline._get_*_events()  ← 优先返回服务器缓存
```

`get_us_events_from_server_or_local()`（`server_sync_handler.py:546`）**先读服务器缓存**，
只有不足 3 条时才回落到本地 store。所以：

**本机把本地库删干净，时间线依旧显示脏数据——因为它读的是服务器缓存。**

### B.2 远端污染程度与本机**完全一致**

实测 `http://ai.secsay.com:8080/api/market/timeline`（2026-10-13 15:27）：

| 指标 | 远端 `us_event` | 远端 `cn_event` |
|---|---|---|
| 条数 | 300（= `MAX_US_EVENTS`） | 500（= `MAX_CN_EVENTS`） |
| **中文板块名占比** | **270/300 = 90%** | 444/500 = 89% |
| `change_percent >= 999` | **275/300** | 48/500 |
| 样本 | 钴金属 / 维生素 / IP经济 / 无人机 / 粤港澳 | 口罩防护 / 维生素 / 钴金属 / IP经济 |

上限数字（500 / 300）与本机 `block_events_store.py` 的 `MAX_CN_EVENTS` / `MAX_US_EVENTS`
**完全相同** → 远端跑的是**同一套 pipeline**，同一个 bug 在那边也在持续产出。

### B.3 结论：必须两边都部署

| | 本机 | 远端 `ai.secsay.com`（152.136.133.71） |
|---|---|---|
| 代码 | ✅ 已修（`0dca409`） | ❌ 需同步部署 |
| 已有脏数据 | ✅ 已清 | ❌ 仍在 48h 窗口内 |

**只修本机达不到"托盘上不再出现 A 股板块带 🇺🇸"的效果**，因为客户端优先读服务器缓存。
远端部署后，旧脏数据最迟 **48h（`CACHE_HOURS`）** 自然过期。

### B.4 本地 `server_sync` 缓存**故意不清**

`~/.naja/server_sync/{cn,us}_events_server.json`（现存 87 条 us / 15:00 快照）**决定不删**：

* 删了也只会立刻从远端**原样拉回来**（远端未修），等于零收益；
* 而它是当前**唯一**还在提供板块事件的数据源（本地库已清、盘中已收）→
  删了反而让时间线的板块事件整段空白，UX 净变差。

→ 等远端部署 + 48h 过期后，这两个文件自然干净。**不折腾。**

### B.5 ✅ 已解决（2026-10-13 晚）—— 远端已部署并验证

原先我以为"无法从本机部署远端"。**实际可以**：

* `~/.ssh` 已有免密通道（`ssh root@secsay.com` 直通，远端主机名 `VM-0-6-centos`，腾讯云）；
* 仓内本就有两个部署脚本：`scripts/sync_to_server.sh`、`scripts/git_update_server.sh`；
* 远端代码路径 `/usr/local/lib/python3.10/site-packages/deva/`，服务由 `nohup python3 -m deva.naja`
  启动、PID 记于 `/root/naja.pid`、日志 `/root/.naja/logs/naja_console.log`。

**执行**：备份 → `scp` 覆盖 `history_tracker.py` → 清 pyc → 清两层脏缓存 → 强杀重启。

**验证（决定性）**——远端重启后新生成的 `us_block_events.json`：

| 指标 | 修复前 | 修复后 |
|---|---|---|
| 条数 | 300 | 20（冷启动） |
| 中文板块名 | 270 (90%) | **0** |
| 999 哨兵 | 275 (90%) | **0** |
| 样本 | 钴金属 / 维生素 / 无人机 | fintech / ai_chip / healthcare / ev / crypto |

→ **跨市场污染已彻底消除**。旧脏数据最迟 48h（`CACHE_HOURS`）自然过期，无须再等。

---

## 附录 C：本轮收口记录（2026-10-13 晚）

前一轮修了 P0+P1（本机），本轮把**剩余全部收口**，并补上最关键的远端部署。

### C.1 做了什么

| # | 项 | 位置 | 状态 |
|---|---|---|---|
| 1 | 跨市场守卫 + 分流改 `new.market` + 量纲自检 | `tracking/history_tracker.py` | ✅ 上轮 `0dca409` |
| 2 | **远端同源部署** | `ai.secsay.com:/usr/local/lib/.../deva/` | ✅ 本轮 |
| 3 | **`register_symbol` 幽灵调用移除** | `data/realtime_fetcher.py` | ✅ 本轮 `cc26fc2` |
| 4 | **A 股事件过滤「恒真」修正** | `ui_components/timeline/market_24h_timeline.py` | ✅ 本轮 `cc26fc2` |

### C.2 远端部署细节（可复用）

```bash
# 0) 探测远端结构（远端 = VM-0-6-centos，代码在 site-packages）
ssh root@secsay.com 'ls /usr/local/lib/python3.10/site-packages/deva/naja/market_hotspot/tracking/'

# 1) 备份（代码 + 两层数据缓存）
ssh root@secsay.com 'mkdir -p /root/naja_backup_$(date +%Y%m%d_%H%M%S) && ...'

# 2) 覆盖单文件（不要用 sync_to_server.sh 的 rsync --delete——远端版本与本地差
#    106 行全是本次修复，整体覆盖会牵扯无关文件；单文件 scp 最稳）
scp deva/naja/market_hotspot/tracking/history_tracker.py \
    root@secsay.com:/usr/local/lib/python3.10/site-packages/deva/naja/market_hotspot/tracking/

# 3) 清 pyc（防加载旧字节码）
ssh root@secsay.com 'find .../tracking/__pycache__ -name "*history_tracker*" -delete'

# 4) 清两层脏缓存
ssh root@secsay.com 'rm -f /root/.naja/{cn,us}_block_events.json \
                             /root/.naja/server_sync/{cn,us}_events_server.json'

# 5) 重启（远端无 systemd；必须 setsid/nohup 脱离 ssh 会话，否则进程随连接死）
ssh root@secsay.com 'pkill -9 -f deva.naja; sleep 3; \
  cd /root && setsid nohup python3 -m deva.naja --port 8080 --host 0.0.0.0 \
  > /root/.naja/logs/naja_console.log 2>&1 < /dev/null &'
```

**踩到的坑**：第一次重启用 `kill $(cat /root/naja.pid)` 失败——`naja.pid` 是**空的**
（远端从未写对 PID 文件），`pkill -f deva.naja` 也没能终止老进程（内存里仍是旧代码）。
正确做法是 `pkill -9 -f deva.naja` 强杀 + 用 `ss -ltnp | grep 8080` 确认端口释放后再起。

### C.3 验证结果汇总

| 验证 | 结果 |
|---|---|
| 远端 `us_block_events` 中文板块名 | 270/300 → **0/20** |
| 远端 `us_block_events` 999 哨兵 | 275/300 → **0/20** |
| 本机 `us_block_events` 中文名 | → **0/15** |
| 全量单测 | **377 passed** |
| `verify_tray_focus.py --strict` | 全绿 |
| `verify_manas_compute_snapshot --check` | 15 场景 **差异 0** |

### C.4 仍待标定（不阻塞）

* **`CN_EVENT_MIN_PCT=20` 只是"不再恒真 + 与美股一致"的默认值**。正式口径需在
  跨市场修复后积累足够真实数据（当前仅 17 条冷启动样本，`change_percent` 集中在 91~400），
  再用分位数标定；可用 `NAJA_CN_EVENT_MIN_PCT` 免改码调整。
* 「tracker 按市场分区」（比"入口守卫"更彻底）仍未做——守卫已堵住污染，暂无必要。

