#!/usr/bin/env python3
import os
import time
import signal
import numpy as np
import pandas as pd

os.environ['NAJA_ATTENTION_ENABLED'] = 'true'
os.environ['NAJA_LAB_DEBUG'] = 'true'

from deva.naja.attention import initialize_attention_system, get_attention_integration
from deva.naja.attention.center import get_orchestrator
from deva.naja.attention.config import load_config

print("=" * 60)
print("🧪 注意力系统实验模式测试 - 显示板块名称")
print("=" * 60)

print("\n[1] Loading config...")
config = load_config()
print(f"    Config enabled: {config.enabled}")

if not config.enabled:
    print("    Enabling attention system...")
    config.enabled = True

print("\n[2] Initializing attention system...")
initialize_attention_system(config.to_attention_system_config())

print("\n[3] Getting orchestrator...")
orchestrator = get_orchestrator()
print(f"    Orchestrator: {orchestrator}")

integration = get_attention_integration()
print(f"    Integration: {integration}")

time.sleep(1)

print("\n[4] Generating test data...")
symbols = [f"{600000 + i:06d}" for i in range(100)]
n = len(symbols)

print(f"    Generating {n} symbols...")

iteration = 0
print("\n" + "=" * 60)
print("开始模拟数据流 (15秒后自动停止)...")
print("=" * 60)

start_time = time.time()
max_duration = 15

try:
    while time.time() - start_time < max_duration:
        iteration += 1

        data = pd.DataFrame({
            'code': symbols,
            'name': [f'股票{i}' for i in range(n)],
            'now': np.random.uniform(5, 50, n),
            'close': np.random.uniform(5, 50, n),
            'open': np.random.uniform(5, 50, n),
            'high': np.random.uniform(5, 50, n),
            'low': np.random.uniform(5, 50, n),
            'volume': np.random.uniform(100000, 10000000, n),
            'amount': np.random.uniform(1000000, 100000000, n),
            'p_change': np.random.uniform(-10, 10, n),
            'date': '2026-03-24',
            'time': '09:30:00',
        })

        data['sector'] = np.random.choice(['科技', '金融', '消费', '医药', '能源'], n)

        orchestrator.process_datasource_data("test_datasource", data)

        if iteration % 10 == 0:
            context = orchestrator.get_attention_context()
            print(f"\n[迭代 {iteration}]")
            print(f"    Global Attention: {context['global_attention']:.4f}")
            print(f"    Processed Frames: {context['processed_frames']}")

            report = integration.get_attention_report()
            print(f"    Snapshots: {report.get('processed_snapshots', 0)}")

            sector_weights = integration.attention_system.sector_attention.get_all_weights(filter_noise=True)
            if sector_weights:
                top5 = sorted(sector_weights.items(), key=lambda x: x[1], reverse=True)[:5]
                from deva.naja.cognition.history_tracker import get_history_tracker
                tracker = get_history_tracker()
                named_top5 = [(tracker.get_block_name(s), w) for s, w in top5]
                print(f"    Top 5 Sectors:")
                for name, weight in named_top5:
                    print(f"      - {name}: {weight:.4f}")

        time.sleep(0.5)

except KeyboardInterrupt:
    print("\n\n用户中断")

print("\n" + "=" * 60)
print("测试完成")
print("=" * 60)
