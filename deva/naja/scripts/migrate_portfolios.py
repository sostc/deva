#!/usr/bin/env python3
"""迁移持仓数据到统一表"""

from deva import NB

print('=' * 60)
print('迁移持仓数据到统一表 naja_bandit_positions')
print('=' * 60)

# 新表
new_db = NB('naja_bandit_positions')

# 迁移 Spark 账户
print('\n[1/3] 迁移 Spark 账户...')
spark_db = NB('naja_bandit_us_portfolio_Spark')
spark_data = spark_db.get('positions', {})
spark_equity = spark_db.get('equity', 0.0)

if spark_data:
    accounts = new_db.get('accounts', {})
    accounts['Spark'] = {
        'account_type': 'us',
        'equity': spark_equity,
        'positions': spark_data
    }
    new_db['accounts'] = accounts
    print(f'  ✓ Spark: 迁移 {len(spark_data)} 个持仓')
else:
    print('  - Spark: 无持仓')

# 迁移 Cutie 账户
print('\n[2/3] 迁移 Cutie 账户...')
cutie_db = NB('naja_bandit_us_portfolio_Cutie')
cutie_data = cutie_db.get('positions', {})

if cutie_data:
    accounts = new_db.get('accounts', {})
    accounts['Cutie'] = {
        'account_type': 'us',
        'equity': 0.0,
        'positions': cutie_data
    }
    new_db['accounts'] = accounts
    print(f'  ✓ Cutie: 迁移 {len(cutie_data)} 个持仓')
else:
    print('  - Cutie: 无持仓')

# 迁移虚拟账户
print('\n[3/3] 迁移虚拟测试账户...')
virtual_db = NB('naja_bandit_virtual_portfolio')
virtual_data = virtual_db.get('positions', {})

if virtual_data:
    accounts = new_db.get('accounts', {})
    accounts['虚拟测试'] = {
        'account_type': 'virtual',
        'total_capital': 1000000.0,
        'positions': virtual_data
    }
    new_db['accounts'] = accounts
    print(f'  ✓ 虚拟测试: 迁移 {len(virtual_data)} 个持仓')
else:
    print('  - 虚拟测试: 无持仓')

# 验证
print('\n' + '=' * 60)
print('验证迁移结果')
print('=' * 60)

accounts = new_db.get('accounts', {})
print(f'统一表中账户数: {len(accounts)}')
for name, data in accounts.items():
    pos_count = len(data.get('positions', {}))
    print(f'  {name}: {pos_count} 个持仓')

print('\n迁移完成!')
print('建议: 运行 VACUUM 压缩数据库')