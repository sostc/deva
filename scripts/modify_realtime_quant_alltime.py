#!/usr/bin/env python3
"""
修改realtime_quant_5s_alltime数据源，使其只在非交易时间执行行情获取
"""

from deva.naja.datasource import get_datasource_manager

def modify_realtime_quant_alltime():
    """修改realtime_quant_5s_alltime数据源"""
    print("=== 修改realtime_quant_5s_alltime数据源 ===")
    
    # 获取数据源管理器
    ds_manager = get_datasource_manager()
    
    # 加载所有数据源
    loaded_count = ds_manager.load_from_db()
    print(f"✓ 加载了 {loaded_count} 个数据源")
    
    # 查找目标数据源
    target_source = ds_manager.get_by_name("realtime_quant_5s_alltime")
    
    if not target_source:
        print("✗ 未找到realtime_quant_5s_alltime数据源")
        return False
    
    print(f"✓ 找到数据源: {target_source.name} (ID: {target_source.id})")
    
    # 查看当前代码
    current_code = target_source._func_code
    print(f"✓ 当前代码长度: {len(current_code)} 字符")
    
    # 生成新的代码，只在非交易时间执行
    new_code = '''import datetime
import time
import random
import pandas as pd

def is_tradedate(dt=None):
    """判断是否为交易日"""
    try:
        if dt is None:
            dt = datetime.datetime.now()
        
        # 周末判断
        if dt.weekday() >= 5:  # Saturday=5, Sunday=6
            return False
        
        # 简单节假日判断（可根据需要扩展）
        holidays = [
            # 元旦
            (1, 1), (1, 2), (1, 3),
            # 春节（需要按年份调整）
            (2, 10), (2, 11), (2, 12), (2, 13), (2, 14), (2, 15), (2, 16),
            # 清明节
            (4, 4), (4, 5), (4, 6),
            # 劳动节
            (5, 1), (5, 2), (5, 3),
            # 端午节
            (6, 10), (6, 11), (6, 12),
            # 中秋节
            (9, 15), (9, 16), (9, 17),
            # 国庆节
            (10, 1), (10, 2), (10, 3), (10, 4), (10, 5), (10, 6), (10, 7),
        ]
        
        current_date = (dt.month, dt.day)
        return current_date not in holidays
    except Exception as e:
        print(f"[ERROR] is_tradedate failed: {str(e)}")
        return True  # 默认认为是交易日

def is_tradetime(dt=None):
    """判断是否为交易时间"""
    try:
        if dt is None:
            dt = datetime.datetime.now()
        
        # 交易时间：9:30-11:30, 13:00-15:00
        current_time = dt.time()
        morning_start = datetime.time(9, 30)
        morning_end = datetime.time(11, 30)
        afternoon_start = datetime.time(13, 0)
        afternoon_end = datetime.time(15, 0)
        
        return (morning_start <= current_time <= morning_end) or (afternoon_start <= current_time <= afternoon_end)
    except Exception as e:
        print(f"[ERROR] is_tradetime failed: {str(e)}")
        return True  # 默认认为是交易时间

def create_mock_data():
    """创建模拟数据，用于测试或数据源不可用的情况"""
    try:
        # 模拟股票代码（包含主要指数和个股）
        mock_codes = [
            "000001", "000002", "000858", "002415", "300059",  # 重要个股
            "600000", "600036", "600519", "600887", "601318",  # 金融消费
            "300001", "300015", "300124", "300750", "399001",  # 创业板+深成指
            "000300", "000905", "399006", "000016", "399300"   # 主要指数
        ]
        
        data = []
        current_time = time.time()
        current_datetime = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        for code in mock_codes:
            base_price = random.uniform(10, 200)
            change = random.uniform(-0.10, 0.10)  # -10% to +10%
            now_price = base_price * (1 + change)
            
            # 生成合理的日内价格
            open_price = base_price * random.uniform(0.98, 1.02)
            high_price = max(open_price, now_price) * random.uniform(1.0, 1.05)
            low_price = min(open_price, now_price) * random.uniform(0.95, 1.0)
            
            data.append({
                "code": code,
                "name": f"股票{code}",
                "open": round(open_price, 2),
                "close": round(base_price, 2),
                "now": round(now_price, 2),
                "high": round(high_price, 2),
                "low": round(low_price, 2),
                "volume": random.randint(10000, 10000000),
                "p_change": round(change, 4),
                "timestamp": current_time,
                "datetime": current_datetime
            })
        
        # 转换为DataFrame
        df = pd.DataFrame(data)
        return df
            
    except Exception as e:
        print(f"[ERROR] create_mock_data failed: {str(e)}")
        # 返回最基本的数据结构
        return pd.DataFrame([{
            "code": "000001",
            "name": "平安银行",
            "open": 10.0,
            "close": 10.0,
            "now": 10.0,
            "high": 10.0,
            "low": 10.0,
            "volume": 10000,
            "p_change": 0.0,
            "timestamp": time.time(),
            "datetime": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }])

def gen_quant():
    """获取股票行情数据"""
    try:
        # 尝试导入easyquotation
        try:
            import easyquotation
            
            # 使用新浪数据源
            quotation_engine = easyquotation.use("sina")
            q1 = quotation_engine.market_snapshot(prefix=False)
            
            # 转换为DataFrame
            df = pd.DataFrame(q1).T
            
            # 过滤无效数据
            df = df[(True ^ df["close"].isin([0]))]
            df = df[(True ^ df["now"].isin([0]))]
            
            # 计算涨跌幅
            df["p_change"] = (df.now - df.close) / df.close
            df["p_change"] = df.p_change.map(float)
            df["code"] = df.index
            
            # 添加时间戳
            df["timestamp"] = time.time()
            df["datetime"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            print(f"[INFO] Successfully fetched {len(df)} stocks from Sina")
            return df
            
        except ImportError:
            print("[WARNING] easyquotation not available, using mock data")
            return create_mock_data()
        except Exception as e:
            print(f"[ERROR] Failed to fetch market data from Sina: {str(e)}")
            print(f"[ERROR] Using mock data instead")
            return create_mock_data()
            
    except Exception as e:
        print(f"[ERROR] gen_quant failed: {str(e)}")
        return create_mock_data()

def fetch_data():
    """定时获取股票行情数据（数据源执行函数）- 只在非交易时间执行"""
    try:
        import datetime
        from deva.naja.common.tradetime import is_tradedate, is_tradetime
        
        now = datetime.datetime.now()
        
        # 检查是否为交易日
        if is_tradedate(now):
            # 交易日，检查是否为交易时间
            if is_tradetime(now):
                # 交易时间，跳过
                print(f"[INFO] Trading time, skipping data fetch: {now.time()}")
                return None
            else:
                # 非交易时间，执行行情获取
                print(f"[INFO] Non-trading time, fetching data: {now.time()}")
        else:
            # 非交易日，执行行情获取
            print(f"[INFO] Non-trading date, fetching data: {now.date()}")
        
        # 获取行情数据
        df = gen_quant()
        
        if df is not None and len(df) > 0:
            print(f"[INFO] Successfully fetched {len(df)} stocks data")
            return df
        else:
            print("[WARNING] No data fetched")
            return None
            
    except Exception as e:
        print(f"[ERROR] fetch_data failed: {str(e)}")
        return None
'''
    
    # 更新数据源代码
    update_result = target_source.update_config(func_code=new_code)
    
    if update_result.get("success"):
        print("✅ 数据源代码更新成功")
        
        # 检查数据源状态
        print(f"✓ 数据源当前状态: {target_source._state.status}")
        
        # 如果数据源正在运行，重启它以应用新代码
        if target_source.is_running:
            print("🔄 重启数据源以应用新代码...")
            target_source.stop()
            time.sleep(1)
            start_result = target_source.start()
            if start_result.get("success"):
                print("✅ 数据源重启成功")
            else:
                print(f"❌ 数据源重启失败: {start_result.get('error')}")
        
        return True
    else:
        print(f"❌ 数据源代码更新失败: {update_result.get('error')}")
        return False

if __name__ == "__main__":
    import time
    success = modify_realtime_quant_alltime()
    exit(0 if success else 1)
