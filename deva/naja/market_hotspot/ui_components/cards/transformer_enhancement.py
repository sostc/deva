"""热点系统 UI - Transformer 增强面板"""

import logging
from typing import Dict, Any, List
from deva.naja.register import SR
from deva.naja.market_hotspot.ui_components.styles import (
    GRADIENT_PURPLE, GRADIENT_SUCCESS, GRADIENT_NEUTRAL,
    GRADIENT_WARNING, GRADIENT_DANGER
)

log = logging.getLogger(__name__)


def get_transformer_enhancement_data() -> Dict[str, Any]:
    """获取 Transformer 增强数据"""
    try:
        asys = SR('hotspot_system')
        if asys:
            # 尝试获取全局热点引擎的 Transformer 增强数据
            global_engine = getattr(asys, 'global_hotspot_engine', None)
            if global_engine and hasattr(global_engine, 'transformer_enhancer'):
                enhancer = global_engine.transformer_enhancer
                history = enhancer.get_history()
                if history:
                    last_enhancement = history[-1]
                    return {
                        'predictions': last_enhancement.get('blocks', []),
                        'history_length': len(history),
                        'enhanced': True
                    }
        return {'enhanced': False}
    except Exception as e:
        log.error(f"获取 Transformer 增强数据失败: {e}")
        return {'enhanced': False}


def render_transformer_enhancement_card() -> str:
    """渲染 Transformer 增强面板"""
    data = get_transformer_enhancement_data()
    
    if not data.get('enhanced'):
        return """
        <div style="background: white; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; margin-top: 16px;">
            <div style="font-weight: 600; margin-bottom: 12px; color: #1e293b; display: flex; align-items: center; gap: 8px;">
                🤖 Transformer 增强分析
                <span style="font-size: 11px; color: #64748b; font-weight: normal;">(AI 热点预测)</span>
            </div>
            <div style="color: #64748b; text-align: center; padding: 20px;">
                <div style="font-size: 24px; margin-bottom: 8px;">⚡</div>
                <div>Transformer 增强功能未启用</div>
                <div style="font-size: 12px; margin-top: 4px;">请确保已集成 Transformer 增强模块</div>
            </div>
        </div>
        """
    
    predictions = data.get('predictions', [])
    history_length = data.get('history_length', 0)
    
    # 按预测分数排序
    sorted_predictions = sorted(predictions, key=lambda x: x.get('prediction_score', 0), reverse=True)[:10]
    
    html = f"""
    <div style="background: white; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; margin-top: 16px;">
        <div style="font-weight: 600; margin-bottom: 16px; color: #1e293b; display: flex; align-items: center; gap: 8px;">
            🤖 Transformer 增强分析
            <span style="font-size: 11px; color: #64748b; font-weight: normal;">(AI 热点预测)</span>
            <span style="background: #f3e8ff; color: #7e22ce; padding: 2px 8px; border-radius: 12px; font-size: 10px; font-weight: 600;">
                历史数据: {history_length}
            </span>
        </div>
    """
    
    if sorted_predictions:
        html += f"""
        <div style="margin-bottom: 16px;">
            <div style="font-size: 13px; font-weight: 600; color: #7e22ce; margin-bottom: 8px;">
                📈 热点预测 Top10
            </div>
            <div style="display: flex; flex-direction: column; gap: 8px;">
        """
        
        for pred in sorted_predictions:
            block_id = pred.get('block_id', '未知')
            name = pred.get('name', block_id)
            trend = pred.get('trend', 'unknown')
            confidence = pred.get('confidence', 0)
            prediction_score = pred.get('prediction_score', 0)
            
            if trend == 'up':
                trend_emoji = '📈'
                trend_color = '#16a34a'
                trend_bg = '#f0fdf4'
            else:
                trend_emoji = '📉'
                trend_color = '#dc2626'
                trend_bg = '#fef2f2'
            
            confidence_bar = min(confidence * 100, 100)
            
            html += f"""
            <div style="background: #f8fafc; border-radius: 8px; padding: 12px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                    <div style="font-size: 14px; font-weight: 600; color: #1e293b;">
                        {name}
                    </div>
                    <div style="background: {trend_bg}; color: {trend_color}; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: 600; display: flex; align-items: center; gap: 4px;">
                        {trend_emoji} {trend}
                    </div>
                </div>
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div style="font-size: 12px; color: #64748b;">
                        预测分数: <strong>{prediction_score:.3f}</strong>
                    </div>
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <div style="font-size: 11px; color: #64748b;">
                            置信度: {confidence:.2f}
                        </div>
                        <div style="width: 80px; height: 6px; background: #e2e8f0; border-radius: 3px; overflow: hidden;">
                            <div style="width: {confidence_bar}%; height: 100%; background: {trend_color}; border-radius: 3px;"></div>
                        </div>
                    </div>
                </div>
            </div>
            """
        
        html += """
            </div>
        </div>
        """
    else:
        html += """
        <div style="background: #f8fafc; border-radius: 8px; padding: 24px; text-align: center; color: #64748b;">
            <div style="font-size: 24px; margin-bottom: 8px;">📊</div>
            <div>暂无预测数据</div>
            <div style="font-size: 12px; margin-top: 4px;">等待市场数据输入...</div>
        </div>
        """
    
    html += """
    <div style="border-top: 1px solid #e2e8f0; padding-top: 12px; margin-top: 12px;">
        <div style="font-size: 12px; color: #64748b; line-height: 1.4;">
            <strong>🤖 Transformer 增强功能:</strong><br>
            • 使用多头自注意力机制分析题材关系<br>
            • 预测热点演变趋势<br>
            • 识别题材间的关联性<br>
            • 提供更准确的市场热点判断
        </div>
    </div>
    </div>
    """
    
    return html
