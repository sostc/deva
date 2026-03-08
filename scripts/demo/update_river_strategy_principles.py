#!/usr/bin/env python3
"""Update River strategies with detailed principle explanations based on stream computing analogy.

根据文章的流计算比喻，为每个 river 策略添加详细的原理解释。
核心概念：将 tick 数据看作流计算系统，从五个维度分析：
1. 向（流向）- 数据流的方向，主动买单/卖单流向
2. 速（流速）- 数据流速，TPS/QPS，tick rate
3. 弹（弹性/放大）- 事件对系统的影响，价格冲击
4. 深（深度）- 系统缓冲能力，盘口深度
5. 波（波动）- 系统负载状态，波动率
"""

from __future__ import annotations

from deva.naja.strategy import get_strategy_manager


# 为每个策略定义详细的原理解释
PRINCIPLE_EXPLANATIONS = {
    "river_短期方向概率_top": {
        "principle": {
            "title": "基于流计算的短期方向概率预测",
            "core_concept": "将 tick 数据流视为实时流计算系统，通过在线学习捕捉流向变化与流速放大信号",
            "five_dimensions": {
                "向_流向": {
                    "description": "监控资金流向哪个节点（股票）",
                    "implementation": "通过 imbalance（买卖盘口失衡）和 spread（价差方向）判断流量涌入方向",
                    "metrics": ["imbalance = (bid_size - ask_size) / (bid_size + ask_size)", "spread = (ask - bid) / price"],
                    "interpretation": "imbalance > 0 表示买单流量聚集，类似服务流量暴涨"
                },
                "速_流速": {
                    "description": "监控数据流速变化（TPS/QPS）",
                    "implementation": "通过 vol_ratio（成交量相对 EMA 的倍数）检测流量爆发",
                    "metrics": ["vol_ratio = volume / vol_ema", "vol_ema = 0.95 * prev_vol_ema + 0.05 * current_volume"],
                    "interpretation": "vol_ratio > 2 表示从 100 events/s 跃升至 5000 events/s，有事情发生"
                },
                "弹_放大": {
                    "description": "观测事件对系统的冲击放大程度",
                    "implementation": "通过 ret_1（一期收益率）和 p_change（涨跌幅）衡量价格冲击",
                    "metrics": ["ret_1 = (price - last_price) / last_price", "p_change"],
                    "interpretation": "小幅成交被吸收 vs 大幅成交引发连锁反应"
                },
                "深_深度": {
                    "description": "评估系统缓冲区（流动性缓冲）",
                    "implementation": "通过 bid_size 和 ask_size 评估盘口深度",
                    "metrics": ["bid_size（买盘厚度）", "ask_size（卖盘厚度）"],
                    "interpretation": "队列深则系统稳定，队列浅则轻微波动即剧烈震荡"
                },
                "波_波动": {
                    "description": "监控系统负载稳定性",
                    "implementation": "通过 spread 和 volume 的联合变化识别系统压力",
                    "metrics": ["spread 扩大 + volume 放大 = 系统负载升高"],
                    "interpretation": "平稳 = 正常运行，剧烈波动 = 系统压力大"
                }
            },
            "learning_mechanism": "使用在线逻辑回归（River LogisticRegression）持续学习特征与上涨方向的映射关系，延迟监督机制确保标签准确性",
            "output_meaning": "up_probability 表示在当前流状态下，下一时刻价格上涨的条件概率 P(up|x)"
        }
    },
    "river_量价盘口异常分数_top": {
        "principle": {
            "title": "基于流异常检测的量价突变识别",
            "core_concept": "使用 HalfSpaceTrees 对流数据进行在线异常评分，识别偏离正常模式的 tick",
            "five_dimensions": {
                "向_流向": {
                    "description": "检测流向突变",
                    "implementation": "通过 imbalance_jump（盘口失衡跳变）识别流量方向突然反转",
                    "metrics": ["imbalance_jump = |imbalance - prev_imbalance|"],
                    "interpretation": "流量突然反向，类似服务请求从正向调用变为错误爆发"
                },
                "速_流速": {
                    "description": "检测流速异常",
                    "implementation": "通过 vol_ratio 识别成交量突然放大",
                    "metrics": ["vol_ratio = volume / vol_ema", "vol_ema = 0.92 * prev + 0.08 * current"],
                    "interpretation": "vol_ratio > 3 表示流量异常爆发"
                },
                "弹_放大": {
                    "description": "检测价格冲击放大",
                    "implementation": "通过 abs_ret（绝对收益率）衡量价格跳跃程度",
                    "metrics": ["abs_ret = |(price - prev_price) / prev_price|"],
                    "interpretation": "abs_ret 突然放大表示事件冲击强烈"
                },
                "深_深度": {
                    "description": "检测深度结构突变",
                    "implementation": "通过 spread（价差）和 imbalance（失衡）联合判断流动性缓冲变化",
                    "metrics": ["spread = (ask - bid) / price", "imbalance"],
                    "interpretation": "spread 突然扩大 + imbalance 反转 = 缓冲区变薄"
                },
                "波_波动": {
                    "description": "检测系统负载波动",
                    "implementation": "HalfSpaceTrees 综合所有特征计算异常分数",
                    "metrics": ["anomaly_score = HST.score(x)"],
                    "interpretation": "高分表示系统从平稳进入波动状态"
                }
            },
            "learning_mechanism": "HalfSpaceTrees 通过构建多棵随机分裂树，统计样本在窗口内的深度分布，快速识别异常点",
            "output_meaning": "anomaly_score 表示当前 tick 偏离正常流模式的程度，分数越高越异常"
        }
    },
    "river_tick_市场气候聚类": {
        "principle": {
            "title": "基于流聚类的市场气候识别",
            "core_concept": "使用在线 KMeans 将 tick 流聚类为不同市场气候状态（震荡/趋势/高波动）",
            "five_dimensions": {
                "向_流向": {
                    "description": "识别流向主导类型",
                    "implementation": "通过 imbalance 和 ret 的符号判断流向特征",
                    "metrics": ["ret（收益率符号）", "imbalance（买卖方向）"],
                    "interpretation": "正向 ret + 正向 imbalance = 趋势气候；杂乱 = 震荡气候"
                },
                "速_流速": {
                    "description": "识别流速特征",
                    "implementation": "通过 volume 衡量流量强度",
                    "metrics": ["volume"],
                    "interpretation": "高 volume + 高 |ret| = 高流速趋势气候"
                },
                "弹_放大": {
                    "description": "识别放大效应",
                    "implementation": "通过 abs_ret 和 spread 的联合大小判断",
                    "metrics": ["abs_ret + spread"],
                    "interpretation": "高值表示事件放大效应强 = 高波动气候"
                },
                "深_深度": {
                    "description": "识别深度状态",
                    "implementation": "通过 spread 衡量流动性缓冲厚度",
                    "metrics": ["spread = (ask - bid) / price"],
                    "interpretation": "spread 小 = 缓冲厚 = 震荡气候；spread 大 = 缓冲薄 = 趋势/高波动气候"
                },
                "波_波动": {
                    "description": "识别系统负载状态",
                    "implementation": "通过 trend_strength 综合判断",
                    "metrics": ["trend_strength = abs_ret / (abs_ret + abs_spread)"],
                    "interpretation": "trend_strength 高 = 趋势气候；低 = 震荡气候"
                }
            },
            "learning_mechanism": "在线 KMeans 持续更新聚类中心，halflife=0.4 确保对近期数据更敏感，自动适应市场气候变迁",
            "output_meaning": "dominant_cluster 表示当前市场以哪种气候为主导（0:震荡/1:趋势/2:高波动）"
        }
    },
    "river_订单流失衡先行信号": {
        "principle": {
            "title": "基于订单流不平衡的先行信号检测",
            "core_concept": "从盘口深度与价差变化学习订单流失衡，预测短期价格方向",
            "five_dimensions": {
                "向_流向": {
                    "description": "直接监控订单流方向",
                    "implementation": "通过 OFI（Order Flow Imbalance）量化订单流净方向",
                    "metrics": ["ofi = (bid_size - prev_bid_size) - (ask_size - prev_ask_size)"],
                    "interpretation": "ofi > 0 表示订单流净流入买盘，类似流量涌向买单节点"
                },
                "速_流速": {
                    "description": "监控订单流速度变化",
                    "implementation": "通过 spread_change 和 ofi 的联合变化判断",
                    "metrics": ["spread_change = spread - prev_spread", "ofi"],
                    "interpretation": "ofi 快速放大 + spread 缩小 = 订单流加速"
                },
                "弹_放大": {
                    "description": "监控订单流冲击放大",
                    "implementation": "通过 depth_imb（深度失衡）和 ofi 衡量冲击",
                    "metrics": ["depth_imb = (bid_size - ask_size) / (bid_size + ask_size)", "ofi"],
                    "interpretation": "大 ofi + 大 depth_imb = 强冲击"
                },
                "深_深度": {
                    "description": "直接分析深度变化",
                    "implementation": "跟踪 bid_size 和 ask_size 的增量变化",
                    "metrics": ["Δbid_size = bid_size - prev_bid_size", "Δask_size = ask_size - prev_ask_size"],
                    "interpretation": "Δbid_size > 0 且 Δask_size < 0 = 买盘深度增加，卖盘深度减少"
                },
                "波_波动": {
                    "description": "监控价差波动",
                    "implementation": "通过 spread 和 spread_change 衡量系统负载",
                    "metrics": ["spread", "spread_change"],
                    "interpretation": "spread 扩大 + spread_change > 0 = 系统压力增加"
                }
            },
            "learning_mechanism": "使用在线逻辑回归学习 OFI、深度失衡、价差变化与下一时刻价格方向的映射关系",
            "output_meaning": "order_flow_up_probability 表示基于订单流不平衡的上涨概率预测"
        }
    },
    "river_微观结构波动异常_top": {
        "principle": {
            "title": "基于微观结构波动异常的流检测",
            "core_concept": "识别微观尺度的波动异常：小幅震荡、高频抖动、突然放大",
            "five_dimensions": {
                "向_流向": {
                    "description": "检测微观流向反转",
                    "implementation": "通过 ret 符号变化判断",
                    "metrics": ["ret = (price - prev_price) / prev_price"],
                    "interpretation": "ret 频繁变号 = 高频抖动；持续同号 = 趋势性放大"
                },
                "速_流速": {
                    "description": "检测微观流速",
                    "implementation": "通过 short_vol 和 long_vol 的比率判断",
                    "metrics": ["vol_ratio = short_vol / long_vol", "short_vol = 0.8*prev + 0.2*|ret|", "long_vol = 0.97*prev + 0.03*|ret|"],
                    "interpretation": "vol_ratio > 1.5 表示短期流速远快于长期 = 突然放大"
                },
                "弹_放大": {
                    "description": "检测微观放大效应",
                    "implementation": "通过 abs_ret 和 vol_ratio 联合判断",
                    "metrics": ["abs_ret", "vol_ratio"],
                    "interpretation": "大 abs_ret + 高 vol_ratio = 微观放大"
                },
                "深_深度": {
                    "description": "间接推断深度",
                    "implementation": "通过 micro_jitter（微幅抖动）推断流动性缓冲",
                    "metrics": ["micro_jitter = |ret - prev_ret|"],
                    "interpretation": "高 micro_jitter = 深度薄，轻微订单即导致价格跳动"
                },
                "波_波动": {
                    "description": "检测微观波动状态",
                    "implementation": "HalfSpaceTrees 综合 short_vol、long_vol、micro_jitter 判断",
                    "metrics": ["anomaly_score = HST.score(abs_ret, short_vol, long_vol, vol_ratio, micro_jitter)"],
                    "interpretation": "高分表示微观结构异常：可能是高频抖动或突然放大"
                }
            },
            "learning_mechanism": "HalfSpaceTrees 在线学习微观波动模式，识别偏离正常状态的异常点",
            "output_meaning": "micro_vol_anomaly_score 表示微观结构波动异常程度，识别小幅震荡/高频抖动/突然放大"
        }
    },
    "river_交易行为痕迹聚类": {
        "principle": {
            "title": "基于流聚类的交易行为痕迹识别",
            "core_concept": "对交易行为脚印进行在线聚类，映射为典型行为标签（做市/分批大单/情绪驱动）",
            "five_dimensions": {
                "向_流向": {
                    "description": "识别行为驱动的流向特征",
                    "implementation": "通过 depth_imb 和 abs_ret 判断",
                    "metrics": ["depth_imb = |bid_size - ask_size| / (bid_size + ask_size)", "abs_ret"],
                    "interpretation": "低 depth_imb + 低 abs_ret = 做市行为；高 depth_imb + 高 abs_ret = 情绪驱动"
                },
                "速_流速": {
                    "description": "识别行为流速特征",
                    "implementation": "通过 vol_ratio 判断",
                    "metrics": ["vol_ratio = volume / vol_ema"],
                    "interpretation": "vol_ratio 持续稳定 = 做市；vol_ratio 间歇放大 = 分批大单"
                },
                "弹_放大": {
                    "description": "识别行为放大效应",
                    "implementation": "通过 burst（爆发力）衡量",
                    "metrics": ["burst = abs_ret * vol_ratio"],
                    "interpretation": "高 burst = 情绪驱动或大单冲击；低 burst = 做市或正常交易"
                },
                "深_深度": {
                    "description": "识别深度操纵痕迹",
                    "implementation": "通过 spread 和 depth_imb 判断",
                    "metrics": ["spread", "depth_imb"],
                    "interpretation": "低 spread + 稳定 depth_imb = 做市提供流动性；spread 波动 + depth_imb 波动 = 大单分批执行"
                },
                "波_波动": {
                    "description": "识别行为波动模式",
                    "implementation": "通过 abs_ret、spread、burst 的联合模式判断",
                    "metrics": ["abs_ret", "spread", "burst"],
                    "interpretation": "低波动簇 = 做市；中波动簇 = 分批大单；高波动簇 = 情绪驱动"
                }
            },
            "learning_mechanism": "在线 KMeans 聚类交易行为特征，halflife=0.35 快速适应行为模式变化，通过簇统计映射语义标签",
            "output_meaning": "behavior_label 表示识别出的交易行为类型：高频做市/大单分批执行/情绪驱动交易"
        }
    },
}


def update_strategies():
    """Update all river strategies with principle explanations."""
    from deva import NB
    
    db = NB('naja_strategies')
    
    updated_count = 0
    failed_count = 0
    not_found_count = 0
    
    # 收集所有需要更新的策略 ID（包括所有重复的）
    strategy_ids_by_name = {}
    for key, value in db.items():
        name = value.get('metadata', {}).get('name')
        if name in PRINCIPLE_EXPLANATIONS:
            # 收集所有同名的策略 ID
            if name not in strategy_ids_by_name:
                strategy_ids_by_name[name] = []
            strategy_ids_by_name[name].append(key)
    
    for strategy_name, strategy_ids in strategy_ids_by_name.items():
        for strategy_id in strategy_ids:
            print(f"处理策略：{strategy_name} (ID: {strategy_id})")
            
            strategy_data = db.get(strategy_id)
            if not strategy_data:
                print(f"  ⚠️  策略数据不存在：{strategy_id}")
                failed_count += 1
                continue
            
            # 更新 diagram_info
            metadata = strategy_data.get('metadata', {})
            if 'diagram_info' not in metadata:
                metadata['diagram_info'] = {}
            
            # 添加原理解释
            metadata['diagram_info']['principle'] = PRINCIPLE_EXPLANATIONS[strategy_name]['principle']
            
            # 保存更新
            strategy_data['metadata'] = metadata
            db[strategy_id] = strategy_data
            
            print(f"  ✅ 更新成功")
            updated_count += 1
    
    # 报告未找到的策略
    for strategy_name in PRINCIPLE_EXPLANATIONS:
        if strategy_name not in strategy_ids_by_name:
            print(f"  ⚠️  未找到策略：{strategy_name}")
            not_found_count += 1
    
    print("\n" + "=" * 80)
    print(f"更新完成：成功 {updated_count} 个，未找到 {not_found_count} 个")
    print("=" * 80)
    
    return updated_count, not_found_count


if __name__ == "__main__":
    updated, not_found = update_strategies()
    if not_found == 0:
        print("\n🎉 所有策略原理解释更新成功！")
    else:
        print(f"\n⚠️  有 {not_found} 个策略未找到，请检查")
