from deva.core.namespace import NB

# 需要检查的策略ID
strategy_ids = ['d0b4ba69e346', '8c0460c1c2f5', 'bca643834222']
strategies = NB('naja_strategies')

for strategy_id in strategy_ids:
    if strategy_id in strategies:
        strategy = strategies[strategy_id]
        print(f"=== Strategy: {strategy['metadata']['name']} ===")
        print(f"Func code:")
        print(strategy.get('func_code', ''))
        print("\n" + "="*80 + "\n")
    else:
        print(f"Strategy with ID {strategy_id} not found")
