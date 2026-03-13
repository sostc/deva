"""
添加 Mock 新闻数据源到 Naja 并绑定到龙虾思想雷达策略

定时器类型：每隔1秒通过 fetch_data 返回一个新闻
"""

import sys
sys.path.insert(0, '/Users/spark/pycharmproject/deva')

import time
import random
from datetime import datetime
from deva import NB


def create_and_register_datasource():
    """创建并注册 Mock 新闻数据源"""
    
    # 保存到 naja 数据源数据库
    db = NB('naja_datasources')
    
    ds_id = "mock_news_finance"
    
    # 检查是否已存在
    if ds_id in db:
        print(f"数据源 {ds_id} 已存在，将更新配置")
    
    # 构建数据源记录 - 定时器类型
    ds_record = {
        "metadata": {
            "id": ds_id,
            "name": "财经新闻模拟源",
            "source_type": "timer",  # 改为定时器类型
            "description": "模拟财经新闻数据源，每3秒生成一条新闻",
            "created_at": time.time(),
            "updated_at": time.time(),
            "config": {
                "interval": 3.0,  # 每3秒一条新闻
            },
        },
        "func_code": '''
"""
Mock 新闻数据源 - 定时器类型
每隔3秒通过 fetch_data 返回一个新闻
"""
import sys
sys.path.insert(0, '/Users/spark/pycharmproject/deva')

import time
import random
from datetime import datetime

# 新闻模板库
NEWS_TEMPLATES = [
    "{company}股价今日上涨{percent}%，市场信心增强",
    "央行宣布降准{percent}%，释放流动性约{amount}亿元",
    "{index}指数突破{points}点，创{period}新高",
    "{company}发布财报，Q{quarter}营收同比增长{percent}%",
    "北向资金今日净流入{amount}亿元，连续{days}日净流入",
    "{sector}板块集体走强，{company}领涨",
    "美联储宣布维持利率不变，符合市场预期",
    "人民币汇率突破{rate}，创{period}新高",
    "{company}发布新一代AI芯片，算力提升{percent}%",
    "{company}宣布投资{amount}亿元建设数据中心",
    "OpenAI发布GPT-{version}，性能大幅提升",
    "新能源汽车销量同比增长{percent}%，渗透率突破{percent2}%",
    "{company}宣布建设{amount}GWh动力电池工厂",
    "光伏组件价格下降{percent}%，装机量创新高",
    "半导体设备国产化率提升至{percent}%",
]

COMPANIES = ["腾讯", "阿里", "字节", "华为", "比亚迪", "宁德时代", "茅台", "美团", "小米", "百度", "京东", "拼多多"]
SECTORS = ["新能源", "半导体", "医药", "消费", "金融", "地产", "传媒", "军工"]
INDICES = ["沪深300", "上证指数", "深证成指", "创业板指", "科创50"]

# 使用类来维护状态
class NewsGenerator:
    def __init__(self):
        self.count = 0
    
    def create_news(self):
        self.count += 1
        
        template = random.choice(NEWS_TEMPLATES)
        
        news_content = template.format(
            company=random.choice(COMPANIES),
            percent=random.randint(5, 50),
            percent2=random.randint(20, 80),
            amount=random.randint(10, 1000),
            points=random.randint(3000, 5000),
            period=random.choice(["年内", "月内", "季度", "半年"]),
            quarter=random.randint(1, 4),
            days=random.randint(3, 15),
            sector=random.choice(SECTORS),
            index=random.choice(INDICES),
            rate=round(random.uniform(6.5, 7.5), 2),
            version=random.randint(4, 6),
        )
        
        news_item = {
            "id": f"news_{int(time.time() * 1000)}_{self.count}",
            "timestamp": time.time(),
            "datetime": datetime.now().isoformat(),
            "type": "finance",
            "title": news_content,
            "content": news_content + "。分析师认为，这一趋势反映了市场的积极变化。",
            "importance": random.choice(["高", "中", "低"]),
            "sentiment": random.choice(["positive", "neutral", "negative"]),
            "keywords": [random.choice(COMPANIES), random.choice(SECTORS)],
        }
        
        return news_item

# 创建生成器实例
_generator = NewsGenerator()

def fetch_data():
    """
    获取数据 - 定时器类型
    每隔3秒被调用一次，返回一条新闻
    """
    news = _generator.create_news()
    return news

def get_stream():
    """获取数据流（兼容接口，定时器类型不使用）"""
    return None
''',
        "state": {
            "status": "stopped",
            "last_run": None,
        }
    }
    
    # 保存
    db[ds_id] = ds_record
    
    print(f"✅ Mock 新闻数据源已注册")
    print(f"   ID: {ds_id}")
    print(f"   名称: 财经新闻模拟源")
    print(f"   类型: 定时器")
    print(f"   生成间隔: 1秒")
    
    return ds_id


def bind_to_lobster_strategy(ds_id: str):
    """绑定数据源到龙虾思想雷达策略"""
    
    db = NB('naja_strategies')
    
    for key, value in db.items():
        if isinstance(value, dict):
            name = value.get('metadata', {}).get('name', '')
            if name == '龙虾思想雷达':
                print(f"\n找到策略: {name} (ID: {key})")
                
                # 获取当前绑定的数据源
                current_ids = value.get('metadata', {}).get('bound_datasource_ids', [])
                
                # 添加新的数据源（如果不存在）
                if ds_id not in current_ids:
                    current_ids.append(ds_id)
                    value['metadata']['bound_datasource_ids'] = current_ids
                    value['metadata']['updated_at'] = time.time()
                    
                    # 保存
                    db[key] = value
                    
                    print(f"✅ 数据源已绑定到策略")
                    print(f"   绑定数据源: {current_ids}")
                else:
                    print(f"ℹ️ 数据源已绑定，无需重复绑定")
                
                return True
    
    print("❌ 未找到龙虾思想雷达策略")
    return False


def main():
    """主函数"""
    print("=" * 60)
    print("添加 Mock 新闻数据源到 Naja (定时器类型)")
    print("=" * 60)
    print()
    
    # 1. 创建并注册数据源
    ds_id = create_and_register_datasource()
    
    # 2. 绑定到龙虾思想雷达策略
    bind_to_lobster_strategy(ds_id)
    
    print()
    print("=" * 60)
    print("✅ 完成")
    print("=" * 60)
    print()
    print("请重启 naja 以应用更改:")
    print("  python -m deva.naja")
    print()
    print("重启后，Mock 新闻数据源将每1秒生成一条新闻")


if __name__ == '__main__':
    main()
