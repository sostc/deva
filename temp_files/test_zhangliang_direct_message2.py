#!/usr/bin/env python3
"""
测试张良智能体是否能接收消息（直接调用_handle_message方法）
"""

import time
import logging
from deva.naja.agent.zhangliang import ZhangLiangAgent
from deva.naja.agent.liubang import LiuBangAgent
from deva.naja.agent.manager import get_agent_manager

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
log = logging.getLogger(__name__)


def test_zhangliang_message():
    """测试张良智能体是否能接收消息"""
    log.info("开始测试张良智能体消息接收")

    # 初始化智能体管理器
    manager = get_agent_manager()

    # 清空现有智能体（如果有）
    for agent_name in list(manager._agents.keys()):
        manager.unregister_agent(agent_name)

    # 创建智能体
    liubang = LiuBangAgent()
    zhangliang = ZhangLiangAgent()

    # 注册智能体
    manager.register_agent(liubang)
    manager.register_agent(zhangliang)

    # 启动智能体
    log.info("启动智能体")
    zhangliang.start()
    liubang.start()

    # 等待智能体启动完成
    log.info("等待智能体启动...")
    time.sleep(2)

    # 直接调用张良的_handle_message方法
    log.info("直接调用张良的_handle_message方法")
    test_message = {
        'type