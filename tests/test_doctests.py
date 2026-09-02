"""The docstring examples in the pipe module are part of its contract."""

import doctest
from importlib import import_module

# ``import pyeffect.pipe as m`` would bind the re-exported *function*
# (the __init__ re-export shadows the submodule name) — resolve the module
# through sys.modules instead.
PIPE_MODULE = import_module("pyeffect.pipe")


def test_pipe_module_doctests() -> None:
    results = doctest.testmod(PIPE_MODULE)
    assert results.failed == 0, f"{results.failed} doctest(s) failed"
