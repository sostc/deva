"""
资金流向分析数据源示例

使用方法：
1. 创建一个新的数据源，类型选择"定时器"
2. 间隔设置为 5 秒
3. 将此代码复制到数据源代码中
4. 补充板块和行业映射数据
"""

# ========== 板块和行业映射（需要补充完整）==========
SECTOR_MAP = {
    # 示例：股票代码 -> 板块名称
    # '000001': '金融',
    # '000002': '房地产',
    # ...
}

INDUSTRY_MAP = {
    # 示例：股票代码 -> 行业名称
    # '000001': '银行',
    # '000002': '房地产开发',
    # ...
}


# ========== 分析器实例（持久化）==========
_analyzer = None
_quick_capture = None
_minute_flow = None


def _get_analyzer():
    """获取或创建分析器实例"""
    global _analyzer, _quick_capture, _minute_flow
    
    if _analyzer is None:
        from deva.naja.datasource.strategies import (
            CapitalFlowAnalyzer,
            QuickCapitalCapture,
            MinuteLevelFlow,
        )
        
        _analyzer = CapitalFlowAnalyzer(history_window=60)
        _analyzer.load_sector_industry_data(SECTOR_MAP, INDUSTRY_MAP)
        
        _quick_capture = QuickCapitalCapture(window_size=12)
        _minute_flow = MinuteLevelFlow(window_minutes=5)
    
    return _analyzer, _quick_capture, _minute_flow


def fetch_data():
    """
    资金流向分析主函数
    
    订阅 realtime_quant_5s_alltime 数据源，分析资金流向
    """
    import pandas as pd
    from deva.naja.datasource import get_datasource_manager
    from deva import NB
    
    # 获取原始数据
    mgr = get_datasource_manager()
    entry = mgr.get('realtime_quant_5s_alltime')
    
    if not entry:
        return {'error': '数据源 realtime_quant_5s_alltime 不存在'}
    
    # 获取最新数据
    raw_data = entry._latest_data
    
    if raw_data is None:
        return {'error': '无最新数据'}
    
    # 转换为 DataFrame
    if isinstance(raw_data, pd.DataFrame):
        df = raw_data
    else:
        df = pd.DataFrame(raw_data).T
    
    # 获取分析器
    analyzer, quick_capture, minute_flow = _get_analyzer()
    
    # 执行分析
    result = {
        'timestamp': pd.Timestamp.now().isoformat(),
        'stock_count': len(df),
    }
    
    # 1. 板块/行业资金流向分析
    flow_result = analyzer.update(df)
    result['sector_flow'] = flow_result['sector_flow']
    result['industry_flow'] = flow_result['industry_flow']
    result['capital_inflow'] = flow_result['capital_inflow']
    result['signals'] = flow_result['signals']
    
    # 2. 快速资金捕获（几十秒级别）
    quick_signals = quick_capture.update(df)
    result['quick_capture'] = quick_signals[:5]
    
    # 3. 分钟级别分析
    minute_result = minute_flow.update(df)
    result['minute_signals'] = minute_result['signals']
    
    # 4. 热门股票
    result['hot_stocks'] = flow_result['hot_stocks'][:10]
    
    # 5. 汇总信号
    all_signals = []
    
    # 板块轮动信号
    for signal in result['signals']:
        if signal['type'] == 'sector_rotation':
            all_signals.append({
                'level': 'high',
                'type': '板块轮动',
                'message': signal['message'],
            })
        elif signal['type'] == 'industry_rotation':
            all_signals.append({
                'level': 'high',
                'type': '行业轮动',
                'message': signal['message'],
            })
        elif signal['type'] == 'capital_inflow':
            all_signals.append({
                'level': 'medium',
                'type': '资金流入',
                'message': signal['message'],
            })
    
    # 快速捕获信号
    for signal in result['quick_capture'][:3]:
        all_signals.append({
            'level': 'high',
            'type': '快速异动',
            'message': signal['message'],
        })
    
    # 分钟级别信号
    for signal in result['minute_signals'][:3]:
        all_signals.append({
            'level': 'medium',
            'type': '分钟趋势',
            'message': signal['message'],
        })
    
    result['all_signals'] = all_signals
    
    # 保存到数据库（可选）
    # db = NB('capital_flow_analysis')
    # db[result['timestamp']] = result
    
    return result


# ========== 简化版本（直接分析，不依赖其他数据源）==========
def fetch_data_simple():
    """
    简化版本：直接获取实时行情并分析
    """
    import easyquotation
    import pandas as pd
    import numpy as np
    from collections import defaultdict
    
    # 获取实时行情
    quotation_engine = easyquotation.use("sina")
    q1 = quotation_engine.market_snapshot(prefix=False)
    df = pd.DataFrame(q1).T
    
    # 过滤无效数据
    df = df[(True ^ df["close"].isin([0]))]
    df = df[(True ^ df["now"].isin([0]))]
    
    # 计算涨跌幅
    df['p_change'] = (df['now'].astype(float) - df['close'].astype(float)) / df['close'].astype(float) * 100
    df['volume'] = df['volume'].astype(float)
    df['turnover'] = df['turnover'].astype(float)
    
    # 按涨跌幅排序
    top_gainers = df.nlargest(10, 'p_change')[['name', 'p_change', 'volume', 'turnover']]
    top_losers = df.nsmallest(10, 'p_change')[['name', 'p_change', 'volume', 'turnover']]
    
    # 按成交额排序
    top_volume = df.nlargest(10, 'turnover')[['name', 'p_change', 'volume', 'turnover']]
    
    # 统计
    up_count = len(df[df['p_change'] > 0])
    down_count = len(df[df['p_change'] < 0])
    flat_count = len(df[df['p_change'] == 0])
    
    # 涨停/跌停
    limit_up = len(df[df['p_change'] >= 9.9])
    limit_down = len(df[df['p_change'] <= -9.9])
    
    # 强势股（涨幅>3%且放量）
    strong_stocks = df[(df['p_change'] > 3) & (df['turnover'] > df['turnover'].median())]
    strong_stocks = strong_stocks.nlargest(10, 'p_change')[['name', 'p_change', 'volume', 'turnover']]
    
    return {
        'timestamp': pd.Timestamp.now().isoformat(),
        'stock_count': len(df),
        'market_breadth': {
            'up': up_count,
            'down': down_count,
            'flat': flat_count,
            'limit_up': limit_up,
            'limit_down': limit_down,
            'strength': round((up_count - down_count) / len(df) * 100, 2),
        },
        'top_gainers': top_gainers.to_dict('records'),
        'top_losers': top_losers.to_dict('records'),
        'top_volume': top_volume.to_dict('records'),
        'strong_stocks': strong_stocks.to_dict('records'),
    }
