#!/usr/bin/env python3
"""
测试刘邦智能体启动，验证是否能正确启动韩信、萧何、张良三个智能体
"""

import time
import logging
from deva import bus, Deva
from deva.naja.agent.manager import get_agent_manager
from deva.naja.agent.liubang import LiuBangAgent
from deva.naja.agent.hanxin import HanXinAgent
from deva.naja.agent.xiaohe import XiaoHeAgent
from deva.naja.agent.zhangliang import ZhangLiangAgent

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
log = logging.getLogger(__name__)

# 调整日志级别，减少日志量
logging.getLogger('deva.naja.agent.xiaohe').setLevel(logging.INFO)
logging.getLogger('deva.naja.agent.hanxin').setLevel(logging.INFO)  # 增加韩信的日志级别
logging.getLogger('deva.naja.agent.zhangliang').setLevel(logging.INFO)  # 增加张良的日志级别
logging.getLogger('deva.naja.agent.liubang').setLevel(logging.INFO)
logging.getLogger('deva.core.bus').setLevel(logging.WARNING)  # 减少总线的日志量
logging.getLogger('deva.naja.datasource').setLevel(logging.WARNING)  # 减少数据源的日志量
logging.getLogger('deva.naja.strategy').setLevel(logging.WARNING)  # 减少策略的日志量

def test_liubang_start():
    """测试刘邦智能体启动"""
    log.info("开始测试刘邦智能体启动")
    
    # 初始化智能体管理器
    manager = get_agent_manager()
    
    # 清空现有智能体（如果有）
    for agent_name in list(manager._agents.keys()):
        manager.unregister_agent(agent_name)
    
    # 创建智能体
    liubang = LiuBangAgent()
    hanxin = HanXinAgent()
    xiaohe = XiaoHeAgent()
    zhangliang = ZhangLiangAgent()
    
    # 注册智能体
    manager.register_agent(liubang)
    manager.register_agent(hanxin)
    manager.register_agent(xiaohe)
    manager.register_agent(zhangliang)
    
    # 启动刘邦智能体
    log.info("启动刘邦智能体")
    liubang.start()
    
    # 等待一段时间，让智能体启动完成
    log.info("等待智能体启动...")
    time.sleep(3)
    
    # 检查智能体状态
    log.info("\n检查智能体状态：")
    for agent_name, agent in manager._agents.items():
        state = agent.state.state.value
        log.info(f"{agent_name} 状态：{state}")
    
    # 检查是否所有智能体都已启动
    all_running = True
    for agent_name, agent in manager._agents.items():
        if agent.state.state.value != 'running':
            all_running = False
            log.error(f"{agent_name} 未启动成功")
    
    if all_running:
        log.info("\n测试成功：刘邦智能体已成功启动所有其他智能体")
    else:
        log.error("\n测试失败：部分智能体未启动成功")
    
    # 停止所有智能体
    log.info("\n停止所有智能体")
    manager.stop_all_agents()
    
    return all_running

if __name__ == "__main__":
    success = test_liubang_start()
    exit(0 if success else 1)
