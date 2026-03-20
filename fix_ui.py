#!/usr/bin/env python3
# 修改热门股票的展示方式为紧凑标签风格

with open('deva/naja/attention/ui.py', 'r') as f:
    content = f.read()

# 找到并替换热门股票代码块
old_block = '''    # 热门股票
    if stocks:
        html += """
            <div>
                <div style="font-weight: 600; color: #2563eb; margin-bottom: 12px; font-size: 14px;
                            display: flex; justify-content: space-between; align-items: center;">
                    <span>📈 热门股票 Top 20</span>
                    <span style="font-size: 11px; color: #94a3b8; font-weight: normal;">注意力得分</span>
                </div>
                <div style="max-height: 500px; overflow-y: auto; padding-right: 4px;">
        """

        # 计算最大权重用于进度条
        max_stock_weight = max([w for _, w in stocks[:20]]) if stocks else 1

        for i, (symbol, weight) in enumerate(stocks[:20], 1):
            # 根据权重确定颜色和状态
            if weight > 5:
                color = "#dc2626"
                status = "🔥 爆发"
                bg_color = "#fef2f2"
                border_color = "#fecaca"
            elif weight > 3:
                color = "#ea580c"
                status = "⚡ 强势"
                bg_color = "#fff7ed"
                border_color = "#fed7aa"
            elif weight > 2:
                color = "#ca8a04"
                status = "📊 活跃"
                bg_color = "#fefce8"
                border_color = "#fef08a"
            else:
                color = "#16a34a"
                status = "💤 平稳"
                bg_color = "#f0fdf4"
                border_color = "#bbf7d0"

            # 获取股票名称、所属板块和涨跌幅
            symbol_name = tracker.get_symbol_name(symbol) if tracker else symbol
            symbol_sector = tracker.get_symbol_sector(symbol) if tracker else ''
            symbol_change = tracker.get_symbol_change(symbol) if tracker else None
            change_str = f"{symbol_change:+.2f}%" if symbol_change is not None else ""
            change_color = "#16a34a" if symbol_change and symbol_change > 0 else ("#dc2626" if symbol_change and symbol_change < 0 else "#64748b")

            # 获取趋势
            trend = "➡️"
            weight_change_str = ""
            if tracker:
                trend_data = tracker.get_symbol_trend(symbol, n=3)
                if len(trend_data) >= 2:
                    prev_weight = trend_data[-2]['weight']
                    change = weight - prev_weight
                    change_pct = (change / prev_weight * 100) if prev_weight > 0 else 0
                    if change_pct > 10:
                        trend = "🚀"
                    elif change_pct > 5:
                        trend = "📈"
                    elif change_pct < -10:
                        trend = "📉"
                    elif change_pct < -5:
                        trend = "🔻"

                    if abs(change_pct) > 1:
                        weight_change_str = f"{change_pct:+.1f}%"

            # 进度条宽度
            progress_width = (weight / max_stock_weight * 100) if max_stock_weight > 0 else 0

            html += f"""
                <div style="
                    padding: 8px 10px;
                    margin-bottom: 6px;
                    background: {bg_color};
                    border: 1px solid {border_color};
                    border-radius: 8px;
                ">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                        <div style="display: flex; align-items: center; gap: 6px; flex: 1;">
                            <span style="color: #64748b; font-weight: 600; min-width: 18px; font-size: 12px;">{i}.</span>
                            <span style="font-weight: 600; color: #1e293b; font-size: 13px;">{symbol}</span>
                            <span style="font-size: 12px; color: #475569;">{symbol_name}</span>
                            {f'<span style="font-size: 10px; color: #64748b; background: #f1f5f9; padding: 1px 4px; border-radius: 3px;">{symbol_sector}</span>' if symbol_sector else ''}
                        </div>
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <span style="font-size: 11px; color: {change_color}; font-weight: 600;">{change_str}</span>
                            <span style="font-size: 11px;">{trend}</span>
                            <span style="color: {color}; font-weight: 700; font-size: 13px;">{weight:.2f}</span>
                            {f'<span style="font-size: 9px; color: #64748b;">({weight_change_str})</span>' if weight_change_str else ''}
                        </div>
                    </div>
                    <div style="display: flex; align-items: center; gap: 6px;">
                        <div style="background: rgba(255,255,255,0.6); height: 3px; border-radius: 2px; overflow: hidden; flex: 1;">
                            <div style="background: {color}; height: 100%; width: {progress_width}%; border-radius: 2px; transition: width 0.3s;"></div>
                        </div>
                        <span style="font-size: 9px; color: {color}; min-width: 35px; text-align: right;">{status}</span>
                    </div>
                </div>
            """
        html += "</div></div>"

    html += "</div></div>"
    return html'''

new_block = '''    # 热门股票
    if stocks:
        html += """
            <div>
                <div style="font-weight: 600; color: #2563eb; margin-bottom: 12px; font-size: 14px;">
                    📈 热门股票 Top 20
                </div>
                <div style="display: flex; flex-wrap: wrap; gap: 6px;">
        """

        for i, (symbol, weight) in enumerate(stocks[:20], 1):
            # 根据权重确定颜色
            if weight > 5:
                color = "#dc2626"
                bg_color = "#fef2f2"
                border_color = "#fecaca"
            elif weight > 3:
                color = "#ea580c"
                bg_color = "#fff7ed"
                border_color = "#fed7aa"
            elif weight > 2:
                color = "#ca8a04"
                bg_color = "#fefce8"
                border_color = "#fef08a"
            else:
                color = "#16a34a"
                bg_color = "#f0fdf4"
                border_color = "#bbf7d0"

            # 获取股票信息
            symbol_name = tracker.get_symbol_name(symbol) if tracker else symbol
            symbol_change = tracker.get_symbol_change(symbol) if tracker else None
            change_str = f"{symbol_change:+.2f}%" if symbol_change is not None else ""
            change_color = "#16a34a" if symbol_change and symbol_change > 0 else ("#dc2626" if symbol_change and symbol_change < 0 else "#64748b")

            # 获取趋势
            trend = ""
            if tracker:
                trend_data = tracker.get_symbol_trend(symbol, n=3)
                if len(trend_data) >= 2:
                    prev_weight = trend_data[-2]['weight']
                    change = weight - prev_weight
                    change_pct = (change / prev_weight * 100) if prev_weight > 0 else 0
                    if change_pct > 10:
                        trend = "🚀"
                    elif change_pct > 5:
                        trend = "📈"
                    elif change_pct < -10:
                        trend = "📉"
                    elif change_pct < -5:
                        trend = "🔻"

            html += f"""
                <div style="
                    background: {bg_color};
                    border: 1px solid {border_color};
                    border-radius: 6px;
                    padding: 4px 8px;
                    font-size: 11px;
                    display: flex;
                    align-items: center;
                    gap: 4px;
                    min-width: 0;
                ">
                    <span style="color: #64748b; font-weight: 600;">{i}.</span>
                    <span style="font-weight: 600; color: #1e293b; max-width: 60px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{symbol}</span>
                    <span style="color: #475569; max-width: 50px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{symbol_name}</span>
                    {f'<span style="font-size: 10px; color: {change_color}; font-weight: 600; white-space: nowrap;">{change_str}</span>' if change_str else ''}
                    {f'<span style="font-size: 10px;">{trend}</span>' if trend else ''}
                    <span style="color: {color}; font-weight: 600;">{weight:.1f}</span>
                </div>
            """
        html += """
                </div>
            </div>
        """
    html += "</div></div>"
    return html'''

if old_block in content:
    content = content.replace(old_block, new_block)
    with open('deva/naja/attention/ui.py', 'w') as f:
        f.write(content)
    print('✅ 热门股票展示已改为紧凑标签风格')
else:
    print('❌ 未找到目标代码块')