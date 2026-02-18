import unittest
from unittest.mock import patch

import dill
from tornado.ioloop import IOLoop

from deva.core import Stream
from deva.endpoints import to_redis
from deva.sources import RedisStream


class _FakeRedis:
    def __init__(self):
        self.xadd_calls = []
        self.xack_calls = []
        self.xgroup_create_calls = []
        self.xreadgroup_calls = 0
        self.xread_calls = 0
        self.owner = None

    async def xadd(self, topic, fields, maxlen=None, approximate=None):
        self.xadd_calls.append({
            "topic": topic,
            "fields": fields,
            "maxlen": maxlen,
            "approximate": approximate,
        })
        return "1-0"

    async def xgroup_create(self, topic, group, id='0-0', mkstream=True):
        self.xgroup_create_calls.append((topic, group, id, mkstream))
        return True

    async def xreadgroup(self, groupname, consumername, streams, count=10, block=500):
        self.xreadgroup_calls += 1
        if self.xreadgroup_calls == 1:
            if self.owner is not None:
                self.owner.stopped = True
            return [
                (b"topic", [(b"1-0", {b"data": dill.dumps("hello")})]),
            ]
        return []

    async def xread(self, streams, count=10, block=500):
        self.xread_calls += 1
        if self.xread_calls == 1:
            if self.owner is not None:
                self.owner.stopped = True
            return [
                (b"topic", [(b"2-0", {b"data": dill.dumps("world")})]),
            ]
        return []

    async def xack(self, topic, group, msg_id):
        self.xack_calls.append((topic, group, msg_id))
        return 1

    async def aclose(self):
        return None


class TestRedisStream(unittest.TestCase):
    def setUp(self):
        self.loop = IOLoop()

    def tearDown(self):
        self.loop.close()

    def test_send_respects_max_len_and_db(self):
        fake = _FakeRedis()
        with patch("deva.sources._new_redis_client", return_value=fake) as new_client:
            stream = RedisStream(topic="t", start=False, db=7, max_len=123)
            stream.loop = self.loop
            self.loop.run_sync(lambda: stream._send({"x": 1}))
            args = new_client.call_args.kwargs
            self.assertEqual(args["db"], 7)
            self.assertEqual(fake.xadd_calls[-1]["maxlen"], 123)

    def test_group_mode_reads_and_acks(self):
        fake = _FakeRedis()
        with patch("deva.sources._new_redis_client", return_value=fake):
            stream = RedisStream(topic="t", start=False, group="g1", retries=0)
            stream.loop = self.loop
            stream.stopped = False
            fake.owner = stream
            out = []
            stream.sink(out.append)
            self.loop.run_sync(stream.process)
            self.assertEqual(out, ["hello"])
            self.assertEqual(fake.xreadgroup_calls, 1)
            self.assertEqual(len(fake.xack_calls), 1)

    def test_non_group_mode_reads_with_last_id(self):
        fake = _FakeRedis()
        with patch("deva.sources._new_redis_client", return_value=fake):
            stream = RedisStream(topic="t", start=False, group=None, retries=0, start_id="0-0")
            stream.loop = self.loop
            stream.stopped = False
            fake.owner = stream
            out = []
            stream.sink(out.append)
            self.loop.run_sync(stream.process)
            self.assertEqual(out, ["world"])
            self.assertEqual(fake.xread_calls, 1)
            self.assertEqual(fake.xack_calls, [])
            self.assertEqual(stream._last_id, b"2-0")

    def test_emit_returns_future(self):
        stream = RedisStream(topic="t", start=False)
        stream.loop = self.loop

        async def ok(_):
            return "9-0"

        stream._send = ok
        fut = stream.emit("x")
        msg_id = self.loop.run_sync(lambda: fut)
        self.assertEqual(msg_id, "9-0")

    def test_stop_safe_without_connection(self):
        stream = RedisStream(topic="t", start=False)
        stream.stop()
        self.assertTrue(stream.stopped)

    def test_to_redis_passes_redis_kwargs(self):
        captured = {}

        class DummyRedisStream(Stream):
            def __init__(self, **kwargs):
                captured.update(kwargs)
                super().__init__(ensure_io_loop=True)

        with patch("deva.endpoints.RedisStream", DummyRedisStream):
            to_redis(topic="ticks", max_len=777, address="127.0.0.1", db=9)
            self.assertEqual(captured["topic"], "ticks")
            self.assertEqual(captured["max_len"], 777)
            self.assertEqual(captured["address"], "127.0.0.1")
            self.assertEqual(captured["db"], 9)


if __name__ == "__main__":
    unittest.main()
