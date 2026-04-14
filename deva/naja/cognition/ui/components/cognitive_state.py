"""认知状态可视化组件"""

from typing import Dict, Any, List
from datetime import datetime

from pywebio.output import put_html, put_markdown, put_table, put_buttons
from pywebio.session import run_js

from deva.naja.cognition.bridge import get_cognition_bridge


def render_cognitive_state(ui):
    """渲染认知状态可视化组件"""
    bridge = get_cognition_bridge()
    
    ui._put_html("""
    <div style="
        background: linear-gradient(135deg, rgba(236,72,153,0.1), rgba(239,68,68,0.1));
        border: 1px solid rgba(236,72,153,0.2);
        border-radius: 12px;
        padding: 16px;
        margin: 16px 0;
    ">
        <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 12px;">
            <span style="font-size: 18px;">📊</span>
            <span style="font-size: 14px; font-weight: 600; color: #f472b6;">认知状态可视化</span>
        </div>
        <div style="font-size: 12px; color: #94a3b8; margin-bottom: 16px;">
            实时展示认知状态、历史变化趋势和交易影响
        </div>
    """)
    
    # 状态类型选择器
    state_types = [
        {"value": "narratives", "label": "叙事状态"},
        {"value": "liquidity", "label": "流动性状态"},
        {"value": "topics", "label": "主题状态"},
        {"value": "drift", "label": "漂移检测"},
        {"value": "merrill_clock", "label": "美林时钟"},
        {"value": "cross_signal", "label": "跨信号分析"},
        {"value": "first_principles", "label": "第一性原理"},
        {"value": "awakened_alaya", "label": "觉醒阿赖耶"},
    ]
    
    # 状态类型选择器
    ui._put_html("""
    <div style="margin-bottom: 16px;">
        <label style="font-size: 12px; color: #94a3b8; margin-right: 8px;">选择状态类型:</label>
        <select id="state_type_selector" style="
            background: #1e293b;
            border: 1px solid #475569;
            border-radius: 6px;
            color: #e2e8f0;
            padding: 4px 8px;
            font-size: 12px;
        ">
    """)
    
    for state_type in state_types:
        ui._put_html(f"<option value='{state_type['value']}'>{state_type['label']}</option>")
    
    ui._put_html("""
        </select>
        <button onclick="loadStateData()" style="
            background: linear-gradient(135deg, #ec4899, #ef4444);
            color: white;
            border: none;
            border-radius: 6px;
            padding: 4px 12px;
            font-size: 12px;
            margin-left: 8px;
            cursor: pointer;
        ">加载数据</button>
    </div>
    """)
    
    # 状态展示区域
    ui._put_html('<div id="state_content" style="margin-bottom: 20px;">')
    ui._put_html('<div style="text-align: center; color: #94a3b8; font-size: 12px;">请选择状态类型并点击加载数据</div>')
    ui._put_html('</div>')
    
    # JavaScript 代码
    ui._put_html("""
    <script>
        async function loadStateData() {
            const stateType = document.getElementById('state_type_selector').value;
            const contentDiv = document.getElementById('state_content');
            
            contentDiv.innerHTML = '<div style="text-align: center; color: #94a3b8; font-size: 12px;">加载中...</div>';
            
            try {
                // 模拟 API 调用，实际项目中可以使用 pywebio 的通讯机制
                await new Promise(resolve => setTimeout(resolve, 500));
                
                // 不同状态类型的展示逻辑
                switch(stateType) {
                    case 'narratives':
                        contentDiv.innerHTML = `
                            <div style="background: #1e293b; border-radius: 8px; padding: 12px;">
                                <div style="font-size: 12px; font-weight: 600; color: #f472b6; margin-bottom: 8px;">当前活跃叙事</div>
                                <div id="narratives_list" style="font-size: 12px; color: #e2e8f0;">加载中...</div>
                            </div>
                        `;
                        break;
                    case 'liquidity':
                        contentDiv.innerHTML = `
                            <div style="background: #1e293b; border-radius: 8px; padding: 12px;">
                                <div style="font-size: 12px; font-weight: 600; color: #f472b6; margin-bottom: 8px;">流动性状态</div>
                                <div id="liquidity_data" style="font-size: 12px; color: #e2e8f0;">加载中...</div>
                            </div>
                        `;
                        break;
                    case 'topics':
                        contentDiv.innerHTML = `
                            <div style="background: #1e293b; border-radius: 8px; padding: 12px;">
                                <div style="font-size: 12px; font-weight: 600; color: #f472b6; margin-bottom: 8px;">活跃主题</div>
                                <div id="topics_list" style="font-size: 12px; color: #e2e8f0;">加载中...</div>
                            </div>
                        `;
                        break;
                    case 'drift':
                        contentDiv.innerHTML = `
                            <div style="background: #1e293b; border-radius: 8px; padding: 12px;">
                                <div style="font-size: 12px; font-weight: 600; color: #f472b6; margin-bottom: 8px;">漂移检测状态</div>
                                <div id="drift_data" style="font-size: 12px; color: #e2e8f0;">加载中...</div>
                            </div>
                        `;
                        break;
                    case 'merrill_clock':
                        contentDiv.innerHTML = `
                            <div style="background: #1e293b; border-radius: 8px; padding: 12px;">
                                <div style="font-size: 12px; font-weight: 600; color: #f472b6; margin-bottom: 8px;">美林时钟状态</div>
                                <div id="merrill_data" style="font-size: 12px; color: #e2e8f0;">加载中...</div>
                            </div>
                        `;
                        break;
                    case 'cross_signal':
                        contentDiv.innerHTML = `
                            <div style="background: #1e293b; border-radius: 8px; padding: 12px;">
                                <div style="font-size: 12px; font-weight: 600; color: #f472b6; margin-bottom: 8px;">跨信号分析</div>
                                <div id="cross_signal_data" style="font-size: 12px; color: #e2e8f0;">加载中...</div>
                            </div>
                        `;
                        break;
                    case 'first_principles':
                        contentDiv.innerHTML = `
                            <div style="background: #1e293b; border-radius: 8px; padding: 12px;">
                                <div style="font-size: 12px; font-weight: 600; color: #f472b6; margin-bottom: 8px;">第一性原理洞察</div>
                                <div id="fp_data" style="font-size: 12px; color: #e2e8f0;">加载中...</div>
                            </div>
                        `;
                        break;
                    case 'awakened_alaya':
                        contentDiv.innerHTML = `
                            <div style="background: #1e293b; border-radius: 8px; padding: 12px;">
                                <div style="font-size: 12px; font-weight: 600; color: #f472b6; margin-bottom: 8px;">觉醒阿赖耶洞察</div>
                                <div id="alaya_data" style="font-size: 12px; color: #e2e8f0;">加载中...</div>
                            </div>
                        `;
                        break;
                }
                
                // 模拟数据加载完成
                await new Promise(resolve => setTimeout(resolve, 500));
                
                // 填充模拟数据
                if (stateType === 'narratives') {
                    document.getElementById('narratives_list').innerHTML = `
                        <ul style="list-style: none; padding: 0; margin: 0;">
                            <li style="padding: 4px 0; border-bottom: 1px solid #334155;">AI 算力需求增长</li>
                            <li style="padding: 4px 0; border-bottom: 1px solid #334155;">半导体行业复苏</li>
                            <li style="padding: 4px 0; border-bottom: 1px solid #334155;">新能源汽车销量增长</li>
                            <li style="padding: 4px 0; border-bottom: 1px solid #334155;">医疗健康创新</li>
                            <li style="padding: 4px 0;">金融科技发展</li>
                        </ul>
                    `;
                } else if (stateType === 'liquidity') {
                    document.getElementById('liquidity_data').innerHTML = `
                        <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px;">
                            <div>
                                <div style="color: #94a3b8;">流动性风险:</div>
                                <div style="font-size: 14px; font-weight: 600;">0.35</div>
                            </div>
                            <div>
                                <div style="color: #94a3b8;">市场流动性:</div>
                                <div style="font-size: 14px; font-weight: 600;">0.65</div>
                            </div>
                        </div>
                        <div style="margin-top: 8px; color: #94a3b8;">行业流动性:</div>
                        <div style="font-size: 11px;">
                            科技: 0.75 | 金融: 0.60 | 医疗: 0.55 | 能源: 0.45
                        </div>
                    `;
                } else if (stateType === 'topics') {
                    document.getElementById('topics_list').innerHTML = `
                        <ul style="list-style: none; padding: 0; margin: 0;">
                            <li style="padding: 4px 0; border-bottom: 1px solid #334155;">人工智能 (热度: 0.92)</li>
                            <li style="padding: 4px 0; border-bottom: 1px solid #334155;">半导体 (热度: 0.85)</li>
                            <li style="padding: 4px 0; border-bottom: 1px solid #334155;">新能源 (热度: 0.78)</li>
                            <li style="padding: 4px 0; border-bottom: 1px solid #334155;">医疗健康 (热度: 0.65)</li>
                            <li style="padding: 4px 0;">金融科技 (热度: 0.60)</li>
                        </ul>
                    `;
                } else {
                    const elementId = stateType === 'drift' ? 'drift_data' : 
                                   stateType === 'merrill_clock' ? 'merrill_data' :
                                   stateType === 'cross_signal' ? 'cross_signal_data' :
                                   stateType === 'first_principles' ? 'fp_data' : 'alaya_data';
                    
                    document.getElementById(elementId).innerHTML = '<div style="color: #94a3b8;">数据加载完成</div>';
                }
                
            } catch (error) {
                contentDiv.innerHTML = `<div style="text-align: center; color: #f87171; font-size: 12px;">加载失败: ${error.message}</div>`;
            }
        }
    </script>
    """)
    
    # 状态历史趋势图
    ui._put_html("""
    <div style="
        background: linear-gradient(135deg, rgba(59,130,246,0.1), rgba(147,51,234,0.1));
        border: 1px solid rgba(59,130,246,0.2);
        border-radius: 12px;
        padding: 16px;
        margin: 16px 0;
    ">
        <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 12px;">
            <span style="font-size: 18px;">📈</span>
            <span style="font-size: 14px; font-weight: 600; color: #93c5fd;">状态变化趋势</span>
        </div>
        <div style="font-size: 12px; color: #94a3b8; margin-bottom: 16px;">
            认知状态历史变化趋势图表
        </div>
        <div style="background: #1e293b; border-radius: 8px; padding: 12px; height: 200px;">
            <div style="display: flex; justify-content: center; align-items: center; height: 100%; color: #94a3b8; font-size: 12px;">
                <span>趋势图表加载中...</span>
            </div>
        </div>
    </div>
    """)
    
    # 交易影响分析
    ui._put_html("""
    <div style="
        background: linear-gradient(135deg, rgba(16,185,129,0.1), rgba(5,150,105,0.1));
        border: 1px solid rgba(16,185,129,0.2);
        border-radius: 12px;
        padding: 16px;
        margin: 16px 0;
    ">
        <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 12px;">
            <span style="font-size: 18px;">💹</span>
            <span style="font-size: 14px; font-weight: 600; color: #6ee7b7;">交易影响分析</span>
        </div>
        <div style="font-size: 12px; color: #94a3b8; margin-bottom: 16px;">
            认知状态对交易决策的影响分析
        </div>
        <div style="background: #1e293b; border-radius: 8px; padding: 12px;">
            <div style="font-size: 12px; color: #e2e8f0; margin-bottom: 8px;">最近交易决策:</div>
            <div style="font-size: 11px; color: #94a3b8; line-height: 1.4;">
                • 决策时间: 2024-01-15 14:30:00<br>
                • 决策类型: 买入<br>
                • 相关认知状态: 流动性风险低 (0.35), 叙事热度高 (0.85)<br>
                • 决策理由: 市场流动性充足，相关叙事热度高，风险可控
            </div>
        </div>
    </div>
    """)
    
    # 历史数据查询
    ui._put_html("""
    <div style="
        background: linear-gradient(135deg, rgba(245,158,11,0.1), rgba(245,158,11,0.1));
        border: 1px solid rgba(245,158,11,0.2);
        border-radius: 12px;
        padding: 16px;
        margin: 16px 0;
    ">
        <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 12px;">
            <span style="font-size: 18px;">📋</span>
            <span style="font-size: 14px; font-weight: 600; color: #fcd34d;">历史数据查询</span>
        </div>
        <div style="font-size: 12px; color: #94a3b8; margin-bottom: 16px;">
            查询历史认知状态数据
        </div>
        <div style="display: flex; gap: 8px; margin-bottom: 12px;">
            <select style="
                background: #1e293b;
                border: 1px solid #475569;
                border-radius: 6px;
                color: #e2e8f0;
                padding: 4px 8px;
                font-size: 12px;
                flex: 1;
            ">
                <option value="24h">最近24小时</option>
                <option value="7d">最近7天</option>
                <option value="30d">最近30天</option>
            </select>
            <button style="
                background: linear-gradient(135deg, #f59e0b, #d97706);
                color: white;
                border: none;
                border-radius: 6px;
                padding: 4px 12px;
                font-size: 12px;
                cursor: pointer;
            ">查询</button>
        </div>
        <div style="background: #1e293b; border-radius: 8px; padding: 12px; max-height: 200px; overflow-y: auto;">
            <div style="font-size: 12px; color: #94a3b8; text-align: center;">请选择时间范围并点击查询</div>
        </div>
    </div>
    """)


# 导出渲染函数
def render_cognitive_state_component(ui):
    """渲染认知状态组件"""
    render_cognitive_state(ui)