#!/usr/bin/env python
"""美股注意力系统详细测试"""

import time
import numpy as np

print('='*70)
print('US Stock Attention System - Detailed Test')
print('='*70)

# Step 1: Test block mapping
print('\n[Step 1] US Stock Sector Mapping')
from deva.naja.market_hotspot.data.global_market_futures import US_STOCK_BLOCKS, US_STOCK_CODES, US_BLOCK_LIST

print(f'   Stock count: {len(US_STOCK_CODES)}')
print(f'   Sector count: {len(US_BLOCK_LIST)}')
print(f'   Key stocks blocks:')
for sym in ['nvda', 'aapl', 'tsla', 'amd', 'baba', 'mstr']:
    print(f'     {sym}: {US_STOCK_BLOCKS.get(sym, "Unknown")}')

# Step 2: Test data conversion
print('\n[Step 2] Data Format Conversion')
mock_data = {
    'nvda': {'price': 800.0, 'prev_close': 780.0, 'change': 20.0, 'change_pct': 2.56, 'volume': 50000000, 'high': 810.0, 'low': 775.0, 'name': 'NVIDIA'},
    'aapl': {'price': 175.0, 'prev_close': 174.0, 'change': 1.0, 'change_pct': 0.57, 'volume': 30000000, 'high': 176.0, 'low': 173.5, 'name': 'Apple'},
    'tsla': {'price': 245.0, 'prev_close': 250.0, 'change': -5.0, 'change_pct': -2.0, 'volume': 80000000, 'high': 252.0, 'low': 243.0, 'name': 'Tesla'},
    'amd': {'price': 150.0, 'prev_close': 148.0, 'change': 2.0, 'change_pct': 1.35, 'volume': 20000000, 'high': 152.0, 'low': 147.0, 'name': 'AMD'},
    'baba': {'price': 85.0, 'prev_close': 82.0, 'change': 3.0, 'change_pct': 3.66, 'volume': 15000000, 'high': 86.0, 'low': 81.0, 'name': 'Alibaba'},
}

from deva.naja.market_hotspot.realtime_data_fetcher import RealtimeDataFetcher

class MockFetcher:
    pass

fetcher = MockFetcher()
fetcher._convert_us_to_dataframe = RealtimeDataFetcher._convert_us_to_dataframe

df = fetcher._convert_us_to_dataframe(None, mock_data)
print(f'   Converted DataFrame:')
print(f'     Rows: {len(df)}')
print(f'     Columns: {list(df.columns)}')
print(f'     Sector distribution:')
for block, count in df['block'].value_counts().items():
    print(f'       {block}: {count}')

# Step 3: Test attention calculation
print('\n[Step 3] Attention System Calculation')
from deva.naja.market_hotspot.integration.attention_system import AttentionSystem, AttentionSystemConfig

config = AttentionSystemConfig()
system = AttentionSystem(config)
system._initialized = True

symbols = df.index.values
returns = df['p_change'].values
volumes = df['volume'].values
prices = df['now'].values
block_ids = df['block'].values

result = system.process_us_snapshot(
    symbols=symbols,
    returns=returns,
    volumes=volumes,
    prices=prices,
    block_ids=block_ids,
    timestamp=time.time()
)

print(f'   global_attention: {result["global_attention"]:.4f}')
print(f'   activity: {result["activity"]:.4f}')
print(f'   block_attention:')
for block, weight in sorted(result['block_attention'].items(), key=lambda x: x[1], reverse=True):
    print(f'     {block}: {weight:.4f}')
print(f'   symbol_weights:')
for sym, weight in sorted(result['symbol_weights'].items(), key=lambda x: x[1], reverse=True):
    print(f'     {sym}: {weight:.4f}')

# Step 4: Test UI rendering
print('\n[Step 4] UI Components Rendering')
from deva.naja.attention.ui_components.us_market import (
    render_us_market_panel,
    render_us_hot_blocks_and_stocks,
    render_us_market_summary,
)

ui_data = {
    'global_attention': result['global_attention'],
    'activity': result['activity'],
    'block_attention': result['block_attention'],
    'symbol_weights': result['symbol_weights'],
}

panel_html = render_us_market_panel(ui_data)
print(f'   render_us_market_panel: {len(panel_html)} chars')

hot_html = render_us_hot_blocks_and_stocks(ui_data)
print(f'   render_us_hot_blocks_and_stocks: {len(hot_html)} chars')

summary_html = render_us_market_summary()
print(f'   render_us_market_summary: {len(summary_html)} chars')

# Step 5: Test state query
print('\n[Step 5] State Query')
state = system.get_us_hotspot_state()
print(f'   get_us_hotspot_state keys: {list(state.keys())}')

print('\n' + '='*70)
print('All tests passed! US Stock Attention System is ready.')
print('='*70)
