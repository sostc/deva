from deva import *
from deva.core import _io_loops


@gen.coroutine
def foo():
    'foo1 run' | print
    yield gen.sleep(1)
    return range << 10 >> sample >> first


async def foo2():
    'foo2 run' | print
    import asyncio
    await asyncio.sleep(1)
    return range << 10 >> sample >> first

# s = Stream()
# s.rate_limit(1).run_future() >> log

# for i in range(3):
#     foo() >> s
#     foo2() >> s

# run = run_future()
# run >> warn

# foo() >> run
# foo2() >> run

foo() | attend(log)

foo2() | attend(log)
Deva().run()
