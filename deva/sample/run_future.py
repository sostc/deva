from deva import *


@gen.coroutine
def foo():
    yield gen.sleep(3)
    return range << 10 >> sample >> first


async def foo2():
    import asyncio
    await asyncio.sleep(3)
    return range << 10 >> sample >> first

s = Stream()
s.rate_limit(1).run_future() >> log

for i in range(3):
    foo() >> s
    foo2() >> s

run = run_future()
run >> warn

foo() >> run
foo2() >> run

Deva.run()
