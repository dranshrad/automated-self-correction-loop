from solution import fib


def test_fib_base() -> None:
    assert fib(0) == 0
    assert fib(1) == 1


def test_fib_values() -> None:
    assert fib(5) == 5
    assert fib(10) == 55
