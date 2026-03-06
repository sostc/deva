#!/usr/bin/env python3
"""
检查策略代码中的df变量使用错误
"""

from deva.naja.strategy import get_strategy_manager


def check_strategy_errors():
    """
    检查所有策略的代码，查找使用了df变量但可能没有正确定义的地方
    """
    mgr = get_strategy_manager()
    mgr.load_from_db()
    
    entries = mgr.list_all()
    error_strategies = []
    
    print(f"Checking {len(entries)} strategies for df variable errors...")
    
    for entry in entries:
        code = entry._func_code
        # 检查是否使用了df变量但没有定义
        if "df" in code and "def process(" in code:
            # 检查process函数的参数
            process_start = code.find("def process(")
            process_end = code.find(")", process_start)
            process_params = code[process_start:process_end+1]
            
            # 检查参数是否使用了data而不是df
            if "data" in process_params and "df" in code:
                # 检查是否在函数体内有df的赋值
                body_start = code.find("\n", code.find("\n", process_start) + 1)
                body_end = code.find("def ", body_start + 1) if "def " in code[body_start+1:] else len(code)
                body = code[body_start:body_end]
                
                # 检查是否有df = data这样的赋值
                if "df = data" not in body and "df=data" not in body:
                    error_strategies.append({
                        "name": entry.name,
                        "id": entry.id,
                        "issue": "Using df variable without assigning it from data parameter"
                    })
    
    if error_strategies:
        print(f"Found {len(error_strategies)} strategies with potential df variable errors:")
        for strategy in error_strategies:
            print(f"- {strategy['name']} (ID: {strategy['id']}): {strategy['issue']}")
    else:
        print("No strategies found with df variable errors.")


if __name__ == "__main__":
    check_strategy_errors()
