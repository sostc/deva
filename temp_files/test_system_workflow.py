#!/usr/bin/env python3
"""
测试整个系统的工作流程
"""

from deva.naja.agent.liubang import LiuBangAgent
from deva.naja.agent.hanxin import HanXinAgent
from deva.naja.agent.xiaohe import XiaoHeAgent
from deva.naja.agent.zhangliang import ZhangLiangAgent
import time

def test_system_workflow():
    """测试整个系统的工作流程"""
    print("=== 测试整个系统的工作流程 ===")
    
    # 导入agent manager
    from deva.naja.agent.manager import get_agent_manager
    manager = get_agent_manager()
    
    # 创建智能体
    liubang = LiuBangAgent()
    hanxin = HanXinAgent()
    xiaohe = XiaoHeAgent()
    zhangliang = ZhangLiangAgent()
    
    # 注册智能体到agent manager
    manager.register_agent(liubang)
    manager.register_agent(hanxin)
    manager.register_agent(xiaohe)
    manager.register_agent(zhangliang)
    
    # 注册智能体到刘邦
    liubang.register_agent(hanxin)
    liubang.register_agent(xiaohe)
    liubang.register_agent(zhangliang)
    
    # 手动设置智能体之间的绑定
    zhangliang.set_hanxin_agent('韩信')
    hanxin.set_xiaohe_agent('萧何')
    
    # 启动所有智能体
    liubang.start_all_agents()
    
    # 等待智能体启动
    time.sleep(2)
    
    # 刘邦启动 river 策略
    print("\n=== 刘邦启动 river 策略 ===")
    result = liubang.start_river_strategies()
    print(f"策略启动结果: {result}")
    
    # 等待策略启动和数据更新
    time.sleep(5)
    
    # 萧何汇报持仓情况
    print("\n=== 萧何汇报持仓情况 ===")
    xiaohe.report_positions()
    
    # 刘邦获取系统状态
    print("\n=== 刘邦获取系统状态 ===")
    report = liubang.get_performance_report()
    print(f"系统健康状态: {report['system_health']}")
    print(f"活跃策略数量: {report['strategies']['active']}")
    print(f"总策略数量: {report['strategies']['total']}")
    
    # 停止所有智能体
    liubang.stop_all_agents()
    
    print("\n=== 测试完成 ===")

if __name__ == "__main__":
    test_system_workflow()
