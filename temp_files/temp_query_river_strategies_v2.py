from deva.core.namespace import NB

strategies = NB('naja_strategies')
river_strategies = []

for key in strategies:
    strategy = strategies[key]
    if isinstance(strategy, dict) and 'metadata' in strategy:
        metadata = strategy['metadata']
        if isinstance(metadata, dict) and 'name' in metadata and metadata['name'].startswith('river'):
            river_strategies.append(metadata)

print("River strategies found:")
for strategy in river_strategies:
    print(f"- {strategy['name']}")

print(f"Total river strategies: {len(river_strategies)}")
