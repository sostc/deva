"""策略图表常量与原理渲染函数"""

from deva.naja.common.ui_style import render_detail_section

STRATEGY_NAME_TO_DIAGRAM = {
    "river_短期方向概率_top": {
        "icon": "🌊",
        "color": "#3b82f6",
        "description": "河流比喻：短期方向概率预测",
        "formula": "up_probability = sigmoid(linear_combination(features))",
        "logic": [
            "接收 tick 数据作为水波纹",
            "计算五维河流特征（向、速、弹、深、波）",
            "在线学习察觉水势变化",
            "输出上涨概率"
        ],
        "output": "up_probability: 0.0-1.0, direction: up/down, confidence: 0.0-1.0",
        "principle": {
            "core_mechanism": "把市场想象成河流，tick是波纹。通过在线学习察觉水势变化，预测水流方向。",
            "key_insights": [
                "河流的水流方向代表价格变动方向，持续观察能发现规律",
                "向：水流偏向哪边；速：水流有多急；弹：碰到石头会不会跳",
                "深：河道宽窄；波：水面是否在起浪",
                "up_probability 表示水流向上涨方向流动的概率"
            ],
            "when_to_use": "需要判断短期方向时使用，如择时、止损止盈等。"
        }
    },
    "river_量价盘口异常分数_top": {
        "icon": "🌊",
        "color": "#8b5cf6",
        "description": "河流比喻：量价盘口异常检测",
        "formula": "anomaly_score = sum(|feature - expected|) / n",
        "logic": [
            "接收 tick 数据流",
            "计算五维河流特征",
            "HalfSpaceTrees 检测河流异常状态",
            "输出异常分数"
        ],
        "output": "anomaly_score: 0.0-1.0, is_anomaly: bool, feature_contributions: {...}",
        "principle": {
            "core_mechanism": "用 HalfSpaceTrees 检测河流异常状态，识别水流突变、河道变化。",
            "key_insights": [
                "向：水流忽然回旋说明遇到阻挡；速：忽然急湍表示有新力量进入",
                "弹：水花四溅代表价格冲击；深：河道宽窄反映盘口厚度",
                "波：水面起浪说明成交在放大；异常分数越高，河流越不稳定",
                "可以提前发现市场异常状态，如同在河流中提前发现漩涡"
            ],
            "when_to_use": "需要发现市场异常、规避风险时使用。"
        }
    },
    "早期趋势检测": {
        "icon": "🔮",
        "color": "#f59e0b",
        "description": "早期趋势发现，识别市场状态转变的早期信号",
        "formula": "trend_indicator = α * price_change + β * volume_change",
        "logic": [
            "监测价格和成交量的早期变化",
            "多周期窗口对比分析",
            "识别趋势形成的前兆",
            "输出早期预警信号"
        ],
        "output": "trend_score: 0.0-1.0, trend_type: emerging/established/reversing",
        "principle": {
            "core_mechanism": "像在河流中观察水流的早期变化，当上游开始下雨时，下游需要时间才能察觉。",
            "key_insights": [
                "趋势形成前总有前兆，如同天气预报看云层",
                "价格变化 + 成交量变化 = 趋势强度",
                "多周期对比能区分噪音和真实趋势",
                "早期发现意味着更大的安全边际"
            ],
            "when_to_use": "需要捕捉趋势启动的早期信号时使用，如追涨、趋势跟踪策略。"
        }
    },
    "市场状态分类": {
        "icon": "📊",
        "color": "#10b981",
        "description": "市场状态分类，识别当前市场环境",
        "formula": "market_state = argmax(P(trending|features), P(rangebound|features), P(volatile|features))",
        "logic": [
            "提取市场特征（波动率、趋势性、成交量）",
            "基于历史模式分类",
            "输出市场状态标签",
            "持续更新状态估计"
        ],
        "output": "market_state: trending/rangebound/volatile, confidence: 0.0-1.0",
        "principle": {
            "core_mechanism": "如同观察河流是平静流淌、快速流动还是波涛汹涌。",
            "key_insights": [
                "trending：河流沿着河道稳定流动，适合顺流而下",
                "rangebound：河流在两岸间来回摆动，适合区间操作",
                "volatile：河流波涛汹涌，风险较高需要谨慎",
                "知道当前状态才能选择合适的策略，如同看天出行"
            ],
            "when_to_use": "任何策略执行前都需要先判断市场状态，如同出行前先看天气。"
        }
    },
    "题材动量分析": {
        "icon": "🌊",
        "color": "#8b5cf6",
        "description": "河流比喻：题材间轮动与动量强度分析",
        "formula": "momentum_score = Σ(block_imbalance) * rotation_speed",
        "logic": [
            "接收题材行情数据流",
            "计算题材间资金流向（河流分支）",
            "测量动量强度与轮动速度",
            "识别强势题材与弱势题材"
        ],
        "output": "rising_blocks: [...], falling_blocks: [...], momentum_score: 0.0-1.0",
        "principle": {
            "core_mechanism": "把题材想象成河流的不同分支，资金在水流间转移形成轮动。观察哪些分支流得更快更急，能判断水的能量分布。",
            "key_insights": [
                "动量强的题材像急流，资金持续流入形成趋势",
                "轮动速度反映热点切换频率，快轮动需要快进快出",
                "强势题材回调后往往二次启动，如同瀑布落下后的反弹",
                "资金集中度 = 河流宽度，越宽说明资金越集中"
            ],
            "when_to_use": "需要捕捉题材轮动、优化行业配置时使用。"
        }
    },
    "资金流向分析": {
        "icon": "💰",
        "color": "#10b981",
        "description": "河流比喻：大单资金追踪与资金集中度分析",
        "formula": "capital_score = money_weight * 0.6 + strength_weight * 0.4",
        "logic": [
            "分解订单流为大单/小单（主流/支流）",
            "计算资金集中度与涨跌强弱",
            "综合评分排序",
            "输出资金信号"
        ],
        "output": "capital_scores: [{code, score, money_flow}], top_picks: [...]",
        "principle": {
            "core_mechanism": "大单就像河流的主流，小单像支流。观察主流的流向和速度，能判断整条河的能量方向。",
            "key_insights": [
                "资金集中度 = 主流占比，主流越强趋势越明确",
                "涨跌强弱 = 水流对河岸的冲击力度",
                "综合得分高意味着资金和趋势共振，是强势信号",
                "资金流入先于价格上涨，如同上游下雨下游水位先涨"
            ],
            "when_to_use": "需要跟随大资金、寻找强势股票时使用。"
        }
    },
    "波动率分析": {
        "icon": "🌊",
        "color": "#ef4444",
        "description": "河流比喻：水面波动幅度与市场风险检测",
        "formula": "volatility_zscore = (current_vol - ema_vol) / std_vol",
        "logic": [
            "计算价格波动率序列",
            "Z-score 标准化异常检测",
            "多周期波动率对比",
            "输出风险等级"
        ],
        "output": "volatility_level: low/medium/high/extreme, zscore: -3.0~3.0",
        "principle": {
            "core_mechanism": "水面平静如镜时风险低，波浪翻滚时风险高。通过测量波浪幅度判断市场情绪。",
            "key_insights": [
                "低波动率 = 水面平静，可能酝酿突破",
                "高波动率 = 水面翻涌，风险与机会并存",
                "Z-score > 2 表示异常波动，需要警惕",
                "波动率聚集现象：剧烈波动后往往持续一段时间"
            ],
            "when_to_use": "需要评估市场风险、设置止损止盈时使用。"
        }
    },
    "早期牛股发现": {
        "icon": "🔮",
        "color": "#f59e0b",
        "description": "河流比喻：在源头发现最具潜力的种子股票",
        "formula": "early_score = momentum * volume_ratio * age_factor",
        "logic": [
            "监测启动初期的股票",
            "计算动量与成交量爆发因子",
            "评估启动位置与时间窗口",
            "输出早期牛股信号"
        ],
        "output": "early_bulls: [{code, score, startup_phase}], top_picks: [...]",
        "principle": {
            "core_mechanism": "像在河流源头发现最有潜力的小溪，在股票刚刚启动时就识别出来。",
            "key_insights": [
                "牛股启动时如同小溪汇入大河，初期能量虽小但方向明确",
                "动量 + 成交量 + 启动位置 = 早期强度",
                "启动位置越低，未来成长空间越大",
                "早期发现意味着成本优势和更大的上涨空间"
            ],
            "when_to_use": "需要寻找高成长标的、愿意承担早期风险时使用。"
        }
    },
    "市场异常检测(HST)": {
        "icon": "🌊",
        "color": "#dc2626",
        "description": "河流比喻：HalfSpaceTrees 异常检测识别市场突变",
        "formula": "anomaly_score = depth_score / tree_depth",
        "logic": [
            "HalfSpaceTrees 在线构建异常树",
            "接收 tick 数据评估异常深度",
            "多维度特征综合评分",
            "输出异常信号与置信度"
        ],
        "output": "is_anomaly: bool, anomaly_score: 0.0-1.0, feature_contribs: {...}",
        "principle": {
            "core_mechanism": "用 HalfSpaceTrees 把正常市场状态建模为河流的正常流态，任何偏离都像漩涡或湍流被检测出来。",
            "key_insights": [
                " HST 像在河流中布下渔网，正常水流穿网而过，异常会被拦住",
                "正常状态外的任何变化都是异常，如同平静水面突然出现漩涡",
                "异常分数越高说明偏离正常流态越远",
                "可以检测到大资金进出、新闻事件影响等引起的市场波动"
            ],
            "when_to_use": "需要实时监控市场异常、防范黑天鹅时使用。"
        }
    },
    "微观波动异常检测": {
        "icon": "🌊",
        "color": "#7c3aed",
        "description": "河流比喻：识别水面的细微涟漪与高频抖动",
        "formula": "micro_volatility = σ(price_changes) * tick_frequency",
        "logic": [
            "高频采样价格变动",
            "计算微观波动率与抖动",
            "识别震荡/放大/收缩模式",
            "输出微观结构信号"
        ],
        "output": "pattern: oscillation/spike/contraction, intensity: 0.0-1.0",
        "principle": {
            "core_mechanism": "观察水面的细微涟漪来预判大浪。微观波动往往先于宏观趋势出现。",
            "key_insights": [
                "小幅震荡 = 水面在积蓄能量，可能突破",
                "突然放大 = 水面被投入石子，可能有大事发生",
                "收缩模式 = 水流在变窄，可能酝酿方向选择",
                "微观信号比宏观信号更早出现，但噪音也更大"
            ],
            "when_to_use": "需要高频交易、捕捉短期机会时使用。"
        }
    },
    "早期预警系统": {
        "icon": "⚠️",
        "color": "#f97316",
        "description": "河流比喻：综合多维度预警，提前发现风险与机会",
        "formula": "warning_score = w1*trend + w2*volatility + w3*volume + w4*momentum",
        "logic": [
            "综合趋势、波动率、成交量等多维度",
            "加权计算综合预警分数",
            "设置多级别预警阈值",
            "输出风险/机会预警信号"
        ],
        "output": "warning_level: green/yellow/orange/red, alert_type: risk/opportunity",
        "principle": {
            "core_mechanism": "像在河流中设置多个观测点，任何一个点出现异常都能触发预警。综合判断比单一指标更可靠。",
            "key_insights": [
                "趋势 + 波动率 + 成交量 + 动量 = 多维度预警",
                "黄色预警：远端有乌云；橙色预警：开始下雨；红色预警：山洪暴发",
                "预警级别越高，需要越快做出响应",
                "机会预警和风险预警同等重要，都是预警"
            ],
            "when_to_use": "需要综合判断市场状态、设置风控预警时使用。"
        }
    },
    "题材牛股精选": {
        "icon": "🎯",
        "color": "#10b981",
        "description": "河流比喻：从概念题材的众多支流中精选最强的一支",
        "formula": "block_strength = Σ(stock_momentum * block_correlation) / n",
        "logic": [
            "计算题材内个股动量",
            "分析题材联动性强度",
            "精选动量最强的牛股",
            "过滤噪音与弱势股票"
        ],
        "output": "top_bulls: [{code, block_score, momentum}], selected: [...]",
        "principle": {
            "core_mechanism": "题材像多条汇入大河的支流，最强的支流往往带动整个水系。通过分析支流强弱选出真正的牛股。",
            "key_insights": [
                "题材联动性 = 支流间的相互影响强度",
                "动量最强的个股 = 最强支流，有引领整个题材的潜力",
                "过滤噪音 = 排除看起来水流急但实际是漩涡的股票",
                "精选策略比广撒网更高效"
            ],
            "when_to_use": "需要精选个股而非选题材时使用。"
        }
    },
    "上涨概率预测": {
        "icon": "📈",
        "color": "#8b5cf6",
        "description": "河流比喻：LogisticRegression 在线学习预测短期方向概率",
        "formula": "P(rise) = sigmoid(w0 + w1*ret + w2*vol_ratio + w3*p_change)",
        "logic": [
            "提取价格变动、成交量比率等特征",
            "LogisticRegression 在线学习",
            "预测短期上涨概率",
            "输出概率排序结果"
        ],
        "output": "probabilities: [{code, prob, ret}], top_predictions: [...]",
        "principle": {
            "core_mechanism": "持续观察河流的水流方向变化，学习什么样的水势组合最可能导致上涨。类似老渔夫看水势判断鱼群走向。",
            "key_insights": [
                "ret = 水流速度，vol_ratio = 水流量，p_change = 水位变化",
                "模型在线学习，根据最新水势不断调整判断",
                "概率 > 0.5 意味着上涨可能性大于下跌",
                "置信度越高，预测越可靠"
            ],
            "when_to_use": "需要预测短期方向概率时使用，如择时、风控等。"
        }
    },
    "river_stock_picker_755b128e": {
        "icon": "🌊",
        "color": "#3b82f6",
        "description": "河流比喻：基于机器学习在线选股，持续优化交易策略",
        "formula": "stock_score = model.predict_proba(features) > buy_threshold",
        "logic": [
            "提取价格、波动率、成交量等特征",
            "LogisticRegression 在线学习",
            "持续更新选股模型",
            "触发阈值时生成买入信号"
        ],
        "output": "buy_signals: [...], sell_signals: [...], portfolio: {...}",
        "principle": {
            "core_mechanism": "让模型像老船夫一样，通过长期观察河流学会判断什么时候该下网、什么时候该收网。",
            "key_insights": [
                "price_change = 水流方向和速度，volatility = 波浪大小，volume_ratio = 水流量",
                "模型持续学习，不断优化判断准确性",
                "buy_threshold = 下网的时机，score 超过阈值才行动",
                "在线学习让模型能适应市场变化"
            ],
            "when_to_use": "需要自动化选股和交易时使用。"
        }
    },
    "Bandit交易信号": {
        "icon": "🎰",
        "color": "#f59e0b",
        "description": "河流比喻：Bandit算法优化交易信号的选择与执行",
        "formula": "signal_value = Σ(reward * confidence) / exploration_bonus",
        "logic": [
            "收集多个信号源的候选信号",
            "Bandit算法评估信号价值",
            "平衡探索与利用",
            "输出最优交易信号"
        ],
        "output": "best_signal: {type, stock, action, confidence}, all_signals: [...]",
        "principle": {
            "core_mechanism": "像在多条河流分支中选择最有价值的那一条。Bandit算法平衡'确定收益'和'探索新机会'。",
            "key_insights": [
                "多信号源 = 多条可能的河流，每条都通向不同的地方",
                "exploitation = 走最熟悉的那条河，exploration = 探索新路线",
                "UCB算法平衡两者：既不过于保守，也不过于冒险",
                "奖励机制让算法学会选择真正能带来收益的信号"
            ],
            "when_to_use": "有多个策略信号需要选择时使用，如信号融合、策略组合等。"
        }
    },
}


def _get_fallback_diagram_info(entry) -> dict:
    """如果策略没有 diagram_info，尝试通过策略名获取默认的图表信息"""
    name = getattr(entry._metadata, 'name', '') or entry.name

    if name in STRATEGY_NAME_TO_DIAGRAM:
        return STRATEGY_NAME_TO_DIAGRAM[name]

    # 支持策略ID别名映射
    entry_id = getattr(entry._metadata, 'id', '') or entry.id
    if entry_id in STRATEGY_NAME_TO_DIAGRAM:
        return STRATEGY_NAME_TO_DIAGRAM[entry_id]

    return {}


from pywebio.input import input_group, input, textarea, select, actions
from pywebio.session import run_async

from deva.naja.common.ui_style import apply_strategy_like_styles, render_empty_state, format_timestamp, render_status_badge, render_detail_section
from deva.naja.page_help import render_help_collapse

try:
    from deva.naja.strategy.handler_type import get_strategy_handler_type, StrategyHandlerType
    HANDLER_TYPE_AVAILABLE = True
except ImportError:
    HANDLER_TYPE_AVAILABLE = False


DEFAULT_STRATEGY_CODE = '''# 策略处理函数
# 必须定义 process(data) 函数
# data 通常是 pandas DataFrame

def process(data):
    """
    策略执行主体函数
    
    参数:
        data: 输入数据 (通常为 pandas.DataFrame)
    
    返回:
        处理后的数据
    """
    import pandas as pd
    
    # 示例：直接返回原始数据
    return data
'''

DEFAULT_DECLARATIVE_CONFIG = {
    "pipeline": [
        {"type": "feature", "name": "price_change"},
        {"type": "feature", "name": "volume_spike"},
    ],
    "model": {"type": "logistic_regression"},
    "params": {"learning_rate": 0.01},
    "logic": {"type": "threshold", "buy": 0.7, "sell": 0.3},
    "state_persist": True,
    "state_persist_interval": 300,
    "state_persist_every_n": 200,
}


def _render_strategy_help(ctx: dict):
    """渲染策略系统帮助说明"""
    render_help_collapse("strategy")


def _render_type_badge(strategy_type: str) -> str:
    stype = str(strategy_type or "legacy").lower()
    color = "#64748b"
    bg = "#f1f5f9"
    label = stype
    if stype == "declarative":
        color = "#0ea5e9"
        bg = "#e0f2fe"
        label = "declarative"
    elif stype == "river":
        color = "#10b981"
        bg = "#dcfce7"
        label = "river"
    elif stype == "plugin":
        color = "#8b5cf6"
        bg = "#ede9fe"
        label = "plugin"
    elif stype == "attention":
        color = "#f59e0b"
        bg = "#fef3c7"
        label = "attention"
    elif stype == "legacy":
        label = "legacy"
    return f'<span style="display:inline-block;padding:2px 8px;border-radius:999px;font-size:11px;font-weight:600;background:{bg};color:{color};">{label}</span>'


def _render_principle_section(ctx: dict, entry, principle: dict, color: str):
    """渲染原理解释部分（河流比喻）

    支持两种格式：
    1. 新格式（推荐）：{core_mechanism, key_insights, when_to_use}
    2. 旧格式（兼容）：{title, core_concept, five_dimensions, learning_mechanism, output_meaning}
    """
    # 检测格式类型
    if "five_dimensions" in principle:
        _render_principle_section_legacy(ctx, principle, color)
        return

    # 新格式渲染
    title = principle.get("title", "🌊 策略原理解释")
    core_mechanism = principle.get("core_mechanism", "")
    key_insights = principle.get("key_insights", [])
    when_to_use = principle.get("when_to_use", "")

    # 核心机制部分
    core_html = ""
    if core_mechanism:
        core_html = f'''
        <div style="background:linear-gradient(135deg,{color}22 0%,{color}11 100%);
                    padding:16px;border-radius:10px;margin-bottom:16px;border-left:4px solid {color};">
            <div style="font-size:13px;color:#333;line-height:1.7;">
                {core_mechanism}
            </div>
        </div>
        '''

    # 关键洞察部分
    insights_html = ""
    if key_insights:
        insights_html = '<div style="margin-bottom:16px;"><div style="font-weight:600;color:#333;font-size:13px;margin-bottom:10px;">💡 关键洞察</div><div style="display:flex;flex-direction:column;gap:8px;">'
        for insight in key_insights:
            insights_html += f'''
            <div style="background:#f8f9fa;padding:10px 12px;border-radius:8px;font-size:12px;color:#555;line-height:1.6;
                        border-left:3px solid {color};">
                {insight}
            </div>
            '''
        insights_html += '</div></div>'

    # 使用时机部分
    when_html = ""
    if when_to_use:
        when_html = f'''
        <div style="background:#fffbe6;padding:12px 16px;border-radius:10px;font-size:12px;color:#665500;
                    border-left:4px solid #f59e0b;margin-top:16px;">
            <div style="font-weight:600;margin-bottom:6px;">🎯 使用时机</div>
            <div style="line-height:1.6;">{when_to_use}</div>
        </div>
        '''

    ctx["put_html"](f"""
    <div style="background:#fff;border-radius:12px;box-shadow:0 2px 12px rgba(0,0,0,0.08);
                overflow:hidden;border:1px solid #eee;margin-bottom:15px;">
        <div style="background:linear-gradient(135deg,{color} 0%,{color}cc 100%);
                    padding:15px 20px;color:white;">
            <div style="display:flex;align-items:center;gap:12px;">
                <div style="font-size:24px;">🌊</div>
                <div>
                    <div style="font-size:16px;font-weight:600;">{title}</div>
                    <div style="font-size:11px;opacity:0.9;margin-top:3px;">策略原理解释 · 河流比喻</div>
                </div>
            </div>
        </div>
        <div style="padding:20px;">
            {core_html}
            {insights_html}
            {when_html}
        </div>
    </div>
    """)


def _render_principle_section_legacy(ctx: dict, principle: dict, color: str):
    """渲染旧格式的原理解释（兼容）"""
    title = principle.get("title", "策略原理解释")
    core_concept = principle.get("core_concept", "")
    five_dimensions = principle.get("five_dimensions", {})
    learning_mechanism = principle.get("learning_mechanism", "")
    output_meaning = principle.get("output_meaning", "")

    dimensions_html = ""
    dim_icons = {
        "向": "🌊",
        "速": "⚡",
        "弹": "💥",
        "深": "📏",
        "波": "🌀"
    }

    for dim_key, dim_data in five_dimensions.items():
        first_char = dim_key.split("_")[0] if "_" in dim_key else dim_key[0]
        icon = dim_icons.get(first_char, "📌")

        dimensions_html += f"""
        <div style="background:#f8f9fa;padding:15px;border-radius:8px;margin-bottom:12px;
                    border-left:3px solid {color};">
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;">
                <span style="font-size:18px;">{icon}</span>
                <span style="font-weight:600;color:#333;font-size:14px;">{dim_key}</span>
            </div>
            <div style="margin-bottom:8px;">
                <span style="color:#666;font-size:12px;">📖 {dim_data.get('description', '')}</span>
            </div>
            <div style="margin-bottom:8px;">
                <span style="color:#666;font-size:12px;">⚙️ {dim_data.get('implementation', '')}</span>
            </div>
            <div style="margin-bottom:8px;">
                <div style="color:#888;font-size:11px;margin-bottom:4px;">📊 指标:</div>
                <div style="background:#fff;padding:8px;border-radius:4px;font-family:monospace;
                            font-size:11px;color:#555;">
                    {'<br>'.join(dim_data.get('metrics', []))}
                </div>
            </div>
            <div>
                <span style="color:#666;font-size:12px;">💭 {dim_data.get('interpretation', '')}</span>
            </div>
        </div>
        """

    extra_html = ""
    if learning_mechanism or output_meaning:
        extra_html = f"""
        <div style="margin-top:15px;display:grid;grid-template-columns:1fr 1fr;gap:15px;">
            {'<div style="background:#e3f2fd;padding:12px;border-radius:8px;font-size:12px;color:#333;">'
             '<strong>🧠 学习机制:</strong><br>' + learning_mechanism + '</div>' if learning_mechanism else ''}
            {'<div style="background:#e8f5e9;padding:12px;border-radius:8px;font-size:12px;color:#333;">'
             '<strong>📤 输出含义:</strong><br>' + output_meaning + '</div>' if output_meaning else ''}
        </div>
        """

    ctx["put_html"](f"""
    <div style="background:#fff;border-radius:12px;box-shadow:0 2px 12px rgba(0,0,0,0.08);
                overflow:hidden;border:1px solid #eee;margin-bottom:15px;">
        <div style="background:linear-gradient(135deg,{color} 0%,{color}dd 100%);
                    padding:15px 20px;color:white;">
            <div style="display:flex;align-items:center;gap:12px;">
                <div style="font-size:24px;">🌊</div>
                <div>
                    <div style="font-size:16px;font-weight:600;">{title}</div>
                    <div style="font-size:12px;opacity:0.9;margin-top:3px;">{core_concept}</div>
                </div>
            </div>
        </div>
        <div style="padding:20px;">
            {dimensions_html}
            {extra_html}
        </div>
    </div>
    """)


def _render_strategy_diagram_section(ctx: dict, entry):
    """渲染策略详解图表部分"""
    diagram_info = getattr(entry._metadata, "diagram_info", {}) or {}

    if not diagram_info:
        diagram_info = _get_fallback_diagram_info(entry)

    if not diagram_info:
        return

    ctx["put_html"](render_detail_section("📊 策略详解"))

    icon = diagram_info.get("icon", "📊")
    color = diagram_info.get("color", "#667eea")
    description = diagram_info.get("description", "")
    formula = diagram_info.get("formula", "")
    logic = diagram_info.get("logic", [])
    output = diagram_info.get("output", "")
    principle = diagram_info.get("principle", {})

    # 生成流程步骤 HTML
    logic_html = "".join([
        f'<div style="padding:4px 0;color:#555;font-size:12px;display:flex;align-items:center;gap:6px;">'
        f'<span style="background:{color};color:white;width:18px;height:18px;border-radius:50%;'
        f'display:flex;align-items:center;justify-content:center;font-size:10px;">{i+1}</span>{step}</div>'
        for i, step in enumerate(logic)
    ])

    # 渲染原有的策略详解
    ctx["put_html"](f"""
    <div style="background:#fff;border-radius:12px;box-shadow:0 2px 12px rgba(0,0,0,0.08);
                overflow:hidden;border:1px solid #eee;margin-bottom:15px;">
        <div style="background:linear-gradient(135deg,{color} 0%,{color}dd 100%);
                    padding:15px 20px;color:white;">
            <div style="display:flex;align-items:center;gap:12px;">
                <div style="font-size:28px;">{icon}</div>
                <div>
                    <div style="font-size:16px;font-weight:600;">{entry.name}</div>
                    <div style="font-size:12px;opacity:0.9;margin-top:3px;">{description}</div>
                </div>
            </div>
        </div>
        <div style="padding:20px;">
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;">
                <div>
                    <div style="font-weight:600;color:#333;margin-bottom:10px;display:flex;align-items:center;gap:6px;">
                        <span style="background:{color};color:white;padding:2px 8px;border-radius:4px;font-size:11px;">公式</span>
                        计算逻辑
                    </div>
                    <div style="background:#f8f9fa;padding:12px;border-radius:8px;
                                font-family:monospace;font-size:12px;color:#555;border-left:3px solid {color};">
                        {formula}
                    </div>
                </div>
                <div>
                    <div style="font-weight:600;color:#333;margin-bottom:10px;display:flex;align-items:center;gap:6px;">
                        <span style="background:{color};color:white;padding:2px 8px;border-radius:4px;font-size:11px;">步骤</span>
                        处理流程
                    </div>
                    <div style="background:#f8f9fa;padding:12px;border-radius:8px;">
                        {logic_html}
                    </div>
                </div>
            </div>
            <div style="margin-top:15px;padding:12px;
                        background:linear-gradient(135deg,{color}11 0%,{color}22 100%);
                        border-radius:8px;border:1px dashed {color}44;">
                <div style="display:flex;align-items:center;gap:6px;color:#333;font-size:13px;">
                    <span style="font-size:16px;">📤</span>
                    <strong>输出：</strong>
                    <span style="color:#666;">{output}</span>
                </div>
            </div>
        </div>
    </div>
    """)

    # 渲染河流比喻（如果有）
    river_metaphor = diagram_info.get("river_metaphor", {})
    if river_metaphor:
        _render_river_metaphor_section(ctx, river_metaphor, color)

    # 渲染记忆结构（如果有）
    memory_structure = diagram_info.get("memory_structure", {})
    if memory_structure:
        _render_memory_structure_section(ctx, memory_structure, color)

    # 渲染信号类型（如果有）
    signal_types = diagram_info.get("signal_types", [])
    if signal_types:
        _render_signal_types_section(ctx, signal_types, color)

    # 渲染原理解释（如果有）
    if principle:
        _render_principle_section(ctx, entry, principle, color)



def _render_river_metaphor_section(ctx: dict, river_metaphor: dict, color: str):
    """渲染河流比喻部分"""
    title = river_metaphor.get("title", "�� 河流比喻")
    description = river_metaphor.get("description", "")
    elements = river_metaphor.get("elements", {})
    process = river_metaphor.get("process", [])
    
    # 生成元素 HTML
    elements_html = ""
    for key, value in elements.items():
        elements_html += f'''<div style="padding:8px 12px;background:#f8f9fa;border-radius:6px;margin-bottom:6px;"><span style="font-weight:600;color:{color};">{key}</span><span style="color:#666;margin-left:8px;">{value}</span></div>'''
    
    # 生成流程 HTML
    process_html = ""
    for step in process:
        process_html += f'''<div style="padding:6px 0;color:#555;font-size:13px;border-left:2px solid {color};padding-left:12px;margin-bottom:4px;">{step}</div>'''
    
    ctx["put_html"](f'''<div style="background:#fff;border-radius:12px;box-shadow:0 2px 12px rgba(0,0,0,0.08);overflow:hidden;border:1px solid #eee;margin-bottom:15px;"><div style="background:linear-gradient(135deg,{color} 0%,{color}dd 100%);padding:12px 20px;color:white;"><div style="font-size:16px;font-weight:600;">{title}</div><div style="font-size:12px;opacity:0.9;margin-top:4px;">{description}</div></div><div style="padding:20px;"><div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;"><div><div style="font-weight:600;color:#333;margin-bottom:10px;">🏞️ 河流元素</div><div style="background:#f8f9fa;padding:12px;border-radius:8px;">{elements_html}</div></div><div><div style="font-weight:600;color:#333;margin-bottom:10px;">🔄 处理流程</div><div style="background:#f8f9fa;padding:12px;border-radius:8px;">{process_html}</div></div></div></div></div>''')


def _get_llm_adjustments(entry, limit: int = 10):
    """获取与该策略相关的 LLM 调节历史"""
    try:
        from deva import NB
        db = NB("naja_llm_decisions")
        items = []
        for _, value in list(db.items()):
            if not isinstance(value, dict):
                continue
            actions = value.get("actions", []) or []
            matched_actions = []
            for action in actions:
                if not isinstance(action, dict):
                    continue
                target = str(action.get("strategy", "") or "")
                if target == entry.id or target == entry.name:
                    matched_actions.append(action)
            if matched_actions:
                items.append((value, matched_actions))

        items.sort(key=lambda x: float(x[0].get("timestamp", 0) or 0), reverse=True)
        rows = []
        for value, acts in items[:limit]:
            ts = format_timestamp(float(value.get("timestamp", 0) or 0))
            summary = value.get("summary", "") or "-"
            reason = value.get("reason", "") or "-"
            act_texts = []
            for a in acts:
                act_texts.append(f"{a.get('action', '')}({a.get('strategy', '')})")
            rows.append([ts, summary, "; ".join(act_texts), reason])
        return rows
    except Exception:
        return []


def _render_memory_structure_section(ctx: dict, memory_structure: dict, color: str):
    """渲染记忆结构部分"""
    # 生成记忆层级 HTML
    levels_html = ""
    level_colors = ["#e3f2fd", "#fff3e0", "#f3e5f5", "#e8f5e9"]
    for i, (key, value) in enumerate(memory_structure.items()):
        bg_color = level_colors[i % len(level_colors)]
        levels_html += f'''<div style="padding:10px 12px;background:{bg_color};border-radius:6px;margin-bottom:8px;border-left:3px solid {color};"><div style="font-weight:600;color:#333;">{key}</div><div style="color:#666;font-size:12px;margin-top:2px;">{value}</div></div>'''
    
    ctx["put_html"](f'''<div style="background:#fff;border-radius:12px;box-shadow:0 2px 12px rgba(0,0,0,0.08);overflow:hidden;border:1px solid #eee;margin-bottom:15px;"><div style="background:linear-gradient(135deg,{color} 0%,{color}dd 100%);padding:12px 20px;color:white;"><div style="font-size:16px;font-weight:600;">🧠 记忆结构</div><div style="font-size:12px;opacity:0.9;margin-top:4px;">分层记忆存储系统</div></div><div style="padding:20px;">{levels_html}</div></div>''')


def _render_signal_types_section(ctx: dict, signal_types: list, color: str):
    """渲染信号类型部分"""
    # 生成信号类型 HTML
    signals_html = ""
    signal_colors = ["#e8f5e9", "#fff3e0", "#ffebee", "#e3f2fd", "#f3e5f5", "#e0f2f1"]
    for i, signal in enumerate(signal_types):
        bg_color = signal_colors[i % len(signal_colors)]
        signals_html += f'''<div style="padding:8px 12px;background:{bg_color};border-radius:6px;margin-bottom:6px;font-size:13px;color:#333;">{signal}</div>'''
    
    ctx["put_html"](f'''<div style="background:#fff;border-radius:12px;box-shadow:0 2px 12px rgba(0,0,0,0.08);overflow:hidden;border:1px solid #eee;margin-bottom:15px;"><div style="background:linear-gradient(135deg,{color} 0%,{color}dd 100%);padding:12px 20px;color:white;"><div style="font-size:16px;font-weight:600;">📡 信号类型</div><div style="font-size:12px;opacity:0.9;margin-top:4px;">策略可能输出的信号</div></div><div style="padding:20px;">{signals_html}</div></div>''')
