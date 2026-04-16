#!/usr/bin/env python3
import os
os.environ['NAJA_ATTENTION_ENABLED'] = 'true'
os.environ['NAJA_LAB_DEBUG'] = 'true'

from deva.naja.attention import initialize_attention_system, get_attention_integration
from deva.naja.attention.config import load_config

print("Loading config...")
config = load_config()
print("Config enabled:", config.enabled)

if not config.enabled:
    print("Enabling attention system...")
    config.enabled = True

print("Initializing attention system...")
initialize_attention_system(config.to_attention_system_config())

import time
time.sleep(3)

integration = get_attention_integration()
if integration.attention_system:
    report = integration.get_attention_report()
    print("\n=== Attention System Report ===")
    print("Status:", report.get("status", "unknown"))
    print("Processed snapshots:", report.get("processed_snapshots", 0))
    print("Global attention: {:.4f}".format(report.get("global_attention", 0)))

    block_weights = integration.attention_system.block_attention.get_all_weights(filter_noise=True)
    print("\nBlock weights count:", len(block_weights))
    if block_weights:
        top5 = sorted(block_weights.items(), key=lambda x: x[1], reverse=True)[:5]
        print("Top 5 blocks:")
        for block_id, weight in top5:
            print("  {}: {:.4f}".format(block_id, weight))
else:
    print("Attention system not available")