from deva.core.namespace import NB

# 获取所有river策略
strategies = NB('naja_strategies')
river_strategies = []

for key in strategies:
    strategy = strategies[key]
    if isinstance(strategy, dict) and 'metadata' in strategy:
        metadata = strategy['metadata']
        if isinstance(metadata, dict) and 'name' in metadata and metadata['name'].startswith('river'):
            river_strategies.append({
                'id': key,
                'name': metadata['name'],
                'bound_datasource_id': metadata.get('bound_datasource_id', 'Not set'),
                'status': strategy.get('state', {}).get('status', 'Unknown')
            })

print(f"Verifying {len(river_strategies)} river strategies:")
print("="*80)

# 验证每个river策略的数据源绑定
realtime_quant_5s_id = 'e626eecd0b86'
all_correct = True

for strategy in river_strategies:
    datasource_id = strategy['bound_datasource_id']
    is_correct = datasource_id == realtime_quant_5s_id
    status = strategy['status']
    
    print(f"Strategy: {strategy['name']}")
    print(f"  ID: {strategy['id']}")
    print(f"  Bound Datasource: {datasource_id}")
    print(f"  Status: {status}")
    print(f"  Correctly bound: {'✓' if is_correct else '✗'}")
    print()
    
    if not is_correct:
        all_correct = False

print("="*80)
if all_correct:
    print("✓ All river strategies are correctly bound to realtime_quant_5s datasource")
else:
    print("✗ Some river strategies are not correctly bound")
