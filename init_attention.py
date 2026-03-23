#!/usr/bin/env python3
import os
os.environ['NAJA_ATTENTION_ENABLED'] = 'true'
os.environ['NAJA_LAB_DEBUG'] = 'true'

from deva.naja.attention_integration import initialize_attention_system, get_attention_integration
from deva.naja.attention_config import load_config

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

    sector_weights = integration.attention_system.sector_attention.get_all_weights(filter_noise=True)
    print("\nSector weights count:", len(sector_weights))
    if sector_weights:
        top5 = sorted(sector_weights.items(), key=lambda x: x[1], reverse=True)[:5]
        print("Top 5 sectors:")
        for sector_id, weight in top5:
            print("  {}: {:.4f}".format(sector_id, weight))
else:
    print("Attention system not available")