"""首页快速链接面板"""


def render_quick_links_panel(ctx: dict):
    """渲染快速链接面板"""
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
