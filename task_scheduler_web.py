#!/usr/bin/env python3
"""
任务调度 Web 设置界面

基于 pywebio 的任务调度配置界面，支持各种高级任务设置
"""

import datetime
import json
from deva import scheduler, timer, when, log
import pywebio
from pywebio import start_server
from pywebio.input import *
from pywebio.output import *
from pywebio.session import *

# 任务存储
tasks = {}
schedulers = {}

# 任务类型定义
task_types = [
    "interval",  # 间隔任务
    "cron",      # 定时任务（cron表达式）
    "delayed",   # 延迟任务
    "once",      # 一次性任务
    "event"      # 事件触发任务
]

# 时间单位选项
time_units = [
    ("seconds", "秒"),
    ("minutes", "分钟"),
    ("hours", "小时"),
    ("days", "天"),
    ("weeks", "周")
]

def create_task_form():
    """创建任务表单"""
    task_type = select("任务类型", options=[
        ("interval", "间隔任务"),
        ("cron", "定时任务（cron表达式）"),
        ("delayed", "延迟任务"),
        ("once", "一次性任务"),
        ("event", "事件触发任务")
    ])
    
    task_name = input("任务名称", required=True)
    task_desc = input("任务描述")
    
    task_config = {}
    
    if task_type == "interval":
        interval_value = input("执行间隔", type=NUMBER, required=True, min=1)
        interval_unit = select("时间单位", options=time_units)
        task_config["interval_value"] = interval_value
        task_config["interval_unit"] = interval_unit
    
    elif task_type == "cron":
        cron_expr = input("Cron 表达式", required=True, placeholder="例如: 0 0 * * *")
        task_config["cron_expr"] = cron_expr
    
    elif task_type == "delayed":
        delay_value = input("延迟时间", type=NUMBER, required=True, min=1)
        delay_unit = select("时间单位", options=time_units)
        task_config["delay_value"] = delay_value
        task_config["delay_unit"] = delay_unit
    
    elif task_type == "once":
        run_date = input("执行时间", type=DATE, required=True)
        run_time = input("执行时刻", type=TIME, required=True)
        task_config["run_date"] = run_date
        task_config["run_time"] = run_time
    
    elif task_type == "event":
        event_condition = input("事件条件", required=True, placeholder="例如: test_event")
        task_config["event_condition"] = event_condition
    
    # 任务执行函数
    task_code = textarea("执行代码", required=True, placeholder="def execute():\n    print('Hello World')\n    return 'Success'")
    
    return {
        "name": task_name,
        "description": task_desc,
        "type": task_type,
        "config": task_config,
        "code": task_code
    }

def execute_task_code(code):
    """执行任务代码"""
    try:
        # 编译代码
        exec_globals = {}
        exec(code, exec_globals)
        
        # 执行 execute 函数
        if "execute" in exec_globals:
            result = exec_globals["execute"]()
            return f"执行成功: {result}"
        else:
            return "错误: 代码中未定义 execute 函数"
    except Exception as e:
        return f"执行错误: {str(e)}"

def add_task():
    """添加任务"""
    put_markdown("## 添加新任务")
    
    task_data = create_task_form()
    
    # 生成任务ID
    task_id = f"task_{len(tasks) + 1}"
    tasks[task_id] = task_data
    
    # 启动任务
    start_task(task_id)
    
    put_success(f"任务 '{task_data['name']}' 添加成功！")
    refresh_task_list()

def start_task(task_id):
    """启动任务"""
    task = tasks[task_id]
    
    # 停止已有的调度器
    if task_id in schedulers:
        schedulers[task_id].stop()
    
    # 创建新的调度器
    s = scheduler()
    schedulers[task_id] = s
    
    if task["type"] == "interval":
        # 间隔任务
        interval_value = task["config"]["interval_value"]
        interval_unit = task["config"]["interval_unit"]
        
        s.add_job(
            func=lambda: execute_task_code(task["code"]),
            name=task_id,
            **{interval_unit: interval_value}
        )
    
    elif task["type"] == "cron":
        # 定时任务
        cron_expr = task["config"]["cron_expr"]
        # 简单解析 cron 表达式（仅支持基础格式）
        parts = cron_expr.split()
        if len(parts) == 5:
            second, minute, hour, day, month = parts
            s.add_job(
                func=lambda: execute_task_code(task["code"]),
                name=task_id,
                trigger="cron",
                second=second, minute=minute, hour=hour, day=day, month=month
            )
    
    elif task["type"] == "delayed":
        # 延迟任务
        delay_value = task["config"]["delay_value"]
        delay_unit = task["config"]["delay_unit"]
        
        # 计算延迟时间
        delay_seconds = {
            "seconds": delay_value,
            "minutes": delay_value * 60,
            "hours": delay_value * 3600,
            "days": delay_value * 86400,
            "weeks": delay_value * 604800
        }[delay_unit]
        
        run_time = datetime.datetime.now() + datetime.timedelta(seconds=delay_seconds)
        s.add_job(
            func=lambda: execute_task_code(task["code"]),
            name=task_id,
            run_date=run_time
        )
    
    elif task["type"] == "once":
        # 一次性任务
        run_date = task["config"]["run_date"]
        run_time = task["config"]["run_time"]
        
        # 解析日期时间
        run_datetime = datetime.datetime.strptime(f"{run_date} {run_time}", "%Y-%m-%d %H:%M")
        s.add_job(
            func=lambda: execute_task_code(task["code"]),
            name=task_id,
            run_date=run_datetime
        )
    
    elif task["type"] == "event":
        # 事件触发任务
        event_condition = task["config"]["event_condition"]
        when(lambda x: event_condition in str(x)).then(
            lambda x: execute_task_code(task["code"])
        )

def stop_task(task_id):
    """停止任务"""
    if task_id in schedulers:
        schedulers[task_id].stop()
        del schedulers[task_id]
        put_success(f"任务已停止")
    else:
        put_error("任务未运行")

def delete_task(task_id):
    """删除任务"""
    # 停止任务
    if task_id in schedulers:
        schedulers[task_id].stop()
        del schedulers[task_id]
    
    # 删除任务
    if task_id in tasks:
        del tasks[task_id]
        put_success("任务已删除")
    else:
        put_error("任务不存在")
    
    refresh_task_list()

def refresh_task_list():
    """刷新任务列表"""
    # 清除当前任务列表
    remove("task_list")
    
    # 显示任务列表
    with use_scope("task_list"):
        put_markdown("## 任务列表")
        
        if not tasks:
            put_info("暂无任务")
            return
        
        for task_id, task in tasks.items():
            is_running = task_id in schedulers
            
            # 使用 put_column 和 put_row 替代 put_card
            put_column([
                put_text(f"**{task['name']}**"),
                put_row([
                    put_column([
                        put_text(f"类型: {dict([
                            ("interval", "间隔任务"),
                            ("cron", "定时任务"),
                            ("delayed", "延迟任务"),
                            ("once", "一次性任务"),
                            ("event", "事件触发任务")
                        ])[task['type']]}"),
                        put_text(f"描述: {task['description'] or '无'}"),
                        put_text(f"状态: {'运行中' if is_running else '已停止'}")
                    ]),
                    put_column([
                        put_button("启动", onclick=lambda tid=task_id: start_task(tid)),
                        put_button("停止", onclick=lambda tid=task_id: stop_task(tid)),
                        put_button("删除", onclick=lambda tid=task_id: delete_task(tid), color="danger")
                    ])
                ]),
                put_hr()
            ])

def main():
    """主函数"""
    put_markdown("# 任务调度管理系统")
    put_markdown("基于 pywebio 和 deva Stream 的任务调度管理界面")
    
    put_row([
        put_button("添加任务", onclick=add_task, color="success"),
        put_button("刷新列表", onclick=refresh_task_list)
    ])
    
    refresh_task_list()

if __name__ == "__main__":
    # 使用非阻塞方式启动服务器
    import threading
    def run_server():
        start_server(main, port=8081, debug=True, auto_open_webbrowser=False)
    
    # 在新线程中启动服务器
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    
    print("任务调度管理系统已启动")
    print("访问地址: http://localhost:8081")
    
    # 保持主线程运行
    import time
    while True:
        time.sleep(1)
