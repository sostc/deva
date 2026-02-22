import unittest
import importlib.util
from pathlib import Path


_MODULE_PATH = Path(__file__).resolve().parents[1] / "deva" / "llm" / "config_utils.py"
_SPEC = importlib.util.spec_from_file_location("deva_llm_config_utils", _MODULE_PATH)
_MOD = importlib.util.module_from_spec(_SPEC)
assert _SPEC and _SPEC.loader
_SPEC.loader.exec_module(_MOD)

build_model_config_example = _MOD.build_model_config_example
get_model_config_status = _MOD.get_model_config_status


class _FakeConfig(dict):
    pass


class TestLlmConfigUtils(unittest.TestCase):
    def test_status_detects_missing_and_blank_values(self):
        store = {
            "kimi": _FakeConfig(
                {
                    "api_key": "",
                    "base_url": "https://api.moonshot.cn/v1",
                }
            )
        }

        def NB(name):
            return store.setdefault(name, _FakeConfig())

        status = get_model_config_status(NB, "kimi")
        self.assertFalse(status["ready"])
        self.assertEqual(status["missing"], ["api_key", "model"])

    def test_example_uses_model_specific_hints(self):
        example = build_model_config_example("deepseek", ["base_url", "model"])
        self.assertIn("https://api.deepseek.com/v1", example)
        self.assertIn("deepseek-chat", example)


if __name__ == "__main__":
    unittest.main()
