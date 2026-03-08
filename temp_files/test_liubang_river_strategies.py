#!/usr/bin/env python3
"""
测试刘邦智能体的start_river_strategies方法
"""

import time
import logging
from deva.naja.agent.liubang import LiuBangAgent
from deva.naja.agent.manager import get_agent_manager

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
log = logging.getLogger(__name__)

def test_liubang_start_river_strategies():
    """测试刘邦智能体启动river策略"""
    log.info("开始测试刘邦智能体启动river策略")
    
    # 初始化智能体管理器
    manager = get_agent_manager()
    
    # 清空现有智能体（如果有）
    for agent_name in list(manager._agents.keys()):
        manager.unregister_agent(agent_name)
    
    # 创建刘邦智能体
    liubang = LiuBangAgent()
    
    # 注册智能体
    manager.register_agent(liubang)
    
    # 启动刘邦智能体
    log.info("启动刘邦智能体")
    liubang.start()
    
    # 等待一段时间，让智能体启动完成
    log.info("等待智能体启动...")
    time.sleep(2)
    
    # 测试启动river策略
    log.info("测试启动river策略")
    results = liubang.start_river_strategies()
    
    # 打印启动结果
    log.info("\nriver策略启动结果：")
    for strategy_name, success in results.items():
        status = "成功" if success else "失败"
        log.info(f"策略 [{strategy_name}] 启动：{status}")
    
    if results:
        log.info(f"\n测试成功：已尝试启动 {len(results)} 个river策略")
    else:
        log.warning("\n测试完成：未找到river策略")
    
    # 停止所有智能体
    log.info("\n停止所有智能体")
    manager.stop_all_agents()
    
    return True

if __name__ == "__main__":
    test_liubang_start_river_strategies()
