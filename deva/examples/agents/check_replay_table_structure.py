#!/usr/bin/env python3
"""检查行情回放数据源使用的表结构

验证行情回放数据源使用的表中是否包含价格字段，以及价格字段的值是否正确。

运行方式:
    python deva/examples/agents/check_replay_table_structure.py
"""

import logging
import sqlite3

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

def check_replay_table_structure():
    """检查行情回放数据源使用的表结构"""
    try:
        logger.info("=" * 80)
        logger.info("=== 检查行情回放数据源表结构 ===")
        logger.info("=" * 80)
        
        # SQLite 数据库路径
        db_path = "/Users/spark/.deva/nb.sqlite"
        
        # 连接数据库
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 检查 quant_snapshot_5min_window 表是否存在
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='quant_snapshot_5min_window';")
        table_exists = cursor.fetchone()
        
        if not table_exists:
            logger.error("表 quant_snapshot_5min_window 不存在")
            return False
        
        logger.info("找到表 quant_snapshot_5min_window")
        
        # 获取表的结构
        cursor.execute("PRAGMA table_info(quant_snapshot_5min_window);")
        columns = cursor.fetchall()
        
        logger.info("\n【表结构】")
        logger.info("字段名 | 数据类型 | 是否可为空 | 默认值")
        logger.info("-" * 60)
        for column in columns:
            cid, name, type_, notnull, dflt_value, pk = column
            logger.info(f"{name:10} | {type_:10} | {notnull:8} | {dflt_value}")
        
        # 检查是否包含价格相关字段
        price_columns = ['current', 'now', 'price', 'last', 'close', 'open', 'high', 'low']
        found_price_columns = []
        
        for column in columns:
            name = column[1]
            if name in price_columns:
                found_price_columns.append(name)
        
        logger.info("\n【价格相关字段】")
        if found_price_columns:
            logger.info(f"找到 {len(found_price_columns)} 个价格相关字段：{', '.join(found_price_columns)}")
        else:
            logger.warning("未找到价格相关字段")
        
        # 查询表中的前 5 条数据，查看价格字段的值
        logger.info("\n【前 5 条数据】")
        cursor.execute("SELECT * FROM quant_snapshot_5min_window LIMIT 5;")
        rows = cursor.fetchall()
        
        if rows:
            # 获取字段名
            column_names = [desc[0] for desc in cursor.description]
            
            for i, row in enumerate(rows, 1):
                logger.info(f"\n数据 {i}:")
                row_dict = dict(zip(column_names, row))
                
                # 打印价格相关字段的值
                logger.info("价格相关字段：")
                for field in price_columns:
                    if field in row_dict:
                        value = row_dict[field]
                        logger.info(f"  {field}: {value}")
                    else:
                        logger.info(f"  {field}: 不存在")
                
                # 打印其他重要字段
                logger.info("其他重要字段：")
                for field in ['code', 'name', 'volume', 'amount']:
                    if field in row_dict:
                        value = row_dict[field]
                        logger.info(f"  {field}: {value}")
        else:
            logger.warning("表中没有数据")
        
        # 关闭数据库连接
        conn.close()
        
        # 总结
        logger.info("\n【总结】")
        if found_price_columns:
            logger.info("表中包含价格相关字段，但需要确保这些字段的值大于 0")
        else:
            logger.info("表中缺少价格相关字段，这可能是导致价格显示为 0 的原因")
        
        return True
        
    except Exception as e:
        logger.error(f"运行出错：{e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    check_replay_table_structure()
