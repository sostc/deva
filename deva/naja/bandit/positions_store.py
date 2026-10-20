"""统一持仓表（``naja_bandit_positions`` 的 ``accounts`` 键）的写锁。

## 为什么需要它

``VirtualPortfolio`` 和 ``PortfolioManager`` 下的每个账户，``_save_positions``
都是同一种形状：

    读 accounts  →  改自己那一格  →  整个 accounts 写回

单账户串行时没问题，但两个**不同实例**并发时会出现：

    A 读（含 B 的旧值）→ B 读（含 A 的旧值）→ A 写 → B 写
                                                  ↑ A 的更新被 B 的旧快照覆盖

表现出来就是「持仓现价莫名回退到上一次的值」，而且没有任何报错 ——
典型的静默丢更新，排查时看不出是谁覆盖的。

价格供给器（``portfolio_price_feed``）接上以后，写频率从「偶尔」涨到
「每 30s 若干次」，而且同一轮里会先后写虚拟仓和本地记账账户，这个窗口
必须关上。

## 用法

::

    from .positions_store import POSITIONS_WRITE_LOCK

    with POSITIONS_WRITE_LOCK:
        accounts = self._db.get("accounts", {})
        ...
        self._db["accounts"] = accounts

锁是模块级、进程内共享的 —— 所有写 ``accounts`` 的地方都必须用它，
否则等于没加。
"""

from __future__ import annotations

import threading

#: 保护 ``naja_bandit_positions`` 里 ``accounts`` 这一格的读-改-写。
#: 用 ``RLock``：同一个线程可能在一轮里连续保存多个账户。
POSITIONS_WRITE_LOCK = threading.RLock()
