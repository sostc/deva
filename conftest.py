"""Pytest collection guardrails for legacy exploratory scripts.

Several historical test files target modules that were intentionally removed
during the Naja cleanup. Keeping them in default collection makes the current
suite fail before active code can be exercised.
"""

import asyncio
import inspect


collect_ignore = [
    "deva/naja/business/openrouter_monitor/tests/test_openrouter_monitor.py",
    "deva/naja/cognition/liquidity/test_liquidity_propagation.py",
    "deva/naja/tests/test_action_executor.py",
    "deva/naja/tests/test_meta_evolution.py",
    "deva/naja/tests/test_meta_evolution_enhanced.py",
    "scripts/test/test_duplicate_names.py",
    "scripts/test/test_name_uniqueness.py",
    "scripts/simulated_test.py",
    "scripts/test_jitter_monitor.py",
    "scripts/verify/test_final_verification.py",
]


def pytest_pyfunc_call(pyfuncitem):
    """Run coroutine-style tests without requiring pytest-asyncio."""
    test_function = pyfuncitem.obj
    if inspect.iscoroutinefunction(test_function):
        fixture_names = pyfuncitem._fixtureinfo.argnames
        kwargs = {
            name: pyfuncitem.funcargs[name]
            for name in fixture_names
            if name in pyfuncitem.funcargs
        }
        asyncio.run(test_function(**kwargs))
        return True
    return None
