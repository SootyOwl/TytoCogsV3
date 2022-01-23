import asyncio
import functools


def memoize(obj):
    """Decorator for memoizing functions adapted from https://wiki.python.org/moin/PythonDecoratorLibrary#Memoize"""
    cache = obj.cache = {}

    if asyncio.iscoroutinefunction(obj):
        @functools.wraps(obj)
        async def memoizer(*args, **kwargs):
            key = str(args) + str(kwargs)
            if key not in cache:
                cache[key] = await obj(*args, **kwargs)
            return cache[key]
    else:
        @functools.wraps(obj)
        def memoizer(*args, **kwargs):
            key = str(args) + str(kwargs)
            if key not in cache:
                cache[key] = obj(*args, **kwargs)
            return cache[key]

    return memoizer
