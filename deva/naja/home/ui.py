"""Naja 首页 UI 模块"""

from pywebio.output import put_markdown, put_html


async def render_home(ctx: dict):
    """渲染首页"""
    from ..datasource import get_datasource_manager
    from ..tasks import get_task_manager
    from ..strategy import get_strategy_manager
    from ..dictionary import get_dictionary_manager

    ds_mgr = get_datasource_manager()
    task_mgr = get_task_manager()
    strategy_mgr = get_strategy_manager()
    dict_mgr = get_dictionary_manager()

    ds_stats = ds_mgr.get_stats()
    task_stats = task_mgr.get_stats()
    strategy_stats = strategy_mgr.get_stats()
    dict_stats = dict_mgr.get_stats()


    ctx["put_markdown"]('''### 🚀 Naja 管理平台

基于 **RecoverableUnit** 抽象的统一管理平台，集成 **Attention Kernel** 注意力中枢，实现"境随心转，执处成真"的智能决策系统。

**核心特性：**
- ✅ 多头注意力机制（Market / News / Flow / Meta）
- ✅ 统一的状态管理
- ✅ 自动恢复机制
- ✅ 代码动态编译
- ✅ 持久化存储
- ✅ Bandit 反馈闭环
''')

    ctx["put_html"](f"""
    <div style="display: flex; flex-wrap: wrap; gap: 15px; margin: 20px 0;">
        <div class="stats-card" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);">
            <div class="stats-value">{ds_stats['total']}</div>
            <div class="stats-label">📡 数据源</div>
        </div>
        <div class="stats-card" style="background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);">
            <div class="stats-value">{task_stats['total']}</div>
            <div class="stats-label">⏰ 任务</div>
        </div>
        <div class="stats-card" style="background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);">
            <div class="stats-value">{strategy_stats['total']}</div>
            <div class="stats-label">📊 策略</div>
        </div>
        <div class="stats-card" style="background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%);">
            <div class="stats-value">{dict_stats['total']}</div>
            <div class="stats-label">📚 字典</div>
        </div>
    </div>
    """)

    ctx["put_html"]('''
    <div style="margin-top: 30px; padding: 30px; background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); border-radius: 16px; box-shadow: 0 10px 40px rgba(0,0,0,0.2);">
        <h3 style="color: #fff; margin-bottom: 25px; text-align: center; font-size: 22px;">🧠 Attention Kernel - 注意力中枢</h3>
        <p style="color: #94a3b8; text-align: center; margin-bottom: 30px;">境随心转，执处成真 — 注意力不是发现世界，而是创造世界</p>

        <!-- 注意力流转图 -->
        <div style="display: flex; justify-content: center; align-items: center; flex-wrap: wrap; gap: 20px; margin-bottom: 30px;">
            <div style="text-align: center;">
                <div style="width: 90px; height: 90px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 50%; display: flex; align-items: center; justify-content: center;">
                    <div>
                        <div style="font-size: 28px;">📡</div>
                        <div style="color: #fff; font-size: 11px;">事件</div>
                    </div>
                </div>
                <div style="color: #aaa; font-size: 11px; margin-top: 8px;">Radar / Signal</div>
            </div>

            <div style="color: #00d4ff; font-size: 24px;">→</div>

            <div style="text-align: center;">
                <div style="width: 100px; height: 100px; background: linear-gradient(135deg, #00d4ff 0%, #0099cc 100%); border-radius: 50%; display: flex; align-items: center; justify-content: center; box-shadow: 0 0 30px rgba(0,212,255,0.4);">
                    <div>
                        <div style="font-size: 32px;">🧠</div>
                        <div style="color: #fff; font-size: 12px; font-weight: bold;">Kernel</div>
                    </div>
                </div>
                <div style="color: #00d4ff; font-size: 11px; margin-top: 8px;">QueryState</div>
            </div>

            <div style="color: #00d4ff; font-size: 24px;">→</div>

            <div style="text-align: center;">
                <div style="width: 90px; height: 90px; background: linear-gradient(135deg, #4ade80 0%, #22c55e 100%); border-radius: 50%; display: flex; align-items: center; justify-content: center;">
                    <div>
                        <div style="font-size: 28px;">🧩</div>
                        <div style="color: #fff; font-size: 11px;">MultiHead</div>
                    </div>
                </div>
                <div style="color: #aaa; font-size: 11px; margin-top: 8px;">多头归因</div>
            </div>

            <div style="color: #00d4ff; font-size: 24px;">→</div>

            <div style="text-align: center;">
                <div style="width: 90px; height: 90px; background: linear-gradient(135deg, #a855f7 0%, #9333ea 100%); border-radius: 50%; display: flex; align-items: center; justify-content: center;">
                    <div>
                        <div style="font-size: 28px;">💾</div>
                        <div style="color: #fff; font-size: 11px;">Memory</div>
                    </div>
                </div>
                <div style="color: #aaa; font-size: 11px; margin-top: 8px;">持久记忆</div>
            </div>

            <div style="color: #00d4ff; font-size: 24px;">→</div>

            <div style="text-align: center;">
                <div style="width: 90px; height: 90px; background: linear-gradient(135deg, #f43f5e 0%, #fbbf24 100%); border-radius: 50%; display: flex; align-items: center; justify-content: center;">
                    <div>
                        <div style="font-size: 28px;">🎰</div>
                        <div style="color: #fff; font-size: 11px;">Bandit</div>
                    </div>
                </div>
                <div style="color: #aaa; font-size: 11px; margin-top: 8px;">反馈闭环</div>
            </div>
        </div>

        <!-- 四大能力 -->
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 20px; margin-top: 20px;">
            <a href="/attentionadmin" style="text-decoration: none;">
                <div style="padding: 25px; background: linear-gradient(135deg, rgba(0,212,255,0.2) 0%, rgba(0,153,204,0.2) 100%); border-radius: 12px; border: 1px solid rgba(0,212,255,0.3); color: white; text-align: center; transition: transform 0.3s;" onmouseover="this.style.transform='scale(1.02)'" onmouseout="this.style.transform='scale(1)'">
                    <div style="font-size: 32px; margin-bottom: 15px;">🎯</div>
                    <div style="font-size: 18px; font-weight: 600;">聚焦</div>
                    <div style="font-size: 12px; opacity: 0.8; margin-top: 8px;">QueryState 驱动优先级</div>
                    <div style="font-size: 11px; color: #00d4ff; margin-top: 10px;">同一事件，不同心→不同现实</div>
                </div>
            </a>
            <a href="/attentionadmin" style="text-decoration: none;">
                <div style="padding: 25px; background: linear-gradient(135deg, rgba(74,222,128,0.2) 0%, rgba(34,197,94,0.2) 100%); border-radius: 12px; border: 1px solid rgba(74,222,128,0.3); color: white; text-align: center; transition: transform 0.3s;" onmouseover="this.style.transform='scale(1.02)'" onmouseout="this.style.transform='scale(1)'">
                    <div style="font-size: 32px; margin-bottom: 15px;">🧩</div>
                    <div style="font-size: 18px; font-weight: 600;">清晰</div>
                    <div style="font-size: 12px; opacity: 0.8; margin-top: 8px;">多头归因，可解释</div>
                    <div style="font-size: 11px; color: #4ade80; margin-top: 10px;">Market/News/Flow/Meta 四头并行</div>
                </div>
            </a>
            <a href="/attentionadmin" style="text-decoration: none;">
                <div style="padding: 25px; background: linear-gradient(135deg, rgba(168,85,247,0.2) 0%, rgba(147,51,234,0.2) 100%); border-radius: 12px; border: 1px solid rgba(168,85,247,0.3); color: white; text-align: center; transition: transform 0.3s;" onmouseover="this.style.transform='scale(1.02)'" onmouseout="this.style.transform='scale(1)'">
                    <div style="font-size: 32px; margin-bottom: 15px;">🎮</div>
                    <div style="font-size: 18px; font-weight: 600;">结果</div>
                    <div style="font-size: 12px; opacity: 0.8; margin-top: 8px;">Bandit 反馈闭环</div>
                    <div style="font-size: 11px; color: #a855f7; margin-top: 10px;">正业增执，负业减执</div>
                </div>
            </a>
            <a href="/attentionadmin" style="text-decoration: none;">
                <div style="padding: 25px; background: linear-gradient(135deg, rgba(251,191,36,0.2) 0%, rgba(234,179,8,0.2) 100%); border-radius: 12px; border: 1px solid rgba(251,191,36,0.3); color: white; text-align: center; transition: transform 0.3s;" onmouseover="this.style.transform='scale(1.02)'" onmouseout="this.style.transform='scale(1)'">
                    <div style="font-size: 32px; margin-bottom: 15px;">💾</div>
                    <div style="font-size: 18px; font-weight: 600;">错误</div>
                    <div style="font-size: 12px; opacity: 0.8; margin-top: 8px;">持久记忆 + 衰减</div>
                    <div style="font-size: 11px; color: #fbbf24; margin-top: 10px;">执念追踪，问题可追溯</div>
                </div>
            </a>
        </div>

        <!-- 多头注意力说明 -->
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 15px; margin-top: 25px;">
            <div style="background: rgba(74,222,128,0.1); border-radius: 8px; padding: 15px; text-align: center;">
                <div style="font-size: 24px;">📈</div>
                <div style="color: #4ade80; font-weight: 600; margin-top: 8px;">Market Head</div>
                <div style="color: #aaa; font-size: 11px; margin-top: 5px;">价格变化信号</div>
            </div>
            <div style="background: rgba(96,165,250,0.1); border-radius: 8px; padding: 15px; text-align: center;">
                <div style="font-size: 24px;">📰</div>
                <div style="color: #60a5fa; font-weight: 600; margin-top: 8px;">News Head</div>
                <div style="color: #aaa; font-size: 11px; margin-top: 5px;">情绪和新闻信号</div>
            </div>
            <div style="background: rgba(244,114,182,0.1); border-radius: 8px; padding: 15px; text-align: center;">
                <div style="font-size: 24px;">💧</div>
                <div style="color: #f472b6; font-weight: 600; margin-top: 8px;">Flow Head</div>
                <div style="color: #aaa; font-size: 11px; margin-top: 5px;">资金流向信号</div>
            </div>
            <div style="background: rgba(251,191,36,0.1); border-radius: 8px; padding: 15px; text-align: center;">
                <div style="font-size: 24px;">🎯</div>
                <div style="color: #fbbf24; font-weight: 600; margin-top: 8px;">Meta Head</div>
                <div style="color: #aaa; font-size: 11px; margin-top: 5px;">历史alpha信号</div>
            </div>
        </div>
    </div>
    ''')

    ctx["put_html"]('''
    <div style="margin-top: 30px;">
        <h3>快速导航</h3>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-top: 15px;">
            <a href="/dsadmin" style="text-decoration: none;">
                <div style="padding: 20px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 12px; color: white; text-align: center;">
                    <div style="font-size: 24px;">📡</div>
                    <div style="font-size: 16px; font-weight: 600; margin-top: 8px;">数据源管理</div>
                </div>
            </a>
            <a href="/signaladmin" style="text-decoration: none;">
                <div style="padding: 20px; background: linear-gradient(135deg, #f5576c 0%, #f093fb 100%); border-radius: 12px; color: white; text-align: center;">
                    <div style="font-size: 24px;">🚨</div>
                    <div style="font-size: 16px; font-weight: 600; margin-top: 8px;">💰 信号流</div>
                </div>
            </a>
            <a href="/attentionadmin" style="text-decoration: none;">
                <div style="padding: 20px; background: linear-gradient(135deg, #00d4ff 0%, #0099cc 100%); border-radius: 12px; color: white; text-align: center;">
                    <div style="font-size: 24px;">🧠</div>
                    <div style="font-size: 16px; font-weight: 600; margin-top: 8px;">注意力系统</div>
                </div>
            </a>
            <a href="/taskadmin" style="text-decoration: none;">
                <div style="padding: 20px; background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); border-radius: 12px; color: white; text-align: center;">
                    <div style="font-size: 24px;">⏰</div>
                    <div style="font-size: 16px; font-weight: 600; margin-top: 8px;">任务管理</div>
                </div>
            </a>
            <a href="/strategyadmin" style="text-decoration: none;">
                <div style="padding: 20px; background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); border-radius: 12px; color: white; text-align: center;">
                    <div style="font-size: 24px;">📊</div>
                    <div style="font-size: 16px; font-weight: 600; margin-top: 8px;">策略管理</div>
                </div>
            </a>
            <a href="/radaradmin" style="text-decoration: none;">
                <div style="padding: 20px; background: linear-gradient(135deg, #f59e0b 0%, #ef4444 100%); border-radius: 12px; color: white; text-align: center;">
                    <div style="font-size: 24px;">📡</div>
                    <div style="font-size: 16px; font-weight: 600; margin-top: 8px;">雷达</div>
                </div>
            </a>
            <a href="/memory" style="text-decoration: none;">
                <div style="padding: 20px; background: linear-gradient(135deg, #8b5cf6 0%, #ec4899 100%); border-radius: 12px; color: white; text-align: center;">
                    <div style="font-size: 24px;">🧠</div>
                    <div style="font-size: 16px; font-weight: 600; margin-top: 8px;">记忆</div>
                </div>
            </a>
            <a href="/banditadmin" style="text-decoration: none;">
                <div style="padding: 20px; background: linear-gradient(135deg, #f43f5e 0%, #fbbf24 100%); border-radius: 12px; color: white; text-align: center;">
                    <div style="font-size: 24px;">🎰</div>
                    <div style="font-size: 16px; font-weight: 600; margin-top: 8px;">Bandit</div>
                </div>
            </a>
            <a href="/dictadmin" style="text-decoration: none;">
                <div style="padding: 20px; background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%); border-radius: 12px; color: white; text-align: center;">
                    <div style="font-size: 24px;">📚</div>
                    <div style="font-size: 16px; font-weight: 600; margin-top: 8px;">字典管理</div>
                </div>
            </a>
            <a href="/tableadmin" style="text-decoration: none;">
                <div style="padding: 20px; background: linear-gradient(135deg, #fa709a 0%, #fee140 100%); border-radius: 12px; color: white; text-align: center;">
                    <div style="font-size: 24px;">🗃️</div>
                    <div style="font-size: 16px; font-weight: 600; margin-top: 8px;">数据表管理</div>
                </div>
            </a>
        </div>
    </div>
    ''')

    ctx["put_html"]('''
    <div style="margin-top: 40px; padding: 30px; background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); border-radius: 16px; box-shadow: 0 10px 40px rgba(0,0,0,0.2);">
        <h3 style="color: #fff; margin-bottom: 25px; text-align: center; font-size: 22px;">🔄 Naja 系统架构</h3>

        <div style="display: flex; flex-direction: column; gap: 25px; margin-bottom: 30px;">
            <!-- 主链路 -->
            <div style="display: flex; justify-content: center; align-items: center; flex-wrap: wrap; gap: 18px;">
                <a href="/dsadmin" style="text-decoration: none;">
                    <div style="text-align: center;">
                        <div style="width: 100px; height: 100px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 50%; display: flex; align-items: center; justify-content: center; box-shadow: 0 8px 22px rgba(102,126,234,0.35); cursor: pointer;">
                            <div>
                                <div style="font-size: 32px;">📡</div>
                                <div style="color: #fff; font-size: 12px; font-weight: 600; margin-top: 5px;">数据源</div>
                            </div>
                        </div>
                        <div style="color: #aaa; font-size: 11px; margin-top: 8px;">实时/定时采集</div>
                    </div>
                </a>

                <div style="color: #4facfe; font-size: 26px;">→</div>

                <div style="text-align: center;">
                    <div style="width: 110px; height: 110px; background: linear-gradient(135deg, #00d4ff 0%, #0099cc 100%); border-radius: 50%; display: flex; align-items: center; justify-content: center; box-shadow: 0 0 30px rgba(0,212,255,0.4);">
                        <div>
                            <div style="font-size: 34px;">🧠</div>
                            <div style="color: #fff; font-size: 12px; font-weight: 600; margin-top: 5px;">Attention</div>
                        </div>
                    </div>
                    <div style="color: #00d4ff; font-size: 11px; margin-top: 8px;">注意力中枢</div>
                </div>

                <div style="color: #4facfe; font-size: 26px;">→</div>

                <a href="/strategyadmin" style="text-decoration: none;">
                    <div style="text-align: center;">
                        <div style="width: 100px; height: 100px; background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); border-radius: 50%; display: flex; align-items: center; justify-content: center; box-shadow: 0 8px 22px rgba(79,172,254,0.35);">
                            <div>
                                <div style="font-size: 32px;">📊</div>
                                <div style="color: #fff; font-size: 12px; font-weight: 600; margin-top: 5px;">策略</div>
                            </div>
                        </div>
                        <div style="color: #aaa; font-size: 11px; margin-top: 8px;">处理+决策</div>
                    </div>
                </a>

                <div style="color: #4facfe; font-size: 26px;">→</div>

                <a href="/signaladmin" style="text-decoration: none;">
                    <div style="text-align: center;">
                        <div style="width: 100px; height: 100px; background: linear-gradient(135deg, #f5576c 0%, #f093fb 100%); border-radius: 50%; display: flex; align-items: center; justify-content: center; box-shadow: 0 8px 22px rgba(245,87,108,0.35);">
                            <div>
                                <div style="font-size: 32px;">🚨</div>
                                <div style="color: #fff; font-size: 12px; font-weight: 600; margin-top: 5px;">信号流</div>
                            </div>
                        </div>
                        <div style="color: #aaa; font-size: 11px; margin-top: 8px;">结果输出</div>
                    </div>
                </a>

                <div style="color: #4facfe; font-size: 26px;">↺</div>
            </div>

            <!-- 辅助链路 -->
            <div style="display: flex; justify-content: center; align-items: center; flex-wrap: wrap; gap: 16px; margin-top: 5px;">
                <a href="/radaradmin" style="text-decoration: none;">
                    <div style="text-align: center;">
                        <div style="width: 85px; height: 85px; background: linear-gradient(135deg, #f59e0b 0%, #ef4444 100%); border-radius: 50%; display: flex; align-items: center; justify-content: center; box-shadow: 0 6px 18px rgba(245,158,11,0.35);">
                            <div>
                                <div style="font-size: 26px;">📡</div>
                                <div style="color: #fff; font-size: 10px; font-weight: 600; margin-top: 3px;">雷达</div>
                            </div>
                        </div>
                        <div style="color: #aaa; font-size: 10px; margin-top: 6px;">异常检测</div>
                    </div>
                </a>

                <a href="/memory" style="text-decoration: none;">
                    <div style="text-align: center;">
                        <div style="width: 85px; height: 85px; background: linear-gradient(135deg, #8b5cf6 0%, #ec4899 100%); border-radius: 50%; display: flex; align-items: center; justify-content: center; box-shadow: 0 6px 18px rgba(139,92,246,0.35);">
                            <div>
                                <div style="font-size: 26px;">🧠</div>
                                <div style="color: #fff; font-size: 10px; font-weight: 600; margin-top: 3px;">记忆</div>
                            </div>
                        </div>
                        <div style="color: #aaa; font-size: 10px; margin-top: 6px;">主题聚类</div>
                    </div>
                </a>

                <div style="color: #10b981; font-size: 22px;">→</div>

                <div style="text-align: center;">
                    <div style="width: 90px; height: 90px; background: linear-gradient(135deg, #10b981 0%, #059669 100%); border-radius: 50%; display: flex; align-items: center; justify-content: center; box-shadow: 0 6px 18px rgba(16,185,129,0.35);">
                        <div>
                            <div style="font-size: 28px;">🤖</div>
                            <div style="color: #fff; font-size: 10px; font-weight: 600; margin-top: 3px;">LLM</div>
                        </div>
                    </div>
                    <div style="color: #aaa; font-size: 10px; margin-top: 6px;">自动调节</div>
                </div>

                <div style="color: #4facfe; font-size: 22px;">→</div>

                <a href="/banditadmin" style="text-decoration: none;">
                    <div style="text-align: center;">
                        <div style="width: 85px; height: 85px; background: linear-gradient(135deg, #f43f5e 0%, #fbbf24 100%); border-radius: 50%; display: flex; align-items: center; justify-content: center; box-shadow: 0 6px 18px rgba(244,63,94,0.35);">
                            <div>
                                <div style="font-size: 26px;">🎰</div>
                                <div style="color: #fff; font-size: 10px; font-weight: 600; margin-top: 3px;">Bandit</div>
                            </div>
                        </div>
                        <div style="color: #aaa; font-size: 10px; margin-top: 6px;">强化学习</div>
                    </div>
                </a>

                <div style="color: #aaa; font-size: 11px;">→</div>

                <div style="text-align: center;">
                    <div style="width: 75px; height: 75px; background: linear-gradient(135deg, #3b82f6 0%, #06b6d4 100%); border-radius: 50%; display: flex; align-items: center; justify-content: center; box-shadow: 0 5px 15px rgba(59,130,246,0.35);">
                        <div>
                            <div style="font-size: 24px;">💰</div>
                            <div style="color: #fff; font-size: 9px; font-weight: 600; margin-top: 2px;">组合</div>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- 组件说明 -->
        <div style="display: flex; justify-content: center; gap: 25px; flex-wrap: wrap; margin-bottom: 20px;">
            <div style="display: flex; align-items: center; gap: 8px;">
                <div style="width: 14px; height: 14px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 50%;"></div>
                <span style="color: #ccc; font-size: 11px;">数据源</span>
            </div>
            <div style="display: flex; align-items: center; gap: 8px;">
                <div style="width: 14px; height: 14px; background: linear-gradient(135deg, #00d4ff 0%, #0099cc 100%); border-radius: 50%;"></div>
                <span style="color: #ccc; font-size: 11px;">Attention</span>
            </div>
            <div style="display: flex; align-items: center; gap: 8px;">
                <div style="width: 14px; height: 14px; background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); border-radius: 50%;"></div>
                <span style="color: #ccc; font-size: 11px;">策略</span>
            </div>
            <div style="display: flex; align-items: center; gap: 8px;">
                <div style="width: 14px; height: 14px; background: linear-gradient(135deg, #f5576c 0%, #f093fb 100%); border-radius: 50%;"></div>
                <span style="color: #ccc; font-size: 11px;">信号流</span>
            </div>
            <div style="display: flex; align-items: center; gap: 8px;">
                <div style="width: 14px; height: 14px; background: linear-gradient(135deg, #f59e0b 0%, #ef4444 100%); border-radius: 50%;"></div>
                <span style="color: #ccc; font-size: 11px;">雷达</span>
            </div>
            <div style="display: flex; align-items: center; gap: 8px;">
                <div style="width: 14px; height: 14px; background: linear-gradient(135deg, #8b5cf6 0%, #ec4899 100%); border-radius: 50%;"></div>
                <span style="color: #ccc; font-size: 11px;">记忆</span>
            </div>
            <div style="display: flex; align-items: center; gap: 8px;">
                <div style="width: 14px; height: 14px; background: linear-gradient(135deg, #f43f5e 0%, #fbbf24 100%); border-radius: 50%;"></div>
                <span style="color: #ccc; font-size: 11px;">Bandit</span>
            </div>
        </div>

        <!-- 核心流程 -->
        <div style="background: rgba(255,255,255,0.05); border-radius: 12px; padding: 20px; margin-bottom: 20px;">
            <div style="color: #fff; font-size: 14px; line-height: 2;">
                <strong style="color: #00d4ff;">🔄 核心流程：</strong><br>
                <span style="color: #ccc;">
                <strong style="color: #667eea;">数据源</strong> → <strong style="color: #00d4ff;">注意力中枢</strong> → <strong style="color: #4facfe;">策略</strong> → <strong style="color: #f5576c;">信号流</strong> → <strong style="color: #f43f5e;">Bandit</strong>
                </span>
            </div>
            <div style="color: #aaa; font-size: 12px; margin-top: 10px; padding: 10px; background: rgba(0,212,255,0.1); border-radius: 8px;">
                💡 <strong>Attention Kernel</strong> 作为核心中枢，协调多头注意力、记忆持久化和 Bandit 反馈
            </div>
        </div>

        <style>
            @keyframes pulse {
                0%, 100% { opacity: 1; }
                50% { opacity: 0.5; }
            }
        </style>
    </div>
    ''')

    ctx["put_html"]('''
    <div style="margin-top: 30px;">
        <h3>快速链接</h3>
        <div style="display: flex; justify-content: center; gap: 40px; flex-wrap: wrap; margin-top: 20px;">
            <div style="text-align: center;">
                <a href="/taskadmin" style="text-decoration: none;">
                    <div style="width: 75px; height: 75px; background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); border-radius: 50%; display: flex; align-items: center; justify-content: center; box-shadow: 0 5px 18px rgba(240,147,251,0.35); cursor: pointer;">
                        <div>
                            <div style="font-size: 22px;">⏰</div>
                            <div style="color: #fff; font-size: 10px; font-weight: 600;">任务</div>
                        </div>
                    </div>
                </a>
                <div style="color: #aaa; font-size: 11px; margin-top: 8px;">定时调度</div>
            </div>

            <div style="text-align: center;">
                <a href="/dictadmin" style="text-decoration: none;">
                    <div style="width: 75px; height: 75px; background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%); border-radius: 50%; display: flex; align-items: center; justify-content: center; box-shadow: 0 5px 18px rgba(67,233,123,0.35); cursor: pointer;">
                        <div>
                            <div style="font-size: 22px;">📚</div>
                            <div style="color: #fff; font-size: 10px; font-weight: 600;">字典</div>
                        </div>
                    </div>
                </a>
                <div style="color: #aaa; font-size: 11px; margin-top: 8px;">参考数据</div>
            </div>

            <div style="text-align: center;">
                <a href="/tableadmin" style="text-decoration: none;">
                    <div style="width: 75px; height: 75px; background: linear-gradient(135deg, #fa709a 0%, #fee140 100%); border-radius: 50%; display: flex; align-items: center; justify-content: center; box-shadow: 0 5px 18px rgba(250,112,154,0.35); cursor: pointer;">
                        <div>
                            <div style="font-size: 22px;">💾</div>
                            <div style="color: #fff; font-size: 10px; font-weight: 600;">数据表</div>
                        </div>
                    </div>
                </a>
                <div style="color: #aaa; font-size: 11px; margin-top: 8px;">持久化</div>
            </div>

            <div style="text-align: center;">
                <a href="/configadmin" style="text-decoration: none;">
                    <div style="width: 75px; height: 75px; background: linear-gradient(135deg, #6a11cb 0%, #2575fc 100%); border-radius: 50%; display: flex; align-items: center; justify-content: center; box-shadow: 0 5px 18px rgba(106,17,203,0.35); cursor: pointer;">
                        <div>
                            <div style="font-size: 22px;">⚙️</div>
                            <div style="color: #fff; font-size: 10px; font-weight: 600;">配置</div>
                        </div>
                    </div>
                </a>
                <div style="color: #aaa; font-size: 11px; margin-top: 8px;">全局参数</div>
            </div>

            <div style="text-align: center;">
                <a href="/system" style="text-decoration: none;">
                    <div style="width: 75px; height: 75px; background: linear-gradient(135deg, #0ea5e9 0%, #38bdf8 100%); border-radius: 50%; display: flex; align-items: center; justify-content: center; box-shadow: 0 5px 18px rgba(14,165,233,0.35); cursor: pointer;">
                        <div>
                            <div style="font-size: 22px;">🛠️</div>
                            <div style="color: #fff; font-size: 10px; font-weight: 600;">系统</div>
                        </div>
                    </div>
                </a>
                <div style="color: #aaa; font-size: 11px; margin-top: 8px;">系统监控</div>
            </div>
        </div>
    </div>
    ''')