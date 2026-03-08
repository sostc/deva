from deva.core.namespace import NB

strategies = NB('naja_strategies')
print("Strategy data structure:")
for key in strategies:
    strategy = strategies[key]
    print(f"Key: {key}")
    print(f"Type: {type(strategy)}")
    if isinstance(strategy, dict):
        print(f"Keys: {list(strategy.keys())}")
    elif hasattr(strategy, '__dict__'):
        print(f"Attributes: {list(strategy.__dict__.keys())}")
    print()
    # 只显示前5个策略的结构
    if len([k for k in strategies]) > 5:
        break
