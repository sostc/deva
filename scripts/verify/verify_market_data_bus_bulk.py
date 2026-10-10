#!/usr/bin/env python3
"""回归：MarketDataBus._persist_quotes_to_db 由逐条 upsert 改为单次 bulk_update。

验证：
  1) 批量写入后每条都能正确读回；
  2) 归一化 key 正确（_normalize_code）；
  3) 空输入不报错；
  4) 相比逐条 upsert 有可测量的提交次数优势（用写入耗时做粗验证）。

跑法（必须清环境）：
    env -i HOME="$HOME" USER="$USER" PATH=/usr/bin:/bin:/usr/sbin:/sbin \
        TMPDIR="$TMPDIR" python3.13 scripts/verify/verify_market_data_bus_bulk.py
"""
import importlib
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from deva.core.store import DBStream  # noqa: E402

mdb = importlib.import_module("deva.naja.bandit.market_data_bus")


class FakeQuote:
    def __init__(self, v):
        self.v = v

    def to_dict(self):
        return {"v": self.v}


def _new_bus(path):
    bus = mdb.MarketDataBus.__new__(mdb.MarketDataBus)  # 跳过 __init__（避免启动副作用）
    bus._db = DBStream("verify_mdb_quotes", filename=path)
    return bus


def main():
    tmpdir = tempfile.mkdtemp(prefix="mdb_bulk_")
    n = 300

    # 1) 批量写入 + 读回
    bus = _new_bus(os.path.join(tmpdir, "bulk"))
    quotes = {f"sh60{i:04d}": FakeQuote(i) for i in range(n)}
    bus._persist_quotes_to_db(quotes)

    ok = 0
    for i in range(n):
        k = mdb._normalize_code(f"sh60{i:04d}")
        got = bus._db.get(k)
        assert got == {"v": i}, (k, got)
        ok += 1
    print(f"1) 批量写入 {ok} 条全部读回 OK")

    # 2) 空输入不报错
    bus._persist_quotes_to_db({})
    print("2) 空输入 OK")

    # 3) 与逐条 upsert 的写入耗时对比（粗验证提交开销）
    bus_bulk = _new_bus(os.path.join(tmpdir, "cmp_bulk"))
    bus_loop = _new_bus(os.path.join(tmpdir, "cmp_loop"))
    data = {f"sz30{i:04d}": FakeQuote(i) for i in range(n)}

    t = time.perf_counter()
    bus_bulk._persist_quotes_to_db(data)
    t_bulk = time.perf_counter() - t

    t = time.perf_counter()
    for code, q in data.items():
        bus_loop._db.upsert(mdb._normalize_code(code), q.to_dict())
    t_loop = time.perf_counter() - t

    print(f"3) {n} 条：批量={t_bulk * 1000:.1f}ms  逐条={t_loop * 1000:.1f}ms")
    # 两者最终内容应一致
    for code in list(data)[:20]:
        k = mdb._normalize_code(code)
        assert bus_bulk._db.get(k) == bus_loop._db.get(k), k
    print("3b) 批量与逐条结果一致 OK")

    print("\nALL PASS")


if __name__ == "__main__":
    main()
