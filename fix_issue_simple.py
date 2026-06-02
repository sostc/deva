#!/usr/bin/env python3
"""Fix the undefined variable issue"""

file_path = '/Users/spark/pycharmproject/deva/deva/naja/bandit/futu_portfolio_syncer.py'

with open(file_path, 'r') as f:
    content = f.read()

# Simple replacements - replace the patterns without quotes with quoted versions
content = content.replace('pos.get("market", US)', 'pos.get("market", "US")')
content = content.replace('pos.get("currency", USD)', 'pos.get("currency", "USD")')
content = content.replace('row.get("currency", USD)', 'row.get("currency", "USD")')

with open(file_path, 'w') as f:
    f.write(content)

print("File fixed successfully!")
