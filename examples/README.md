# pyeffect examples

Runnable applications that demonstrate `pyeffect` end to end. Each example
is its own uv project — own `pyproject.toml`, `README.md`, and dependencies
— and a member of this repository's uv workspace, so every example links
`pyeffect` from the checked-out source and shares the repo's lockfile and
virtualenv.

```bash
uv run python examples/checkout/main.py    # from the repository root
cd examples/checkout && uv run python main.py   # or from inside an example
```

| Example | Demonstrates | Run |
|---|---|---|
| [checkout](checkout/) | one order flow applying the whole library: `Result`/`Option`/`do`, lazy `Effect` + `do_effect`, `retry` + `Policy`, tagged errors, `Codec` serialization, and the `Panic` defect boundary | `uv run python examples/checkout/main.py` |

## Adding an example

```bash
uv init examples/my-example --app --python 3.12     # registers it in the workspace
cd examples/my-example
uv add pyeffect                                      # links the workspace member
```

Write your `main.py`, replace the generated `README.md`, and run it with
`uv run python examples/my-example/main.py`. The workspace root's
`ruff check` and `ty check` already cover `examples/`, so keep example code
as clean as library code.
