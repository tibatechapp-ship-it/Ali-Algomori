"""Pytest path anchor for the workspace layer.

Makes the repo-local ``scripts.*`` namespace package importable from the test
suite regardless of how pytest is invoked (``pytest`` vs ``python -m pytest``):
pytest prepends the directory holding this conftest to ``sys.path``.
"""
