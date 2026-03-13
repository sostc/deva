#!/usr/bin/env python3
"""分析行情回放数据源的tick数据

按照建议的步骤分析行情回放数据源中的tick数据：
1. 验证数据完整性和质量
2. 提取价格和成交量数据
3. 进行时间序列分析和模式识别
4. 生成交易见解和策略建议
5. 回测识别的模式以验证有效性

运行方式:
    python scripts/analysis/analyze_replay_tick_data.py
"""

import logging
import time
import numpy as np
import pandas as pd
from datetime import datetime
from deva.naja.datasource import get_datasource_manager
from deva import NB

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

def analyze_replay_tick_data():
    """分析行情回放数据源的tick数据"""
    try:
        logger.info("=" * 80)
        logger.info("=== 分析行情回放数据源tick数据 ===")
        logger.info("=" * 80)
        
        # 获取数据源管理器
        ds_mgr = get_datasource_manager()
        
        # 加载数据源
        ds_mgr.load_from_db()
        
        # 查找行情回放数据源
        replay_ds = None
        for ds in ds_mgr.list_all():
            ds_name = getattr(ds, "name", "")
            if "回放" in ds_name or "replay" in ds_name.lower():
                replay_ds = ds
                break
        
        if not replay_ds:
            logger.error("未找到行情回放数据源")
            return False
        
        logger.info(f"找到行情回放数据源：{replay_ds.name} (ID: {replay_ds.id})")
        
        # 检查数据源状态
        logger.info(f"数据源状态：{'运行中' if replay_ds.is_running else '未运行'}")
        
        # 如果数据源未运行，尝试启动
        if not replay_ds.is_running:
            logger.info("正在启动行情回放数据源...")
            start_result = replay_ds.start()
            if start_result.get('success'):
                logger.info("行情回放数据源启动成功")
            else:
                logger.error(f"行情回放数据源启动失败：{start_result.get('error', '')}")
                return False
        
        # 等待数据加载
        time.sleep(2)
        
        # 1. 验证数据完整性和质量
        logger.info("\n1. 验证数据完整性和质量")
        
        # 从数据库获取原始数据
        db = NB("quant_snapshot_5min_window")
        data = list(db.items())
        
        logger.info(f"从 quant_snapshot_5min_window 表获取到 {len(data)} 条数据")
        
        # 查看前几条数据的格式
        if data:
            logger.info("\n查看前3条数据的格式：")
            for i, (key, value) in enumerate(data[:3]):
                logger.info(f"数据 {i+1} 键: {key}")
                logger.info(f"数据 {i+1} 值类型: {type(value)}")
                if isinstance(value, pd.DataFrame):
                    logger.info(f"数据 {i+1} DataFrame 形状: {value.shape}")
                    logger.info(f"数据 {i+1} DataFrame 列: {list(value.columns)}")
                    logger.info(f"数据 {i+1} 前5行:")
                    logger.info(f"{value.head()}")
                logger.info("-" * 50)
        
        # 解析数据
        all_stock_data = []
        valid_count = 0
        invalid_count = 0
        
        for timestamp, df in data:
            try:
                if isinstance(df, pd.DataFrame):
                    # 为每条记录添加时间戳
                    df['timestamp'] = timestamp
                    # 提取需要的列
                    if 'now' in df.columns:
                        df['price'] = df['now']
                    elif 'close' in df.columns:
                        df['price'] = df['close']
                    
                    # 选择需要的列
                    if 'price' in df.columns and 'volume' in df.columns:
                        stock_data = df[['code', 'name', 'price', 'volume', 'timestamp']].copy()
                        all_stock_data.append(stock_data)
                        valid_count += len(stock_data)
                    else:
                        logger.warning(f"DataFrame 缺少必要的列")
                        invalid_count += 1
                else:
                    logger.warning(f"数据格式不是 DataFrame：{type(df)}")
                    invalid_count += 1
            except Exception as e:
                logger.error(f"解析数据出错：{e}")
                invalid_count += 1
        
        logger.info(f"有效数据：{valid_count} 条")
        logger.info(f"无效数据：{invalid_count} 条")
        
        if not all_stock_data:
            logger.error("没有有效的数据可分析")
            return False
        
        # 合并所有数据
        combined_df = pd.concat(all_stock_data, ignore_index=True)
        
        # 2. 提取价格和成交量数据
        logger.info("\n2. 提取价格和成交量数据")
        
        # 按时间排序
        combined_df['timestamp'] = pd.to_datetime(combined_df['timestamp'])
        combined_df = combined_df.sort_values(['code', 'timestamp'])
        
        # 计算价格变化
        combined_df['price_change'] = combined_df.groupby('code')['price'].pct_change() * 100
        
        # 计算成交量变化（使用更直接的方法，避免索引问题）
        combined_df['volume_prev'] = combined_df.groupby('code')['volume'].shift(1)
        mask = combined_df['volume_prev'] != 0
        combined_df['volume_change'] = np.nan
        combined_df.loc[mask, 'volume_change'] = (combined_df.loc[mask, 'volume'] - combined_df.loc[mask, 'volume_prev']) / combined_df.loc[mask, 'volume_prev'] * 100
        combined_df.drop('volume_prev', axis=1, inplace=True)
        
        # 基本统计信息
        logger.info(f"总记录数：{len(combined_df)}")
        logger.info(f"股票数量：{len(combined_df['code'].unique())}")
        logger.info(f"价格范围：{combined_df['price'].min():.2f} - {combined_df['price'].max():.2f}")
        logger.info(f"平均价格：{combined_df['price'].mean():.2f}")
        logger.info(f"价格标准差：{combined_df['price'].std():.2f}")
        logger.info(f"成交量范围：{combined_df['volume'].min():.0f} - {combined_df['volume'].max():.0f}")
        logger.info(f"平均成交量：{combined_df['volume'].mean():.0f}")
        
        # 3. 进行时间序列分析和模式识别
        logger.info("\n3. 进行时间序列分析和模式识别")
        
        # 分析上证指数
        sh_index = combined_df[combined_df['code'] == '000001'].copy()
        if not sh_index.empty:
            # 识别价格趋势
            price_trend = "上升" if sh_index['price'].iloc[-1] > sh_index['price'].iloc[0] else "下降"
            logger.info(f"上证指数整体价格趋势：{price_trend}")
            
            # 识别成交量模式
            volume_mean = sh_index['volume'].mean()
            high_volume_periods = sh_index[sh_index['volume'] > volume_mean * 1.5]
            logger.info(f"上证指数高成交量时段：{len(high_volume_periods)} 个")
            
            # 识别价格波动
            price_volatility = sh_index['price_change'].std()
            logger.info(f"上证指数价格波动率：{price_volatility:.2f}%")
        
        # 4. 生成交易见解和策略建议
        logger.info("\n4. 生成交易见解和策略建议")
        
        # 基于量价关系分析
        if not combined_df.empty:
            # 计算量价配合情况
            combined_df['volume_price_correlation'] = combined_df['volume_change'] * combined_df['price_change']
            positive_correlation = len(combined_df[combined_df['volume_price_correlation'] > 0])
            negative_correlation = len(combined_df[combined_df['volume_price_correlation'] < 0])
            
            logger.info(f"量价正相关：{positive_correlation} 次")
            logger.info(f"量价负相关：{negative_correlation} 次")
            
            # 策略建议
            if positive_correlation > negative_correlation:
                logger.info("策略建议：跟随趋势，成交量放大时跟随价格方向建仓")
            else:
                logger.info("策略建议：注意量价背离，可能是反转信号")
        
        # 5. 回测识别的模式
        logger.info("\n5. 回测识别的模式")
        
        # 简单回测：假设跟随上证指数趋势交易
        if not sh_index.empty:
            initial_price = sh_index['price'].iloc[0]
            final_price = sh_index['price'].iloc[-1]
            profit = (final_price - initial_price) / initial_price * 100
            
            logger.info(f"回测结果（上证指数）：")
            logger.info(f"初始价格：{initial_price:.2f}")
            logger.info(f"最终价格：{final_price:.2f}")
            logger.info(f"模拟收益：{profit:.2f}%")
        
        # 保存分析结果
        analysis_result = {
            'timestamp': datetime.now().isoformat(),
            'total_records': len(combined_df),
            'stock_count': len(combined_df['code'].unique()),
            'price_range': f"{combined_df['price'].min():.2f} - {combined_df['price'].max():.2f}",
            'average_price': combined_df['price'].mean(),
            'price_volatility': price_volatility if 'price_volatility' in locals() else 0,
            'volume_range': f"{combined_df['volume'].min():.0f} - {combined_df['volume'].max():.0f}",
            'average_volume': combined_df['volume'].mean(),
            'price_trend': price_trend if 'price_trend' in locals() else "未知",
            'high_volume_periods': len(high_volume_periods) if 'high_volume_periods' in locals() else 0,
            'positive_correlation': positive_correlation if 'positive_correlation' in locals() else 0,
            'negative_correlation': negative_correlation if 'negative_correlation' in locals() else 0,
            'simulated_profit': profit if 'profit' in locals() else 0
        }
        
        # 保存到数据库
        analysis_db = NB("replay_tick_analysis")
        analysis_db[datetime.now().isoformat()] = analysis_result
        
        logger.info("\n分析结果已保存到 replay_tick_analysis 表")
        
        # 6. 额外分析：行业表现
        logger.info("\n6. 行业表现分析")
        
        # 识别行业指数
        industry_codes = ['000934', '000974', '000986', '000991', '000992']
        industry_names = {
            '000934': '中证金融',
            '000974': '800金融',
            '000986': '全指能源',
            '000991': '全指医药',
            '000992': '全指金融'
        }
        
        for code, name in industry_names.items():
            industry_data = combined_df[combined_df['code'] == code]
            if not industry_data.empty:
                initial_price = industry_data['price'].iloc[0]
                final_price = industry_data['price'].iloc[-1]
                change = (final_price - initial_price) / initial_price * 100
                logger.info(f"{name} ({code}): {change:.2f}%")
        
        logger.info("\n" + "=" * 80)
        logger.info("=== 分析完成 ===")
        logger.info("=" * 80)
        
        return True
        
    except Exception as e:
        logger.error(f"运行出错：{e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    analyze_replay_tick_data()
