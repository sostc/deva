存储（DBStream）
=================

概述
----

`DBStream` 提供了“流 + SQLite 持久化”一体化能力，适合保存配置、任务状态、以及可回放的事件流。

核心能力
--------

- 字典式读写：`db[key] = value`、`db[key]`
- 流式写入：`x >> db`
- 时间切片：`db[start:end]`
- 回放：`db.replay(start=..., end=..., interval=...)`
- 容量控制：`maxsize`

键模式（key_mode）
------------------

`DBStream(..., key_mode=...)` 支持两种模式：

- `explicit`（默认）

  - `dict` 输入视为批量 upsert（兼容旧行为）
  - 适合配置数据、任务状态等 KV 存储

- `time`

  - 适合事件流存储
  - 推荐使用 `append(value)` 写入事件
  - `dict` 输入默认拒绝（`time_dict_policy='reject'`），避免误把字段当 key

新 API
------

- `append(value, key=None)`：按时间键追加一条事件（可选自定义 key）
- `upsert(key, value)`：按显式键写入/覆盖
- `bulk_update(mapping)`：批量更新

示例
----

.. code-block:: python

   from deva import NB

   # 事件流模式
   events = NB('signals', key_mode='time')
   events.append({'symbol': '600519.SH', 'score': 0.92})

   # 显式键模式（默认）
   config = NB('config')
   config.upsert('risk.max_position', 0.2)

容量控制与淘汰
--------------

当设置 `maxsize` 时，`DBStream` 会优先按时间键淘汰最旧记录；
如果没有时间键，则按确定性顺序淘汰，避免随机行为。

注意事项
--------

- 事件流建议使用 `key_mode='time'` + `append()`
- 配置类表建议保持默认 `key_mode='explicit'`
- 回放基于时间键，非时间键会自动忽略


Redis 流（Bus/Topic）
=====================

`RedisStream/Topic/to_redis` 在 P0/P1 中完成了以下增强：

- Redis 客户端优先 `redis.asyncio`，回退 `aioredis`
- `db/max_len/read_count/block_ms/start_id` 参数可配置且实际生效
- 支持消费者组读取（`XREADGROUP + XACK`）与非组读取（`XREAD`）
- 发送与读取增加重试和退避，避免短暂网络抖动直接中断

示例：

.. code-block:: python

   from deva import Stream
   from deva.topic import Topic

   # 可靠消费（消费者组）
   orders = Topic("orders", group="risk-engine", max_len=5000, db=0)

   # 仅追踪新消息（非消费者组）
   live = Stream.RedisStream(
       topic="quotes",
       group=None,
       start_id="$",
       block_ms=300,
       read_count=100,
       max_len=20000,
   )
