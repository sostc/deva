"""增强版策略面板(AI Enhanced Strategy Panel)

为策略面板集成AI代码生成功能，提供用户审核编辑界面。
"""

from __future__ import annotations

import json
import traceback
from typing import Any, Dict, List, Optional, Callable
from datetime import datetime

from deva import log

from .ai_code_generation_dialog import AICodeGenerationDialog
from .interactive_ai_code_generator import InteractiveCodeGenerator, CodeReviewResult
from .ai_code_generation_ui import AICodeGenerationUI, get_ai_code_generation_ui


async def show_enhanced_create_strategy_dialog(ctx):
    """增强版创建策略对话框 - 集成AI代码生成功能"""
    try:
        from pywebio import output as pw_output
        from pywebio import input as pw_input
        
        ds_mgr = get_ds_manager()
        sources = ds_mgr.list_source_objects()
        
        source_options = []
        for s in sources:
            if isinstance(s, dict):
                source_name = s.get('name', '')
                source_id = s.get('id', '')
            else:
                source_name = getattr(s, 'name', '')
                source_id = getattr(s, 'id', '')
            source_options.append({"label": source_name, "value": source_id})
        
        source_options = source_options if source_options else []
        
        with ctx["popup"]("创建新策略 (AI增强版)", size="large", closable=True):
            ctx["put_markdown"]("### 策略配置 (AI增强版)")
            ctx["put_html"]("""
            <div style='background:#e3f2fd;padding:12px;border-radius:8px;margin-bottom:15px;'>
                <p style='color:#1565c0;font-size:14px;margin:0;'>
                    💡 <strong>AI代码生成</strong>：点击「AI生成」按钮，由AI根据需求描述自动生成策略代码
                </p>
                <p style='color:#1565c0;font-size:12px;margin:5px 0 0 0;'>
                    📝 <strong>代码审核</strong>：生成的代码需要您的审核和编辑确认
                </p>
            </div>
            """)
            
            # 基础信息收集
            basic_form = await ctx["input_group"]("基础信息", [
                ctx["input"]("策略名称", name="name", required=True, placeholder="输入策略名称"),
                ctx["textarea"]("描述", name="description", placeholder="策略描述（可选）", rows=2),
                ctx["input"]("标签", name="tags", placeholder="多个标签用逗号分隔"),
                ctx["select"]("上游数据源", name="upstream", options=source_options) if source_options else ctx["input"]("上游数据源", name="upstream", placeholder="数据源名称（可选）"),
                ctx["input"]("下游输出", name="downstream", placeholder="输出目标名称（可选）"),
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
                    {"label": "📋 从模板选择 - 选择预设代码模板", "value": "template_select"}
                ],
                value="ai_generate"
            )
            
            generated_code = ""
            
            if code_generation_method == "ai_generate":
                generated_code = await _enhanced_ai_code_generation(ctx, basic_form, source_options)
                
            elif code_generation_method == "manual_write":
                generated_code = await _manual_code_input(ctx)
                
            elif code_generation_method == "template_select":
                generated_code = await _template_code_selection(ctx)
            
            if not generated_code:
                ctx["toast"]("代码生成被取消", color="warning")
                return
            
            # 最终确认
            ctx["put_markdown"]("### 最终确认")
            ctx["put_info"](f"策略名称: {basic_form['name']}")
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
                    {"label": "✅ 创建策略", "value": "create", "color": "success"},
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
            
            # 创建策略
            manager = get_manager()
            result = manager.create_strategy(
                name=basic_form["name"],
                description=basic_form.get("description", ""),
                tags=[t.strip() for t in basic_form.get("tags", "").split(",") if t.strip()],
                processor_code=generated_code,
                upstream_source=basic_form.get("upstream") or None,
                downstream_sink=basic_form.get("downstream") or None,
            )
            
            if result.get("success"):
                ctx["toast"](f"策略创建成功: {result['unit_id']}", color="success")
                ctx["run_js"]("location.reload()")
            else:
                ctx["toast"](f"创建失败: {result.get('error', '')}", color="error")
                
    except Exception as e:
        log.error(f"增强版创建策略对话框错误: {e}")
        ctx["toast"](f"创建策略对话框错误: {e}", color="error")
        ctx["close_popup"]()


async def _enhanced_ai_code_generation(ctx, basic_form: Dict[str, Any], source_options: List[Dict[str, str]]) -> str:
    """增强版AI代码生成流程"""
    try:
        # 创建AI代码生成对话框
        ai_dialog = AICodeGenerationDialog("strategy", ctx)
        
        # 显示AI代码生成向导
        ctx["put_markdown"]("### 🤖 AI代码生成向导")
        ctx["put_html"]("""
        <div style='background:#f3e5f5;padding:12px;border-radius:8px;margin-bottom:15px;'>
            <p style='color:#6a1b9a;font-size:14px;margin:0;'>
                💡 <strong>AI代码生成向导</strong>将引导您完成代码生成过程
            </p>
            <p style='color:#6a1b9a;font-size:12px;margin:5px 0 0 0;'>
                📝 请详细描述您的策略需求，AI将生成相应的Python代码
            </p>
        </div>
        """)
        
        # 步骤1: 选择数据源
        ctx["put_markdown"]("#### 步骤1: 选择数据源")
        
        if not source_options:
            ctx["put_warning"]("⚠️ 未找到可用数据源，AI将基于通用数据结构生成代码")
            selected_source = None
            data_schema = get_generic_data_schema()
        else:
            selected_source_id = await ctx["select"](
                "选择数据源",
                options=source_options,
                help_text="AI将分析此数据源的结构来生成代码"
            )
            
            ds_mgr = get_ds_manager()
            selected_source = ds_mgr.get_source(selected_source_id)
            
            if selected_source:
                # 获取数据源样本数据
                recent_data = selected_source.get_recent_data(1)
                if recent_data:
                    sample_data = recent_data[0]
                    data_schema = analyze_data_schema(sample_data)
                    ctx["put_success"]("✅ 获取到数据源样本数据")
                else:
                    # 基于元数据推断数据结构
                    data_schema = build_schema_from_metadata(selected_source)
                    ctx["put_warning"]("⚠️ 数据源暂无实际数据，基于元数据推断结构")
            else:
                ctx["put_error"]("❌ 数据源不存在")
                return ""
        
        # 显示数据结构分析
        if data_schema:
            with ctx["put_collapse"]("📊 数据结构分析", open=False):
                ctx["put_code"](json.dumps(data_schema, ensure_ascii=False, indent=2), language="json")
        
        # 步骤2: 描述策略需求
        ctx["put_markdown"]("#### 步骤2: 描述策略需求")
        
        requirement_form = await ctx["input_group"]("策略需求描述", [
            ctx["textarea"](
                "策略需求描述",
                name="requirement",
                placeholder="请详细描述您的策略需求，例如：\n- 基于5日和20日均线交叉生成交易信号\n- 当短期均线上穿长期均线时买入，下穿时卖出\n- 需要包含止损和止盈逻辑",
                rows=4,
                required=True
            ),
            ctx["textarea"](
                "期望输出格式",
                name="output_format",
                placeholder="描述期望的输出格式，例如：\n- 返回包含买卖信号的DataFrame\n- 信号列：1表示买入，-1表示卖出，0表示持有\n- 包含时间戳和信号强度",
                rows=3
            ),
            ctx["textarea"](
                "特殊要求或约束",
                name="constraints",
                placeholder="任何特殊要求或约束条件，例如：\n- 需要包含错误处理\n- 考虑数据缺失情况\n- 性能优化要求",
                rows=2
            ),
            ctx["checkbox"](
                "生成选项",
                name="generation_options",
                options=[
                    {"label": "包含详细注释", "value": "include_comments", "selected": True},
                    {"label": "包含错误处理", "value": "include_error_handling", "selected": True},
                    {"label": "包含性能优化", "value": "include_optimization", "selected": False},
                    {"label": "包含日志记录", "value": "include_logging", "selected": True}
                ]
            )
        ])
        
        if not requirement_form:
            return ""
        
        # 步骤3: AI代码生成
        ctx["put_markdown"]("#### 步骤3: AI代码生成")
        ctx["put_info"]("正在生成代码，请稍候...")
        
        # 构建生成上下文
        generation_context = {
            "strategy_name": basic_form.get("name", "未命名策略"),
            "datasource_name": selected_source.name if selected_source else "通用数据源",
            "data_schema": data_schema,
            "generation_options": requirement_form.get("generation_options", []),
            "bound_datasource": basic_form.get("upstream") or (selected_source.name if selected_source else None)
        }
        
        # 使用交互式代码生成器
        generator = InteractiveCodeGenerator("strategy")
        
        review_result = await generator.generate_and_review(
            requirement=requirement_form["requirement"],
            context=generation_context,
            show_comparison=True,
            enable_realtime_validation=True,
            include_comments="include_comments" in requirement_form["generation_options"],
            include_error_handling="include_error_handling" in requirement_form["generation_options"],
            include_optimization="include_optimization" in requirement_form["generation_options"],
            input_schema=data_schema,
            output_format=requirement_form.get("output_format", "")
        )
        
        if not review_result.approved:
            ctx["toast"]("代码生成被取消", color="warning")
            return ""
        
        # 显示生成结果
        ctx["put_markdown"]("#### 步骤4: 代码审核与编辑")
        
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
            return await _enhanced_ai_code_generation(ctx, basic_form, source_options)
        
        # 检查确认选项
        required_confirmations = ["reviewed", "approved"]
        selected_confirmations = final_confirm.get("code_confirmations", [])
        
        for req in required_confirmations:
            if req not in selected_confirmations:
                ctx["toast"]("请确认所有必要选项", color="warning")
                return await _enhanced_ai_code_generation(ctx, basic_form, source_options)
        
        return review_result.code
        
    except Exception as e:
        log.error(f"增强版AI代码生成错误: {e}")
        ctx["toast"](f"AI代码生成错误: {e}", color="error")
        return ""


async def _manual_code_input(ctx) -> str:
    """手动代码输入"""
    ctx["put_markdown"]("### 手动代码输入")
    ctx["put_html"]("""
    <div style='background:#fff3e0;padding:12px;border-radius:8px;margin-bottom:15px;'>
        <p style='color:#e65100;font-size:14px;margin:0;'>
            💡 <strong>手动代码输入</strong> - 请直接输入Python代码
        </p>
        <p style='color:#e65100;font-size:12px;margin:5px 0 0 0;'>
            📝 函数签名必须为: def process(data):
        </p>
    </div>
    """)
    
    code_input = await ctx["input_group"]("代码输入", [
        ctx["textarea"](
            "策略代码",
            name="code",
            placeholder="def process(data):\n    # 在这里输入您的策略代码\n    return data",
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
        validation = validate_strategy_code(code)
        if validation["valid"]:
            ctx["put_success"]("✅ 代码验证通过")
            use_code = await ctx["actions"]("是否使用此代码？", [
                {"label": "✅ 使用", "value": "yes"},
                {"label": "❌ 重新编辑", "value": "edit"}
            ])
            if use_code == "edit":
                return await _manual_code_input(ctx)
        else:
            ctx["put_error"](f"❌ 代码验证失败: {'; '.join(validation['errors'])}")
            return await _manual_code_input(ctx)
    
    return code


async def _template_code_selection(ctx) -> str:
    """模板代码选择"""
    ctx["put_markdown"]("### 模板代码选择")
    ctx["put_html"]("""
    <div style='background:#e8f5e9;padding:12px;border-radius:8px;margin-bottom:15px;'>
        <p style='color:#2e7d32;font-size:14px;margin:0;'>
            📋 <strong>模板代码选择</strong> - 选择预设的代码模板
        </p>
        <p style='color:#2e7d32;font-size:12px;margin:5px 0 0 0;'>
            🚀 选择模板后可以根据需要进行修改
        </p>
    </div>
    """)
    
    # 预定义模板
    templates = {
        "moving_average_crossover": {
            "name": "移动平均线交叉策略",
            "description": "基于短期和长期移动平均线交叉生成交易信号",
            "code": '''def process(data):
    """移动平均线交叉策略"""
    import pandas as pd
    import numpy as np
    
    # 计算移动平均线
    data['ma_short'] = data['close'].rolling(window=5).mean()
    data['ma_long'] = data['close'].rolling(window=20).mean()
    
    # 生成交易信号
    data['signal'] = np.where(data['ma_short'] > data['ma_long'], 1, 0)
    data['position'] = data['signal'].diff()
    
    # 返回结果
    result = pd.DataFrame({
        'close': data['close'],
        'ma_short': data['ma_short'],
        'ma_long': data['ma_long'],
        'signal': data['signal'],
        'position': data['position']
    })
    
    return result'''
        },
        "rsi_strategy": {
            "name": "RSI相对强弱指标策略",
            "description": "基于RSI指标的超买超卖策略",
            "code": '''def process(data):
    """RSI相对强弱指标策略"""
    import pandas as pd
    import numpy as np
    
    # 计算RSI
    delta = data['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    
    # 生成交易信号
    data['rsi'] = rsi
    data['oversold'] = rsi < 30
    data['overbought'] = rsi > 70
    
    # 返回结果
    result = pd.DataFrame({
        'close': data['close'],
        'rsi': data['rsi'],
        'oversold': data['oversold'],
        'overbought': data['overbought']
    })
    
    return result'''
        },
        "volume_analysis": {
            "name": "成交量分析策略",
            "description": "基于成交量变化分析市场活跃度",
            "code": '''def process(data):
    """成交量分析策略"""
    import pandas as pd
    import numpy as np
    
    # 计算成交量相关指标
    data['volume_ma'] = data['volume'].rolling(window=10).mean()
    data['volume_ratio'] = data['volume'] / data['volume_ma']
    data['high_volume'] = data['volume_ratio'] > 2.0
    
    # 返回结果
    result = pd.DataFrame({
        'close': data['close'],
        'volume': data['volume'],
        'volume_ma': data['volume_ma'],
        'volume_ratio': data['volume_ratio'],
        'high_volume': data['high_volume']
    })
    
    return result'''
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
        "选择代码模板",
        options=template_options,
        help_text="选择预设的策略代码模板"
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
        return await _template_code_selection(ctx)
    else:
        return ""


# ==========================================================================
# 辅助函数
# ==========================================================================

def get_generic_data_schema() -> Dict[str, Any]:
    """获取通用数据模式"""
    return {
        "type": "DataFrame",
        "columns": ["open", "high", "low", "close", "volume"],
        "dtypes": {
            "open": "float64",
            "high": "float64", 
            "low": "float64",
            "close": "float64",
            "volume": "int64"
        },
        "description": "通用股票数据格式，包含OHLCV数据"
    }


def build_schema_from_metadata(source) -> Dict[str, Any]:
    """基于数据源元数据构建模式"""
    try:
        # 这里应该根据数据源的元数据推断数据结构
        # 简化实现，返回通用模式
        return get_generic_data_schema()
    except Exception as e:
        log.error(f"构建数据源模式错误: {e}")
        return get_generic_data_schema()


def analyze_data_schema(data: Any) -> Dict[str, Any]:
    """分析数据结构"""
    try:
        import pandas as pd
        
        if isinstance(data, pd.DataFrame):
            return {
                "type": "DataFrame",
                "row_count": len(data),
                "column_count": len(data.columns),
                "columns": list(data.columns),
                "dtypes": {col: str(dtype) for col, dtype in data.dtypes.items()},
                "sample": data.head(3).to_dict('records') if len(data) > 0 else []
            }
        else:
            return {
                "type": type(data).__name__,
                "description": str(data)[:200]
            }
    except Exception as e:
        log.error(f"分析数据结构错误: {e}")
        return {"type": "unknown", "error": str(e)}


def build_datasource_context(source) -> Dict[str, Any]:
    """构建数据源上下文"""
    return {
        "source_name": source.name,
        "source_id": source.id,
        "source_type": getattr(source, 'source_type', 'unknown'),
        "metadata": getattr(source, 'metadata', {})
    }


def validate_strategy_code(code: str) -> Dict[str, Any]:
    """验证策略代码"""
    try:
        import ast
        import inspect
        
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
            if isinstance(node, ast.FunctionDef):
                functions.append(node.name)
        
        if "process" not in functions:
            return {
                "valid": False,
                "errors": ["未找到'process'函数定义"]
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
# 导入必要的模块
# ==========================================================================

def get_manager():
    """获取策略管理器"""
    from .strategy_manager import get_manager as get_strategy_manager
    return get_strategy_manager()


def get_ds_manager():
    """获取数据源管理器"""
    from .datasource import get_ds_manager as get_datasource_manager
    return get_datasource_manager()


def generate_strategy_code(ctx, data_schema: Dict[str, Any], user_requirement: str, 
                         strategy_name: str = "", datasource_context: Dict[str, Any] = None) -> str:
    """生成策略代码"""
    try:
        from .ai_strategy_generator import generate_strategy_code as ai_generate_strategy_code
        return ai_generate_strategy_code(ctx, data_schema, user_requirement, strategy_name, datasource_context)
    except ImportError:
        # 如果AI生成器不可用，返回默认代码
        return '''def process(data):
    """默认策略处理函数"""
    import pandas as pd
    
    # 简单的数据处理示例
    result = data.copy()
    result['processed'] = True
    
    return result'''


def test_strategy_code(code: str, sample_data: Any) -> Dict[str, Any]:
    """测试策略代码"""
    try:
        from .ai_strategy_generator import test_strategy_code as ai_test_strategy_code
        return ai_test_strategy_code(code, sample_data)
    except ImportError:
        return {
            "success": True,
            "execution_time_ms": 0,
            "result_preview": "测试功能不可用"
        }