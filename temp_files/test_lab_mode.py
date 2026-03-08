#!/usr/bin/env python3
"""
测试刘邦启动实验室模式，萧何订阅行情并打印行情数据的流程
"""

import time
import logging
from deva import bus,Deva
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
logging.getLogger('deva.naja.agent.hanxin').setLevel(logging.WARNING)  # 减少韩信的日志量
logging.getLogger('deva.naja.agent.liubang').setLevel(logging.INFO)
logging.getLogger('deva.core.bus').setLevel(logging.WARNING)  # 减少总线的日志量
logging.getLogger('deva.naja.datasource').setLevel(logging.WARNING)  # 减少数据源的日志量
logging.getLogger('deva.naja.strategy').setLevel(logging.WARNING)  # 减少策略的日志量

def test_lab_mode():
    """测试刘邦启动实验室模式，萧何订阅行情并打印行情数据的流程"""
    log.info("开始测试刘邦启动实验室模式，萧何订阅行情并打印行情数据的流程")
    
    # 初始化智能体管理器
    manager = get_agent_manager()
    
    # 创建智能体
    liubang = LiuBangAgent()
    # 开启韩信的自动交易功能
    hanxin_config = {'auto_trade_enabled': True}
    hanxin = HanXinAgent(hanxin_config)
    xiaohe = XiaoHeAgent()
    zhangliang = ZhangLiangAgent()
    
    # 注册智能体
    manager.register_agent(liubang)
    manager.register_agent(hanxin)
    manager.register_agent(xiaohe)
    manager.register_agent(zhangliang)
    
    # 启动智能体
    log.info("启动智能体")
    liubang.start()
    time.sleep(0.5)
    xiaohe.start()
    time.sleep(0.5)
    zhangliang.start()
    time.sleep(0.5)
    hanxin.start()
    time.sleep(0.5)
    
    # 刘邦启动实验室模式（模拟）
    log.info("刘邦启动实验室模式")
    # 这里我们用启动行情回放数据源来模拟启动实验室模式
    start_result = liubang.start_replay_datasource()
    log.info(f"数据源启动结果：{start_result}")
    

import atexit

def exit_handler():
    """程序退出前的处理函数"""
    try:
        from deva.naja.agent.manager import get_agent_manager
        manager = get_agent_manager()
        xiaohe = manager.get_agent('萧何')
        if xiaohe:
            # 触发萧何的持仓盈亏报告
            xiaohe.report_positions()
            # 计算总盈亏
            positions = xiaohe.get_all_positions()
            total_pnl = 0
            for position in positions:
                total_pnl += (position.current_price - position.avg_price) * position.amount
            log.info(f"程序退出前，萧何汇报总盈亏：{total_pnl:.2f}")
    except Exception as e:
        log.error(f"退出处理失败：{e}")

# 注册退出处理函数
atexit.register(exit_handler)

if __name__ == "__main__":
    test_lab_mode()
    Deva.run()