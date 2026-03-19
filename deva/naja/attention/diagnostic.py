"""
注意力系统诊断工具

在 Web UI 中查看注意力系统的运行状态
"""

from typing import Dict, Any
from pywebio.output import *
from pywebio.session import run_js


def _initialize_from_diagnostic():
    """从诊断页面初始化注意力系统"""
    try:
        from ..attention_config import load_config
        from ..attention_integration import initialize_attention_system
        
        config = load_config()
        if config.enabled:
            attention_system = initialize_attention_system(config)
            put_success("✅ 注意力系统初始化成功！")
            put_text(f"系统: {attention_system}")
            put_button("刷新页面", onclick=lambda: run_js("window.location.reload()"))
        else:
            put_warning("⚠️ 注意力系统被禁用（配置中 enabled=False）")
    except Exception as e:
        put_error(f"❌ 初始化失败: {e}")
        import traceback
        put_text(traceback.format_exc())


def render_attention_diagnostic():
    """渲染注意力系统诊断页面"""
    
    put_html("<h2>🔍 注意力系统诊断</h2>")
    
    # 1. 检查注意力集成
    put_html("<h3>1. 注意力集成状态</h3>")
    try:
        from ..attention_integration import get_attention_integration
        integration = get_attention_integration()
        
        if integration is None:
            put_error("❌ 注意力集成未初始化")
        else:
            put_success("✅ 注意力集成已创建")
            
            if integration.attention_system is None:
                put_error("❌ 注意力系统未初始化")
                put_text("")
                put_html("""
                <div style="padding:12px;border-radius:8px;background:#fef2f2;border:1px solid #fecaca;color:#991b1b;">
                    <strong>可能原因：</strong><br>
                    1. naja 启动时未使用 --attention 参数<br>
                    2. 环境变量 NAJA_ATTENTION_ENABLED 未设置为 true<br>
                    3. 配置文件中 enabled 被设置为 false
                </div>
                """)
                put_text("")
                put_button("🚀 立即初始化注意力系统", onclick=lambda: _initialize_from_diagnostic(), color="danger")
            else:
                put_success("✅ 注意力系统已创建")
                
                # 显示状态
                report = integration.get_attention_report()
                put_text(f"全局注意力: {report.get('global_attention', 0):.3f}")
                put_text(f"处理快照数: {report.get('processed_snapshots', 0)}")
                put_text(f"状态: {report.get('status', 'unknown')}")
                
                # 显示权重数量
                sector_weights = integration.attention_system.sector_attention.get_all_weights()
                symbol_weights = integration.attention_system.weight_pool.get_all_weights()
                
                put_text(f"板块权重数: {len(sector_weights)}")
                put_text(f"个股权重数: {len(symbol_weights)}")
                
                if len(symbol_weights) > 0:
                    # 显示Top 5
                    top_symbols = sorted(symbol_weights.items(), key=lambda x: x[1], reverse=True)[:5]
                    put_text("Top 5 股票:")
                    for symbol, weight in top_symbols:
                        put_text(f"  {symbol}: {weight:.3f}")
                else:
                    put_warning("⚠️ 没有计算任何个股权重")
                    
    except Exception as e:
        put_error(f"❌ 错误: {e}")
    
    # 2. 检查调度中心
    put_html("<h3>2. 调度中心状态</h3>")
    try:
        from ..attention_orchestrator import get_orchestrator
        orchestrator = get_orchestrator()
        
        put_success("✅ 调度中心已创建")
        put_text(f"处理帧数: {orchestrator._processed_frames}")
        put_text(f"过滤帧数: {orchestrator._filtered_frames}")
        put_text(f"注册数据源: {list(orchestrator._datasources.keys())}")
        
        if orchestrator._processed_frames == 0:
            put_warning("⚠️ 调度中心没有处理任何数据！")
            put_text("可能原因:")
            put_text("1. 数据源没有 emit 数据")
            put_text("2. 数据源没有正确绑定到调度中心")
            put_text("3. 数据格式不正确（不是 DataFrame）")
        else:
            put_success(f"✅ 数据流正常: 已处理 {orchestrator._processed_frames} 帧")
            
    except Exception as e:
        put_error(f"❌ 错误: {e}")
    
    # 3. 检查历史追踪器
    put_html("<h3>3. 历史追踪器状态</h3>")
    try:
        from .history_tracker import get_history_tracker
        tracker = get_history_tracker()
        
        put_success("✅ 历史追踪器已创建")
        
        summary = tracker.get_summary()
        put_text(f"快照数: {summary['snapshot_count']}")
        put_text(f"变化数: {summary['change_count']}")
        put_text(f"最近变化: {summary['recent_changes']}")
        
        if summary['snapshot_count'] == 0:
            put_warning("⚠️ 历史追踪器没有记录任何快照！")
        
        # 显示变化
        changes = tracker.get_recent_changes(n=10)
        if changes:
            put_text(f"最近 {len(changes)} 条变化:")
            for change in changes[-5:]:
                emoji = {
                    'new_hot': '🔥',
                    'cooled': '❄️',
                    'strengthen': '📈',
                    'weaken': '📉'
                }.get(change.change_type, '•')
                put_text(f"{emoji} {change.description}")
        else:
            put_text("暂无变化记录")
            
    except Exception as e:
        put_error(f"❌ 错误: {e}")
    
    # 4. 检查策略管理器
    put_html("<h3>4. 策略管理器状态</h3>")
    try:
        from naja_attention_strategies import get_strategy_manager
        manager = get_strategy_manager()
        
        stats = manager.get_all_stats()
        
        if stats['is_running']:
            put_success("🟢 策略管理器运行中")
        else:
            put_error("🔴 策略管理器已停止")
        
        put_text(f"总策略数: {stats['total_strategies']}")
        put_text(f"活跃策略: {stats['active_strategies']}")
        put_text(f"总信号数: {stats['total_signals_generated']}")
        
        if stats['total_strategies'] == 0:
            put_warning("⚠️ 没有注册任何策略！")
        else:
            put_text("各策略统计:")
            for strategy_id, strategy_stats in stats['strategy_stats'].items():
                status = "🟢" if strategy_stats['enabled'] else "🔴"
                put_text(f"  {status} {strategy_stats['name']}: 执行 {strategy_stats['execution_count']} 次, 信号 {strategy_stats['signal_count']} 个")
        
        # 实验模式
        exp_info = manager.get_experiment_info()
        if exp_info.get('active'):
            put_success(f"🧪 实验模式运行中: {exp_info.get('datasource_id')}")
        else:
            put_text("⚪ 实验模式未启动")
            
    except Exception as e:
        put_error(f"❌ 错误: {e}")
    
    # 5. 检查数据源
    put_html("<h3>5. 数据源状态</h3>")
    try:
        from ..datasource import get_datasource_manager
        ds_mgr = get_datasource_manager()
        
        # 尝试获取数据源信息
        try:
            # 不同的 DataSourceManager 可能有不同的方法
            datasources = ds_mgr.get_all() if hasattr(ds_mgr, 'get_all') else []
            put_text(f"数据源数量: {len(datasources)}")
            
            for ds in datasources:
                status = "🟢 运行中" if getattr(ds, 'is_running', False) else "🔴 停止"
                put_text(f"  {status}: {getattr(ds, 'name', 'Unknown')}")
        except:
            put_text("无法获取数据源列表")
            
    except Exception as e:
        put_error(f"❌ 错误: {e}")
    
    put_html("<hr>")
    put_text("诊断完成。如果发现问题，请检查：")
    put_text("1. 数据源是否正在运行")
    put_text("2. 实验模式是否正确启动")
    put_text("3. 数据格式是否正确（需要包含 code, p_change, volume 字段）")
