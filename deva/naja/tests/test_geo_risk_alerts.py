"""评级跃迁告警：单例、只推变化、Stream/回调、latest 截断。"""

from deva.naja.geo_risk.alerts import GeoRiskAlertCenter, get_alert_center


def _center() -> GeoRiskAlertCenter:
    center = get_alert_center()
    center._latest.clear()
    return center


def test_singleton_and_stream_name():
    assert get_alert_center() is GeoRiskAlertCenter()
    assert get_alert_center().get_stream().name == "geo_risk_alerts"


def test_publish_drops_non_transitions():
    center = _center()
    assert center.publish({"from": "yellow", "to": "yellow"}) is False
    assert center.publish({"from": None, "to": "red"}) is False
    assert center.publish({"from": "yellow"}) is False
    assert center.publish("not-a-dict") is False
    assert center.get_latest() == []


def test_publish_emits_stream_and_callbacks():
    center = _center()
    payloads = []
    stream_payloads = []
    center.register_callback(payloads.append)
    sink = center.get_stream().sink(stream_payloads.append)

    ok = center.publish({
        "project_id": "p1", "name": "YTL Johor",
        "from": "yellow", "to": "red", "direction": "escalated",
    })
    assert ok is True

    latest = center.get_latest()
    assert len(latest) == 1
    assert latest[0]["project_id"] == "p1"
    assert latest[0]["to"] == "red"
    assert "timestamp" in latest[0]

    assert payloads and payloads[-1]["alerts"][0]["project_id"] == "p1"
    assert stream_payloads and stream_payloads[-1]["alerts"][0]["to"] == "red"
    center.unregister_callback(payloads.append)
    center.get_stream().disconnect(sink)


def test_latest_is_capped_at_50():
    center = _center()
    for i in range(55):
        center.publish({"project_id": f"p{i}", "from": "green", "to": "yellow"})
    latest = center.get_latest(limit=100)
    assert len(latest) == 50
    assert latest[0]["project_id"] == "p54"
