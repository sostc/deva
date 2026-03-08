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
                'strategy': strategy
            })

print(f"Found {len(river_strategies)} river strategies to update")

# 更新每个river策略的数据源绑定
realtime_quant_5s_id = 'e626eecd0b86'
updated_count = 0

for river_strat in river_strategies:
    strategy_id = river_strat['id']
    strategy_name = river_strat['name']
    strategy = river_strat['strategy']
    
    # 检查并更新metadata中的bound_datasource_id
    if 'metadata' in strategy:
        if 'bound_datasource_id' in strategy['metadata']:
            old_datasource = strategy['metadata']['bound_datasource_id']
            print(f"Updating {strategy_name} (ID: {strategy_id}) from datasource {old_datasource} to {realtime_quant_5s_id}")
        else:
            print(f"Adding datasource {realtime_quant_5s_id} to {strategy_name} (ID: {strategy_id})")
        
        # 更新数据源绑定
        strategy['metadata']['bound_datasource_id'] = realtime_quant_5s_id
        strategies[strategy_id] = strategy
        updated_count += 1

print(f"Updated {updated_count} river strategies to use realtime_quant_5s datasource")
