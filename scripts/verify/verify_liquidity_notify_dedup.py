"""验证流动性预测通知不再重复轰炸钉钉（三层去重闸门）。

背景：
    Radar 每 60 秒扫一次全球市场，同一条传播边在单边行情里被反复触发。
    修复前会产生 N 条内容一模一样的预测，验证时又套用同一份快照，
    最终钉钉收到几十条一字不差的「预测验证成功」。

三层闸门：
    1) PredictionTracker —— 同一条边同一方向同时只允许一条 PENDING 预测
    2) InfluenceEdge     —— pending 传播事件队列有界（2 小时窗口）
    3) LiquidityNotifier —— 内容指纹去重 + 同类突发上限 + 全局最小间隔

跑法：
    env -u PYTHONPATH TMPDIR=$(mktemp -d) python3 \
        scripts/verify/verify_liquidity_notify_dedup.py
"""
import ast
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

LIQUIDITY_DIR = os.path.join(ROOT, "deva", "naja", "cognition", "liquidity")


# ────────────────────────────────────────────────────────────────
#  假钉钉：拦截真实外发
# ────────────────────────────────────────────────────────────────
class FakeDtalk:
    sent = []

    def __rrshift__(self, message):
        FakeDtalk.sent.append(message)


def install_fake_dtalk():
    import deva.endpoints as endpoints

    FakeDtalk.sent = []
    endpoints.Dtalk = FakeDtalk
    return FakeDtalk


def fresh_notifier(**kwargs):
    from deva.naja.cognition.liquidity.notifier import LiquidityNotifier

    kwargs.setdefault("min_interval", 0.0)
    kwargs.setdefault("burst_limit", 1000)
    return LiquidityNotifier(**kwargs)


def confirm(notifier, **over):
    payload = {
        "from_market": "nasdaq",
        "to_market": "a_share",
        "direction": "down",
        "probability": 0.8,
        "actual_change": -2.50,
    }
    payload.update(over)
    notifier.send_prediction_confirmed(**payload)


# ────────────────────────────────────────────────────────────────
#  静态检查工具
# ────────────────────────────────────────────────────────────────
def _strip_comment_lines(source: str) -> str:
    """去掉注释行与行尾注释，避免注释里的示例代码造成假警报"""
    from io import StringIO
    import tokenize

    pieces = []
    try:
        tokens = tokenize.generate_tokens(StringIO(source).readline)
        for tok in tokens:
            if tok.type == tokenize.COMMENT:
                continue
            pieces.append(tok.string)
    except tokenize.TokenError:
        return source
    return "".join(pieces)


def method_bodies(source: str, class_name: str):
    """返回 {方法名: 去注释后的源码}"""
    tree = ast.parse(source)
    result = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    segment = ast.get_source_segment(source, item) or ""
                    result[item.name] = _strip_comment_lines(segment)
    return result


# ────────────────────────────────────────────────────────────────
#  运行时守卫
# ────────────────────────────────────────────────────────────────
def check_layer1_same_content():
    """第 3 层：同内容连发 N 条，只准出去 1 条"""
    fake = install_fake_dtalk()
    n = fresh_notifier(dedupe_window=1800.0)
    for _ in range(50):
        confirm(n)
    stats = n.get_stats()
    assert stats["total_sent"] == 1, f"同内容应只发 1 条，实际 {stats['total_sent']}"
    assert stats["suppressed_duplicate"] == 49, stats
    assert len(fake.sent) == 1, len(fake.sent)
    print("1) 同内容 50 条 -> 实发 1 条 / 抑制 49 条 OK")


def check_layer1_content_change():
    """内容真的变了就必须放行，去重不能吞掉新信息"""
    install_fake_dtalk()
    n = fresh_notifier(dedupe_window=1800.0)
    confirm(n)                                        # -2.50%
    confirm(n, actual_change=-3.10)                   # 幅度变了
    confirm(n, direction="up", actual_change=1.20)    # 方向变了
    confirm(n, to_market="hk_equity", actual_change=-2.50)  # 目标市场变了
    stats = n.get_stats()
    assert stats["total_sent"] == 4, f"内容变化应放行，实际 {stats['total_sent']}"
    assert stats["total_suppressed"] == 0, stats
    print("2) 内容或去向变化 -> 正常放行（不误杀） OK")


def check_layer1_window_expiry():
    """去重窗口过期后，同一内容允许再次提醒"""
    install_fake_dtalk()
    n = fresh_notifier(dedupe_window=10.0)
    confirm(n)
    n._fingerprints = {fp: ts - 20.0 for fp, ts in n._fingerprints.items()}
    confirm(n)
    assert n.get_stats()["total_sent"] == 2, n.get_stats()
    print("3) 去重窗口过期 -> 同内容可再发一次 OK")


def check_layer1_burst_limit():
    """同类型突发上限：不同内容也不能无限灌"""
    install_fake_dtalk()
    n = fresh_notifier(dedupe_window=0.0, burst_limit=4, burst_window=600.0)
    for i in range(20):
        confirm(n, actual_change=-(1.0 + i * 0.1))
    stats = n.get_stats()
    assert stats["total_sent"] == 4, f"突发上限 4，实际 {stats['total_sent']}"
    assert stats["suppressed_burst"] == 16, stats
    print("4) 同类型突发 20 条 -> 放行 4 条 / 抑制 16 条 OK")


def check_layer1_min_interval():
    """全局最小间隔：挡住秒级连发"""
    install_fake_dtalk()
    n = fresh_notifier(dedupe_window=0.0, burst_limit=1000, min_interval=300.0)
    confirm(n)
    confirm(n, actual_change=-3.0)
    stats = n.get_stats()
    assert stats["total_sent"] == 1, stats
    assert stats["suppressed_interval"] == 1, stats
    print("5) 全局最小间隔内 -> 第二条被挡 OK")


def check_layer1_disabled():
    """禁用开关仍然生效（不能因为加了去重就绕过）"""
    install_fake_dtalk()
    n = fresh_notifier()
    n.disable()
    confirm(n)
    assert len(FakeDtalk.sent) == 0, FakeDtalk.sent
    print("6) 通知器禁用 -> 一条都不发 OK")


def check_layer1_market_name():
    """market_id 必须显示成人话，不能漏出英文 id"""
    from deva.naja.cognition.liquidity.notifier import market_display_name

    assert market_display_name("nasdaq") == "纳斯达克", market_display_name("nasdaq")
    assert market_display_name("a_share") == "A 股"
    assert market_display_name("完全没配的市场") == "完全没配的市场"

    install_fake_dtalk()
    n = fresh_notifier()
    confirm(n)
    payload = FakeDtalk.sent[0]
    head = payload[len("@md@"):]
    assert "nasdaq" not in head, f"文案漏出英文 id: {head}"
    assert "纳斯达克 → A 股" in head, head
    title = head.split("\n")[0].strip()
    print(f"7) 标题使用中文市场名 OK（{title}）")


def check_layer2_tracker_dedup():
    """第 1 层：同一条边反复触发，只保留一条 PENDING 预测"""
    from deva.naja.cognition.liquidity.liquidity_cognition import PredictionTracker
    from deva.naja.cognition.liquidity.propagation_engine import PropagationEngine

    engine = PropagationEngine()
    engine.initialize()
    tracker = PredictionTracker(engine)

    ids = [
        tracker.create_prediction_with_schedule(
            "us_equity", "a_share", "down", 0.8, -2.5
        )
        for _ in range(40)
    ]
    assert len(set(ids)) == 1, f"同边同方向应复用同一条，实际 {len(set(ids))} 个"
    assert tracker.get_stats()["total_created"] == 1
    assert tracker.get_stats()["total_deduped"] == 39
    assert tracker.get_stats()["active_count"] == 1
    print("8) 同边 40 次触发 -> 只建 1 条预测 OK")


def check_layer2_reverse_signal():
    """反向信号要能打断旧预测（去重不能吞掉反向）"""
    from deva.naja.cognition.liquidity.liquidity_cognition import PredictionTracker
    from deva.naja.cognition.liquidity.propagation_engine import PropagationEngine

    engine = PropagationEngine()
    engine.initialize()
    tracker = PredictionTracker(engine)

    down_id = tracker.create_prediction_with_schedule(
        "us_equity", "a_share", "down", 0.8, -2.5
    )
    up_id = tracker.create_prediction_with_schedule(
        "us_equity", "a_share", "up", 0.75, 2.0
    )
    assert up_id != down_id, "反向信号应新建预测"
    assert tracker.get_stats()["total_cancelled"] == 1
    old = tracker.get_prediction(down_id)
    assert old.status.value == "cancelled", old.status
    print("9) 反向信号 -> 旧预测取消、新建反向预测 OK")


def check_layer2_index_release():
    """预测一旦离开 PENDING，边索引必须释放，否则永久无法再建"""
    from deva.naja.cognition.liquidity.liquidity_cognition import (
        PredictionTracker,
        PredictionStatus,
    )
    from deva.naja.cognition.liquidity.propagation_engine import PropagationEngine

    engine = PropagationEngine()
    engine.initialize()
    tracker = PredictionTracker(engine)

    first = tracker.create_prediction_with_schedule(
        "us_equity", "a_share", "up", 0.8, 2.0
    )
    tracker.verify_prediction(first, "up", 1.5)
    assert tracker.get_prediction(first).status == PredictionStatus.CONFIRMED

    second = tracker.create_prediction_with_schedule(
        "us_equity", "a_share", "up", 0.8, 2.0
    )
    assert second != first, "旧预测终结后应能再建"
    assert len(tracker._predictions_by_status[PredictionStatus.PENDING]) == 1
    print("10) 预测终结后边索引释放、可再建 OK")


def check_layer2_other_edges_unaffected():
    """去重按边隔离，不能顺手把别的边也挡了"""
    from deva.naja.cognition.liquidity.liquidity_cognition import PredictionTracker
    from deva.naja.cognition.liquidity.propagation_engine import PropagationEngine

    engine = PropagationEngine()
    engine.initialize()
    tracker = PredictionTracker(engine)

    targets = [edge.to_market for edge in engine._edges.values()
               if edge.from_market == "us_equity"]
    assert len(targets) >= 2, f"需要多条边才能验证隔离性，实际 {targets}"

    created = [
        tracker.create_prediction_with_schedule("us_equity", m, "down", 0.8, -2.5)
        for m in targets
    ]
    assert len(set(created)) == len(targets), "不同边的预测不应互相去重"
    print(f"11) 去重按边隔离 OK（{len(targets)} 条边各自保留）")


def check_layer3_pending_bounded():
    """第 2 层：pending 传播事件队列有界，且过期事件被清理"""
    from deva.naja.cognition.liquidity.influence_edge import InfluenceEdge

    edge = InfluenceEdge("us_equity", "a_share", base_strength=0.8)

    edge.propagate(-2.5, time.time() - 3 * 3600)   # 3 小时前的事件
    edge.propagate(-2.5)                            # 触发清理后再 append
    assert len(edge.get_pending_events()) == 1, edge.get_pending_events()

    for _ in range(200):
        edge.propagate(-2.5)
    pending = edge.get_pending_events()
    assert len(pending) == 201, f"2 小时窗口内应有界保留，实际 {len(pending)}"

    edge.cleanup_expired_events(1.0)
    time.sleep(1.2)
    edge.cleanup_expired_events(1.0)
    assert len(edge.get_pending_events()) == 0, "过期后应清空"
    print("12) pending 队列清理生效、窗口内有界 OK")


def check_layer3_boost_path_still_works():
    """验证成功仍要增强边权重（不能为了去重把学习机制弄丢）"""
    from deva.naja.cognition.liquidity.influence_edge import InfluenceEdge

    edge = InfluenceEdge("us_equity", "a_share", base_strength=0.6)
    before = edge.get_weight()
    edge._boost_weight()
    assert edge.get_weight() > before, "boost 后权重应上升"
    edge._decay_weight()
    edge._decay_weight()
    assert edge.get_weight() < before + 0.1, "decay 后权重应回落"
    print("13) 边权重学习（boost/decay）未被破坏 OK")


# ────────────────────────────────────────────────────────────────
#  静态守卫：防止去重闸门被绕过 / 幽灵字段复发
# ────────────────────────────────────────────────────────────────
def check_static_notify_paths():
    """四个外发方法都必须走 _send_to_dtalk，不能有人绕过去重闸门"""
    path = os.path.join(LIQUIDITY_DIR, "notifier.py")
    with open(path, encoding="utf-8") as fh:
        source = fh.read()

    bodies = method_bodies(source, "LiquidityNotifier")
    producers = [
        "send_prediction_created",
        "send_prediction_confirmed",
        "send_prediction_denied",
        "send_resonance_detected",
        "send_signal_change",
    ]
    for name in producers:
        assert name in bodies, f"缺少通知方法 {name}"
        body = bodies[name]
        assert "self._send_to_dtalk(" in body, \
            f"{name} 未走统一出口 _send_to_dtalk，去重闸门会被绕过"

    gate = bodies.get("_send_to_dtalk", "")
    assert "self._check_send_allowed(" in gate, \
        "_send_to_dtalk 未做限流判定，去重闸门失效"
    print(f"14) 静态：{len(producers)} 个通知方法均经统一限流出口 OK")


def check_static_no_ghost_field():
    """PropagationEvent 上没有 predicted_change 字段，引用它会静默断链"""
    path = os.path.join(LIQUIDITY_DIR, "liquidity_cognition.py")
    with open(path, encoding="utf-8") as fh:
        source = fh.read()

    bodies = method_bodies(source, "LiquidityCognition")
    body = bodies.get("_get_pending_propagations", "")
    assert body, "找不到 _get_pending_propagations"
    assert "predicted_change" not in body, \
        "predicted_change 是 PropagationEvent 上不存在的字段（幽灵调用复发）"
    assert "source_change" in body, "应取 source_change 作为本次源市场变化"
    print("15) 静态：无 predicted_change 幽灵字段 OK")


def check_static_pending_prune():
    """propagate 必须先清过期事件，否则队列无限增长"""
    path = os.path.join(LIQUIDITY_DIR, "influence_edge.py")
    with open(path, encoding="utf-8") as fh:
        source = fh.read()

    bodies = method_bodies(source, "InfluenceEdge")
    body = bodies.get("propagate", "")
    assert body, "找不到 InfluenceEdge.propagate"
    assert "cleanup_expired_events(" in body, \
        "propagate 未清理过期事件，pending 队列会无限增长"
    print("16) 静态：propagate 入口已挂过期清理 OK")


def main():
    # 运行时
    check_layer1_same_content()
    check_layer1_content_change()
    check_layer1_window_expiry()
    check_layer1_burst_limit()
    check_layer1_min_interval()
    check_layer1_disabled()
    check_layer1_market_name()
    check_layer2_tracker_dedup()
    check_layer2_reverse_signal()
    check_layer2_index_release()
    check_layer2_other_edges_unaffected()
    check_layer3_pending_bounded()
    check_layer3_boost_path_still_works()
    # 静态
    check_static_notify_paths()
    check_static_no_ghost_field()
    check_static_pending_prune()

    print("\nALL PASS")


if __name__ == "__main__":
    main()
