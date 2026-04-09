"""系统架构说明模块

详细展示雷达感知层和认知层的来龙去脉
"""

SYSTEM_ARCHITECTURE_DOC = """
<div style="margin-bottom: 16px; background: linear-gradient(135deg, #1e3a5f 0%, #0f172a 100%); border-radius: 12px; padding: 16px 20px; border: 1px solid rgba(255,255,255,0.1);">
    <div style="font-size: 14px; font-weight: 600; color: #e2e8f0; margin-bottom: 12px; display: flex; align-items: center; gap: 8px;">
        🏗️ Naja 系统架构 · 来龙去脉
    </div>

    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px;">
        <!-- 左侧：雷达层 -->
        <div style="background: rgba(0,0,0,0.3); border-radius: 10px; padding: 14px; border: 1px solid rgba(245,158,11,0.3);">
            <div style="font-size: 13px; font-weight: 600; color: #f59e0b; margin-bottom: 10px; display: flex; align-items: center; gap: 6px;">
                📡 市场感知层 (Radar/Perception)
            </div>

            <div style="font-size: 11px; color: #94a3b8; line-height: 1.8;">
                <div style="margin-bottom: 8px;">
                    <div style="color: #f59e0b; font-weight: 500; margin-bottom: 4px;">📥 数据获取</div>
                    <div style="padding-left: 8px; border-left: 2px solid rgba(245,158,11,0.3);">
                        新闻/行情/全球市场 → <code style="background: rgba(245,158,11,0.1); padding: 1px 4px; border-radius: 3px; font-size: 10px;">RadarNewsFetcher / GlobalMarketScanner</code>
                    </div>
                </div>

                <div style="margin-bottom: 8px;">
                    <div style="color: #f59e0b; font-weight: 500; margin-bottom: 4px;">🔍 异常检测 (MarketScanner)</div>
                    <div style="padding-left: 8px; border-left: 2px solid rgba(245,158,11,0.3);">
                        <div style="margin-bottom: 4px;">
                            <span style="color: #10b981;">● Pattern</span>：同一信号 × N次重复 → <code>score = min(1.0, count/10)</code>
                        </div>
                        <div style="margin-bottom: 4px;">
                            <span style="color: #3b82f6;">● Drift</span>：ADWIN算法检测分布漂移 → <code>drift_detected = True/False</code>
                        </div>
                        <div style="margin-bottom: 4px;">
                            <span style="color: #ef4444;">● Anomaly</span>：Z-score统计异常 → <code>z = (x-mean)/std, |z|>3 触发</code>
                        </div>
                        <div>
                            <span style="color: #8b5cf6;">● BlockAnomaly</span>：齐涨齐跌检测 → <code>up_ratio/down_ratio > 0.7</code>
                        </div>
                    </div>
                </div>

                <div style="margin-bottom: 8px;">
                    <div style="color: #f59e0b; font-weight: 500; margin-bottom: 4px;">📤 事件分发</div>
                    <div style="padding-left: 8px; border-left: 2px solid rgba(245,158,11,0.3);">
                        <code style="background: rgba(0,0,0,0.3); padding: 2px 6px; border-radius: 4px; font-size: 10px;">RadarEvent</code> →
                        NB数据库(<code>naja_radar_events</code>) →
                        认知引擎
                    </div>
                </div>

                <div>
                    <div style="color: #f59e0b; font-weight: 500; margin-bottom: 4px;">⚙️ 核心组件</div>
                    <div style="padding-left: 8px; font-size: 10px; color: #64748b;">
                        NewsFetcher(新闻) | GlobalMarketScanner(全球) | TradingClock(时钟)
                    </div>
                </div>
            </div>
        </div>

        <!-- 右侧：认知层 -->
        <div style="background: rgba(0,0,0,0.3); border-radius: 10px; padding: 14px; border: 1px solid rgba(20,184,166,0.3);">
            <div style="font-size: 13px; font-weight: 600; color: #14b8a6; margin-bottom: 10px; display: flex; align-items: center; gap: 6px;">
                🧠 认知层 (Cognition)
            </div>

            <div style="font-size: 11px; color: #94a3b8; line-height: 1.8;">
                <div style="margin-bottom: 8px;">
                    <div style="color: #14b8a6; font-weight: 500; margin-bottom: 4px;">📥 数据输入</div>
                    <div style="padding-left: 8px; border-left: 2px solid rgba(20,184,166,0.3);">
                        雷达事件 + 新闻/舆情 + 策略结果 → <code style="background: rgba(20,184,166,0.1); padding: 1px 4px; border-radius: 3px; font-size: 10px;">CognitionEngine.ingest_result()</code>
                    </div>
                </div>

                <div style="margin-bottom: 8px;">
                    <div style="color: #14b8a6; font-weight: 500; margin-bottom: 4px;">🧩 信号类型 (SignalType)</div>
                    <div style="padding-left: 8px; border-left: 2px solid rgba(20,184,166,0.3);">
                        <div style="margin-bottom: 2px;"><span style="color: #a855f7;">● topic_emerge/grow/fade</span></div>
                        <div style="margin-bottom: 2px;"><span style="color: #f97316;">● topic_high_attention</span></div>
                        <div><span style="color: #60a5fa;">● topic_trend_shift / narrative_drift</span></div>
                    </div>
                </div>

                <div style="margin-bottom: 8px;">
                    <div style="color: #14b8a6; font-weight: 500; margin-bottom: 4px;">💾 记忆分层</div>
                    <div style="padding-left: 8px; border-left: 2px solid rgba(20,184,166,0.3);">
                        <div>Short(1000条) → Mid(score≥0.6) → Long(LLM反思)</div>
                    </div>
                </div>

                <div>
                    <div style="color: #14b8a6; font-weight: 500; margin-bottom: 4px;">📤 输出</div>
                    <div style="padding-left: 8px; border-left: 2px solid rgba(20,184,166,0.3);">
                        洞察(<code>Insight</code>) → 注意力权重 → 雷达/策略反馈
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- 数据流示意 -->
    <div style="margin-top: 14px; padding: 12px; background: rgba(0,0,0,0.2); border-radius: 8px;">
        <div style="font-size: 11px; color: #64748b; margin-bottom: 8px; text-align: center;">📍 完整数据流</div>
        <div style="display: flex; align-items: center; justify-content: center; gap: 8px; font-size: 10px; flex-wrap: wrap;">
            <span style="color: #94a3b8;">市场数据</span>
            <span style="color: #475569;">→</span>
            <span style="color: #f59e0b; background: rgba(245,158,11,0.1); padding: 2px 8px; border-radius: 4px;">📡 Radar感知层</span>
            <span style="color: #475569;">→</span>
            <span style="color: #10b981;">NewsFetcher/Scanner</span>
            <span style="color: #475569;">→</span>
            <span style="color: #14b8a6;">RadarEvent</span>
            <span style="color: #475569;">→</span>
            <span style="color: #a855f7;">🧠 Cognition认知层</span>
            <span style="color: #475569;">→</span>
            <span style="color: #fb923c;">NewsMindStrategy</span>
            <span style="color: #475569;">→</span>
            <span style="color: #60a5fa;">分层记忆</span>
            <span style="color: #475569;">→</span>
            <span style="color: #f59e0b;">🎯 Attention调度</span>
        </div>
    </div>
</div>
"""


RADAR_DETAILED_DOC = """
<div style="margin-bottom: 16px; background: linear-gradient(135deg, #1e3a5f 0%, #0f172a 100%); border-radius: 12px; padding: 16px 20px; border: 1px solid rgba(245,158,11,0.2);">
    <div style="font-size: 14px; font-weight: 600; color: #f59e0b; margin-bottom: 14px; display: flex; align-items: center; gap: 8px;">
        📡 市场感知层 · 详细工作原理
    </div>

    <div style="font-size: 11px; color: #94a3b8; line-height: 1.8;">
        <!-- 定位说明 -->
        <div style="margin-bottom: 14px; padding: 12px; background: rgba(0,0,0,0.2); border-radius: 8px; border-left: 3px solid #f59e0b;">
            <div style="color: #f59e0b; font-weight: 600; margin-bottom: 8px;">🎯 定位：市场感知层 (Perception Layer)</div>
            <div style="color: #64748b; font-size: 10px; line-height: 1.6;">
                感知层是系统的"眼睛"，负责从外部世界获取市场信息：<br/>
                • 新闻获取：RadarNewsFetcher 实时监控新闻动态<br/>
                • 全球市场：GlobalMarketScanner 追踪国际市场<br/>
                • 异常检测：SignalAnomalyDetector 发现值得关注的模式<br/>
                • 交易时钟：TradingClock 提供市场状态判断
            </div>
        </div>

        <!-- 输入部分 -->
        <div style="margin-bottom: 14px; padding: 12px; background: rgba(0,0,0,0.2); border-radius: 8px; border-left: 3px solid #10b981;">
            <div style="color: #10b981; font-weight: 600; margin-bottom: 8px;">📥 数据获取</div>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; font-size: 10px;">
                <div style="background: rgba(16,185,129,0.1); padding: 8px; border-radius: 6px;">
                    <div style="color: #10b981; font-weight: 500; margin-bottom: 4px;">📰 RadarNewsFetcher</div>
                    <div style="color: #64748b;">定时获取新闻，发布到 TextSignalBus</div>
                </div>
                <div style="background: rgba(16,185,129,0.1); padding: 8px; border-radius: 6px;">
                    <div style="color: #10b981; font-weight: 500; margin-bottom: 4px;">🌐 GlobalMarketScanner</div>
                    <div style="color: #64748b;">全球主要市场行情监控</div>
                </div>
            </div>
        </div>

        <!-- 核心检测器 -->
        <div style="margin-bottom: 14px; padding: 12px; background: rgba(0,0,0,0.2); border-radius: 8px; border-left: 3px solid #3b82f6;">
            <div style="color: #3b82f6; font-weight: 600; margin-bottom: 8px;">🔍 核心检测器 (SignalAnomalyDetector)</div>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px;">
                <!-- Pattern -->
                <div style="margin-bottom: 8px;">
                    <div style="color: #10b981; font-weight: 500; margin-bottom: 4px;">● Pattern（信号模式重复）</div>
                    <div style="color: #64748b; font-size: 10px;">
                        原理：300秒内同一信号≥3次触发<br/>
                        冷却：120秒内不再触发<br/>
                        分数：<code>score = min(1.0, count/10)</code>
                    </div>
                </div>
                <!-- Drift -->
                <div style="margin-bottom: 8px;">
                    <div style="color: #3b82f6; font-weight: 500; margin-bottom: 4px;">● Drift（概念漂移）</div>
                    <div style="color: #64748b; font-size: 10px;">
                        原理：ADWIN算法检测数据分布变化<br/>
                        触发：<code>drift_detected == True</code><br/>
                        分数：<code>score = abs(score)</code>
                    </div>
                </div>
                <!-- Anomaly -->
                <div style="margin-bottom: 8px;">
                    <div style="color: #ef4444; font-weight: 500; margin-bottom: 4px;">● Anomaly（统计异常）</div>
                    <div style="color: #64748b; font-size: 10px;">
                        原理：Welford算法，Z-score检测<br/>
                        触发：积累≥30样本后，<code>|z|>3.0</code><br/>
                        分数：<code>score = min(1.0, |z|/5.0)</code>
                    </div>
                </div>
                <!-- Block -->
                <div>
                    <div style="color: #8b5cf6; font-weight: 500; margin-bottom: 4px;">● BlockAnomaly（板块联动）</div>
                    <div style="color: #64748b; font-size: 10px;">
                        原理：统计板块内齐涨齐跌比例<br/>
                        触发：<code>up/down_ratio > 0.7</code><br/>
                        涨跌家数占比 > 0.5%的股票
                    </div>
                </div>
            </div>
        </div>

        <!-- 输出部分 -->
        <div style="padding: 12px; background: rgba(0,0,0,0.2); border-radius: 8px; border-left: 3px solid #14b8a6;">
            <div style="color: #14b8a6; font-weight: 600; margin-bottom: 8px;">📤 事件分发</div>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; font-size: 10px;">
                <div><span style="color: #64748b;">event_type:</span> radar_pattern/drift/anomaly/block_anomaly</div>
                <div><span style="color: #64748b;">score:</span> 0.0 ~ 1.0</div>
                <div><span style="color: #64748b;">strategy_id:</span> 来源策略ID</div>
                <div><span style="color: #64748b;">message:</span> 事件描述</div>
            </div>
            <div style="margin-top: 8px; color: #64748b; font-size: 10px;">
                后续：存储到 <code>naja_radar_events</code> → 发送到认知引擎
            </div>
        </div>
    </div>
</div>
"""


COGNITION_DETAILED_DOC = """
<div style="margin-bottom: 16px; background: linear-gradient(135deg, #1e3a5f 0%, #0f172a 100%); border-radius: 12px; padding: 16px 20px; border: 1px solid rgba(20,184,166,0.2);">
    <div style="font-size: 14px; font-weight: 600; color: #14b8a6; margin-bottom: 14px; display: flex; align-items: center; gap: 8px;">
        🧠 认知层 · 详细工作原理
    </div>

    <div style="font-size: 11px; color: #94a3b8; line-height: 1.8;">
        <!-- 输入部分 -->
        <div style="margin-bottom: 14px; padding: 12px; background: rgba(0,0,0,0.2); border-radius: 8px; border-left: 3px solid #14b8a6;">
            <div style="color: #14b8a6; font-weight: 600; margin-bottom: 8px;">📥 输入：多源数据</div>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 6px; font-size: 10px;">
                <div style="color: #f59e0b;">📡 雷达事件</div>
                <div style="color: #a855f7;">📰 新闻舆情</div>
                <div style="color: #3b82f6;">📊 策略结果</div>
                <div style="color: #fb923c;">💭 用户反馈</div>
                <div style="color: #10b981;">🔗 供应链事件</div>
                <div style="color: #ec4899;">⚡ 第一性原理</div>
            </div>
            <div style="margin-top: 8px; font-size: 10px;">
                <code style="background: rgba(20,184,166,0.1); padding: 2px 6px; border-radius: 3px;">
                    CognitionEngine.ingest_result(result)
                </code>
            </div>
        </div>

        <!-- 核心处理模块 -->
        <div style="margin-bottom: 14px; padding: 12px; background: rgba(0,0,0,0.2); border-radius: 8px; border-left: 3px solid #a855f7;">
            <div style="color: #a855f7; font-weight: 600; margin-bottom: 8px;">⚙️ 核心处理模块</div>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; font-size: 10px;">
                <div style="background: rgba(139,92,246,0.1); padding: 8px; border-radius: 6px;">
                    <div style="color: #c084fc; font-weight: 500; margin-bottom: 4px;">🔄 CrossSignalAnalyzer</div>
                    <div style="color: #64748b; line-height: 1.5;">
                        跨信号共振检测<br/>
                        新闻×注意力 / 宏观叙事<br/>
                        市场×市场共振
                    </div>
                </div>
                <div style="background: rgba(236,72,153,0.1); padding: 8px; border-radius: 6px;">
                    <div style="color: #ec4899; font-weight: 500; margin-bottom: 4px;">📖 NarrativeTracker</div>
                    <div style="color: #64748b; line-height: 1.5;">
                        叙事生命周期追踪<br/>
                        萌芽→扩散→高潮→消退<br/>
                        供应链叙事联动 ⚡新
                    </div>
                </div>
                <div style="background: rgba(96,165,250,0.1); padding: 8px; border-radius: 6px;">
                    <div style="color: #60a5fa; font-weight: 500; margin-bottom: 4px;">❄️ SemanticColdStart</div>
                    <div style="color: #64748b; line-height: 1.5;">
                        种子词→语义扩展<br/>
                        权重计算→图谱构建<br/>
                        行业衰减配置
                    </div>
                </div>
                <div style="background: rgba(249,115,22,0.1); padding: 8px; border-radius: 6px;">
                    <div style="color: #fb923c; font-weight: 500; margin-bottom: 4px;">🔬 FirstPrinciplesMind ⚡新</div>
                    <div style="color: #64748b; line-height: 1.5;">
                        第一性原理分析<br/>
                        因果链推导<br/>
                        矛盾检测与归纳
                    </div>
                </div>
                <div style="background: rgba(16,185,129,0.1); padding: 8px; border-radius: 6px;">
                    <div style="color: #10b981; font-weight: 500; margin-bottom: 4px;">💰 LiquidityCognition ⚡新</div>
                    <div style="color: #64748b; line-height: 1.5;">
                        流动性结构分析<br/>
                        美林时钟四象限<br/>
                        资金流向追踪
                    </div>
                </div>
                <div style="background: rgba(245,158,11,0.1); padding: 8px; border-radius: 6px;">
                    <div style="color: #f59e0b; font-weight: 500; margin-bottom: 4px;">🌐 GlobalPropagation ⚡新</div>
                    <div style="color: #64748b; line-height: 1.5;">
                        全球市场传播网络<br/>
                        节点变化→沿边传播<br/>
                        动态调权验证
                    </div>
                </div>
            </div>
        </div>

        <!-- 信号类型 -->
        <div style="margin-bottom: 14px; padding: 12px; background: rgba(0,0,0,0.2); border-radius: 8px; border-left: 3px solid #60a5fa;">
            <div style="color: #60a5fa; font-weight: 600; margin-bottom: 8px;">🏷️ 信号类型 (SignalType)</div>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 6px; font-size: 10px;">
                <div><span style="color: #10b981;">topic_emerge</span> - 新话题出现</div>
                <div><span style="color: #10b981;">topic_grow</span> - 话题增长</div>
                <div><span style="color: #64748b;">topic_fade</span> - 话题消退</div>
                <div><span style="color: #f59e0b;">topic_high_attention</span> - 高关注度</div>
                <div><span style="color: #3b82f6;">topic_trend_shift</span> - 趋势转变</div>
                <div><span style="color: #8b5cf6;">narrative_drift</span> - 叙事漂移</div>
                <div><span style="color: #ec4899;">cross_signal_resonance</span> ⚡新</div>
                <div><span style="color: #f59e0b;">narrative_stage_change</span> ⚡新</div>
            </div>
        </div>

        <!-- 记忆分层 -->
        <div style="margin-bottom: 14px; padding: 12px; background: rgba(0,0,0,0.2); border-radius: 8px; border-left: 3px solid #fb923c;">
            <div style="color: #fb923c; font-weight: 600; margin-bottom: 8px;">💾 分层记忆机制</div>
            <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px; font-size: 10px;">
                <div style="text-align: center; padding: 8px; background: rgba(0,0,0,0.3); border-radius: 6px;">
                    <div style="color: #10b981; font-weight: 600;">Short Memory</div>
                    <div style="color: #64748b;">容量: 1000条</div>
                    <div style="color: #64748b;">实时事件流</div>
                </div>
                <div style="text-align: center; padding: 8px; background: rgba(0,0,0,0.3); border-radius: 6px;">
                    <div style="color: #f59e0b; font-weight: 600;">Mid Memory</div>
                    <div style="color: #64748b;">score ≥ 0.6</div>
                    <div style="color: #64748b;">容量: 5000条</div>
                </div>
                <div style="text-align: center; padding: 8px; background: rgba(0,0,0,0.3); border-radius: 6px;">
                    <div style="color: #a855f7; font-weight: 600;">Long Memory</div>
                    <div style="color: #64748b;">LLM反思生成</div>
                    <div style="color: #64748b;">持久保存</div>
                </div>
            </div>
            <div style="margin-top: 8px; padding: 8px; background: rgba(16,185,129,0.1); border-radius: 6px;">
                <div style="color: #10b981; font-weight: 500; margin-bottom: 4px;">🔄 动态阈值调整</div>
                <div style="color: #64748b; font-size: 9px;">
                    市场活跃(>0.6) → 提高阈值(0.85) 减少噪音 | 市场平淡(<0.3) → 降低阈值(0.5) 保留信号
                </div>
            </div>
        </div>

        <!-- 叙事生命周期 -->
        <div style="margin-bottom: 14px; padding: 12px; background: rgba(0,0,0,0.2); border-radius: 8px; border-left: 3px solid #ec4899;">
            <div style="color: #ec4899; font-weight: 600; margin-bottom: 8px;">🌊 叙事生命周期 (NarrativeTracker)</div>
            <div style="display: flex; align-items: center; gap: 4px; margin-bottom: 8px;">
                <span style="padding: 2px 8px; background: #60a5fa; color: #0f172a; border-radius: 4px; font-size: 9px; font-weight: 600;">萌芽</span>
                <span style="color: #475569;">→</span>
                <span style="padding: 2px 8px; background: #818cf8; color: #0f172a; border-radius: 4px; font-size: 9px; font-weight: 600;">扩散</span>
                <span style="color: #475569;">→</span>
                <span style="padding: 2px 8px; background: #f87171; color: #0f172a; border-radius: 4px; font-size: 9px; font-weight: 600;">高潮</span>
                <span style="color: #475569;">→</span>
                <span style="padding: 2px 8px; background: #fb923c; color: #0f172a; border-radius: 4px; font-size: 9px; font-weight: 600;">消退</span>
            </div>
            <div style="font-size: 10px; color: #64748b; line-height: 1.6;">
                <div>• 关键词命中 → 叙事识别 → 阶段判定</div>
                <div>• 注意力分数 = 0.6×计数得分 + 0.4×平均注意力</div>
                <div>• 供应链叙事联动：叙事热点 ↔ 供应链股票双向映射 ⚡新</div>
            </div>
        </div>

        <!-- 输出 -->
        <div style="padding: 12px; background: rgba(0,0,0,0.2); border-radius: 8px; border-left: 3px solid #f59e0b;">
            <div style="color: #f59e0b; font-weight: 600; margin-bottom: 8px;">📤 输出：洞察与建议</div>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; font-size: 10px;">
                <div style="background: rgba(20,184,166,0.1); padding: 8px; border-radius: 6px;">
                    <div style="color: #14b8a6; font-weight: 500;">👁️ 注意力建议</div>
                    <div style="color: #64748b; margin-top: 4px;">标的/板块权重 → Attention Kernel</div>
                </div>
                <div style="background: rgba(168,85,247,0.1); padding: 8px; border-radius: 6px;">
                    <div style="color: #a855f7; font-weight: 500;">🤖 LLM反思</div>
                    <div style="color: #64748b; margin-top: 4px;">深度总结 → InsightPool</div>
                </div>
                <div style="background: rgba(96,165,250,0.1); padding: 8px; border-radius: 6px;">
                    <div style="color: #60a5fa; font-weight: 500;">🔬 第一性原理</div>
                    <div style="color: #64748b; margin-top: 4px;">因果分析 → MetaEvolution ⚡新</div>
                </div>
                <div style="background: rgba(16,185,129,0.1); padding: 8px; border-radius: 6px;">
                    <div style="color: #10b981; font-weight: 500;">💰 流动性信号</div>
                    <div style="color: #64748b; margin-top: 4px;">结构分析 → 四维决策 ⚡新</div>
                </div>
            </div>
        </div>
    </div>
</div>
"""


def get_radar_architecture_doc() -> str:
    """获取雷达层详细架构说明"""
    return RADAR_DETAILED_DOC


def get_cognition_architecture_doc() -> str:
    """获取认知层详细架构说明"""
    return COGNITION_DETAILED_DOC


def get_system_architecture_doc() -> str:
    """获取完整系统架构说明"""
    return SYSTEM_ARCHITECTURE_DOC
