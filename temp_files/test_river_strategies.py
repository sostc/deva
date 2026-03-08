#!/usr/bin/env python3
"""
测试刘邦启动 river 开头的策略，持续到所有数据回放结束后程序退出
"""

from deva.naja.agent.liubang import LiuBangAgent
from deva.naja.agent.hanxin import HanXinAgent
from deva.naja.agent.xiaohe import XiaoHeAgent
from deva.naja.agent.zhangliang import ZhangLiangAgent
from deva.naja.agent.manager import get_agent_manager
import time

def test_river_strategies():
    """测试刘邦启动 river 开头的策略，持续到所有数据回放结束后程序退出"""
    print("=== 测试刘邦启动 river 开头的策略 ===")
    
    # 获取agent manager
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
    
    # 刘邦启动 river 开头的策略
    print("\n=== 刘邦启动 river 开头的策略 ===")
    print("正在启动行情回放数据源...")
    # 先启动行情回放数据源
    liubang.start_replay_datasource()
    print("正在启动 river 策略...")
    result = liubang.start_river_strategies()
    print(f"策略启动结果: {result}")
    
    # 打印智能体状态
    print("\n=== 智能体状态 ===")
    for agent_name in ['刘邦', '韩信', '萧何', '张良']:
        status = liubang.get_agent_status(agent_name)
        if status:
            print(f"{agent_name}: 状态={status.state}, 健康={status.health.value}")
        else:
            print(f"{agent_name}: 未注册")
    
    # 等待一段时间，让智能体有时间处理消息
    print("\n=== 等待智能体处理消息 ===")
    time.sleep(5)
    
    # 等待策略启动和数据更新
    print("\n=== 等待数据回放完成 ===")
    print("正在监控交易和价格更新...")
    
    # 持续监控，直到数据回放结束
    # 这里我们假设数据回放会在一定时间内完成
    # 实际应用中，可能需要根据数据源的状态来判断是否结束
    start_time = time.time()
    max_runtime = 60  # 最大运行时间，单位：秒
    
    while time.time() - start_time < max_runtime:
        # 每5秒汇报一次持仓情况
        time.sleep(5)
        print("\n=== 萧何汇报持仓情况 ===")
        xiaohe.report_positions()
        
        # 检查系统状态
        report = liubang.get_performance_report()
        print(f"系统健康状态: {report['system_health']}")
        print(f"活跃策略数量: {report['strategies']['active']}")
        print(f"总策略数量: {report['strategies']['total']}")
    
    # 数据回放结束，停止所有智能体
    print("\n=== 数据回放结束，停止所有智能体 ===")
    liubang.stop_all_agents()
    
    # 最后汇报一次持仓情况
    print("\n=== 最终持仓情况 ===")
    xiaohe.report_positions()
    
    print("\n=== 测试完成 ===")

if __name__ == "__main__":
    test_river_strategies()
