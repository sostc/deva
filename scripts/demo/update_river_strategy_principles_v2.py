#!/usr/bin/env python3
"""Update River strategies with principle explanations based on river analogy.

根据文章的河流比喻，为每个 river 策略添加详细的原理解释。
核心概念：将市场想象成一条河流，tick 是水面上的波纹
五个维度：向（流向）、速（流速）、弹（弹性）、深（深度）、波（波动）
"""

from __future__ import annotations

from deva import NB


# 为每个策略定义基于河流比喻的原理解释
PRINCIPLE_EXPLANATIONS = {
    "river_短期方向概率_top": {
        "principle": {
            "title": "河流比喻：短期方向概率预测",
            "core_concept": "把市场想象成河流，tick 是波纹。通过在线学习察觉水势变化，预测水流方向。",
            "five_dimensions": {
                "向_水往哪流": {
                    "description": "水在往哪边流",
                    "implementation": "通过 imbalance 和 spread 判断水流方向，就像观察水面漂浮物的移动",
                    "metrics": [
                        "imbalance = (bid_size - ask_size) / (bid_size + ask_size) - 水流偏向",
                        "spread = (ask - bid) / price - 水流阻力"
                    ],
                    "interpretation": "主动买多时，像水流向一个方向加速；主动卖多时，像水在倒灌"
                },
                "速_流得多急": {
                    "description": "水流有多急",
                    "implementation": "通过 vol_ratio 检测流速变化，就像观察河水的湍急程度",
                    "metrics": [
                        "vol_ratio = volume / vol_ema",
                        "vol_ema = 0.95 * prev + 0.05 * current - 平滑流速"
                    ],
                    "interpretation": "水流速度变快，意味着上游来水增加或河道变窄；成交密集说明有新力量进入河道"
                },
                "弹_撞石会不会跳": {
                    "description": "水碰到石头会不会跳起来",
                    "implementation": "通过 ret_1 和 p_change 观察价格跳跃，就像看水花溅起的高度",
                    "metrics": [
                        "ret_1 = (price - last_price) / last_price - 水花高度",
                        "p_change - 涨跌幅"
                    ],
                    "interpretation": "有的河水撞到石头就溅起浪花，有的却只是缓慢流过；这取决于河道结构"
                },
                "深_河道有多深": {
                    "description": "河道有多深多宽",
                    "implementation": "通过 bid_size 和 ask_size 评估河道深度",
                    "metrics": [
                        "bid_size - 买盘厚度（河道一侧深度）",
                        "ask_size - 卖盘厚度（河道另一侧深度）"
                    ],
                    "interpretation": "河道深宽时，再大水流也不易起浪；盘口厚时，市场像深水河道；盘口薄时，像浅滩"
                },
                "波_水面起不起浪": {
                    "description": "水面是不是在起浪",
                    "implementation": "通过 spread 和 volume 的联合变化观察波浪",
                    "metrics": ["spread 扩大 + volume 放大 = 浪花翻滚"],
                    "interpretation": "河水平静如镜时，市场没有情绪；浪花翻滚时，水流正在互相冲撞"
                }
            },
            "learning_mechanism": "使用 River LogisticRegression 持续学习，就像在河边放了一双会记忆的眼睛，慢慢察觉上游水势的改变",
            "output_meaning": "up_probability 表示水流向上涨方向流动的概率，不预测每滴水去向，但察觉水势变化"
        }
    },
    "river_量价盘口异常分数_top": {
        "principle": {
            "title": "河流比喻：量价盘口异常检测",
            "core_concept": "用 HalfSpaceTrees 检测河流异常状态，识别水流突变、河道变化。",
            "five_dimensions": {
                "向_水流回旋": {
                    "description": "水流忽然回旋，说明遇到阻挡",
                    "implementation": "通过 imbalance_jump 检测流向突变",
                    "metrics": ["imbalance_jump = |imbalance - prev_imbalance| - 水流回旋程度"],
                    "interpretation": "水流如果明显向一个方向加速，说明上游来水在增加；忽然回旋说明下游遇到阻挡"
                },
                "速_忽然急湍": {
                    "description": "有的河段突然急湍",
                    "implementation": "通过 vol_ratio 识别流速突变",
                    "metrics": ["vol_ratio = volume / vol_ema - 流速变化"],
                    "interpretation": "水流速度变快通常意味着：上游突然来水，或者河道变窄"
                },
                "弹_水花四溅": {
                    "description": "撞到石头溅起浪花",
                    "implementation": "通过 abs_ret 衡量价格跳跃",
                    "metrics": ["abs_ret = |(price - prev_price) / prev_price| - 水花高度"],
                    "interpretation": "有时候一点点成交就让价格跳动，有时候很多成交价格却不动"
                },
                "深_河道宽窄": {
                    "description": "河道结构决定水流行为",
                    "implementation": "通过 spread 和 imbalance 判断河道结构",
                    "metrics": [
                        "spread = (ask - bid) / price - 河道宽度",
                        "imbalance - 河道偏向"
                    ],
                    "interpretation": "河道如果很深很宽，再大的水流也不容易掀起波浪"
                },
                "波_浪花翻滚": {
                    "description": "浪花翻滚说明水流冲撞",
                    "implementation": "HalfSpaceTrees 综合所有特征计算异常分数",
                    "metrics": ["anomaly_score = HST.score(x) - 浪花高度"],
                    "interpretation": "浪大的时候，说明水流正在互相冲撞"
                }
            },
            "learning_mechanism": "HalfSpaceTrees 通过构建多棵随机分裂树，统计样本在窗口内的深度分布，快速识别河流异常点",
            "output_meaning": "anomaly_score 表示河流异常程度，识别水流突变、河道变化等异常情况"
        }
    },
    "river_tick_市场气候聚类": {
        "principle": {
            "title": "河流比喻：市场气候（河流状态）聚类",
            "core_concept": "用在线 KMeans 将河流状态聚类为不同气候：平静河道/湍急河流/浪花翻滚。",
            "five_dimensions": {
                "向_主流方向": {
                    "description": "河流的主流方向",
                    "implementation": "通过 ret 和 imbalance 判断流向特征",
                    "metrics": [
                        "ret - 水流方向",
                        "imbalance - 水流偏向"
                    ],
                    "interpretation": "水流如果明显向一个方向加速，说明是趋势气候；杂乱回旋是震荡气候"
                },
                "速_缓急程度": {
                    "description": "河段是缓慢还是急湍",
                    "implementation": "通过 volume 衡量流量强度",
                    "metrics": ["volume - 水流强度"],
                    "interpretation": "有的河段缓慢平静，有的地方突然急湍"
                },
                "弹_撞石反应": {
                    "description": "水撞石头的反应",
                    "implementation": "通过 abs_ret 和 spread 判断",
                    "metrics": ["abs_ret + spread - 撞石反应强度"],
                    "interpretation": "高值表示事件放大效应强，像撞到石头溅起浪花"
                },
                "深_河道深浅": {
                    "description": "河道是深水还是浅滩",
                    "implementation": "通过 spread 衡量河道深度",
                    "metrics": ["spread = (ask - bid) / price - 河道深度"],
                    "interpretation": "spread 小 = 深水河道；spread 大 = 浅滩"
                },
                "波_水面状态": {
                    "description": "水面是平静还是起浪",
                    "implementation": "通过 trend_strength 综合判断",
                    "metrics": ["trend_strength = abs_ret / (abs_ret + abs_spread) - 波浪程度"],
                    "interpretation": "trend_strength 高 = 湍急河流；低 = 平静河道"
                }
            },
            "learning_mechanism": "在线 KMeans 持续更新聚类中心，halflife=0.4 确保对近期水势更敏感，自动适应河流状态变迁",
            "output_meaning": "dominant_cluster 表示当前河流的主导状态（0:平静河道/1:湍急河流/2:浪花翻滚）"
        }
    },
    "river_订单流失衡先行信号": {
        "principle": {
            "title": "河流比喻：订单流失衡（上游水势）先行信号",
            "core_concept": "从盘口深度与价差变化学习订单流失衡，就像观察上游水势预测下游水流。",
            "five_dimensions": {
                "向_上游来水": {
                    "description": "上游来水在增加还是减少",
                    "implementation": "通过 OFI（Order Flow Imbalance）量化订单流净方向",
                    "metrics": ["ofi = (bid_size - prev_bid_size) - (ask_size - prev_ask_size) - 上游来水量"],
                    "interpretation": "ofi > 0 表示订单流净流入买盘，就像上游来水在增加"
                },
                "速_水流加速": {
                    "description": "水流正在加速还是减速",
                    "implementation": "通过 spread_change 和 ofi 的联合变化判断",
                    "metrics": [
                        "spread_change = spread - prev_spread - 河道变化",
                        "ofi - 来水量"
                    ],
                    "interpretation": "ofi 快速放大 + spread 缩小 = 订单流加速，像河道变窄水流加速"
                },
                "弹_冲击力度": {
                    "description": "水流冲击河道的力度",
                    "implementation": "通过 depth_imb 和 ofi 衡量冲击",
                    "metrics": [
                        "depth_imb = (bid_size - ask_size) / (bid_size + ask_size) - 河道偏向",
                        "ofi - 来水量"
                    ],
                    "interpretation": "大 ofi + 大 depth_imb = 强冲击，像洪水冲击河道"
                },
                "深_河道结构": {
                    "description": "直接观察河道结构变化",
                    "implementation": "跟踪 bid_size 和 ask_size 的增量变化",
                    "metrics": [
                        "Δbid_size = bid_size - prev_bid_size - 买盘侧河道变化",
                        "Δask_size = ask_size - prev_ask_size - 卖盘侧河道变化"
                    ],
                    "interpretation": "Δbid_size > 0 且 Δask_size < 0 = 买盘侧河道加深，卖盘侧变浅"
                },
                "波_水面反应": {
                    "description": "水面对来水的反应",
                    "implementation": "通过 spread 和 spread_change 衡量",
                    "metrics": [
                        "spread - 河道宽度",
                        "spread_change - 河道变化"
                    ],
                    "interpretation": "spread 扩大 + spread_change > 0 = 河道变窄，系统压力增加"
                }
            },
            "learning_mechanism": "使用在线逻辑回归学习 OFI、深度失衡、价差变化与下一时刻价格方向的映射关系，就像学习上游水势与下游水流的关系",
            "output_meaning": "order_flow_up_probability 表示基于上游水势的下游水流方向预测"
        }
    },
    "river_微观结构波动异常_top": {
        "principle": {
            "title": "河流比喻：微观结构波动（水纹）异常检测",
            "core_concept": "识别微观尺度的水纹异常：小幅震荡、高频抖动、突然放大，就像观察水面波纹的细微变化。",
            "five_dimensions": {
                "向_水纹方向": {
                    "description": "水纹的方向变化",
                    "implementation": "通过 ret 符号变化判断",
                    "metrics": ["ret = (price - prev_price) / prev_price - 水纹方向"],
                    "interpretation": "ret 频繁变号 = 高频抖动，像水面微风扰动；持续同号 = 趋势性放大"
                },
                "速_波纹速度": {
                    "description": "波纹传播的速度",
                    "implementation": "通过 short_vol 和 long_vol 的比率判断",
                    "metrics": [
                        "vol_ratio = short_vol / long_vol - 波纹速度比",
                        "short_vol = 0.8*prev + 0.2*|ret| - 短期波纹",
                        "long_vol = 0.97*prev + 0.03*|ret| - 长期波纹"
                    ],
                    "interpretation": "vol_ratio > 1.5 表示短期波纹远快于长期 = 突然放大，像石子投入水中"
                },
                "弹_水花跳跃": {
                    "description": "水花的跳跃程度",
                    "implementation": "通过 abs_ret 和 vol_ratio 联合判断",
                    "metrics": ["abs_ret - 水花高度", "vol_ratio - 波纹速度"],
                    "interpretation": "大 abs_ret + 高 vol_ratio = 微观放大，像石子激起水花"
                },
                "深_水面深浅": {
                    "description": "水面的深浅程度",
                    "implementation": "通过 micro_jitter 推断水面深浅",
                    "metrics": ["micro_jitter = |ret - prev_ret| - 水纹抖动"],
                    "interpretation": "高 micro_jitter = 水面浅，轻微扰动即导致水纹跳动"
                },
                "波_波纹状态": {
                    "description": "波纹的异常状态",
                    "implementation": "HalfSpaceTrees 综合所有特征判断",
                    "metrics": ["anomaly_score = HST.score(abs_ret, short_vol, long_vol, vol_ratio, micro_jitter)"],
                    "interpretation": "高分表示微观水纹异常：可能是高频抖动或突然放大"
                }
            },
            "learning_mechanism": "HalfSpaceTrees 在线学习微观水纹模式，识别偏离正常状态的异常点",
            "output_meaning": "micro_vol_anomaly_score 表示微观水纹波动异常程度，识别小幅震荡/高频抖动/突然放大"
        }
    },
    "river_交易行为痕迹聚类": {
        "principle": {
            "title": "河流比喻：交易行为痕迹（水流脚印）聚类",
            "core_concept": "对交易行为脚印进行在线聚类，映射为典型行为标签，就像观察河流中的水流脚印识别水源类型。",
            "five_dimensions": {
                "向_水流脚印": {
                    "description": "水流留下的方向脚印",
                    "implementation": "通过 depth_imb 和 abs_ret 判断",
                    "metrics": [
                        "depth_imb = |bid_size - ask_size| / (bid_size + ask_size) - 水流偏向脚印",
                        "abs_ret - 水流强度脚印"
                    ],
                    "interpretation": "低 depth_imb + 低 abs_ret = 做市行为，像稳定水流；高 depth_imb + 高 abs_ret = 情绪驱动，像洪水"
                },
                "速_水流节奏": {
                    "description": "水流的节奏特征",
                    "implementation": "通过 vol_ratio 判断",
                    "metrics": ["vol_ratio = volume / vol_ema - 水流节奏"],
                    "interpretation": "vol_ratio 持续稳定 = 做市，像稳定河流；vol_ratio 间歇放大 = 分批大单，像间歇性来水"
                },
                "弹_水流冲击": {
                    "description": "水流的冲击力度",
                    "implementation": "通过 burst（爆发力）衡量",
                    "metrics": ["burst = abs_ret * vol_ratio - 水流爆发力"],
                    "interpretation": "高 burst = 情绪驱动或大单冲击，像洪水冲击；低 burst = 做市或正常交易，像平缓水流"
                },
                "深_河道塑造": {
                    "description": "水流塑造的河道痕迹",
                    "implementation": "通过 spread 和 depth_imb 判断",
                    "metrics": [
                        "spread - 河道宽度",
                        "depth_imb - 河道偏向"
                    ],
                    "interpretation": "低 spread + 稳定 depth_imb = 做市提供流动性，像稳定河道；spread 波动 + depth_imb 波动 = 大单分批执行，像河道被不断塑造"
                },
                "波_水流波纹": {
                    "description": "水流产生的波纹模式",
                    "implementation": "通过 abs_ret、spread、burst 的联合模式判断",
                    "metrics": ["abs_ret - 波纹高度", "spread - 河道宽度", "burst - 冲击力度"],
                    "interpretation": "低波动簇 = 做市，像平静河流；中波动簇 = 分批大单，像间歇水流；高波动簇 = 情绪驱动，像洪水"
                }
            },
            "learning_mechanism": "在线 KMeans 聚类交易行为特征，halflife=0.35 快速适应水流模式变化，通过簇统计映射水源类型标签",
            "output_meaning": "behavior_label 表示识别出的水流脚印类型：高频做市（稳定河流）/大单分批执行（间歇水流）/情绪驱动交易（洪水）"
        }
    },
}


def update_strategies():
    """Update all river strategies with principle explanations based on river analogy."""
    db = NB('naja_strategies')
    
    updated_count = 0
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
