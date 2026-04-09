# coding: utf-8
"""
Attention Kernel 页面演示

展示 Attention Kernel 的四大能力：
1. 聚焦 - QueryState 驱动优先级
2. 清晰 - MultiHead 多头归因
3. 结果 - Bandit 反馈闭环
4. 错误 - AttentionMemory 持久记忆
"""

import time
from deva.page import page, webview
from deva import *
from deva.naja.attention.kernel import (
    AttentionEvent,
    QueryState,
    Encoder,
    MultiHeadAttention,
    AttentionKernel,
    get_default_heads,
)
from deva.naja.attention.ui_components.kernel import (
    render_kernel_dashboard,
    render_attention_flow_diagram,
)


def create_kernel():
    encoder = Encoder()
    heads = get_default_heads()
    multi_head = MultiHeadAttention(heads)
    return AttentionKernel(encoder, multi_head)


kernel = create_kernel()
Q = QueryState()
Q.market_regime = {"type": "trend"}
Q.risk_bias = 0.6
Q.attention_focus = {"market": 0.8, "news": 0.5, "flow": 0.3}


def generate_attention_events():
    events = [
        AttentionEvent("market", {"code": "000001"}, {
            "price_change": 0.05,
            "sentiment": 0.3,
            "volume_spike": 0.4,
            "historical_alpha": 0.6,
            "alpha": 0.7,
            "risk": 0.3,
            "confidence": 0.8
        }, time.time()),
        AttentionEvent("news", {"headline": "央行宣布降息"}, {
            "price_change": 0.0,
            "sentiment": 0.8,
            "volume_spike": 0.5,
            "historical_alpha": 0.3,
            "alpha": 0.6,
            "risk": 0.2,
            "confidence": 0.9
        }, time.time()),
        AttentionEvent("flow", {"direction": "inflow"}, {
            "price_change": 0.02,
            "sentiment": 0.4,
            "volume_spike": 0.9,
            "historical_alpha": 0.7,
            "alpha": 0.85,
            "risk": 0.4,
            "confidence": 0.75
        }, time.time()),
    ]
    return events


def generate_html():
    events = generate_attention_events()
    result = kernel.process(Q, events)

    heads_output = {}
    for head in kernel.multi_head.heads:
        head_result = head.compute(Q, events)
        heads_output[head.name] = head_result

    kernel_state = {
        "query_state": {
            "strategy_state": {"momentum": True, "mean_reversion": False},
            "portfolio_state": {"000001": 1000, "000002": 500},
            "market_regime": Q.market_regime,
            "attention_focus": Q.attention_focus,
            "risk_bias": Q.risk_bias
        },
        "heads_output": heads_output,
        "memory_items": [],
        "feedback_info": {
            "reward": result["confidence"] * 0.1,
            "action": "buy_momentum",
            "last_update": time.time(),
            "total_feedbacks": 42
        }
    }

    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px;">
        <h1 style="color: #00d4ff; text-align: center;">
            🧠 Attention Kernel - 注意力中枢
        </h1>
        <p style="text-align: center; color: #94a3b8;">
            境随心转，执处成真
        </p>

        {render_attention_flow_diagram()}

        <h2 style="color: #fff; border-bottom: 2px solid #00d4ff; padding-bottom: 10px;">
            📊 实时状态
        </h2>

        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px;">
            <div style="background: rgba(0,212,255,0.1); border-radius: 12px; padding: 20px;">
                <h3 style="color: #00d4ff; margin-top: 0;">📍 核心参数</h3>
                <table style="width: 100%; color: #fff;">
                    <tr>
                        <td>市场状态:</td>
                        <td style="color: #4ade80;">{Q.market_regime.get('type', 'unknown').upper()}</td>
                    </tr>
                    <tr>
                        <td>风险偏好:</td>
                        <td>{Q.risk_bias:.2f}</td>
                    </tr>
                    <tr>
                        <td>策略数:</td>
                        <td>{len(Q.strategy_state)}</td>
                    </tr>
                    <tr>
                        <td>持仓数:</td>
                        <td>{len(Q.portfolio_state)}</td>
                    </tr>
                </table>
            </div>

            <div style="background: rgba(74,222,128,0.1); border-radius: 12px; padding: 20px;">
                <h3 style="color: #4ade80; margin-top: 0;">📈 处理结果</h3>
                <table style="width: 100%; color: #fff;">
                    <tr>
                        <td>Alpha:</td>
                        <td style="color: #00d4ff; font-weight: bold;">{result['alpha']:.4f}</td>
                    </tr>
                    <tr>
                        <td>Risk:</td>
                        <td>{result['risk']:.4f}</td>
                    </tr>
                    <tr>
                        <td>Confidence:</td>
                        <td style="color: #fbbf24;">{result['confidence']:.4f}</td>
                    </tr>
                    <tr>
                        <td>事件数:</td>
                        <td>{len(events)}</td>
                    </tr>
                </table>
            </div>
        </div>

        {render_kernel_dashboard(kernel_state)}

        <h2 style="color: #fff; border-bottom: 2px solid #00d4ff; padding-bottom: 10px;">
            🧩 多头注意力详情
        </h2>

        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px;">
            <div style="background: rgba(74,222,128,0.1); border-radius: 8px; padding: 15px;">
                <h4 style="color: #4ade80; margin: 0 0 10px 0;">📈 Market Head</h4>
                <div style="color: #fff;">Alpha: {heads_output.get('market', {}).get('alpha', 0):.4f}</div>
                <div style="color: #94a3b8;">专注价格变化信号</div>
            </div>
            <div style="background: rgba(96,165,250,0.1); border-radius: 8px; padding: 15px;">
                <h4 style="color: #60a5fa; margin: 0 0 10px 0;">📰 News Head</h4>
                <div style="color: #fff;">Alpha: {heads_output.get('news', {}).get('alpha', 0):.4f}</div>
                <div style="color: #94a3b8;">专注情绪和新闻信号</div>
            </div>
            <div style="background: rgba(244,114,182,0.1); border-radius: 8px; padding: 15px;">
                <h4 style="color: #f472b6; margin: 0 0 10px 0;">💧 Flow Head</h4>
                <div style="color: #fff;">Alpha: {heads_output.get('flow', {}).get('alpha', 0):.4f}</div>
                <div style="color: #94a3b8;">专注资金流向信号</div>
            </div>
            <div style="background: rgba(251,191,36,0.1); border-radius: 8px; padding: 15px;">
                <h4 style="color: #fbbf24; margin: 0 0 10px 0;">🎯 Meta Head</h4>
                <div style="color: #fff;">Alpha: {heads_output.get('meta', {}).get('alpha', 0):.4f}</div>
                <div style="color: #94a3b8;">专注历史alpha信号</div>
            </div>
        </div>

        <h2 style="color: #fff; border-bottom: 2px solid #00d4ff; padding-bottom: 10px; margin-top: 30px;">
            💾 注意力记忆
        </h2>

        <div style="background: rgba(168,85,247,0.1); border-radius: 12px; padding: 20px;">
            <div style="color: #64748b; font-size: 14px;">
                记忆功能已移动到 Cognition 系统
            </div>
        </div>

        <div style="margin-top: 30px; padding: 20px; background: rgba(0,0,0,0.3); border-radius: 12px;">
            <h3 style="color: #00d4ff;">🔄 四大能力</h3>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-top: 15px;">
                <div style="padding: 15px; background: rgba(0,212,255,0.1); border-radius: 8px;">
                    <h4 style="color: #00d4ff; margin: 0 0 10px 0;">🎯 聚焦</h4>
                    <p style="color: #94a3b8; margin: 0;">QueryState 驱动优先级</p>
                </div>
                <div style="padding: 15px; background: rgba(74,222,128,0.1); border-radius: 8px;">
                    <h4 style="color: #4ade80; margin: 0 0 10px 0;">🧩 清晰</h4>
                    <p style="color: #94a3b8; margin: 0;">多头归因，可解释</p>
                </div>
                <div style="padding: 15px; background: rgba(168,85,247,0.1); border-radius: 8px;">
                    <h4 style="color: #a855f7; margin: 0 0 10px 0;">🎮 结果</h4>
                    <p style="color: #94a3b8; margin: 0;">Bandit 反馈闭环</p>
                </div>
                <div style="padding: 15px; background: rgba(251,191,36,0.1); border-radius: 8px;">
                    <h4 style="color: #fbbf24; margin: 0 0 10px 0;">💾 错误</h4>
                    <p style="color: #94a3b8; margin: 0;">持久记忆 + 衰减</p>
                </div>
            </div>
        </div>

        <div style="margin-top: 30px; text-align: center; color: #64748b; font-size: 12px;">
            Attention Kernel | 执处成境
        </div>
    </div>
    """

    return html


s_attention = timer(
    func=generate_html,
    start=True,
    name='Attention Kernel',
    interval=1
)

s_attention.webview('/attention')
print("Attention Kernel 页面已启动: http://localhost:9999/attention")

Deva.run()
