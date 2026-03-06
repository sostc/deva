#!/usr/bin/env python3
"""
将Stock模块转化为naja的数字字典
"""

from deva.naja.dictionary import get_dictionary_manager
from deva.naja.dictionary.stock.stock import refresh_stock_basic_dataframe


def create_stock_dictionary():
    """创建股票数据字典"""
    print("开始创建股票数据字典...")
    print("=" * 80)
    
    # 获取字典管理器
    dict_mgr = get_dictionary_manager()
    
    # 定义fetch_data函数
    fetch_data_code = '''
def fetch_data():
    """获取股票基础数据"""
    from deva.naja.dictionary.stock.stock import refresh_stock_basic_dataframe
    
    # 刷新股票基础数据
    result = refresh_stock_basic_dataframe()
    print(f"股票数据刷新结果: {result}")
    
    # 返回刷新后的基础数据
    from deva import NB
    return NB("naja").get("basic_df")
'''
    
    # 创建字典条目
    create_result = dict_mgr.create(
        name="股票基础数据",
        func_code=fetch_data_code,
        description="股票基础信息数据，包括代码、名称、行业、板块等",
        dict_type="dimension",
        schedule_type="daily",
        daily_time="03:00",
        interval_seconds=3600,
        tags=["股票", "基础数据", "行业", "板块"],
        source_mode="task",
        execution_mode="scheduler",
        scheduler_trigger="cron",
        cron_expr="0 3 * * *",  # 每天凌晨3点执行
    )
    
    if create_result.get("success"):
        print("\n股票数据字典创建成功！")
        print(f"字典ID: {create_result.get('id')}")
        print(f"字典名称: 股票基础数据")
        
        # 立即执行一次，获取初始数据
        print("\n正在获取初始股票数据...")
        run_result = dict_mgr.run_once(create_result.get('id'))
        if run_result.get("success"):
            print("初始数据获取成功！")
        else:
            print(f"初始数据获取失败: {run_result.get('error')}")
    else:
        print(f"\n股票数据字典创建失败: {create_result.get('error')}")
    
    print("=" * 80)
    print("操作完成！")


if __name__ == "__main__":
    create_stock_dictionary()
