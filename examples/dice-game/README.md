# pyeffect-dice-game

A Snakes & Ladders simulation built on `pyeffect` — one game where every
expected failure (a chute spec that goes nowhere, a die landing cocked, a
game that stalls without a winner, a tampered save file, a flaky
leaderboard) is an `Err` **value**, and the one impossible state (a die
that shows 0) is a `PanicError`.

```bash
uv run python examples/dice-game/main.py    # from the repository root
# or from this directory:
uv run python main.py
```

Everything is deterministic: Luna and Zed play scripted dice, the
tournament uses seeded random dice, and retry sleeps are injected no-ops —
so the transcript below is exactly what the default run prints, every
time. `--seed N` re-seeds the tournament and `--break-die` runs the defect
demo (sections 1-4 run first; then the panic is reported and the process
exits 1).

## What the run shows

```
== 1. the board — expected config failures are values ==
   a preset is validated chute by chute (traverse fails fast):
   classic: 14 chutes accepted (7 ladders, 7 snakes)
   a board that arrives over the wire is untrusted data:
   rejected a wire board: chute 40->40 goes nowhere
   rejected another wire board: chute 95->101 leaves squares 1..100
   an unknown preset is an Err too — recover to the house board:
   preset 'royale': no board preset named 'royale'
   recovered by falling back to the house board (classic)

== 2. the dice tower — one race, played lazily ==
   Luna vs Zed on the classic board. game_effect(...) is a lazy Effect: building it runs nothing.
   r 1 Luna  rolled 3: 1 -> 4 -> 14 (ladder)
   r 1 Zed   die cocked twice — stays at 1
   r 2 Luna  rolled 6: 14 -> 20 -> 38 (ladder)
   r 2 Zed   rolled 4: 1 -> 5
   r 3 Luna  rolled 6: 38 -> 44
   r 3 Zed   rolled 3: 5 -> 8
   r 4 Luna  rolled 6: 44 -> 50
   r 4 Zed   rolled 5: 8 -> 13
   r 5 Luna  rolled 4: 50 -> 54 -> 34 (snake)
   r 5 Zed   rolled 4: 13 -> 17 -> 7 (snake)
   r 6 Luna  rolled 6: 34 -> 40 -> 59 (ladder)
   r 6 Zed   rolled 2: 7 -> 9 -> 31 (ladder)
   r 7 Luna  rolled 4: 59 -> 63 -> 81 (ladder)
   r 7 Zed   rolled 3: 31 -> 34
   r 8 Luna  rolled 5: 81 -> 86
   r 8 Zed   rolled 6: 34 -> 40 -> 59 (ladder)
   r 9 Luna  rolled 6: 86 -> 92
   r 9 Zed   rolled 4: 59 -> 63 -> 81 (ladder)
   r10 Luna  rolled 2: 92 -> 94
   r10 Zed   rolled 2: 81 -> 83
   r11 Luna  rolled 6: 94 -> 100  WINS

   Luna reached square 100 in round 11
   standings: Luna @ 100, Zed @ 83
   dice: Luna 1 reroll, Zed 1 reroll (cocked rolls are retried once, then skipped)
   replay: running the same Effect again produced the same winner (Luna) in 21 turns — identical: True

== 3. the tournament — every game's outcome is a value ==
   [mira / theo / jun, fair dice] Mira wins in round 11
   [tortoise / snail, dice of ones] no winner after 10 rounds
   partition: 1 game(s) finished, 1 stalled (seed 38)

== 4. wire — a scoreboard survives the boundary ==
   envelope: {'status': 'ok', 'value': {'winner': 'Luna', 'rounds': 11, 'turns': 21, 'standings': [{'name': 'Luna', 'position': 100}, {'name': 'Zed', 'position': 83}]}}
   round trip: decoded == original: True
   the envelope is tampered with before it comes back...
   rejected: ResultDeserializationError (could not deserialize value)
   uploading to a flaky leaderboard server...
   uploaded after 3 attempts (2 transient blips retried)
   a stalled game is logged as: {'status': 'error', 'error': {'tag': 'GameStalled', 'message': 'no winner after 10 rounds'}}
```

## What each section is doing

| Section | Library pieces | Why it looks like that |
|---|---|---|
| 1. The board | `Result`, `traverse` (fail fast), `and_then`, tagged errors, `recover` | A board spec is untrusted data: per-chute checks run through `traverse`, so the first bad entry rejects the whole preset; an unknown preset is an `Err` that `recover` falls back from to the house board |
| 2. The race | lazy `Effect` + `and_then`, `retry` + `Policy`, `Option` (`Some`/`Nothing`/`from_optional`), `pipe`, `panic` (defensive) | The die is impure, so a roll is an `Effect`; a cocked roll is a `Nothing` that becomes an `Err` and `retry` re-rolls once (`should_retry` on `CockedDieError`). Movement is pure: `Option` chute lookups, exact-finish bounce-back. The whole game is one re-runnable effect — replaying it reproduces the same race |
| 3. The tournament | `partition` | Every game's outcome is a value: winners and stalled games split into two lists. A fair-dice trio (seeded) finishes; two dice-of-ones players can't reach 100 inside their round cap and stall |
| 4. Wire | `Codec`, `attempt`, `retry`, `should_retry`, injected `sleep` | A `Scoreboard` round-trips through a `{"status", ...}` envelope; a tampered payload is an expected wire failure and decodes to an `Err`. Uploading is `attempt` at the exception boundary plus `retry` — only `NetworkBlip` is retried, and the sleep is injected so the demo waits 0s |
| 5. Defect | `PanicError`, the defect boundary in `main()` | `--break-die` makes Luna's die jam and show 0 — impossible for a physical die — so `panic()` fires at the exact line, propagates through every `Effect`/`retry` (never folded into an `Err`), and `main()` — the only place allowed to catch `PanicError` — reports the bug and exits 1 |

## Notes

- **This is a uv workspace member.** It links `pyeffect` from the checked-out
  source (`[tool.uv.sources] pyeffect = { workspace = true }` in
  `pyproject.toml`), so the example always runs against current code and
  shares the repository's lockfile and virtualenv.
- **To ship it standalone** (against a published `pyeffect`): move this
  folder out of `examples/`, delete the `[tool.uv.sources]` table, and run
  `uv lock` — then `pyeffect` resolves from PyPI.
- **Why the example prints:** examples are runnable demos, so
  `examples/dice-game/main.py` is exempted from ruff's `T201` (print) rule
  in the root `ruff.toml` — the transcript is the demo.
- **Deterministic dice:** every player carries a die *pattern* (entries are
  roll attempts, `None` is a cocked roll, an empty pattern means a seeded
  fair die). The pattern is cycled inside a fresh `Session` created per
  game run, which is what makes `game_effect` re-runnable — running it
  twice replays the same game.
- Everything runs offline and instantly: no I/O, no real sleep, seeded
  randomness only.
