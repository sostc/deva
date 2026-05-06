#!/usr/bin/env python3
"""
全量获取腾讯文档特药申请数据 - 直接调用腾讯文档API
"""
import json
import os
from datetime import datetime
import subprocess

# 所有smartsheet的ID和名称列表 (从新到旧)
SHEETS = [
    ("ss_bk7poz", "20260504-20260510"),
    ("ss_d8gjh1", "20260427-20260503"),
    ("ss_7kyhpg", "20260420-20260426"),
    ("ss_f32fn4", "20260413-20260419"),
    ("ss_0eto4w", "20260406-20260412"),
    ("ss_mhn384", "20260330-20260405"),
    ("ss_87expt", "20260323-20260329"),
    ("ss_xowm53", "20260316-20260322"),
    ("ss_3gxudm", "20260309-20260315"),
    ("ss_a7puws", "20260105-20260111"),
    ("ss_skma3b", "20251229-20260104"),
    ("ss_m5jmiz", "20251222-20251228"),
    ("ss_182b7d", "20251215-20251221"),
    ("ss_4xo132", "20251208-20251214"),
    ("ss_1nrd0z", "20251201-20251207"),
    ("ss_55zrb3", "20251124-20251130"),
    ("ss_7r6cki", "20251117-20251123"),
    ("ss_0vzl6l", "20251110-20251116"),
    ("ss_13z5gy", "20251103-20251109"),
    ("ss_ckyiox", "20251027-20251102"),
    ("ss_pjupmy", "20251020-20251026"),
    ("ss_qtypwv", "20251013-20251019"),
    ("ss_xoq6qo", "20251006-20251012"),
    ("ss_bx5u72", "20250929-20251005"),
    ("ss_oyhbte", "20250922-20250928"),
    ("ss_fpjhrh", "20250915-20250921"),
    ("ss_ta5ofe", "20250908-20250914"),
    ("ss_0j15c0", "20250901-20250907"),
    ("ss_7kv3p0", "20250825-20250831"),
    ("ss_zheu9j", "20250818-20250824"),
    ("ss_1w07v6", "20250811-20250817"),
    ("ss_x90ss0", "20250804-20250810"),
    ("ss_3qv83a", "20250728-20250803"),
    ("ss_1cd9hn", "20250721-20250727"),
    ("ss_b9x39r", "20250714-20250720"),
    ("ss_2woxdy", "20250707-20250713"),
    ("ss_v1tvgg", "20250630-20250706"),
    ("ss_xpxsx1", "20250623-20250629"),
    ("ss_3rtp7o", "20250616-20250622"),
    ("ss_yuoou8", "20250609-20250615"),
    ("ss_vcdk84", "20250602-20250608"),
    ("ss_pskem5", "20250127-20250202"),
    ("ss_3lf5mz", "20250120-20250126"),
    ("ss_nbsdrf", "20250113-20250119"),
    ("ss_2h8k0d", "20250106-20250112"),
    ("ss_4ozgym", "20241230-20250105"),
    ("ss_otx0s0", "20241223-20241229"),
    ("ss_ndptr5", "20241216-20241222"),
    ("ss_pe23xf", "20241209-20241215"),
    ("ss_75ok7g", "20241202-20241208"),
    ("ss_npyfte", "20241125-20241201"),
    ("ss_oebanp", "20241118-20241124"),
    ("ss_22ri8p", "20241111-20241117"),
    ("ss_2rs5tz", "20241104-20241110"),
    ("ss_iualim", "20241028-20241103"),
    ("ss_08uzfr", "20241021-20241027"),
    ("ss_q5ijp0", "20241014-20241020"),
    ("ss_mc2ils", "20241007-20241013"),
    ("ss_zj005p", "20240930-20241006"),
    ("ss_kuo5p9", "20240923-20240929"),
    ("ss_vd7xk9", "20240916-20240922"),
    ("ss_zz9dsw", "20240909-20240915"),
    ("ss_7f75hl", "20240902-20240908"),
    ("ss_bcsl9r", "20240826-20240901"),
    ("ss_xwqa4f", "20240819-20240825"),
    ("ss_q563gg", "20240812-20240818"),
    ("ss_6cjyo2", "20240805-20240811"),
    ("ss_6i2ht2", "20240729-20240804"),
    ("ss_e3h780", "20240722-20240728"),
    ("ss_7ve0o4", "20240715-20240721"),
    ("ss_q4pff4", "20240708-20240714"),
    ("ss_tf5xss", "20240701-20240707"),
    ("ss_eas815", "20240624-20240630"),
    ("ss_ekkpyz", "20240617-20240623"),
    ("ss_k1c87o", "20240610-20240616"),
    ("ss_yn2si5", "20240603-20240609"),
]

FILE_ID = "DmbhrPvPDmrO"
OUTPUT_DIR = "/Users/spark/pycharmproject/deva/deva/naja/.workbuddy/teyao_full"

def extract_field_value(field_values, field_name):
    """从field_values中提取指定字段的值"""
    for fv in field_values:
        if fv.get('field') == field_name:
            if 'text_value' in fv:
                items = fv['text_value'].get('items', [])
                return ''.join(item.get('text', '') for item in items)
            elif 'option_value' in fv:
                items = fv['option_value'].get('items', [])
                return items[0].get('text', '') if items else ''
            elif 'string_value' in fv:
                return fv['string_value']
            elif 'number_value' in fv:
                return str(fv['number_value'])
    return ''

def parse_timestamp(ts_str):
    """解析时间戳"""
    try:
        ts = int(ts_str) / 1000
        return datetime.fromtimestamp(ts).strftime('%Y-%m-%d')
    except:
        return ''

def call_mcp_tool(tool_name, params):
    """调用MCP工具"""
    cmd = [
        'node', '-e', f'''
        const {{ connectCloudService }} = require('workbuddy-connector');
        (async () => {{
            try {{
                const service = await connectCloudService('tencent-docs');
                const result = await service.call('{tool_name}', {json.dumps(params)});
                console.log(JSON.stringify(result));
            }} catch (e) {{
                console.log(JSON.stringify({{ error: e.message }}));
            }}
        }})();
        '''
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return json.loads(result.stdout)
    except:
        pass
    return None

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    all_records = []
    total_sheets = len(SHEETS)
    
    print(f"开始获取 {total_sheets} 个工作表的数据...")
    print("=" * 50)
    
    for idx, (sheet_id, sheet_name) in enumerate(SHEETS):
        print(f"[{idx+1}/{total_sheets}] {sheet_name}...", end=" ", flush=True)
        
        try:
            # 获取第一页
            data = call_mcp_tool("mcp__tencent-docs__smartsheet.list_records", {
                "file_id": FILE_ID,
                "sheet_id": sheet_id,
                "limit": 100,
                "offset": 0
            })
            
            if data and 'structuredContent' in data:
                content = data['structuredContent']
                records = content.get('records', [])
                total = content.get('total', 0)
                all_page_records = list(records)
                
                # 继续获取剩余页面
                offset = 100
                while offset < total and len(records) == 100:
                    data2 = call_mcp_tool("mcp__tencent-docs__smartsheet.list_records", {
                        "file_id": FILE_ID,
                        "sheet_id": sheet_id,
                        "limit": 100,
                        "offset": offset
                    })
                    
                    if data2 and 'structuredContent' in data2:
                        records = data2['structuredContent'].get('records', [])
                        all_page_records.extend(records)
                        offset += 100
                    else:
                        break
                
                # 提取关键字段
                for record in all_page_records:
                    field_values = record.get('field_values', [])
                    disease = extract_field_value(field_values, '疾病名称（必填）')
                    medicine = extract_field_value(field_values, '申请药名（必填）')
                    insurance = extract_field_value(field_values, '医保类别（必填）')
                    doctor = extract_field_value(field_values, '特药医师（必填）')
                    patient = extract_field_value(field_values, '患者姓名（必填）')
                    submit_time = extract_field_value(field_values, '提交时间（自动）')
                    
                    all_records.append({
                        'sheet_name': sheet_name,
                        'disease': disease,
                        'medicine': medicine,
                        'insurance': insurance,
                        'doctor': doctor,
                        'patient': patient,
                        'submit_time': parse_timestamp(submit_time) if submit_time else sheet_name[:8]
                    })
                
                print(f"✓ {len(all_page_records)}条")
            else:
                print(f"✗ 获取失败")
                
        except Exception as e:
            print(f"✗ 错误: {str(e)[:50]}")
    
    print("=" * 50)
    print(f"数据获取完成！共 {len(all_records)} 条记录")
    
    # 保存原始数据
    output_file = os.path.join(OUTPUT_DIR, "raw_data.json")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_records, f, ensure_ascii=False, indent=2)
    
    print(f"数据已保存到: {output_file}")
    
    # 统计汇总
    stats = {}
    for r in all_records:
        period = r['sheet_name'][:6]  # YYYYMM
        disease = r['disease']
        if period not in stats:
            stats[period] = {}
        stats[period][disease] = stats[period].get(disease, 0) + 1
    
    print("\n按月统计疾病数量:")
    for period in sorted(stats.keys()):
        print(f"  {period}: {sum(stats[period].values())}条, {len(stats[period])}种疾病")
    
    return all_records

if __name__ == "__main__":
    main()
