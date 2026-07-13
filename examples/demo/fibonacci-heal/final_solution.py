def fib(n: int) -> int:
    if n < 0:
        raise ValueError('n must be non-negative')
    if n < 2:
        return n
    a, b = 0, 1
    for _ in range(2, n + 1):
        a, b = b, a + b
    return b