from deva.core.namespace import NB

strategies = NB('naja_strategies')
print("All strategies in database:")
for key in strategies:
    strategy = strategies[key]
    if isinstance(strategy, dict) and 'name' in strategy:
        print(f"- {strategy['name']}")
