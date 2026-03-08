#!/usr/bin/env python3
"""
测试刘邦行动，韩信交易，萧何生成盈亏报告的流程
"""

import time
import logging
from deva import bus
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

# 增加萧何的日志级别
logging.getLogger('deva.naja.agent.xiaohe').setLevel(logging.INFO)

def test_liubang_action():
    """测试刘邦行动，韩信交易，萧何生成盈亏报告的流程"""
    log.info("开始测试刘邦行动，韩信交易，萧何生成盈亏报告的流程")
    
    # 初始化智能体管理器
    manager = get_agent_manager()
    
    # 创建智能体
    liubang = LiuBangAgent()
    # 启用韩信的自动交易功能
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
    
    # 刘邦启动行情回放数据源
    log.info("刘邦启动行情回放数据源")
    start_result = liubang.start_replay_datasource()
    log.info(f"数据源启动结果：{start_result}")
    time.sleep(2)  # 等待萧何订阅数据源
    
    # 刘邦启动river策略
    log.info("刘邦启动river策略")
    river_results = liubang.start_river_strategies()
    log.info(f"river策略启动结果：{river_results}")
    
    # 让韩信交易一段时间
    log.info("让韩信交易一段时间")
    time.sleep(5)  # 等待韩信执行交易
    
    # 让萧何等待一段时间
    log.info("让萧何等待一段时间")
    time.sleep(3)  # 让萧何等待
    
    # 萧何生成盈亏报告
    log.info("萧何生成盈亏报告")
    xiaohe.report_positions()
    
    # 生成最终交易总结报告
    log.info("生成最终交易总结报告")
    xiaohe.generate_final_report(hanxin)
    
    # 停止智能体
    log.info("停止智能体")
    liubang.stop()
    hanxin.stop()
    xiaohe.stop()
    zhangliang.stop()
    
    log.info("测试结束")

if __name__ == "__main__":
    test_liubang_action()
