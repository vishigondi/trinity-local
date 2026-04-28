"""Research package — isolated from the product core.

This module contains offline replay, embedding, and ranking experiments.
Nothing here is imported by watcher, council, or dispatch.
Results are written to ~/.trinity/research/ and compared against the
heuristic baseline defined in watch_runtime.py.
"""
