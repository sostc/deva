from .pipe import P, passed

__all__ = [
    'Counter', 'Summer',
]


def Counter(log=passed, start=0):
    """[返回一个计数器函数]

    [计数器]
    counter = Counter(start=0)
    counter()

    args:
        start: [计数器开始数字] (default: {0})
        log: 结果进入流

    Returns:
        [一个计数器函数]
        [函数]
    """
    result = start

    def _(*args):
        nonlocal result
        result += 1
        result >> log
        return result

    return _ @ P


def Summer(log=passed, start=0):
    """[返回一个累加器器函数]

    [计数器]
    summer = Summer(start=0)
    summer(10)

    args:
        start: [累加开始数字] (default: {0})
        log: 结果进入流

    Returns:
        [一个累加器函数]
    """
    result = start

    def _(x):
        nonlocal result
        result += x
        result >> log
        return result

    return _ @ P
