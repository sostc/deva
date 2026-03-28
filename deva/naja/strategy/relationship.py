"""策略关系分析模块

分析策略之间的血缘关系、相似度、适用场景
提供可视化的策略关系图
"""

STRATEGY_RELATIONSHIPS = {
    "选股场景": {
        "color": "#10b981",
        "bg_color": "#dcfce7",
        "strategies": [
            "早期牛股发现",
            "板块牛股精选",
            "实时选股策略-流式学习版",
        ],
        "description": "从大量股票中筛选出最有潜力的标的",
        "typical_flow": "先用市场状态分类判断环境，再用资金流向/板块动量过滤，最后用选股策略精选"
    },
    "方向预测": {
        "color": "#3b82f6",
        "bg_color": "#dbeafe",
        "strategies": [
            "上涨概率预测",
            "早期趋势检测",
            "river_短期方向概率_top",
        ],
        "description": "预测价格短期走向，判断涨跌概率",
        "typical_flow": "结合波动率分析和量价异常检测，确认方向信号"
    },
    "市场分析": {
        "color": "#8b5cf6",
        "bg_color": "#ede9fe",
        "strategies": [
            "市场状态分类",
            "板块动量分析",
            "资金流向分析",
        ],
        "description": "分析整体市场状态和板块轮动",
        "typical_flow": "市场状态分类 → 板块动量 → 资金流向 → 选股"
    },
    "异常检测": {
        "color": "#ef4444",
        "bg_color": "#fee2e2",
        "strategies": [
            "市场异常检测(HST)",
            "微观波动异常检测",
            "波动率分析",
            "早期预警系统",
        ],
        "description": "检测市场异常状态，预警风险",
        "typical_flow": "发现异常后可能触发止损或停止其他策略"
    },
    "信号融合": {
        "color": "#f59e0b",
        "bg_color": "#fef3c7",
        "strategies": [
            "Bandit交易信号",
            "新闻舆情记忆",
        ],
        "description": "综合多源信息生成最终交易信号",
        "typical_flow": "收集各类策略信号，Bandit选择最优执行"
    },
}

STRATEGY_DIMENSIONS = {
    "早期牛股发现": {
        "data_type": ["价格", "成交量"],
        "time_horizon": "中期",
        "output_type": "信号",
        "risk_level": "中高",
    },
    "板块牛股精选": {
        "data_type": ["板块", "动量"],
        "time_horizon": "中期",
        "output_type": "信号",
        "risk_level": "中",
    },
    "实时选股策略-流式学习版": {
        "data_type": ["价格", "成交量", "波动率"],
        "time_horizon": "短期",
        "output_type": "信号",
        "risk_level": "中",
    },
    "上涨概率预测": {
        "data_type": ["价格", "成交量"],
        "time_horizon": "短期",
        "output_type": "概率",
        "risk_level": "中",
    },
    "早期趋势检测": {
        "data_type": ["价格", "成交量"],
        "time_horizon": "中期",
        "output_type": "信号",
        "risk_level": "中",
    },
    "river_短期方向概率_top": {
        "data_type": ["价格", "成交量", "盘口"],
        "time_horizon": "超短期",
        "output_type": "概率",
        "risk_level": "中",
    },
    "市场状态分类": {
        "data_type": ["价格", "成交量", "波动率"],
        "time_horizon": "任意",
        "output_type": "分类",
        "risk_level": "低",
    },
    "板块动量分析": {
        "data_type": ["板块", "动量"],
        "time_horizon": "中期",
        "output_type": "排序",
        "risk_level": "中",
    },
    "资金流向分析": {
        "data_type": ["资金流", "大单"],
        "time_horizon": "短期",
        "output_type": "分数",
        "risk_level": "中",
    },
    "市场异常检测(HST)": {
        "data_type": ["价格", "成交量", "波动率"],
        "time_horizon": "任意",
        "output_type": "布尔",
        "risk_level": "高",
    },
    "微观波动异常检测": {
        "data_type": ["价格", "盘口"],
        "time_horizon": "超短期",
        "output_type": "模式",
        "risk_level": "高",
    },
    "波动率分析": {
        "data_type": ["波动率"],
        "time_horizon": "任意",
        "output_type": "等级",
        "risk_level": "高",
    },
    "早期预警系统": {
        "data_type": ["趋势", "波动率", "成交量", "动量"],
        "time_horizon": "任意",
        "output_type": "预警",
        "risk_level": "高",
    },
    "Bandit交易信号": {
        "data_type": ["综合信号"],
        "time_horizon": "任意",
        "output_type": "决策",
        "risk_level": "中",
    },
    "新闻舆情记忆": {
        "data_type": ["新闻", "舆情", "文本"],
        "time_horizon": "中长期",
        "output_type": "主题",
        "risk_level": "低",
    },
}

STRATEGY_SIMILARITY = [
    ("早期牛股发现", "早期趋势检测", 0.7, "都用于早期发现趋势"),
    ("资金流向分析", "板块动量分析", 0.6, "都分析资金/板块轮动"),
    ("市场异常检测(HST)", "微观波动异常检测", 0.8, "都是异常检测"),
    ("波动率分析", "早期预警系统", 0.6, "都关注风险"),
    ("上涨概率预测", "river_短期方向概率_top", 0.9, "都是短期方向概率"),
    ("实时选股策略-流式学习版", "板块牛股精选", 0.5, "都是选股策略"),
    ("实时选股策略-流式学习版", "早期牛股发现", 0.4, "都关注早期启动"),
]

STRATEGY_RECOMMENDED_FLOWS = [
    {
        "name": "稳健选股",
        "steps": ["市场状态分类", "板块动量分析", "板块牛股精选"],
        "description": "先判断市场环境，再分析板块轮动，最后精选个股"
    },
    {
        "name": "激进选股",
        "steps": ["早期趋势检测", "资金流向分析", "早期牛股发现"],
        "description": "追逐动量和资金流向，发掘早期启动的牛股"
    },
    {
        "name": "短线交易",
        "steps": ["river_短期方向概率_top", "微观波动异常检测", "Bandit交易信号"],
        "description": "高频判断短期方向，检测异常，Bandit选择最优执行"
    },
    {
        "name": "风控预警",
        "steps": ["市场异常检测(HST)", "波动率分析", "早期预警系统"],
        "description": "多维度检测市场异常，设置综合预警"
    },
    {
        "name": "舆情驱动",
        "steps": ["新闻舆情记忆", "市场状态分类", "板块动量分析"],
        "description": "基于舆情分析市场状态，指导板块配置"
    },
]


def get_strategy_scenarios() -> dict:
    """获取策略场景分类"""
    return STRATEGY_RELATIONSHIPS


def get_strategy_dimensions(strategy_name: str) -> dict:
    """获取策略的维度信息"""
    return STRATEGY_DIMENSIONS.get(strategy_name, {})


def get_strategy_similarity() -> list:
    """获取策略相似度列表"""
    return STRATEGY_SIMILARITY


def get_recommended_flows() -> list:
    """获取推荐的策略使用流程"""
    return STRATEGY_RECOMMENDED_FLOWS


def build_relationship_html() -> str:
    """构建策略关系图的HTML"""
    scenarios = STRATEGY_RELATIONSHIPS
    flows = STRATEGY_RECOMMENDED_FLOWS

    html = '''
    <div style="background:#f8fafc;border-radius:12px;padding:20px;margin-top:20px;border:1px solid #e2e8f0;">
        <div style="font-size:16px;font-weight:600;color:#1e293b;margin-bottom:16px;display:flex;align-items:center;gap:8px;">
            🧬 策略血缘关系与场景分析
        </div>

        <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;">
            <!-- 左侧：场景分类 -->
            <div style="background:#fff;border-radius:8px;padding:16px;border:1px solid #e5e7eb;">
                <div style="font-size:13px;font-weight:600;color:#374151;margin-bottom:12px;">📂 按场景分类</div>
    '''

    for scenario_name, scenario_data in scenarios.items():
        strategies_html = ""
        for s in scenario_data["strategies"]:
            strategies_html += f'<span style="display:inline-block;padding:2px 8px;background:{scenario_data["bg_color"]};color:{scenario_data["color"]};border-radius:4px;font-size:11px;margin:2px;">{s}</span>'

        html += f'''
                <div style="margin-bottom:14px;padding-bottom:14px;border-bottom:1px solid #f1f5f9;">
                    <div style="display:flex;align-items:center;gap:6px;margin-bottom:8px;">
                        <span style="width:10px;height:10px;border-radius:50%;background:{scenario_data["color"]};"></span>
                        <span style="font-size:12px;font-weight:600;color:#1e293b;">{scenario_name}</span>
                    </div>
                    <div style="font-size:11px;color:#64748b;margin-bottom:6px;">{scenario_data["description"]}</div>
                    <div>{strategies_html}</div>
                </div>
        '''

    html += '''
            </div>

            <!-- 右侧：推荐流程 -->
            <div style="background:#fff;border-radius:8px;padding:16px;border:1px solid #e5e7eb;">
                <div style="font-size:13px;font-weight:600;color:#374151;margin-bottom:12px;">🔗 推荐使用流程</div>
    '''

    for flow in flows:
        steps_html = " → ".join([f'<span style="color:#3b82f6;font-weight:500;">{s}</span>' for s in flow["steps"]])
        html += f'''
                <div style="margin-bottom:12px;padding:10px;background:#f8fafc;border-radius:6px;">
                    <div style="font-size:12px;font-weight:600;color:#1e293b;margin-bottom:4px;">{flow["name"]}</div>
                    <div style="font-size:11px;color:#64748b;margin-bottom:6px;">{flow["description"]}</div>
                    <div style="font-size:11px;">{steps_html}</div>
                </div>
        '''

    html += '''
            </div>
        </div>

        <!-- 策略维度表 -->
        <div style="margin-top:20px;background:#fff;border-radius:8px;padding:16px;border:1px solid #e5e7eb;">
            <div style="font-size:13px;font-weight:600;color:#374151;margin-bottom:12px;">📊 策略维度对比</div>
            <div style="overflow-x:auto;">
                <table style="width:100%;border-collapse:collapse;font-size:11px;">
                    <thead>
                        <tr style="background:#f1f5f9;">
                            <th style="padding:8px 10px;text-align:left;color:#64748b;font-weight:500;">策略</th>
                            <th style="padding:8px 10px;text-align:left;color:#64748b;font-weight:500;">数据类型</th>
                            <th style="padding:8px 10px;text-align:left;color:#64748b;font-weight:500;">时间维度</th>
                            <th style="padding:8px 10px;text-align:left;color:#64748b;font-weight:500;">输出类型</th>
                            <th style="padding:8px 10px;text-align:left;color:#64748b;font-weight:500;">风险等级</th>
                        </tr>
                    </thead>
                    <tbody>
    '''

    for strategy_name, dims in STRATEGY_DIMENSIONS.items():
        data_types = ", ".join(dims.get("data_type", []))
        time_horizon = dims.get("time_horizon", "-")
        output_type = dims.get("output_type", "-")
        risk = dims.get("risk_level", "-")
        risk_color = {"低": "#10b981", "中": "#f59e0b", "中高": "#f97316", "高": "#ef4444"}.get(risk, "#64748b")

        html += f'''
                        <tr style="border-bottom:1px solid #f1f5f9;">
                            <td style="padding:8px 10px;color:#1e293b;font-weight:500;">{strategy_name}</td>
                            <td style="padding:8px 10px;color:#64748b;">{data_types}</td>
                            <td style="padding:8px 10px;color:#64748b;">{time_horizon}</td>
                            <td style="padding:8px 10px;color:#64748b;">{output_type}</td>
                            <td style="padding:8px 10px;"><span style="color:{risk_color};font-weight:500;">{risk}</span></td>
                        </tr>
        '''

    html += '''
                    </tbody>
                </table>
            </div>
        </div>
    </div>
    '''

    return html
