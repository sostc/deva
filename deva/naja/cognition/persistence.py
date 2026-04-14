"""认知状态持久化模块"""

import time
import json
import sqlite3
from typing import Dict, Any, List, Optional
import logging

log = logging.getLogger(__name__)


class CognitiveStatePersistence:
    """认知状态持久化"""
    
    def __init__(self, db_path: str = ":memory:"):
        """初始化持久化模块
        
        Args:
            db_path: 数据库路径，默认使用内存数据库
        """
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """初始化数据库"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 创建认知状态表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS cognitive_states (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                state_type TEXT NOT NULL,
                state_data TEXT NOT NULL,
                importance REAL DEFAULT 0.5
            )
            ''')
            
            # 创建状态变化历史表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS state_changes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                state_type TEXT NOT NULL,
                old_state TEXT,
                new_state TEXT,
                change_score REAL DEFAULT 0.0
            )
            ''')
            
            # 创建索引
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_state_type ON cognitive_states(state_type)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON cognitive_states(timestamp)')
            
            conn.commit()
            conn.close()
        except Exception as e:
            log.warning(f"[CognitiveStatePersistence] 初始化数据库失败: {e}")
    
    def save_state(self, state_type: str, state_data: Dict[str, Any], importance: float = 0.5):
        """保存认知状态
        
        Args:
            state_type: 状态类型
            state_data: 状态数据
            importance: 重要性
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 获取最新状态
            cursor.execute(
                'SELECT state_data FROM cognitive_states WHERE state_type = ? ORDER BY timestamp DESC LIMIT 1',
                (state_type,)
            )
            old_state_row = cursor.fetchone()
            old_state = json.loads(old_state_row[0]) if old_state_row else None
            
            # 保存新状态
            cursor.execute(
                'INSERT INTO cognitive_states (timestamp, state_type, state_data, importance) VALUES (?, ?, ?, ?)',
                (time.time(), state_type, json.dumps(state_data), importance)
            )
            
            # 记录状态变化
            if old_state:
                change_score = self._calculate_change_score(old_state, state_data)
                cursor.execute(
                    'INSERT INTO state_changes (timestamp, state_type, old_state, new_state, change_score) VALUES (?, ?, ?, ?, ?)',
                    (time.time(), state_type, json.dumps(old_state), json.dumps(state_data), change_score)
                )
            
            conn.commit()
            conn.close()
        except Exception as e:
            log.warning(f"[CognitiveStatePersistence] 保存状态失败: {e}")
    
    def get_latest_state(self, state_type: str) -> Optional[Dict[str, Any]]:
        """获取最新状态
        
        Args:
            state_type: 状态类型
            
        Returns:
            状态数据，若不存在则返回 None
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute(
                'SELECT state_data FROM cognitive_states WHERE state_type = ? ORDER BY timestamp DESC LIMIT 1',
                (state_type,)
            )
            row = cursor.fetchone()
            conn.close()
            
            if row:
                return json.loads(row[0])
            return None
        except Exception as e:
            log.warning(f"[CognitiveStatePersistence] 获取最新状态失败: {e}")
            return None
    
    def get_state_history(self, state_type: str, limit: int = 100) -> List[Dict[str, Any]]:
        """获取状态历史
        
        Args:
            state_type: 状态类型
            limit: 限制数量
            
        Returns:
            状态历史列表
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute(
                'SELECT timestamp, state_data, importance FROM cognitive_states WHERE state_type = ? ORDER BY timestamp DESC LIMIT ?',
                (state_type, limit)
            )
            rows = cursor.fetchall()
            conn.close()
            
            history = []
            for row in rows:
                history.append({
                    'timestamp': row[0],
                    'state': json.loads(row[1]),
                    'importance': row[2]
                })
            return history
        except Exception as e:
            log.warning(f"[CognitiveStatePersistence] 获取状态历史失败: {e}")
            return []
    
    def get_state_changes(self, state_type: str, limit: int = 50) -> List[Dict[str, Any]]:
        """获取状态变化历史
        
        Args:
            state_type: 状态类型
            limit: 限制数量
            
        Returns:
            状态变化历史列表
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute(
                'SELECT timestamp, old_state, new_state, change_score FROM state_changes WHERE state_type = ? ORDER BY timestamp DESC LIMIT ?',
                (state_type, limit)
            )
            rows = cursor.fetchall()
            conn.close()
            
            changes = []
            for row in rows:
                changes.append({
                    'timestamp': row[0],
                    'old_state': json.loads(row[1]) if row[1] else None,
                    'new_state': json.loads(row[2]) if row[2] else None,
                    'change_score': row[3]
                })
            return changes
        except Exception as e:
            log.warning(f"[CognitiveStatePersistence] 获取状态变化失败: {e}")
            return []
    
    def _calculate_change_score(self, old_state: Dict[str, Any], new_state: Dict[str, Any]) -> float:
        """计算状态变化分数
        
        Args:
            old_state: 旧状态
            new_state: 新状态
            
        Returns:
            变化分数 (0-1)
        """
        try:
            # 简化的变化计算方法
            # 实际应用中可以根据具体状态类型实现更复杂的计算
            change_score = 0.0
            common_keys = set(old_state.keys()) & set(new_state.keys())
            
            if common_keys:
                for key in common_keys:
                    old_val = old_state.get(key)
                    new_val = new_state.get(key)
                    
                    if isinstance(old_val, (int, float)) and isinstance(new_val, (int, float)):
                        # 数值型变化
                        if old_val != 0:
                            change_score += abs((new_val - old_val) / old_val)
                        else:
                            change_score += abs(new_val)
            
            # 归一化到 0-1
            return min(1.0, change_score)
        except Exception:
            return 0.0
    
    def clear_old_data(self, days: int = 7):
        """清理旧数据
        
        Args:
            days: 保留天数
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cutoff_time = time.time() - (days * 24 * 3600)
            
            # 清理旧状态
            cursor.execute(
                'DELETE FROM cognitive_states WHERE timestamp < ?',
                (cutoff_time,)
            )
            
            # 清理旧变化记录
            cursor.execute(
                'DELETE FROM state_changes WHERE timestamp < ?',
                (cutoff_time,)
            )
            
            conn.commit()
            conn.close()
        except Exception as e:
            log.warning(f"[CognitiveStatePersistence] 清理旧数据失败: {e}")


# 单例模式
_cognitive_persistence = None

def get_cognitive_persistence() -> CognitiveStatePersistence:
    """获取认知状态持久化单例"""
    global _cognitive_persistence
    if _cognitive_persistence is None:
        _cognitive_persistence = CognitiveStatePersistence(
            db_path='cognitive_state.db'  # 使用文件数据库
        )
    return _cognitive_persistence