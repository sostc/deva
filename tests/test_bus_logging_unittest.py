import unittest
import os

from deva.bus import _format_log_line, _normalize_log_record, _should_emit_level, _warn_sink, _debug_sink, log


class TestBusLogging(unittest.TestCase):
    def test_normalize_string_record(self):
        rec = _normalize_log_record("hello")
        self.assertEqual(rec["level"], "INFO")
        self.assertEqual(rec["message"], "hello")
        self.assertEqual(rec["source"], "deva")

    def test_normalize_dict_record(self):
        rec = _normalize_log_record({
            "level": "warning",
            "source": "crawler",
            "message": "timeout",
            "url": "https://example.com",
        })
        self.assertEqual(rec["level"], "WARNING")
        self.assertEqual(rec["source"], "crawler")
        self.assertEqual(rec["message"], "timeout")
        self.assertIn("url", rec["extra"])

    def test_format_log_line_contains_main_fields(self):
        rec = {
            "ts": "2026-01-01 10:00:00",
            "level": "INFO",
            "source": "deva",
            "message": "ok",
            "extra": {"k": "v"},
        }
        line = _format_log_line(rec)
        self.assertIn("[2026-01-01 10:00:00][INFO][deva] ok", line)
        self.assertIn('"k":"v"', line)

    def test_level_filtering(self):
        old = os.environ.get("DEVA_LOG_LEVEL")
        try:
            os.environ["DEVA_LOG_LEVEL"] = "WARNING"
            self.assertFalse(_should_emit_level("INFO"))
            self.assertFalse(_should_emit_level("DEBUG"))
            self.assertTrue(_should_emit_level("WARNING"))
            self.assertTrue(_should_emit_level("ERROR"))
        finally:
            if old is None:
                os.environ.pop("DEVA_LOG_LEVEL", None)
            else:
                os.environ["DEVA_LOG_LEVEL"] = old

    def test_warn_and_debug_sink_attach_default_level(self):
        captured = []
        old_emit = log.emit
        log.emit = lambda payload, asynchronous=False: captured.append(payload)
        try:
            _warn_sink("warn-msg")
            _debug_sink("dbg-msg")
        finally:
            log.emit = old_emit
        self.assertEqual(captured[0]["level"], "WARNING")
        self.assertEqual(captured[0]["source"], "deva.warn")
        self.assertEqual(captured[1]["level"], "DEBUG")
        self.assertEqual(captured[1]["source"], "deva.debug")


if __name__ == "__main__":
    unittest.main()
