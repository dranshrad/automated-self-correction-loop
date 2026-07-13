"""Broken on purpose — use with `ascl heal` and the frozen tests."""

def fib(n: int) -> int:
    if n < 2:
        return n
    return fib(n - 1) + fib(n - 2) + 1
