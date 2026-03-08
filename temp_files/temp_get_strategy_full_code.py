from deva.core.namespace import NB

# 获取所有策略
strategies = NB('naja_strategies')

# 要检查的策略名称
strategy_names = [
    'river_微观结构波动异常_top',
    'river_交易行为痕迹聚类',
    'river_量价盘口异常分数_top',
    'river_订单流失衡先行信号',
    'river_短期方向概率_top'
]

# 查找并打印每个策略的代码
for name in strategy_names:
    found = False
    for strategy_id, strategy in strategies.items():
        if strategy.get('metadata', {}).get('name') == name:
            print(f"\nStrategy: {name}")
            print(f"Strategy ID: {strategy_id}")
            print(f"Func code:")
            print(strategy.get('func_code', ''))
            found = True
            break
    if not found:
        print(f"\nStrategy {name} not found")
