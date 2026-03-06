import os
import tempfile
import unittest

from deva.naja.signal.stream import SignalStream
from deva.naja.strategy.result_store import StrategyResult


class TestSignalStream(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db_path = os.environ.get("DEVA_DB_PATH")
        os.environ["DEVA_DB_PATH"] = os.path.join(self.tmp.name, "signal_stream.sqlite")
        SignalStream._instance = None

    def tearDown(self):
        stream = SignalStream._instance
        if stream is not None:
            stream.clear()
            stream.close(persist=False)
        SignalStream._instance = None

        if self.old_db_path is None:
            os.environ.pop("DEVA_DB_PATH", None)
        else:
            os.environ["DEVA_DB_PATH"] = self.old_db_path
        self.tmp.cleanup()

    def _result(self, idx: int) -> StrategyResult:
        return StrategyResult(
            id=f"r{idx}",
            strategy_id="s1",
            strategy_name="demo",
            ts=float(idx),
            success=True,
            output_preview=f"result-{idx}",
        )

    def test_update_only_writes_stream_cache(self):
        stream = SignalStream(max_cache_size=2, persist_name="signal_stream_test_cache")

        stream.update(self._result(1))

        self.assertTrue(stream.is_cache)
        self.assertEqual([item.id for item in stream.get_recent(limit=5)], ["r1"])
        self.assertEqual(list(stream.db.keys()), [])

    def test_persist_keeps_only_fixed_cache_and_reloads(self):
        persist_name = "signal_stream_test_persist"
        stream = SignalStream(max_cache_size=2, persist_name=persist_name)

        stream.update(self._result(1))
        stream.update(self._result(2))
        stream.update(self._result(3))
        stream.persist()

        recent_signals = stream.db.get("recentSignal")
        persisted = [item["id"] for item in recent_signals]
        self.assertEqual(sorted(persisted), ["r2", "r3"])

        stream.close(persist=False)
        SignalStream._instance = None
        reloaded = SignalStream(max_cache_size=2, persist_name=persist_name)

        self.assertEqual([item.id for item in reloaded.get_recent(limit=5)], ["r3", "r2"])


if __name__ == "__main__":
    unittest.main()
