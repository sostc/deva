"""增强版数据源面板(AI Enhanced DataSource Panel)

为数据源面板集成AI代码生成功能，提供用户审核编辑界面。
"""

from __future__ import annotations

import json
import traceback
from typing import Any, Dict, List, Optional, Callable
from datetime import datetime

from deva import log

from .datasource import DataSourceType, get_ds_manager
from ..ai.ai_code_generation_dialog import AICodeGenerationDialog
from .interactive_ai_code_generator import InteractiveCodeGenerator, CodeReviewResult
from .ai_code_generation_ui import AICodeGenerationUI, get_ai_code_generation_ui


async def show_enhanced_create_datasource_dialog(ctx):
    """增强版创建数据源对话框 - 集成AI代码生成功能"""
    try:
        from pywebio import output as pw_output
        from pywebio import input as pw_input
        
        with ctx["popup"]("创建新数据源 (AI增强版)", size="large", closable=True):
            ctx["put_markdown"]("### 数据源配置 (AI增强版)")
            ctx["put_html"]("""
            <div style='background:#e3f2fd;padding:12px;border-radius:8px;margin-bottom:15px;'>
                <p style='color:#1565c0;font-size:14px;margin:0;'>
                    💡 <strong>AI代码生成</strong>：点击「AI生成」按钮，由AI根据需求描述自动生成数据获取代码
                </p>
                <p style='color:#1565c0;font-size:12px;margin:5px 0 0 0;'>
                    📝 <strong>代码审核</strong>：生成的代码需要您的审核和编辑确认
                </p>
            </div>
            """)
            
            # 基础信息收集
            basic_form = await ctx["input_group"]("基础信息", [
                ctx["input"]("数据源名称", name="name", required=True, placeholder="输入数据源名称"),
                ctx["select"](
                    "数据源类型",
                    name="source_type",
                    options=[
                        {"label": "定时器 (Timer)", "value": "TIMER"},
                        {"label": "自定义 (Custom)", "value": "CUSTOM"},
                        {"label": "文件 (File)", "value": "FILE"},
                        {"label": "数据库 (Database)", "value": "DATABASE"},
                        {"label": "API接口 (API)", "value": "API"},
                        {"label": "消息队列 (Queue)", "value": "QUEUE"}
                    ],
                    value="TIMER"
                ),
                ctx["textarea"]("描述", name="description", placeholder="数据源描述（可选）", rows=2),
                ctx["input"]("更新间隔 (秒)", name="interval", type="number", value="5", help_text="数据更新间隔时间")
            ])
            
            if not basic_form:
                ctx["close_popup"]()
                return
            
            # 代码生成选项
            ctx["put_markdown"]("### 代码生成选项")
            code_generation_method = await ctx["radio"](
                "选择代码生成方式",
                options=[
                    {"label": "🤖 AI智能生成 - 描述需求，AI自动生成代码", "value": "ai_generate"},
                    {"label": "✏️ 手动编写 - 直接输入Python代码", "value": "manual_write"},
                    {"label": "📋 从模板选择 - 选择预设代码模板", "value": "template_select"},
                    {"label": "📁 从文件导入 - 上传Python代码文件", "value": "file_import"}
                ],
                value="ai_generate"
            )
            
            generated_code = ""
            
            if code_generation_method == "ai_generate":
                generated_code = await _enhanced_datasource_ai_generation(ctx, basic_form)
                
            elif code_generation_method == "manual_write":
                generated_code = await _manual_datasource_code_input(ctx)
                
            elif code_generation_method == "template_select":
                generated_code = await _datasource_template_selection(ctx)
                
            elif code_generation_method == "file_import":
                generated_code = await _datasource_file_import(ctx)
            
            if not generated_code:
                ctx["toast"]("代码生成被取消", color="warning")
                return
            
            # 最终确认
            ctx["put_markdown"]("### 最终确认")
            ctx["put_info"](f"数据源名称: {basic_form['name']}")
            ctx["put_info"](f"数据源类型: {basic_form['source_type']}")
            ctx["put_info"](f"代码长度: {len(generated_code)} 字符")
            
            with ctx["put_collapse"]("预览代码", open=False):
                ctx["put_code"](generated_code, language="python")
            
            final_confirm = await ctx["input_group"]("确认创建", [
                ctx["checkbox"](
                    "确认选项",
                    name="confirmations",
                    options=[
                        {"label": "我已审核生成的代码", "value": "code_reviewed", "selected": True},
                        {"label": "我理解代码的执行逻辑", "value": "logic_understood", "selected": True},
                        {"label": "我确认使用此代码", "value": "code_approved", "selected": True}
                    ]
                ),
                ctx["actions"]("操作", [
                    {"label": "✅ 创建数据源", "value": "create", "color": "success"},
                    {"label": "❌ 取消", "value": "cancel", "color": "danger"}
                ], name="action")
            ])
            
            if not final_confirm or final_confirm.get("action") != "create":
                return
            
            # 检查确认选项
            required_confirmations = ["code_reviewed", "code_approved"]
            selected_confirmations = final_confirm.get("confirmations", [])
            
            for req in required_confirmations:
                if req not in selected_confirmations:
                    ctx["toast"]("请确认所有必要选项", color="warning")
                    return
            
            # 创建数据源
            ds_mgr = get_ds_manager()
            source_type = DataSourceType(basic_form["source_type"])
            
            result = ds_mgr.create_source(
                name=basic_form["name"],
                source_type=source_type,
                description=basic_form.get("description", ""),
                config={"interval": basic_form.get("interval", 5)} if source_type == DataSourceType.TIMER else {},
                data_func_code=generated_code,
                interval=basic_form.get("interval", 5) if source_type == DataSourceType.TIMER else 5.0,
                auto_start=False,
            )
            
            if result.get("success"):
                ctx["toast"](f"数据源创建成功: {result['source_id']}", color="success")
                ctx["run_js"]("location.reload()")
            else:
                ctx["toast"](f"创建失败: {result.get('error', '')}", color="error")
                
    except Exception as e:
        log.error(f"增强版创建数据源对话框错误: {e}")
        ctx["toast"](f"创建数据源对话框错误: {e}", color="error")
        ctx["close_popup"]()


async def _enhanced_datasource_ai_generation(ctx, basic_form: Dict[str, Any]) -> str:
    """增强版AI数据源代码生成流程"""
    try:
        # 创建AI代码生成对话框
        ai_dialog = AICodeGenerationDialog("datasource", ctx)
        
        # 显示AI代码生成向导
        ctx["put_markdown"]("#### 🤖 AI数据源代码生成向导")
        ctx["put_html"]("""
        <div style='background:#e8f5e9;padding:12px;border-radius:8px;margin-bottom:15px;'>
            <p style='color:#2e7d32;font-size:14px;margin:0;'>
                💡 <strong>AI数据源代码生成向导</strong>将引导您完成代码生成过程
            </p>
            <p style='color:#2e7d32;font-size:12px;margin:5px 0 0 0;'>
                📝 请详细描述您的数据源需求，AI将生成相应的Python代码
            </p>
        </div>
        """)
        
        # 步骤1: 数据源需求收集
        ctx["put_markdown"]("##### 步骤1: 数据源需求收集")
        
        requirement_form = await _collect_datasource_requirements(ctx, basic_form)
        
        if not requirement_form:
            return ""
        
        # 步骤2: AI代码生成
        ctx["put_markdown"]("##### 步骤2: AI代码生成")
        ctx["put_info"]("正在生成代码，请稍候...")
        
        # 构建生成上下文
        generation_context = {
            "datasource_name": basic_form.get("name", "未命名数据源"),
            "datasource_type": basic_form.get("source_type", "TIMER"),
            "update_frequency": requirement_form.get("update_frequency", ""),
            "data_format": requirement_form.get("data_format", ""),
            "api_info": requirement_form.get("api_info", ""),
            "generation_options": requirement_form.get("generation_options", [])
        }
        
        # 使用交互式代码生成器
        generator = InteractiveCodeGenerator("datasource")
        
        review_result = await generator.generate_and_review(
            requirement=requirement_form["requirement"],
            context=generation_context,
            show_comparison=True,
            enable_realtime_validation=True,
            include_error_handling="include_error_handling" in requirement_form["generation_options"],
            include_retry="include_retry" in requirement_form["generation_options"]
        )
        
        if not review_result.approved:
            ctx["toast"]("代码生成被取消", color="warning")
            return ""
        
        # 显示生成结果
        ctx["put_markdown"]("##### 步骤3: 代码审核与编辑")
        
        # 显示代码摘要
        ctx["put_success"](f"✅ 代码生成完成 (长度: {len(review_result.code)} 字符)")
        if review_result.user_modified:
            ctx["put_info"]("📝 用户对代码进行了修改")
        
        # 显示代码预览
        with ctx["put_collapse"]("📋 生成代码预览", open=False):
            ctx["put_code"](review_result.code, language="python")
        
        # 显示代码说明
        if review_result.validation_result:
            with ctx["put_collapse"]("📖 代码说明和验证结果", open=False):
                if review_result.validation_result.get("success"):
                    ctx["put_success"]("✅ 代码验证通过")
                else:
                    ctx["put_error"](f"❌ 代码验证失败: {review_result.validation_result.get('error', '')}")
                
                warnings = review_result.validation_result.get("warnings", [])
                if warnings:
                    ctx["put_warning"](f"⚠️  发现 {len(warnings)} 个警告:")
                    for warning in warnings:
                        ctx["put_text"](f"   • {warning}")
        
        # 最终确认
        final_confirm = await ctx["input_group"]("代码确认", [
            ctx["checkbox"](
                "确认选项",
                name="code_confirmations",
                options=[
                    {"label": "我已审核生成的代码", "value": "reviewed", "selected": True},
                    {"label": "我理解代码的执行逻辑", "value": "understood", "selected": True},
                    {"label": "我确认使用此代码", "value": "approved", "selected": True}
                ]
            ),
            ctx["actions"]("操作", [
                {"label": "✅ 使用此代码", "value": "use_code", "color": "success"},
                {"label": "🔄 重新生成", "value": "regenerate", "color": "warning"},
                {"label": "❌ 取消", "value": "cancel", "color": "danger"}
            ], name="action")
        ])
        
        if not final_confirm or final_confirm.get("action") == "cancel":
            return ""
        
        if final_confirm.get("action") == "regenerate":
            return await _enhanced_datasource_ai_generation(ctx, basic_form)
        
        # 检查确认选项
        required_confirmations = ["reviewed", "approved"]
        selected_confirmations = final_confirm.get("code_confirmations", [])
        
        for req in required_confirmations:
            if req not in selected_confirmations:
                ctx["toast"]("请确认所有必要选项", color="warning")
                return await _enhanced_datasource_ai_generation(ctx, basic_form)
        
        return review_result.code
        
    except Exception as e:
        log.error(f"增强版AI数据源代码生成错误: {e}")
        ctx["toast"](f"AI代码生成错误: {e}", color="error")
        return ""


async def _collect_datasource_requirements(ctx, basic_form: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """收集数据源需求信息"""
    try:
        # 数据源类型选项
        datasource_type_options = [
            {"label": "API接口", "value": "api"},
            {"label": "数据库", "value": "database"},
            {"label": "文件", "value": "file"},
            {"label": "网页抓取", "value": "web_scraping"},
            {"label": "自定义", "value": "custom"}
        ]
        
        # 根据基础表单中的数据源类型预设选择
        source_type = basic_form.get("source_type", "TIMER")
        default_datasource_type = "custom"
        if source_type == "API":
            default_datasource_type = "api"
        elif source_type == "DATABASE":
            default_datasource_type = "database"
        elif source_type == "FILE":
            default_datasource_type = "file"
        
        # 显示需求收集表单
        requirement_form = await ctx["input_group"]("数据源需求配置", [
            ctx["select"](
                "数据源类型",
                name="datasource_type",
                options=datasource_type_options,
                value=default_datasource_type,
                help_text="选择数据源类型，AI将根据类型生成相应的代码"
            ),
            ctx["textarea"](
                "数据源需求描述",
                name="requirement",
                placeholder="描述您需要获取的数据，例如：\n- 从天气API获取实时天气数据\n- 包含温度、湿度、风速等信息\n- 每5分钟更新一次",
                rows=3,
                required=True,
                value=f"为数据源'{basic_form.get('name', '')}'生成数据获取函数" if basic_form.get('name') else ""
            ),
            ctx["textarea"](
                "数据更新频率",
                name="update_frequency",
                placeholder="例如：每5分钟更新一次，或每天更新一次",
                rows=1,
                help_text="设置数据获取的频率要求",
                value=f"每{basic_form.get('interval', 5)}秒更新一次" if basic_form.get('interval') else ""
            ),
            ctx["textarea"](
                "数据格式要求",
                name="data_format",
                placeholder="描述期望的数据格式，例如：\n- 返回包含温度、湿度、风速的DataFrame\n- 包含时间戳和数据值\n- 数据类型为数值型",
                rows=2
            ),
            ctx["textarea"](
                "API信息 (如果适用)",
                name="api_info",
                placeholder="API地址、认证方式、请求参数等信息\n例如：https://api.example.com/weather\n认证：Bearer token\n参数：city=北京",
                rows=2,
                help_text="如果是API数据源，请提供相关信息"
            ),
            ctx["checkbox"](
                "生成选项",
                name="generation_options",
                options=[
                    {"label": "包含错误处理", "value": "include_error_handling", "selected": True},
                    {"label": "包含重试机制", "value": "include_retry", "selected": True},
                    {"label": "包含数据验证", "value": "include_validation", "selected": True},
                    {"label": "包含日志记录", "value": "include_logging", "selected": True}
                ]
            )
        ])
        
        return requirement_form
        
    except Exception as e:
        log.error(f"收集数据源需求错误: {e}")
        return None


async def _manual_datasource_code_input(ctx) -> str:
    """手动数据源代码输入"""
    ctx["put_markdown"]("### 手动代码输入")
    ctx["put_html"]("""
    <div style='background:#fff3e0;padding:12px;border-radius:8px;margin-bottom:15px;'>
        <p style='color:#e65100;font-size:14px;margin:0;'>
            💡 <strong>手动代码输入</strong> - 请直接输入Python代码
        </p>
        <p style='color:#e65100;font-size:12px;margin:5px 0 0 0;'>
            📝 函数签名必须为: async def fetch_data():
        </p>
    </div>
    """)
    
    code_input = await ctx["input_group"]("代码输入", [
        ctx["textarea"](
            "数据源代码",
            name="code",
            placeholder="async def fetch_data():\n    # 在这里输入您的数据源代码\n    # 返回获取的数据\n    return data",
            rows=12,
            required=True
        ),
        ctx["actions"]("操作", [
            {"label": "✅ 验证代码", "value": "validate"},
            {"label": "💾 使用代码", "value": "use"},
            {"label": "❌ 取消", "value": "cancel"}
        ], name="action")
    ])
    
    if not code_input or code_input.get("action") == "cancel":
        return ""
    
    code = code_input["code"]
    
    if code_input.get("action") == "validate":
        # 验证代码
        validation = validate_datasource_code(code)
        if validation["valid"]:
            ctx["put_success"]("✅ 代码验证通过")
            use_code = await ctx["actions"]("是否使用此代码？", [
                {"label": "✅ 使用", "value": "yes"},
                {"label": "❌ 重新编辑", "value": "edit"}
            ])
            if use_code == "edit":
                return await _manual_datasource_code_input(ctx)
        else:
            ctx["put_error"](f"❌ 代码验证失败: {'; '.join(validation['errors'])}")
            return await _manual_datasource_code_input(ctx)
    
    return code


async def _datasource_template_selection(ctx) -> str:
    """数据源模板选择"""
    ctx["put_markdown"]("### 数据源模板选择")
    ctx["put_html"]("""
    <div style='background:#e8f5e9;padding:12px;border-radius:8px;margin-bottom:15px;'>
        <p style='color:#2e7d32;font-size:14px;margin:0;'>
            📋 <strong>数据源模板选择</strong> - 选择预设的代码模板
        </p>
        <p style='color:#2e7d32;font-size:12px;margin:5px 0 0 0;'>
            🚀 选择模板后可以根据需要进行修改
        </p>
    </div>
    """)
    
    # 预定义数据源模板
    templates = {
        "stock_data_api": {
            "name": "股票数据API",
            "description": "从股票API获取实时股票数据",
            "code": '''async def fetch_data():
    """获取股票数据"""
    import pandas as pd
    import asyncio
    import random
    
    # 模拟股票数据获取
    symbols = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA"]
    data = []
    
    for symbol in symbols:
        data.append({
            "symbol": symbol,
            "price": random.uniform(100, 500),
            "volume": random.randint(100000, 1000000),
            "change": random.uniform(-5, 5),
            "timestamp": pd.Timestamp.now()
        })
    
    df = pd.DataFrame(data)
    return df'''
        },
        "weather_api": {
            "name": "天气数据API",
            "description": "获取天气数据",
            "code": '''async def fetch_data():
    """获取天气数据"""
    import pandas as pd
    import random
    import asyncio
    
    # 模拟天气数据
    cities = ["北京", "上海", "广州", "深圳", "杭州"]
    data = []
    
    for city in cities:
        data.append({
            "city": city,
            "temperature": random.uniform(-10, 35),
            "humidity": random.uniform(30, 90),
            "wind_speed": random.uniform(0, 20),
            "weather": random.choice(["晴", "多云", "雨", "雪"]),
            "timestamp": pd.Timestamp.now()
        })
    
    df = pd.DataFrame(data)
    return df'''
        },
        "sensor_data": {
            "name": "传感器数据",
            "description": "获取传感器数据",
            "code": '''async def fetch_data():
    """获取传感器数据"""
    import pandas as pd
    import random
    import asyncio
    
    # 模拟传感器数据
    sensors = ["温度传感器", "湿度传感器", "压力传感器", "光照传感器"]
    data = []
    
    for sensor in sensors:
        data.append({
            "sensor_id": sensor,
            "value": random.uniform(0, 100),
            "unit": random.choice(["°C", "%", "Pa", "lux"]),
            "status": random.choice(["正常", "警告", "异常"]),
            "timestamp": pd.Timestamp.now()
        })
    
    df = pd.DataFrame(data)
    return df'''
        },
        "financial_data": {
            "name": "金融数据",
            "description": "获取金融数据",
            "code": '''async def fetch_data():
    """获取金融数据"""
    import pandas as pd
    import random
    import asyncio
    
    # 模拟金融数据
    currencies = ["USD", "EUR", "GBP", "JPY", "CNY"]
    data = []
    
    for currency in currencies:
        data.append({
            "currency": currency,
            "rate": random.uniform(0.8, 1.2),
            "change": random.uniform(-0.05, 0.05),
            "volume": random.randint(1000000, 10000000),
            "timestamp": pd.Timestamp.now()
        })
    
    df = pd.DataFrame(data)
    return df'''
        }
    }
    
    # 显示模板选择
    template_options = []
    for key, template in templates.items():
        template_options.append({
            "label": f"{template['name']} - {template['description']}",
            "value": key
        })
    
    selected_template = await ctx["select"](
        "选择数据源模板",
        options=template_options,
        help_text="选择预设的数据源代码模板"
    )
    
    if not selected_template:
        return ""
    
    # 显示模板代码
    template_info = templates[selected_template]
    
    ctx["put_markdown"](f"#### 模板: {template_info['name']}")
    ctx["put_text"](f"描述: {template_info['description']}")
    
    with ctx["put_collapse"]("📋 模板代码预览", open=True):
        ctx["put_code"](template_info['code'], language="python")
    
    # 确认使用
    confirm_use = await ctx["actions"]("是否使用此模板？", [
        {"label": "✅ 使用模板", "value": "use"},
        {"label": "✏️ 编辑模板", "value": "edit"},
        {"label": "❌ 重新选择", "value": "reselect"}
    ])
    
    if confirm_use == "edit":
        # 允许用户编辑模板
        edited_code = await ctx["textarea"](
            "编辑代码",
            value=template_info['code'],
            rows=15,
            help_text="您可以在此修改模板代码"
        )
        return edited_code if edited_code else template_info['code']
    elif confirm_use == "use":
        return template_info['code']
    elif confirm_use == "reselect":
        return await _datasource_template_selection(ctx)
    else:
        return ""


async def _datasource_file_import(ctx) -> str:
    """从文件导入数据源代码"""
    ctx["put_markdown"]("### 从文件导入代码")
    ctx["put_html"]("""
    <div style='background:#f3e5f5;padding:12px;border-radius:8px;margin-bottom:15px;'>
        <p style='color:#6a1b9a;font-size:14px;margin:0;'>
            📁 <strong>文件导入</strong> - 上传Python代码文件
        </p>
        <p style='color:#6a1b9a;font-size:12px;margin:5px 0 0 0;'>
            📋 文件内容必须包含 async def fetch_data() 函数
        </p>
    </div>
    """)
    
    # 文件上传
    uploaded_file = await ctx["file_upload"](
        "选择Python文件",
        accept=".py",
        help_text="上传包含 fetch_data 函数的Python文件"
    )
    
    if not uploaded_file:
        ctx["toast"]("未选择文件", color="warning")
        return ""
    
    try:
        # 读取文件内容
        file_content = uploaded_file['content'].decode('utf-8')
        
        # 验证代码
        validation = validate_datasource_code(file_content)
        
        if validation["valid"]:
            ctx["put_success"]("✅ 文件验证通过")
            
            # 显示代码预览
            with ctx["put_collapse"]("📋 文件内容预览", open=False):
                ctx["put_code"](file_content, language="python")
            
            # 确认使用
            confirm = await ctx["actions"]("是否使用此文件？", [
                {"label": "✅ 使用文件", "value": "use"},
                {"label": "❌ 取消", "value": "cancel"}
            ])
            
            if confirm == "use":
                return file_content
            else:
                return ""
        else:
            ctx["put_error"](f"❌ 文件验证失败: {'; '.join(validation['errors'])}")
            return ""
            
    except Exception as e:
        ctx["put_error"](f"❌ 文件处理错误: {str(e)}")
        return ""


def validate_datasource_code(code: str) -> Dict[str, Any]:
    """验证数据源代码"""
    try:
        import ast
        
        # 语法检查
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return {
                "valid": False,
                "errors": [f"语法错误: {e}"]
            }
        
        # 检查函数定义
        functions = []
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef):
                functions.append(node.name)
            elif isinstance(node, ast.FunctionDef):
                functions.append(node.name)
        
        if "fetch_data" not in functions:
            return {
                "valid": False,
                "errors": ["未找到'fetch_data'函数定义，数据源必须包含fetch_data函数"]
            }
        
        # 安全性检查
        dangerous_keywords = ['eval', 'exec', '__import__', 'open', 'file']
        warnings = []
        for keyword in dangerous_keywords:
            if keyword in code:
                warnings.append(f"检测到潜在危险关键字: {keyword}")
        
        return {
            "valid": True,
            "errors": [],
            "warnings": warnings,
            "functions": functions
        }
        
    except Exception as e:
        return {
            "valid": False,
            "errors": [f"验证过程出错: {e}"]
        }


# ==========================================================================
# 增强版编辑数据源对话框
# ==========================================================================

async def show_enhanced_edit_datasource_dialog(ctx, source_id: str):
    """增强版编辑数据源对话框 - 集成AI代码生成功能"""
    try:
        from pywebio import output as pw_output
        from pywebio import input as pw_input
        
        ds_mgr = get_ds_manager()
        source = ds_mgr.get_source(source_id)
        
        if not source:
            ctx["toast"]("数据源不存在", color="error")
            return
        
        with ctx["popup"](f"编辑数据源: {source.name} (AI增强版)", size="large", closable=True):
            ctx["put_markdown"](f"### 编辑数据源: {source.name}")
            ctx["put_html"]("""
            <div style='background:#e3f2fd;padding:12px;border-radius:8px;margin-bottom:15px;'>
                <p style='color:#1565c0;font-size:14px;margin:0;'>
                    💡 <strong>AI代码生成</strong>：点击「AI生成」按钮，由AI根据需求描述自动生成数据获取代码
                </p>
                <p style='color:#1565c0;font-size:12px;margin:5px 0 0 0;'>
                    📝 <strong>代码审核</strong>：生成的代码需要您的审核和编辑确认
                </p>
            </div>
            """)
            
            # 基础信息编辑
            basic_form = await ctx["input_group"]("基础信息", [
                ctx["input"]("数据源名称", name="name", required=True, value=source.name),
                ctx["select"](
                    "数据源类型",
                    name="source_type",
                    options=[
                        {"label": "定时器 (Timer)", "value": "TIMER"},
                        {"label": "自定义 (Custom)", "value": "CUSTOM"},
                        {"label": "文件 (File)", "value": "FILE"},
                        {"label": "数据库 (Database)", "value": "DATABASE"},
                        {"label": "API接口 (API)", "value": "API"},
                        {"label": "消息队列 (Queue)", "value": "QUEUE"}
                    ],
                    value=source.metadata.source_type.value
                ),
                ctx["textarea"]("描述", name="description", placeholder="数据源描述（可选）", 
                               rows=2, value=source.metadata.description or ""),
                ctx["input"]("更新间隔 (秒)", name="interval", type="number", 
                           value=str(source.metadata.interval), help_text="数据更新间隔时间")
            ])
            
            if not basic_form:
                ctx["close_popup"]()
                return
            
            # 代码编辑选项
            ctx["put_markdown"]("### 代码编辑选项")
            
            # 显示当前代码
            current_code = source.metadata.data_func_code or ""
            if current_code:
                with ctx["put_collapse"]("📋 当前代码", open=False):
                    ctx["put_code"](current_code, language="python")
            
            code_edit_method = await ctx["radio"](
                "选择代码编辑方式",
                options=[
                    {"label": "🤖 AI智能生成 - 描述需求，AI自动生成代码", "value": "ai_generate"},
                    {"label": "✏️ 手动编辑 - 直接修改Python代码", "value": "manual_edit"},
                    {"label": "📋 从模板选择 - 选择预设代码模板", "value": "template_select"},
                    {"label": "📁 从文件导入 - 上传Python代码文件", "value": "file_import"},
                    {"label": "💾 保持现有代码 - 不修改代码", "value": "keep_existing"}
                ],
                value="keep_existing"
            )
            
            new_code = current_code
            
            if code_edit_method == "ai_generate":
                new_code = await _enhanced_datasource_ai_generation(ctx, basic_form)
            elif code_edit_method == "manual_edit":
                new_code = await _manual_datasource_code_edit(ctx, current_code)
            elif code_edit_method == "template_select":
                new_code = await _datasource_template_selection(ctx)
            elif code_edit_method == "file_import":
                new_code = await _datasource_file_import(ctx)
            
            if code_edit_method != "keep_existing" and not new_code:
                ctx["toast"]("代码编辑被取消", color="warning")
                return
            
            # 最终确认
            ctx["put_markdown"]("### 最终确认")
            ctx["put_info"](f"数据源名称: {basic_form['name']}")
            ctx["put_info"](f"数据源类型: {basic_form['source_type']}")
            
            if new_code != current_code:
                ctx["put_info"](f"代码长度: {len(new_code)} 字符")
                with ctx["put_collapse"]("预览新代码", open=False):
                    ctx["put_code"](new_code, language="python")
            else:
                ctx["put_info"]("代码未修改")
            
            final_confirm = await ctx["input_group"]("确认编辑", [
                ctx["checkbox"](
                    "确认选项",
                    name="confirmations",
                    options=[
                        {"label": "我已审核代码修改", "value": "code_reviewed", "selected": True},
                        {"label": "我理解代码的执行逻辑", "value": "logic_understood", "selected": True},
                        {"label": "我确认保存修改", "value": "save_approved", "selected": True}
                    ]
                ),
                ctx["actions"]("操作", [
                    {"label": "✅ 保存修改", "value": "save", "color": "success"},
                    {"label": "❌ 取消", "value": "cancel", "color": "danger"}
                ], name="action")
            ])
            
            if not final_confirm or final_confirm.get("action") != "save":
                return
            
            # 检查确认选项
            required_confirmations = ["code_reviewed", "save_approved"]
            selected_confirmations = final_confirm.get("confirmations", [])
            
            for req in required_confirmations:
                if req not in selected_confirmations:
                    ctx["toast"]("请确认所有必要选项", color="warning")
                    return
            
            # 更新数据源
            ds_mgr = get_ds_manager()
            source_type = DataSourceType(basic_form["source_type"])
            
            # 更新元数据
            source.metadata.name = basic_form["name"]
            source.metadata.description = basic_form.get("description", "")
            source.metadata.source_type = source_type
            source.metadata.interval = float(basic_form.get("interval", 5))
            
            if new_code != current_code:
                source.metadata.data_func_code = new_code
            
            # 保存修改
            source.save()
            
            ctx["toast"]("数据源修改保存成功", color="success")
            ctx["run_js"]("location.reload()")
            
    except Exception as e:
        log.error(f"增强版编辑数据源对话框错误: {e}")
        ctx["toast"](f"编辑数据源对话框错误: {e}", color="error")
        ctx["close_popup"]()


async def _manual_datasource_code_edit(ctx, current_code: str) -> str:
    """手动编辑数据源代码"""
    ctx["put_markdown"]("### 手动编辑代码")
    ctx["put_html"]("""
    <div style='background:#fff3e0;padding:12px;border-radius:8px;margin-bottom:15px;'>
        <p style='color:#e65100;font-size:14px;margin:0;'>
            💡 <strong>手动编辑代码</strong> - 请直接修改Python代码
        </p>
        <p style='color:#e65100;font-size:12px;margin:5px 0 0 0;'>
            📝 函数签名必须为: async def fetch_data():
        </p>
    </div>
    """)
    
    code_input = await ctx["input_group"]("代码编辑", [
        ctx["textarea"](
            "数据源代码",
            name="code",
            placeholder="async def fetch_data():\n    # 在这里输入您的数据源代码\n    # 返回获取的数据\n    return data",
            rows=12,
            required=True,
            value=current_code
        ),
        ctx["actions"]("操作", [
            {"label": "✅ 验证代码", "value": "validate"},
            {"label": "💾 保存代码", "value": "save"},
            {"label": "❌ 取消", "value": "cancel"}
        ], name="action")
    ])
    
    if not code_input or code_input.get("action") == "cancel":
        return current_code
    
    code = code_input["code"]
    
    if code_input.get("action") == "validate":
        # 验证代码
        validation = validate_datasource_code(code)
        if validation["valid"]:
            ctx["put_success"]("✅ 代码验证通过")
            use_code = await ctx["actions"]("是否使用此代码？", [
                {"label": "✅ 使用", "value": "yes"},
                {"label": "❌ 重新编辑", "value": "edit"}
            ])
            if use_code == "edit":
                return await _manual_datasource_code_edit(ctx, current_code)
        else:
            ctx["put_error"](f"❌ 代码验证失败: {'; '.join(validation['errors'])}")
            return await _manual_datasource_code_edit(ctx, current_code)
    
    return code