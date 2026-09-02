# pyeffect-checkout

A checkout pipeline built on `pyeffect` — one order flow where every
expected failure (no such order, unknown SKU, out of stock, declined card,
gateway timeout) is an `Err` **value**, and the one impossible state (the
gateway settling a different amount than quoted) is a `Panic`.

```bash
uv run python examples/checkout/main.py    # from the repository root
# or from this directory:
uv run python main.py
```

## What the run shows

Every demo order is scripted (catalog, inventory, and a fake payment
gateway are injected), so the output is deterministic:

```
== 1. quote every order — traverse fails fast ==
   quoting stopped at: order E500: sku vaporware is not in the catalog
   (A100-D400 priced fine, but traverse is all-or-nothing)

== 2. checkout each order — effects run, partition keeps every outcome ==
   A100: charged $37.00 [AUTH-A100]
   C300: charged $36.00 [AUTH-C300]
   order B200: payment declined (insufficient funds)
   order D400: sku rare-mug is out of stock (only 3 left)

== 3. retry policy — only transient failures retry ==
   A100: 3 attempt(s) ['timeout', 'timeout', 'ok'] (retried until ok)
   B200: 1 attempt(s) ['declined'] (terminal, not retried)
   C300: 1 attempt(s) ['ok'] (succeeded on the first attempt)
   (sleep was injected: exponential backoff 50ms base, 20% jitter)

== 4. wire boundary — Codec round-trips a Result through a dict ==
   envelope: {"status": "ok", "value": {"order_id": "A100", "user": "ada", "total_cents": 3700, "auth": "AUTH-A100"}}
   round trip: A100 $37.00 (decoded == original: True)
   tampered envelope rejected: ResultDeserializationError
   declined order is logged as: {"status": "error", "error": {"tag": "CardDeclined", "message": "insufficient funds"}}
```

## What each section is doing

| Section | Library pieces | Why it looks like that |
|---|---|---|
| 1. Quote | `Option` (`from_optional` + `Some`/`Nothing` match), `Result`, `do`-notation, `traverse`, tagged errors, `pipe` | `do` linearizes lookup → validate → price; `traverse` fails fast, so the unknown SKU in E500 drops the whole quote batch |
| 2. Checkout | lazy `Effect`, `do_effect`, `attempt`, `partition` | `do_effect` composes the impure steps (reserve → charge → receipt) into one re-runnable effect; `partition` keeps every outcome — which is why each error carries its `order_id` |
| 3. Retry | `retry` + `Policy` (exponential, jittered), `should_retry`, injected `sleep` | only `GatewayTimeout` is transient, so A100's two timeouts are retried while B200's decline is terminal |
| 4. Wire | `Codec`, `serialize`/`deserialize`, `expect` | receipts round-trip through a `{"status", ...}` envelope; a tampered payload is an expected wire failure and decodes to an `Err` |

## See the defect boundary

The gateway can be made buggy — settling one cent off-quote — which violates
an invariant the receipt step checks:

```bash
uv run python examples/checkout/main.py --break-settlement
```

The checkout stops at the exact line with `panic(...)`, and `main()` — the
only place allowed to catch `Panic` — reports the bug and exits `1`. The
panic is never converted back into an `Err`; a wrong receipt is never
written.

## Notes

- **This is a uv workspace member.** It links `pyeffect` from the checked-out
  source (`[tool.uv.sources] pyeffect = { workspace = true }` in
  `pyproject.toml`), so the example always runs against current code and
  shares the repository's lockfile and virtualenv.
- **To ship it standalone** (against a published `pyeffect`): move this
  folder out of `examples/`, delete the `[tool.uv.sources]` table, and run
  `uv lock` — then `pyeffect` resolves from PyPI.
- **Why errors carry `order_id`:** `partition` splits results into two
  lists, losing which order a failure belongs to. Carrying the context in
  the error — not in the position of the result — keeps failures
  self-describing after any combinator.
- Everything runs offline: the gateway, inventory, and store are injected
  stand-ins, and retry sleeps are real but tiny (50 ms base).
