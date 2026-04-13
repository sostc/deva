"""热点系统 UI 智能增强面板"""

from deva.naja.market_hotspot.tracking.history_tracker import get_history_tracker


def get_intelligence_system():
    """获取智能增强系统"""
    try:
        from deva.naja.market_hotspot.integration.market_hotspot_integration import MarketHotspotIntegration
        integration = MarketHotspotIntegration()  # 单例，不会重复创建
        if hasattr(integration, 'intelligence_system') and integration.intelligence_system is not None:
            return integration.intelligence_system
        return None
    except Exception:
        return None


def get_block_name(block_id: str) -> str:
    """获取题材名称"""
    tracker = get_history_tracker()
    if tracker and hasattr(tracker, 'get_block_name'):
        return tracker.get_block_name(block_id)
    return block_id


def render_predictive_hotspot_panel() -> str:
    """渲染预测个股热点面板"""
    intelligence_system = get_intelligence_system()
    if not intelligence_system or not hasattr(intelligence_system, 'predictive_engine'):
        return """
        <div style="background: #f0f9ff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 16px;">
            <div style="font-weight: 600; margin-bottom: 8px; color: #64748b;">🔮 预测个股 <span style="font-size: 11px; color: #94a3b8;">未启用</span></div>
            <div style="color: #94a3b8; font-size: 12px;">预测热点引擎未初始化</div>
        </div>
        """

    try:
        tracker = get_history_tracker()

        market_time = ""
        try:
            from deva.naja.attention.orchestration.trading_center import get_trading_center
            tc = get_trading_center()
            market_time = tc.get_cached_market_time()
        except Exception:
            pass

        top_predictions = intelligence_system.predictive_engine.get_predictions_top_k(k=5)
        if not top_predictions:
            return """
            <div style="background: #f0f9ff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 16px;">
                <div style="font-weight: 600; margin-bottom: 8px;">🔮 预测个股</div>
                <div style="color: #64748b; font-size: 12px;">暂无预测数据</div>
            </div>
            """

        time_html = f"<div style='font-size: 11px; color: #64748b; margin-bottom: 8px;'>📊 {market_time}</div>" if market_time else ""

        items_html = ""
        for item in list(top_predictions)[:5]:
            if isinstance(item, tuple) and len(item) == 2:
                symbol, pred_score = item
                curr_att = intelligence_system.predictive_engine._last_scores.get(symbol, 0.5)
                symbol_name = tracker.get_symbol_name(symbol) if tracker and hasattr(tracker, 'get_symbol_name') else ""
                display_name = f"{symbol} {symbol_name}" if symbol_name else symbol
            else:
                continue
            bar_width = pred_score * 100
            emoji = "🟢" if pred_score >= 0.8 else ("🟡" if pred_score >= 0.6 else "🔴")
            items_html += f"""
            <div style="margin-bottom: 8px;">
                <div style="display: flex; justify-content: space-between; font-size: 12px;">
                    <span style="font-weight: 600;">{emoji} {display_name}</span>
                    <span style="color: #64748b;">{pred_score:.3f}</span>
                </div>
                <div style="background: #e2e8f0; height: 4px; border-radius: 2px; margin-top: 4px;">
                    <div style="background: linear-gradient(90deg, #0ea5e9, #06b6d4); height: 4px; border-radius: 2px; width: {bar_width}%;"></div>
                </div>
            </div>
            """

        return f"""
        <div style="background: #f0f9ff; border: 1px solid #0ea5e944; border-radius: 12px; padding: 16px;">
            <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 12px;">
                <span style="font-size: 18px;">🔮</span>
                <span style="font-weight: 600;">预测个股</span>
            </div>
            {time_html}
            {items_html}
        </div>
        """
    except Exception as e:
        return f"""
        <div style="background: #f0f9ff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 16px;">
            <div style="font-weight: 600; margin-bottom: 8px;">🔮 预测个股</div>
            <div style="color: #ef4444; font-size: 12px;">Error: {str(e)}</div>
        </div>
        """


def render_block_predictive_hotspot_panel() -> str:
    """渲染预测题材热点面板"""
    intelligence_system = get_intelligence_system()
    if not intelligence_system or not hasattr(intelligence_system, 'predictive_engine'):
        return """
        <div style="background: #fef3c7; border: 1px solid #fcd34d44; border-radius: 12px; padding: 16px;">
            <div style="font-weight: 600; color: #64748b;">🏛️ 预测题材 <span style="font-size: 11px; color: #94a3b8;">未启用</span></div>
            <div style="color: #94a3b8; font-size: 12px; margin-top: 8px;">预测引擎未初始化</div>
        </div>
        """

    try:
        market_time = ""
        try:
            from deva.naja.attention.orchestration.trading_center import get_trading_center
            tc = get_trading_center()
            market_time = tc.get_cached_market_time()
        except Exception:
            pass

        try:
            from deva.naja.market_hotspot.processing.block_noise_detector import get_block_noise_detector
            noise_detector = get_block_noise_detector()
        except ImportError:
            noise_detector = None

        if noise_detector:
            def is_noise_block(block_id: str) -> bool:
                block_name = get_block_name(block_id)
                return noise_detector.is_noise(block_id, block_name)
        else:
            blacklist_patterns = [
                '通达信', '系统', 'ST', 'B股', '基金', '指数', '期权', '期货',
                '上证', '深证', '沪深', '大盘', '权重', '综合', '行业', '地域',
                '概念', '风格', '上证所', '深交所', '_sys', '_index', '884',
            ]
            def is_noise_block(block_id: str) -> bool:
                name = get_block_name(block_id)
                display = name if name else block_id
                for pattern in blacklist_patterns:
                    if pattern in display or pattern in block_id:
                        return True
                return False

        top_block_predictions = intelligence_system.predictive_engine.get_block_predictions_top_k(k=20)
        filtered_predictions = [
            (block_id, score) for block_id, score in top_block_predictions
            if not is_noise_block(block_id)
        ][:5]

        noise_count = len(top_block_predictions) - len(filtered_predictions)

        if not filtered_predictions:
            return """
            <div style="background: #fef3c7; border: 1px solid #fcd34d44; border-radius: 12px; padding: 16px;">
                <div style="font-weight: 600;">🏛️ 预测题材</div>
                <div style="color: #64748b; font-size: 12px; margin-top: 8px;">暂无有效题材预测数据（已过滤噪声题材）</div>
            </div>
            """

        time_html = f"<div style='font-size: 11px; color: #64748b; margin-bottom: 8px;'>📊 {market_time}</div>" if market_time else ""

        items_html = ""
        for item in list(filtered_predictions)[:5]:
            if isinstance(item, tuple) and len(item) == 2:
                block_id, pred_score = item
                block_name = get_block_name(block_id)
                display_name = block_name if block_name else block_id
            else:
                continue
            bar_width = pred_score * 100
            emoji = "🟢" if pred_score >= 0.8 else ("🟡" if pred_score >= 0.6 else "🔴")
            items_html += f"""
            <div style="margin-bottom: 8px;">
                <div style="display: flex; justify-content: space-between; font-size: 12px;">
                    <span style="font-weight: 600;">{emoji} {display_name}</span>
                    <span style="color: #64748b;">{pred_score:.3f}</span>
                </div>
                <div style="background: #e2e8f0; height: 4px; border-radius: 2px; margin-top: 4px;">
                    <div style="background: linear-gradient(90deg, #f59e0b, #fbbf24); height: 4px; border-radius: 2px; width: {bar_width}%;"></div>
                </div>
            </div>
            """

        help_text = f"""
        <div style="margin-top: 12px; padding-top: 12px; border-top: 1px dashed #fcd34d; font-size: 11px; color: #64748b;">
            💡 题材预测 = 题材内个股加权扩散概率，高分=题材活跃可能持续 | 已过滤 {noise_count} 个噪声题材
        </div>
        """

        return f"""
        <div style="background: #fef3c7; border: 1px solid #fcd34d44; border-radius: 12px; padding: 16px;">
            <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 12px;">
                <span style="font-size: 18px;">🏛️</span>
                <span style="font-weight: 600;">预测题材</span>
            </div>
            {time_html}
            {items_html}
            {help_text}
        </div>
        """
    except Exception as e:
        return f"""
        <div style="background: #fef3c7; border: 1px solid #fcd34d44; border-radius: 12px; padding: 16px;">
            <div style="font-weight: 600;">🏛️ 预测题材</div>
            <div style="color: #ef4444; font-size: 12px; margin-top: 8px;">Error: {str(e)}</div>
        </div>
        """


def render_intelligence_panels() -> str:
    """渲染所有智能增强面板 - 一行两个模块"""
    return f"""
    <div style="display: flex; flex-direction: column; gap: 12px;">
        {render_intelligence_summary_panel()}
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
            <div>{render_predictive_hotspot_panel()}</div>
            <div>{render_block_predictive_hotspot_panel()}</div>
            <div>{render_feedback_loop_panel()}</div>
            <div>{render_budget_panel()}</div>
            <div style="grid-column: span 2;">{render_strategy_learning_panel()}</div>
        </div>
    </div>
    """


def render_propagation_panel() -> str:
    """渲染题材扩散面板"""
    intelligence_system = get_intelligence_system()
    if not intelligence_system or not hasattr(intelligence_system, 'propagation'):
        return """
        <div style="background: #fae8ff; border: 1px solid #f5d0fe; border-radius: 12px; padding: 16px; margin-top: 16px;">
            <div style="font-weight: 600; margin-bottom: 8px; color: #64748b;">🌊 题材联动 <span style="font-size: 11px; color: #94a3b8;">未启用</span></div>
            <div style="color: #94a3b8; font-size: 12px;">题材联动未初始化</div>
        </div>
        """

    try:
        tracker = get_history_tracker()
        propagation = intelligence_system.propagation
        summary = propagation.get_propagation_summary()
        blacklist = propagation.get_blacklist()
        relations = propagation.get_all_relations()[:5]

        filtered_relations = []
        for rel in relations:
            if hasattr(rel, 'source_block') and hasattr(rel, 'target_block'):
                if rel.source_block not in blacklist and rel.target_block not in blacklist:
                    filtered_relations.append(rel)

        relations_html = ""
        for rel in filtered_relations:
            source_name = get_block_name(rel.source_block)
            target_name = get_block_name(rel.target_block)
            source_display = source_name if source_name != rel.source_block else rel.source_block
            target_display = target_name if target_name != rel.target_block else rel.target_block
            corr = rel.correlation
            delay = rel.delay_ticks
            quality = getattr(rel, 'strength', 1.0)
            quality_emoji = "🟢" if quality >= 0.5 else ("🟡" if quality >= 0.3 else "🔴")
            relations_html += f"<div style='margin-bottom: 4px;'>{quality_emoji} {source_display} → {target_display} <span style='color:#9333ea;'>相关度{corr:.2f}</span> <span style='color:#94a3b8;'>延迟{delay}t</span></div>"

        if not filtered_relations:
            status_html = """
            <div style="color: #94a3b8; font-size: 12px;">
                <div>正在学习有效题材关联...</div>
                <div style="margin-top: 4px; font-size: 11px;">已过滤无意义的题材关系</div>
            </div>
            """
        else:
            status_html = f"""
            <div style="font-size: 11px; color: #64748b; margin-bottom: 8px;">
                共 {summary.get('total_blocks', 0)} 个题材，已过滤 {len(blacklist)} 个噪声题材
            </div>
            <div style="color: #1e293b;">{relations_html}</div>
            """

        return f"""
        <div style="background: #fae8ff; border: 1px solid #f5d0fe; border-radius: 12px; padding: 16px; margin-top: 16px;">
            <div style="font-weight: 600; margin-bottom: 8px;">🌊 题材联动</div>
            <div style="font-size: 12px;">
                <div style="color: #64748b; margin-bottom: 4px;">有效题材关联 Top5:</div>
                {status_html}
            </div>
            <div style="margin-top: 8px; padding-top: 8px; border-top: 1px dashed #e9d5ff; font-size: 11px; color: #94a3b8;">
                🟢高质量 🟡中等 🔴低质量 | 自动过滤噪声题材和虚假关联
            </div>
        </div>
        """
    except Exception as e:
        import traceback
        return f"""
        <div style="background: #fae8ff; border: 1px solid #f5d0fe; border-radius: 12px; padding: 16px; margin-top: 16px;">
            <div style="font-weight: 600; margin-bottom: 8px;">🌊 题材联动</div>
            <div style="color: #ef4444; font-size: 12px;">Error: {str(e)}</div>
        </div>
        """


def render_block_propagation_panel() -> str:
    """渲染题材题材联动详情面板"""
    intelligence_system = get_intelligence_system()
    if not intelligence_system or not hasattr(intelligence_system, 'propagation'):
        return ""

    try:
        tracker = get_history_tracker()
        propagation = intelligence_system.propagation
        blacklist = propagation.get_blacklist()

        valid_blocks = []
        if tracker:
            valid_blocks = tracker.filter_valid_blocks(list(blacklist))

        if len(blacklist) == 0:
            return ""

        return f"""
        <div style="background: #fef3c7; border: 1px solid #fcd34d; border-radius: 12px; padding: 12px; margin-top: 12px;">
            <div style="font-weight: 600; margin-bottom: 8px; color: #92400e;">🚫 噪声题材黑名单 ({len(blacklist)} 个)</div>
            <div style="font-size: 11px; color: #78350f;">
                已自动过滤: 含B股、通达信88等噪声题材
            </div>
        </div>
        """
    except Exception:
        return ""


def render_intelligence_summary_panel() -> str:
    """渲染智能增强系统总览面板 - 酷炫版本"""
    intelligence_system = get_intelligence_system()
    if not intelligence_system:
        return """
        <div style="background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); border: 1px solid #334155; border-radius: 16px; padding: 20px; margin-top: 16px; box-shadow: 0 4px 24px rgba(0,0,0,0.3);">
            <div style="display: flex; align-items: center; gap: 12px;">
                <span style="font-size: 28px;">🧠</span>
                <div>
                    <div style="font-weight: 700; font-size: 18px; color: #f1f5f9;">智能增强系统</div>
                    <div style="font-size: 12px; color: #94a3b8;">未启用</div>
                </div>
            </div>
            <div style="background: #1e293b; border-radius: 8px; padding: 12px; color: #64748b; font-size: 13px; margin-top: 16px;">
                系统未初始化，请在配置中启用智能增强功能
            </div>
        </div>
        """

    try:
        summary = intelligence_system.get_summary()
        enabled = summary.get('enabled_modules', {})

        enabled_modules = [k for k, v in enabled.items() if v]
        disabled_modules = [k for k, v in enabled.items() if not v]

        module_icons = {'predictive': '🔮', 'feedback': '🔄', 'budget': '⚡', 'propagation': '🌊', 'strategy_learning': '🎯'}
        module_labels = {'predictive': '预测热点', 'feedback': '反馈学习', 'budget': '算力分配', 'propagation': '题材联动', 'strategy_learning': '策略实践'}

        modules_html = ""
        for mod in enabled_modules:
            icon = module_icons.get(mod, '⚡')
            label = module_labels.get(mod, mod)
            modules_html += f"""<div style="display: inline-flex; align-items: center; gap: 6px; background: linear-gradient(135deg, #16a34a22, #16a34a11); border: 1px solid #16a34a44; border-radius: 20px; padding: 6px 12px; margin: 4px; font-size: 12px; color: #16a34a;"><span>{icon}</span><span style="font-weight: 600;">{label}</span></div>"""

        for mod in disabled_modules:
            icon = module_icons.get(mod, '⚡')
            label = module_labels.get(mod, mod)
            modules_html += f"""<div style="display: inline-flex; align-items: center; gap: 6px; background: linear-gradient(135deg, #47556922, #47556911); border: 1px solid #47556944; border-radius: 20px; padding: 6px 12px; margin: 4px; font-size: 12px; color: #64748b;"><span>{icon}</span><span>{label}</span></div>"""

        avg_latency = summary.get('base_status', {}).get('avg_latency_ms', 0)

        return f"""
        <div style="background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); border: 1px solid #0ea5e944; border-radius: 16px; padding: 20px; margin-top: 16px; box-shadow: 0 4px 24px rgba(14, 165, 233, 0.15); position: relative; overflow: hidden;">
            <div style="position: absolute; top: -50%; left: -50%; width: 200%; height: 200%; background: radial-gradient(circle at 30% 30%, #0ea5e908 0%, transparent 50%); pointer-events: none;"></div>
            <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 16px; position: relative;">
                <span style="font-size: 32px; filter: drop-shadow(0 2px 4px rgba(14, 165, 233, 0.3));">🧠</span>
                <div>
                    <div style="font-weight: 700; font-size: 18px; color: #f1f5f9;">智能增强系统</div>
                    <div style="font-size: 12px; color: #16a34a; display: flex; align-items: center; gap: 6px;">
                        <span style="width: 6px; height: 6px; background: #16a34a; border-radius: 50%; animation: pulse 2s infinite;"></span>
                        已启用 {len(enabled_modules)} 个模块
                    </div>
                </div>
            </div>
            <div style="display: flex; flex-wrap: wrap; margin-bottom: 16px; position: relative;">{modules_html}</div>
            <div style="display: flex; gap: 16px; padding-top: 12px; border-top: 1px solid #334155; position: relative;">
                <div style="flex: 1;">
                    <div style="font-size: 11px; color: #64748b; margin-bottom: 2px;">计算延迟</div>
                    <div style="font-size: 16px; font-weight: 600; color: #0ea5e9;">{avg_latency:.1f}ms</div>
                </div>
                <div style="flex: 1;">
                    <div style="font-size: 11px; color: #64748b; margin-bottom: 2px;">系统状态</div>
                    <div style="font-size: 16px; font-weight: 600; color: #16a34a;">运行中</div>
                </div>
            </div>
        </div>
        <style>@keyframes pulse {{ 0%, 100% {{ opacity: 1; }} 50% {{ opacity: 0.5; }} }}</style>
        """
    except Exception as e:
        return f"""<div style="background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); border: 1px solid #ef444444; border-radius: 16px; padding: 20px; margin-top: 16px;"><div style="font-weight: 600; color: #ef4444;">🧠 智能增强系统</div><div style="color: #ef4444; font-size: 12px; margin-top: 8px;">Error: {str(e)}</div></div>"""


def render_feedback_loop_panel() -> str:
    """渲染反馈学习面板"""
    intelligence_system = get_intelligence_system()
    if not intelligence_system or not hasattr(intelligence_system, 'feedback_loop'):
        return """<div style="background: #fef3c7; border: 1px solid #fcd34d; border-radius: 12px; padding: 16px;"><div style="font-weight: 600; margin-bottom: 8px; color: #64748b;">🔄 反馈学习 <span style="font-size: 11px; color: #94a3b8;">未启用</span></div><div style="color: #94a3b8; font-size: 12px;">反馈学习未初始化</div></div>"""

    try:
        import time
        summary = intelligence_system.feedback_loop.get_summary()
        effective = intelligence_system.feedback_loop.get_effective_patterns()
        ineffective = intelligence_system.feedback_loop.get_ineffective_patterns()
        effective_html = "无" if not effective else ", ".join(effective[:2])
        ineffective_html = "无" if not ineffective else ", ".join(ineffective[:2])
        recent_outcomes = intelligence_system.feedback_loop.collector.get_recent_outcomes(n=100)
        recent_24h = sum(1 for o in recent_outcomes if time.time() - o.timestamp < 86400)

        return f"""
        <div style="background: #fef3c7; border: 1px solid #fcd34d44; border-radius: 12px; padding: 16px;">
            <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 12px;">
                <span style="font-size: 18px;">🔄</span>
                <span style="font-weight: 600;">反馈学习</span>
            </div>
            <div style="font-size: 12px; margin-bottom: 8px;">
                <div style="color: #16a34a; margin-bottom: 4px;">✅ {effective_html}</div>
                <div style="color: #dc2626;">❌ {ineffective_html}</div>
            </div>
            <div style="display: flex; gap: 12px; font-size: 11px; color: #64748b;">
                <span>总数: {summary.get('total_outcomes', 0)}</span>
                <span>24h: {recent_24h}</span>
            </div>
        </div>
        """
    except Exception as e:
        return f"""<div style="background: #fef3c7; border: 1px solid #fcd34d; border-radius: 12px; padding: 16px;"><div style="font-weight: 600; margin-bottom: 8px;">🔄 反馈学习</div><div style="color: #ef4444; font-size: 12px;">Error: {str(e)}</div></div>"""


def render_budget_panel() -> str:
    """渲染算力分配面板"""
    intelligence_system = get_intelligence_system()
    if not intelligence_system or not hasattr(intelligence_system, 'budget_system'):
        return """<div style="background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 12px; padding: 16px;"><div style="font-weight: 600; margin-bottom: 8px; color: #64748b;">⚡ 算力分配 <span style="font-size: 11px; color: #94a3b8;">未启用</span></div><div style="color: #94a3b8; font-size: 12px;">算力分配未初始化</div></div>"""

    try:
        summary = intelligence_system.get_summary()
        budget_summary = summary.get('budget_summary', {})
        allocation_summary = budget_summary.get('allocation_summary', {})

        utilization = allocation_summary.get('budget_utilization', 0)
        tier1_count = allocation_summary.get('tier1_count', 0)
        tier2_count = allocation_summary.get('tier2_count', 0)
        tier3_count = allocation_summary.get('tier3_count', 0)

        return f"""
        <div style="background: #f0fdf4; border: 1px solid #bbf7d044; border-radius: 12px; padding: 16px;">
            <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 12px;">
                <span style="font-size: 18px;">💰</span>
                <span style="font-weight: 600;">算力分配</span>
            </div>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; font-size: 12px;">
                <div><div style="color: #64748b;">使用率</div><div style="font-weight: 600; color: #16a34a; font-size: 16px;">{utilization:.0%}</div></div>
                <div><div style="color: #64748b;">高频</div><div style="font-weight: 600; color: #dc2626;">{tier1_count}</div></div>
                <div><div style="color: #64748b;">中频</div><div style="font-weight: 600;">{tier2_count}</div></div>
                <div><div style="color: #64748b;">低频</div><div style="font-weight: 600;">{tier3_count}</div></div>
            </div>
        </div>
        """
    except Exception as e:
        return f"""<div style="background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 12px; padding: 16px;"><div style="font-weight: 600; margin-bottom: 8px;">⚡ 算力分配</div><div style="color: #ef4444; font-size: 12px;">Error: {str(e)}</div></div>"""


def render_strategy_learning_panel() -> str:
    """渲染策略实践面板"""
    intelligence_system = get_intelligence_system()
    if not intelligence_system or not hasattr(intelligence_system, 'strategy_learning'):
        return """<div style="background: #fdf4ff; border: 1px solid #e9d5ff; border-radius: 12px; padding: 16px;"><div style="font-weight: 600; margin-bottom: 8px; color: #64748b;">🎯 策略实践 <span style="font-size: 11px; color: #94a3b8;">未启用</span></div><div style="color: #94a3b8; font-size: 12px;">策略实践未初始化</div></div>"""

    try:
        summary = intelligence_system.strategy_learning.get_selection_summary()
        learning_stats = intelligence_system.strategy_learning.get_learning_stats()
        market_state = summary.get('market_state', 'unknown')
        selected_strategies = summary.get('selected_strategies', [])
        strategies_html = ", ".join(selected_strategies[:2]) if selected_strategies else "无"

        return f"""
        <div style="background: #fdf4ff; border: 1px solid #e9d5ff44; border-radius: 12px; padding: 16px;">
            <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 12px;">
                <span style="font-size: 18px;">📚</span>
                <span style="font-weight: 600;">策略实践</span>
            </div>
            <div style="font-size: 12px;">
                <div style="color: #64748b; margin-bottom: 4px;">状态: <span style="color: #7c3aed;">{market_state}</span></div>
                <div style="color: #64748b; margin-bottom: 4px;">策略: {strategies_html}</div>
                <div style="color: #64748b;">学习: {learning_stats.get('total_updates', 0)} 次</div>
            </div>
        </div>
        """
    except Exception as e:
        return f"""<div style="background: #fdf4ff; border: 1px solid #e9d5ff; border-radius: 12px; padding: 16px;"><div style="font-weight: 600; margin-bottom: 8px;">🎯 策略实践</div><div style="color: #ef4444; font-size: 12px;">Error: {str(e)}</div></div>"""
