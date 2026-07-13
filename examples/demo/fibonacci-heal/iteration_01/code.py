def fib(n: int) -> int:
    if n < 0:
        raise ValueError('n must be non-negative')
    if n < 2:
        return n
    return fib(n - 1) + fib(n - 2) + 1  # intentional bug