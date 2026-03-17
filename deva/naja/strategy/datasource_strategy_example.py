"""数据源和策略联动使用示例

展示如何创建数据源、策略，并将它们联动使用。

完整流程:
1. 创建数据源 (DataSource)
2. 创建策略 (Strategy) 并绑定数据源
3. 启动数据源和策略
4. 数据流向: 数据源 → 策略 → 输出模块 (radar/memory/bandit)
"""

from deva.naja.datasource import get_datasource_manager
from deva.naja.strategy import get_strategy_manager


def create_tick_datasource():
    """示例1: 创建逐笔数据源"""
    ds_mgr = get_datasource_manager()

    result = ds_mgr.create(
        name="stock_tick_ds",
        source_type="custom",
        func_code='''
from datetime import datetime
import random

def fetch_data():
    """模拟获取逐笔数据"""
    now = datetime.now()
    return {
        "ts": now.timestamp(),
        "code": "000001",
        "price": 10.0 + random.random() * 0.1,
        "volume": random.randint(100, 10000),
        "direction": random.choice(["buy", "sell"]),
    }
''',
        interval=1.0,
        description="股票逐笔数据源",
        tags=["stock", "tick"],
        execution_mode="timer",
    )
    print(f"创建数据源: {result}")
    return result


def create_news_datasource():
    """示例2: 创建新闻数据源"""
    ds_mgr = get_datasource_manager()

    result = ds_mgr.create(
        name="news_ds",
        source_type="custom",
        func_code='''
from datetime import datetime
import random

NEWS_TOPICS = ["利好", "利空", "业绩", "并购", "政策"]

def fetch_data():
    """模拟获取新闻数据"""
    return {
        "ts": datetime.now().timestamp(),
        "title": f"新闻标题 {random.randint(1, 100)}",
        "content": f"这是新闻内容，包含 {random.choice(NEWS_TOPICS)} 相关信息",
        "source": "财经网",
    }
''',
        interval=5.0,
        description="新闻数据源",
        tags=["news"],
    )
    print(f"创建数据源: {result}")
    return result


def create_strategy_bound_to_datasource(datasource_id: str):
    """示例3: 创建策略并绑定数据源"""
    strategy_mgr = get_strategy_manager()

    result = strategy_mgr.create(
        name="anomaly_detection_strategy",
        func_code='''
def process(data, context=None):
    """异常检测策略"""
    ts = data.get("ts", 0)
    price = data.get("price", 0)

    # 简单异常检测
    is_anomaly = price > 10.1 or price < 9.9

    return {
        "signal_type": "anomaly",
        "score": 1.0 if is_anomaly else 0.0,
        "value": price,
        "message": "检测到异常" if is_anomaly else "正常",
    }
''',
        bound_datasource_id=datasource_id,
        strategy_type="legacy",
        handler_type="radar",
        description="异常检测策略",
    )
    print(f"创建策略: {result}")
    return result


def create_multi_datasource_strategy(datasource_ids: list):
    """示例4: 创建多数据源策略"""
    strategy_mgr = get_strategy_manager()

    result = strategy_mgr.create(
        name="combo_strategy",
        func_code='''
def process(data, context=None):
    """多数据源组合策略"""
    # data 包含多个数据源的数据
    tick = data.get("tick", {})
    news = data.get("news", {})

    return {
        "signal_type": "combo",
        "score": 0.5,
        "content": news.get("content", ""),
    }
''',
        bound_datasource_ids=datasource_ids,
        strategy_type="legacy",
        handler_type="memory",
    )
    print(f"创建多数据源策略: {result}")
    return result


def start_datasource_and_strategy(datasource_id: str, strategy_id: str):
    """示例5: 启动数据源和策略"""
    ds_mgr = get_datasource_manager()
    strategy_mgr = get_strategy_manager()

    ds = ds_mgr.get(datasource_id)
    strategy = strategy_mgr.get(strategy_id)

    if ds:
        ds.start()
        print(f"数据源 {ds.name} 已启动")

    if strategy:
        strategy.start()
        print(f"策略 {strategy.name} 已启动")


def workflow_example():
    """完整工作流程示例"""
    print("=" * 50)
    print("数据源和策略联动示例")
    print("=" * 50)

    # 1. 创建数据源
    ds_result = create_tick_datasource()
    if not ds_result.get("success"):
        print(f"创建数据源失败: {ds_result.get('error')}")
        return

    datasource_id = ds_result.get("id")

    # 2. 创建策略并绑定数据源
    strategy_result = create_strategy_bound_to_datasource(datasource_id)
    if not strategy_result.get("success"):
        print(f"创建策略失败: {strategy_result.get('error')}")
        return

    strategy_id = strategy_result.get("id")

    # 3. 启动数据源和策略
    start_datasource_and_strategy(datasource_id, strategy_id)

    print("\n✅ 数据流已建立:")
    print(f"   数据源 → 策略 → Radar/Memory/Bandit")
    print(f"   {datasource_id} → {strategy_id} → radar")


def multi_datasource_workflow():
    """多数据源工作流程示例"""
    print("=" * 50)
    print("多数据源策略示例")
    print("=" * 50)

    # 1. 创建多个数据源
    tick_result = create_tick_datasource()
    news_result = create_news_datasource()

    if not tick_result.get("success") or not news_result.get("success"):
        print("创建数据源失败")
        return

    datasource_ids = [tick_result["id"], news_result["id"]]

    # 2. 创建多数据源策略
    strategy_result = create_multi_datasource_strategy(datasource_ids)
    if not strategy_result.get("success"):
        print("创建策略失败")
        return

    strategy_id = strategy_result["id"]

    # 3. 启动
    strategy_mgr = get_strategy_manager()
    strategy = strategy_mgr.get(strategy_id)
    if strategy:
        strategy.start()

    print("\n✅ 多数据源流已建立:")
    print(f"   [数据源1, 数据源2] → 策略 → 输出")


if __name__ == "__main__":
    # 运行简单示例
    workflow_example()

    # 或运行多数据源示例
    # multi_datasource_workflow()
