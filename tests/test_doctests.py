"""Docstring examples in every pyeffect module are part of its contract."""

from __future__ import annotations

import doctest
import pkgutil
from importlib import import_module

import pyeffect


def test_all_module_doctests() -> None:
    failed = 0
    for module_info in pkgutil.iter_modules(pyeffect.__path__):
        module = import_module(f"pyeffect.{module_info.name}")
        results = doctest.testmod(module)
        failed += results.failed
    assert failed == 0, f"{failed} doctest(s) failed across the package"
