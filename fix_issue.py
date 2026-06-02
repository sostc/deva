#!/usr/bin/env python3
"""Fix the undefined variable issue"""

file_path = '/Users/spark/pycharmproject/deva/deva/naja/bandit/futu_portfolio_syncer.py'

with open(file_path, 'r') as f:
    lines = f.readlines()

# Fix the three problematic lines
for i, line in enumerate(lines):
    if '"currency": str(row.get("currency", USD)),' in line:
        lines[i] = line.replace('USD', '"USD"')
    if '"market": pos.get("market", US),' in line:
        lines[i] = line.replace('US', '"US"')
    if '"currency": pos.get("currency", USD),' in line:
        lines[i] = line.replace('USD', '"USD"')

with open(file_path, 'w') as f:
    f.writelines(lines)

print("File fixed successfully!")
