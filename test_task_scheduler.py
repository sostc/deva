#!/usr/bin/env python3
"""
测试任务调度的高级功能

展示如何使用 scheduler、timer 和 when 来实现各种高级任务设置
"""

import datetime
from deva import scheduler, timer, when, log
import time

# 测试 1: 使用 scheduler 设置间隔执行任务
def test_interval_task():
    print("\n=== 测试 1: 间隔执行任务 ===")
    s = scheduler()
    
    # 每2秒执行一次
    s.add_job(
        func=lambda: print(f"[间隔任务] 当前时间: {datetime.datetime.now()}"),
        name="interval_task",
        seconds=2
    )
    
    time.sleep(10)  # 运行10秒
    s.stop()

# 测试 2: 使用 scheduler 设置定时执行任务（基于 cron 表达式）
def test_cron_task():
    print("\n=== 测试 2: 定时执行任务（cron）===")
    s = scheduler()
    
    # 每分钟的第10秒执行一次
    s.add_job(
        func=lambda: print(f"[定时任务] 当前时间: {datetime.datetime.now()}"),
        name="cron_task",
        trigger="cron",
        second=10
    )
    
    time.sleep(20)  # 运行20秒
    s.stop()

# 测试 3: 使用 scheduler 设置延迟执行任务
def test_delayed_task():
    print("\n=== 测试 3: 延迟执行任务 ===")
    s = scheduler()
    
    # 3秒后执行一次
    run_time = datetime.datetime.now() + datetime.timedelta(seconds=3)
    s.add_job(
        func=lambda: print(f"[延迟任务] 当前时间: {datetime.datetime.now()}"),
        name="delayed_task",
        run_date=run_time
    )
    
    print(f"[延迟任务] 计划执行时间: {run_time}")
    time.sleep(5)  # 运行5秒
    s.stop()

# 测试 4: 使用 timer 设置简单的间隔任务
def test_timer_task():
    print("\n=== 测试 4: 使用 timer 设置间隔任务 ===")
    
    # 每1秒执行一次
    t = timer(
        interval=1,
        func=lambda: print(f"[Timer任务] 当前时间: {datetime.datetime.now()}"),
        start=True
    )
    
    time.sleep(5)  # 运行5秒
    t.stop()

# 测试 5: 使用 when 设置事件触发任务
def test_event_task():
    print("\n=== 测试 5: 事件触发任务 ===")
    
    # 当收到 'test_event' 事件时执行
    when(lambda x: 'test_event' in str(x)).then(
        lambda x: print(f"[事件任务] 收到事件: {x}")
    )
    
    # 发送测试事件
    print("[事件任务] 发送测试事件...")
    'test_event: Hello World' >> log
    
    time.sleep(1)  # 等待事件处理

# 测试 6: 任务管理功能
def test_task_management():
    print("\n=== 测试 6: 任务管理 ===")
    s = scheduler()
    
    # 添加多个任务
    s.add_job(
        func=lambda: print("[任务1] 执行"),
        name="job1",
        seconds=5
    )
    
    s.add_job(
        func=lambda: print("[任务2] 执行"),
        name="job2",
        seconds=10
    )
    
    # 获取所有任务
    jobs = s.get_jobs()
    print(f"[任务管理] 当前任务数量: {len(jobs)}")
    for job in jobs:
        print(f"[任务管理] 任务名称: {job.id}, 下次执行时间: {job.next_run_time}")
    
    # 移除任务
    print("[任务管理] 移除任务 job1")
    s.remove_job("job1")
    
    # 再次获取任务
    jobs = s.get_jobs()
    print(f"[任务管理] 移除后任务数量: {len(jobs)}")
    for job in jobs:
        print(f"[任务管理] 任务名称: {job.id}, 下次执行时间: {job.next_run_time}")
    
    time.sleep(15)  # 运行15秒
    s.stop()

# 测试 7: 集成到 naja 任务管理模块的示例
def test_naja_integration():
    print("\n=== 测试 7: 集成到 naja 任务管理模块 ===")
    
    # 模拟 naja 任务管理模块使用 scheduler
    class MockTaskEntry:
        def __init__(self, task_type, interval_seconds=60, daily_time="03:00"):
            self.task_type = task_type
            self.interval_seconds = interval_seconds
            self.daily_time = daily_time
            self._scheduler = None
        
        def start(self, func):
            self._scheduler = scheduler()
            
            if self.task_type == "once":
                # 一次性任务
                run_time = datetime.datetime.now() + datetime.timedelta(seconds=1)
                self._scheduler.add_job(
                    func=lambda: func(),
                    name="once_task",
                    run_date=run_time
                )
            elif self.task_type == "daily":
                # 每日定时任务
                hour, minute = map(int, self.daily_time.split(":"))
                self._scheduler.add_job(
                    func=lambda: func(),
                    name="daily_task",
                    trigger="cron",
                    hour=hour,
                    minute=minute
                )
            else:
                # 间隔任务
                self._scheduler.add_job(
                    func=lambda: func(),
                    name="interval_task",
                    seconds=self.interval_seconds
                )
        
        def stop(self):
            if self._scheduler:
                self._scheduler.stop()
    
    # 测试不同类型的任务
    def test_func():
        print(f"[Naja任务] 执行时间: {datetime.datetime.now()}")
    
    # 测试间隔任务
    task1 = MockTaskEntry("interval", interval_seconds=2)
    task1.start(test_func)
    
    # 测试每日定时任务
    task2 = MockTaskEntry("daily", daily_time="12:00")
    task2.start(test_func)
    
    # 测试一次性任务
    task3 = MockTaskEntry("once")
    task3.start(test_func)
    
    time.sleep(10)  # 运行10秒
    task1.stop()
    task2.stop()
    task3.stop()

if __name__ == "__main__":
    # 运行所有测试
    test_interval_task()
    test_cron_task()
    test_delayed_task()
    test_timer_task()
    test_event_task()
    test_task_management()
    test_naja_integration()
    
    print("\n所有测试完成！")
