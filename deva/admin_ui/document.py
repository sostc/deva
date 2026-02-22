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
    'page', 'lambdas', 'admin', 'llm', 'admin_ui', 'page_ui',
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
        return False, f"函数需要参数: {', '.join(p.name for p in required)}"
    return True, 'ok'


async def run_object_smoke_test(module_name, obj_name, obj, examples, *, toast, popup, put_markdown, put_table):
    ok, reason = callable_smoke_eligibility(obj)
    if not ok:
        toast(f'跳过测试: {obj_name} ({reason})', color='warning')
        return
    try:
        if inspect.iscoroutinefunction(obj):
            result = await asyncio.wait_for(obj(), timeout=5)
        else:
            result = await asyncio.wait_for(asyncio.to_thread(obj), timeout=5)
        popup(
            title=f"测试结果: {module_name}.{obj_name}",
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
            title=f"测试失败: {module_name}.{obj_name}",
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
            methods.append([attr, f'无法访问: {str(e)}'])
    content.append(put_table([['方法名', '文档说明']] + methods))
    popup(title="对象详情", content=content, size='large')


def _resolve_source_files(source_dir):
    if not source_dir.exists():
        return {}
    resolved = {}
    for p in source_dir.iterdir():
        resolved[p.name.strip().lower()] = p
    return resolved


def _load_admin_usage_doc():
    """Load admin guide text, preferring manual_cn.rst by default."""
    root = Path(__file__).resolve().parents[2]
    source_dir = root / "source"
    resolved = _resolve_source_files(source_dir)
    candidates = [
        resolved.get("manual_cn.rst"),
        resolved.get("usage.rst"),
        root / "source" / "manual_cn.rst",
        root / "source" / "usage.rst",
        root / "README.rst",
    ]

    seen = set()
    for path in candidates:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        try:
            if path.exists():
                text = path.read_text(encoding="utf-8", errors="ignore").strip()
                if text:
                    return text, str(path)
        except Exception:
            continue
    return "", ""


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


def _build_usage_tab(ctx):
    put_html = ctx["put_html"]
    usage_text, usage_path = _load_admin_usage_doc()
    if not usage_text:
        return {
            "title": "使用说明",
            "content": ctx["put_text"]("未找到使用说明文档（期望 source/manual_cn.rst、source/usage.rst 或 README.rst）。"),
        }

    rendered_html, render_error = _render_rst_to_html(usage_text, usage_path)
    if render_error:
        body = (
            '<div style="padding:12px;border:1px solid #f5c2c7;background:#fff5f5;color:#842029;border-radius:6px;margin-bottom:12px;">'
            f'RST 渲染失败，已降级为源码显示：{html.escape(render_error)}'
            "</div>"
            f"<pre style='white-space:pre-wrap;line-height:1.6'>{html.escape(usage_text)}</pre>"
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
    </style>
    """
    rendered = (
        doc_style
        + "<div class='admin-rst-doc'>"
        + f"<div style='color:#6b7280;font-size:12px;margin-bottom:10px'>来源: {html.escape(usage_path)}</div>"
        + body
        + "</div>"
    )
    return {
        "title": "使用说明",
        "content": put_html(rendered),
    }


def render_document_ui(ctx):
    module_data = scan_document_modules(cache=ctx['cache'], cache_ttl=ctx['cache_ttl'], warn=ctx['warn'])
    tabs = [_build_usage_tab(ctx)]
    for item in module_data:
        module_name = item['module_name']
        if item['error']:
            tabs.append({'title': module_name, 'content': ctx['put_text'](f"无法加载模块: {item['error']}")})
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
    ctx['put_row']([
        ctx['put_button']('刷新文档缓存', onclick=lambda: (ctx['cache'].update({'ts': 0.0, 'data': None}), ctx['run_async'](ctx['document']()))),
    ])
    ctx['put_tabs'](tabs)
