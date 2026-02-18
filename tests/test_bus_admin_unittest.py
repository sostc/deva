import unittest
from pathlib import Path

from deva.bus import get_bus_runtime_status, get_bus_clients, get_bus_recent_messages


ROOT = Path(__file__).resolve().parents[1]


class TestBusAdminIntegration(unittest.TestCase):
    def test_bus_runtime_status_has_core_fields(self):
        status = get_bus_runtime_status()
        for key in ["mode", "topic", "connected", "type", "redis_ready"]:
            self.assertIn(key, status)

    def test_bus_management_helpers_return_collections(self):
        self.assertIsInstance(get_bus_clients(), list)
        self.assertIsInstance(get_bus_recent_messages(5), list)

    def test_main_ui_context_exposes_bus_status_function(self):
        source = (ROOT / "deva/admin_parts/contexts.py").read_text(encoding="utf-8")
        self.assertIn("'get_bus_runtime_status': ns['get_bus_runtime_status']", source)
        self.assertIn("'get_bus_clients': ns['get_bus_clients']", source)
        self.assertIn("'get_bus_recent_messages': ns['get_bus_recent_messages']", source)
        self.assertIn("'send_bus_message': ns['send_bus_message']", source)

    def test_nav_contains_busadmin_entry(self):
        source = (ROOT / "deva/admin_parts/main_ui.py").read_text(encoding="utf-8")
        self.assertIn("{name: 'Bus', path: '/busadmin'", source)
        self.assertIn("### 已连接进程（心跳）", source)
        self.assertIn("### 最新消息", source)
        self.assertIn("发送到 Bus", source)

    def test_admin_registers_busadmin_route(self):
        source = (ROOT / "deva/admin.py").read_text(encoding="utf-8")
        self.assertIn("(r'/busadmin', webio_handler(busadmin, cdn=cdn))", source)


if __name__ == "__main__":
    unittest.main()
