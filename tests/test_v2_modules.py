"""验证所有 V2 模块"""

print('='*60)
print('验证 V2 模块导入')
print('='*60)

# 1. DataSource V2
print('\n1. DataSource V2:')
from deva.admin_ui.datasource import (
    DataSourceEntry,
    DataSourceManagerV2,
    get_datasource_manager_v2,
)
ds_mgr = get_datasource_manager_v2()
print(f'   Manager: {ds_mgr}')
print(f'   DataSourceEntry: {DataSourceEntry}')
print(f'   Stats: {ds_mgr.get_stats()}')

# 2. Task V2
print('\n2. Task V2:')
from deva.admin_ui.tasks import (
    TaskEntry,
    TaskManagerV2,
    get_task_manager_v2,
)
task_mgr = get_task_manager_v2()
print(f'   Manager: {task_mgr}')
print(f'   TaskEntry: {TaskEntry}')
print(f'   Stats: {task_mgr.get_stats()}')

# 3. Strategy V2
print('\n3. Strategy V2:')
from deva.admin_ui.strategy import (
    StrategyEntry,
    StrategyManagerV2,
    get_strategy_manager_v2,
)
strategy_mgr = get_strategy_manager_v2()
print(f'   Manager: {strategy_mgr}')
print(f'   StrategyEntry: {StrategyEntry}')
print(f'   Stats: {strategy_mgr.get_stats()}')

# 4. Dictionary V2 (已存在)
print('\n4. Dictionary V2:')
from deva.admin_ui.dictionary import (
    DictionaryEntry,
    DictionaryManager,
    get_dictionary_manager_v2,
)
dict_mgr = get_dictionary_manager_v2()
print(f'   Manager: {dict_mgr}')
print(f'   DictionaryEntry: {DictionaryEntry}')
print(f'   Stats: {dict_mgr.get_stats()}')

print('\n' + '='*60)
print('所有 V2 模块导入成功!')
print('='*60)

# 测试创建和恢复
print('\n测试创建和自动恢复:')
print('-'*60)

# 创建 DataSource
ds_result = ds_mgr.create(
    name="test_ds_v2",
    func_code="""
def fetch_data():
    import time
    return {"ts": time.time(), "value": 42}
""",
    interval=5.0,
)
print(f'创建 DataSource: {ds_result.get("success")}')

# 创建 Task
task_result = task_mgr.create(
    name="test_task_v2",
    func_code="""
def execute():
    import time
    print(f"Task executed at {time.time()}")
    return "done"
""",
    task_type="interval",
    interval_seconds=60.0,
)
print(f'创建 Task: {task_result.get("success")}')

# 创建 Strategy
strategy_result = strategy_mgr.create(
    name="test_strategy_v2",
    func_code="""
def process(data):
    return {"processed": True, "input": str(data)[:100]}
""",
    compute_mode="record",
)
print(f'创建 Strategy: {strategy_result.get("success")}')

# 创建 Dictionary
dict_result = dict_mgr.create(
    name="test_dict_v2",
    func_code="""
def fetch_data():
    import pandas as pd
    return pd.DataFrame({"code": ["000001", "000002"], "name": ["平安银行", "万科A"]})
""",
    schedule_type="interval",
    interval_seconds=300,
)
print(f'创建 Dictionary: {dict_result.get("success")}')

print('\n测试启动和停止:')
print('-'*60)

# 启动
if ds_result.get("success"):
    ds_id = ds_result["id"]
    start_result = ds_mgr.start(ds_id)
    print(f'DataSource 启动: {start_result.get("success")}')
    
    # 检查恢复信息
    entry = ds_mgr.get(ds_id)
    print(f'  was_running: {entry.was_running}')
    print(f'  is_running: {entry.is_running}')
    
    # 停止
    stop_result = ds_mgr.stop(ds_id)
    print(f'DataSource 停止: {stop_result.get("success")}')
    print(f'  was_running after stop: {entry.was_running}')

print('\n' + '='*60)
print('测试完成!')
print('='*60)
