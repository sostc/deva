#!/usr/bin/env python3
"""
测试韩信无法交易时的流程
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
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
log = logging.getLogger(__name__)

# 增加萧何的日志级别
logging.getLogger('deva.naja.agent.xiaohe').setLevel(logging.DEBUG)


def test_trade_failed_flow():
    """测试韩信无法交易时的流程"""
    log.info("开始测试韩信无法交易的情况")

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

    # 启动行情回放数据源
    log.info("启动行情回放数据源")
    start_result = liubang.start_replay_datasource()
    log.info(f"数据源启动结果：{start_result}")
    time.sleep(2)  # 等待萧何订阅数据源

    # 检查萧何是否成功订阅了数据源
    if hasattr(xiaohe, '_data_source') and xiaohe._data_source:
        log.info(f"萧何已成功订阅数据源：{xiaohe._data_source.name}")
    else:
        log.warning("萧何未订阅数据源")

        # 手动触发萧何订阅数据源
        log.info("手动触发萧何订阅数据源")
        try:
            from deva.naja.datasource import get_datasource_manager
            ds_mgr = get_datasource_manager()
            ds_mgr.load_from_db()

            # 查找行情回放数据源
            replay_ds = None
            for ds in ds_mgr.list_all():
                ds_name = getattr(ds, "name", "")
                if "回放" in ds_name or "replay" in ds_name.lower():
                    replay_ds = ds
                    break

            if replay_ds:
                log.info(f"找到行情回放数据源：{replay_ds.name}")
                xiaohe.subscribe_to_data_source(replay_ds)
                log.info("已手动订阅数据源")
            else:
                log.warning("未找到行情回放数据源")
        except Exception as e:
            log.error(f"手动订阅数据源失败：{e}")

    # # 为萧何添加一些测试持仓
    # log.info("为萧何添加测试持仓")
    # xiaohe.add_position(
    #     strategy_name="test_strategy",
    #     amount=100,
    #     price=10.0,
    #     stock_code="TEST",
    #     stock_name="测试股票"
    # )

    # # 模拟数据源推送价格更新
    # log.info("模拟数据源推送价格更新")
    # if hasattr(xiaohe, '_data_source') and xiaohe._data_source:
    #     # 直接调用萧何的_process_data_source_update方法来模拟数据源推送
    #     test_data = {"code": "TEST", "current": 10.5}
    #     xiaohe._process_data_source_update(test_data)
    #     time.sleep(1)

    #     # 再次推送价格更新
    #     test_data = {"code": "TEST", "current": 11.0}
    #     xiaohe._process_data_source_update(test_data)
    #     time.sleep(1)

    # 直接发送trade_failed消息给刘邦
    # log.info("发送trade_failed消息给刘邦")
    # message = {
    #     'type': 'trade_failed',
    #     'to': '刘邦',
    #     'from': '韩信',
    #     'reason': '风控检查未通过',
    #     'stock_name': '测试股票',
    #     'stock_code': 'TEST',
    #     'strategy_name': 'test_strategy',
    #     'message': '无法执行交易：风控检查未通过',
    #     'timestamp': time.time()
    # }
    # log.info(f"发送消息：{message}")

    # 直接调用刘邦的receive_message方法
    # log.info("直接调用刘邦的receive_message方法")
    # liubang.receive_message(message)

    # 运行一段时间
    try:
        # log.info("等待5秒，观察处理结果")
        # time.sleep(5)

        # 手动触发萧何汇报持仓
        log.info("手动触发萧何汇报持仓")
        xiaohe.report_positions()

        # 生成最终交易总结报告
        log.info("生成最终交易总结报告")
        xiaohe.generate_final_report(hanxin)
    except KeyboardInterrupt:
        log.info("测试被中断")
    finally:
        # 停止智能体
        log.info("停止智能体")
        liubang.stop()
        hanxin.stop()
        xiaohe.stop()
        zhangliang.stop()

        log.info("测试结束")


if __name__ == "__main__":
    test_trade_failed_flow()
