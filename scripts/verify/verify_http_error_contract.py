"""回归：HTTP 层的错误传播契约（P2 #14）。

契约：
  * httpx() 成功返回 response；失败默认抛 HttpError
    （带 request / cause / status_code / timestamp）；
  * 只有显式传 raise_on_error=False 才退回 None（宽容模式）；
  * crawler 流的失败**不下发**下游，而是结构化后路由到 error 回调。

注意：本机有 HTTP 代理，连不上的地址可能直接返回 502 而不是抛异常，
所以这里用桩对象注入，保证用例是确定性的。

用法：python3 scripts/verify/verify_http_error_contract.py
"""
import time

from tornado import gen
from tornado.ioloop import IOLoop

import deva
from deva.core import http_stream as H


class _BoomSession:
    """get() 直接抛异常的假 session。"""

    def __init__(self, exc):
        self.exc = exc

    def get(self, *args, **kwargs):
        raise self.exc


@gen.coroutine
def _runner():
    out = {}

    # --- 1) 严格模式：失败抛 HttpError，而不是静默返回 None ---
    H._global_httpclient = _BoomSession(ConnectionError("boom"))
    try:
        yield H.httpx("http://example.com", timeout=1)
        out["strict"] = "NO_RAISE"
    except H.HttpError as e:
        out["strict"] = ("HttpError", e.to_dict())
    except Exception as e:  # pragma: no cover
        out["strict"] = ("OTHER", repr(e))

    # --- 2) 宽容模式：显式要求才返回 None ---
    H._global_httpclient = _BoomSession(ConnectionError("boom"))
    out["lenient"] = yield H.httpx(
        "http://example.com", timeout=1, raise_on_error=False)

    # --- 3) 非法入参：包成 HttpError，cause 仍是原始 TypeError ---
    H._global_httpclient = _BoomSession(ConnectionError("boom"))
    try:
        yield H.httpx(123, timeout=1)
        out["bad_type"] = "NO_RAISE"
    except H.HttpError as e:
        out["bad_type"] = (type(e.cause).__name__, str(e.cause))
    except Exception as e:  # pragma: no cover
        out["bad_type"] = ("OTHER", repr(e))

    # --- 4) crawler 流：失败进 error 回调，下游收不到 None ---
    seen, errs = [], []
    s = H.crawler(render=False, workers=2, error=errs.append)
    s.map(lambda r: seen.append(r))
    H._global_httpclient = _BoomSession(ConnectionError("boom"))
    s.emit("http://example.com")
    yield gen.sleep(2)
    out["downstream"] = seen
    out["errors"] = errs

    return out


def main():
    result = {}
    assert deva.Stream is not None  # deva 导入即初始化事件循环
    loop = IOLoop.current()

    @gen.coroutine
    def go():
        try:
            result['out'] = yield _runner()
        except Exception as e:  # pragma: no cover
            result['out'] = {'error': repr(e)}
        finally:
            result['done'] = True

    loop.add_callback(go)

    deadline = time.time() + 60
    while not result.get('done') and time.time() < deadline:
        time.sleep(0.05)

    out = result.get('out') or {}
    if 'error' in out:
        raise SystemExit('FAIL: ' + out['error'])

    strict = out.get("strict")
    assert isinstance(strict, tuple) and strict[0] == "HttpError", strict
    err = strict[1]
    for key in ("request", "error", "status_code", "timestamp"):
        assert key in err, f"HttpError.to_dict() 缺少字段 {key}: {err}"
    assert err["request"] == "http://example.com", err

    assert out.get("lenient") is None, out.get("lenient")
    assert out["bad_type"][0] == "TypeError", out["bad_type"]
    assert out["downstream"] == [], out["downstream"]
    assert len(out["errors"]) == 1, out["errors"]
    got = out["errors"][0]
    assert isinstance(got, dict), got
    assert got["request"] == "http://example.com", got
    assert "error" in got and "timestamp" in got, got

    print("1) httpx 严格模式抛 HttpError        OK -> request=%r cause=%s"
          % (err["request"], type(strict[1]).__name__))
    print("2) HttpError.to_dict 字段完整         OK ->", sorted(err.keys()))
    print("3) 宽容模式仅在 raise_on_error=False 返回 None  OK")
    print("4) 非法入参不再被吞掉                 OK ->", out["bad_type"][1])
    print("5) crawler 失败进 error 回调          OK ->", sorted(got.keys()))
    print("6) crawler 下游未收到 None            OK")
    print("ALL PASS")


if __name__ == "__main__":
    main()
