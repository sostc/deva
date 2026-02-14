import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _module(path: Path):
    return ast.parse(path.read_text(encoding='utf-8'))


def test_init_has_no_eager_gpt_import():
    module = _module(ROOT / 'deva' / '__init__.py')
    for node in module.body:
        if isinstance(node, ast.ImportFrom) and node.module == 'gpt':
            raise AssertionError('deva.__init__ should not eagerly import deva.gpt')


def test_gpt_module_has_no_eager_singleton_instantiation():
    module = _module(ROOT / 'deva' / 'gpt.py')
    for node in module.body:
        if isinstance(node, ast.Assign):
            value = node.value
            if isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id == 'GPT':
                raise AssertionError('deva.gpt should not instantiate GPT() at import time')
