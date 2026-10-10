import os
import sys
import tempfile

os.environ["DEVA_DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="naja_core_test_"), "nb.sqlite")
sys.path.insert(0, "/Users/spark/pycharmproject/deva")

from deva.core import Stream, NS, NT
from deva import NB
from deva.core.namespace import _CONSTRUCTORS

# 1) sink：无参函数 / 带参函数 都要正确
out_noarg = []
out_onearg = []
src = Stream()
def on_noarg():
    out_noarg.append(1)
def on_onearg(x):
    out_onearg.append(x)
src.sink(on_noarg)
src.sink(on_onearg)
src.emit(1)
src.emit(2)
assert out_noarg == [1, 1], out_noarg
assert out_onearg == [1, 2], out_onearg
print("sink no-arg / one-arg OK:", out_noarg, out_onearg)

# 2) sink 的 Stream kwargs 仍被识别（如 name=）
src2 = Stream()
seen = []
src2.sink(seen.append, name="my_sink")
src2.emit("a")
assert seen == ["a"], seen
assert src2.downstreams and list(src2.downstreams)[0].name is not None
print("sink stream-kwargs OK")

# 3) 链路投递仍正确（map -> sink），覆盖 _emit 路径
s3 = Stream()
got = []
s3.map(lambda x: x * 2).sink(got.append)
s3.emit(1)
s3.emit(2)
assert got == [2, 4], got
print("chain map->sink OK:", got)

# 4) 命名空间：缓存、未知类型报错
assert NS("s1") is NS("s1")
assert NB("t1") is NB("t1")
assert NT("tp1") is NT("tp1")
try:
    from deva.core.namespace import global_namespace
    global_namespace.create(name="x", typ="data")
    raise SystemExit("should have raised")
except ValueError as e:
    assert "Unsupported" in str(e), e
print("namespace cache + error OK; constructors =", sorted(_CONSTRUCTORS))

print("ALL PASS")
