"""验证 core/sources.py 的 HTTP 编解码。

重要发现：改动前的实现引用 `P.map`，而 `deva.core.pipe` 里**并不存在**
`map` 这个名字（`P` 是 Pipe 实例，只有 `__ror__`/`__rrshift__`）。因此
`_decode_http_body` / `_encode_http_body` 一旦被调用必然 `AttributeError`
—— 即 from_http_request / TCPStream 的请求体编解码路径此前是死的。
本脚本先固化这一事实，再验证新实现返回正确语义。

跑法：
    env -i HOME="$HOME" USER="$USER" PATH=/usr/bin:/bin:/usr/sbin:/sbin \
        TMPDIR="$TMPDIR" python3.13 scripts/verify/verify_sources_http_codec.py
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

import json  # noqa: E402

import dill  # noqa: E402
import pandas as pd  # noqa: E402

from deva.core.sources import _decode_http_body, _encode_http_body  # noqa: E402


def main():
    # ── 0) 固化既有 bug：旧实现的 `P.map` 不存在 ────────────────────
    from deva.core.pipe import P
    assert not hasattr(P, "map"), "若 P.map 出现，说明 pipe 模块变了，需重新评估"
    try:
        P.map(lambda x: x)
        raise SystemExit("预期 AttributeError 未发生")
    except AttributeError:
        pass
    print("0) 旧实现 P.map 缺失 → 原编解码路径必然 AttributeError（已确认）")

    # ── 1) decode：显式语义校验 ───────────────────────────────────
    df_src_ok = b'{"a": [1, 2], "b": [3, 4]}'
    dill_none = dill.dumps(None)
    cases = [
        ("json dict", b'{"a": 1, "b": [2, 3]}', False, {"a": 1, "b": [2, 3]}),
        ("json list", b'[1, 2, 3]', False, [1, 2, 3]),
        ("json number", b'123', False, 123),
        ("plain text", b'hello world', False, "hello world"),
        ("non-utf8", b'\xff\xfe\x00\x01', False, b'\xff\xfe\x00\x01'),
        ("empty", b'', False, ""),
        ("dill list", dill.dumps([1, 2, 3]), False, [1, 2, 3]),
        ("dill dict", dill.dumps({"k": "v"}), False, {"k": "v"}),
        ("dill None→原始字节", dill_none, False, dill_none),
        ("dill bytes", dill.dumps(b"raw-bytes"), False, b"raw-bytes"),
        ("str 输入", '{"x": 9}', False, {"x": 9}),
    ]
    for name, body, as_df, exp in cases:
        got = _decode_http_body(body, as_dataframe=as_df)
        assert type(got) is type(exp) and got == exp, \
            f"decode [{name}]: got={got!r}({type(got).__name__}) exp={exp!r}({type(exp).__name__})"
    print(f"1) decode 语义 OK（{len(cases)} 例）")

    # dataframe 分支
    got_df = _decode_http_body(df_src_ok, as_dataframe=True)
    assert isinstance(got_df, pd.DataFrame), type(got_df)
    assert got_df.equals(pd.DataFrame({"a": [1, 2], "b": [3, 4]})), got_df
    got_fail = _decode_http_body(b'hello', as_dataframe=True)
    assert got_fail == "hello", got_fail
    print("2) decode as_dataframe 分支 OK")

    # ── 3) encode：显式语义校验 ───────────────────────────────────
    enc_cases = [
        ({"a": 1}, '{"a": 1}'),
        ([1, 2, 3], '[1, 2, 3]'),
        ("text", '"text"'),
        (42, '42'),
        (None, 'null'),
        (True, 'true'),
        ({"中文": "值"}, '{"中文": "值"}'),
    ]
    for body, exp in enc_cases:
        got = _encode_http_body(body)
        assert got == exp, f"encode {body!r}: got={got!r} exp={exp!r}"
    print(f"3) encode 语义 OK（{len(enc_cases)} 例）")

    df = pd.DataFrame({"a": range(30), "b": range(30)})
    enc = _encode_http_body(df)
    assert isinstance(enc, str)
    html = json.loads(enc)
    assert html.startswith("<table") and html.rstrip().endswith("</table>"), html[:60]
    print("4) encode DataFrame → JSON 包裹 HTML 表 OK")

    # ── 5) 性能：单次调用开销（无 Pipe 链/闭包重建） ────────────────
    body = b'{"a": 1, "b": [2, 3, 4]}'
    N = 20000
    t = time.perf_counter()
    for _ in range(N):
        _decode_http_body(body)
    t_new = time.perf_counter() - t
    print(f"5) decode {N} 次耗时 = {t_new:.4f}s（{t_new / N * 1e6:.2f} µs/次）")

    # ── 6) sources 内另一处 P.map 死路径：from_textfile._fetch_data ──
    from deva.core.sources import from_textfile

    class _FakeFile:
        def __init__(self, chunks):
            self._chunks = list(chunks)

        def read(self):
            return self._chunks.pop(0) if self._chunks else ""

    tf = from_textfile(_FakeFile(["L1\nL2\n", "L3\nL4\n"]))
    assert tf._fetch_data() == ["L1\n", "L2\n"]
    assert tf._fetch_data() == ["L3\n", "L4\n"]
    assert tf._fetch_data() == []
    print("6) from_textfile._fetch_data（原 P.map 死路径）已修复并正确补回分隔符 OK")

    print("\nALL PASS")


if __name__ == "__main__":
    main()
