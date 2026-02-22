import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def parse_module(rel_path: str) -> ast.AST:
    path = ROOT / rel_path
    return ast.parse(path.read_text(encoding='utf-8'))


def find_class(module: ast.AST, name: str) -> ast.ClassDef:
    for node in module.body:
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    raise AssertionError(f'class {name} not found')


def find_method(class_node: ast.ClassDef, name: str):
    for node in class_node.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f'method {class_node.name}.{name} not found')


class TestP1Regressions(unittest.TestCase):
    def test_init_has_no_eager_gpt_import(self):
        module = parse_module('deva/__init__.py')
        for node in module.body:
            if isinstance(node, ast.ImportFrom) and node.module == 'llm':
                self.fail('deva.__init__ should not eagerly import deva.llm')

    def test_llm_module_has_no_eager_singleton_instantiation(self):
        module = parse_module('deva/llm/client.py')
        for node in module.body:
            if isinstance(node, ast.Assign):
                value = node.value
                if isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id == 'GPT':
                    self.fail('deva.llm should not instantiate GPT() at import time')

    def test_llm_has_lazy_factory(self):
        module = parse_module('deva/llm/client.py')
        has_get_gpt = any(isinstance(n, ast.FunctionDef) and n.name == 'get_gpt' for n in module.body)
        self.assertTrue(has_get_gpt, 'deva.llm should expose get_gpt() lazy factory')

    def test_deva_run_uses_current_ioloop(self):
        module = parse_module('deva/core.py')
        deva_class = find_class(module, 'Deva')
        run = find_method(deva_class, 'run')

        has_current = False
        has_invalid_start_chain = False

        for node in ast.walk(run):
            # IOLoop.current()
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if isinstance(node.func.value, ast.Name) and node.func.value.id == 'IOLoop' and node.func.attr == 'current':
                    has_current = True

            # IOLoop().start() used as rvalue is the historical bug
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                inner = node.func.value
                if (
                    node.func.attr == 'start'
                    and isinstance(inner, ast.Call)
                    and isinstance(inner.func, ast.Name)
                    and inner.func.id == 'IOLoop'
                ):
                    has_invalid_start_chain = True

        self.assertTrue(has_current, 'Deva.run should use IOLoop.current()')
        self.assertFalse(has_invalid_start_chain, 'Deva.run must not use IOLoop().start() return value')

    def test_from_textfile_uses_persistent_buffer(self):
        module = parse_module('deva/sources.py')
        source_cls = find_class(module, 'from_textfile')
        init = find_method(source_cls, '__init__')
        fetch = find_method(source_cls, '_fetch_data')

        init_sets_buffer = False
        fetch_updates_self_buffer = False
        fetch_has_local_buffer_reset = False

        for node in ast.walk(init):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if (
                        isinstance(target, ast.Attribute)
                        and isinstance(target.value, ast.Name)
                        and target.value.id == 'self'
                        and target.attr == '_buffer'
                    ):
                        init_sets_buffer = True

        for node in ast.walk(fetch):
            if isinstance(node, ast.AugAssign):
                t = node.target
                if (
                    isinstance(t, ast.Attribute)
                    and isinstance(t.value, ast.Name)
                    and t.value.id == 'self'
                    and t.attr == '_buffer'
                ):
                    fetch_updates_self_buffer = True

            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == 'buffer':
                        fetch_has_local_buffer_reset = True

        self.assertTrue(init_sets_buffer, 'from_textfile.__init__ should initialize self._buffer')
        self.assertTrue(fetch_updates_self_buffer, 'from_textfile._fetch_data should append to self._buffer')
        self.assertFalse(fetch_has_local_buffer_reset, 'from_textfile._fetch_data should not reset local buffer each poll')

    def test_rshift_default_branch_raises_typeerror(self):
        source = (ROOT / 'deva/core.py').read_text(encoding='utf-8')
        self.assertIn('.throw(TypeError(', source, '__rshift__ should raise TypeError in ANY branch')


if __name__ == '__main__':
    unittest.main()
