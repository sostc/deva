"""
资金流向分析策略

基于 realtime_quant_5s_alltime 数据源，分析资金在行业和板块的流动
"""

import pandas as pd
import numpy as np
from collections import defaultdict
from typing import Dict, List, Optional, Any
import time


class CapitalFlowAnalyzer:
    """资金流向分析器"""
    
    def __init__(self, history_window: int = 60):
        """
        初始化
        
        Args:
            history_window: 历史数据窗口大小（秒），默认60秒
        """
        self.history_window = history_window
        self.history: List[Dict] = []
        self.last_timestamp: float = 0
        
        # 板块/行业映射（需要补充完整）
        self.sector_map: Dict[str, str] = {}
        self.industry_map: Dict[str, str] = {}
        
        # 缓存
        self._sector_cache: Dict[str, Dict] = defaultdict(dict)
        self._industry_cache: Dict[str, Dict] = defaultdict(dict)
    
    def load_sector_industry_data(self, sector_map: Dict[str, str], industry_map: Dict[str, str]):
        """
        加载板块和行业映射数据
        
        Args:
            sector_map: 股票代码 -> 板块名称
            industry_map: 股票代码 -> 行业名称
        """
        self.sector_map = sector_map
        self.industry_map = industry_map
    
    def update(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        更新数据并分析
        
        Args:
            df: 实时行情数据
            
        Returns:
            分析结果
        """
        timestamp = time.time()
        
        # 添加时间戳和涨跌幅
        df = df.copy()
        df['timestamp'] = timestamp
        df['p_change'] = (df['now'].astype(float) - df['close'].astype(float)) / df['close'].astype(float) * 100
        df['volume'] = df['volume'].astype(float)
        df['turnover'] = df['turnover'].astype(float)
        
        # 添加板块和行业
        df['sector'] = df.index.map(lambda x: self.sector_map.get(x, '未知板块'))
        df['industry'] = df.index.map(lambda x: self.industry_map.get(x, '未知行业'))
        
        # 保存历史
        self.history.append({
            'timestamp': timestamp,
            'df': df,
        })
        
        # 清理过期数据
        cutoff = timestamp - self.history_window
        self.history = [h for h in self.history if h['timestamp'] > cutoff]
        
        # 执行分析
        result = {
            'timestamp': timestamp,
            'sector_flow': self._analyze_sector_flow(df),
            'industry_flow': self._analyze_industry_flow(df),
            'hot_stocks': self._find_hot_stocks(df),
            'capital_inflow': self._detect_capital_inflow(df),
            'signals': [],
        }
        
        # 生成信号
        result['signals'] = self._generate_signals(result)
        
        self.last_timestamp = timestamp
        
        return result
    
    def _analyze_sector_flow(self, df: pd.DataFrame) -> Dict[str, Dict]:
        """分析板块资金流向"""
        sector_stats = {}
        
        for sector in df['sector'].unique():
            sector_df = df[df['sector'] == sector]
            
            # 计算板块统计
            avg_p_change = sector_df['p_change'].mean()
            total_volume = sector_df['volume'].sum()
            total_turnover = sector_df['turnover'].sum()
            
            # 计算涨跌家数
            up_count = len(sector_df[sector_df['p_change'] > 0])
            down_count = len(sector_df[sector_df['p_change'] < 0])
            
            # 计算强势股比例
            strong_count = len(sector_df[sector_df['p_change'] > 2])
            
            sector_stats[sector] = {
                'avg_p_change': round(avg_p_change, 2),
                'total_volume': total_volume,
                'total_turnover': total_turnover,
                'up_count': up_count,
                'down_count': down_count,
                'strong_count': strong_count,
                'stock_count': len(sector_df),
                'strength': round((up_count - down_count) / max(len(sector_df), 1) * 100, 2),
            }
        
        return sector_stats
    
    def _analyze_industry_flow(self, df: pd.DataFrame) -> Dict[str, Dict]:
        """分析行业资金流向"""
        industry_stats = {}
        
        for industry in df['industry'].unique():
            industry_df = df[df['industry'] == industry]
            
            avg_p_change = industry_df['p_change'].mean()
            total_volume = industry_df['volume'].sum()
            total_turnover = industry_df['turnover'].sum()
            
            up_count = len(industry_df[industry_df['p_change'] > 0])
            down_count = len(industry_df[industry_df['p_change'] < 0])
            
            industry_stats[industry] = {
                'avg_p_change': round(avg_p_change, 2),
                'total_volume': total_volume,
                'total_turnover': total_turnover,
                'up_count': up_count,
                'down_count': down_count,
                'stock_count': len(industry_df),
                'strength': round((up_count - down_count) / max(len(industry_df), 1) * 100, 2),
            }
        
        return industry_stats
    
    def _find_hot_stocks(self, df: pd.DataFrame) -> List[Dict]:
        """发现热门股票"""
        # 按成交额排序
        df_sorted = df.nlargest(20, 'turnover')
        
        hot_stocks = []
        for idx, row in df_sorted.iterrows():
            hot_stocks.append({
                'code': idx,
                'name': row['name'],
                'p_change': round(row['p_change'], 2),
                'volume': row['volume'],
                'turnover': row['turnover'],
                'sector': row['sector'],
                'industry': row['industry'],
            })
        
        return hot_stocks
    
    def _detect_capital_inflow(self, df: pd.DataFrame) -> Dict[str, List]:
        """检测资金流入"""
        inflow_stocks = []
        outflow_stocks = []
        
        # 基于涨跌幅和成交量判断资金流向
        for idx, row in df.iterrows():
            p_change = row['p_change']
            volume = row['volume']
            
            # 获取历史数据
            if len(self.history) > 1:
                prev_df = self.history[-2]['df']
                if idx in prev_df.index:
                    prev_volume = prev_df.loc[idx, 'volume']
                    volume_change = (volume - prev_volume) / max(prev_volume, 1)
                    
                    # 放量上涨 = 资金流入
                    if p_change > 1 and volume_change > 0.1:
                        inflow_stocks.append({
                            'code': idx,
                            'name': row['name'],
                            'p_change': round(p_change, 2),
                            'volume_change': round(volume_change * 100, 2),
                            'sector': row['sector'],
                            'industry': row['industry'],
                        })
                    
                    # 放量下跌 = 资金流出
                    elif p_change < -1 and volume_change > 0.1:
                        outflow_stocks.append({
                            'code': idx,
                            'name': row['name'],
                            'p_change': round(p_change, 2),
                            'volume_change': round(volume_change * 100, 2),
                            'sector': row['sector'],
                            'industry': row['industry'],
                        })
        
        return {
            'inflow': sorted(inflow_stocks, key=lambda x: x['p_change'], reverse=True)[:10],
            'outflow': sorted(outflow_stocks, key=lambda x: x['p_change'])[:10],
        }
    
    def _generate_signals(self, result: Dict) -> List[Dict]:
        """生成交易信号"""
        signals = []
        
        # 板块轮动信号
        sector_flow = result['sector_flow']
        sorted_sectors = sorted(sector_flow.items(), key=lambda x: x[1]['strength'], reverse=True)
        
        if sorted_sectors:
            top_sector = sorted_sectors[0]
            if top_sector[1]['strength'] > 50 and top_sector[1]['avg_p_change'] > 1:
                signals.append({
                    'type': 'sector_rotation',
                    'level': 'strong',
                    'message': f"板块【{top_sector[0]}】强势，强度{top_sector[1]['strength']}%，涨幅{top_sector[1]['avg_p_change']}%",
                    'data': top_sector[1],
                })
        
        # 行业轮动信号
        industry_flow = result['industry_flow']
        sorted_industries = sorted(industry_flow.items(), key=lambda x: x[1]['strength'], reverse=True)
        
        if sorted_industries:
            top_industry = sorted_industries[0]
            if top_industry[1]['strength'] > 50 and top_industry[1]['avg_p_change'] > 1:
                signals.append({
                    'type': 'industry_rotation',
                    'level': 'strong',
                    'message': f"行业【{top_industry[0]}】强势，强度{top_industry[1]['strength']}%，涨幅{top_industry[1]['avg_p_change']}%",
                    'data': top_industry[1],
                })
        
        # 资金流入信号
        inflow = result['capital_inflow']['inflow']
        if len(inflow) >= 3:
            signals.append({
                'type': 'capital_inflow',
                'level': 'medium',
                'message': f"检测到{len(inflow)}只股票资金快速流入",
                'data': inflow[:5],
            })
        
        return signals


class QuickCapitalCapture:
    """快速资金捕获策略 - 几十秒级别"""
    
    def __init__(self, window_size: int = 12):
        """
        初始化
        
        Args:
            window_size: 窗口大小（数据点数），12个点 = 60秒
        """
        self.window_size = window_size
        self.price_history: Dict[str, List[float]] = defaultdict(list)
        self.volume_history: Dict[str, List[float]] = defaultdict(list)
        self.p_change_history: Dict[str, List[float]] = defaultdict(list)
    
    def update(self, df: pd.DataFrame) -> List[Dict]:
        """
        更新数据并检测信号
        
        Args:
            df: 实时行情数据
            
        Returns:
            检测到的信号列表
        """
        signals = []
        
        for idx, row in df.iterrows():
            code = idx
            now_price = float(row['now'])
            volume = float(row['volume'])
            p_change = (now_price - float(row['close'])) / float(row['close']) * 100
            
            # 更新历史
            self.price_history[code].append(now_price)
            self.volume_history[code].append(volume)
            self.p_change_history[code].append(p_change)
            
            # 保持窗口大小
            if len(self.price_history[code]) > self.window_size:
                self.price_history[code] = self.price_history[code][-self.window_size:]
                self.volume_history[code] = self.volume_history[code][-self.window_size:]
                self.p_change_history[code] = self.p_change_history[code][-self.window_size:]
            
            # 检测信号
            signal = self._detect_signal(code, row['name'])
            if signal:
                signals.append(signal)
        
        return sorted(signals, key=lambda x: x['score'], reverse=True)[:10]
    
    def _detect_signal(self, code: str, name: str) -> Optional[Dict]:
        """检测单个股票的信号"""
        if len(self.price_history[code]) < self.window_size:
            return None
        
        prices = self.price_history[code]
        volumes = self.volume_history[code]
        p_changes = self.p_change_history[code]
        
        # 计算价格变化速度
        price_velocity = (prices[-1] - prices[0]) / prices[0] * 100 if prices[0] != 0 else 0
        
        # 计算成交量变化
        avg_volume = np.mean(volumes[:-3]) if len(volumes) > 3 else volumes[0]
        current_volume = volumes[-1]
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0
        
        # 计算涨跌幅加速度
        if len(p_changes) >= 3:
            acceleration = p_changes[-1] - p_changes[-3]
        else:
            acceleration = 0
        
        # 计算综合得分
        score = 0
        
        # 价格快速上涨
        if price_velocity > 1:
            score += 30
        elif price_velocity > 0.5:
            score += 20
        elif price_velocity > 0.2:
            score += 10
        
        # 放量
        if volume_ratio > 3:
            score += 30
        elif volume_ratio > 2:
            score += 20
        elif volume_ratio > 1.5:
            score += 10
        
        # 加速度
        if acceleration > 0.5:
            score += 20
        elif acceleration > 0.2:
            score += 10
        
        # 当前涨跌幅
        current_p_change = p_changes[-1]
        if current_p_change > 5:
            score += 20
        elif current_p_change > 3:
            score += 15
        elif current_p_change > 1:
            score += 10
        
        if score >= 50:
            return {
                'code': code,
                'name': name,
                'score': score,
                'p_change': round(current_p_change, 2),
                'price_velocity': round(price_velocity, 2),
                'volume_ratio': round(volume_ratio, 2),
                'acceleration': round(acceleration, 2),
                'signal_type': 'quick_capture',
                'message': f"【{name}】快速异动，得分{score}，涨幅{current_p_change:.2f}%，量比{volume_ratio:.2f}",
            }
        
        return None


class MinuteLevelFlow:
    """分钟级别资金流向分析"""
    
    def __init__(self, window_minutes: int = 5):
        """
        初始化
        
        Args:
            window_minutes: 窗口大小（分钟）
        """
        self.window_minutes = window_minutes
        self.minute_data: Dict[str, List[Dict]] = defaultdict(list)
        self.last_minute: int = -1
    
    def update(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        更新数据
        
        Args:
            df: 实时行情数据
            
        Returns:
            分析结果
        """
        current_minute = int(time.time() // 60)
        
        # 新的一分钟，聚合数据
        if current_minute != self.last_minute:
            for idx, row in df.iterrows():
                code = idx
                self.minute_data[code].append({
                    'minute': current_minute,
                    'open': float(row['now']),
                    'close': float(row['now']),
                    'high': float(row['high']),
                    'low': float(row['low']),
                    'volume': float(row['volume']),
                    'turnover': float(row['turnover']),
                    'p_change': (float(row['now']) - float(row['close'])) / float(row['close']) * 100,
                })
            
            self.last_minute = current_minute
        
        # 清理过期数据
        cutoff_minute = current_minute - self.window_minutes
        for code in list(self.minute_data.keys()):
            self.minute_data[code] = [
                d for d in self.minute_data[code] if d['minute'] > cutoff_minute
            ]
        
        # 分析
        return self._analyze()
    
    def _analyze(self) -> Dict[str, Any]:
        """分析分钟级别资金流向"""
        sector_flow = defaultdict(lambda: {
            'total_volume': 0,
            'total_turnover': 0,
            'avg_p_change': 0,
            'count': 0,
        })
        
        signals = []
        
        for code, data_list in self.minute_data.items():
            if len(data_list) < 2:
                continue
            
            # 计算分钟级别的变化
            first = data_list[0]
            last = data_list[-1]
            
            volume_change = last['volume'] - first['volume']
            p_change = last['p_change']
            
            # 检测连续上涨或下跌
            consecutive_up = 0
            consecutive_down = 0
            
            for i in range(1, len(data_list)):
                if data_list[i]['p_change'] > data_list[i-1]['p_change']:
                    consecutive_up += 1
                    consecutive_down = 0
                elif data_list[i]['p_change'] < data_list[i-1]['p_change']:
                    consecutive_down += 1
                    consecutive_up = 0
            
            # 生成信号
            if consecutive_up >= 3 and p_change > 1:
                signals.append({
                    'code': code,
                    'type': 'consecutive_up',
                    'minutes': consecutive_up,
                    'p_change': round(p_change, 2),
                    'message': f"连续{consecutive_up}分钟上涨，涨幅{p_change:.2f}%",
                })
            
            elif consecutive_down >= 3 and p_change < -1:
                signals.append({
                    'code': code,
                    'type': 'consecutive_down',
                    'minutes': consecutive_down,
                    'p_change': round(p_change, 2),
                    'message': f"连续{consecutive_down}分钟下跌，跌幅{p_change:.2f}%",
                })
        
        return {
            'signals': signals[:10],
            'minute': self.last_minute,
        }


# 示例使用代码
def fetch_data():
    """
    数据源处理函数示例
    """
    from deva.naja.datasource import get_datasource_manager
    
    mgr = get_datasource_manager()
    entry = mgr.get('realtime_quant_5s_alltime')
    
    if not entry or not entry._latest_data:
        return None
    
    df = entry._latest_data
    
    # 初始化分析器（需要持久化）
    analyzer = CapitalFlowAnalyzer(history_window=60)
    
    # 加载板块行业数据（需要补充）
    # analyzer.load_sector_industry_data(sector_map, industry_map)
    
    # 分析
    result = analyzer.update(df)
    
    return result
