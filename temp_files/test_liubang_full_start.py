#!/usr/bin/env python3
"""
测试刘邦智能体的完整启动流程
验证刘邦启动时是否能正确启动三个智能体、数据源和river策略
"""

import time
import logging
from deva.naja.agent.liubang import LiuBangAgent
from deva.naja.agent.hanxin import HanXinAgent
from deva.naja.agent.xiaohe import XiaoHeAgent
from deva.naja.agent.zhangliang import ZhangLiangAgent
from deva.naja.agent.manager import get_agent_manager

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
log = logging.getLogger(__name__)


def test_liubang_full_start():
    """测试刘邦智能体完整启动流程"""
    log.info("开始测试刘邦智能体完整启动流程")

    # 初始化智能体管理器
    manager = get_agent_manager()

    # 清空现有智能体（如果有）
    for agent_name in list(manager._agents.keys()):
        manager.unregister_agent(agent_name)

    # 创建并启动刘邦智能体
    liubang = LiuBangAgent()
    manager.register_agent(liubang)
    log.info("启动刘邦智能体")
    liubang.start()
    
    # 设置数据源回放间隔为 0.1 秒
    log.info("设置数据源回放间隔为 0.1 秒")
    liubang.start_replay_datasource(interval=0.1)

    # 等待一段时间，让智能体启动完成
    log.info("等待智能体启动...")
    time.sleep(10)

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
    # log.info("\n停止所有智能体")
    # manager.stop_all_agents()

    return all_running


if __name__ == "__main__":
    test_liubang_full_start()
    from deva import Deva
    Deva.run()
