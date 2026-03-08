#!/usr/bin/env python3
"""刘邦问题分发测试

测试刘邦智能体的问题分发功能，将不同类型的问题分发给韩信、萧何、张良处理。
"""

import sys
import time
import logging
from deva.naja.agent.liubang import LiuBangAgent
from deva.naja.agent.zhangliang import ZhangLiangAgent
from deva.naja.agent.hanxin import HanXinAgent
from deva.naja.agent.xiaohe import XiaoHeAgent

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

def main():
    """主函数"""
    try:
        logger.info("=== 刘邦问题分发测试 ===")
        
        # 创建智能体
        liubang = LiuBangAgent()
        zhangliang = ZhangLiangAgent()
        hanxin = HanXinAgent()
        xiaohe = XiaoHeAgent()
        
        # 注册智能体
        liubang.register_agent(zhangliang)
        liubang.register_agent(hanxin)
        liubang.register_agent(xiaohe)
        
        # 建立智能体之间的协调关系
        zhangliang.set_hanxin_agent(hanxin.name)
        hanxin.set_xiaohe_agent(xiaohe.name)
        
        # 启动智能体
        liubang.start()
        zhangliang.start()
        hanxin.start()
        xiaohe.start()
        
        logger.info("智能体启动完成，开始测试问题分发功能")
        
        # 测试分发策略相关问题给张良
        logger.info("\n1. 测试分发策略相关问题给张良")
        result = liubang.distribute_issue(
            'strategy',
            '需要优化river策略的信号提取逻辑，提高信号质量'
        )
        logger.info(f"分发结果: {result}")
        
        time.sleep(2)  # 等待处理
        
        # 测试分发交易执行问题给韩信
        logger.info("\n2. 测试分发交易执行问题给韩信")
        result = liubang.distribute_issue(
            'trade',
            '交易执行速度较慢，需要优化信号处理流程'
        )
        logger.info(f"分发结果: {result}")
        
        time.sleep(2)  # 等待处理
        
        # 测试分发风控问题给萧何
        logger.info("\n3. 测试分发风控问题给萧何")
        result = liubang.distribute_issue(
            'risk',
            '风控阈值设置过于严格，导致很多合理交易被拒绝'
        )
        logger.info(f"分发结果: {result}")
        
        time.sleep(2)  # 等待处理
        
        # 测试分发系统问题给自己处理
        logger.info("\n4. 测试分发系统问题给刘邦自己处理")
        result = liubang.distribute_issue(
            'system',
            '系统内存使用过高，需要优化资源管理'
        )
        logger.info(f"分发结果: {result}")
        
        time.sleep(2)  # 等待处理
        
        # 获取问题处理历史
        logger.info("\n5. 获取问题处理历史")
        history = liubang.get_issue_history()
        logger.info(f"问题历史数量: {len(history)}")
        for issue in history:
            logger.info(f"  - ID: {issue['issue_id']}, 类型: {issue['type']}, 处理者: {issue['handler']}, 状态: {issue['status']}")
        
        logger.info("\n测试完成，按 Ctrl+C 停止")
        
        # 运行事件循环
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        
    except KeyboardInterrupt:
        logger.info("用户中断")
    except Exception as e:
        logger.error(f"测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
