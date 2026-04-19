#!/usr/bin/env python
"""
特征工程模块 - 智能选股策略系统 v2.0
提供丰富的技术指标、板块特征和市场情绪特征
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional
from collections import defaultdict


class TechnicalIndicatorCalculator:
    """技术指标计算器"""
    
    @staticmethod
    def calculate_ma(prices: List[float], window: int) -> float:
        """计算移动平均线"""
        if len(prices) < window:
            return prices[-1] if prices else 0.0
        return np.mean(prices[-window:])
    
    @staticmethod
    def calculate_ema(prices: List[float], window: int) -> float:
        """计算指数移动平均线"""
        if len(prices) < window:
            return prices[-1] if prices else 0.0
        
        alpha = 2 / (window + 1)
        ema = prices[0]
        for price in prices[1:]:
            ema = alpha * price + (1 - alpha) * ema
        return ema
    
    @staticmethod
    def calculate_rsi(prices: List[float], window: int = 14) -> float:
        """计算RSI相对强弱指标"""
        if len(prices) < window + 1:
            return 50.0
        
        deltas = np.diff(prices)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gain = np.mean(gains[-window:])
        avg_loss = np.mean(losses[-window:])
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    @staticmethod
    def calculate_macd(prices: List[float], fast: int = 12, slow: int = 26, signal: int = 9) -> Dict[str, float]:
        """计算MACD指标"""
        if len(prices) < slow:
            return {'macd': 0.0, 'signal': 0.0, 'histogram': 0.0}
        
        ema_fast = TechnicalIndicatorCalculator.calculate_ema(prices, fast)
        ema_slow = TechnicalIndicatorCalculator.calculate_ema(prices, slow)
        
        macd_line = ema_fast - ema_slow
        # 简化计算signal line
        signal_line = macd_line * 0.9  # 近似值
        histogram = macd_line - signal_line
        
        return {
            'macd': macd_line,
            'signal': signal_line,
            'histogram': histogram
        }
    
    @staticmethod
    def calculate_bollinger_bands(prices: List[float], window: int = 20, num_std: int = 2) -> Dict[str, float]:
        """计算布林带"""
        if len(prices) < window:
            return {'upper': prices[-1] if prices else 0.0, 
                   'middle': prices[-1] if prices else 0.0, 
                   'lower': prices[-1] if prices else 0.0,
                   'position': 0.5}
        
        recent_prices = prices[-window:]
        middle = np.mean(recent_prices)
        std = np.std(recent_prices)
        
        upper = middle + num_std * std
        lower = middle - num_std * std
        
        # 计算价格在布林带中的位置 (0-1)
        if upper == lower:
            position = 0.5
        else:
            position = (prices[-1] - lower) / (upper - lower)
        
        return {
            'upper': upper,
            'middle': middle,
            'lower': lower,
            'position': position
        }
    
    @staticmethod
    def calculate_atr(highs: List[float], lows: List[float], closes: List[float], window: int = 14) -> float:
        """计算ATR平均真实波幅"""
        if len(closes) < window + 1:
            return 0.0
        
        tr_list = []
        for i in range(1, len(closes)):
            high = highs[i] if i < len(highs) else closes[i]
            low = lows[i] if i < len(lows) else closes[i]
            prev_close = closes[i-1]
            
            tr1 = high - low
            tr2 = abs(high - prev_close)
            tr3 = abs(low - prev_close)
            
            tr = max(tr1, tr2, tr3)
            tr_list.append(tr)
        
        return np.mean(tr_list[-window:]) if tr_list else 0.0
    
    @staticmethod
    def calculate_kdj(highs: List[float], lows: List[float], closes: List[float], 
                     n: int = 9, m1: int = 3, m2: int = 3) -> Dict[str, float]:
        """计算KDJ指标"""
        if len(closes) < n:
            return {'k': 50.0, 'd': 50.0, 'j': 50.0}
        
        # 计算RSV
        recent_highs = highs[-n:] if len(highs) >= n else [closes[-1]] * n
        recent_lows = lows[-n:] if len(lows) >= n else [closes[-1]] * n
        
        highest = max(recent_highs)
        lowest = min(recent_lows)
        close = closes[-1]
        
        if highest == lowest:
            rsv = 50.0
        else:
            rsv = (close - lowest) / (highest - lowest) * 100
        
        # 简化计算K、D、J
        k = rsv
        d = rsv
        j = 3 * k - 2 * d
        
        return {'k': k, 'd': d, 'j': j}
    
    @staticmethod
    def calculate_obv(closes: List[float], volumes: List[float]) -> float:
        """计算OBV能量潮"""
        if len(closes) < 2 or len(volumes) < 2:
            return 0.0
        
        obv = 0
        for i in range(1, len(closes)):
            if closes[i] > closes[i-1]:
                obv += volumes[i]
            elif closes[i] < closes[i-1]:
                obv -= volumes[i]
        
        return obv
    
    @staticmethod
    def calculate_momentum(prices: List[float], window: int = 10) -> float:
        """计算动量指标"""
        if len(prices) < window + 1:
            return 0.0
        
        return (prices[-1] - prices[-window-1]) / prices[-window-1] * 100


class FeatureExtractor:
    """特征提取器"""
    
    def __init__(self, stock_blocks: Dict[str, List[str]] = None):
        self.stock_blocks = stock_blocks or {}
        self.block_data: Dict[str, List[str]] = {}
        self.calculator = TechnicalIndicatorCalculator()
        
        # 股票历史数据缓存
        self.stock_history: Dict[str, List[Dict]] = defaultdict(list)
    
    def load_block_data(self, block_file: str):
        """加载板块数据"""
        try:
            with open(block_file, 'r', encoding='gb2312', errors='ignore') as f:
                content = f.read()
            
            lines = content.split('\n')
            current_block = None
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                if line.startswith('#'):
                    current_block = line[1:].split(',')[0].strip()
                    self.block_data[current_block] = []
                elif current_block:
                    stocks = line.split(',')
                    for stock in stocks:
                        stock = stock.strip()
                        if stock and '#' in stock:
                            code = stock.split('#')[1]
                            self.block_data[current_block].append(code)
                            
                            if code not in self.stock_blocks:
                                self.stock_blocks[code] = []
                            if current_block not in self.stock_blocks[code]:
                                self.stock_blocks[code].append(current_block)
            
            print(f"[特征工程] 成功加载 {len(self.block_data)} 个板块, {len(self.stock_blocks)} 只股票")
            
        except Exception as e:
            print(f"[特征工程] 加载板块数据失败: {e}")
    
    def update_history(self, code: str, price: float, volume: float, 
                      high: float = None, low: float = None):
        """更新股票历史数据"""
        self.stock_history[code].append({
            'price': price,
            'volume': volume,
            'high': high if high else price,
            'low': low if low else price,
            'close': price
        })
        
        # 限制历史长度
        if len(self.stock_history[code]) > 50:
            self.stock_history[code] = self.stock_history[code][-50:]
    
    def extract_all_features(self, code: str, current_price: float, 
                            current_volume: float, df: pd.DataFrame = None) -> Dict[str, float]:
        """提取所有特征"""
        history = self.stock_history.get(code, [])
        
        if len(history) < 5:
            return self._extract_basic_features(code, current_price, current_volume)
        
        features = {}
        
        # 基础价格特征
        prices = [h['price'] for h in history]
        volumes = [h['volume'] for h in history]
        highs = [h['high'] for h in history]
        lows = [h['low'] for h in history]
        closes = [h['close'] for h in history]
        
        # 1. 趋势特征
        features['price_change_1d'] = (prices[-1] - prices[-2]) / prices[-2] * 100 if len(prices) >= 2 else 0
        features['price_change_5d'] = (prices[-1] - prices[-5]) / prices[-5] * 100 if len(prices) >= 5 else 0
        features['ma5_ratio'] = prices[-1] / self.calculator.calculate_ma(prices, 5) - 1
        features['ma10_ratio'] = prices[-1] / self.calculator.calculate_ma(prices, 10) - 1 if len(prices) >= 10 else 0
        features['ma20_ratio'] = prices[-1] / self.calculator.calculate_ma(prices, 20) - 1 if len(prices) >= 20 else 0
        
        # 2. 动量特征
        features['rsi_6'] = self.calculator.calculate_rsi(prices, 6)
        features['rsi_14'] = self.calculator.calculate_rsi(prices, 14)
        features['momentum_10'] = self.calculator.calculate_momentum(prices, 10)
        
        # 3. MACD特征
        macd = self.calculator.calculate_macd(prices)
        features['macd'] = macd['macd']
        features['macd_histogram'] = macd['histogram']
        
        # 4. 布林带特征
        bb = self.calculator.calculate_bollinger_bands(prices)
        features['bollinger_position'] = bb['position']
        
        # 5. 波动率特征
        features['volatility_20'] = np.std(prices[-20:]) / np.mean(prices[-20:]) * 100 if len(prices) >= 20 else 0
        features['atr_14'] = self.calculator.calculate_atr(highs, lows, closes, 14)
        
        # 6. KDJ特征
        kdj = self.calculator.calculate_kdj(highs, lows, closes)
        features['kdj_k'] = kdj['k']
        features['kdj_d'] = kdj['d']
        features['kdj_j'] = kdj['j']
        
        # 7. 成交量特征
        features['volume_ratio'] = volumes[-1] / np.mean(volumes[-5:]) if len(volumes) >= 5 else 1.0
        features['volume_ma5_ratio'] = volumes[-1] / self.calculator.calculate_ma(volumes, 5) if len(volumes) >= 5 else 1.0
        features['obv'] = self.calculator.calculate_obv(closes, volumes)
        
        # 8. 板块特征
        blocks = self.stock_blocks.get(code, [])
        features['block_count'] = len(blocks)
        
        # 计算板块动量（简化版）
        if blocks and df is not None:
            block_momentum = self._calculate_block_momentum(code, blocks, df)
            features['block_momentum'] = block_momentum
        else:
            features['block_momentum'] = 0.0
        
        return features
    
    def _extract_basic_features(self, code: str, price: float, volume: float) -> Dict[str, float]:
        """提取基础特征（历史数据不足时使用）"""
        return {
            'price_change_1d': 0.0,
            'price_change_5d': 0.0,
            'ma5_ratio': 0.0,
            'ma10_ratio': 0.0,
            'ma20_ratio': 0.0,
            'rsi_6': 50.0,
            'rsi_14': 50.0,
            'momentum_10': 0.0,
            'macd': 0.0,
            'macd_histogram': 0.0,
            'bollinger_position': 0.5,
            'volatility_20': 0.0,
            'atr_14': 0.0,
            'kdj_k': 50.0,
            'kdj_d': 50.0,
            'kdj_j': 50.0,
            'volume_ratio': 1.0,
            'volume_ma5_ratio': 1.0,
            'obv': 0.0,
            'block_count': len(self.stock_blocks.get(code, [])),
            'block_momentum': 0.0,
        }
    
    def _calculate_block_momentum(self, code: str, blocks: List[str], df: pd.DataFrame) -> float:
        """计算板块动量"""
        if not blocks or df is None or df.empty:
            return 0.0
        
        momentum_list = []
        
        for block in blocks[:3]:  # 只看前3个板块
            block_stocks = self.block_data.get(block, [])
            if len(block_stocks) > 1:
                # 计算板块内其他股票的平均涨幅
                other_stocks = [s for s in block_stocks if s != code][:5]
                stock_momentums = []
                
                for s in other_stocks:
                    s_history = self.stock_history.get(s, [])
                    if len(s_history) >= 2:
                        gain = (s_history[-1]['price'] - s_history[0]['price']) / s_history[0]['price'] * 100
                        stock_momentums.append(gain)
                
                if stock_momentums:
                    momentum_list.append(np.mean(stock_momentums))
        
        return np.mean(momentum_list) if momentum_list else 0.0


class MarketSentimentCalculator:
    """市场情绪计算器"""
    
    def __init__(self):
        self.market_history: List[Dict] = []
    
    def update_market_data(self, df: pd.DataFrame):
        """更新市场数据"""
        if df is None or df.empty:
            return
        
        # 计算市场指标
        up_count = 0
        down_count = 0
        limit_up_count = 0
        total_change = 0.0
        
        for _, row in df.iterrows():
            price = row.get('now', row.get('close', 0))
            pre_close = row.get('pre_close', price)
            
            if price > pre_close:
                up_count += 1
            elif price < pre_close:
                down_count += 1
            
            change_pct = (price - pre_close) / pre_close * 100 if pre_close > 0 else 0
            if change_pct > 9.5:
                limit_up_count += 1
            
            total_change += change_pct
        
        avg_change = total_change / len(df) if len(df) > 0 else 0
        
        self.market_history.append({
            'up_count': up_count,
            'down_count': down_count,
            'limit_up_count': limit_up_count,
            'avg_change': avg_change,
            'total_stocks': len(df)
        })
        
        # 限制历史长度
        if len(self.market_history) > 20:
            self.market_history = self.market_history[-20:]
    
    def get_sentiment_features(self) -> Dict[str, float]:
        """获取市场情绪特征"""
        if not self.market_history:
            return {
                'market_sentiment': 0.0,
                'up_down_ratio': 1.0,
                'limit_up_ratio': 0.0,
                'market_volatility': 0.0,
            }
        
        latest = self.market_history[-1]
        
        # 涨跌比
        up_down_ratio = latest['up_count'] / max(latest['down_count'], 1)
        
        # 市场情绪 (-1 到 1)
        total = latest['up_count'] + latest['down_count']
        if total > 0:
            market_sentiment = (latest['up_count'] - latest['down_count']) / total
        else:
            market_sentiment = 0.0
        
        # 涨停比例
        limit_up_ratio = latest['limit_up_count'] / max(latest['total_stocks'], 1)
        
        # 市场波动率
        if len(self.market_history) >= 5:
            changes = [h['avg_change'] for h in self.market_history[-5:]]
            market_volatility = np.std(changes)
        else:
            market_volatility = 0.0
        
        return {
            'market_sentiment': market_sentiment,
            'up_down_ratio': up_down_ratio,
            'limit_up_ratio': limit_up_ratio,
            'market_volatility': market_volatility,
        }


# 测试代码
if __name__ == "__main__":
    print("="*70)
    print("特征工程模块测试")
    print("="*70)
    
    # 创建特征提取器
    extractor = FeatureExtractor()
    
    # 加载板块数据
    extractor.load_block_data("/Users/spark/pycharmproject/deva/deva/naja/dictionary/infoharbor_block.dat")
    
    # 模拟历史数据
    for i in range(30):
        price = 10.0 + i * 0.1 + np.random.randn() * 0.5
        volume = 1000000 + np.random.randint(-100000, 100000)
        extractor.update_history('000001', price, volume, price + 0.5, price - 0.5)
    
    # 提取特征
    features = extractor.extract_all_features('000001', 13.0, 1100000)
    
    print(f"\n提取的特征数量: {len(features)}")
    print("\n特征示例:")
    for key, value in list(features.items())[:10]:
        print(f"  {key}: {value:.4f}")
    
    print("\n" + "="*70)
    print("测试完成!")
    print("="*70)
