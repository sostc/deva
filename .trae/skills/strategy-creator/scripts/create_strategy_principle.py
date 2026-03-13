# 新的 principle 结构生成函数
# 用于替换旧的 river_metaphor 函数

def generate_fisherman_principle(user_logic: str, has_dictionary: bool) -> dict:
    """渔夫钓鱼比喻 - 用于价格/行情类策略（principle 结构）"""
    return {
        "title": "🌊 河流比喻：渔夫在行情河流中钓鱼",
        "core_concept": "像渔夫在河边观察水流，用鱼竿感知鱼群（价格）的动向。实时监控价格变化，识别突破机会。",
        "five_dimensions": {
            "向_价格趋势": {
                "description": "价格变动的方向和趋势",
                "implementation": "通过价格序列计算趋势",
                "metrics": ["price_direction - 价格方向", "trend_strength - 趋势强度"],
                "interpretation": "向上趋势 = 水流向前，可能上涨；向下趋势 = 水流后退，可能下跌"
            },
            "速_价格变化速度": {
                "description": "价格变化的节奏和速度",
                "implementation": "通过价格变化率计算",
                "metrics": ["price_velocity - 价格速度", "change_frequency - 变化频率"],
                "interpretation": "快速变化 = 急流，可能突破；缓慢变化 = 缓流，可能盘整"
            },
            "弹_价格突破": {
                "description": "价格突破阈值的冲击力",
                "implementation": "通过阈值检测",
                "metrics": ["breakout_strength - 突破强度", "threshold_distance - 阈值距离"],
                "interpretation": "突破阈值 = 漩涡，触发信号；未突破 = 平缓水流，继续观察"
            },
            "深_价格记忆": {
                "description": "历史价格数据的深度",
                "implementation": "通过历史数据存储",
                "metrics": ["history_depth - 历史深度", "support_resistance - 支撑阻力位"],
                "interpretation": "深层历史 = 河床石头，形成支撑阻力；浅层历史 = 水面波纹，短期波动"
            },
            "波_价格波动模式": {
                "description": "价格波动的周期性模式",
                "implementation": "通过波动率分析",
                "metrics": ["volatility - 波动率", "wave_pattern - 波纹模式"],
                "interpretation": "高波动 = 波涛汹涌，机会多；低波动 = 平静湖面，机会少"
            }
        },
        "learning_mechanism": "实时监控价格数据，通过阈值检测识别突破机会，halflife=0.5 平衡响应速度和稳定性",
        "output_meaning": "信号表示价格突破事件：PRICE_BREAKOUT（价格突破）/ PRICE_ALERT（价格警报）"
    }


def generate_otter_principle(user_logic: str, has_dictionary: bool) -> dict:
    """水獭收集比喻 - 用于新闻/文本类策略（principle 结构）"""
    return {
        "title": "🌊 河流比喻：水獭在信息河流中收集新闻",
        "core_concept": "像水獭在河面收集漂浮的树叶（新闻），筛选有价值的信息。实时分析新闻流，识别热点事件。",
        "five_dimensions": {
            "向_新闻流向": {
                "description": "新闻主题的演变方向",
                "implementation": "通过主题追踪",
                "metrics": ["topic_direction - 主题方向", "sentiment_trend - 情感趋势"],
                "interpretation": "正面情感 = 顺流，利好；负面情感 = 逆流，利空"
            },
            "速_新闻流速": {
                "description": "新闻发布的频率和密度",
                "implementation": "通过新闻频率计算",
                "metrics": ["news_frequency - 新闻频率", "burst_rate - 爆发率"],
                "interpretation": "高频新闻 = 急流，热点事件；低频新闻 = 缓流，平静期"
            },
            "弹_热点冲击": {
                "description": "热点新闻的冲击力",
                "implementation": "通过关键词匹配和情感分析",
                "metrics": ["keyword_match - 关键词匹配度", "sentiment_spike - 情感峰值"],
                "interpretation": "高匹配度 = 漩涡，重要新闻；低匹配度 = 普通水流，一般新闻"
            },
            "深_新闻记忆": {
                "description": "历史新闻数据的深度",
                "implementation": "通过新闻存储和索引",
                "metrics": ["news_history - 新闻历史", "topic_persistence - 主题持久度"],
                "interpretation": "持久主题 = 河床石头，长期关注；短暂主题 = 水面落叶，短期热点"
            },
            "波_新闻传播": {
                "description": "新闻传播的模式和范围",
                "implementation": "通过传播分析",
                "metrics": ["spread_range - 传播范围", "influence_score - 影响力分数"],
                "interpretation": "广泛传播 = 大波浪，重要事件；有限传播 = 小波纹，局部事件"
            }
        },
        "learning_mechanism": "实时接收新闻数据，通过关键词匹配和情感分析识别热点，halflife=0.3 快速响应新闻变化",
        "output_meaning": "信号表示新闻热点事件：NEWS_HOT（热点新闻）/ SENTIMENT_ALERT（情感警报）"
    }


def generate_heron_principle(user_logic: str, has_dictionary: bool) -> dict:
    """苍鹭观察比喻 - 用于日志/监控类策略（principle 结构）"""
    return {
        "title": "🌊 河流比喻：苍鹭在日志河流中静静观察",
        "core_concept": "像苍鹭静静站在河边，敏锐地观察水面（日志）的异常波动。实时监控日志流，识别异常事件。",
        "five_dimensions": {
            "向_日志流向": {
                "description": "日志事件的演变方向",
                "implementation": "通过日志模式分析",
                "metrics": ["log_pattern - 日志模式", "error_trend - 错误趋势"],
                "interpretation": "错误增加 = 逆流，问题恶化；错误减少 = 顺流，问题缓解"
            },
            "速_日志流速": {
                "description": "日志产生的频率和密度",
                "implementation": "通过日志频率计算",
                "metrics": ["log_frequency - 日志频率", "burst_rate - 爆发率"],
                "interpretation": "高频日志 = 急流，系统繁忙；低频日志 = 缓流，系统平静"
            },
            "弹_异常冲击": {
                "description": "异常事件的冲击力",
                "implementation": "通过异常检测算法",
                "metrics": ["anomaly_score - 异常分数", "error_severity - 错误严重程度"],
                "interpretation": "高异常分数 = 漩涡，严重错误；低异常分数 = 普通水流，正常日志"
            },
            "深_日志记忆": {
                "description": "历史日志数据的深度",
                "implementation": "通过日志存储和归档",
                "metrics": ["log_history - 日志历史", "pattern_memory - 模式记忆"],
                "interpretation": "深层历史 = 河床石头，长期模式；浅层历史 = 水面波纹，短期现象"
            },
            "波_日志波动": {
                "description": "日志产生的波动模式",
                "implementation": "通过时间序列分析",
                "metrics": ["log_volatility - 日志波动率", "pattern_cycle - 模式周期"],
                "interpretation": "高波动 = 波涛汹涌，系统不稳定；低波动 = 平静湖面，系统稳定"
            }
        },
        "learning_mechanism": "实时监控日志数据，通过异常检测识别问题，halflife=0.2 快速响应异常",
        "output_meaning": "信号表示日志异常事件：ERROR_ALERT（错误警报）/ ANOMALY_DETECTED（异常检测）"
    }


def generate_beaver_principle(user_logic: str, has_dictionary: bool) -> dict:
    """海狸筑坝比喻 - 用于文件/目录类策略（principle 结构）"""
    return {
        "title": "🌊 河流比喻：海狸在文件河流中筑坝监控",
        "core_concept": "像海狸在河边筑坝，监控河流（文件）的变化并建造结构。实时跟踪文件变更，维护文件索引。",
        "five_dimensions": {
            "向_文件流向": {
                "description": "文件变更的方向和趋势",
                "implementation": "通过文件事件分析",
                "metrics": ["change_direction - 变更方向", "file_trend - 文件趋势"],
                "interpretation": "创建增加 = 顺流，文件增长；删除增加 = 逆流，文件减少"
            },
            "速_文件流速": {
                "description": "文件变更的频率和密度",
                "implementation": "通过变更频率计算",
                "metrics": ["change_frequency - 变更频率", "event_rate - 事件率"],
                "interpretation": "高频变更 = 急流，活跃目录；低频变更 = 缓流，静态目录"
            },
            "弹_变更冲击": {
                "description": "重大变更的冲击力",
                "implementation": "通过变更大小和类型判断",
                "metrics": ["change_impact - 变更影响", "file_size_delta - 文件大小变化"],
                "interpretation": "大文件变更 = 漩涡，重大更新；小文件变更 = 普通水流，轻微修改"
            },
            "深_文件记忆": {
                "description": "文件历史记录的深度",
                "implementation": "通过文件版本控制",
                "metrics": ["version_history - 版本历史", "change_log - 变更日志"],
                "interpretation": "深层历史 = 河床石头，完整记录；浅层历史 = 水面波纹，近期变更"
            },
            "波_变更波动": {
                "description": "文件变更的波动模式",
                "implementation": "通过变更时间分析",
                "metrics": ["change_pattern - 变更模式", "activity_cycle - 活动周期"],
                "interpretation": "规律变更 = 周期性波浪，定时任务；随机变更 = 不规则波纹，用户操作"
            }
        },
        "learning_mechanism": "实时监控文件系统，通过事件监听跟踪变更，halflife=0.3 快速响应文件变化",
        "output_meaning": "信号表示文件变更事件：FILE_CREATED（文件创建）/ FILE_MODIFIED（文件修改）/ FILE_DELETED（文件删除）"
    }


def generate_duck_principle(user_logic: str, has_dictionary: bool) -> dict:
    """鸭子巡游比喻 - 用于板块/行业类策略（principle 结构）"""
    return {
        "title": "🌊 河流比喻：鸭子在板块河流中巡游觅食",
        "core_concept": "像鸭子在水中巡游，寻找食物（优质股票）并观察鸭群（板块）动向。实时扫描板块，筛选优质标的。",
        "five_dimensions": {
            "向_板块流向": {
                "description": "板块轮动的方向和趋势",
                "implementation": "通过板块指数分析",
                "metrics": ["sector_rotation - 板块轮动", "trend_direction - 趋势方向"],
                "interpretation": "板块上涨 = 顺流，资金流入；板块下跌 = 逆流，资金流出"
            },
            "速_板块流速": {
                "description": "板块变化的节奏和速度",
                "implementation": "通过板块动量计算",
                "metrics": ["sector_momentum - 板块动量", "rotation_speed - 轮动速度"],
                "interpretation": "快速轮动 = 急流，热点切换快；慢速轮动 = 缓流，热点持续"
            },
            "弹_板块冲击": {
                "description": "板块异动的冲击力",
                "implementation": "通过涨跌幅和成交量判断",
                "metrics": ["price_change - 涨跌幅", "volume_spike - 成交量峰值"],
                "interpretation": "大涨放量 = 漩涡，板块启动；小涨缩量 = 普通水流，正常波动"
            },
            "深_板块记忆": {
                "description": "板块历史表现的深度",
                "implementation": "通过历史数据回测",
                "metrics": ["historical_performance - 历史表现", "seasonal_pattern - 季节性模式"],
                "interpretation": "深层历史 = 河床石头，长期规律；浅层历史 = 水面波纹，短期现象"
            },
            "波_板块波动": {
                "description": "板块内个股的波动模式",
                "implementation": "通过成分股分析",
                "metrics": ["constituent_volatility - 成分股波动率", "correlation_pattern - 相关性模式"],
                "interpretation": "高相关性 = 大波浪，板块共振；低相关性 = 小波纹，个股独立"
            }
        },
        "learning_mechanism": "实时扫描板块数据，通过动量分析识别热点，halflife=0.4 平衡响应速度和持续性",
        "output_meaning": "信号表示板块轮动事件：SECTOR_LEAD（板块领涨）/ SECTOR_LAG（板块领跌）/ ROTATION_SIGNAL（轮动信号）"
    }


def generate_lobster_principle(user_logic: str, has_dictionary: bool) -> dict:
    """龙虾感知比喻 - 通用/流式学习类策略（principle 结构）"""
    return {
        "title": "🌊 河流比喻：龙虾在信息河流中感知水流",
        "core_concept": "想象一条信息河流，龙虾在河底用触角感知水流的变化。实时分析数据流，动态生成主题信号和注意力信号，就像龙虾感知河流中的水流变化、漩涡和暗流。",
        "five_dimensions": {
            "向_水流方向": {
                "description": "数据流的方向和趋势",
                "implementation": "通过主题分析判断",
                "metrics": ["topic_direction - 主题演变方向", "topic_velocity - 主题变化速度"],
                "interpretation": "稳定方向 = 成熟主题，像稳定河流；快速变化 = 新兴主题，像湍急水流"
            },
            "速_水流速度": {
                "description": "数据流的节奏和速度",
                "implementation": "通过数据频率和密度判断",
                "metrics": ["data_frequency - 数据频率", "topic_growth_rate - 主题增长率"],
                "interpretation": "高频率 + 稳定增长 = 热门主题，像急流；低频率 = 冷门主题，像缓流"
            },
            "弹_水流冲击": {
                "description": "高注意力事件的冲击力",
                "implementation": "通过 attention_level 衡量",
                "metrics": ["attention_level - 注意力等级", "attention_spike - 注意力峰值"],
                "interpretation": "高 attention_level = 热点事件，像漩涡；低 attention_level = 普通事件，像平缓水流"
            },
            "深_河床结构": {
                "description": "分层记忆结构的深度",
                "implementation": "通过记忆层级判断",
                "metrics": ["memory_depth - 记忆深度", "topic_persistence - 主题持久度"],
                "interpretation": "深层记忆 = 持久主题，像河床石头；浅层记忆 = 临时主题，像水面落叶"
            },
            "波_水流波纹": {
                "description": "数据流产生的波纹模式",
                "implementation": "通过信号类型和频率判断",
                "metrics": ["signal_frequency - 信号频率", "topic_diversity - 主题多样性"],
                "interpretation": "频繁信号 + 多样主题 = 活跃市场，像波涛汹涌；稀少信号 = 平静市场，像平静湖面"
            }
        },
        "learning_mechanism": "流式学习实时更新分层记忆，halflife=0.5 平衡响应速度和稳定性，周期性自我反思优化记忆结构，通过主题演变和注意力检测生成信号",
        "output_meaning": "信号表示识别出的水流变化：TOPIC_EMERGE（新水流分支）/ TOPIC_GROW（水流增强）/ HIGH_ATTENTION（漩涡热点）/ TREND_SHIFT（水流改向）"
    }
