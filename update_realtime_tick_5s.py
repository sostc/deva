#!/usr/bin/env python3
"""
更新realtime_tick_5s数据源的执行逻辑，添加更多非个股代码的过滤
"""

import sys
sys.path.insert(0, '/Users/spark/pycharmproject/deva')

from deva import NB

def update_realtime_tick_5s():
    """更新realtime_tick_5s数据源的执行逻辑"""
    # 直接操作数据库
    db = NB('naja_datasources')
    
    print("📋 检查naja_datasources数据库...")
    print(f"   数据库条目数: {len(db)}")
    
    # 查找realtime_tick_5s数据源
    target_ds_id = None
    target_ds_data = None
    for ds_id, ds_data in db.items():
        if isinstance(ds_data, dict):
            metadata = ds_data.get('metadata', {})
            name = metadata.get('name', '')
            print(f"   - {name} (ID: {ds_id})")
            if name == 'realtime_tick_5s':
                target_ds_id = ds_id
                target_ds_data = ds_data
                print(f"   🔍 找到目标数据源: {name} (ID: {target_ds_id})")
                break
    
    if not target_ds_id or not target_ds_data:
        print("❌ 未找到realtime_tick_5s数据源")
        return False
    
    # 新的执行逻辑 - 添加更多非个股代码的过滤
    new_func_code = '''def gen_quant():
    import easyquotation
    import pandas as pd

    quotation_engine = easyquotation.use("sina")
    q1 = quotation_engine.market_snapshot(prefix=False)
    df = pd.DataFrame(q1).T
    
    # 过滤掉 close 为 0 的股票
    df = df[(True ^ df["close"].isin([0]))]
    # 过滤掉 now 为 0 的股票
    df = df[(True ^ df["now"].isin([0]))]
    
    # 过滤掉指数和基金产品
    # 1. 过滤掉指数代码（以000、399、688开头）
    df = df[~df.index.str.match('^000')]
    df = df[~df.index.str.match('^399')]
    df = df[~df.index.str.match('^688')]
    
    # 2. 过滤掉基金代码
    # ETF基金：上交所51开头，深交所159开头
    df = df[~df.index.str.match('^51')]
    df = df[~df.index.str.match('^159')]
    # LOF基金：上交所501、502开头，深交所16开头
    df = df[~df.index.str.match('^501')]
    df = df[~df.index.str.match('^502')]
    df = df[~df.index.str.match('^16')]
    # 封闭式基金：上交所50开头，深交所184开头
    df = df[~df.index.str.match('^50')]
    df = df[~df.index.str.match('^184')]
    # 分级基金：15开头（包括150）
    df = df[~df.index.str.match('^15')]
    
    # 3. 过滤掉name字段中包含特定关键字的产品
    if 'name' in df.columns:
        keywords = ['指数', 'ETF', 'LOF', '基金', '债券']
        for keyword in keywords:
            df = df[~df['name'].str.contains(keyword, na=False, regex=False)]
    
    # 过滤掉僵尸票（成交量小于 100 手）
    df = df[df.get('volume', 0) > 100]
    
    # 过滤掉退市票和ST股票（name字段包含特定后缀）
    if 'name' in df.columns:
        delisted_patterns = ['退', 'ST', '*ST']
        for pattern in delisted_patterns:
            df = df[~df['name'].str.contains(pattern, na=False, regex=False)]
    
    # 计算涨跌幅
    df["p_change"] = (df.now - df.close) / df.close
    df["p_change"] = df.p_change.map(float)
    df["code"] = df.index
    return df


def get_realtime_quant():
    """获取实盘实时行情,非盘中时间不获取数据"""
    import datetime
    from deva.naja.common.tradetime import is_tradedate, is_tradetime

    if is_tradedate(datetime.datetime.today()) and is_tradetime(datetime.datetime.now()):
        return gen_quant()
    return None


def fetch_data():
    return get_realtime_quant()
'''
    
    # 直接修改数据并保存
    print(f"🔄 更新数据源配置...")
    print(f"   原代码长度: {len(target_ds_data.get('func_code', ''))}")
    print(f"   新代码长度: {len(new_func_code)}")
    
    # 直接修改字典
    target_ds_data['func_code'] = new_func_code
    target_ds_data['metadata']['updated_at'] = pd.Timestamp.now().timestamp()
    
    # 保存到数据库
    print(f"💾 保存到数据库...")
    db[target_ds_id] = target_ds_data
    print(f"✅ 数据库保存完成")
    
    # 重新加载验证
    print(f"🔍 重新验证更新...")
    reloaded_ds_data = db[target_ds_id]
    reloaded_func_code = reloaded_ds_data.get('func_code', '')
    print(f"   重新加载后代码长度: {len(reloaded_func_code)}")
    print(f"   包含15开头过滤: {'^15' in reloaded_func_code}")
    print(f"   包含51开头过滤: {'^51' in reloaded_func_code}")
    print(f"   包含16开头过滤: {'^16' in reloaded_func_code}")
    
    print("\n✅ 成功更新realtime_tick_5s数据源的执行逻辑")
    print(f"  数据源ID: {target_ds_id}")
    print("  已添加更多非个股代码过滤：")
    print("    - 过滤ETF基金（51开头、159开头）")
    print("    - 过滤LOF基金（501、502、16开头）")
    print("    - 过滤封闭式基金（50、184开头）")
    print("    - 过滤分级基金（15开头，包括150）")
    print("    - 过滤name字段中包含债券关键字的产品")
    
    return True

if __name__ == '__main__':
    print("=" * 60)
    print("更新realtime_tick_5s数据源执行逻辑")
    print("=" * 60)
    
    # 导入pandas用于时间戳
    import pandas as pd
    
    success = update_realtime_tick_5s()
    
    if success:
        print("\n🎯 任务完成！")
        print("realtime_tick_5s数据源现在会过滤掉更多非个股代码，只返回真正的个股")
    else:
        print("\n❌ 任务失败！")
