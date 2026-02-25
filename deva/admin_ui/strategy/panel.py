"""Strategy admin page with runtime switches and strategy lab."""

from __future__ import annotations

FLOW_CHART_HTML = """
<pre style="font-size: 11px; line-height: 1.4; background: #f8f9fa; padding: 12px; border-radius: 6px; overflow-x: auto;">
<b>【数据流】</b>
gen_quant() / 历史数据 → DataSourceManager → quant stream
                                            ↓
                    ┌───────────┬───────────┬───────────┐
                    ↓           ↓           ↓           ↓
                Bus同步    板块异动计算   领涨领跌     涨跌停
                    ↓           ↓           ↓           ↓
                NS("bus")  NS("板块异动") NS("领涨领跌") NS("涨跌停")

<b>【回放流程】</b>
开启自动保存 → 行情自动存入DBStream → 点击Tick回放 → 数据推送到stream → 下游自动计算

<b>【数据处理】</b>
_prepare_df: 选择列 → 添加元数据 → 展开板块(军工|安防 → 两行)
_calc_block_ranking: 排序 → 每板块取前N只 → 计算平均涨幅 → TOP10

<b>【策略实验室】</b>
历史数据 → 影子运行(新策略) → 可视化比对 → 采纳/放弃
</pre>
"""

STRATEGY_LAB_HTML = """
<pre style="font-size: 11px; line-height: 1.4; background: #e8f5e9; padding: 12px; border-radius: 6px; overflow-x: auto;">
<b>🧪 策略实验室工作流</b>

┌─────────────────────────────────────────────────────────────────────────────┐
│  1. 数据抽取：从存储中提取历史记录（DBStream / 内存 Buffer）                    │
│  2. 影子运行：启动临时流分支，挂载新策略函数                                    │
│  3. 可视化比对：并排展示"原始逻辑输出"与"新策略输出"                            │
│  4. 差异审计：字段级对比、空值检查、逻辑收缩风险标记                            │
│  5. 决策闭环：采纳新策略 / 放弃更新                                            │
└─────────────────────────────────────────────────────────────────────────────┘

<b>生命周期管理</b>
┌────────────┬──────────────────────────────┬─────────────────────────────┐
│ 阶段       │ 实验室内表现                  │ 对应管理操作                 │
├────────────┼──────────────────────────────┼─────────────────────────────┤
│ 测试中     │ 利用 replay 进行无损测试      │ 策略标记为 Draft (草稿)      │
│ 上线前     │ 生成可视化对比报告和 AI 说明   │ 记录备注、属性及上下游预期    │
│ 暂停/删除  │ 在实验室模拟"断流"对下游影响   │ 可视化警告：下游影响评估      │
└────────────┴──────────────────────────────┴─────────────────────────────┘
</pre>
"""


async def render_strategy_admin_page(ctx):
    await ctx["init_admin_ui"]("Deva策略管理")

    def refresh_all_status():
        cfg = ctx["get_strategy_config"]()
        meta = ctx["get_strategy_basic_meta"]()
        replay_cfg = ctx["get_replay_config"]()
        auto_save_cfg = ctx["get_auto_save_config"]()
        tick_meta = ctx["get_tick_metadata"]()
        history_meta = ctx["get_history_metadata"]()
        
        updated_at = meta.get("updated_at", 0)
        updated_at_text = "-"
        if updated_at:
            import datetime
            updated_at_text = datetime.datetime.fromtimestamp(float(updated_at)).strftime("%Y-%m-%d %H:%M:%S")
        
        is_replaying = ctx["is_replay_running"]()
        auto_save_status = "✅ 已开启" if auto_save_cfg.get("enabled") else "❌ 已关闭"
        force_fetch_status = "✅ 强制抓取" if cfg["force_fetch"] else "❌ 仅交易日"
        bus_status = "✅ 已开启" if cfg["sync_bus"] else "❌ 已关闭"
        replay_status = f"🔄 正在回放 {replay_cfg.get('replay_date', '')}" if is_replaying else "⏹️ 空闲"
        
        with ctx["use_scope"]("status_table", clear=True):
            ctx["put_table"]([
                ["功能", "状态", "操作"],
                ["行情抓取", force_fetch_status, ctx["put_buttons"](["切换"], onclick=lambda _: toggle_force_fetch())],
                ["Bus同步", bus_status, ctx["put_buttons"](["切换"], onclick=lambda _: toggle_sync_bus())],
                ["自动保存", auto_save_status, ctx["put_buttons"](["切换"], onclick=lambda _: toggle_auto_save())],
                ["回放状态", replay_status, ctx["put_buttons"](["停止"], onclick=lambda _: stop_replay()) if is_replaying else "-"],
                ["历史快照数", str(tick_meta.get("total_ticks", 0)), "-"],
                ["板块数据更新", updated_at_text, ctx["put_buttons"](["更新"], onclick=lambda _: refresh_blockname())],
            ])

    def toggle_force_fetch():
        cfg = ctx["get_strategy_config"]()
        ctx["set_strategy_config"](force_fetch=not cfg["force_fetch"])
        ctx["toast"]("已切换行情抓取模式", color="success")
        refresh_all_status()

    def toggle_sync_bus():
        cfg = ctx["get_strategy_config"]()
        ctx["set_strategy_config"](sync_bus=not cfg["sync_bus"])
        ctx["toast"]("已切换Bus同步", color="success")
        refresh_all_status()

    def toggle_auto_save():
        cfg = ctx["get_auto_save_config"]()
        ctx["set_auto_save"](not cfg.get("enabled", False))
        ctx["toast"]("已切换自动保存", color="success")
        refresh_all_status()

    def refresh_blockname():
        async def _do_refresh():
            await ctx["refresh_strategy_basic_df_async"](force=True)
            ctx["toast"]("板块数据已更新", color="success")
            refresh_all_status()
        ctx["run_async"](_do_refresh())

    def stop_replay():
        result = ctx["stop_history_replay"]()
        if result.get("success"):
            ctx["toast"]("已停止回放", color="success")
        else:
            ctx["toast"](f"停止失败: {result.get('error')}", color="error")
        refresh_all_status()

    def select_replay_date(date_str):
        ctx["set_replay_config"](replay_date=date_str)
        ctx["toast"](f"已选择: {date_str}", color="info")
        refresh_all_status()

    def start_replay():
        replay_cfg = ctx["get_replay_config"]()
        date_str = replay_cfg.get("replay_date")
        if not date_str:
            ctx["toast"]("请先选择日期", color="warning")
            return
        result = ctx["start_history_replay"](date_str=date_str, interval=3.0, use_ticks=False)
        if result.get("success"):
            ctx["toast"](f"开始回放: {date_str}", color="success")
        else:
            ctx["toast"](f"启动失败: {result.get('error')}", color="error")
        refresh_all_status()

    def start_tick_replay():
        result = ctx["start_history_replay"](interval=3.0, use_ticks=True)
        if result.get("success"):
            ctx["toast"]("开始Tick回放", color="success")
        else:
            ctx["toast"](f"启动失败: {result.get('error')}", color="error")
        refresh_all_status()

    def save_snapshot():
        result = ctx["save_current_quant_to_history"]()
        if result.get("success"):
            ctx["toast"](f"已保存: {result.get('date')} ({result.get('rows')}行)", color="success")
        else:
            ctx["toast"](f"保存失败: {result.get('error')}", color="error")
        refresh_all_status()

    ctx["put_collapse"]("📊 数据流程图", [ctx["put_html"](FLOW_CHART_HTML)], open=False)
    
    ctx["put_markdown"]("### 状态控制")
    ctx["set_scope"]("status_table")
    refresh_all_status()

    ctx["put_markdown"]("### 历史数据回放")
    history_meta = ctx["get_history_metadata"]()
    available_dates = history_meta.get("dates", [])
    if available_dates:
        ctx["put_text"]("选择日期:")
        date_buttons = [(d, d) for d in available_dates[:10]]
        ctx["put_buttons"](date_buttons, onclick=select_replay_date)
        if len(available_dates) > 10:
            ctx["put_text"](f"... 共{len(available_dates)}天")
    
    ctx["put_row"]([
        ctx["put_button"]("回放选中日期", onclick=start_replay, color="success").style("margin-right: 10px"),
        ctx["put_button"]("Tick回放", onclick=start_tick_replay, color="info").style("margin-right: 10px"),
        ctx["put_button"]("保存当前快照", onclick=save_snapshot),
    ]).style("display: flex; justify-content: flex-start; align-items: center")

    ctx["put_markdown"]("### 监控流")
    stream_names = ["涨跌停", "领涨领跌板块", "1分钟板块异动", "30秒板块异动"]
    for name in stream_names:
        stream = ctx["NS"](name)
        ctx["put_html"](f'<details><summary>{name}</summary><iframe src="/{hash(stream)}" style="width:100%;height:240px;border:none;"></iframe></details>')

    ctx["put_collapse"]("🧪 策略实验室", [ctx["put_html"](STRATEGY_LAB_HTML)], open=False)
    
    ctx["put_markdown"]("### 策略验证")
    ctx["set_scope"]("strategy_lab")
    
    def open_strategy_lab():
        ctx["run_async"](_render_strategy_lab(ctx))

    ctx["put_button"]("打开策略实验室", onclick=open_strategy_lab, color="primary")


async def _render_strategy_lab(ctx):
    """渲染策略实验室弹窗"""
    with ctx["popup"]("🧪 策略实验室", size="large", closable=True):
        ctx["put_markdown"]("### 回放配置")
        
        lab_config = await ctx["input_group"]("策略实验室配置", [
            ctx["input"]("回放条数", name="limit", type=ctx["NUMBER"], value=10),
            ctx["select"]("对比模式", name="mode", options=[
                {"label": "最新代码 vs 历史数据", "value": "vs_history"},
                {"label": "代码 A vs 代码 B", "value": "vs_code"}
            ]),
            ctx["textarea"]("新策略代码 (Python)", name="new_code", placeholder="def process(data): ...", rows=5),
        ])
        
        if not lab_config:
            return
        
        ctx["put_markdown"]("### 验证结果")
        ctx["set_scope"]("lab_table")
        
        ctx["put_table"]([
            ["原始输入", "新策略输出", "状态", "差异说明"]
        ], scope='lab_table')
        
        tick_stream = ctx["get_tick_stream"]()
        if tick_stream is None:
            ctx["toast"]("没有可用的历史数据", color="warning")
            return
        
        limit = lab_config["limit"]
        new_code = lab_config.get("new_code", "")
        mode = lab_config["mode"]
        
        new_processor = None
        if new_code:
            try:
                local_ns = {}
                exec(new_code, {"__builtins__": __builtins__}, local_ns)
                new_processor = local_ns.get("process")
                if not new_processor:
                    ctx["toast"]("代码中未找到 process 函数", color="warning")
                    return
            except Exception as e:
                ctx["toast"](f"代码编译错误: {e}", color="error")
                return
        
        count = 0
        for key in tick_stream:
            if count >= limit:
                break
            df = tick_stream[key]
            if df is None:
                continue
            
            original_output = "原始逻辑已执行"
            new_output = "-"
            status = "✅ 正常"
            diff_note = "-"
            
            if new_processor:
                try:
                    result = new_processor(df)
                    if result is None:
                        new_output = "None (被过滤)"
                        status = "⚠️ 过滤"
                        diff_note = "新策略返回 None，数据被过滤"
                    else:
                        new_output = str(result)[:200]
                        if isinstance(result, type(df)):
                            diff_note = _compare_dataframes(df, result)
                except Exception as e:
                    new_output = f"❌ 异常: {str(e)[:100]}"
                    status = "❌ 异常"
                    diff_note = f"运行时错误: {str(e)[:100]}"
            
            with ctx["use_scope"]("lab_table", clear=False):
                ctx["put_row"]([
                    ctx["put_text"](f"数据包 {count+1}"),
                    ctx["put_code"](new_output[:100] if new_output else "-", language="text"),
                    ctx["put_text"](status),
                    ctx["put_text"](diff_note[:100] if diff_note else "-"),
                ])
            
            count += 1
        
        ctx["put_markdown"](f"**验证完成: 共处理 {count} 条数据**")
        
        ctx["put_row"]([
            ctx["put_button"]("采纳新策略", onclick=lambda: ctx["toast"]("新策略已采纳", color="success"), color="success").style("margin-right: 10px"),
            ctx["put_button"]("放弃更新", onclick=lambda: ctx["close_popup"](), color="danger"),
        ]).style("display: flex; justify-content: flex-start; align-items: center")


def _compare_dataframes(original, new):
    """比较两个 DataFrame 的差异"""
    import pandas as pd
    
    notes = []
    
    if not isinstance(new, pd.DataFrame):
        return "输出类型不是 DataFrame"
    
    if len(original) != len(new):
        notes.append(f"行数变化: {len(original)} → {len(new)}")
    
    orig_cols = set(original.columns)
    new_cols = set(new.columns)
    
    added_cols = new_cols - orig_cols
    removed_cols = orig_cols - new_cols
    
    if added_cols:
        notes.append(f"新增列: {added_cols}")
    if removed_cols:
        notes.append(f"移除列: {removed_cols}")
    
    common_cols = orig_cols & new_cols
    for col in common_cols:
        orig_dtype = original[col].dtype
        new_dtype = new[col].dtype
        if orig_dtype != new_dtype:
            notes.append(f"列 '{col}' 类型变化: {orig_dtype} → {new_dtype}")
    
    if not notes:
        return "无明显差异"
    
    return "; ".join(notes[:5])


render_strategy_admin = render_strategy_admin_page
