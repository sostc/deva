import os
import tempfile
import time
import unittest
from pathlib import Path

from deva.bus import FileIpcBusBackend, LocalBusBackend


class TestBusBackends(unittest.TestCase):
    def test_local_backend_builds_stream(self):
        backend = LocalBusBackend()
        stream = backend.build_stream("test_local_bus_backend")
        self.assertIsNotNone(stream)
        self.assertTrue(hasattr(stream, "emit"))

    def test_file_ipc_backend_publish_and_tail(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "bus.log")
            backend = FileIpcBusBackend(file_path=path)
            stream = backend.build_stream("test_file_ipc_bus")
            out = []
            stream.sink(out.append)
            backend.publish(stream, {"sender": "t", "message": "hello", "ts": time.time()})
            deadline = time.time() + 2
            while time.time() < deadline and not out:
                time.sleep(0.05)
            backend.stop()
            self.assertTrue(out, "file-ipc backend should emit published message via tail loop")

    def test_new_bus_module_removed(self):
        root = Path(__file__).resolve().parents[1]
        self.assertFalse((root / "deva/new_bus.py").exists())


if __name__ == "__main__":
    unittest.main()
