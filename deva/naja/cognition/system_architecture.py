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
                📡 雷达感知层 (Radar)
            </div>

            <div style="font-size: 11px; color: #94a3b8; line-height: 1.8;">
                <div style="margin-bottom: 8px;">
                    <div style="color: #f59e0b; font-weight: 500; margin-bottom: 4px;">📥 数据输入</div>
                    <div style="padding-left: 8px; border-left: 2px solid rgba(245,158,11,0.3);">
                        策略执行结果 → <code style="background: rgba(245,158,11,0.1); padding: 1px 4px; border-radius: 3px; font-size: 10px;">RadarEngine.ingest_result()</code>
                    </div>
                </div>

                <div style="margin-bottom: 8px;">
                    <div style="color: #f59e0b; font-weight: 500; margin-bottom: 4px;">🔍 四种检测器 (MarketScanner)</div>
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
                            <span style="color: #8b5cf6;">● SectorAnomaly</span>：齐涨齐跌检测 → <code>up_ratio/down_ratio > 0.7</code>
                        </div>
                    </div>
                </div>

                <div style="margin-bottom: 8px;">
                    <div style="color: #f59e0b; font-weight: 500; margin-bottom: 4px;">📤 数据输出</div>
                    <div style="padding-left: 8px; border-left: 2px solid rgba(245,158,11,0.3);">
                        <code style="background: rgba(0,0,0,0.3); padding: 2px 6px; border-radius: 4px; font-size: 10px;">RadarEvent</code> →
                        NB数据库(<code>naja_radar_events</code>) →
                        认知引擎
                    </div>
                </div>

                <div>
                    <div style="color: #f59e0b; font-weight: 500; margin-bottom: 4px;">⚙️ 核心参数</div>
                    <div style="padding-left: 8px; font-size: 10px; color: #64748b;">
                        pattern_window=300s | cooldown=120s | z_threshold=3.0 | sector_ratio=0.7
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
            <span style="color: #94a3b8;">策略执行</span>
            <span style="color: #475569;">→</span>
            <span style="color: #f59e0b; background: rgba(245,158,11,0.1); padding: 2px 8px; border-radius: 4px;">Radar.ingest_result()</span>
            <span style="color: #475569;">→</span>
            <span style="color: #10b981;">MarketScanner</span>
            <span style="color: #475569;">→</span>
            <span style="color: #14b8a6;">RadarEvent</span>
            <span style="color: #475569;">→</span>
            <span style="color: #a855f7;">CognitionEngine</span>
            <span style="color: #475569;">→</span>
            <span style="color: #fb923c;">NewsMindStrategy</span>
            <span style="color: #475569;">→</span>
            <span style="color: #60a5fa;">分层记忆</span>
            <span style="color: #475569;">→</span>
            <span style="color: #f59e0b;">Attention调度</span>
        </div>
    </div>
</div>
"""


RADAR_DETAILED_DOC = """
<div style="margin-bottom: 16px; background: linear-gradient(135deg, #1e3a5f 0%, #0f172a 100%); border-radius: 12px; padding: 16px 20px; border: 1px solid rgba(245,158,11,0.2);">
    <div style="font-size: 14px; font-weight: 600; color: #f59e0b; margin-bottom: 14px; display: flex; align-items: center; gap: 8px;">
        📡 雷达感知层 · 详细工作原理
    </div>

    <div style="font-size: 11px; color: #94a3b8; line-height: 1.8;">
        <!-- 输入部分 -->
        <div style="margin-bottom: 14px; padding: 12px; background: rgba(0,0,0,0.2); border-radius: 8px; border-left: 3px solid #f59e0b;">
            <div style="color: #f59e0b; font-weight: 600; margin-bottom: 8px;">📥 输入：策略执行结果</div>
            <div style="margin-bottom: 6px;">
                <code style="background: rgba(245,158,11,0.1); padding: 2px 6px; border-radius: 3px; font-size: 10px;">
                    RadarEngine.ingest_result(result)
                </code>
            </div>
            <div style="color: #64748b; font-size: 10px;">
                result 包含: strategy_id, signal_type, score, message, payload 等字段
            </div>
        </div>

        <!-- 检测器1 -->
        <div style="margin-bottom: 14px; padding: 12px; background: rgba(0,0,0,0.2); border-radius: 8px; border-left: 3px solid #10b981;">
            <div style="color: #10b981; font-weight: 600; margin-bottom: 8px;">🔍 检测器1: Pattern（信号模式重复）</div>
            <div style="margin-bottom: 6px;">
                <code style="background: rgba(16,185,129,0.1); padding: 2px 6px; border-radius: 3px; font-size: 10px;">
                    scan_pattern(strategy_id, signal_type, timestamp)
                </code>
            </div>
            <div style="color: #64748b; font-size: 10px; line-height: 1.6;">
                原理：记录同一策略+同类型信号的时间戳，300秒内出现≥3次则触发<br/>
                冷却：触发后120秒内不再触发<br/>
                分数：<code>score = min(1.0, count / 10)</code>
            </div>
        </div>

        <!-- 检测器2 -->
        <div style="margin-bottom: 14px; padding: 12px; background: rgba(0,0,0,0.2); border-radius: 8px; border-left: 3px solid #3b82f6;">
            <div style="color: #3b82f6; font-weight: 600; margin-bottom: 8px;">🔍 检测器2: Drift（概念漂移）</div>
            <div style="margin-bottom: 6px;">
                <code style="background: rgba(59,130,246,0.1); padding: 2px 6px; border-radius: 3px; font-size: 10px;">
                    scan_drift(strategy_id, score, timestamp)  # 使用 ADWIN 算法
                </code>
            </div>
            <div style="color: #64748b; font-size: 10px; line-height: 1.6;">
                原理：River库的ADWIN漂移检测器，持续监测数据分布变化<br/>
                触发：<code>detector.drift_detected == True</code><br/>
                分数：<code>score = abs(score)</code>
            </div>
        </div>

        <!-- 检测器3 -->
        <div style="margin-bottom: 14px; padding: 12px; background: rgba(0,0,0,0.2); border-radius: 8px; border-left: 3px solid #ef4444;">
            <div style="color: #ef4444; font-weight: 600; margin-bottom: 8px;">🔍 检测器3: Anomaly（统计异常）</div>
            <div style="margin-bottom: 6px;">
                <code style="background: rgba(239,68,68,0.1); padding: 2px 6px; border-radius: 3px; font-size: 10px;">
                    scan_anomaly(strategy_id, signal_type, score, timestamp)
                </code>
            </div>
            <div style="color: #64748b; font-size: 10px; line-height: 1.6;">
                原理：Welford在线算法计算均值和方差<br/>
                触发：积累≥30个样本后，<code>|z-score| > 3.0</code><br/>
                分数：<code>score = min(1.0, |z| / 5.0)</code>
            </div>
        </div>

        <!-- 检测器4 -->
        <div style="margin-bottom: 14px; padding: 12px; background: rgba(0,0,0,0.2); border-radius: 8px; border-left: 3px solid #8b5cf6;">
            <div style="color: #8b5cf6; font-weight: 600; margin-bottom: 8px;">🔍 检测器4: SectorAnomaly（板块联动）</div>
            <div style="margin-bottom: 6px;">
                <code style="background: rgba(139,92,246,0.1); padding: 2px 6px; border-radius: 3px; font-size: 10px;">
                    scan_sector_anomaly(sector_id, symbols, returns, timestamp)
                </code>
            </div>
            <div style="color: #64748b; font-size: 10px; line-height: 1.6;">
                原理：统计板块内个股涨跌情况<br/>
                触发：<code>up_ratio > 0.7</code>（齐涨）或 <code>down_ratio > 0.7</code>（齐跌）<br/>
                涨跌家数占比 = 涨跌幅>0.5%的股票数 / 总股票数
            </div>
        </div>

        <!-- 输出部分 -->
        <div style="padding: 12px; background: rgba(0,0,0,0.2); border-radius: 8px; border-left: 3px solid #14b8a6;">
            <div style="color: #14b8a6; font-weight: 600; margin-bottom: 8px;">📤 输出：RadarEvent</div>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; font-size: 10px;">
                <div><span style="color: #64748b;">event_type:</span> radar_pattern/drift/anomaly/sector_anomaly</div>
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
            </div>
            <div style="margin-top: 8px; font-size: 10px;">
                <code style="background: rgba(20,184,166,0.1); padding: 2px 6px; border-radius: 3px;">
                    CognitionEngine.ingest_result(result)
                </code>
            </div>
        </div>

        <!-- 信号类型 -->
        <div style="margin-bottom: 14px; padding: 12px; background: rgba(0,0,0,0.2); border-radius: 8px; border-left: 3px solid #a855f7;">
            <div style="color: #a855f7; font-weight: 600; margin-bottom: 8px;">🏷️ 信号类型 (SignalType)</div>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 6px; font-size: 10px;">
                <div><span style="color: #10b981;">topic_emerge</span> - 新话题出现</div>
                <div><span style="color: #10b981;">topic_grow</span> - 话题增长</div>
                <div><span style="color: #64748b;">topic_fade</span> - 话题消退</div>
                <div><span style="color: #f59e0b;">topic_high_attention</span> - 高关注度</div>
                <div><span style="color: #3b82f6;">topic_trend_shift</span> - 趋势转变</div>
                <div><span style="color: #8b5cf6;">narrative_drift</span> - 叙事漂移</div>
            </div>
        </div>

        <!-- 数据源识别 -->
        <div style="margin-bottom: 14px; padding: 12px; background: rgba(0,0,0,0.2); border-radius: 8px; border-left: 3px solid #60a5fa;">
            <div style="color: #60a5fa; font-weight: 600; margin-bottom: 8px;">🔎 数据源类型识别</div>
            <div style="font-size: 10px; line-height: 1.6;">
                <div>根据 <code>_datasource_name</code> 或 <code>source</code> 字段识别数据类型：</div>
                <div style="margin-top: 4px; padding-left: 8px; border-left: 2px solid rgba(96,165,250,0.3);">
                    <span style="color: #f59e0b;">新闻类</span>：财经新闻、金十数据、jin10 等<br/>
                    <span style="color: #3b82f6;">行情类</span>：tick、quant、realtime_quant 等<br/>
                    <span style="color: #64748b;">日志类</span>：log、system 等<br/>
                    <span style="color: #8b5cf6;">文件类</span>：file、download 等
                </div>
            </div>
        </div>

        <!-- 记忆分层 -->
        <div style="margin-bottom: 14px; padding: 12px; background: rgba(0,0,0,0.2); border-radius: 8px; border-left: 3px solid #fb923c;">
            <div style="color: #fb923c; font-weight: 600; margin-bottom: 8px;">💾 分层记忆机制</div>
            <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px; font-size: 10px;">
                <div style="text-align: center; padding: 8px; background: rgba(0,0,0,0.3); border-radius: 6px;">
                    <div style="color: #10b981; font-weight: 600;">Short Memory</div>
                    <div style="color: #64748b;">容量: 1000条</div>
                    <div style="color: #64748b;">自动淘汰</div>
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
        </div>

        <!-- 叙事追踪 -->
        <div style="margin-bottom: 14px; padding: 12px; background: rgba(0,0,0,0.2); border-radius: 8px; border-left: 3px solid #ec4899;">
            <div style="color: #ec4899; font-weight: 600; margin-bottom: 8px;">📖 叙事追踪 (NarrativeTracker)</div>
            <div style="font-size: 10px; color: #64748b; line-height: 1.6;">
                <div>• 从新闻事件中提取叙事主题</div>
                <div>• 追踪叙事生命周期：emerging → growing → stable → declining</div>
                <div>• 检测叙事间的关联和冲突</div>
                <div>• 生成叙事摘要供LLM反思使用</div>
            </div>
        </div>

        <!-- 输出 -->
        <div style="padding: 12px; background: rgba(0,0,0,0.2); border-radius: 8px; border-left: 3px solid #f59e0b;">
            <div style="color: #f59e0b; font-weight: 600; margin-bottom: 8px;">📤 输出：洞察与建议</div>
            <div style="font-size: 10px; line-height: 1.6;">
                <div>• <span style="color: #14b8a6;">注意力建议</span>：标的/板块权重 → 反馈给注意力调度</div>
                <div>• <span style="color: #a855f7;">洞察摘要</span>：<code>summarize_for_llm()</code> → LLM反思</div>
                <div>• <span style="color: #60a5fa;">记忆报告</span>：<code>get_memory_report()</code> → 记忆状态</div>
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
