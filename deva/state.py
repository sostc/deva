from .pipe import P

__all__ = [
    'Counter', 'Summer',
]


def Counter(start=0):
    """[返回一个计数器函数]

    [计数器]
    counter = Counter(start=0)
    counter()

    args:
        start: [计数器开始数字] (default: {0})

    Returns:
        [一个计数器函数]
        [函数]
    """
    l1 = [start]

    def _(*args):
        l1[0] += 1
        return l1[0]

    return _ @ P


def Summer(start=0):
    """[返回一个累加器器函数]

    [计数器]
    summer = Summer(start=0)
    summer(10)

    args:
        start: [累加开始数字] (default: {0})

    Returns:
        [一个累加器函数]
    """
    l1 = [start]

    def _(x):
        l1[0] += x
        return l1[0]

    return _ @ P
