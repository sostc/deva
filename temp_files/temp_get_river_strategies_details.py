from deva.core.namespace import NB

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
                'func_code': strategy.get('func_code', ''),
                'metadata': metadata
            })

print(f"Found {len(river_strategies)} river strategies:")
for i, strategy in enumerate(river_strategies):
    print(f"\n=== Strategy {i+1} ===")
    print(f"Strategy ID: {strategy['id']}")
    print(f"Name: {strategy['name']}")
    print(f"Func code length: {len(strategy['func_code'])}")
    # 只打印func_code的前500个字符，避免输出过长
    print("Func code (first 500 chars):")
    print(strategy['func_code'][:500] + "..." if len(strategy['func_code']) > 500 else strategy['func_code'])
    print("\n" + "="*50)
