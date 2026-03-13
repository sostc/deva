#!/usr/bin/env python3
"""
尝试恢复被删除的数据
"""

import os
import sys
sys.path.insert(0, '/Users/spark/pycharmproject/deva')

from deva import NB
import pandas as pd

def try_recover():
    """尝试恢复数据"""
    print("📋 尝试恢复数据...")
    
    nb_sqlite_path = '/Users/spark/.deva/nb.sqlite'
    
    # 检查SQLite文件是否存在
    print(f"\n🔍 检查数据库文件...")
    print(f"   数据库路径: {nb_sqlite_path}")
    print(f"   文件存在: {os.path.exists(nb_sqlite_path)}")
    
    if os.path.exists(nb_sqlite_path):
        file_size = os.path.getsize(nb_sqlite_path)
        print(f"   文件大小: {file_size / 1024 / 1024:.2f} MB")
        print(f"   修改时间: {os.path.getmtime(nb_sqlite_path)}")
    
    # 检查是否有-wal文件
    wal_path = nb_sqlite_path + "-wal"
    shm_path = nb_sqlite_path + "-shm"
    print(f"\n🔍 检查WAL文件...")
    print(f"   WAL文件存在: {os.path.exists(wal_path)}")
    print(f"   SHM文件存在: {os.path.exists(shm_path)}")
    
    # 检查是否有备份文件
    backup_paths = [
        '/Users/spark/.deva/nb.sqlite.backup',
        '/Users/spark/.deva/nb.sqlite.bak',
        '/Users/spark/.deva/backup/nb.sqlite',
    ]
    print(f"\n🔍 检查备份文件...")
    for backup_path in backup_paths:
        if os.path.exists(backup_path):
            print(f"   ✅ 找到备份: {backup_path}")
            backup_size = os.path.getsize(backup_path)
            print(f"   大小: {backup_size / 1024 / 1024:.2f} MB")
    
    # 尝试从当前数据库中导出剩余数据
    print(f"\n📊 当前数据库中的quant_snapshot_5min_window表:")
    db = NB('quant_snapshot_5min_window')
    print(f"   当前数据量: {len(db)} 条")
    
    for key, value in db.items():
        if isinstance(value, pd.DataFrame):
            print(f"   - {key}: {len(value)} rows")
    
    print(f"\n❌ 无法恢复已删除的数据:")
    print(f"   SQLite没有内置的撤销删除功能")
    print(f"   已删除的数据无法通过代码恢复")
    
    print(f"\n📋 建议:")
    print(f"   1. 如果有数据库备份，可以从备份恢复整个数据库")
    print(f"   2. 策略正在运行，每5分钟会自动存储新数据")
    print(f"   3. 可以等待新数据入库")
    
    return False

if __name__ == '__main__':
    print("=" * 60)
    print("尝试恢复被删除的数据")
    print("=" * 60)
    print()
    
    try_recover()
