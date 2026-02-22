# -*- coding: utf-8 -*-
"""Lambda表达式工具模块

该模块提供了用于创建和操作lambda表达式的工具函数和类。
主要用于简化函数式编程中的操作，支持常见的数学运算和逻辑操作。

主要功能：
- 支持通过运算符重载创建lambda表达式
- 提供映射操作符的装饰器
- 支持函数参数翻转
- 提供类型安全的lambda表达式创建

主要类：
- _Callable: 核心类，通过运算符重载创建lambda表达式

示例用法：
1. 创建简单的lambda表达式
>>> f = _Callable()
>>> add_one = f + 1  # 等价于 lambda x: x + 1
>>> result = add_one(5)  # 输出: 6

2. 使用映射操作符
>>> get_name = f['name']  # 等价于 lambda x: x['name']
>>> result = get_name({'name': 'Alice'})  # 输出: 'Alice'

3. 组合操作
>>> complex_op = (f + 1) * 2  # 等价于 lambda x: (x + 1) * 2
>>> result = complex_op(3)  # 输出: 8

注意事项：
- 使用TypeVar确保类型安全
- 支持常见的数学运算符（+,-,*,/,%等）
- 支持逻辑运算符（and,or,not等）
"""

import operator
from typing import Callable, Mapping, TypeVar
from .pipe import P

T1 = TypeVar('T1')
T2 = TypeVar('T2')


def _fmap(callback):
    def decorator(self, second):
        return (lambda first: callback(first, second))@P
    return decorator


def _unary_fmap(callback):
    def decorator(self):
        return callback
    return decorator


def _flip(callback):
    return (lambda first, second: callback(second, first))@P


class _Callable(object):
    def __getitem__(
        self, key: T1,
    ) -> Callable[[Mapping[T1, T2]], T2]:
        return operator.itemgetter(key)

    __add__: Callable[['_Callable', T1], Callable[[T1], T1]] = _fmap(
        operator.add,
    )
    __mul__: Callable[['_Callable', T1], Callable[[T1], T1]] = _fmap(
        operator.mul,
    )
    __sub__: Callable[['_Callable', T1], Callable[[T1], T1]] = _fmap(
        operator.sub,
    )
    __mod__: Callable[['_Callable', T1], Callable[[T1], T1]] = _fmap(
        operator.mod,
    )
    __pow__: Callable[['_Callable', T1], Callable[[T1], T1]] = _fmap(
        operator.pow,
    )

    __and__: Callable[['_Callable', T1], Callable[[T1], T1]] = _fmap(
        operator.and_,
    )
    __or__: Callable[['_Callable', T1], Callable[[T1], T1]] = _fmap(
        operator.or_,
    )
    __xor__: Callable[['_Callable', T1], Callable[[T1], T1]] = _fmap(
        operator.xor,
    )

    __div__: Callable[['_Callable', T1], Callable[[T1], T1]] = _fmap(
        operator.truediv,
    )
    __divmod__: Callable[['_Callable', T1], Callable[[T1], T1]] = _fmap(divmod)
    __floordiv__: Callable[['_Callable', T1], Callable[[T1], T1]] = _fmap(
        operator.floordiv,
    )
    __truediv__: Callable[['_Callable', T1], Callable[[T1], T1]] = _fmap(
        operator.truediv,
    )

    __lshift__: Callable[['_Callable', T1], Callable[[T1], T1]] = _fmap(
        operator.lshift,
    )
    __rshift__: Callable[['_Callable', T1], Callable[[T1], T1]] = _fmap(
        operator.rshift,
    )

    __lt__: Callable[['_Callable', T1], Callable[[T1], T1]] = _fmap(
        operator.lt,
    )
    __le__: Callable[['_Callable', T1], Callable[[T1], T1]] = _fmap(
        operator.le,
    )
    __gt__: Callable[['_Callable', T1], Callable[[T1], T1]] = _fmap(
        operator.gt,
    )
    __ge__: Callable[['_Callable', T1], Callable[[T1], T1]] = _fmap(
        operator.ge,
    )
    __eq__: Callable[
        ['_Callable', object], Callable[[object], bool],
    ] = _fmap(  # type: ignore
        operator.eq,
    )
    __ne__: Callable[
        ['_Callable', object], Callable[[object], bool],
    ] = _fmap(  # type: ignore
        operator.ne,
    )

    __neg__: Callable[['_Callable'], Callable[[T1], T1]] = _unary_fmap(
        operator.neg,
    )
    __pos__: Callable[['_Callable'], Callable[[T1], T1]] = _unary_fmap(
        operator.pos,
    )
    __invert__: Callable[['_Callable'], Callable[[T1], T1]] = _unary_fmap(
        operator.invert,
    )

    __radd__: Callable[['_Callable', T1], Callable[[T1], T1]] = _fmap(
        _flip(operator.add),
    )
    __rmul__: Callable[['_Callable', T1], Callable[[T1], T1]] = _fmap(
        _flip(operator.mul),
    )
    __rsub__: Callable[['_Callable', T1], Callable[[T1], T1]] = _fmap(
        _flip(operator.sub),
    )
    __rmod__: Callable[['_Callable', T1], Callable[[T1], T1]] = _fmap(
        _flip(operator.mod),
    )
    __rpow__: Callable[['_Callable', T1], Callable[[T1], T1]] = _fmap(
        _flip(operator.pow),
    )
    __rdiv__: Callable[['_Callable', T1], Callable[[T1], T1]] = _fmap(
        _flip(operator.truediv),
    )
    __rdivmod__: Callable[['_Callable', T1], Callable[[T1], T1]] = _fmap(
        _flip(divmod),
    )
    __rtruediv__: Callable[['_Callable', T1], Callable[[T1], T1]] = _fmap(
        _flip(operator.truediv),
    )
    __rfloordiv__: Callable[['_Callable', T1], Callable[[T1], T1]] = _fmap(
        _flip(operator.floordiv),
    )

    __rlshift__: Callable[['_Callable', T1], Callable[[T1], T1]] = _fmap(
        _flip(operator.lshift),
    )
    __rrshift__: Callable[['_Callable', T1], Callable[[T1], T1]] = _fmap(
        _flip(operator.rshift),
    )

    __rand__: Callable[['_Callable', T1], Callable[[T1], T1]] = _fmap(
        _flip(operator.and_),
    )
    __ror__: Callable[['_Callable', T1], Callable[[T1], T1]] = _fmap(
        _flip(operator.or_),
    )
    __rxor__: Callable[['_Callable', T1], Callable[[T1], T1]] = _fmap(
        _flip(operator.xor),
    )


_ = _Callable()  # noqa: WPS122
