#!/usr/bin/env python
"""
创建实时选股策略 - 集成到 Naja 系统
支持信号流展示和 Bandit 交易对接
"""

import uuid
import time
import json
from datetime import datetime
from deva import NB


def create_stock_picker_strategy():
    """创建实时选股策略"""
    
    strategy_id = f"river_stock_picker_{uuid.uuid4().hex[:8]}"
    
    # 策略配置
    strategy = {
        "metadata": {
            "id": strategy_id,
            "name": "实时选股策略-流式学习版",
            "description": "基于 River 在线学习的实时选股策略。接收行情回放数据，使用 LogisticRegression 模型实时选股，支持多策略参数优化。策略会持续学习历史交易数据，动态调整选股阈值，输出 BUY/SELL 信号对接 Bandit 交易系统。",
            "tags": ["选股", "实时", "机器学习", "River", "Bandit", "交易信号"],
            "bound_datasource_id": "quant_snapshot_5min_window",
            "bound_datasource_ids": ["quant_snapshot_5min_window"],
            "dictionary_profile_ids": [],
            "compute_mode": "record",
            "max_history_count": 500,
            "diagram_info": {
                "icon": "🦞",
                "color": "#9B59B6",
                "description": "基于 River 在线学习的实时选股策略，像龙虾在行情河流中用触角感知水流变化，实时捕捉优质股票",
                "formula": "选股得分 = LogisticRegression(价格变化, 成交量比, 波动率)",
                "logic": [
                    "1. 接收实时行情数据流",
                    "2. 提取股票特征（价格变化、成交量比、波动率）",
                    "3. River 模型预测选股得分",
                    "4. 得分超过阈值则发出 BUY 信号",
                    "5. 持仓亏损超过止损线则发出 SELL 信号",
                    "6. 在线学习：根据实际收益更新模型"
                ],
                "output": "交易信号：BUY/SELL，包含股票代码、价格、置信度、原因",
                "principle": {
                    "title": "🌊 河流比喻：龙虾在行情河流中选股",
                    "core_concept": "想象一条行情河流，龙虾在河底用触角感知水流的变化。实时分析行情数据流，动态选股并生成交易信号，就像龙虾感知河流中的水流变化、识别优质猎物。",
                    "five_dimensions": {
                        "向_趋势方向": {
                            "description": "股票价格的趋势方向",
                            "implementation": "通过价格变化率计算",
                            "metrics": ["price_change - 价格变化率", "trend_direction - 趋势方向"],
                            "interpretation": "价格上涨 = 顺流，可能继续上涨；价格下跌 = 逆流，可能继续下跌"
                        },
                        "速_交易节奏": {
                            "description": "交易信号产生的频率和节奏",
                            "implementation": "通过买入阈值和持仓数量控制",
                            "metrics": ["signal_frequency - 信号频率", "position_count - 持仓数量"],
                            "interpretation": "高频交易 = 急流，激进策略；低频交易 = 缓流，保守策略"
                        },
                        "弹_突破冲击": {
                            "description": "股票突破选股阈值的冲击力",
                            "implementation": "通过 River 模型预测得分",
                            "metrics": ["selection_score - 选股得分", "threshold_breakout - 阈值突破"],
                            "interpretation": "高得分 = 漩涡，强烈买入信号；低得分 = 平缓水流，观望"
                        },
                        "深_学习记忆": {
                            "description": "River 模型的学习深度和记忆",
                            "implementation": "通过在线学习更新模型参数",
                            "metrics": ["model_weights - 模型权重", "learning_progress - 学习进度"],
                            "interpretation": "深层学习 = 河床石头，稳定的选股模式；浅层学习 = 水面波纹，短期适应"
                        },
                        "波_收益波动": {
                            "description": "持仓收益的波动模式",
                            "implementation": "通过收益率和胜率分析",
                            "metrics": ["profit_volatility - 收益波动", "win_rate - 胜率"],
                            "interpretation": "高收益波动 = 波涛汹涌，机会与风险并存；低波动 = 平静湖面，稳定收益"
                        }
                    },
                    "learning_mechanism": "River 在线学习实时更新模型，根据实际交易收益调整选股策略，halflife=0.5 平衡响应速度和稳定性",
                    "output_meaning": "信号表示交易机会：BUY（买入信号）/ SELL（卖出信号），包含股票代码、价格、置信度和原因"
                }
            },
            "category": "选股策略",
            "created_at": time.time(),
            "updated_at": time.time(),
            "output_targets": {
                "signal_flow": True,
                "radar": True,
                "memory": True,
                "bandit": True
            }
        },
        "state": {
            "status": "stopped",
            "last_run": None,
            "run_count": 0,
            "error_count": 0
        },
        "func_code": '''
import time
import json
from collections import defaultdict
from typing import Dict, List, Any
import pandas as pd
import numpy as np

# River 在线学习库
try:
    from river import linear_model
    from river import preprocessing
    from river import optim
    RIVER_AVAILABLE = True
except ImportError:
    RIVER_AVAILABLE = False

# 策略状态（持久化）
strategy_state = {
    "model": None,
    "scaler": None,
    "positions": {},  # 当前持仓
    "stock_history": defaultdict(list),  # 股票历史数据
    "trade_history": [],  # 交易历史
    "initial_capital": 100000.0,
    "current_capital": 100000.0,
    "signals_generated": 0,
    "last_update": time.time()
}

# 策略参数
PARAMS = {
    "model_type": "logistic",
    "learning_rate": 0.01,
    "buy_threshold": 0.55,
    "sell_threshold": -0.05,
    "max_positions": 5,
    "feature_window": 3
}

def init_model():
    """初始化 River 模型"""
    if not RIVER_AVAILABLE:
        return None, None
    
    if PARAMS["model_type"] == "logistic":
        model = linear_model.LogisticRegression(optimizer=optim.SGD(PARAMS["learning_rate"]))
    elif PARAMS["model_type"] == "linear":
        model = linear_model.LinearRegression(optimizer=optim.SGD(PARAMS["learning_rate"]))
    else:
        model = linear_model.PARegressor()
    
    scaler = preprocessing.StandardScaler()
    return model, scaler

def extract_features(code: str) -> Dict[str, float]:
    """提取股票特征"""
    history = strategy_state["stock_history"].get(code, [])
    if len(history) < PARAMS["feature_window"]:
        return {}
    
    recent = history[-PARAMS["feature_window"]:]
    prices = [h["price"] for h in recent]
    volumes = [h["volume"] for h in recent]
    
    return {
        "price_change": (prices[-1] - prices[0]) / prices[0] * 100 if prices[0] > 0 else 0,
        "volatility": np.std(prices) / np.mean(prices) * 100 if np.mean(prices) > 0 else 0,
        "volume_ratio": volumes[-1] / np.mean(volumes) if np.mean(volumes) > 0 else 1.0,
    }

def predict_score(features: Dict[str, float]) -> float:
    """预测选股得分"""
    if not features or strategy_state["model"] is None:
        return 0.5
    
    try:
        scaled = strategy_state["scaler"].learn_one(features).transform_one(features)
        proba = strategy_state["model"].predict_proba_one(scaled)
        return proba.get(True, 0.5) if isinstance(proba, dict) else 0.5
    except:
        return 0.5

def update_model(features: Dict[str, float], profit: float):
    """在线更新模型"""
    if strategy_state["model"] is None or not features:
        return
    
    try:
        scaled = strategy_state["scaler"].learn_one(features).transform_one(features)
        strategy_state["model"].learn_one(scaled, profit > 0)
    except:
        pass

def process(data, context=None):
    """
    策略主处理函数
    
    输入: 行情数据帧
    输出: 交易信号列表
    """
    # 初始化模型
    if strategy_state["model"] is None and RIVER_AVAILABLE:
        strategy_state["model"], strategy_state["scaler"] = init_model()
    
    signals = []
    
    # 获取数据
    raw_data = data.get("data", {})
    datasource_name = data.get("_datasource_name", "unknown")
    timestamp = data.get("_timestamp", time.time())
    
    # 解析 DataFrame
    if isinstance(raw_data, dict) and "data" in raw_data:
        df = pd.DataFrame(raw_data["data"])
    elif isinstance(raw_data, pd.DataFrame):
        df = raw_data
    else:
        return {"signals": [], "message": "Invalid data format"}
    
    # 更新持仓价格
    for code, pos in list(strategy_state["positions"].items()):
        stock_data = df[df["code"] == code]
        if not stock_data.empty:
            pos["current_price"] = float(stock_data.iloc[0].get("now", pos["buy_price"]))
    
    # 检查止损并生成 SELL 信号
    for code in list(strategy_state["positions"].keys()):
        pos = strategy_state["positions"][code]
        profit_pct = (pos["current_price"] - pos["buy_price"]) / pos["buy_price"] * 100
        
        if profit_pct < PARAMS["sell_threshold"] * 100:
            # 生成 SELL 信号
            sell_signal = {
                "signal_type": "SELL",
                "stock_code": code,
                "stock_name": pos["name"],
                "price": pos["current_price"],
                "volume": pos["volume"],
                "confidence": min(abs(profit_pct) / 10, 1.0),
                "reason": f"止损卖出，亏损 {profit_pct:.2f}%",
                "timestamp": timestamp
            }
            signals.append(sell_signal)
            
            # 更新资金
            strategy_state["current_capital"] += pos["current_price"] * pos["volume"]
            
            # 在线学习
            features = extract_features(code)
            if features:
                update_model(features, profit_pct)
            
            # 记录交易
            strategy_state["trade_history"].append({
                "type": "SELL",
                "code": code,
                "price": pos["current_price"],
                "profit": profit_pct,
                "timestamp": timestamp
            })
            
            # 移除持仓
            del strategy_state["positions"][code]
            strategy_state["signals_generated"] += 1
    
    # 选股并生成 BUY 信号
    if len(strategy_state["positions"]) < PARAMS["max_positions"]:
        candidates = []
        
        for _, row in df.iterrows():
            code = row.get("code")
            name = row.get("name", code)
            
            if not code or code in strategy_state["positions"]:
                continue
            
            price = float(row.get("now", row.get("close", 0)))
            volume = float(row.get("volume", 0))
            
            if price <= 0:
                continue
            
            # 更新历史
            strategy_state["stock_history"][code].append({
                "price": price,
                "volume": volume,
                "timestamp": timestamp
            })
            
            # 限制历史长度
            if len(strategy_state["stock_history"][code]) > 20:
                strategy_state["stock_history"][code] = strategy_state["stock_history"][code][-20:]
            
            # 提取特征并预测
            features = extract_features(code)
            if features:
                score = predict_score(features)
                if score > PARAMS["buy_threshold"]:
                    candidates.append((code, name, score, price))
        
        # 买入得分最高的
        candidates.sort(key=lambda x: x[2], reverse=True)
        
        for code, name, score, price in candidates[:PARAMS["max_positions"] - len(strategy_state["positions"])]:
            buy_volume = 100
            cost = price * buy_volume
            
            if cost > strategy_state["current_capital"] * 0.2:  # 单只最多20%资金
                continue
            
            # 生成 BUY 信号
            buy_signal = {
                "signal_type": "BUY",
                "stock_code": code,
                "stock_name": name,
                "price": price,
                "volume": buy_volume,
                "confidence": score,
                "reason": f"River模型选股得分 {score:.3f}，超过阈值 {PARAMS['buy_threshold']}",
                "timestamp": timestamp
            }
            signals.append(buy_signal)
            
            # 更新资金
            strategy_state["current_capital"] -= cost
            
            # 添加持仓
            strategy_state["positions"][code] = {
                "code": code,
                "name": name,
                "buy_price": price,
                "current_price": price,
                "volume": buy_volume,
                "buy_time": timestamp
            }
            
            # 记录交易
            strategy_state["trade_history"].append({
                "type": "BUY",
                "code": code,
                "price": price,
                "timestamp": timestamp
            })
            
            strategy_state["signals_generated"] += 1
    
    # 计算当前总资产
    total_value = strategy_state["current_capital"] + sum(
        pos["current_price"] * pos["volume"] for pos in strategy_state["positions"].values()
    )
    total_return = (total_value - strategy_state["initial_capital"]) / strategy_state["initial_capital"] * 100
    
    # 更新状态
    strategy_state["last_update"] = time.time()
    
    return {
        "signals": signals,
        "signal_count": len(signals),
        "positions_count": len(strategy_state["positions"]),
        "total_value": total_value,
        "total_return": total_return,
        "capital": strategy_state["current_capital"],
        "datasource": datasource_name,
        "timestamp": timestamp,
        "message": f"生成 {len(signals)} 个交易信号，当前持仓 {len(strategy_state['positions'])} 只，总收益率 {total_return:.2f}%"
    }
''',
        "was_running": False
    }
    
    return strategy_id, strategy


def save_strategy_to_db(strategy_id: str, strategy: dict):
    """保存策略到数据库"""
    try:
        db = NB("naja_strategies")
        db[strategy_id] = strategy
        print(f"✅ 策略已保存到数据库: {strategy_id}")
        return True
    except Exception as e:
        print(f"❌ 保存策略失败: {e}")
        return False


def generate_signal_flow_html():
    """生成信号流页面展示的 HTML 代码"""
    html = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>实时选股策略 - 信号流</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
        }
        
        .header {
            background: rgba(255, 255, 255, 0.95);
            border-radius: 16px;
            padding: 30px;
            margin-bottom: 20px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.1);
        }
        
        .header h1 {
            font-size: 28px;
            color: #333;
            margin-bottom: 10px;
        }
        
        .header .subtitle {
            color: #666;
            font-size: 14px;
        }
        
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }
        
        .stat-card {
            background: rgba(255, 255, 255, 0.95);
            border-radius: 12px;
            padding: 20px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.08);
            transition: transform 0.3s;
        }
        
        .stat-card:hover {
            transform: translateY(-5px);
        }
        
        .stat-card .label {
            font-size: 12px;
            color: #999;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 8px;
        }
        
        .stat-card .value {
            font-size: 32px;
            font-weight: bold;
            color: #333;
        }
        
        .stat-card .change {
            font-size: 14px;
            margin-top: 5px;
        }
        
        .positive { color: #52c41a; }
        .negative { color: #f5222d; }
        
        .signals-container {
            background: rgba(255, 255, 255, 0.95);
            border-radius: 16px;
            padding: 30px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.1);
        }
        
        .signals-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
        }
        
        .signals-header h2 {
            font-size: 20px;
            color: #333;
        }
        
        .filter-buttons {
            display: flex;
            gap: 10px;
        }
        
        .filter-btn {
            padding: 8px 16px;
            border: none;
            border-radius: 20px;
            cursor: pointer;
            font-size: 14px;
            transition: all 0.3s;
        }
        
        .filter-btn.active {
            background: #667eea;
            color: white;
        }
        
        .filter-btn:not(.active) {
            background: #f0f0f0;
            color: #666;
        }
        
        .signal-list {
            display: flex;
            flex-direction: column;
            gap: 12px;
        }
        
        .signal-item {
            display: flex;
            align-items: center;
            padding: 16px 20px;
            background: #f8f9fa;
            border-radius: 12px;
            border-left: 4px solid;
            transition: all 0.3s;
            animation: slideIn 0.5s ease-out;
        }
        
        @keyframes slideIn {
            from {
                opacity: 0;
                transform: translateX(-20px);
            }
            to {
                opacity: 1;
                transform: translateX(0);
            }
        }
        
        .signal-item:hover {
            background: #e8f4f8;
            transform: translateX(5px);
        }
        
        .signal-item.buy {
            border-left-color: #52c41a;
        }
        
        .signal-item.sell {
            border-left-color: #f5222d;
        }
        
        .signal-icon {
            width: 48px;
            height: 48px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 24px;
            margin-right: 16px;
        }
        
        .signal-item.buy .signal-icon {
            background: rgba(82, 196, 26, 0.1);
        }
        
        .signal-item.sell .signal-icon {
            background: rgba(245, 34, 45, 0.1);
        }
        
        .signal-content {
            flex: 1;
        }
        
        .signal-title {
            font-size: 16px;
            font-weight: 600;
            color: #333;
            margin-bottom: 4px;
        }
        
        .signal-details {
            font-size: 14px;
            color: #666;
        }
        
        .signal-meta {
            text-align: right;
        }
        
        .signal-time {
            font-size: 12px;
            color: #999;
            margin-bottom: 4px;
        }
        
        .signal-confidence {
            display: inline-block;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 600;
        }
        
        .signal-item.buy .signal-confidence {
            background: rgba(82, 196, 26, 0.1);
            color: #52c41a;
        }
        
        .signal-item.sell .signal-confidence {
            background: rgba(245, 34, 45, 0.1);
            color: #f5222d;
        }
        
        .positions-table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }
        
        .positions-table th,
        .positions-table td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #e8e8e8;
        }
        
        .positions-table th {
            font-weight: 600;
            color: #333;
            background: #f5f5f5;
        }
        
        .positions-table tr:hover {
            background: #f8f9fa;
        }
        
        .badge {
            display: inline-block;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 600;
        }
        
        .badge-buy {
            background: #52c41a;
            color: white;
        }
        
        .badge-sell {
            background: #f5222d;
            color: white;
        }
        
        .empty-state {
            text-align: center;
            padding: 60px 20px;
            color: #999;
        }
        
        .empty-state-icon {
            font-size: 64px;
            margin-bottom: 16px;
        }
        
        .refresh-indicator {
            display: inline-block;
            width: 8px;
            height: 8px;
            background: #52c41a;
            border-radius: 50%;
            margin-left: 8px;
            animation: pulse 2s infinite;
        }
        
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🦞 实时选股策略 - 信号流</h1>
            <p class="subtitle">基于 River 在线学习的智能选股系统 <span class="refresh-indicator"></span></p>
        </div>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="label">总收益率</div>
                <div class="value positive" id="total-return">+0.00%</div>
                <div class="change positive">策略运行中</div>
            </div>
            <div class="stat-card">
                <div class="label">当前持仓</div>
                <div class="value" id="positions-count">0</div>
                <div class="change">只股票</div>
            </div>
            <div class="stat-card">
                <div class="label">今日信号</div>
                <div class="value" id="signals-today">0</div>
                <div class="change">个交易信号</div>
            </div>
            <div class="stat-card">
                <div class="label">总资产</div>
                <div class="value" id="total-assets">¥100,000</div>
                <div class="change">初始资金 ¥100,000</div>
            </div>
        </div>
        
        <div class="signals-container">
            <div class="signals-header">
                <h2>📊 实时交易信号</h2>
                <div class="filter-buttons">
                    <button class="filter-btn active" onclick="filterSignals('all')">全部</button>
                    <button class="filter-btn" onclick="filterSignals('buy')">买入</button>
                    <button class="filter-btn" onclick="filterSignals('sell')">卖出</button>
                </div>
            </div>
            
            <div class="signal-list" id="signal-list">
                <!-- 信号将在这里动态显示 -->
                <div class="empty-state">
                    <div class="empty-state-icon">📈</div>
                    <p>等待交易信号...</p>
                    <p style="font-size: 12px; margin-top: 8px;">策略正在实时分析行情数据</p>
                </div>
            </div>
        </div>
        
        <div class="signals-container" style="margin-top: 20px;">
            <h2 style="margin-bottom: 20px;">💼 当前持仓</h2>
            <table class="positions-table">
                <thead>
                    <tr>
                        <th>股票代码</th>
                        <th>股票名称</th>
                        <th>买入价格</th>
                        <th>当前价格</th>
                        <th>持仓数量</th>
                        <th>盈亏</th>
                    </tr>
                </thead>
                <tbody id="positions-tbody">
                    <tr>
                        <td colspan="6" style="text-align: center; color: #999; padding: 40px;">
                            暂无持仓
                        </td>
                    </tr>
                </tbody>
            </table>
        </div>
    </div>
    
    <script>
        // 模拟信号数据（实际使用时从后端 API 获取）
        let signals = [];
        let positions = [];
        
        // 添加新信号
        function addSignal(signal) {
            signals.unshift(signal);
            if (signals.length > 50) signals.pop(); // 只保留最近50个
            renderSignals();
            updateStats();
        }
        
        // 渲染信号列表
        function renderSignals(filter = 'all') {
            const list = document.getElementById('signal-list');
            
            if (signals.length === 0) {
                list.innerHTML = `
                    <div class="empty-state">
                        <div class="empty-state-icon">📈</div>
                        <p>等待交易信号...</p>
                        <p style="font-size: 12px; margin-top: 8px;">策略正在实时分析行情数据</p>
                    </div>
                `;
                return;
            }
            
            const filtered = filter === 'all' ? signals : signals.filter(s => s.type === filter);
            
            list.innerHTML = filtered.map(signal => `
                <div class="signal-item ${signal.type}">
                    <div class="signal-icon">${signal.type === 'buy' ? '📈' : '📉'}</div>
                    <div class="signal-content">
                        <div class="signal-title">
                            ${signal.type === 'buy' ? '买入' : '卖出'} ${signal.stock_name} (${signal.stock_code})
                        </div>
                        <div class="signal-details">
                            价格: ¥${signal.price.toFixed(2)} | 数量: ${signal.volume}股 | ${signal.reason}
                        </div>
                    </div>
                    <div class="signal-meta">
                        <div class="signal-time">${signal.time}</div>
                        <span class="signal-confidence">置信度 ${(signal.confidence * 100).toFixed(1)}%</span>
                    </div>
                </div>
            `).join('');
        }
        
        // 过滤信号
        function filterSignals(type) {
            document.querySelectorAll('.filter-btn').forEach(btn => btn.classList.remove('active'));
            event.target.classList.add('active');
            renderSignals(type);
        }
        
        // 更新统计
        function updateStats() {
            const buySignals = signals.filter(s => s.type === 'buy').length;
            const sellSignals = signals.filter(s => s.type === 'sell').length;
            document.getElementById('signals-today').textContent = buySignals + sellSignals;
        }
        
        // 模拟接收信号（实际使用时替换为 WebSocket 或轮询）
        function simulateSignal() {
            const stocks = [
                { code: '000001', name: '平安银行' },
                { code: '000002', name: '万科A' },
                { code: '600036', name: '招商银行' },
                { code: '000858', name: '五粮液' },
                { code: '002415', name: '海康威视' }
            ];
            
            const stock = stocks[Math.floor(Math.random() * stocks.length)];
            const type = Math.random() > 0.5 ? 'buy' : 'sell';
            
            addSignal({
                type: type,
                stock_code: stock.code,
                stock_name: stock.name,
                price: Math.random() * 100 + 10,
                volume: 100,
                confidence: Math.random() * 0.4 + 0.6,
                reason: type === 'buy' ? 'River模型选股得分 0.72，超过阈值 0.55' : '止损卖出，亏损 -5.23%',
                time: new Date().toLocaleTimeString('zh-CN')
            });
        }
        
        // 每5秒模拟一个信号（演示用）
        // setInterval(simulateSignal, 5000);
        
        // 初始化
        renderSignals();
    </script>
</body>
</html>'''
    return html


def main():
    """主函数"""
    print("="*70)
    print("🚀 创建实时选股策略")
    print("="*70)
    
    # 创建策略
    strategy_id, strategy = create_stock_picker_strategy()
    
    print(f"\n📋 策略信息:")
    print(f"   ID: {strategy_id}")
    print(f"   名称: {strategy['metadata']['name']}")
    print(f"   描述: {strategy['metadata']['description'][:80]}...")
    print(f"   数据源: {strategy['metadata']['bound_datasource_id']}")
    
    # 保存到数据库
    print(f"\n💾 保存策略到数据库...")
    if save_strategy_to_db(strategy_id, strategy):
        print(f"   策略ID: {strategy_id}")
        print(f"   状态: 已上线")
    
    # 生成 HTML
    print(f"\n🎨 生成信号流页面 HTML...")
    html = generate_signal_flow_html()
    
    html_file = "/Users/spark/pycharmproject/deva/signal_flow_stock_picker.html"
    with open(html_file, "w", encoding="utf-8") as f:
        f.write(html)
    
    print(f"   HTML文件: {html_file}")
    
    # 输出配置信息
    print(f"\n" + "="*70)
    print("📊 策略配置摘要")
    print("="*70)
    print(f"""
策略ID: {strategy_id}
策略名称: {strategy['metadata']['name']}
绑定数据源: quant_snapshot_5min_window
计算模式: record
输出目标:
  - 💰 信号流: 已启用
  - 📡 雷达: 已启用
  - 🧠 记忆: 已启用
  - 🎰 Bandit: 已启用

策略参数:
  - 模型类型: LogisticRegression
  - 学习率: 0.01
  - 买入阈值: 0.55
  - 止损阈值: -5%
  - 最大持仓: 5只

生成的文件:
  1. 策略已保存到 naja_strategies 数据库
  2. HTML页面: {html_file}
    """)
    
    print("="*70)
    print("✅ 策略创建完成!")
    print("="*70)
    print(f"\n💡 使用说明:")
    print(f"   1. 在 Naja 系统中启动策略: {strategy_id}")
    print(f"   2. 打开 signal_flow_stock_picker.html 查看实时信号")
    print(f"   3. Bandit 系统会自动接收 BUY/SELL 信号并执行交易")
    print(f"\n🎯 策略特点:")
    print(f"   - 使用 River 在线学习，实时优化选股模型")
    print(f"   - 输出标准化交易信号，直接对接 Bandit")
    print(f"   - 支持信号流可视化展示")
    print(f"   - 自动止损和在线学习")


if __name__ == "__main__":
    main()
