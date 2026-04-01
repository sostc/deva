"""
行业供应链配置模板

为每个行业提供完整的上中下游供应链结构
"""

SUPPLY_CHAIN_TEMPLATES = {
    "AI": {
        "name": "人工智能",
        "upstream": {
            "name": "芯片/算力",
            "description": "AI计算的基础设施",
            "nodes": [
                {
                    "name": "GPU",
                    "key_companies": ["英伟达", "AMD", "英特尔", "昇腾", "昆仑"],
                    "signal": "算力告急",
                    "tiandao_keywords": ["GPU缺货", "算力告急", "英伟达产能", "H100", "H200", "A100"]
                },
                {
                    "name": "HBM内存",
                    "key_companies": ["SK海力士", "三星", "美光"],
                    "signal": "HBM缺货",
                    "tiandao_keywords": ["HBM缺货", "HBM产能", "内存短缺", "HBM3", "HBM3E"]
                },
                {
                    "name": "光刻机",
                    "key_companies": ["ASML", "佳能", "尼康"],
                    "signal": "产能受限",
                    "tiandao_keywords": ["光刻机交付", "EUV产能", "先进封装产能", "CoWoS满载"]
                },
                {
                    "name": "先进封装",
                    "key_companies": ["台积电", "日月光", "通富微电", "长电科技"],
                    "signal": "封装排队",
                    "tiandao_keywords": ["先进封装", "CoWoS", "SoIC", "封装产能", "封装排队"]
                }
            ],
            "tiandao_keywords": [
                "限流", "算力告急", "GPU排队", "算力不足", "HBM缺货",
                "产能不足", "良品率", "卡脖子", "API限流", "服务器过载"
            ]
        },
        "midstream": {
            "name": "模型/算法",
            "description": "大模型训练和推理",
            "nodes": [
                {
                    "name": "大模型训练",
                    "key_companies": ["OpenAI", "Anthropic", "Google", "Meta", "百度", "阿里", "字节"],
                    "signal": "技术突破",
                    "tiandao_keywords": ["GPT-5", "Claude4", "Gemini2", "大模型突破", "训练成本"]
                },
                {
                    "name": "推理服务",
                    "key_companies": ["Azure", "AWS", "Google Cloud", "阿里云", "腾讯云", "百度云"],
                    "signal": "token消耗",
                    "tiandao_keywords": ["token消耗", "API调用量", "推理成本", "ChatGPT限流", "Claude限流"]
                },
                {
                    "name": "AI Infra",
                    "key_companies": ["CoreWeave", "Lambda Labs", "AutoDL", "矿潮消退"],
                    "signal": "算力租赁",
                    "tiandao_keywords": ["算力租赁", "GPU服务器", "云计算需求", "AI算力"]
                }
            ],
            "tiandao_keywords": [
                "性能提升", "成本下降", "效率提升", "推理加速", "训练成本下降",
                "新一代", "突破", "新架构", "技术创新", "技术路线突破"
            ]
        },
        "downstream": {
            "name": "应用/服务",
            "description": "AI技术的落地和应用",
            "nodes": [
                {
                    "name": "AI应用",
                    "key_companies": ["各类AI应用公司"],
                    "signal": "商业化落地",
                    "tiandao_keywords": ["AI应用", "Agent", "AIGC", "Copilot", "落地"]
                },
                {
                    "name": "行业AI化",
                    "key_companies": ["各行业龙头"],
                    "signal": "渗透率提升",
                    "tiandao_keywords": ["AI改造", "降本增效", "行业AI化", "渗透率", "商业化"]
                },
                {
                    "name": "用户增长",
                    "key_companies": ["OpenAI", "Anthropic", "百度", "阿里"],
                    "signal": "用户爆发",
                    "tiandao_keywords": ["付费转化", "用户增长", "API调用量增长", "收入增长"]
                }
            ],
            "tiandao_keywords": [
                "渗透率", "落地", "商业化", "盈利", "用户增长",
                "付费转化", "API调用量增长", "降本增效", "行业AI化"
            ]
        }
    },

    "芯片": {
        "name": "半导体/芯片",
        "upstream": {
            "name": "材料/设备",
            "description": "芯片制造的上游材料和设备",
            "nodes": [
                {
                    "name": "硅片",
                    "key_companies": ["信越化学", "SUMCO", "沪硅产业", "立昂微"],
                    "signal": "硅片涨价",
                    "tiandao_keywords": ["硅片产能", "硅片价格", "晶圆材料"]
                },
                {
                    "name": "光刻胶",
                    "key_companies": ["JSR", "东京应化", "晶瑞电材", "华懋科技"],
                    "signal": "材料短缺",
                    "tiandao_keywords": ["光刻胶", "光刻材料", "电子化学品"]
                },
                {
                    "name": "特气",
                    "key_companies": ["空气化工", "林德", "杭氧股份", "华特气体"],
                    "signal": "特气供应",
                    "tiandao_keywords": ["电子特气", "高纯气体", "半导体材料"]
                }
            ],
            "tiandao_keywords": [
                "晶圆厂产能满", "产能告急", "设备交付延迟", "材料短缺",
                "硅片产能", "光刻胶", "电子特气", "关键材料"
            ]
        },
        "midstream": {
            "name": "制造/封测",
            "description": "芯片制造和封装测试",
            "nodes": [
                {
                    "name": "晶圆制造",
                    "key_companies": ["台积电", "三星", "英特尔", "中芯国际", "华虹半导体"],
                    "signal": "制程突破",
                    "tiandao_keywords": ["制程突破", "良率提升", "3nm", "5nm", "7nm", "成熟制程", "先进制程"]
                },
                {
                    "name": "封装测试",
                    "key_companies": ["日月光", "通富微电", "长电科技", "华天科技"],
                    "signal": "封装产能",
                    "tiandao_keywords": ["封装产能", "先进封装", "CoWoS", "HBM封装", "封装技术突破"]
                },
                {
                    "name": "成熟制程",
                    "key_companies": ["联电", "格罗方德", "中芯国际", "华虹半导体"],
                    "signal": "成熟制程需求",
                    "tiandao_keywords": ["成熟制程", "28nm", "55nm", "车规芯片", "功率半导体"]
                }
            ],
            "tiandao_keywords": [
                "晶圆厂产能满", "制程突破", "良率提升", "封装排队",
                "产能不足", "成熟制程", "先进封装", "国产替代"
            ]
        },
        "downstream": {
            "name": "设计/应用",
            "description": "芯片设计和产品应用",
            "nodes": [
                {
                    "name": "IC设计",
                    "key_companies": ["英伟达", "高通", "AMD", "联发科", "华为海思", "寒武纪"],
                    "signal": "芯片需求",
                    "tiandao_keywords": ["芯片需求", "AI芯片", "手机芯片", "汽车芯片", "国产替代"]
                },
                {
                    "name": "存储芯片",
                    "key_companies": ["三星", "SK海力士", "美光", "长江存储", "长鑫存储"],
                    "signal": "存储周期",
                    "tiandao_keywords": ["存储芯片", "NAND", "DRAM", "HBM", "长江存储", "存储周期"]
                },
                {
                    "name": "功率半导体",
                    "key_companies": ["英飞凌", "安森美", "士兰微", "斯达半导", "比亚迪半导体"],
                    "signal": "功率需求",
                    "tiandao_keywords": ["功率半导体", "碳化硅", "IGBT", "MOSFET", "新能源车"]
                }
            ],
            "tiandao_keywords": [
                "芯片需求爆发", "国产替代", "汽车芯片", "AI芯片",
                "需求增长", "渗透率提升", "行业复苏"
            ]
        }
    },

    "新能源": {
        "name": "新能源",
        "upstream": {
            "name": "矿产资源",
            "description": "锂电和光伏的上游资源",
            "nodes": [
                {
                    "name": "锂矿",
                    "key_companies": ["雅保", "SQM", "赣锋锂业", "天齐锂业", "永兴材料"],
                    "signal": "锂价波动",
                    "tiandao_keywords": ["锂价", "锂矿", "碳酸锂", "氢氧化锂", "锂资源"]
                },
                {
                    "name": "钴镍",
                    "key_companies": ["洛阳钼业", "华友钴业", "格林美"],
                    "signal": "钴镍价格",
                    "tiandao_keywords": ["钴价", "镍价", "钴资源", "镍资源"]
                },
                {
                    "name": "硅料",
                    "key_companies": ["通威股份", "大全能源", "协鑫科技", "新特能源"],
                    "signal": "硅料价格",
                    "tiandao_keywords": ["硅料", "多晶硅", "硅料价格", "颗粒硅"]
                }
            ],
            "tiandao_keywords": [
                "锂价", "碳酸锂", "锂矿", "硅料价格", "钴镍",
                "资源价格", "上游材料", "成本传导"
            ]
        },
        "midstream": {
            "name": "电池/组件",
            "description": "锂电池和光伏组件制造",
            "nodes": [
                {
                    "name": "锂电池",
                    "key_companies": ["宁德时代", "比亚迪", "亿纬锂能", "中创新航", "国轩高科"],
                    "signal": "电池技术",
                    "tiandao_keywords": ["锂电池", "电池技术", "能量密度", "续航突破", "快充技术"]
                },
                {
                    "name": "光伏组件",
                    "key_companies": ["隆基绿能", "晶科能源", "天合光能", "晶澳科技", "通威股份"],
                    "signal": "组件效率",
                    "tiandao_keywords": ["光伏组件", "转换效率", "TOPCon", "HJT", "BC电池", "组件价格"]
                },
                {
                    "name": "逆变器",
                    "key_companies": ["阳光电源", "华为数字能源", "锦浪科技", "固德威", "德业股份"],
                    "signal": "储能需求",
                    "tiandao_keywords": ["逆变器", "储能", "光伏逆变器", "储能变流器"]
                }
            ],
            "tiandao_keywords": [
                "电池技术突破", "能量密度提升", "成本下降", "转换效率",
                "光伏技术", "TOPCon", "HJT", "储能需求"
            ]
        },
        "downstream": {
            "name": "应用/整车",
            "description": "新能源汽车和储能应用",
            "nodes": [
                {
                    "name": "新能源汽车",
                    "key_companies": ["比亚迪", "特斯拉", "蔚来", "小鹏", "理想", "广汽埃安"],
                    "signal": "销量增长",
                    "tiandao_keywords": ["新能源车销量", "电动车渗透率", "蔚来销量", "小鹏销量", "比亚迪销量"]
                },
                {
                    "name": "储能",
                    "key_companies": ["宁德时代", "比亚迪", "阳光电源", "科陆电子"],
                    "signal": "储能装机",
                    "tiandao_keywords": ["储能装机", "大储", "工商业储能", "户用储能", "储能需求"]
                },
                {
                    "name": "充电桩",
                    "key_companies": ["特锐德", "星星充电", "国家电网"],
                    "signal": "充电桩建设",
                    "tiandao_keywords": ["充电桩", "充电网络", "快充桩", "超充桩"]
                }
            ],
            "tiandao_keywords": [
                "新能源车销量", "电动车渗透率", "储能装机", "充电桩建设",
                "以旧换新", "政策补贴", "市场渗透"
            ]
        }
    },

    "医药": {
        "name": "医药/生物医药",
        "upstream": {
            "name": "原料药/CXO",
            "description": "医药研发和生产服务",
            "nodes": [
                {
                    "name": "原料药",
                    "key_companies": ["新和成", "浙江医药", "亿帆医药", "天宇股份"],
                    "signal": "原料药价格",
                    "tiandao_keywords": ["原料药", "维生素", "原料药价格", "肝素"]
                },
                {
                    "name": "CXO",
                    "key_companies": ["药明康德", "药明生物", "康龙化成", "泰格医药", "凯莱英"],
                    "signal": "订单情况",
                    "tiandao_keywords": ["CXO", "创新药研发", "CRO", "CDMO", "药明康德", "订单"]
                }
            ],
            "tiandao_keywords": [
                "原料药", "CXO", "CRO", "CDMO", "创新药研发",
                "订单", "产能", "药明康德", "泰格医药"
            ]
        },
        "midstream": {
            "name": "创新药",
            "description": "创新药研发",
            "nodes": [
                {
                    "name": "生物药",
                    "key_companies": ["恒瑞医药", "百济神州", "信达生物", "君实生物", "荣昌生物"],
                    "signal": "新药获批",
                    "tiandao_keywords": ["创新药", "生物药", "PD-1", "ADC", "新药获批", "临床进展"]
                },
                {
                    "name": "中药",
                    "key_companies": ["片仔癀", "云南白药", "同仁堂", "以岭药业"],
                    "signal": "中药政策",
                    "tiandao_keywords": ["中药", "中医药", "中药材", "政策支持"]
                }
            ],
            "tiandao_keywords": [
                "创新药", "新药获批", "临床突破", "PD-1", "ADC",
                "生物药", "国产创新药", "me-better"
            ]
        },
        "downstream": {
            "name": "医疗器械/流通",
            "description": "医疗器械和医药流通",
            "nodes": [
                {
                    "name": "医疗器械",
                    "key_companies": ["迈瑞医疗", "联影医疗", "微创医疗", "乐普医疗"],
                    "signal": "设备更新",
                    "tiandao_keywords": ["医疗器械", "医疗设备", "设备更新", "国产替代", "集采"]
                },
                {
                    "name": "医药流通",
                    "key_companies": ["上海医药", "国药股份", "九州通", "华润医药"],
                    "signal": "集采影响",
                    "tiandao_keywords": ["医药流通", "药品集采", "处方药", "院外市场"]
                }
            ],
            "tiandao_keywords": [
                "医疗器械", "医疗设备", "集采", "国产替代",
                "设备更新", "医药流通", "处方药"
            ]
        }
    },

    "华为": {
        "name": "华为产业链",
        "upstream": {
            "name": "芯片/算力",
            "description": "华为芯片和算力基础设施",
            "nodes": [
                {
                    "name": "昇腾芯片",
                    "key_companies": ["华为", "中际旭创", "光迅科技"],
                    "signal": "昇腾产能",
                    "tiandao_keywords": ["昇腾", "昇腾910", "昇腾310", "华为AI芯片", "达芬奇"]
                },
                {
                    "name": "鲲鹏芯片",
                    "key_companies": ["华为", "神州数码", "东软集团"],
                    "signal": "鲲鹏生态",
                    "tiandao_keywords": ["鲲鹏", "鲲鹏920", "华为服务器", "ARM服务器"]
                }
            ],
            "tiandao_keywords": [
                "昇腾", "鲲鹏", "华为芯片", "达芬奇", "昇腾910",
                "算力", "AI芯片", "国产替代"
            ]
        },
        "midstream": {
            "name": "操作系统/软件",
            "description": "华为操作系统和软件生态",
            "nodes": [
                {
                    "name": "鸿蒙系统",
                    "key_companies": ["华为"],
                    "signal": "鸿蒙生态",
                    "tiandao_keywords": ["鸿蒙", "HarmonyOS", "鸿蒙生态", "HarmonyOS NEXT", "原生应用"]
                },
                {
                    "name": "昇思框架",
                    "key_companies": ["华为"],
                    "signal": "AI框架",
                    "tiandao_keywords": ["昇思", "MindSpore", "AI框架", "深度学习框架"]
                }
            ],
            "tiandao_keywords": [
                "鸿蒙", "HarmonyOS", "昇思", "MindSpore",
                "操作系统", "国产软件", "软件生态"
            ]
        },
        "downstream": {
            "name": "产品/应用",
            "description": "华为终端产品和应用",
            "nodes": [
                {
                    "name": "手机",
                    "key_companies": ["华为", "荣耀"],
                    "signal": "手机销量",
                    "tiandao_keywords": ["华为手机", "Mate60", "P70", "麒麟芯片", "5G回归"]
                },
                {
                    "name": "问界/智选",
                    "key_companies": ["赛力斯", "华为", "长安汽车"],
                    "signal": "问界销量",
                    "tiandao_keywords": ["问界", "智界", "华为汽车", "鸿蒙智行", "新能源车"]
                },
                {
                    "name": "华为云",
                    "key_companies": ["华为"],
                    "signal": "云服务",
                    "tiandao_keywords": ["华为云", "云服务", "昇腾云", "盘古大模型"]
                }
            ],
            "tiandao_keywords": [
                "华为手机", "问界", "鸿蒙智行", "华为云",
                "盘古大模型", "Mate60", "麒麟回归", "5G"
            ]
        }
    },

    "全球宏观": {
        "name": "全球宏观",
        "upstream": {
            "name": "央行政策",
            "description": "全球央行货币政策",
            "nodes": [
                {
                    "name": "美联储",
                    "key_companies": ["美联储", "美国财政部"],
                    "signal": "美联储政策",
                    "tiandao_keywords": ["美联储", "加息", "降息", "缩表", "QE", "FOMC"]
                },
                {
                    "name": "欧央行",
                    "key_companies": ["欧洲央行"],
                    "signal": "欧央行政策",
                    "tiandao_keywords": ["欧央行", "欧元区", "加息", "降息"]
                }
            ],
            "tiandao_keywords": [
                "美联储", "加息", "降息", "缩表", "QE", "FOMC",
                "欧央行", "日本央行", "全球央行", "货币政策"
            ]
        },
        "midstream": {
            "name": "经济数据",
            "description": "全球经济数据",
            "nodes": [
                {
                    "name": "美国经济",
                    "key_companies": ["美国政府"],
                    "signal": "经济数据",
                    "tiandao_keywords": ["美国GDP", "非农", "CPI", "PPI", "就业数据", "零售数据"]
                },
                {
                    "name": "中国数据",
                    "key_companies": ["中国政府"],
                    "signal": "中国经济",
                    "tiandao_keywords": ["中国GDP", "社融", "出口", "进口", "PMI", "CPI", "PPI"]
                }
            ],
            "tiandao_keywords": [
                "GDP", "非农", "CPI", "PPI", "PMI", "社融",
                "经济数据", "宏观经济", "全球经济"
            ]
        },
        "downstream": {
            "name": "大类资产",
            "description": "黄金、原油等大类资产",
            "nodes": [
                {
                    "name": "黄金",
                    "key_companies": ["各国央行"],
                    "signal": "黄金走势",
                    "tiandao_keywords": ["黄金", "金价", "COMEX黄金", "伦敦金", "央行购金"]
                },
                {
                    "name": "原油",
                    "key_companies": ["OPEC", "沙特", "俄罗斯"],
                    "signal": "原油价格",
                    "tiandao_keywords": ["原油", "布伦特", "WTI", "OPEC", "原油价格"]
                }
            ],
            "tiandao_keywords": [
                "黄金", "金价", "原油", "油价", "布伦特",
                "WTI", "大宗商品", "避险", "通胀"
            ]
        }
    }
}


def get_supply_chain(domain: str) -> dict:
    """获取指定行业的供应链配置"""
    return SUPPLY_CHAIN_TEMPLATES.get(domain, {})


def get_all_domains() -> list:
    """获取所有已配置的行业"""
    return list(SUPPLY_CHAIN_TEMPLATES.keys())


def expand_supply_chain_keywords(domains: list) -> dict:
    """
    根据选中的行业扩展供应链关键词

    Args:
        domains: 行业列表，如 ["AI", "芯片"]

    Returns:
        包含所有供应链关键词的字典
    """
    result = {
        "tiandao": [],
        "minxin": [],
        "supply_chain": {}
    }

    for domain in domains:
        if domain in SUPPLY_CHAIN_TEMPLATES:
            supply_chain = SUPPLY_CHAIN_TEMPLATES[domain]
            result["supply_chain"][domain] = supply_chain

            for level in ["upstream", "midstream", "downstream"]:
                if level in supply_chain:
                    result["tiandao"].extend(supply_chain[level].get("tiandao_keywords", []))

    result["tiandao"] = list(set(result["tiandao"]))

    return result
