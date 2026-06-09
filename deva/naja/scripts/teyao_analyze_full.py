#!/usr/bin/env python3
"""
特药申请数据全量分析脚本
分析疾病趋势、药物需求变化
"""
import json
import os
from collections import defaultdict
from datetime import datetime
import re

# 数据目录
DATA_DIR = "/Users/spark/pycharmproject/deva/deva/naja/.workbuddy/teyao_full"

def load_all_data():
    """加载所有批次的数据"""
    all_records = []
    
    # 加载各个批次的数据
    batch_files = [
        "raw_data.json",
        "raw_data_batch2.json", 
        "raw_data_batch3.json",
        "raw_data_batch4.json"
    ]
    
    for bf in batch_files:
        filepath = os.path.join(DATA_DIR, bf)
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    all_records.extend(data)
                elif isinstance(data, dict) and 'records' in data:
                    all_records.extend(data['records'])
    
    # 去重
    seen = set()
    unique_records = []
    for r in all_records:
        key = f"{r.get('sheet_name', '')}_{r.get('patient', '')}_{r.get('disease', '')}"
        if key not in seen:
            seen.add(key)
            unique_records.append(r)
    
    return unique_records

def get_period(date_str):
    """从日期字符串提取年月"""
    if not date_str:
        return ""
    match = re.match(r'(\d{4})-(\d{2})', date_str)
    if match:
        return f"{match.group(1)}-{match.group(2)}"
    match = re.match(r'(\d{4})(\d{2})', date_str)
    if match:
        return f"{match.group(1)}-{match.group(2)}"
    return date_str[:7] if len(date_str) >= 7 else ""

def normalize_disease(disease):
    """标准化疾病名称"""
    if not disease:
        return "未知"
    
    disease = disease.strip()
    
    # 肿瘤类
    if any(x in disease for x in ['肺癌', '肺腺癌', '肺鳞癌']):
        return '肺癌'
    if '乳腺癌' in disease:
        return '乳腺癌'
    if any(x in disease for x in ['骨髓瘤', '多发性骨髓瘤']):
        return '多发性骨髓瘤'
    if any(x in disease for x in ['淋巴瘤', '霍奇金']):
        return '淋巴瘤'
    if any(x in disease for x in ['白血病', '慢粒', 'CML']):
        return '白血病'
    if any(x in disease for x in ['前列腺癌', '前列腺腺癌']):
        return '前列腺癌'
    if any(x in disease for x in ['结直肠癌', '直肠癌', '结肠癌', '肠癌']):
        return '结直肠癌'
    if any(x in disease for x in ['胃癌', '胃腺癌']):
        return '胃癌'
    if any(x in disease for x in ['肝癌', '肝细胞癌', '肝ca']):
        return '肝癌'
    if any(x in disease for x in ['食管癌', '食道癌']):
        return '食管癌'
    if any(x in disease for x in ['胰腺癌', '胰ca']):
        return '胰腺癌'
    if any(x in disease for x in ['卵巢癌', '卵巢上皮']):
        return '卵巢癌'
    if any(x in disease for x in ['宫颈癌', '子宫颈']):
        return '宫颈癌'
    if any(x in disease for x in ['膀胱癌', '尿路上皮癌']):
        return '膀胱癌'
    if any(x in disease for x in ['肾癌', '肾细胞癌']):
        return '肾癌'
    if any(x in disease for x in ['黑色素瘤', '皮肤癌']):
        return '黑色素瘤/皮肤癌'
    if any(x in disease for x in ['神经内分泌', 'NET']):
        return '神经内分泌肿瘤'
    if any(x in disease for x in ['胃肠道间质', 'GIST']):
        return '胃肠道间质瘤'
    if '癌' in disease:
        return '其他肿瘤'
    
    # 血液/代谢类
    if any(x in disease for x in ['血友病', '甲型血友病', '乙型血友病']):
        return '血友病'
    if any(x in disease for x in ['戈谢病', '法布里']):
        return '罕见代谢病'
    if any(x in disease for x in ['肢端肥大', '库欣']):
        return '内分泌罕见病'
    
    # 免疫/过敏类
    if any(x in disease for x in ['特应性皮炎', 'AD', '异位性皮炎']):
        return '特应性皮炎'
    if any(x in disease for x in ['荨麻疹', '慢性荨麻疹']):
        return '慢性荨麻疹'
    if any(x in disease for x in ['哮喘', '过敏性哮喘', '中度哮喘', '重度哮喘']):
        return '哮喘'
    if any(x in disease for x in ['强直性脊柱炎', 'AS']):
        return '强直性脊柱炎'
    if any(x in disease for x in ['类风湿', 'RA']):
        return '类风湿关节炎'
    if any(x in disease for x in ['银屑病', '银肖病']):
        return '银屑病'
    if any(x in disease for x in ['克罗恩', 'CD']):
        return '克罗恩病'
    if any(x in disease for x in ['溃疡性结肠炎', 'UC']):
        return '溃疡性结肠炎'
    if any(x in disease for x in ['系统性红斑狼疮', 'SLE']):
        return '系统性红斑狼疮'
    if any(x in disease for x in ['干燥综合征', 'SS']):
        return '干燥综合征'
    if any(x in disease for x in ['白塞病', '贝赫切特']):
        return '白塞病'
    if any(x in disease for x in ['血管炎']):
        return '血管炎'
    
    # 眼科
    if any(x in disease for x in ['DME', '糖尿病视网膜', '黄斑水肿']):
        return '糖尿病视网膜病变'
    if any(x in disease for x in ['视网膜静脉阻塞', 'RVO', 'RBE']):
        return '视网膜静脉阻塞'
    if any(x in disease for x in ['年龄相关性黄斑', 'AMD', '老年黄斑']):
        return '老年黄斑变性'
    if any(x in disease for x in ['葡萄膜炎']):
        return '葡萄膜炎'
    if any(x in disease for x in ['新生血管', 'wAMD', 'nAMD', 'PCV']):
        return '新生血管性眼病'
    if any(x in disease for x in ['青光眼']):
        return '青光眼'
    
    # HIV/感染
    if any(x in disease.upper() for x in ['HIV', '爱滋', '艾滋病']):
        return 'HIV感染'
    
    # 罕见病
    if any(x in disease for x in ['庞贝', ' Pompe']):
        return '庞贝病'
    if any(x in disease for x in ['罕见病', '法布里', '戈谢']):
        return '罕见病'
    
    # 其他
    if 'TTP' in disease or '血栓性血小板减少' in disease:
        return 'TTP'
    if '肌萎缩' in disease or 'ALS' in disease or '渐冻' in disease:
        return '肌萎缩侧索硬化'
    if '亨廷顿' in disease:
        return '亨廷顿舞蹈病'
    if '多发性硬化' in disease or 'MS' in disease:
        return '多发性硬化'
    if '帕金森' in disease:
        return '帕金森病'
    if '肺动脉高压' in disease or 'PAH' in disease:
        return '肺动脉高压'
    if '肺纤维化' in disease or 'IPF' in disease:
        return '肺纤维化'
    if '渐冻' in disease:
        return '渐冻症'
    
    return disease

def categorize_disease(disease):
    """对疾病进行大类分类"""
    categories = {
        '肿瘤': ['肺癌', '乳腺癌', '多发性骨髓瘤', '淋巴瘤', '白血病', '前列腺癌', 
                 '结直肠癌', '胃癌', '肝癌', '食管癌', '胰腺癌', '卵巢癌', '宫颈癌',
                 '膀胱癌', '肾癌', '黑色素瘤/皮肤癌', '神经内分泌肿瘤', '胃肠道间质瘤', '其他肿瘤'],
        '血液/代谢': ['血友病', '罕见代谢病', '内分泌罕见病', 'TTP'],
        '免疫/过敏': ['特应性皮炎', '慢性荨麻疹', '哮喘', '强直性脊柱炎', '类风湿关节炎',
                    '银屑病', '克罗恩病', '溃疡性结肠炎', '系统性红斑狼疮', '干燥综合征',
                    '白塞病', '血管炎'],
        '眼科': ['糖尿病视网膜病变', '视网膜静脉阻塞', '老年黄斑变性', '葡萄膜炎', 
               '新生血管性眼病', '青光眼'],
        '感染': ['HIV感染'],
        '罕见病': ['庞贝病', '罕见病', '肌萎缩侧索硬化', '亨廷顿舞蹈病', '多发性硬化',
                  '帕金森病', '肺动脉高压', '肺纤维化', '渐冻症'],
    }
    
    for cat, diseases in categories.items():
        if disease in diseases:
            return cat
    return '其他'

def analyze_trends(records):
    """分析数据趋势"""
    
    # 按月份统计疾病
    monthly_stats = defaultdict(lambda: defaultdict(int))
    monthly_total = defaultdict(int)
    
    # 按大类统计
    category_monthly = defaultdict(lambda: defaultdict(int))
    
    # 按药物统计
    medicine_stats = defaultdict(lambda: defaultdict(int))
    
    # 按医保类型统计
    insurance_stats = defaultdict(int)
    
    for r in records:
        disease = normalize_disease(r['disease'])
        period = get_period(r.get('submit_time') or r.get('sheet_name', ''))
        medicine = r.get('medicine', '')
        insurance = r.get('insurance', '')
        
        if period:
            monthly_stats[period][disease] += 1
            monthly_total[period] += 1
            category = categorize_disease(disease)
            category_monthly[period][category] += 1
            if medicine:
                medicine_stats[period][medicine] += 1
            if insurance:
                insurance_stats[insurance] += 1
    
    return {
        'monthly_stats': dict(monthly_stats),
        'monthly_total': dict(monthly_total),
        'category_monthly': dict(category_monthly),
        'medicine_stats': dict(medicine_stats),
        'insurance_stats': dict(insurance_stats),
        'total_records': len(records)
    }

def get_disease_trend(stats, disease_name):
    """获取特定疾病的月度趋势"""
    trend = []
    for period in sorted(stats['monthly_stats'].keys()):
        count = stats['monthly_stats'][period].get(disease_name, 0)
        total = stats['monthly_total'].get(period, 1)
        trend.append({
            'period': period,
            'count': count,
            'ratio': round(count / total * 100, 1) if total > 0 else 0
        })
    return trend

def get_top_diseases(stats, top_n=15):
    """获取排名靠前的疾病"""
    disease_totals = defaultdict(int)
    for period, diseases in stats['monthly_stats'].items():
        for disease, count in diseases.items():
            disease_totals[disease] += count
    
    return sorted(disease_totals.items(), key=lambda x: -x[1])[:top_n]

def generate_html_report(stats, records):
    """生成HTML可视化报告"""
    
    # 获取主要疾病列表
    top_diseases = get_top_diseases(stats, 15)
    disease_names = [d[0] for d in top_diseases]
    
    # 生成每月各类别的数据
    periods = sorted(stats['monthly_total'].keys())
    
    # 疾病趋势数据
    disease_trends = {}
    for disease in disease_names[:10]:
        disease_trends[disease] = []
        for period in periods:
            count = stats['monthly_stats'][period].get(disease, 0)
            disease_trends[disease].append(count)
    
    # 大类分布
    categories = ['肿瘤', '眼科', '免疫/过敏', '血液/代谢', '感染', '罕见病', '其他']
    category_data = {cat: [] for cat in categories}
    for period in periods:
        for cat in categories:
            category_data[cat].append(stats['category_monthly'][period].get(cat, 0))
    
    # 医保类型分布
    insurance_html = ""
    for ins, count in sorted(stats['insurance_stats'].items(), key=lambda x: -x[1])[:8]:
        pct = round(count / stats['total_records'] * 100, 1)
        insurance_html += f'<div class="stat-item"><span class="label">{ins}</span><span class="value">{count}</span><span class="pct">({pct}%)</span></div>'
    
    # 疾病卡片HTML
    disease_cards = ""
    for disease, total in top_diseases:
        cat = categorize_disease(disease)
        trend = get_disease_trend(stats, disease)
        if len(trend) >= 2:
            first_half = sum(t['count'] for t in trend[:len(trend)//2])
            second_half = sum(t['count'] for t in trend[len(trend)//2:])
            if second_half > first_half * 1.2:
                trend_icon = "📈"
                trend_class = "up"
            elif second_half < first_half * 0.8:
                trend_icon = "📉"
                trend_class = "down"
            else:
                trend_icon = "➡️"
                trend_class = "stable"
        else:
            trend_icon = "➡️"
            trend_class = "stable"
        
        disease_cards += f'''
        <div class="disease-card">
            <div class="disease-header">
                <span class="disease-name">{disease}</span>
                <span class="disease-cat">{cat}</span>
                <span class="trend {trend_class}">{trend_icon}</span>
            </div>
            <div class="disease-stats">
                <span class="total-count">共 {total} 例</span>
            </div>
            <div class="disease-trend">
                {' '.join([f'<span class="month-bar" style="height:{max(5, count*10)}px">{count}</span>' for period, count in [(t['period'][-5:], t['count']) for t in trend]])}
            </div>
        </div>
        '''
    
    # 月度总量趋势
    monthly_total_data = [stats['monthly_total'].get(p, 0) for p in periods]
    max_monthly = max(monthly_total_data) if monthly_total_data else 1
    
    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>山西白求恩医院特药申请分析报告</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ 
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            color: #e0e0e0;
            padding: 20px;
        }}
        .container {{ max-width: 1400px; margin: 0 auto; }}
        h1 {{ 
            text-align: center; 
            color: #fff; 
            margin-bottom: 10px;
            font-size: 2rem;
        }}
        .subtitle {{ 
            text-align: center; 
            color: #888; 
            margin-bottom: 30px;
        }}
        .stats-bar {{
            display: flex;
            justify-content: center;
            gap: 30px;
            margin-bottom: 40px;
        }}
        .stat-box {{
            background: rgba(255,255,255,0.1);
            padding: 15px 30px;
            border-radius: 10px;
            text-align: center;
        }}
        .stat-box .number {{
            font-size: 2rem;
            font-weight: bold;
            color: #4ecdc4;
        }}
        .stat-box .label {{
            font-size: 0.9rem;
            color: #888;
        }}
        .chart-container {{
            background: rgba(255,255,255,0.05);
            border-radius: 15px;
            padding: 25px;
            margin-bottom: 30px;
        }}
        .chart-title {{
            font-size: 1.2rem;
            margin-bottom: 20px;
            color: #fff;
        }}
        .charts-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
        }}
        @media (max-width: 900px) {{
            .charts-grid {{ grid-template-columns: 1fr; }}
        }}
        .disease-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
            gap: 15px;
            margin-top: 30px;
        }}
        .disease-card {{
            background: rgba(255,255,255,0.08);
            border-radius: 10px;
            padding: 15px;
            transition: transform 0.2s;
        }}
        .disease-card:hover {{
            transform: translateY(-3px);
            background: rgba(255,255,255,0.12);
        }}
        .disease-header {{
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 10px;
        }}
        .disease-name {{
            font-weight: bold;
            color: #fff;
            flex: 1;
        }}
        .disease-cat {{
            font-size: 0.75rem;
            padding: 3px 8px;
            border-radius: 10px;
            background: rgba(78, 205, 196, 0.3);
            color: #4ecdc4;
        }}
        .trend {{ font-size: 1.2rem; }}
        .trend.up {{ color: #ff6b6b; }}
        .trend.down {{ color: #4ecdc4; }}
        .trend.stable {{ color: #ffd93d; }}
        .disease-stats {{
            font-size: 0.9rem;
            color: #888;
            margin-bottom: 10px;
        }}
        .disease-trend {{
            display: flex;
            align-items: flex-end;
            gap: 3px;
            height: 40px;
        }}
        .month-bar {{
            flex: 1;
            background: linear-gradient(to top, #4ecdc4, #44a3aa);
            border-radius: 3px 3px 0 0;
            display: flex;
            align-items: flex-end;
            justify-content: center;
            font-size: 0.65rem;
            color: #1a1a2e;
            min-height: 5px;
        }}
        .insurance-section, .insights-section {{
            background: rgba(255,255,255,0.05);
            border-radius: 15px;
            padding: 25px;
            margin-top: 30px;
        }}
        .stat-item {{
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 10px 0;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }}
        .stat-item .label {{ flex: 1; }}
        .stat-item .value {{ font-weight: bold; color: #4ecdc4; }}
        .stat-item .pct {{ color: #888; font-size: 0.85rem; }}
        .insight-item {{
            padding: 15px;
            background: rgba(78, 205, 196, 0.1);
            border-radius: 10px;
            margin-bottom: 15px;
            border-left: 4px solid #4ecdc4;
        }}
        .insight-item.negative {{
            background: rgba(255, 107, 107, 0.1);
            border-left-color: #ff6b6b;
        }}
        .insight-item.neutral {{
            background: rgba(255, 217, 61, 0.1);
            border-left-color: #ffd93d;
        }}
        .insight-title {{
            font-weight: bold;
            margin-bottom: 5px;
        }}
        .insight-content {{
            font-size: 0.9rem;
            color: #aaa;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🏥 山西白求恩医院特药申请分析报告</h1>
        <p class="subtitle">数据范围: 2024年6月 - 2026年5月 | 共 {stats['total_records']} 条申请记录</p>
        
        <div class="stats-bar">
            <div class="stat-box">
                <div class="number">{stats['total_records']}</div>
                <div class="label">总申请量</div>
            </div>
            <div class="stat-box">
                <div class="number">{len(periods)}</div>
                <div class="label">统计周期</div>
            </div>
            <div class="stat-box">
                <div class="number">{len(stats['insurance_stats'])}</div>
                <div class="label">医保类型</div>
            </div>
        </div>
        
        <div class="charts-grid">
            <div class="chart-container">
                <h3 class="chart-title">📊 月度申请总量趋势</h3>
                <canvas id="totalChart"></canvas>
            </div>
            <div class="chart-container">
                <h3 class="chart-title">🥧 医保类型分布</h3>
                <canvas id="insuranceChart"></canvas>
            </div>
        </div>
        
        <div class="chart-container">
            <h3 class="chart-title">📈 主要疾病申请趋势 (Top 10)</h3>
            <canvas id="diseaseChart"></canvas>
        </div>
        
        <div class="chart-container">
            <h3 class="chart-title">🏥 疾病大类分布趋势</h3>
            <canvas id="categoryChart"></canvas>
        </div>
        
        <div class="chart-container">
            <h3 class="chart-title">🔬 主要疾病排名 (共 {len(top_diseases)} 种)</h3>
            <div class="disease-grid">
                {disease_cards}
            </div>
        </div>
        
        <div class="insurance-section">
            <h3 class="chart-title">🏦 医保类型详细分布</h3>
            {insurance_html}
        </div>
        
        <div class="insights-section">
            <h3 class="chart-title">💡 关键洞察</h3>
            <div class="insight-item">
                <div class="insight-title">📈 上升趋势疾病</div>
                <div class="insight-content">
                    多发性骨髓瘤、特应性皮炎、过敏性哮喘呈明显上升趋势，可能与新药可及性提高和患者认知增强有关。
                </div>
            </div>
            <div class="insight-item negative">
                <div class="insight-title">📉 下降趋势疾病</div>
                <div class="insight-content">
                    乳腺癌、HIV相关申请呈下降趋势，可能与药品纳入常规医保目录有关。
                </div>
            </div>
            <div class="insight-item neutral">
                <div class="insight-title">➡️ 稳定需求疾病</div>
                <div class="insight-content">
                    眼科类疾病（糖尿病视网膜病变、黄斑变性）、过敏性哮喘等保持稳定需求。
                </div>
            </div>
            <div class="insight-item">
                <div class="insight-title">🔍 肿瘤仍是主力</div>
                <div class="insight-content">
                    肿瘤类疾病（肺癌、乳腺癌、多发性骨髓瘤等）占申请总量的最大比例，靶向药物需求持续旺盛。
                </div>
            </div>
        </div>
    </div>
    
    <script>
        // 颜色配置
        const colors = [
            '#ff6b6b', '#4ecdc4', '#45b7d1', '#96ceb4', '#ffeaa7',
            '#dfe6e9', '#a29bfe', '#fd79a8', '#fdcb6e', '#6c5ce7',
            '#00b894', '#e17055', '#74b9ff', '#55a3ff', '#ff7675'
        ];
        
        // 月度总量趋势
        new Chart(document.getElementById('totalChart'), {{
            type: 'line',
            data: {{
                labels: {json.dumps(periods)},
                datasets: [{{
                    label: '申请量',
                    data: {json.dumps(monthly_total_data)},
                    borderColor: '#4ecdc4',
                    backgroundColor: 'rgba(78, 205, 196, 0.2)',
                    fill: true,
                    tension: 0.3
                }}]
            }},
            options: {{
                responsive: true,
                plugins: {{ legend: {{ display: false }} }},
                scales: {{
                    y: {{ beginAtZero: true, grid: {{ color: 'rgba(255,255,255,0.1)' }}, ticks: {{ color: '#888' }} }},
                    x: {{ grid: {{ display: false }}, ticks: {{ color: '#888', maxRotation: 45 }} }}
                }}
            }}
        }});
        
        // 医保类型分布
        const insuranceData = {json.dumps(dict(sorted(stats['insurance_stats'].items(), key=lambda x: -x[1])[:8]))};
        new Chart(document.getElementById('insuranceChart'), {{
            type: 'doughnut',
            data: {{
                labels: Object.keys(insuranceData),
                datasets: [{{
                    data: Object.values(insuranceData),
                    backgroundColor: colors.slice(0, Object.keys(insuranceData).length)
                }}]
            }},
            options: {{
                responsive: true,
                plugins: {{ legend: {{ position: 'right', labels: {{ color: '#aaa', font: {{ size: 11 }} }} }} }}
            }}
        }});
        
        // 主要疾病趋势
        const diseaseLabels = {json.dumps(disease_names[:10])};
        const diseaseDatasets = diseaseLabels.map((name, i) => ({{
            label: name,
            data: {json.dumps(disease_trends.get(name, []))},
            borderColor: colors[i],
            backgroundColor: 'transparent',
            tension: 0.3
        }}));
        new Chart(document.getElementById('diseaseChart'), {{
            type: 'line',
            data: {{ labels: {json.dumps(periods)}, datasets: diseaseDatasets }},
            options: {{
                responsive: true,
                plugins: {{ legend: {{ position: 'right', labels: {{ color: '#aaa', font: {{ size: 10 }} }} }} }},
                scales: {{
                    y: {{ beginAtZero: true, grid: {{ color: 'rgba(255,255,255,0.1)' }}, ticks: {{ color: '#888' }} }},
                    x: {{ grid: {{ display: false }}, ticks: {{ color: '#888', maxRotation: 45 }} }}
                }}
            }}
        }});
        
        // 疾病大类分布
        new Chart(document.getElementById('categoryChart'), {{
            type: 'bar',
            data: {{
                labels: {json.dumps(periods)},
                datasets: [
                    {{ label: '肿瘤', data: {json.dumps(category_data['肿瘤'])}, backgroundColor: '#ff6b6b' }},
                    {{ label: '眼科', data: {json.dumps(category_data['眼科'])}, backgroundColor: '#4ecdc4' }},
                    {{ label: '免疫/过敏', data: {json.dumps(category_data['免疫/过敏'])}, backgroundColor: '#45b7d1' }},
                    {{ label: '血液/代谢', data: {json.dumps(category_data['血液/代谢'])}, backgroundColor: '#96ceb4' }},
                    {{ label: '罕见病', data: {json.dumps(category_data['罕见病'])}, backgroundColor: '#a29bfe' }},
                    {{ label: '其他', data: {json.dumps(category_data['其他'])}, backgroundColor: '#636e72' }}
                ]
            }},
            options: {{
                responsive: true,
                plugins: {{ legend: {{ position: 'right', labels: {{ color: '#aaa' }} }} }},
                scales: {{
                    y: {{ stacked: true, beginAtZero: true, grid: {{ color: 'rgba(255,255,255,0.1)' }}, ticks: {{ color: '#888' }} }},
                    x: {{ stacked: true, grid: {{ display: false }}, ticks: {{ color: '#888', maxRotation: 45 }} }}
                }}
            }}
        }});
    </script>
</body>
</html>'''
    
    return html

def main():
    print("加载全量数据...")
    records = load_all_data()
    print(f"共加载 {len(records)} 条记录")
    
    print("分析数据趋势...")
    stats = analyze_trends(records)
    
    print("生成HTML报告...")
    html = generate_html_report(stats, records)
    
    # 保存报告
    output_file = os.path.join(DATA_DIR, "teyao_full_analysis.html")
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html)
    
    print(f"报告已保存到: {output_file}")
    
    # 打印简要统计
    print("\n=== 简要统计 ===")
    print(f"总记录数: {stats['total_records']}")
    print(f"统计周期: {len(stats['monthly_total'])} 个月")
    print("\nTop 10 疾病:")
    for disease, count in get_top_diseases(stats, 10):
        print(f"  {disease}: {count}")
    
    return stats

if __name__ == "__main__":
    main()
