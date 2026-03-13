#!/usr/bin/env python3
"""
验证realtime_tick_5s数据源的更新状态
"""

import sys
sys.path.insert(0, '/Users/spark/pycharmproject/deva')

from deva import NB

def verify_update():
    """验证realtime_tick_5s数据源的更新状态"""
    print("📋 验证realtime_tick_5s数据源更新状态...")
    
    # 直接操作数据库
    db = NB('naja_datasources')
    
    print(f"   数据库条目数: {len(db)}")
    
    # 查找realtime_tick_5s数据源
    target_ds_id = None
    target_ds_data = None
    for ds_id, ds_data in db.items():
        if isinstance(ds_data, dict):
            metadata = ds_data.get('metadata', {})
            name = metadata.get('name', '')
            if name == 'realtime_tick_5s':
                target_ds_id = ds_id
                target_ds_data = ds_data
                print(f"   🔍 找到目标数据源: {name} (ID: {target_ds_id})")
                break
    
    if not target_ds_id or not target_ds_data:
        print("❌ 未找到realtime_tick_5s数据源")
        return False
    
    # 检查func_code中的过滤规则
    func_code = target_ds_data.get('func_code', '')
    
    print("\n🔍 检查过滤规则是否存在:")
    
    # 检查指数过滤
    has_index_filter = '^000' in func_code and '^399' in func_code and '^688' in func_code
    print(f"   指数代码过滤: {'✅' if has_index_filter else '❌'}")
    
    # 检查ETF基金过滤
    has_etf_filter = '^51' in func_code and '^159' in func_code
    print(f"   ETF基金过滤: {'✅' if has_etf_filter else '❌'}")
    
    # 检查LOF基金过滤
    has_lof_filter = '^501' in func_code and '^502' in func_code and '^16' in func_code
    print(f"   LOF基金过滤: {'✅' if has_lof_filter else '❌'}")
    
    # 检查封闭式基金过滤
    has_close_filter = '^50' in func_code and '^184' in func_code
    print(f"   封闭式基金过滤: {'✅' if has_close_filter else '❌'}")
    
    # 检查分级基金过滤（包括150）
    has_grade_filter = '^15' in func_code
    print(f"   分级基金过滤: {'✅' if has_grade_filter else '❌'}")
    
    # 检查关键字过滤
    has_keyword_filter = '指数' in func_code and 'ETF' in func_code and 'LOF' in func_code and '基金' in func_code and '债券' in func_code
    print(f"   关键字过滤: {'✅' if has_keyword_filter else '❌'}")
    
    # 检查regex=False参数
    has_regex_fix = 'regex=False' in func_code
    print(f"   正则表达式修复: {'✅' if has_regex_fix else '❌'}")
    
    # 检查僵尸票过滤
    has_zombie_filter = 'volume' in func_code and '> 100' in func_code
    print(f"   僵尸票过滤: {'✅' if has_zombie_filter else '❌'}")
    
    # 检查ST和退市票过滤
    has_st_filter = 'ST' in func_code and '退' in func_code
    print(f"   ST和退市票过滤: {'✅' if has_st_filter else '❌'}")
    
    # 检查更新时间
    updated_at = target_ds_data.get('metadata', {}).get('updated_at', 0)
    print(f"\n📅 更新时间: {updated_at}")
    
    # 检查代码长度
    code_length = len(func_code)
    print(f"📏 代码长度: {code_length} 字符")
    
    # 验证所有过滤规则是否都已应用
    all_rules_applied = all([
        has_index_filter,
        has_etf_filter,
        has_lof_filter,
        has_close_filter,
        has_grade_filter,
        has_keyword_filter,
        has_regex_fix,
        has_zombie_filter,
        has_st_filter
    ])
    
    print(f"\n🎯 验证结果: {'✅ 所有过滤规则已正确应用' if all_rules_applied else '❌ 部分过滤规则未应用'}")
    
    if not all_rules_applied:
        print("\n⚠️  未应用的过滤规则:")
        if not has_index_filter:
            print("   - 指数代码过滤")
        if not has_etf_filter:
            print("   - ETF基金过滤")
        if not has_lof_filter:
            print("   - LOF基金过滤")
        if not has_close_filter:
            print("   - 封闭式基金过滤")
        if not has_grade_filter:
            print("   - 分级基金过滤")
        if not has_keyword_filter:
            print("   - 关键字过滤")
        if not has_regex_fix:
            print("   - 正则表达式修复")
        if not has_zombie_filter:
            print("   - 僵尸票过滤")
        if not has_st_filter:
            print("   - ST和退市票过滤")
    
    return all_rules_applied

if __name__ == '__main__':
    print("=" * 60)
    print("验证realtime_tick_5s数据源更新状态")
    print("=" * 60)
    
    success = verify_update()
    
    if success:
        print("\n✅ 验证完成！")
        print("realtime_tick_5s数据源已成功更新，所有过滤规则都已正确应用")
        print("现在数据源会过滤掉:")
        print("  - 指数代码（000、399、688开头）")
        print("  - ETF基金（51、159开头）")
        print("  - LOF基金（501、502、16开头）")
        print("  - 封闭式基金（50、184开头）")
        print("  - 分级基金（15开头，包括150）")
        print("  - 名称包含指数、ETF、LOF、基金、债券关键字的产品")
        print("  - 僵尸票（成交量≤100手）")
        print("  - ST和退市票")
    else:
        print("\n❌ 验证失败！")
        print("realtime_tick_5s数据源的过滤规则未完全应用")
