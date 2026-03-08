from deva.core.namespace import NB

strategies = NB('naja_strategies')
river_strategies = []

for key in strategies:
    strategy = strategies[key]
    if isinstance(strategy, dict) and 'metadata' in strategy:
        metadata = strategy['metadata']
        if isinstance(metadata, dict) and 'name' in metadata and metadata['name'].startswith('river'):
            func_code = strategy.get('func_code', '')
            has_price_in_return = '"price":' in func_code
            has_price_field = 'price' in func_code
            
            river_strategies.append({
                'id': key,
                'name': metadata['name'],
                'has_price_in_return': has_price_in_return,
                'has_price_field': has_price_field
            })

print(f"Found {len(river_strategies)} river strategies:")
for strategy in river_strategies:
    print(f"- {strategy['name']} (ID: {strategy['id']})")
    print(f"  Has price in return: {strategy['has_price_in_return']}")
    print(f"  Has price field: {strategy['has_price_field']}")
    print()
