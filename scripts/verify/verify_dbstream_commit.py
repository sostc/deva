import os
import sys
import time
import tempfile

sys.path.insert(0, "/Users/spark/pycharmproject/deva")

from deva.core.store import DBStream

tmpdir = tempfile.mkdtemp(prefix="dbstream_test_")
path = os.path.join(tmpdir, "t")

print("WRITE_COMMIT_BLOCKING =", DBStream.WRITE_COMMIT_BLOCKING)

db = DBStream("tbl", filename=path)

# 1) append 若干条
keys = []
for i in range(5):
    keys.append(db.append({"i": i}))

# 2) upsert + bulk_update
db.upsert("k1", {"v": 1})
db.bulk_update({"k2": {"v": 2}, "k3": {"v": 3}})

# 3) 立即读回（验证 FIFO 顺序：读一定发生在上述 commit 之后）
assert db.get(keys[0]) == {"i": 0}, db.get(keys[0])
assert db.get(keys[4]) == {"i": 4}, db.get(keys[4])
assert db.get("k1") == {"v": 1}, db.get("k1")
assert db.get("k2") == {"v": 2}, db.get("k2")
assert db.get("k3") == {"v": 3}, db.get("k3")
print("read-back OK, len =", len(db))

# 4) persist 后跨新连接读取（验证确实落盘）
db.persist()
db2 = DBStream("tbl", filename=path)
assert db2.get("k1") == {"v": 1}, db2.get("k1")
assert len(db2) == 8, len(db2)
print("persist + reopen OK, len =", len(db2))

# 5) 删除路径
del db["k3"]
assert "k3" not in db
print("delete OK")

# 6) maxsize 路径（覆盖 _check_size_limit）
db3 = DBStream("capped", filename=os.path.join(tmpdir, "c"), maxsize=3)
for i in range(6):
    db3.append({"i": i}, key=float(1000 + i))
n = len(db3)
print("maxsize eviction -> len =", n)
assert n <= 3, n

# 7) persist 阻塞提交仍可用（DBStream 无 close，需经底层 SqliteDict 关闭）
db3.persist()
db3.db.close()
db.persist()
db.db.close()
db2.db.close()
print("ALL PASS")
