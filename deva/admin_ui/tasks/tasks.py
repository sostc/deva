"""Task-related admin UI logic extracted from admin.py."""

from __future__ import annotations

import ast
import asyncio
import re


async def watch_topic(ctx, topic):
    full_prompt = (
        f" 获取{topic},要求返回的内容每一行都是一个一句话，开头用一个和内容对应的图标，"
        "然后是一个不大于十个字的高度浓缩概括词，概括词用加粗字体，再后面是一句话摘要，"
        "用破折号区隔开。每行一个内容，不要有标题等其他任何介绍性内容，只需要返回6 条新闻即可。"
    )
    return await ctx["get_gpt_response"](prompt=full_prompt, model_type="kimi")


def _load_job_from_code(job_code, global_ns):
    try:
        tree = ast.parse(job_code)
        namespace = {}
        exec(job_code, global_ns, namespace)
        function_names = [node.name for node in ast.walk(tree) if isinstance(node, ast.AsyncFunctionDef)]
        if not function_names:
            raise ValueError("未生成有效的异步函数")
        return namespace[function_names[0]]
    except SyntaxError as e:
        error_msg = f"代码语法错误: {e}"
        raise ValueError(error_msg)
    except Exception as e:
        error_msg = f"代码加载失败: {e}"
        raise ValueError(error_msg)


def _schedule_job(scheduler, name, job_func, task_type, time_value, retry_count=0, retry_interval=5):
    # 包装任务函数，添加执行历史记录、重试逻辑和实时状态反馈
    async def wrapped_job_func():
        import time
        import traceback
        from datetime import datetime
        
        # 更新任务状态为运行中
        update_task_status(name, "running")
        
        total_attempts = retry_count + 1
        last_error = None
        
        for attempt in range(total_attempts):
            start_time = time.time()
            start_datetime = datetime.now()
            status = "success"
            output = ""
            error = ""
            
            try:
                # 更新尝试次数
                update_task_status(name, "running", attempt=attempt+1, total_attempts=total_attempts)
                
                result = await job_func()
                if result:
                    output = str(result)
                
                # 执行成功，记录历史并返回
                end_time = time.time()
                end_datetime = datetime.now()
                duration = end_time - start_time
                record_history(start_datetime, end_datetime, duration, status, output, error)
                update_task_status(name, "success")
                return result
            except Exception as e:
                last_error = e
                status = "failed"
                error = str(e)
                traceback_str = traceback.format_exc()
                traceback_str >> ctx["log"]
                
                end_time = time.time()
                end_datetime = datetime.now()
                duration = end_time - start_time
                record_history(start_datetime, end_datetime, duration, status, output, error)
                update_task_status(name, "failed", error=error)
                
                # 如果还有重试次数，等待后重试
                if attempt < retry_count:
                    retry_msg = f"任务执行失败，将在 {retry_interval} 秒后进行第 {attempt + 2} 次尝试..."
                    retry_msg >> ctx["log"]
                    update_task_status(name, "retrying", attempt=attempt+1, total_attempts=total_attempts, retry_interval=retry_interval)
                    await asyncio.sleep(retry_interval)
                else:
                    # 重试次数用完，最终失败
                    final_error_msg = f"任务执行失败，已达到最大重试次数 {retry_count} 次"
                    final_error_msg >> ctx["log"]
                    update_task_status(name, "failed", error=final_error_msg)
                    raise last_error
    
    def record_history(start_datetime, end_datetime, duration, status, output, error):
        # 记录执行历史
        if "task_history" not in ctx:
            ctx["task_history"] = {}
        if name not in ctx["task_history"]:
            ctx["task_history"][name] = []
        
        history_entry = {
            "start_time": start_datetime.isoformat(),
            "end_time": end_datetime.isoformat(),
            "duration": round(duration, 2),
            "status": status,
            "output": output,
            "error": error
        }
        
        ctx["task_history"][name].append(history_entry)
        # 限制历史记录数量，保留最近100条
        if len(ctx["task_history"][name]) > 100:
            ctx["task_history"][name] = ctx["task_history"][name][-100:]
        
        # 保存到数据库
        if "NB" in ctx:
            ctx["NB"]("task_history")[name] = ctx["task_history"][name]
    
    def update_task_status(task_name, status, attempt=None, total_attempts=None, retry_interval=None, error=None):
        from datetime import datetime
        # 更新任务状态
        if "task_status" not in ctx:
            ctx["task_status"] = {}
        
        status_info = {
            "status": status,
            "timestamp": datetime.now().isoformat()
        }
        
        if attempt is not None:
            status_info["attempt"] = attempt
        if total_attempts is not None:
            status_info["total_attempts"] = total_attempts
        if retry_interval is not None:
            status_info["retry_interval"] = retry_interval
        if error is not None:
            status_info["error"] = error
        
        ctx["task_status"][task_name] = status_info
        
        # 保存到数据库
        if "NB" in ctx:
            try:
                ctx["NB"]("task_status")[task_name] = status_info
            except Exception as e:
                e >> ctx["log"]
    
    # 从上下文中获取 ctx
    from deva.core.namespace import NB
    from deva.core.bus import log
    import asyncio
    ctx = {"NB": NB, "log": log}
    
    if task_type == "interval":
        interval = int(time_value)
        scheduler.add_job(wrapped_job_func, "interval", seconds=interval, id=name)
    elif task_type == "cron":
        hour, minute = map(int, str(time_value).split(":"))
        scheduler.add_job(wrapped_job_func, "cron", hour=hour, minute=minute, id=name)
    else:
        raise ValueError(f"不支持的任务类型: {task_type}")


async def create_task(ctx):
    input_group = ctx["input_group"]
    input_comp = ctx["input"]
    textarea = ctx["textarea"]
    select = ctx["select"]
    toast = ctx["toast"]
    tasks = ctx["tasks"]

    task_info = await input_group("创建定时任务", [
        input_comp("任务名称", name="name", type=ctx["TEXT"]),
        textarea("任务描述", name="description", placeholder="请输入任务描述"),
        select("任务类型", name="type", options=[
            ("间隔任务（每隔X秒执行）", "interval"),
            ("定时任务（每天固定时间执行）", "cron")
        ]),
        input_comp("间隔时间（秒）或执行时间（HH:MM）", name="time", type=ctx["TEXT"]),
        input_comp("重试次数（失败后自动重试）", name="retry_count", type=ctx["TEXT"], value="0", placeholder="0表示不重试"),
        input_comp("重试间隔（秒）", name="retry_interval", type=ctx["TEXT"], value="5", placeholder="重试之间的等待时间")
    ])

    name = task_info["name"]
    description = task_info["description"]
    task_type = task_info["type"]
    time_value = task_info["time"]
    retry_count = int(task_info.get("retry_count", "0"))
    retry_interval = int(task_info.get("retry_interval", "5"))

    if name in tasks:
        toast("任务名称已存在，请使用其他名称！", color="error")
        return

    task_info >> ctx["log"]
    toast("开始创建定时任务，需要一点时间...")
    samplecode = """我有下面这些功能可以调用，使用例子如下,请选择使用里面的功能来合理完成需求：
    from deva import write_to_file, httpx, Dtalk, bus, log, warn, debug, DBStream, IndexStream, FileLogStream
    from deva.admin import watch_topic
    
    # 核心功能：
    # 1. 流式编程模型
    打印日志：'sometext' >> log
    写入文件： 'some text' >> write_to_file('filename')
    发送到钉钉通知我：'@md@焦点分析|'+'some text' >> Dtalk()
    
    # 2. 网络操作
    抓取网页： response = await httpx(url)
    查找网页标签：response.html.search('<title>{}</title>')
    
    # 3. 数据流转
    发送数据到总线：'data' >> bus
    从总线接收数据：bus >> lambda x: x >> log
    
    # 4. 数据流类型
    创建时序数据库流：db_stream = DBStream('events')
    创建全文检索流：index_stream = IndexStream('docs')
    创建文件日志流：file_stream = FileLogStream('app.log')
    
    # 5. 流操作
    数据转换：stream.map(lambda x: x * 2) >> log
    数据过滤：stream.filter(lambda x: x > 0) >> log
    数据聚合：stream.reduce(lambda acc, x: acc + x) >> log
    时间窗口：stream.window(300) >> log  # 5分钟窗口
    
    # 6. 定时任务
    定期关注总结查看话题： content = await watch_topic('话题')
    
    # 7. 异常处理
    try:
        # 可能出错的代码
    except Exception as e:
        e >> warn
    """
    prompt = (
        f"基于以下 deva 库的核心功能和使用方法：{samplecode}，根据任务描述: {description}，生成一个Python异步函数,"
        "要求：只生成函数主体，不需要执行代码，所有 import 都放在函数内部，添加详细的代码注释，"
        "充分利用 deva 的流式编程模型和核心功能来实现任务需求"
    )
    result = await asyncio.create_task(ctx["async_gpt"](prompts=prompt))
    python_code = re.findall(r"```python(.*?)```", result or "", re.DOTALL)
    job_code = python_code[0].strip() if python_code else None
    if not job_code:
        toast("模型未返回可执行代码", color="error")
        return
    job_code >> ctx["log"]

    try:
        job = _load_job_from_code(job_code, ctx["global_ns"])
        _schedule_job(scheduler, name, job, task_type, time_value, retry_count, retry_interval)
    except ValueError as e:
        error_msg = f"任务配置错误: {e}"
        error_msg >> ctx["log"]
        toast(error_msg, color="error")
        return
    except Exception as e:
        error_msg = f"任务创建失败: {e}"
        import traceback
        traceback.format_exc() >> ctx["log"]
        toast(error_msg, color="error")
        return

    tasks[name] = {
        "type": task_type,
        "time": time_value,
        "status": "运行中",
        "description": description,
        "job_code": job_code,
        "retry_count": retry_count,
        "retry_interval": retry_interval
    }
    ctx["NB"]("tasks")[name] = tasks[name]
    toast(f"任务 '{name}' 创建成功！", color="success")
    ctx["manage_tasks"]()


def manage_tasks(ctx):
    put_text = ctx["put_text"]
    put_markdown = ctx["put_markdown"]
    put_code = ctx["put_code"]
    put_table = ctx["put_table"]
    put_row = ctx["put_row"]
    put_button = ctx["put_button"]
    put_collapse = ctx["put_collapse"]
    use_scope = ctx["use_scope"]
    textarea = ctx["textarea"]
    tasks = ctx["tasks"]
    log = ctx["log"]
    scheduler = ctx["scheduler"]
    NB = ctx["NB"]

    async def edit_code(name):
        code = await textarea("输入代码", code={"mode": "python", "theme": "darcula"}, value=tasks[name]["job_code"])
        code >> log
        tasks[name]["job_code"] = code
        NB("tasks")[name] = tasks[name]
        try:
            scheduler.remove_job(name)
        except Exception as e:
            error_msg = f"移除旧任务失败: {e}"
            error_msg >> log
        
        try:
            job_func = _load_job_from_code(code, ctx["global_ns"])
            _schedule_job(
                scheduler, 
                name, 
                job_func, 
                tasks[name]["type"], 
                tasks[name]["time"],
                tasks[name].get("retry_count", 0),
                tasks[name].get("retry_interval", 5)
            )
            success_msg = f"任务代码更新成功: {name}"
            success_msg >> log
            ctx["toast"](success_msg, color="success")
        except Exception as e:
            error_msg = f"任务代码更新失败: {e}"
            import traceback
            traceback.format_exc() >> log
            ctx["toast"](error_msg, color="error")

    with use_scope("task_management", clear=True):
        if not tasks:
            put_text("当前没有定时任务。")
            return
        tasks >> log
        active_table_data = []
        deleted_table_data = []
        
        # 导入导出功能
        async def export_tasks():
            import json
            import datetime
            
            # 准备导出数据
            export_data = {
                "version": "1.0",
                "export_time": datetime.datetime.now().isoformat(),
                "tasks": tasks
            }
            
            # 转换为JSON
            json_data = json.dumps(export_data, ensure_ascii=False, indent=2)
            
            # 创建下载文件
            from pywebio.output import put_file
            put_file("tasks_export.json", json_data.encode('utf-8'), "下载任务配置")
        
        async def import_tasks():
            from pywebio.input import file_upload
            from pywebio.output import toast
            import json
            
            # 上传文件
            file = await file_upload("选择任务配置文件", accept=".json")
            if not file:
                return
            
            try:
                # 解析JSON
                json_data = json.loads(file["content"].decode('utf-8'))
                imported_tasks = json_data.get("tasks", {})
                
                # 导入任务
                imported_count = 0
                for name, task_info in imported_tasks.items():
                    if name in tasks:
                        # 更新现有任务
                        tasks[name] = task_info
                        ctx["NB"]("tasks")[name] = task_info
                        
                        # 重新调度任务
                        try:
                            scheduler = ctx["scheduler"]
                            scheduler.remove_job(name)
                            job_func = _load_job_from_code(task_info["job_code"], ctx["global_ns"])
                            _schedule_job(
                                scheduler, 
                                name, 
                                job_func, 
                                task_info["type"], 
                                task_info["time"],
                                task_info.get("retry_count", 0),
                                task_info.get("retry_interval", 5)
                            )
                        except Exception as e:
                            e >> ctx["log"]
                    else:
                        # 创建新任务
                        tasks[name] = task_info
                        ctx["NB"]("tasks")[name] = task_info
                        
                        # 调度新任务
                        try:
                            scheduler = ctx["scheduler"]
                            job_func = _load_job_from_code(task_info["job_code"], ctx["global_ns"])
                            _schedule_job(
                                scheduler, 
                                name, 
                                job_func, 
                                task_info["type"], 
                                task_info["time"],
                                task_info.get("retry_count", 0),
                                task_info.get("retry_interval", 5)
                            )
                        except Exception as e:
                            e >> ctx["log"]
                    
                    imported_count += 1
                
                toast(f"成功导入 {imported_count} 个任务", color="success")
                ctx["manage_tasks"]()
            except json.JSONDecodeError as e:
                toast(f"JSON解析错误: {e}", color="error")
            except Exception as e:
                error_msg = f"导入失败: {e}"
                error_msg >> ctx["log"]
                toast(error_msg, color="error")
        
        # 添加导入导出按钮
        from pywebio.output import put_row
        put_row([
            put_button("导出任务", onclick=export_tasks, color="primary"),
            put_button("导入任务", onclick=import_tasks, color="primary"),
        ])
        put_text("")  # 空行
        
        # 加载任务执行历史
        task_history = ctx.get("task_history", {})
        if not task_history:
            try:
                task_history = ctx["NB"]("task_history")
                ctx["task_history"] = task_history
            except Exception as e:
                e >> log
        
        # 加载任务状态
        task_status = ctx.get("task_status", {})
        if not task_status:
            try:
                task_status = ctx["NB"]("task_status")
                ctx["task_status"] = task_status
            except Exception as e:
                e >> log
        
        # 生成有效的作用域名称
        def get_valid_scope_name(prefix, name):
            import re
            # 只保留字母、数字、连字符和下划线
            valid_name = re.sub(r'[^a-zA-Z0-9_-]', '_', name)
            return f"{prefix}_{valid_name}"
        
        # 查看任务历史的函数
        def view_history(name):
            scope_name = get_valid_scope_name("history", name)
            with use_scope(scope_name, clear=True):
                history = task_history.get(name, [])
                if not history:
                    put_text(f"任务 '{name}' 暂无执行历史。")
                    return
                
                # 按时间倒序排列
                history = sorted(history, key=lambda x: x["start_time"], reverse=True)
                
                # 显示最近10条记录
                history_data = []
                for entry in history[:10]:
                    status_color = "success" if entry["status"] == "success" else "danger"
                    row = [
                        entry["start_time"],
                        entry["end_time"],
                        f"{entry['duration']}s",
                        put_markdown(f"**{entry['status']}**"),

                        put_collapse("输出", [put_code(entry["output"][:1000] + "..." if len(entry["output"]) > 1000 else entry["output"])]),
                        put_collapse("错误", [put_code(entry["error"][:1000] + "..." if len(entry["error"]) > 1000 else entry["error"])])
                    ]
                    history_data.append(row)
                
                put_table(history_data, header=["开始时间", "结束时间", "执行时长", "状态", "输出", "错误"])
                put_button("关闭", onclick=lambda: use_scope(scope_name, clear=True))
        
        # 查看任务实时状态的函数
        def view_status(name):
            scope_name = get_valid_scope_name("status", name)
            with use_scope(scope_name, clear=True):
                status_info = task_status.get(name, {})
                if not status_info:
                    put_text(f"任务 '{name}' 暂无执行状态。")
                    return
                
                status = status_info.get("status", "unknown")
                timestamp = status_info.get("timestamp", "")
                attempt = status_info.get("attempt", 0)
                total_attempts = status_info.get("total_attempts", 0)
                error = status_info.get("error", "")
                
                status_color = {
                    "running": "info",
                    "success": "success",
                    "failed": "danger",
                    "retrying": "warning",
                    "unknown": "secondary"
                }.get(status, "secondary")
                
                status_display = {
                    "running": "运行中",
                    "success": "执行成功",
                    "failed": "执行失败",
                    "retrying": "重试中",
                    "unknown": "未知状态"
                }.get(status, "未知状态")
                
                put_markdown(f"### 任务 '{name}' 实时状态")
                put_table([
                    ["状态", put_markdown(f"**{status_display}**")],
                    ["时间戳", timestamp],
                    ["尝试次数", f"{attempt}/{total_attempts}" if total_attempts > 0 else "-"],
                    ["错误信息", put_collapse("查看错误", [put_code(error)]) if error else "-"],
                ])
                put_button("关闭", onclick=lambda: use_scope(scope_name, clear=True))
        
        for name, info in tasks.items():
            row = [name, info["description"], info["type"], info["time"], info["status"]]
            if info["status"] in ["运行中", "已停止"]:
                row.append(put_row([
                    put_button("源码", onclick=lambda n=name: edit_code(n), color="primary"),
                    put_button("停止", onclick=lambda n=name: ctx["stop_task"](n), color="danger" if info["status"] == "运行中" else "secondary", disabled=info["status"] != "运行中"),
                    put_button("启动", onclick=lambda n=name: ctx["start_task"](n), color="success" if info["status"] == "已停止" else "secondary", disabled=info["status"] != "已停止"),
                    put_button("状态", onclick=lambda n=name: view_status(n), color="info"),
                    put_button("历史", onclick=lambda n=name: view_history(n), color="info"),
                    put_button("删除", onclick=lambda n=name: ctx["delete_task"](n), color="warning"),
                ]))
                active_table_data.append(row)
            elif info["status"] == "已删除":
                row.append(put_row([
                    put_button("源码", onclick=lambda n=name: edit_code(n), color="primary"),
                    put_button("恢复", onclick=lambda n=name: ctx["recover_task"](n), color="success"),
                    put_button("状态", onclick=lambda n=name: view_status(n), color="info"),
                    put_button("历史", onclick=lambda n=name: view_history(n), color="info"),
                    put_button("彻底删除", onclick=lambda n=name: ctx["remove_task_forever"](n), color="danger"),
                ]))
                deleted_table_data.append(row)
        if active_table_data:
            put_table(active_table_data, header=["任务名称", "任务描述", "任务类型", "时间/间隔", "状态", "操作"])
        if deleted_table_data:
            with put_collapse("已删除任务", open=False):
                put_table(deleted_table_data, header=["任务名称", "任务描述", "任务类型", "时间/间隔", "状态", "操作"])


def stop_task(ctx, name):
    try:
        ctx["scheduler"].pause_job(name)
    except Exception as e:
        # Job not found, just update status
        e >> ctx["log"]
    ctx["tasks"][name]["status"] = "已停止"
    ctx["toast"](f"任务 '{name}' 已停止！", color="success")
    ctx["run_js"]("location.reload()")
    ctx["NB"]("tasks")[name] = ctx["tasks"][name]
    ctx["manage_tasks"]()


def start_task(ctx, name):
    try:
        ctx["scheduler"].resume_job(name)
    except Exception as e:
        # Job not found, recreate it
        e >> ctx["log"]
        info = ctx["tasks"][name]
        job_func = _load_job_from_code(info["job_code"], ctx["global_ns"])
        _schedule_job(ctx["scheduler"], name, job_func, info["type"], info["time"])
    ctx["tasks"][name]["status"] = "运行中"
    ctx["toast"](f"任务 '{name}' 已启动！", color="success")
    ctx["run_js"]("location.reload()")
    ctx["NB"]("tasks")[name] = ctx["tasks"][name]
    ctx["manage_tasks"]()


def delete_task(ctx, name):
    try:
        ctx["scheduler"].remove_job(name) >> ctx["log"]
    except Exception as e:
        e >> ctx["log"]
    ctx["tasks"][name].update({"status": "已删除"})
    ctx["NB"]("tasks")[name] = ctx["tasks"][name]
    ctx["toast"](f"任务 '{name}' 已删除！", color="success")
    ctx["manage_tasks"]()


def recover_task(ctx, name):
    db = ctx["NB"]("tasks")
    info = db[name]
    info["status"] = "运行中"
    ctx["tasks"][name] = info
    db[name] = info
    job_func = _load_job_from_code(info["job_code"], ctx["global_ns"])
    _schedule_job(
        ctx["scheduler"],
        name,
        job_func,
        info["type"],
        info["time"],
        info.get("retry_count", 0),
        info.get("retry_interval", 5)
    )
    ctx["manage_tasks"]()


def remove_task_forever(ctx, name):
    try:
        ctx["scheduler"].remove_job(name) >> ctx["log"]
    except Exception as e:
        e >> ctx["log"]
    del ctx["tasks"][name]
    del ctx["NB"]("tasks")[name]
    ctx["toast"](f"任务 '{name}' 已删除！", color="success")
    ctx["manage_tasks"]()


def restore_tasks_from_db(ctx):
    """从数据库恢复任务（系统启动时调用）"""
    db = ctx["NB"]("tasks")
    tasks = ctx["tasks"]
    scheduler = ctx["scheduler"]
    
    for name, info in db.items():
        tasks[name] = info
        # 只恢复运行中的任务
        if info.get("status") != "运行中":
            continue
        try:
            job_func = _load_job_from_code(info["job_code"], ctx["global_ns"])
            _schedule_job(
                scheduler,
                name,
                job_func,
                info["type"],
                info["time"],
                info.get("retry_count", 0),
                info.get("retry_interval", 5)
            )
            (f"任务 '{name}' 已从数据库恢复") >> ctx["log"]
        except Exception as e:
            (f"恢复任务 '{name}' 失败：{e}") >> ctx["log"]

    _ensure_default_strategy_task(ctx, db, tasks, scheduler)


def _ensure_default_strategy_task(ctx, db, tasks, scheduler):
    """确保默认的策略板块数据更新任务存在"""
    task_name = "策略板块数据更新"
    if task_name in tasks:
        return
    
    job_code = '''async def update_strategy_blockname():
    """
    更新策略板块基础数据
    从 akshare/tushare 获取最新的股票列表和板块映射
    """
    from deva.admin_ui.strategy.runtime import refresh_strategy_basic_df, log_strategy_event
    
    try:
        result = refresh_strategy_basic_df(force=True)
        log_strategy_event("INFO", "strategy blockname update completed", result=str(result))
        return result
    except Exception as e:
        log_strategy_event("ERROR", "strategy blockname update failed", error=str(e))
        raise
'''
    
    try:
        job_func = _load_job_from_code(job_code, ctx["global_ns"])
        _schedule_job(scheduler, task_name, job_func, "interval", 86400, retry_count=2, retry_interval=60)
        
        tasks[task_name] = {
            "type": "interval",
            "time": "86400",
            "status": "运行中",
            "description": "每天更新策略板块基础数据（股票列表、行业、概念板块）",
            "job_code": job_code,
            "retry_count": 2,
            "retry_interval": 60
        }
        db[task_name] = tasks[task_name]
        f"Default task '{task_name}' created" >> ctx["log"]
    except Exception as e:
        f"Failed to create default strategy task: {e}" >> ctx["log"]
