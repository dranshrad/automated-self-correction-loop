# Intentional failing prompt samples for demos / fixtures

## infinite_loop
Prompt: "Write a Python script that counts forever."
Expected: timeout on first attempt; model should self-correct to a finite loop or print-and-exit.

## wrong_fib
Prompt: see examples/fibonacci/PROMPT.txt
Tests: examples/fibonacci/test_fib.py
Expected: heal mode converges on correct fib within a few iterations.
