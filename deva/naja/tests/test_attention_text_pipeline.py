"""
测试注意力文本处理架构

测试模块：
1. AttentionTextRouter - 注意力路由器
2. TextSignalBus - 信号总线
3. TextProcessingPipeline - 处理流水线
"""

import unittest
import time
from typing import List

from deva.naja.cognition.attention_text_router import (
    AttentionTextItem,
    AttentionTextRouter,
    ManasState,
    TextSource,
    THRESHOLD_DEEP,
    THRESHOLD_INDEX,
    THRESHOLD_DROP,
    get_attention_router,
)
from deva.naja.cognition.text_signal_bus import (
    TextSignalBus,
    get_text_bus,
    reset_text_bus,
)
from deva.naja.cognition.text_processing_pipeline import (
    TextProcessingPipeline,
    get_text_pipeline,
    process_text,
    subscribe_to_signals,
)


class TestAttentionTextRouter(unittest.TestCase):
    """AttentionTextRouter 测试"""

    def setUp(self):
        self.router = get_attention_router()
        self.router.reset_stats()

    def test_basic_score(self):
        """测试基本评分"""
        score = self.router.compute_attention_score(
            text="英伟达发布新一代GPU芯片，性能大幅提升",
            title="英伟达发布新芯片",
            source=TextSource.NEWS_FEED,
        )
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 1)

    def test_keyword_match(self):
        """测试关键词匹配"""
        # 高匹配
        high_score = self.router.compute_attention_score(
            text="英伟达GPU芯片大涨，AMD跟进，AI算力需求爆发",
            title="AI芯片板块大涨",
        )
        # 低匹配
        low_score = self.router.compute_attention_score(
            text="今天天气不错，适合出去走走",
            title="天气",
        )
        self.assertGreater(high_score, low_score)

    def test_source_weight(self):
        """测试来源权重"""
        high_source = self.router.compute_attention_score(
            text="英伟达大涨",
            source=TextSource.USER_ARTICLE,  # 高权重
        )
        low_source = self.router.compute_attention_score(
            text="英伟达大涨",
            source=TextSource.SOCIAL_MEDIA,  # 低权重
        )
        self.assertGreater(high_source, low_source)

    def test_freshness_decay(self):
        """测试新鲜度衰减"""
        # 刚发布
        fresh = self.router.compute_attention_score(
            text="英伟达大涨",
            timestamp=time.time(),
        )
        # 1小时前
        old = self.router.compute_attention_score(
            text="英伟达大涨",
            timestamp=time.time() - 3600,
        )
        self.assertGreater(fresh, old)

    def test_manas_state_boost(self):
        """测试末那识状态提升"""
        # 设置末那识状态，聚焦AI算力
        self.router.set_manas_state(ManasState(
            focus_topics=[{"topic": "AI算力", "weight": 0.9}],
            timestamp=time.time(),
        ))

        # 匹配AI算力的文本应该有较高分数
        match_score = self.router.compute_attention_score(
            text="英伟达GPU大涨，AI算力需求爆发",
            title="AI芯片大涨",
        )

        # 不匹配的文本分数应该更低
        no_match_score = self.router.compute_attention_score(
            text="今天天气不错",
            title="天气",
        )

        self.assertGreater(match_score, no_match_score)

    def test_routing(self):
        """测试路由分类"""
        items = [
            AttentionTextItem(
                text="英伟达发布新一代GPU芯片，性能大幅提升，AI算力需求爆发",
                title="英伟达发布新芯片",
            ),
            AttentionTextItem(
                text="某公司发布季报，营收小幅增长",
                title="财报发布",
            ),
            AttentionTextItem(
                text="今天天气不错",
                title="天气",
            ),
        ]

        buckets = self.router.route(items)

        self.assertIn("deep", buckets)
        self.assertIn("index", buckets)
        self.assertIn("drop", buckets)

        # 应该有不同级别的内容
        self.assertGreater(len(buckets["deep"]) + len(buckets["index"]), 0)

    def test_quick_score(self):
        """测试快速评分"""
        score = self.router.quick_score(
            "英伟达AMD GPU芯片大涨",
            title="AI芯片",
        )
        self.assertGreater(score, 0)
        self.assertLessEqual(score, 1)


class TestTextSignalBus(unittest.TestCase):
    """TextSignalBus 测试"""

    def setUp(self):
        reset_text_bus()
        self.bus = get_text_bus()
        self.bus.reset_stats()
        self.received_items = []

    def callback_a(self, item: AttentionTextItem):
        self.received_items.append(("A", item.item_id))

    def callback_b(self, item: AttentionTextItem):
        self.received_items.append(("B", item.item_id))

    def test_subscribe_unsubscribe(self):
        """测试订阅和取消"""
        sub = self.bus.subscribe("TestModule", self.callback_a)
        self.assertIn("TestModule", self.bus.list_modules())

        self.bus.unsubscribe("TestModule")
        self.assertNotIn("TestModule", self.bus.list_modules())

    def test_publish_high_attention(self):
        """测试发布高注意力信号"""
        self.bus.subscribe("ModuleA", self.callback_a, min_attention=0.5)

        item = AttentionTextItem(
            text="英伟达大涨",
            attention_score=0.8,
        )
        results = self.bus.publish(item)

        self.assertIn("ModuleA", results)
        self.assertTrue(results["ModuleA"])
        self.assertEqual(len(self.received_items), 1)

    def test_publish_low_attention_filtered(self):
        """测试低注意力信号被过滤"""
        self.bus.subscribe("ModuleA", self.callback_a, min_attention=0.7)

        item = AttentionTextItem(
            text="普通新闻",
            attention_score=0.3,
        )
        results = self.bus.publish(item)

        # 不应该发送
        self.assertEqual(len(self.received_items), 0)

    def test_multiple_subscribers(self):
        """测试多订阅者"""
        self.bus.subscribe("ModuleA", self.callback_a, min_attention=0.5)
        self.bus.subscribe("ModuleB", self.callback_b, min_attention=0.4)

        item = AttentionTextItem(
            text="重要新闻",
            attention_score=0.6,
        )
        self.bus.publish(item)

        self.assertEqual(len(self.received_items), 2)

    def test_topic_filter(self):
        """测试主题过滤"""
        self.received_topics = []

        def callback(item):
            self.received_topics.append(item.topic_candidates)

        self.bus.subscribe(
            "ModuleA",
            callback,
            min_attention=0.0,
            topics=["AI算力"],
        )

        item1 = AttentionTextItem(
            text="英伟达新闻",
            topic_candidates=["AI算力"],
            attention_score=0.5,
        )
        item2 = AttentionTextItem(
            text="天气新闻",
            topic_candidates=["天气"],
            attention_score=0.5,
        )

        self.bus.publish(item1)
        self.bus.publish(item2)

        self.assertEqual(len(self.received_topics), 1)
        self.assertEqual(self.received_topics[0], ["AI算力"])

    def test_broadcast(self):
        """测试批量发布"""
        self.bus.subscribe("ModuleA", self.callback_a, min_attention=0.5)

        items = [
            AttentionTextItem(text=f"新闻{i}", attention_score=0.6)
            for i in range(5)
        ]

        stats = self.bus.broadcast(items)

        self.assertEqual(stats["total_items"], 5)
        self.assertGreater(stats["total_delivered"], 0)

    def test_stats(self):
        """测试统计"""
        self.bus.subscribe("ModuleA", self.callback_a, min_attention=0.5)

        item = AttentionTextItem(
            text="测试",
            attention_score=0.6,
        )
        self.bus.publish(item)

        stats = self.bus.get_stats()
        self.assertEqual(stats["total_published"], 1)
        self.assertEqual(stats["total_delivered"], 1)


class TestTextProcessingPipeline(unittest.TestCase):
    """TextProcessingPipeline 测试"""

    def setUp(self):
        self.pipeline = get_text_pipeline()
        self.received = []

    def test_process_single_item(self):
        """测试单条处理"""
        item = AttentionTextItem(
            text="英伟达发布新一代GPU芯片，性能大幅提升，AI算力需求爆发",
            title="英伟达发布新芯片",
        )

        result = self.pipeline.process(item)

        self.assertIsNotNone(result.attention_score)
        self.assertGreater(len(result.raw_keywords), 0)

    def test_process_batch(self):
        """测试批量处理"""
        items = [
            AttentionTextItem(
                text="英伟达发布新一代GPU芯片，性能大幅提升，AI算力需求爆发",
                title="英伟达发布新芯片",
            ),
            AttentionTextItem(
                text="天气不错适合出去走走",
                title="天气",
            ),
        ]

        stats = self.pipeline.process_batch(items)

        self.assertEqual(stats["total"], 2)
        # 至少有索引或深度处理
        self.assertGreater(stats["deep"] + stats["index"], 0,
            f"应该至少有一些内容被处理，但 stats={stats}")

    def test_deep_processing(self):
        """测试深度处理"""
        item = AttentionTextItem(
            text="英伟达GPU芯片大涨，AI算力需求爆发，供不应求",
            title="AI芯片大涨",
            attention_score=0.8,  # 预设高分
        )

        result = self.pipeline.process(item)

        # 深度处理应该有 structured_signal
        self.assertTrue(result.processed)
        if result.structured_signal:
            self.assertIsNotNone(result.structured_signal.sentiment)

    def test_set_manas_state(self):
        """测试设置末那识状态"""
        state = ManasState(
            focus_topics=[{"topic": "AI算力", "weight": 0.9}],
            timestamp=time.time(),
        )

        self.pipeline.set_manas_state(state)

        # 应该影响后续处理的注意力分数
        item = AttentionTextItem(
            text="英伟达GPU大涨",
            title="英伟达",
        )
        result = self.pipeline.process(item)

        # 匹配到焦点话题，分数应该较高
        self.assertGreater(result.attention_score, 0.3)

    def test_get_recent_index(self):
        """测试获取最近索引"""
        for i in range(10):
            item = AttentionTextItem(
                text=f"新闻{i}",
                title=f"标题{i}",
            )
            self.pipeline.process(item)

        recent = self.pipeline.get_recent_index(5)
        self.assertLessEqual(len(recent), 5)

    def test_subscribe_to_signals(self):
        """测试便捷订阅函数"""
        self.received = []

        def callback(item):
            self.received.append(item.item_id)

        subscribe_to_signals(
            "TestModule",
            callback,
            min_attention=0.5,
        )

        # 发布信号
        item = AttentionTextItem(
            text="测试",
            attention_score=0.6,
        )
        process_text(item.text, item.title)

        # 检查是否收到（通过流水线处理）
        # 注意：subscribe_to_signals 只是注册，总线需要通过流水线触发


class TestProcessText(unittest.TestCase):
    """便捷函数测试"""

    def test_process_text_basic(self):
        """测试 process_text 基本功能"""
        item = process_text(
            text="英伟达发布新一代GPU芯片，性能大幅提升",
            title="英伟达发布新芯片",
            source=TextSource.NEWS_FEED,
        )

        self.assertIsNotNone(item.item_id)
        self.assertIsNotNone(item.attention_score)
        self.assertGreater(len(item.raw_keywords), 0)

    def test_process_text_integration(self):
        """测试完整流程"""
        # 创建高注意力文本
        item = process_text(
            text="英伟达GPU大涨，AI算力需求爆发，供不应求",
            title="AI芯片板块大涨",
            source=TextSource.USER_ARTICLE,
        )

        # 应该被深度处理
        self.assertGreaterEqual(item.attention_score, THRESHOLD_DEEP)


if __name__ == "__main__":
    unittest.main(verbosity=2)
