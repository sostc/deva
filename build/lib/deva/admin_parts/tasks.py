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
    tree = ast.parse(job_code)
    namespace = {}
    exec(job_code, global_ns, namespace)
    function_names = [node.name for node in ast.walk(tree) if isinstance(node, ast.AsyncFunctionDef)]
    if not function_names:
        raise ValueError("未生成有效的异步函数")
    return namespace[function_names[0]]


def _schedule_job(scheduler, name, job_func, task_type, time_value):
    if task_type == "interval":
        interval = int(time_value)
        scheduler.add_job(job_func, "interval", seconds=interval, id=name)
    elif task_type == "cron":
        hour, minute = map(int, str(time_value).split(":"))
        scheduler.add_job(job_func, "cron", hour=hour, minute=minute, id=name)
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
        input_comp("间隔时间（秒）或执行时间（HH:MM）", name="time", type=ctx["TEXT"])
    ])

    name = task_info["name"]
    description = task_info["description"]
    task_type = task_info["type"]
    time_value = task_info["time"]

    if name in tasks:
        toast("任务名称已存在，请使用其他名称！", color="error")
        return

    task_info >> ctx["log"]
    toast("开始创建定时任务，需要一点时间...")
    samplecode = """我有下面这些功能可以调用，使用例子如下,请选择使用里面的功能来合理完成需求：
    from deva import write_to_file,httpx,Dtalk
    from deva.admin import watch_topic
    打印日志：'sometext' >> log
    写入文件： 'some text' >>write_to_file('filename')
    抓取网页： response = await httpx(url)
    查找网页标签：response.html.search('<title>{}</title>')
    发送到钉钉通知我：'@md@焦点分析|'+'some text'>>Dtalk()
    定期关注总结查看话题： content = await watch_topic('话题')
    """
    prompt = (
        f"仅限于以下的功能和使用方法：{samplecode}，根据以下描述: {description}，生成一个Python异步函数,"
        "只生成函数主体就可以，不需要执行代码，所有 import 都放在函数内部,详细的代码注释"
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
        _schedule_job(ctx["scheduler"], name, job, task_type, time_value)
    except ValueError:
        toast("时间格式错误：interval 需要整数；cron 需要 HH:MM", color="error")
        return
    except Exception as e:
        toast(f"任务创建失败: {e}", color="error")
        return

    tasks[name] = {
        "type": task_type,
        "time": time_value,
        "status": "运行中",
        "description": description,
        "job_code": job_code
    }
    ctx["NB"]("tasks")[name] = tasks[name]
    toast(f"任务 '{name}' 创建成功！", color="success")
    ctx["manage_tasks"]()


def manage_tasks(ctx):
    put_text = ctx["put_text"]
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
            e >> log
        job_func = _load_job_from_code(code, ctx["global_ns"])
        _schedule_job(scheduler, name, job_func, tasks[name]["type"], tasks[name]["time"])

    with use_scope("task_management", clear=True):
        if not tasks:
            put_text("当前没有定时任务。")
            return
        tasks >> log
        active_table_data = []
        deleted_table_data = []
        for name, info in tasks.items():
            row = [name, info["description"], info["type"], info["time"], info["status"]]
            if info["status"] in ["运行中", "已停止"]:
                row.append(put_row([
                    put_button("源码", onclick=lambda n=name: edit_code(n), color="primary"),
                    put_button("停止", onclick=lambda n=name: ctx["stop_task"](n), color="danger" if info["status"] == "运行中" else "secondary", disabled=info["status"] != "运行中"),
                    put_button("启动", onclick=lambda n=name: ctx["start_task"](n), color="success" if info["status"] == "已停止" else "secondary", disabled=info["status"] != "已停止"),
                    put_button("删除", onclick=lambda n=name: ctx["delete_task"](n), color="warning"),
                ]))
                active_table_data.append(row)
            elif info["status"] == "已删除":
                row.append(put_row([
                    put_button("源码", onclick=lambda n=name: edit_code(n), color="primary"),
                    put_button("恢复", onclick=lambda n=name: ctx["recover_task"](n), color="success"),
                    put_button("彻底删除", onclick=lambda n=name: ctx["remove_task_forever"](n), color="danger"),
                ]))
                deleted_table_data.append(row)
        if active_table_data:
            put_table(active_table_data, header=["任务名称", "任务描述", "任务类型", "时间/间隔", "状态", "操作"])
        if deleted_table_data:
            with put_collapse("已删除任务", open=False):
                put_table(deleted_table_data, header=["任务名称", "任务描述", "任务类型", "时间/间隔", "状态", "操作"])


def stop_task(ctx, name):
    ctx["scheduler"].pause_job(name)
    ctx["tasks"][name]["status"] = "已停止"
    ctx["toast"](f"任务 '{name}' 已停止！", color="success")
    ctx["run_js"]("location.reload()")
    ctx["NB"]("tasks")[name] = ctx["tasks"][name]
    ctx["manage_tasks"]()


def start_task(ctx, name):
    ctx["scheduler"].resume_job(name)
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
    _schedule_job(ctx["scheduler"], name, job_func, info["type"], info["time"])
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
    db = ctx["NB"]("tasks")
    tasks = ctx["tasks"]
    scheduler = ctx["scheduler"]
    for name, info in db.items():
        tasks[name] = info
        if info.get("status") != "运行中":
            continue
        try:
            job_func = _load_job_from_code(info["job_code"], ctx["global_ns"])
            _schedule_job(scheduler, name, job_func, info["type"], info["time"])
        except Exception as e:
            e >> ctx["log"]
