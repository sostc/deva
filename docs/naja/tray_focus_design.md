# 托盘信息聚焦（Tray Focus）设计

> 起因：用户问「托盘菜单里现在有哪些信息会过载」。
> 排查后的结论是——**问题不只是"太多"，而是"该多的多、该少的少"**：
> 15 条板块异动霸屏，真正的新闻类一条都进不来，连带通知功能实际处于失效状态。

交付：`select_timeline_events`（唯一截断口径）+ 托盘一级菜单重构 + 通知聚合限流
+ `scripts/verify/verify_tray_focus.py`（5 组）+ `test_tray_focus.py`（15 条）。

---

## 1. 问题现场

### 1.1 菜单全貌（重构前，展开约 40 项、需滚动）

```
服务状态 3 行（标题 / 状态 / 端口）
📈 常用页面（市场热点 / 交易中心 / 认知系统 / 系统日志 / 系统状态）
🔧 管理工具（策略 / 信号 / 数据源 / 任务）
🚀 登录时自动启动
🌐 打开 Web / 📄 打开日志 / 🔄 刷新 / ☁️ 从服务器同步
⏰ 全球市场时间线 | 🇨🇳 30 | 🇺🇸 8 | 📰 8 | 📌 7      ← 4 个裸数字
✨ 一键总结当前时间线
事件流 15~20 条（含「─ ×30」日期分隔行）
🔄 重启服务
```

### 1.2 五个过载点

| # | 过载点 | 证据 |
|---|---|---|
| 1 | 事件流平铺一级菜单 | `events[:20]`，菜单被撑到 ~40 项 |
| 2 | 统计条 4 个裸数字 | `时间线 \| 中30 \| 美8 \| 闻8 \| 十7`——无单位无语境 |
| 3 | 噪声数据 | 实测 `风电 +999.0%`、`乡村振兴 -100.0%`（哨兵值）；同一词以 中+999 / 美-100 重复且矛盾 |
| 4 | 分层不当 | 低频运维页（`/logstream`、`/health`）混进"常用页面"；"管理工具"4 项占顶层 |
| 5 | 重复项 + 缺项 | 顶层「📄 打开日志」与常用页面内「📜 系统日志」重复；新上线的 **`/focusadmin` 没有入口** |

### 1.3 最严重的不是过载，是"该显示的没显示"

`market_24h_timeline.py` 的 `all_events[:15]` —— **只按 timestamp 降序硬截断，没有分类配额**。

- 板块异动（cn_event/us_event）是**秒级持续更新**的，时间戳永远最新 → 永远霸占全部 15 个名额；
- 高分新闻（8 条）与金十快讯（7 条）更新频率低 → **几乎永远被挤出 `list`**。

实测 `/api/tray/data` 印证：

```
stats: cn_events=30, us_events=8, high_score_news=8, jin10_news=7   ← 共 53 条
list : 15 条，type 分布 = {us_event: 7, cn_event: 8}                ← 新闻类 0 条
```

更糟的是连带的**通知也死了**：`_check_and_send_notifications` 只对
`high_score_news`/`jin10_news` 且 `score≥0.7` 弹通知，而它遍历的正是同一个 `list`
→ **托盘通知实际永不触发**。菜单里看不到新闻、通知也不响，托盘的"信息入口"价值归零。

> 这是本项目反复出现的同一类病因：**「链路写了、数据不在同一条路上」的静默失效**。

---

## 2. 设计要点

用户明确要求：**新闻流仍留一级菜单直接可见 + 可点击总结**。
所以手法**不是**"把事件流折叠进子菜单"，而是 **配额 + 排序 + 限长**：
一级菜单依然是一屏看得完的新闻流，但内容**先给新闻**。

### 2.1 `select_timeline_events` —— 全仓唯一的截断口径

```python
TRAY_TIMELINE_LIMITS = {
    "high_score_news": 4,
    "jin10_news": 4,
    "cn_event": 2,
    "us_event": 2,
}

def select_timeline_events(all_events, per_type_limits=None):
    if not per_type_limits:
        return list(all_events[:15])          # 旧行为，调用方零影响
    picked = []
    for etype, limit in per_type_limits.items():
        if limit <= 0:
            continue
        picked.extend([e for e in all_events if e.get("type") == etype][:limit])
    picked.sort(key=lambda e: e.get("timestamp", 0), reverse=True)
    return picked
```

两条设计约束：

1. **`per_type_limits=None` → 旧 `[:15]`**：`/market` 等既有调用方行为完全不变，
   只有显式传配额的托盘侧才改变。**改口径不改默认值**，把影响面收窄到目标调用方。
2. **口径只有一份**：托盘侧 `_get_timeline_events` 与页面/数据接口
   `get_timeline_data_for_api` 都调这一个函数。原先两处各写一遍 `[:15]`，
   改一处漏一处就会分叉——这次收口成一个函数。

### 2.2 托盘一级菜单重构

| 区域 | 改动 |
|---|---|
| 状态行 | 3 行（标题 / 状态 / 端口）→ **1 行**：`📊 Naja 运行中 · 交易中 · 端口 8080` |
| 常用页面 | 补 `/focusadmin`；`/logstream`、`/health` 移出 |
| 顶层快捷 | 「📄 打开日志」去重（常用页面内的「系统日志」已删） |
| 新闻流 | 标题 `📰 今日新闻流 · 24h N 条 · 显示 M`（如实区分总量与上屏数）；**按时间倒序**，`ordered[:TRAY_MENU_MAX_EVENTS]` 限长；保留「✨ 一键总结」；补「⏰ 查看全部时间线（N 条）」 |
| 系统子菜单 | `⚙️ 系统 ▸` 收拢：日志流 / 系统状态 / 数据源 / 任务 / 策略 / 信号 / 自启 / 同步 / 重启 / 退出 |

**呈现顺序 = 纯时间倒序**（2026-10-13 修订）：

```python
ordered = sorted(items, key=lambda e: -float(e.get('timestamp', 0) or 0))
```

> **为什么不再按 `news_first` 分组**：分组会把时间线切成"新闻段 + 板块段"两截，
> 看着不像时间线（用户诉求原话：「event 和新闻最好是按照时间排序」）。
>
> 「新闻不被板块异动挤掉」这件事**已经由取数侧的配额保证**——
> `select_timeline_events(TRAY_TIMELINE_LIMITS)` 让板块异动最多只占 3/12 个名额，
> 呈现层再分组就是重复设防。
>
> 副作用（符合预期）：板块异动是秒级/批式更新的，时间戳最新 → 会自然落在**最上面几条**。
> 这是时间序的真实反映，不是"又被挤占"——数量上它只有 3 条，其余 9 条是新闻。

### 2.2.1 配额依据：按「信息价值密度」而非「产生速率」

实测（见 `docs/naja/event_frequency_analysis.md`）：

| 类型 | 产生速率 | 配额 |
|---|---|---|
| `cn_event` | ≈ 14 条/分钟（**批式**：一次扫描 100+ 条） | 2 |
| `us_event` | ≈ 10 条/分钟（内容 100% 是 cn 的子集） | 1 |
| `high_score_news` | ≈ 1.2 条/分钟 | 5 |
| `jin10_news` | ≪ 1 条/分钟 | 4 |

**速率越高 → 配额越小**。因为「取最新 N 条」对秒级/批式事件等价于随机抽样，
对低频新闻才真的等于"最新资讯"。若反过来按速率分配，`cn_event` 该拿 6 个名额——
那正是原 `[:15]` 的病根。

配额外还有一层：同类事件**按标的去重**（`_event_dedup_key`），
保证 2 个 `cn_event` 名额代表 **2 个不同板块**，而不是同一板块的重复刷新。

### 2.2.2 单价噪音治理

```python
NEW_ENTRY_SENTINEL = 999.0   # 源端 change_pct == inf 的编码

def format_change_percent(chg) -> str:
    return "新进榜" if abs(chg) >= NEW_ENTRY_SENTINEL else f"{'+' if chg >= 0 else ''}{chg:.1f}%"
```

`history_tracker.py:693` 把 `inf` 写成 `999`，原样渲染就是菜单上的 `+999.0%`。
托盘、`/market` 页面、文本导出三处**共用**这一个函数，避免各写一份再漂移。

### 2.3 通知聚合限流

修好截断后，单轮可能出现多条达标新闻；若仍逐条弹，会从"从不响"直接变成"轰炸"。

```python
NOTIFY_MIN_INTERVAL = 300.0    # 时间窗：每 5 分钟最多一条通知
NOTIFY_MIN_SCORE    = 0.7      # 分数线（沿用原逻辑）
```

流程：**收集候选 → 时间窗限流 → 相关性优先排序 → 聚合成一条**。

- 候选留在池中（未标已通知），窗口到期后一次性聚合发出——既不"攒着不发"，也不"逐条轰炸"；
- 相关性排前面：复用 `news.focus.build_focus_state()` 的持仓/自选/关注主题关键词，
  **命中的优先**；关键词读不到就返回空集 → 降级为纯分数排序，**绝不阻断通知本身**；
- 多候选聚合文案：`📰 N 条重要新闻` / 副标题=最重要那条 / 正文=`另有 N-1 条 · 点开菜单查看`；
- **板块异动（cn/us event）永不进通知**（哪怕分数很高）。

### 2.4 「一键总结」失效：启动期代理环境卫生

> 典型「代码一点问题没有、坏的是继承来的环境」的静默失效。

**症状**：点「✨ 一键总结当前时间线」立刻弹「❌ 总结失败 / Connection error.」，
`~/.naja/logs/tray.log` 里是 `openai.APIConnectionError: Connection error.`。

**根因**：httpx 堆栈显示请求是**走代理**出去的，而那个代理是
`HTTP_PROXY=http://127.0.0.1:53631` —— 一个随集成终端（IDE / agent shell）
会话生灭、当时**已无人监听**的沙箱代理。链条：

1. 从带沙箱代理的终端执行 `-s start` → 当前环境含这个代理；
2. `__main__` 里 `env = os.environ.copy()` 把它**整块复制**给 Naja 与托盘子进程；
3. `openai` / `httpx` 默认 `trust_env=True`，把它当成唯一出口；
4. 端口已死 → 所有大模型请求 `All connection attempts failed`。

对比：**开机自启（launchd）启动的进程环境是干净的**，所以这条路径一直正常；
只有「从集成终端手动 `-s start`」才会踩到。

**修法**：`daemon.sanitize_proxy_env()` —— 剔除「回环地址 + 端口无人监听」的代理变量。

```python
# 判据很窄：只碰本机回环、且确证端口不通的
for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", ...):
    host, port = _proxy_url_target(env[name])
    if host in {"127.0.0.1", "localhost", "::1"} and port is not None:
        # 连不上 → 剔除 + 留一行 warning；连得上 → 视为真代理，保留
```

- 用户真实的梯度代理（Surge 6152 / Clash 7890 在监听）**一律保留**；
- 非回环代理**不探测、不删**（尊重用户设置）；
- 接入点是**所有启动路径的唯一入口**：`main()` 开头（覆盖 `-s start` 与直接跑服务）
  与 `start_tray.py`（托盘进程不经过 `__main__`）；
- **时序关键**：清洗必须早于 `handle_service_command()` 里的 `os.environ.copy()`，
  否则"清洗了个寂寞"——守卫第 ③ 段专门守这条。

同时让失败提示**自证**：`_summarize_error_hint()` 把连接类错误翻成
「网络/代理不可达，请检查代理是否运行」，401 → API Key 无效，402 → 额度不足。
原来只显示裸的 `Connection error.`，用户完全不知道该看哪里。

---

### 2.5 主线程零阻塞审计（2026-10-13）

代理问题修完后回头问了一句：「菜单里还有会堵塞的同步代码吗」。**有，而且不止一处。**

前提事实：rumps 的**菜单回调**与 `rumps.timer` 回调都跑在 **AppKit 主 runloop** 上，
所以任何 HTTP / 抓取 / 子进程等待都会冻住整条菜单栏（图标不刷、点击无响应）。

审计结论与修法：

| # | 位置 | 阻塞调用 | 症状 | 修法 |
|---|---|---|---|---|
| ① | `_build_menu()`（空缓存分支） | `_get_system_status()` → `GET /api/health`（5s 超时） | 返回值在菜单里**从未被使用**——纯浪费的阻塞 | 删除该取数（连同 `_get_system_status_cached`） |
| ② | `_build_menu()`（空缓存分支） | `_is_trading_time()` → `GET /api/trading/status`（5s 超时、**无缓存**） | 每 30s 一次定时刷新都可能卡 5s | 删除；改用纯 datetime 的 `_is_trading_time_local()` 兜底 |
| ③ | ① ② 都在 `with self._menu_cache_lock` **内** | 持锁做 IO | 连带把后台预加载线程也堵在锁上 | 锁内只留 dict 读写（毫秒级） |
| ④ | `_on_timer` | `_check_naja_ready()` → `GET /api/health`（2s 超时） | 启动期每 5 秒就可能冻 2 秒 | 新增 `_check_naja_listening()`：**纯 TCP 端口探测**，0.3s 封顶 |
| ⑤ | `_on_toggle_autostart` | `toggle_login_item()` → `subprocess.run(["launchctl",…], timeout=5)` + plist 写盘 | 点一下最多冻 5s | 移入后台线程；勾选状态回主线程改 |
| ⑥ | `_on_timer`（总结收尾） | 写文件 / `pbcopy` / 钉钉 / `subprocess.run(["open"])` | 总结完成后主线程串行做四件重活 | 封装 `_finish_summary` 丢后台；主线程只留「弹通知 + `Popen` 打开页面」 |

**有意保留**的唯一主线程阻塞：`_on_quit` 里 SIGTERM 后的等待（最多 10s，超时升级
`SIGKILL`）。不挪走的原因是——托盘进程一退，daemon 线程随之消失，就没人做"超时
升级到 SIGKILL"这一步了，服务可能永远不退出；而它的代价只发生在用户**主动点退出**时
（菜单本就即将消失）。

**关键设计**：主线程只需要"缓存优先、回退纯计算"两条路，任何一条都不允许发请求。
服务端口径（含节假日）随 `/api/tray/data` 进 `_menu_cache['trading']`，由**后台预加载
线程**负责刷新——主线程只管读。

**守卫上的一个坑**：静态守卫会被"解释这个坑"的**注释**本身触发。本次就踩到——
`_build_menu` 里的说明注释写了 `_get_system_status()` 用于标注已删除的取数，
结果守卫把自己判成违约。故守卫扫描前先 `_strip_comment_lines()` 去掉整行注释
（只去整行，不做 inline 剥离，避免误伤字符串字面量）。

### 2.6 长任务状态可见（2026-10-13）

用户反馈：「点击菜单里系统重启时，整个动画和显示不明显，状态无感知」。

追查后确认**不是动画问题，是四态全缺**。`_on_reload → _restart_tray → _do_restart`
的实际耗时结构：

| 阶段 | 代码 | 最坏 |
|---|---|---|
| 等旧服务退出 | `_wait_for_pid_exit(timeout=15)` | 15s |
| 起新进程 | `Popen(… -s start)` | — |
| 等新服务就绪 | `_wait_for_naja_ready(timeout=30)`，每 0.5s 轮询 | 30s |
| 刷新菜单 | `_refresh_after_restart()` | 静默 |

典型 8~15s、最坏 45s，而这期间**菜单栏图标不变、菜单内容不变、通知也没有**——
代码里只有 `_notify_restart_failed` 一条通知路径，**成功分支只写日志**。

#### 载体：菜单栏文字（`app.title`）

rumps 的 `App.title` → `setStatusBarTitle()` → `nsstatusitem.setTitle_()`，与
`setImage_()`（图标）**互不冲突**、可并存。它是唯一「始终可见 + 不受系统勿扰模式
影响 + 可与图标共存」的通道——而全代码里 `_app.title` **一次都没被赋值**。

系统通知仍保留作完成态提醒，但不再作为唯一反馈（会被勿扰吞、`LSUIElement` 应用
不保证显示、闪过即消失）。

#### 状态位机制

```python
self._op_status = {"key": "restart", "label": "🔄 停止旧服务…",
                   "started": ts, "busy": True}
```

| 方法 | 作用 |
|---|---|
| `_begin_op(key, label)` | 占用状态位；返回 `False` = 已有长任务在进行（**互斥**） |
| `_update_op(label)` | 更新阶段文案 |
| `_clear_op(key=None)` | 释放；传 key 时**只清自己的**（不误清别的任务） |
| `_flash_status(label, s)` | 短暂提示（不置 busy、可被覆盖，但**不抢占**长任务） |

互斥是必需的：重启期间再点一次重启会起第二个线程，两个线程同时 kill 同一 PID、
同时 `Popen` 新进程 → 服务状态彻底错乱。

#### 接入范围

| 操作 | 状态文案 | 释放点 |
|---|---|---|
| 🔄 重启服务 | 正在重启 / 停止旧服务 / 启动新服务 / 等待服务就绪 | `try/finally`（异常也释放） |
| 🚪 退出 | 「正在退出…」 | 不释放（进程随即退出） |
| 🚀 登录自启 | 「设置自启…」 | 主线程 `apply` 内 |
| 🔄 刷新菜单 | 「刷新中…」→「已刷新 HH:MM:SS」 | flash 到期自动清 |
| ☁️ 服务器同步 | 「同步中…」 | `finally` |
| ✨ 一键总结 | 「总结中…」（大模型调用可能十几秒） | `_on_timer` 消费结果时 |

未接入的两类：**瞬时操作**（打开页面 / Web / 日志——浏览器弹出即是反馈，加状态
反成噪音）与 **`_check_and_send_notifications`**（它自己就是通知，无需再挂状态）。

#### 三个必须写下来的坑

**① 状态行会谎报。** 重启期间托盘**故意不重启**（避免图标空窗，见 2.2），所以菜单
不会重建，那行 `📊 Naja 运行中 · …` 会一直挂着——而此刻旧服务**其实已经停了**。
用户点开菜单想确认，看到的反而是错的状态。修法：`_op_line(port)` 在有 busy 任务时
返回任务进度，`_build_menu` 走 `if op_line:` 分支。

**② 释放必须走 `finally`。** 状态位卡住会让**后续所有长任务被互斥拒绝**——比不显示
状态更糟。所以重启/同步都用 `try/finally`。

**③ 阻塞前要先渲染。** `_on_quit` 会阻塞主线程最多 10s，而阻塞期间 AppKit 不重绘
——直接设 `app.title` 是画不出来的。所以先用 `_apply_op_status()` 写状态，再用
`threading.Timer(0.4, …)` 推迟进入阻塞：这 0.4s 主线程空闲、runloop 正常跑，
标题才真的画得出来。

> 守卫注意：`_op_line` 的 docstring 里**自然会写到「运行中」这个词**（解释为什么
> 不能写它）。所以「状态行不含运行中」这条**不能扫文本**，要改成**行为断言**
> （有操作时调用 `_op_line`，断言返回值不含该词）——否则又是一次假警报。

---

## 3. 改动清单

| 文件 | 改动 |
|---|---|
| `market_hotspot/ui_components/timeline/market_24h_timeline.py` | 新增 `TRAY_TIMELINE_LIMITS` + `select_timeline_events` + `TRAY_MENU_MAX_EVENTS` + `format_change_percent`；`get_timeline_data_for_api` 增 `per_type_limits` 参数 |
| `infra/ui/menu_bar_tray.py` | `_get_timeline_events` 传配额；`_build_menu` 纯时间倒序 + 结构重构；`_check_and_send_notifications` 聚合限流 + `_relevance_keywords`；新增 `_summarize_error_hint` |
| `web_ui/routes.py` | `TrayDataHandler._fetch_timeline` 传 `per_type_limits=TRAY_TIMELINE_LIMITS` |
| `infra/runtime/daemon.py` | 新增 `sanitize_proxy_env` / `_proxy_url_target`（回环 + 死端口 → 剔除） |
| `__main__.py` | `main()` 开头调用 `sanitize_proxy_env()`（所有启动路径唯一入口） |
| `scripts/start_tray.py` | 启动托盘前调用 `sanitize_proxy_env()`（托盘不经 `__main__`） |
| `tests/test_tray_focus.py`（新） | 23 条：配额/去重/哨兵渲染 15 + 通知 8 |
| `tests/test_proxy_sanitize.py`（新） | 14 条：URL 解析 7 + 清洗行为 5 + 失败提示 2 |
| `scripts/verify/verify_tray_focus.py`（新） | 7 段：配额行为 / 托盘取数口径 / 菜单结构静态守卫 / 频率→配额 / 哨兵渲染 / 通知聚合 / 冷启动 |
| `scripts/verify/verify_proxy_sanitize.py`（新） | 5 段：清洗行为 / 启动接入 / 时序 / 提示自证 / 环境体检 |
| `infra/ui/menu_bar_tray.py`（2.5 主线程审计） | `_build_menu` 去掉 2 处 HTTP 取数、IO 移出锁；删 `_get_system_status` / `_get_system_status_cached` / `_is_trading_time`；新增 `_check_naja_listening`；`_on_timer` 总结收尾封装 `_finish_summary` 丢后台；`_on_toggle_autostart` 移入后台线程；`open` 改非阻塞 `Popen` |
| `tests/test_tray_no_block.py`（新） | 12 条：空缓存零 HTTP / 端口探测 / 各回调静态守卫 |
| `scripts/verify/verify_tray_no_block.py`（新） | 6 段：空缓存零 HTTP / 端口探测 / `_build_menu` 静态守卫 / `_on_timer` + 收尾 / 自启开关 + 死代码 / 冷启动 |
| `infra/ui/menu_bar_tray.py`（2.6 状态可见） | 新增状态位机制 `_begin_op` / `_update_op` / `_clear_op` / `_flash_status` / `_op_line` / `_apply_op_status`；`_do_restart_tray` 拆出包 `try/finally` 并加四态文案 + 成功通知；`_on_quit` 拆出 `_stop_service_and_quit`（先渲染再阻塞）；自启补失败提示；刷新改异步 + 可见反馈；同步/总结接入状态位；`_build_menu` 状态行改用 `_op_line` |
| `tests/test_tray_status.py`（新） | 19 条：状态位机制 8 + 各任务接入与释放 7 + 状态行/退出 3 + 冷启动 1 |
| `scripts/verify/verify_tray_status.py`（新） | 6 段：状态位机制 / 重启四态 + `finally` / 其他长任务接入 / 状态行不谎报 / 退出先渲染 / 冷启动 |

---

## 4. 验证

`scripts/verify/verify_tray_focus.py --strict`（7 段）：

1. **配额行为**：不传配额=旧 `[:15]`；配额后新闻必现；板块异动限流；同类按标的去重；输出仍时间降序；空输入返回空
2. **托盘取数口径**：托盘侧与数据接口都传了配额；无残留 `all_events[:15]`
3. **菜单结构静态守卫**：`/focusadmin` 有入口；「打开日志」不重复；低频页在「系统」子菜单；
   **新闻流仍在一级菜单**（用户硬要求）；列表**按时间倒序**；旧裸数字行/日期分隔行已删
4. **频率与配额匹配**：模块内记录实测速率；板块异动配额显著少于新闻配额
5. **哨兵值渲染**：`change_percent` 的 999 不再打成「+999.0%」
6. **通知聚合**：限流常量存在 + 多候选只发一条 + 板块异动不弹 + 窗口内不重复
7. **冷启动**：托盘与时间线模块可独立导入

单测：`deva/naja/tests/test_tray_focus.py` 23 条。

> 静态守卫必须**限定在 `_build_menu` 内**：`_build_simple_menu()`（启动中的简化菜单）
> 是另一个方法，它有自己的 3 行状态（含 `📍 端口`），不该被菜单守卫误伤——
> 否则会报**假警报**（本项目铁律：假报警比不报警更伤）。

`scripts/verify/verify_proxy_sanitize.py --strict`（5 段）：

1. **清洗行为**：死代理（回环 + 端口不通）剔除；活代理保留；非回环不动；幂等
2. **启动接入**：`main()` 与 `start_tray.py` 都调用 `sanitize_proxy_env()`
3. **时序**：`main()` 内清洗早于 `handle_service_command()`（后者才 `os.environ.copy()`）
4. **失败提示自证**：连接类错误指向网络/代理；401 → API Key
5. **本机环境体检**：当前进程是否带死代理（**环境条件，不计违约**——数据依赖项要能如实跳过）

单测：`deva/naja/tests/test_proxy_sanitize.py` 14 条。

`scripts/verify/verify_tray_no_block.py --strict`（6 段）：

1. **空缓存构建菜单**：spy `_http_get`，构建全过程中 **0 次 HTTP**；降级但菜单照常构建
2. **就绪探测**：活端口 → True；死端口 → False 且耗时 **< 500ms**
3. **`_build_menu` 静态守卫**（按方法块切 + 去注释）：无 `_http_get(` / `_get_system_status` /
   `_is_trading_time(` / `_get_timeline_events(` / `requests.` / `urlopen`
4. **`_on_timer` 静态守卫**：用 `_check_naja_listening()` 而非 HTTP 版；总结收尾
   （写文件/pbcopy/钉钉/生成 HTML）在 `_finish_summary` 后台线程内
5. **自启开关 + 死代码**：`_on_toggle_autostart` 在后台线程、勾选状态回主线程；
   三个 HTTP 版助手已删除、`_is_trading_time_local` 保留
6. **冷启动**：`menu_bar_tray` 可独立导入

单测：`deva/naja/tests/test_tray_no_block.py` 12 条。

`scripts/verify/verify_tray_status.py --strict`（6 段）：

1. **状态位机制**（功能）：占用置 busy 并写 `app.title`；互斥拒绝且不覆盖；阶段文案可更新；
   别的 key 不能清自己的；`flash` 不抢占长任务；释放后恢复为只有图标；`flash` 到点自动清
2. **重启四态 + 保证释放**：四个阶段文案齐全；释放位于 `try/finally`（异常也不会卡住）；
   成功分支有完成通知（原先静默）；失败通知保留
3. **其他长任务接入**：同步（`finally`）/ 一键总结 / 登录自启（含失败提示）/ 刷新菜单
4. **状态行不谎报**：`_build_menu` 走 `if op_line:` 分支；**行为断言**——重启期间菜单里
   出现任务进度、且**不出现「运行中」**
5. **退出先渲染再阻塞**：`_apply_op_status()` 在阻塞前，`threading.Timer(...)` 推迟进入阻塞
6. **冷启动**：`menu_bar_tray` 可独立导入

单测：`deva/naja/tests/test_tray_status.py` 19 条。

---

## 5. 边界与遗留

- 配额是**固定值**，不随"当前有几条新闻"自适应；后续若某类新闻常年为 0，可考虑动态配额。
- `us_event` 的标题是中文 A 股板块名、涨跌幅 ±999%/-100%（源端哨兵值），
  本次**未深挖**——它只影响观感，不影响"新闻能否进列表"这条主线。
- 托盘菜单是原生 macOS 菜单，无法像网页那样截图验收；本轮以
  **静态守卫 + `/api/tray/data` 实测**替代。
- 代理卫生只处理「回环 + 死端口」：若沙箱代理端口**恰好还活着**，环境上就与真代理
  无法区分（这类只能在源头不注入）。实测中确实遇到过活着的沙箱代理
  （`127.0.0.1:63386`，`sandbox-c` 监听且能通），启动清洗会正确地保留它。
- 因此「一键总结」另有一道**兜底重试**：连接失败 → `sanitize_proxy_env()`
  （返回非空 = 确实剔掉了死代理）→ 重试一次。覆盖「启动时代理还活着、之后才死」
  这个启动期清洗够不到的场景。其余 LLM 调用路径**暂未加兜底**（本轮只覆盖用户诉求路径）。
- 主线程阻塞审计后，剩下的同步调用都只剩**毫秒级**（`webbrowser.open`、`Popen` 起
  子进程），以及 `_on_quit` 那处**有意保留**的等待（见 2.5）。
- `_relevance_keywords()` → `build_focus_state()` 仍在主线程被调用，但它自带
  60s TTL（外加 5min 关键词缓存）、只读内存/本地焦点快照，且失败降级为空集
  **绝不阻断通知** —— 属可接受量级，未动。
- **状态位只在菜单栏文字上呈现，没有进度百分比**：重启的分阶段文案（停止旧服务 →
  启动新服务 → 等待服务就绪）是**离散四态**，不是 `30%` 这种连续进度——因为
  `_wait_for_naja_ready` 的剩余时间不可预估，报百分比反而会误导。
- **托盘图标仍是两态**（交易中 / 休市），本轮**未加**「重启中」第三态：用户选了
  以菜单栏文字为优先载体。若后续要加，注意 `ICON_GREEN` 常量实际指向
  `naja_tray_red_22.png`（**变量名与文件语义不符**，改前先重命名）。
- **互斥是按"同一时刻一个长任务"设计的**：若将来出现"可并行的两个长任务"，需要把
  `_op_status` 从单槽改为多槽（或引入优先级），当前不做——现有六个长任务本就互斥。
- 托盘菜单是原生 macOS 菜单，状态呈现无法像网页那样截图验收；本轮以
  **守卫的行为断言（`_op_line` / `_build_menu` 实际产出）+ 落盘日志**替代。

