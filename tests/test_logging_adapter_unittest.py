import logging
import unittest

from deva.core import format_line, normalize_record, setup_deva_logging


class TestLoggingAdapter(unittest.TestCase):
    def test_normalize_and_format(self):
        record = normalize_record(
            {"level": "warning", "source": "deva.test", "message": "hello", "k": 1},
            default_level="INFO",
            default_source="deva",
        )
        line = format_line(record)
        self.assertIn("[WARNING][deva.test] hello", line)
        self.assertIn('"k":1', line)

    def test_setup_installs_handlers(self):
        logger = setup_deva_logging()
        self.assertEqual(logger.name, "deva")
        self.assertTrue(logger.handlers)
        self.assertFalse(logger.propagate)
        self.assertTrue(logging.getLogger("sqlitedict").handlers)
        self.assertTrue(logging.getLogger("simhash").handlers)


if __name__ == "__main__":
    unittest.main()
