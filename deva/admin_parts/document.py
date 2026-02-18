import asyncio
import inspect
import pkgutil
import re
import time


DOCUMENT_MODULE_WHITELIST = {
    'core', 'pipe', 'store', 'sources', 'when', 'namespace', 'bus',
    'topic', 'endpoints', 'future', 'compute', 'search', 'browser',
    'page', 'lambdas', 'admin', 'llm', 'llm_parts',
    'bus_parts'
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


def render_document_ui(ctx):
    module_data = scan_document_modules(cache=ctx['cache'], cache_ttl=ctx['cache_ttl'], warn=ctx['warn'])
    tabs = []
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
