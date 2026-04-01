"""
美股注意力系统集成测试

测试美股数据从获取到UI展示的完整流程
"""

import unittest
import sys
import os
import time
import asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np


class TestUSStockSectors(unittest.TestCase):
    """测试美股板块映射"""

    def test_us_stock_sectors_exists(self):
        """测试 US_STOCK_SECTORS 映射存在"""
        from deva.naja.attention.data.global_market_futures import US_STOCK_SECTORS, US_STOCK_CODES
        self.assertIsInstance(US_STOCK_SECTORS, dict)
        self.assertIsInstance(US_STOCK_CODES, dict)
        print(f"✅ US_STOCK_CODES: {len(US_STOCK_CODES)} 只股票")
        print(f"✅ US_STOCK_SECTORS: {len(US_STOCK_SECTORS)} 只股票")

    def test_us_stock_sectors_coverage(self):
        """测试美股板块覆盖"""
        from deva.naja.attention.data.global_market_futures import US_STOCK_SECTORS, US_SECTOR_LIST
        for symbol in ['aapl', 'nvda', 'tsla', 'baba', 'amd']:
            self.assertIn(symbol, US_STOCK_SECTORS, f"{symbol} 应该在板块映射中")
        print(f"✅ 关键股票板块映射: aapl={US_STOCK_SECTORS['aapl']}, nvda={US_STOCK_SECTORS['nvda']}, tsla={US_STOCK_SECTORS['tsla']}")

    def test_us_sector_list(self):
        """测试板块列表"""
        from deva.naja.attention.data.global_market_futures import US_SECTOR_LIST
        self.assertIsInstance(US_SECTOR_LIST, list)
        self.assertGreater(len(US_SECTOR_LIST), 10)
        print(f"✅ 板块列表 ({len(US_SECTOR_LIST)}): {US_SECTOR_LIST[:5]}...")


class TestDataConversion(unittest.TestCase):
    """测试数据转换"""

    def setUp(self):
        self.mock_us_data = {
            'nvda': {'price': 800.0, 'prev_close': 780.0, 'change': 20.0, 'change_pct': 2.56, 'volume': 50000000, 'high': 810.0, 'low': 775.0, 'name': 'NVIDIA'},
            'aapl': {'price': 175.0, 'prev_close': 174.0, 'change': 1.0, 'change_pct': 0.57, 'volume': 30000000, 'high': 176.0, 'low': 173.5, 'name': 'Apple'},
            'tsla': {'price': 245.0, 'prev_close': 250.0, 'change': -5.0, 'change_pct': -2.0, 'volume': 80000000, 'high': 252.0, 'low': 243.0, 'name': 'Tesla'},
        }

    def test_convert_us_to_dataframe(self):
        """测试美股数据转换为 DataFrame"""
        from deva.naja.attention.realtime_data_fetcher import RealtimeDataFetcher

        class MockFetcher:
            pass

        fetcher = MockFetcher()
        fetcher._convert_us_to_dataframe = RealtimeDataFetcher._convert_us_to_dataframe

        df = fetcher._convert_us_to_dataframe(None, self.mock_us_data)

        self.assertIsNotNone(df)
        self.assertEqual(len(df), 3)
        self.assertIn('sector', df.columns)
        self.assertIn('market', df.columns)
        self.assertIn('p_change', df.columns)
        self.assertIn('volume', df.columns)
        self.assertIn('now', df.columns)
        self.assertIn('close', df.columns)

        print(f"✅ DataFrame 列: {list(df.columns)}")
        print(f"✅ DataFrame 索引: {list(df.index)}")
        print(f"✅ 板块分布:\n{df['sector'].value_counts()}")

    def test_convert_empty_data(self):
        """测试空数据处理"""
        from deva.naja.attention.realtime_data_fetcher import RealtimeDataFetcher

        class MockFetcher:
            pass

        fetcher = MockFetcher()
        fetcher._convert_us_to_dataframe = RealtimeDataFetcher._convert_us_to_dataframe

        df = fetcher._convert_us_to_dataframe(None, {})
        self.assertIsNone(df)

        df = fetcher._convert_us_to_dataframe(None, None)
        self.assertIsNone(df)

        print("✅ 空数据处理正确")


class TestAttentionSystem(unittest.TestCase):
    """测试注意力系统美股处理"""

    def test_process_us_snapshot_basic(self):
        """测试基本的 process_us_snapshot 调用"""
        from deva.naja.attention.integration.attention_system import AttentionSystem, AttentionSystemConfig

        config = AttentionSystemConfig()
        system = AttentionSystem(config)
        system._initialized = True

        symbols = np.array(['nvda', 'aapl', 'tsla', 'amd', 'baba'])
        returns = np.array([2.5, 0.5, -2.0, 1.5, 3.0])
        volumes = np.array([5e7, 3e7, 8e7, 2e7, 4e7])
        prices = np.array([800, 175, 245, 150, 85])
        sector_ids = np.array(['半导体', '科技', '新能源车', '半导体', '电商'])
        timestamp = time.time()

        result = system.process_us_snapshot(
            symbols=symbols,
            returns=returns,
            volumes=volumes,
            prices=prices,
            sector_ids=sector_ids,
            timestamp=timestamp
        )

        self.assertEqual(result['market'], 'US')
        self.assertIn('global_attention', result)
        self.assertIn('activity', result)
        self.assertIn('sector_attention', result)
        self.assertIn('symbol_weights', result)
        self.assertGreater(result['stock_count'], 0)

        print(f"✅ global_attention: {result['global_attention']:.4f}")
        print(f"✅ activity: {result['activity']:.4f}")
        print(f"✅ sector_count: {len(result['sector_attention'])}")
        print(f"✅ symbol_count: {len(result['symbol_weights'])}")
        print(f"✅ sector_attention: {result['sector_attention']}")

    def test_process_us_snapshot_uninitialized(self):
        """测试未初始化时的处理"""
        from deva.naja.attention.integration.attention_system import AttentionSystem

        system = AttentionSystem()

        symbols = np.array(['nvda'])
        returns = np.array([2.5])
        volumes = np.array([5e7])
        prices = np.array([800])
        sector_ids = np.array(['半导体'])
        timestamp = time.time()

        result = system.process_us_snapshot(
            symbols=symbols,
            returns=returns,
            volumes=volumes,
            prices=prices,
            sector_ids=sector_ids,
            timestamp=timestamp
        )

        self.assertEqual(result['market'], 'US')
        self.assertEqual(result['global_attention'], 0.5)

        print("✅ 未初始化时返回降级结果")

    def test_get_us_attention_state(self):
        """测试获取美股注意力状态"""
        from deva.naja.attention.integration.attention_system import AttentionSystem, AttentionSystemConfig

        config = AttentionSystemConfig()
        system = AttentionSystem(config)
        system._initialized = True

        state = system.get_us_attention_state()

        self.assertIn('global_attention', state)
        self.assertIn('activity', state)
        self.assertIn('sector_attention', state)
        self.assertIn('symbol_weights', state)

        print("✅ get_us_attention_state 返回正确结构")

    def test_extreme_values(self):
        """测试极端值处理"""
        from deva.naja.attention.integration.attention_system import AttentionSystem, AttentionSystemConfig

        config = AttentionSystemConfig()
        system = AttentionSystem(config)
        system._initialized = True

        symbols = np.array(['extreme'])
        returns = np.array([100.0])
        volumes = np.array([1e20])
        prices = np.array([0.001])
        sector_ids = np.array(['测试'])
        timestamp = time.time()

        result = system.process_us_snapshot(
            symbols=symbols,
            returns=returns,
            volumes=volumes,
            prices=prices,
            sector_ids=sector_ids,
            timestamp=timestamp
        )

        self.assertIsNotNone(result)
        self.assertEqual(result['market'], 'US')

        print("✅ 极端值处理正确 (returns=100, volumes=1e20, price=0.001)")


class TestUSMarketUI(unittest.TestCase):
    """测试美股市场UI组件"""

    def test_get_us_attention_data(self):
        """测试获取美股注意力数据"""
        from deva.naja.attention.ui_components.us_market import get_us_attention_data

        data = get_us_attention_data()

        self.assertIsInstance(data, dict)
        print(f"✅ get_us_attention_data 返回: {list(data.keys())}")

    def test_render_us_market_panel(self):
        """测试渲染美股市场面板"""
        from deva.naja.attention.ui_components.us_market import render_us_market_panel

        mock_data = {
            'global_attention': 0.65,
            'activity': 0.72,
            'sector_attention': {
                '半导体': 0.8,
                '科技': 0.6,
                '新能源车': 0.45,
            },
            'symbol_weights': {
                'nvda': 5.2,
                'aapl': 3.1,
                'tsla': 2.8,
            }
        }

        html = render_us_market_panel(mock_data)

        self.assertIsInstance(html, str)
        self.assertIn('美股市场', html)
        self.assertIn('🇺🇸', html)
        self.assertIn('0.650', html)
        self.assertIn('半导体', html)
        self.assertIn('NVDA', html.upper())

        print("✅ render_us_market_panel 生成正确 HTML")

    def test_render_us_hot_sectors_and_stocks(self):
        """测试渲染美股热门板块和股票"""
        from deva.naja.attention.ui_components.us_market import render_us_hot_sectors_and_stocks

        mock_data = {
            'sector_attention': {
                '半导体': 0.85,
                '科技': 0.65,
                '电商': 0.45,
            },
            'symbol_weights': {
                'nvda': 5.5,
                'amd': 4.2,
                'aapl': 3.0,
                'baba': 2.5,
            }
        }

        html = render_us_hot_sectors_and_stocks(mock_data)

        self.assertIsInstance(html, str)
        self.assertIn('美股热门板块', html)
        self.assertIn('美股热门股票', html)
        self.assertIn('半导体', html)
        self.assertIn('NVDA', html)

        print("✅ render_us_hot_sectors_and_stocks 生成正确 HTML")

    def test_render_us_market_summary(self):
        """测试渲染美股市场摘要"""
        from deva.naja.attention.ui_components.us_market import render_us_market_summary

        html = render_us_market_summary()

        self.assertIsInstance(html, str)
        self.assertIn('美股', html)

        print("✅ render_us_market_summary 生成正确 HTML")


class TestIntegration(unittest.TestCase):
    """集成测试：端到端流程"""

    def test_full_pipeline(self):
        """测试完整流程：数据 -> 注意力 -> UI"""
        print("\n" + "="*60)
        print("开始集成测试：端到端流程")
        print("="*60)

        mock_us_data = {
            'nvda': {'price': 800.0, 'prev_close': 780.0, 'change': 20.0, 'change_pct': 2.56, 'volume': 50000000, 'high': 810.0, 'low': 775.0, 'name': 'NVIDIA'},
            'aapl': {'price': 175.0, 'prev_close': 174.0, 'change': 1.0, 'change_pct': 0.57, 'volume': 30000000, 'high': 176.0, 'low': 173.5, 'name': 'Apple'},
            'tsla': {'price': 245.0, 'prev_close': 250.0, 'change': -5.0, 'change_pct': -2.0, 'volume': 80000000, 'high': 252.0, 'low': 243.0, 'name': 'Tesla'},
            'amd': {'price': 150.0, 'prev_close': 148.0, 'change': 2.0, 'change_pct': 1.35, 'volume': 20000000, 'high': 152.0, 'low': 147.0, 'name': 'AMD'},
            'baba': {'price': 85.0, 'prev_close': 82.0, 'change': 3.0, 'change_pct': 3.66, 'volume': 15000000, 'high': 86.0, 'low': 81.0, 'name': 'Alibaba'},
            'msft': {'price': 380.0, 'prev_close': 378.0, 'change': 2.0, 'change_pct': 0.53, 'volume': 25000000, 'high': 381.0, 'low': 377.0, 'name': 'Microsoft'},
            'meta': {'price': 500.0, 'prev_close': 495.0, 'change': 5.0, 'change_pct': 1.01, 'volume': 18000000, 'high': 502.0, 'low': 494.0, 'name': 'Meta'},
            'amzn': {'price': 180.0, 'prev_close': 178.0, 'change': 2.0, 'change_pct': 1.12, 'volume': 40000000, 'high': 181.0, 'low': 177.5, 'name': 'Amazon'},
        }

        print("\n📊 Step 1: 数据转换")
        from deva.naja.attention.realtime_data_fetcher import RealtimeDataFetcher

        class MockFetcher:
            pass

        fetcher = MockFetcher()
        fetcher._convert_us_to_dataframe = RealtimeDataFetcher._convert_us_to_dataframe

        df = fetcher._convert_us_to_dataframe(None, mock_us_data)
        self.assertIsNotNone(df)
        print(f"✅ 转换成功: {len(df)} 只股票")
        print(f"   板块分布: {df['sector'].value_counts().to_dict()}")

        print("\n📊 Step 2: 注意力计算")
        from deva.naja.attention.integration.attention_system import AttentionSystem, AttentionSystemConfig

        config = AttentionSystemConfig()
        system = AttentionSystem(config)
        system._initialized = True

        symbols = df.index.values
        returns = df['p_change'].values
        volumes = df['volume'].values
        prices = df['now'].values
        sector_ids = df['sector'].values

        result = system.process_us_snapshot(
            symbols=symbols,
            returns=returns,
            volumes=volumes,
            prices=prices,
            sector_ids=sector_ids,
            timestamp=time.time()
        )

        print(f"✅ 注意力计算成功")
        print(f"   global_attention: {result['global_attention']:.4f}")
        print(f"   activity: {result['activity']:.4f}")
        print(f"   板块注意力: {result['sector_attention']}")
        print(f"   个股权重 Top5: {sorted(result['symbol_weights'].items(), key=lambda x: x[1], reverse=True)[:5]}")

        print("\n📊 Step 3: UI渲染")
        from deva.naja.attention.ui_components.us_market import (
            render_us_market_panel,
            render_us_hot_sectors_and_stocks,
            render_us_market_summary,
        )

        ui_data = {
            'global_attention': result['global_attention'],
            'activity': result['activity'],
            'sector_attention': result['sector_attention'],
            'symbol_weights': result['symbol_weights'],
        }

        panel_html = render_us_market_panel(ui_data)
        hot_html = render_us_hot_sectors_and_stocks(ui_data)
        summary_html = render_us_market_summary()

        print(f"✅ UI渲染成功")
        print(f"   panel_html 长度: {len(panel_html)}")
        print(f"   hot_html 长度: {len(hot_html)}")
        print(f"   summary_html 长度: {len(summary_html)}")

        print("\n" + "="*60)
        print("✅ 集成测试通过：端到端流程验证成功")
        print("="*60)


if __name__ == '__main__':
    print("\n" + "="*70)
    print("🧪 美股注意力系统集成测试")
    print("="*70 + "\n")

    unittest.main(verbosity=2)
