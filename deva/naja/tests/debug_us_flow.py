#!/usr/bin/env python
"""Debug US Stock Data Flow"""

import os
os.environ['NAJA_FORCE_REALTIME'] = '1'

import time
print('=== Debug: Full US Stock Data Flow ===')

# 1. Check AttentionSystem
from deva.naja.market_hotspot.integration import get_market_hotspot_integration
integration = get_market_hotspot_integration()
print(f'1. integration: {integration}')
print(f'   integration.hotspot_system: {integration.hotspot_system}')

# 2. Check US attention state
if integration.hotspot_system:
    us_state = integration.hotspot_system.get_us_hotspot_state()
    print(f'2. US attention state: {us_state}')

    # 3. Check _us_* attributes
    print(f'3. _us_last_global_attention: {integration.hotspot_system._us_last_global_attention}')
    print(f'   _us_last_activity: {integration.hotspot_system._us_last_activity}')
    print(f'   _us_last_block_attention: {integration.hotspot_system._us_last_block_attention}')

    # 4. Check _initialized
    print(f'4. _initialized: {integration.hotspot_system._initialized}')

# 5. Check RealtimeDataFetcher
from deva.naja.market_hotspot.realtime_data_fetcher import get_data_fetcher
fetcher = get_data_fetcher()
print(f'5. fetcher: {fetcher}')
if fetcher:
    print(f'   fetcher.hotspot_system: {fetcher.hotspot_system}')
    print(f'   fetcher._us_active: {fetcher._us_active}')
    print(f'   fetcher._is_active: {fetcher._is_active}')
    print(f'   fetcher._running: {fetcher._running}')

    # 6. Check get_stats
    stats = fetcher.get_stats()
    print(f'6. fetcher stats: is_us_trading={stats.get("is_us_trading")}, is_trading={stats.get("is_trading")}')
else:
    print('5. fetcher is None - need to initialize first')

# 7. Check UI component data
print('\n=== UI Component Data ===')
from deva.naja.attention.ui_components.us_market import get_us_attention_data
us_data = get_us_attention_data()
print(f'7. get_us_attention_data(): {us_data}')

# 8. Manual test: call process_us_snapshot directly
print('\n=== Manual Test: process_us_snapshot ===')
import numpy as np
from deva.naja.market_hotspot.integration.hotspot_system import AttentionSystem, AttentionSystemConfig

config = AttentionSystemConfig()
system = AttentionSystem(config)
system._initialized = True

symbols = np.array(['nvda', 'aapl', 'tsla'])
returns = np.array([2.5, 0.5, -2.0])
volumes = np.array([5e7, 3e7, 8e7])
prices = np.array([800, 175, 245])
sector_ids = np.array(['半导体', '科技', '新能源车'])
timestamp = time.time()

result = system.process_us_snapshot(
    symbols=symbols,
    returns=returns,
    volumes=volumes,
    prices=prices,
    sector_ids=sector_ids,
    timestamp=timestamp
)
print(f'8. process_us_snapshot result:')
print(f'   global_attention: {result["global_attention"]}')
print(f'   activity: {result["activity"]}')
print(f'   sector_attention: {result["sector_attention"]}')
print(f'   symbol_weights: {result["symbol_weights"]}')

# 9. Check if the data is accessible via get_us_attention_data
print('\n=== After manual processing ===')
# Note: The data is stored in the system instance we just created, not the singleton
