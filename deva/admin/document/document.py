import asyncio
import html
import inspect
import pkgutil
import re
import time
from pathlib import Path


DOCUMENT_MODULE_WHITELIST = {
    'core', 'pipe', 'store', 'sources', 'when', 'namespace', 'bus',
    'endpoints', 'compute', 'search', 'browser',
    'page', 'lambdas', 'admin', 'llm', 'admin', 'page_ui',
}


def document_module_allowed(module_name):
    return module_name in DOCUMENT_MODULE_WHITELIST


def extract_doc_examples(doc):
    if not isinstance(doc, str) or '>>>' not in doc:
        return []
    blocks = []
    current = []
    for line in doc.splitlines():
        s = line.strip()
        if s.startswith('>>>') or s.startswith('...'):
            current.append(re.sub(r'^(>>>|\.\.\.)\s?', '', s))
        else:
            if current:
                blocks.append('\n'.join(current))
                current = []
    if current:
        blocks.append('\n'.join(current))
    return blocks


def mask_attr_value(attr_name, value, limit=100):
    sensitive_keywords = ('key', 'token', 'secret', 'password', 'passwd', 'credential')
    attr_lower = (attr_name or '').lower()
    if any(k in attr_lower for k in sensitive_keywords):
        return '[MASKED]'
    text = str(value)
    if any(k in text.lower() for k in sensitive_keywords):
        return '[MASKED]'
    return text[:limit]


def callable_smoke_eligibility(obj):
    if not callable(obj) or isinstance(obj, type):
        return False, '仅支持函数/可调用对象的自动测试，类不自动执行'
    try:
        sig = inspect.signature(obj)
    except Exception:
        return False, '无法解析函数签名'
    required = [
        p for p in sig.parameters.values()
        if p.default is inspect._empty and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
    ]
    if required:
        return False, f"函数需要参数：{', '.join(p.name for p in required)}"
    return True, 'ok'


async def run_object_smoke_test(module_name, obj_name, obj, examples, *, toast, popup, put_markdown, put_table):
    ok, reason = callable_smoke_eligibility(obj)
    if not ok:
        toast(f'跳过测试：{obj_name} ({reason})', color='warning')
        return
    try:
        if inspect.iscoroutinefunction(obj):
            result = await asyncio.wait_for(obj(), timeout=5)
        else:
            result = await asyncio.wait_for(asyncio.to_thread(obj), timeout=5)
        popup(
            title=f"测试结果：{module_name}.{obj_name}",
            content=[
                put_markdown('### 执行成功'),
                put_table([['返回值类型', type(result).__name__], ['返回值', str(result)[:500]]]),
                put_markdown('### 文档样例'),
                put_markdown('\n\n'.join(f'```python\\n{e}\\n```' for e in examples[:3]) if examples else '无样例'),
            ],
            size='large'
        )
    except Exception as e:
        popup(
            title=f"测试失败：{module_name}.{obj_name}",
            content=[
                put_markdown('### 执行失败'),
                put_markdown(f'`{type(e).__name__}`: {str(e)}'),
                put_markdown('### 文档样例'),
                put_markdown('\n\n'.join(f'```python\\n{e}\\n```' for e in examples[:3]) if examples else '无样例'),
            ],
            size='large'
        )


def scan_document_modules(*, cache, cache_ttl, warn):
    now = time.time()
    if cache.get('data') is not None and now - cache.get('ts', 0) < cache_ttl:
        return cache['data']

    import deva
    module_data = []
    for module_info in pkgutil.iter_modules(deva.__path__):
        module_name = module_info.name
        if module_name not in DOCUMENT_MODULE_WHITELIST:
            continue
        try:
            module = __import__(f'deva.{module_name}', fromlist=['*'])
            members = inspect.getmembers(module)
            global_vars = {k: v for k, v in module.__dict__.items() if not k.startswith('__') and not inspect.ismodule(v)}
            all_objects = {**dict(members), **global_vars}
            objects = []
            for name, obj in all_objects.items():
                if name.startswith('_'):
                    continue
                if not (inspect.isclass(obj) or inspect.isfunction(obj) or hasattr(obj, '__wrapped__') or not inspect.ismodule(obj)):
                    continue
                doc = obj.__doc__ or '无文档说明'
                if hasattr(obj, '__wrapped__'):
                    doc = obj.__wrapped__.__doc__ or doc
                if not isinstance(doc, str):
                    doc = '无文档说明'
                if inspect.isclass(obj):
                    obj_type = '类'
                elif inspect.isfunction(obj) or hasattr(obj, '__wrapped__'):
                    obj_type = '函数'
                else:
                    obj_type = '全局对象'
                objects.append({'name': name, 'type': obj_type, 'doc': doc[:200], 'obj': obj, 'examples': extract_doc_examples(doc)})
            module_data.append({'module_name': module_name, 'objects': objects, 'error': None})
        except Exception as e:
            module_data.append({'module_name': module_name, 'objects': [], 'error': f"{type(e).__name__}: {str(e)}"})
            warn(f"无法导入模块 {module_name}: {e}")

    cache['ts'] = now
    cache['data'] = module_data
    return module_data


def inspect_object_ui(ctx, obj):
    put_markdown = ctx['put_markdown']
    put_table = ctx['put_table']
    put_text = ctx['put_text']
    popup = ctx['popup']
    mask_attr_value_func = ctx['mask_attr_value']
    extract_doc_examples_func = ctx['extract_doc_examples']

    content = []
    content.append(put_markdown("### 对象信息"))
    content.append(put_table([
        ['类型', type(obj).__name__],
        ['ID', id(obj)],
        ['哈希值', hash(obj) if not isinstance(obj, dict) else 'N/A (字典不可哈希)'],
        ['可调用', callable(obj)]
    ]))

    if obj.__doc__:
        content.append(put_markdown("#### 文档说明"))
        doc_lines = obj.__doc__.split('\n')
        formatted_doc = []
        in_code_block = False
        for line in doc_lines:
            if line.strip().startswith('>>>') or line.strip().startswith('...'):
                if not in_code_block:
                    formatted_doc.append('```python')
                    in_code_block = True
                formatted_doc.append(line)
            else:
                if in_code_block:
                    formatted_doc.append('```')
                    in_code_block = False
                formatted_doc.append(line)
        if in_code_block:
            formatted_doc.append('```')
        content.append(put_markdown('\n'.join(formatted_doc)))

    examples = extract_doc_examples_func(obj.__doc__ or '')
    content.append(put_markdown("#### 样例"))
    if examples:
        content.append(put_markdown('\n\n'.join(f'```python\n{e}\n```' for e in examples[:5])))
    else:
        content.append(put_text('无可解析样例'))

    content.append(put_markdown("#### 属性"))
    attrs = []
    for attr in dir(obj):
        if attr.startswith('__'):
            continue
        try:
            value = getattr(obj, attr)
            if not callable(value):
                attrs.append([attr, type(value).__name__, mask_attr_value_func(attr, value)])
        except Exception as e:
            attrs.append([attr, '无法访问', str(e)])
    content.append(put_table([['属性名', '类型', '值']] + attrs))

    content.append(put_markdown("#### 方法"))
    methods = []
    for attr in dir(obj):
        if attr.startswith('__'):
            continue
        try:
            value = getattr(obj, attr)
            if callable(value):
                doc = value.__doc__ or '无文档说明'
                methods.append([attr, doc[:200]])
        except Exception as e:
            methods.append([attr, f'无法访问：{str(e)}'])
    content.append(put_table([['方法名', '文档说明']] + methods))
    popup(title="对象详情", content=content, size='large')


def _resolve_source_files(source_dir):
    if not source_dir.exists():
        return {}
    resolved = {}
    for p in source_dir.iterdir():
        resolved[p.name.strip().lower()] = p
    return resolved


def _load_document_file(filename):
    """Load a specific document file from the source directory."""
    root = Path(__file__).resolve().parents[2]
    source_dir = root / "source"
    
    # Try source directory first
    path = source_dir / filename
    if path.exists():
        try:
            text = path.read_text(encoding="utf-8", errors="ignore").strip()
            if text:
                return text, str(path)
        except Exception:
            pass
    
    # Fallback to root directory
    path = root / filename
    if path.exists():
        try:
            text = path.read_text(encoding="utf-8", errors="ignore").strip()
            if text:
                return text, str(path)
        except Exception:
            pass
    
    return "", ""


def _load_all_documents():
    """Load all documentation files."""
    documents = {}
    
    # Document files to load (filename, tab_title)
    doc_files = [
        ("quickstart.rst", "快速开始"),
        ("installation.rst", "安装指南"),
        ("usage.rst", "使用指南"),
        ("best_practices.rst", "最佳实践"),
        ("troubleshooting.rst", "故障排查"),
        ("api.rst", "API 参考"),
        ("glossary.rst", "术语表"),
    ]
    
    for filename, title in doc_files:
        text, path = _load_document_file(filename)
        if text:
            documents[filename] = {
                'title': title,
                'content': text,
                'path': path
            }
    
    return documents


def _render_rst_to_html(rst_text, source_path):
    try:
        from docutils.core import publish_parts

        parts = publish_parts(
            source=rst_text,
            source_path=source_path or None,
            writer_name="html5",
            settings_overrides={
                "input_encoding": "utf-8",
                "doctitle_xform": False,
                "file_insertion_enabled": False,
                "raw_enabled": False,
                "report_level": 5,
                "halt_level": 6,
                "syntax_highlight": "short",
            },
        )
        html_body = parts.get("html_body") or parts.get("body") or ""
        if html_body.strip():
            return html_body, None
        return "", "RST 渲染结果为空"
    except Exception as e:
        return "", f"{type(e).__name__}: {e}"


def _build_document_tab(ctx, filename, doc_info):
    """Build a tab for a specific document."""
    put_html = ctx["put_html"]
    put_markdown = ctx["put_markdown"]
    put_text = ctx["put_text"]
    
    rendered_html, render_error = _render_rst_to_html(doc_info['content'], doc_info['path'])
    
    if render_error:
        body = (
            '<div style="padding:12px;border:1px solid #f5c2c7;background:#fff5f5;color:#842029;border-radius:6px;margin-bottom:12px;">'
            f'RST 渲染失败，已降级为源码显示：{html.escape(render_error)}'
            "</div>"
            f"<pre style='white-space:pre-wrap;line-height:1.6'>{html.escape(doc_info['content'])}</pre>"
        )
    else:
        body = rendered_html

    doc_style = """
    <style>
      .admin-rst-doc { max-width: 980px; margin: 0 auto; line-height: 1.8; font-size: 15px; color: #222; }
      .admin-rst-doc h1, .admin-rst-doc h2, .admin-rst-doc h3 { margin-top: 1.2em; margin-bottom: 0.5em; }
      .admin-rst-doc code, .admin-rst-doc tt { background: #f6f8fa; padding: 1px 4px; border-radius: 4px; }
      .admin-rst-doc pre { background: #f6f8fa; border: 1px solid #e5e7eb; border-radius: 8px; padding: 12px; overflow-x: auto; }
      .admin-rst-doc img { max-width: 100%; height: auto; border-radius: 6px; }
      .admin-rst-doc table { border-collapse: collapse; width: 100%; }
      .admin-rst-doc th, .admin-rst-doc td { border: 1px solid #ddd; padding: 6px 8px; text-align: left; }
      .admin-rst-doc blockquote { margin: 8px 0; padding-left: 12px; border-left: 3px solid #ddd; color: #555; }
      .admin-doc-toc { background: #f8f9fa; padding: 15px; border-radius: 8px; margin: 20px 0; }
      .admin-doc-toc ul { list-style: none; padding-left: 0; }
      .admin-doc-toc li { margin: 8px 0; }
      .admin-doc-toc a { color: #0366d6; text-decoration: none; }
      .admin-doc-toc a:hover { text-decoration: underline; }
    </style>
    """
    
    rendered = (
        doc_style
        + "<div class='admin-rst-doc'>"
        + f"<div style='color:#6b7280;font-size:12px;margin-bottom:10px'>来源：{html.escape(doc_info['path'])}</div>"
        + body
        + "</div>"
    )
    
    return {
        "title": doc_info['title'],
        "content": put_html(rendered),
    }


def _build_examples_tab(ctx):
    """Build the examples documentation tab."""
    put_html = ctx["put_html"]
    put_markdown = ctx["put_markdown"]
    put_table = ctx["put_table"]
    put_button = ctx["put_button"]
    run_async = ctx["run_async"]
    
    # Load examples README
    root = Path(__file__).resolve().parents[2]
    examples_readme = root / "deva" / "examples" / "README.md"
    
    if not examples_readme.exists():
        return {
            "title": "示例文档",
            "content": put_markdown("未找到示例文档（期望 deva/examples/README.md）。")
        }
    
    try:
        md_content = examples_readme.read_text(encoding="utf-8", errors="ignore")
        
        # Simple markdown to HTML conversion
        html_content = md_content
        html_content = re.sub(r'^### (.*?)$', r'<h3>\1</h3>', html_content, flags=re.MULTILINE)
        html_content = re.sub(r'^## (.*?)$', r'<h2>\1</h2>', html_content, flags=re.MULTILINE)
        html_content = re.sub(r'^# (.*?)$', r'<h1>\1</h1>', html_content, flags=re.MULTILINE)
        html_content = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', html_content)
        html_content = re.sub(r'`([^`]+)`', r'<code>\1</code>', html_content)
        html_content = re.sub(r'\n```(\w*)\n(.*?)\n```', r'<pre><code>\2</code></pre>', html_content, flags=re.DOTALL)
        html_content = re.sub(r'\n- (.*?)(?=\n|$)', r'<li>\1</li>', html_content)
        html_content = re.sub(r'(\n\d+\.) (.*?)(?=\n|$)', r'<li>\2</li>', html_content)
        html_content = re.sub(r'\[([^\]]+)\]\(([^\)]+)\)', r'<a href="\2" target="_blank">\1</a>', html_content)
        
        rendered = f"""
        <style>
          .admin-examples-doc {{ max-width: 1000px; margin: 0 auto; line-height: 1.8; font-size: 15px; color: #222; }}
          .admin-examples-doc h1, .admin-examples-doc h2, .admin-examples-doc h3 {{ margin-top: 1.2em; margin-bottom: 0.5em; }}
          .admin-examples-doc code {{ background: #f6f8fa; padding: 1px 4px; border-radius: 4px; }}
          .admin-examples-doc pre {{ background: #f6f8fa; border: 1px solid #e5e7eb; border-radius: 8px; padding: 12px; overflow-x: auto; }}
          .admin-examples-doc table {{ border-collapse: collapse; width: 100%; margin: 15px 0; }}
          .admin-examples-doc th, .admin-examples-doc td {{ border: 1px solid #ddd; padding: 8px 10px; text-align: left; }}
          .admin-examples-doc th {{ background: #f8fafc; font-weight: 600; }}
          .admin-examples-doc a {{ color: #0366d6; text-decoration: none; }}
          .admin-examples-doc a:hover {{ text-decoration: underline; }}
        </style>
        <div class='admin-examples-doc'>
        <h1>📚 示例文档集合</h1>
        {html_content}
        </div>
        """
        
        return {
            "title": "示例文档",
            "content": put_html(rendered),
        }
    except Exception as e:
        return {
            "title": "示例文档",
            "content": put_markdown(f"加载示例文档失败：{e}")
        }


def _build_optimization_report_tab(ctx):
    """Build the documentation optimization report tab."""
    put_html = ctx["put_html"]
    put_markdown = ctx["put_markdown"]
    
    root = Path(__file__).resolve().parents[2]
    report_file = root / "DOCUMENTATION_OPTIMIZATION_SUMMARY.md"
    
    if not report_file.exists():
        return {
            "title": "文档优化报告",
            "content": put_markdown("未找到文档优化报告。")
        }
    
    try:
        md_content = report_file.read_text(encoding="utf-8", errors="ignore")
        
        # Simple markdown to HTML conversion
        html_content = md_content
        html_content = re.sub(r'^### (.*?)$', r'<h3>\1</h3>', html_content, flags=re.MULTILINE)
        html_content = re.sub(r'^## (.*?)$', r'<h2>\1</h2>', html_content, flags=re.MULTILINE)
        html_content = re.sub(r'^# (.*?)$', r'<h1>\1</h1>', html_content, flags=re.MULTILINE)
        html_content = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', html_content)
        html_content = re.sub(r'`([^`]+)`', r'<code>\1</code>', html_content)
        html_content = re.sub(r'\n```(\w*)\n(.*?)\n```', r'<pre><code>\2</code></pre>', html_content, flags=re.DOTALL)
        html_content = re.sub(r'- (.*?)(?=\n|$)', r'<li>\1</li>', html_content)
        html_content = re.sub(r'\[([^\]]+)\]\(([^\)]+)\)', r'<a href="\2" target="_blank">\1</a>', html_content)
        html_content = re.sub(r'✅', '<span style="color:#22c55e">✅</span>', html_content)
        html_content = re.sub(r'❌', '<span style="color:#ef4444">❌</span>', html_content)
        
        rendered = f"""
        <style>
          .admin-report-doc {{ max-width: 1000px; margin: 0 auto; line-height: 1.8; font-size: 14px; color: #222; }}
          .admin-report-doc h1 {{ font-size: 24px; border-bottom: 2px solid #e5e7eb; padding-bottom: 10px; }}
          .admin-report-doc h2 {{ font-size: 20px; border-bottom: 1px solid #e5e7eb; padding-bottom: 8px; margin-top: 20px; }}
          .admin-report-doc code {{ background: #f6f8fa; padding: 2px 5px; border-radius: 4px; }}
          .admin-report-doc pre {{ background: #f6f8fa; border: 1px solid #e5e7eb; border-radius: 8px; padding: 12px; overflow-x: auto; font-size: 13px; }}
          .admin-report-doc table {{ border-collapse: collapse; width: 100%; margin: 15px 0; }}
          .admin-report-doc th, .admin-report-doc td {{ border: 1px solid #ddd; padding: 8px 10px; text-align: left; }}
          .admin-report-doc th {{ background: #f8fafc; font-weight: 600; }}
          .admin-report-doc a {{ color: #0366d6; text-decoration: none; }}
          .admin-report-doc a:hover {{ text-decoration: underline; }}
        </style>
        <div class='admin-report-doc'>
        {html_content}
        </div>
        """
        
        return {
            "title": "文档优化报告",
            "content": put_html(rendered),
        }
    except Exception as e:
        return {
            "title": "文档优化报告",
            "content": put_markdown(f"加载报告失败：{e}")
        }


def _build_admin_docs_tab(ctx):
    """Build the Admin UI documentation tab."""
    import os
    
    docs_dir = os.path.join(os.path.dirname(__file__), '..')
    project_root = os.path.join(docs_dir, '..', '..')
    docs_root = os.path.join(project_root, 'docs')
    examples_root = os.path.join(docs_dir, 'examples')
    
    # All documentation files
    doc_files = [
        # Admin UI docs
        ('📘 Admin 模块文档', os.path.join(docs_dir, 'README.md')),
        ('📖 UI 使用指南', os.path.join(docs_dir, 'UI_GUIDE.md')),
        ('📝 重构总结', os.path.join(docs_dir, 'REFACTORING_SUMMARY.md')),
        ('📋 菜单重构', os.path.join(docs_dir, 'menus', 'REFACTORING.md')),
        ('🔧 文档集成', os.path.join(docs_dir, 'DOCS_INTEGRATION.md')),
        
        # Project core docs
        ('📚 项目文档', os.path.join(docs_root, 'README.md')),
        ('🚀 快速开始', os.path.join(docs_root, 'guides', 'quickstart.md')),
        ('📦 安装指南', os.path.join(project_root, 'source', 'installation.rst')),
        ('📖 使用手册', os.path.join(project_root, 'source', 'usage.rst')),
        ('🔧 故障排查', os.path.join(project_root, 'source', 'troubleshooting.rst')),
        ('📊 最佳实践', os.path.join(project_root, 'source', 'best_practices.rst')),
        
        # AI docs
        ('🤖 AI 中心指南', os.path.join(docs_root, 'guides', 'ai', 'AI_CENTER_GUIDE.md')),
        ('🎨 AI Studio', os.path.join(docs_root, 'ai', 'AI_STUDIO_INTEGRATION.md')),
        ('💻 AI 代码生成', os.path.join(docs_root, 'ai', 'AI_CODE_CREATOR_GUIDE.md')),
        
        # Strategy docs
        ('📈 策略指南', os.path.join(docs_root, 'admin', 'strategy_guide.md')),
        ('📡 数据源指南', os.path.join(docs_root, 'admin', 'datasource_guide.md')),
        ('⏰ 任务指南', os.path.join(docs_root, 'admin', 'task_guide.md')),
        
        # Core modules docs
        ('🌊 流计算指南', os.path.join(examples_root, 'README.md')),
        ('🚌 Bus 总线', os.path.join(examples_root, 'bus', 'README.md')),
        ('💾 存储回放', os.path.join(examples_root, 'storage', 'README.md')),
        ('⏰ 定时器', os.path.join(examples_root, 'when', 'timer', 'README.md')),
        ('📅 调度器', os.path.join(examples_root, 'when', 'scheduler', 'README.md')),
        ('🌐 Web 可视化', os.path.join(examples_root, 'webview', 'stream_page', 'README.md')),
        ('📡 SSE 推送', os.path.join(examples_root, 'sse', 'README.md')),
        ('🔍 全文检索', os.path.join(examples_root, 'search', 'README.md')),
        ('🕵️ 日志监控', os.path.join(examples_root, 'log_watchdog', 'README.md')),
        
        # Reports
        ('📋 集成报告', os.path.join(docs_root, 'reports', 'integration', 'INTEGRATION_COMPLETE_REPORT.md')),
        ('✅ 最终报告', os.path.join(docs_root, 'reports', 'integration', 'FINAL_INTEGRATION_SUCCESS_REPORT.md')),
    ]
    
    # Read documentation files
    docs = {}
    for name, path in doc_files:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                docs[name] = f.read()
        except Exception as e:
            docs[name] = f"加载失败：{e}"
    
    # Build tab content with collapsible sections
    content = []
    content.append(ctx['put_markdown']("### 📚 Deva 完整文档中心"))
    content.append(ctx['put_markdown']("""
欢迎使用 Deva 完整文档中心！这里包含了 Deva 平台的所有重要文档。

**文档分类**：
- 📘 **Admin UI 文档** - Admin 模块的完整文档
- 📚 **项目文档** - 项目整体说明和指南
- 🤖 **AI 相关文档** - AI 功能中心、AI Studio、代码生成
- 📈 **业务指南** - 策略、数据源、任务等业务模块
- 🌊 **核心模块** - 流计算、Bus、存储、定时器等核心功能
- 📋 **技术报告** - 集成报告、技术文档
    """))
    
    # Group documents by category
    categories = {
        '📘 Admin UI 文档': ['📘 Admin 模块文档', '📖 UI 使用指南', '📝 重构总结', '📋 菜单重构', '🔧 文档集成'],
        '📚 项目文档': ['📚 项目文档', '🚀 快速开始', '📦 安装指南', '📖 使用手册', '🔧 故障排查', '📊 最佳实践'],
        '🤖 AI 相关文档': ['🤖 AI 中心指南', '🎨 AI Studio', '💻 AI 代码生成'],
        '📈 业务指南': ['📈 策略指南', '📡 数据源指南', '⏰ 任务指南'],
        '🌊 核心模块文档': ['🌊 流计算指南', '🚌 Bus 总线', '💾 存储回放', '⏰ 定时器', '📅 调度器', '🌐 Web 可视化', '📡 SSE 推送', '🔍 全文检索', '🕵️ 日志监控'],
        '📋 技术报告': ['📋 集成报告', '✅ 最终报告'],
    }
    
    # Add documents by category
    for category, doc_names in categories.items():
        content.append(ctx['put_markdown'](f"\n---\n\n## {category}"))
        
        for doc_name in doc_names:
            if doc_name in docs:
                doc_content = docs[doc_name]
                content.append(ctx['put_markdown'](f"### {doc_name}"))
                
                # Show preview (first 2000 chars)
                preview = doc_content[:2000] if len(doc_content) > 2000 else doc_content
                content.append(ctx['put_markdown'](f"``````markdown\n{preview}\n{'...（文档过长，仅显示前 2000 字符）' if len(doc_content) > 2000 else ''}\n``````"))
    
    # Add summary section
    content.append(ctx['put_markdown']("\n---\n\n### 📄 完整文档文件位置"))
    content.append(ctx['put_markdown']("""
所有文档文件位于以下目录：

| 分类 | 目录路径 |
|------|---------|
| 📘 Admin 文档 | `deva/admin/` |
| 📚 项目文档 | `docs/`, `source/` |
| 🤖 AI 相关文档 | `docs/ai/`, `docs/guides/ai/` |
| 📈 业务指南 | `docs/admin/` |
| 🌊 核心模块文档 | `deva/examples/` |
| 📋 技术报告 | `docs/reports/` |
    """))
    
    content.append(ctx['put_markdown']("\n### 🎯 文档内容概览"))
    content.append(ctx['put_markdown']("""
#### 📘 Admin 文档
- Admin 模块结构和分层架构
- 10 个不依赖 UI 的核心库
- 完整的 API 参考和使用示例
- UI 界面操作指南
- 重构总结和架构分析

#### 📚 项目文档
- 项目简介和快速开始
- 安装指南和配置说明
- 使用手册和最佳实践
- 故障排查指南

#### 🤖 AI 相关文档
- AI 功能中心使用指南
- AI Studio 集成说明
- AI 代码生成器使用教程

#### 📈 业务指南
- 量化策略开发指南
- 数据源配置和管理
- 定时任务管理

#### 🌊 核心模块文档
- **流计算** - Stream 实时数据处理
- **Bus 总线** - 跨进程消息传递
- **存储回放** - 数据持久化和事件回放
- **定时器** - 定时任务和周期执行
- **调度器** - 计划任务和 CRON 调度
- **Web 可视化** - 实时数据流 Web 展示
- **SSE 推送** - Server-Sent Events 服务器推送
- **全文检索** - 基于 Whoosh 的流式搜索
- **日志监控** - 实时日志监控和告警

#### 📋 技术报告
- 模块集成报告
- 技术实现文档
- 功能增强报告
    """))
    
    return {
        "title": "📚 Deva 文档",
        "content": content
    }


def _build_core_libraries_tab(ctx):
    """Build the Core Libraries documentation tab."""
    content = []
    content.append(ctx['put_markdown']("### 🔧 不依赖 UI 的核心库"))
    content.append(ctx['put_markdown']("""
以下核心库可以**独立使用**，无需 PyWebIO 或任何 UI 依赖。这些库提供了 Deva 的核心功能。
    """))
    
    # Core library list
    core_libs = [
        {
            'name': '基础架构',
            'module': 'deva.admin.strategy.base',
            'exports': ['BaseManager', 'BaseMetadata', 'BaseState', 'BaseStatus'],
            'desc': '所有管理器、单元类的基类，提供生命周期管理、状态跟踪、回调机制'
        },
        {
            'name': '可执行单元',
            'module': 'deva.admin.strategy.executable_unit',
            'exports': ['ExecutableUnit', 'ExecutableUnitMetadata', 'ExecutableUnitState'],
            'desc': '策略、数据源、任务的统一基类，提供代码执行、状态管理能力'
        },
        {
            'name': '持久化层',
            'module': 'deva.admin.strategy.persistence',
            'exports': ['PersistenceManager', 'MemoryBackend', 'FileBackend', 'DatabaseBackend'],
            'desc': '多后端数据持久化，支持配置序列化/反序列化'
        },
        {
            'name': '日志上下文',
            'module': 'deva.admin.strategy.logging_context',
            'exports': ['LoggingContext', 'strategy_log', 'datasource_log', 'task_log'],
            'desc': '线程安全的日志上下文管理，自动携带组件信息'
        },
        {
            'name': '结果存储',
            'module': 'deva.admin.strategy.result_store',
            'exports': ['StrategyResult', 'ResultStore', 'get_result_store'],
            'desc': '策略执行结果的缓存和持久化'
        },
        {
            'name': '工具函数',
            'module': 'deva.admin.strategy.utils',
            'exports': ['format_pct', 'format_duration', 'df_to_html', 'prepare_df'],
            'desc': '数据格式化、DataFrame 处理、板块分析等'
        },
        {
            'name': '交易时间',
            'module': 'deva.admin.strategy.tradetime',
            'exports': ['is_tradetime', 'is_tradedate', 'get_next_trade_date'],
            'desc': '交易日判断、交易时间判断、交易时间执行装饰器'
        },
        {
            'name': 'AI 工作器',
            'module': 'deva.admin.llm.worker_runtime',
            'exports': ['run_ai_in_worker', 'submit_ai_coro'],
            'desc': '在独立线程中运行 AI 相关操作，避免阻塞主线程'
        },
        {
            'name': 'LLM 配置',
            'module': 'deva.admin.llm.config_utils',
            'exports': ['get_model_config_status', 'build_model_config_example'],
            'desc': 'LLM 配置工具，提供配置状态检查和示例生成'
        },
        {
            'name': '错误处理',
            'module': 'deva.admin.strategy.error_handler',
            'exports': ['ErrorHandler', 'ErrorCollector', 'ErrorLevel'],
            'desc': '统一错误处理，提供错误收集、分类、统计功能'
        },
    ]
    
    # Build table
    table_data = [['核心库', '模块路径', '主要导出', '功能说明']]
    for lib in core_libs:
        table_data.append([
            ctx['put_markdown'](f"**{lib['name']}**"),
            ctx['put_markdown'](f"`{lib['module']}`"),
            ctx['put_markdown'](', '.join(lib['exports'][:3]) + ('...' if len(lib['exports']) > 3 else '')),
            lib['desc']
        ])
    
    content.append(ctx['put_markdown']("#### 核心库列表"))
    content.append(ctx['put_table'](table_data))
    
    # Usage example
    content.append(ctx['put_markdown']("\n#### 使用示例"))
    content.append(ctx['put_markdown']("""
```python
# 1. 使用基础架构
from deva.admin.strategy.base import BaseManager

class MyManager(BaseManager):
    def _do_start(self, item):
        pass

# 2. 使用持久化层
from deva.admin.strategy.persistence import PersistenceManager
pm = PersistenceManager()
pm.save_config('key', data)

# 3. 使用日志上下文
from deva.admin.strategy.logging_context import LoggingContext
ctx = LoggingContext(component_type='strategy', component_id='my_strategy')
with ctx:
    strategy_log.info('策略启动')

# 4. 使用 AI 工作器
from deva.admin.llm.worker_runtime import run_ai_in_worker
result = await run_ai_in_worker(call_llm_api())
```
    """))
    
    return {
        "title": "🔧 核心库",
        "content": content
    }


def render_document_ui(ctx):
    """Render the complete documentation UI with all documents."""
    # Load all documents
    documents = _load_all_documents()

    # Build tabs
    tabs = []

    # Tab 1: Admin UI 完整文档中心 (main documentation hub)
    admin_docs_tab = _build_admin_docs_tab(ctx)
    tabs.append(admin_docs_tab)

    # Tab 2: 核心库文档 (Core libraries - UI independent)
    core_libs_tab = _build_core_libraries_tab(ctx)
    tabs.append(core_libs_tab)

    # Tab 3: 使用示例 (Usage examples)
    examples_tab = _build_examples_tab(ctx)
    tabs.append(examples_tab)

    # Tab 4+: API module tabs
    module_data = scan_document_modules(cache=ctx['cache'], cache_ttl=ctx['cache_ttl'], warn=ctx['warn'])
    for item in module_data:
        module_name = item['module_name']
        if item['error']:
            tabs.append({'title': module_name, 'content': ctx['put_text'](f"无法加载模块：{item['error']}")})
            continue
        module_table = [['名称', '类型', '文档说明', '样例', '测试']]
        for record in item['objects']:
            name = record['name']
            obj = record['obj']
            obj_type = record['type']
            doc = record['doc']
            examples = record['examples']
            action_button = ctx['put_button'](name, onclick=lambda o=obj: ctx['run_async'](ctx['inspect_object'](o)))
            sample_preview = examples[0][:120] if examples else '无'
            test_btn = ctx['put_button'](
                '执行测试',
                onclick=lambda m=module_name, n=name, o=obj, ex=examples: ctx['run_async'](ctx['run_object_smoke_test'](m, n, o, ex)),
                disabled=(obj_type != '函数')
            )
            module_table.append([action_button, obj_type, doc, sample_preview, test_btn])
        tabs.append({'title': module_name, 'content': ctx['put_table'](module_table)})

    # Last Tab: 重构总结 (Refactoring summary)
    refactor_tab = _build_optimization_report_tab(ctx)
    tabs.append(refactor_tab)

    # Render tabs
    ctx['put_markdown']("### 📚 Deva 文档中心")
    ctx['put_markdown']("本文档中心包含快速开始、安装指南、使用手册、最佳实践、故障排查等完整文档。")

    ctx['put_row']([
        ctx['put_button']('🔄 刷新文档缓存', onclick=lambda: (ctx['cache'].update({'ts': 0.0, 'data': None}), ctx['run_async'](ctx['document']()))),
    ])

    ctx['put_tabs'](tabs)
