from deva.core.namespace import NB

strategies = NB('naja_strategies')
river_strategies = []

for key in strategies:
    strategy = strategies[key]
    if isinstance(strategy, dict) and 'name' in strategy and strategy['name'].startswith('river'):
        river_strategies.append(strategy)

print("River strategies found:")
for strategy in river_strategies:
    print(f"- {strategy['name']} (ID: {key if 'id' not in strategy else strategy.get('id')})")

print(f"Total river strategies: {len(river_strategies)}")
