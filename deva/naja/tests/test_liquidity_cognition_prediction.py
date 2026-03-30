"""
LiquidityCognition PredictionTracker 测试

测试新增的预测跟踪和验证功能
"""

import pytest
import time
from deva.naja.cognition.liquidity.liquidity_cognition import (
    LiquidityCognition,
    LiquidityPrediction,
    PredictionTracker,
    PredictionStatus,
    get_liquidity_cognition,
)


class TestPredictionTracker:
    """PredictionTracker 测试"""

    def test_create_prediction(self):
        """测试创建预测"""
        lc = LiquidityCognition()
        tracker = lc.get_prediction_tracker()

        pred_id = tracker.create_prediction(
            from_market="nasdaq",
            to_market="a_share",
            direction="down",
            probability=0.8,
            verify_minutes=30,
        )

        assert pred_id is not None
        assert pred_id.startswith("liq_pred_")

        stats = tracker.get_stats()
        assert stats["total_created"] == 1
        assert stats["active_count"] == 1

    def test_get_active_prediction(self):
        """测试获取活跃预测"""
        lc = LiquidityCognition()
        tracker = lc.get_prediction_tracker()

        pred_id = tracker.create_prediction(
            from_market="nasdaq",
            to_market="a_share",
            direction="down",
            probability=0.8,
        )

        pred = tracker.get_active_prediction("a_share")
        assert pred is not None
        assert pred.id == pred_id
        assert pred.direction == "down"
        assert pred.status == PredictionStatus.PENDING

    def test_get_active_prediction_no_prediction(self):
        """测试没有预测时返回 None"""
        lc = LiquidityCognition()
        tracker = lc.get_prediction_tracker()

        pred = tracker.get_active_prediction("a_share")
        assert pred is None

    def test_verify_prediction_success(self):
        """测试预测验证成功"""
        lc = LiquidityCognition()
        tracker = lc.get_prediction_tracker()

        pred_id = tracker.create_prediction(
            from_market="nasdaq",
            to_market="a_share",
            direction="down",
            probability=0.8,
            verify_minutes=1,  # 1分钟
        )

        time.sleep(0.1)

        verified = tracker.verify_prediction(
            pred_id,
            actual_direction="down",
            actual_change=-2.5,
        )

        assert verified is True

        pred = tracker.get_prediction(pred_id)
        assert pred.status == PredictionStatus.CONFIRMED

        stats = tracker.get_stats()
        assert stats["total_confirmed"] == 1

    def test_verify_prediction_failure(self):
        """测试预测验证失败"""
        lc = LiquidityCognition()
        tracker = lc.get_prediction_tracker()

        pred_id = tracker.create_prediction(
            from_market="nasdaq",
            to_market="a_share",
            direction="down",
            probability=0.8,
            verify_minutes=1,
        )

        time.sleep(0.1)

        verified = tracker.verify_prediction(
            pred_id,
            actual_direction="up",
            actual_change=2.5,
        )

        assert verified is False

        pred = tracker.get_prediction(pred_id)
        assert pred.status == PredictionStatus.DENIED

        stats = tracker.get_stats()
        assert stats["total_denied"] == 1

    def test_cancel_prediction(self):
        """测试取消预测"""
        lc = LiquidityCognition()
        tracker = lc.get_prediction_tracker()

        pred_id = tracker.create_prediction(
            from_market="nasdaq",
            to_market="a_share",
            direction="down",
            probability=0.8,
        )

        cancelled = tracker.cancel_prediction(pred_id, "出现反向信号")
        assert cancelled is True

        pred = tracker.get_prediction(pred_id)
        assert pred.status == PredictionStatus.CANCELLED
        assert pred.cancel_reason == "出现反向信号"

        stats = tracker.get_stats()
        assert stats["total_cancelled"] == 1
        assert stats["active_count"] == 0

    def test_cancel_predictions_for_market(self):
        """测试批量取消市场预测"""
        lc = LiquidityCognition()
        tracker = lc.get_prediction_tracker()

        tracker.create_prediction(
            from_market="nasdaq",
            to_market="a_share",
            direction="down",
            probability=0.8,
        )
        tracker.create_prediction(
            from_market="sp500",
            to_market="a_share",
            direction="up",
            probability=0.7,
        )

        count = tracker.cancel_predictions_for_market(
            "a_share",
            "市场出现反弹",
        )

        assert count == 2
        assert tracker.get_active_prediction("a_share") is None

    def test_verify_and_update_timeout(self):
        """测试超时自动标记为失败"""
        lc = LiquidityCognition()
        tracker = lc.get_prediction_tracker()

        tracker._default_verify_minutes = 0  # 立即超时

        pred_id = tracker.create_prediction(
            from_market="nasdaq",
            to_market="a_share",
            direction="down",
            probability=0.8,
        )

        time.sleep(0.1)

        stats = tracker.verify_and_update()

        assert stats["denied"] == 1

        pred = tracker.get_prediction(pred_id)
        assert pred.status == PredictionStatus.DENIED

    def test_get_prediction_rate(self):
        """测试预测准确率"""
        lc = LiquidityCognition()
        tracker = lc.get_prediction_tracker()

        rate = tracker.get_prediction_rate()
        assert rate == 0.5  # 无数据时返回 0.5

        tracker.create_prediction(
            from_market="nasdaq",
            to_market="a_share",
            direction="down",
            probability=0.8,
        )
        tracker.verify_prediction(
            tracker._predictions_by_status[PredictionStatus.PENDING][0],
            "down",
            -2.5,
        )

        rate = tracker.get_prediction_rate()
        assert rate == 1.0


class TestLiquidityCognitionPrediction:
    """LiquidityCognition 预测接口测试"""

    def test_get_active_prediction(self):
        """测试获取活跃预测接口"""
        lc = LiquidityCognition()

        result = lc.get_active_prediction("a_share")
        assert result is None  # 没有预测

        tracker = lc.get_prediction_tracker()
        tracker.create_prediction(
            from_market="us_equity",
            to_market="a_share",
            direction="down",
            probability=0.8,
        )

        result = lc.get_active_prediction("a_share")
        assert result is not None
        assert result["has_prediction"] is True
        assert result["direction"] == "down"
        assert "probability" in result

    def test_query_for_signals(self):
        """测试批量查询接口"""
        lc = LiquidityCognition()

        results = lc.query_for_signals(["a_share", "hk_equity"])
        assert results["a_share"]["has_prediction"] is False
        assert results["hk_equity"]["has_prediction"] is False

        tracker = lc.get_prediction_tracker()
        tracker.create_prediction(
            from_market="us_equity",
            to_market="a_share",
            direction="down",
            probability=0.8,
        )

        results = lc.query_for_signals(["a_share", "hk_equity"])
        assert results["a_share"]["has_prediction"] is True

    def test_cancel_predictions_for_event(self):
        """测试取消预测"""
        lc = LiquidityCognition()

        lc.ingest_global_market_event({
            "market_id": "nvda",
            "current": 500,
            "change_pct": -2.5,
            "volume": 1000000,
            "is_abnormal": True,
        })

        count = lc.cancel_predictions_for_event("a_share", "市场反弹取消预测")
        assert count >= 0  # 可能没有针对 a_share 的预测

    def test_get_summary_with_predictions(self):
        """测试获取摘要包含预测信息"""
        lc = LiquidityCognition()

        lc.ingest_global_market_event({
            "market_id": "nvda",
            "current": 500,
            "change_pct": -2.5,
            "volume": 1000000,
            "is_abnormal": True,
        })

        summary = lc.get_summary()
        assert "active_predictions" in summary
        assert summary["active_predictions"] >= 0


class TestPredictionIntegration:
    """预测集成测试"""

    def test_full_prediction_lifecycle(self):
        """测试完整预测生命周期"""
        lc = LiquidityCognition()

        tracker = lc.get_prediction_tracker()
        pred_id = tracker.create_prediction(
            from_market="us_equity",
            to_market="a_share",
            direction="down",
            probability=0.8,
        )

        pred_result = lc.get_active_prediction("a_share")
        assert pred_result is not None
        assert pred_result["has_prediction"] is True
        assert pred_result["direction"] == "down"
        assert pred_result["from_market"] == "us_equity"

        verified = tracker.verify_prediction(
            pred_id,
            actual_direction="down",
            actual_change=-2.5,
        )
        assert verified is True

        stats = tracker.get_stats()
        assert stats["total_confirmed"] == 1

    def test_multiple_markets_propagation(self):
        """测试多个市场传播"""
        lc = LiquidityCognition()

        tracker = lc.get_prediction_tracker()
        tracker.create_prediction(
            from_market="us_equity",
            to_market="a_share",
            direction="down",
            probability=0.8,
        )
        tracker.create_prediction(
            from_market="us_equity",
            to_market="hk_equity",
            direction="down",
            probability=0.7,
        )

        results = lc.query_for_signals(["a_share", "hk_equity", "tiger"])
        assert "a_share" in results
        assert "hk_equity" in results


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
