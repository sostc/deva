import IPython
from deva import *


@gen.coroutine
def foo1():
    'foo1 run' | print
    yield gen.sleep(1)
    return 'foo1 result'


async def foo2():
    'foo2 run' | print
    import asyncio
    await asyncio.sleep(1)
    return 'foo2 result'

# s = Stream()
# s.rate_limit(1).run_future() >> log

# for i in range(3):
#     foo() >> s
#     foo2() >> s

# run = run_future()
# run >> warn

# foo() >> run
# foo2() >> run

foo1() | log

foo1() | print

foo2() | log

foo2() | attend()
name = "Masnun"

# IPython.embed()

Deva().run()
