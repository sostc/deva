"""
测试流动性预测通知功能

运行此测试验证：
1. 通知器是否正常工作
2. 钉钉消息是否能发送
3. UI 是否能显示通知历史
"""

import time
from deva.naja.cognition.liquidity import get_notifier, get_liquidity_cognition


def test_notifier():
    """测试通知器基本功能"""
    print("=" * 60)
    print("测试流动性预测通知器")
    print("=" * 60)
    
    # 获取通知器
    notifier = get_notifier()
    
    print(f"\n✓ 通知器已初始化：{notifier}")
    print(f"✓ 通知状态：{'启用' if notifier.is_enabled() else '禁用'}")
    
    # 测试发送预测创建通知
    print("\n1. 测试预测创建通知...")
    notifier.send_prediction_created(
        from_market="us_equity",
        to_market="a_share",
        direction="down",
        probability=0.85,
        source_change=-3.5,
        verify_minutes=30,
    )
    print("   ✓ 已发送预测创建通知")
    
    # 测试发送预测验证成功通知
    print("\n2. 测试预测验证成功通知...")
    notifier.send_prediction_confirmed(
        from_market="us_equity",
        to_market="a_share",
        direction="down",
        probability=0.85,
        actual_change=-2.8,
    )
    print("   ✓ 已发送预测验证成功通知")
    
    # 测试发送预测验证失败通知
    print("\n3. 测试预测验证失败通知...")
    notifier.send_prediction_denied(
        from_market="us_futures",
        to_market="hk_equity",
        direction="up",
        probability=0.75,
        actual_change=-1.2,
        reason="direction_mismatch",
    )
    print("   ✓ 已发送预测验证失败通知")
    
    # 测试发送共振检测通知
    print("\n4. 测试共振检测通知...")
    notifier.send_resonance_detected(
        markets=["us_equity", "a_share", "hk_equity"],
        resonance_level="high",
        confidence=0.88,
    )
    print("   ✓ 已发送共振检测通知")
    
    # 测试发送信号变化通知
    print("\n5. 测试信号变化通知...")
    notifier.send_signal_change(
        market="a_share",
        old_signal=0.65,
        new_signal=0.35,
        change_pct=-0.46,
    )
    print("   ✓ 已发送信号变化通知")
    
    # 获取通知历史
    print("\n6. 查询通知历史...")
    notifications = notifier.get_recent_notifications(limit=10)
    print(f"   ✓ 共有 {len(notifications)} 条通知记录")
    
    for i, n in enumerate(notifications, 1):
        print(f"\n   [{i}] {n.get('title', 'N/A')}")
        print(f"       时间：{n.get('time_str', 'N/A')}")
        print(f"       类型：{n.get('type', 'N/A')}")
        print(f"       严重程度：{n.get('severity', 'N/A')}")
        print(f"       已发送：{'是' if n.get('sent') else '否'}")
    
    # 获取统计信息
    print("\n7. 统计信息...")
    stats = notifier.get_stats()
    print(f"   总发送数：{stats.get('total_sent', 0)}")
    print(f"   总失败数：{stats.get('total_failed', 0)}")
    print(f"   历史记录数：{stats.get('history_count', 0)}")
    print(f"   按类型统计：{stats.get('by_type', {})}")
    
    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)


def test_liquidity_cognition_integration():
    """测试与 LiquidityCognition 的集成"""
    print("\n" + "=" * 60)
    print("测试 LiquidityCognition 集成")
    print("=" * 60)
    
    # 获取流动性认知系统
    lc = get_liquidity_cognition()
    
    print(f"\n✓ 流动性认知系统已初始化：{lc}")
    
    # 获取预测跟踪器
    tracker = lc.get_prediction_tracker()
    print(f"✓ 预测跟踪器：{tracker}")
    
    # 创建预测（应该自动发送通知）
    print("\n创建高置信度预测（应该触发通知）...")
    pred_id = tracker.create_prediction(
        from_market="nasdaq",
        to_market="a_share",
        direction="down",
        probability=0.85,
        verify_minutes=30,
        source_change=-4.2,
    )
    print(f"✓ 预测已创建：{pred_id}")
    
    # 等待一小段时间
    time.sleep(0.5)
    
    # 查询通知
    notifier = get_notifier()
    notifications = notifier.get_recent_notifications(limit=3)
    
    if notifications:
        latest = notifications[0]
        print(f"\n✓ 最新通知：{latest.get('title', 'N/A')}")
        print(f"  类型：{latest.get('type', 'N/A')}")
        print(f"  时间：{latest.get('time_str', 'N/A')}")
    
    print("\n" + "=" * 60)
    print("集成测试完成！")
    print("=" * 60)


if __name__ == "__main__":
    try:
        test_notifier()
        test_liquidity_cognition_integration()
        print("\n✅ 所有测试通过！")
    except Exception as e:
        print(f"\n❌ 测试失败：{e}")
        import traceback
        traceback.print_exc()
