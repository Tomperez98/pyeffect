"""Snakes & Ladders, simulated with pyeffect — a runnable dice-game demo.

One game (a race up a 100-square board) that meets the library's one rule
at every boundary:

* **Expected failures are values.** A chute spec that goes nowhere, points
  off the board, a duplicate start, an unknown board preset, a die that
  lands cocked, a game that hits its round cap without a winner, a tampered
  save file, a flaky leaderboard — each is an ``Err`` carrying a
  ``TaggedError`` with a ``tag`` you can match on.
* **Impossible states are bugs and panic.** A die that shows 0 or 7 — no
  physical die does — is a broken dependency, so ``panic()`` fires at the
  exact line instead of inventing a position. ``PanicError`` is never folded
  into an ``Err``; only ``main()`` (the defect boundary) catches it.

Each section of the transcript is one library module:

    == 1. the board ==   ``traverse`` chute validation (fail fast), tagged
                         errors, ``recover`` to a fallback preset
    == 2. the race  ==   dice as a lazy ``Effect``, ``retry`` when a roll
                         comes up cocked, ``Option`` chute lookups,
                         ``pipe`` reporting, effect re-runnability
    == 3. tournament ==  ``partition`` splits finished games from stalled
                         ones
    == 4. wire      ==   ``Codec`` round trip, a tampered envelope, and
                         ``attempt`` + ``retry`` against a flaky server
    == 5. defect    ==   ``--break-die``: a die that jams panics and the
                         defect boundary reports it (never an ``Err``)

Run it from this directory (``pyeffect`` resolves to the repo this example
lives in, see ``pyproject.toml``):

    uv run python main.py                       # sections 1-4, exit 0
    uv run python main.py --break-die           # + a PanicError defect demo

Everything is deterministic: scripted dice, seeded random dice, injected
sleep, no wall-clock randomness. The tournament seed can be overridden with
``--seed N``.
"""

from __future__ import annotations

import itertools
import random
import sys
from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pyeffect import (
    Codec,
    Effect,
    Err,
    Nothing,
    Ok,
    Option,
    PanicError,
    Policy,
    Result,
    Some,
    TaggedError,
    UnhandledError,
    attempt,
    from_optional,
    match_error,
    panic,
    partition,
    pipe,
    recover,
    retry,
    traverse,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator

BOARD_SIZE = 100
REROLL_POLICY = Policy(max_attempts=2, delay=0.0)
UPLOAD_POLICY = Policy(max_attempts=3, delay=0.0)
TOURNEY_SEED = 38

# --------------------------------------------------------------------------
# Domain data
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Chute:
    """A snake (``end < start``) or ladder (``end > start``) on the board."""

    start: int
    end: int

    @property
    def is_ladder(self) -> bool:
        return self.end > self.start


@dataclass(frozen=True, slots=True)
class Board:
    """A square-count board with its (start -> end) chutes."""

    name: str
    size: int
    chutes: tuple[Chute, ...]

    def lookup(self, square: int) -> Option[Chute]:
        """Return the chute that starts on ``square``, if any."""
        for chute in self.chutes:
            if chute.start == square:
                return Some(chute)
        return Nothing()


@dataclass(frozen=True, slots=True)
class Player:
    """A contestant. An empty ``pattern`` rolls fair; ``None`` means cocked.

    ``pattern`` is the die script: entries are consumed one per roll attempt
    and cycled. ``None`` is a roll that lands cocked (expected, retried),
    ``jams_on`` is the roll that physically breaks the die (a defect — the
    ``--break-die`` demo) and ``None`` means the die never jams.
    """

    name: str
    pattern: tuple[int | None, ...] = ()
    jams_on: int | None = None


@dataclass(frozen=True, slots=True)
class Services:
    """Injected dependencies. ``sleep`` is a no-op here, so retries cost 0s."""

    sleep: Callable[[float], None]


@dataclass(frozen=True, slots=True)
class TurnEvent:
    """One turn of one player: a roll (or a cocked skip), and where it landed."""

    player: str
    round: int
    roll: int | None  # None: the die stayed cocked and the turn was skipped
    frm: int
    to: int
    via: Chute | None
    won: bool


@dataclass(frozen=True, slots=True)
class PlayerScore:
    name: str
    position: int


@dataclass(frozen=True, slots=True)
class GameRecord:
    """The pure outcome of a finished game: winner, log, and final board."""

    winner: str
    rounds: int
    events: tuple[TurnEvent, ...]
    standings: tuple[PlayerScore, ...]
    rerolls: dict[str, int]


@dataclass(frozen=True, slots=True)
class Scoreboard:
    """The wire-friendly slice of a GameRecord (no per-turn log)."""

    winner: str
    rounds: int
    turns: int
    standings: tuple[PlayerScore, ...]


@dataclass(frozen=True, slots=True)
class Game:
    label: str
    players: tuple[Player, ...]
    seed: int
    round_cap: int


# --------------------------------------------------------------------------
# The error vocabulary: tagged errors, one union per boundary
# --------------------------------------------------------------------------


class PortalToSelfError(TaggedError, tag="PortalToSelf"):
    """A chute whose start equals its end goes nowhere."""

    def __init__(self, start: int) -> None:
        self.start = start
        super().__init__(f"chute {start}->{start} goes nowhere")


class ChuteOutOfBoundsError(TaggedError, tag="ChuteOutOfBounds"):
    """A chute endpoint outside squares 1..BOARD_SIZE."""

    def __init__(self, start: int, end: int) -> None:
        self.start = start
        self.end = end
        super().__init__(f"chute {start}->{end} leaves the board")


class ChuteOnLastSquareError(TaggedError, tag="ChuteOnLastSquare"):
    """A chute starting on the last square can never be landed on."""

    def __init__(self, start: int, end: int) -> None:
        self.start = start
        self.end = end
        super().__init__(f"chute {start}->{end} starts on the last square")


class OverlappingChutesError(TaggedError, tag="OverlappingChutes"):
    """Two chutes starting on the same square is contradictory config."""

    def __init__(self, start: int, end: int) -> None:
        self.start = start
        self.end = end
        super().__init__(f"two chutes start on square {start}")


class UnknownBoardError(TaggedError, tag="UnknownBoard"):
    """A requested board preset does not exist."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"no preset named {name!r}")


type BoardError = (
    PortalToSelfError
    | ChuteOutOfBoundsError
    | ChuteOnLastSquareError
    | OverlappingChutesError
    | UnknownBoardError
)


class CockedDieError(TaggedError, tag="CockedDie"):
    """A roll landed cocked: transient, so ``should_retry`` re-rolls it."""

    def __init__(self, player: str) -> None:
        self.player = player
        super().__init__(f"{player}'s die came up cocked")


class GameStalledError(TaggedError, tag="GameStalled"):
    """No winner inside the round cap — an expected, non-winning outcome."""

    def __init__(self, rounds: int) -> None:
        self.rounds = rounds
        super().__init__(f"no winner after {rounds} rounds")


type GameError = CockedDieError | GameStalledError


class ScoreServerBlipError(Exception):
    """The flaky leaderboard raises, because network SDKs raise."""


class NetworkBlipError(TaggedError, tag="NetworkBlip"):
    """A transient upload failure: retryable."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)


type UploadError = NetworkBlipError | UnhandledError


def _board_fail[X](error: BoardError) -> Result[X, BoardError]:
    """Build an ``Err`` at the board's error type.

    Python generics are invariant, so ``Err[PortalToSelfError]`` is not an
    ``Err[BoardError]`` — this helper widens once, at one place.
    """
    return Err(error)


def _game_fail[X](error: GameError) -> Result[X, GameError]:
    """Build an ``Err`` at the game's error type (see ``_board_fail``)."""
    return Err(error)


# --------------------------------------------------------------------------
# Board config: validating an untrusted spec is Result work
# --------------------------------------------------------------------------


type ChuteSpec = tuple[int, int]


def _check_entry(entry: ChuteSpec) -> Result[Chute, BoardError]:
    """Validate one chute spec; every defect is an expected config failure."""
    start, end = entry
    if not (1 <= start <= BOARD_SIZE and 1 <= end <= BOARD_SIZE):
        return _board_fail(ChuteOutOfBoundsError(start, end))
    if start == BOARD_SIZE:
        return _board_fail(ChuteOnLastSquareError(start, end))
    if start == end:
        return _board_fail(PortalToSelfError(start))
    return Ok(Chute(start, end))


def _reject_overlaps(chutes: list[Chute]) -> Result[list[Chute], BoardError]:
    """Reject a second chute on a square already occupied by one."""
    seen: set[int] = set()
    for chute in chutes:
        if chute.start in seen:
            return _board_fail(OverlappingChutesError(chute.start, chute.end))
        seen.add(chute.start)
    return Ok(chutes)


def _validate(entries: Iterable[ChuteSpec]) -> Result[list[Chute], BoardError]:
    """Validate a full chute spec: per-entry checks, then the overlap pass.

    ``traverse`` runs the per-entry checks and fails fast on the first bad
    entry — an all-or-nothing contract, like quoting every order in one
    batch. ``and_then`` chains the whole-list overlap check behind it.
    """
    return traverse(_check_entry, entries).and_then(_reject_overlaps)


CLASSIC_ENTRIES: tuple[ChuteSpec, ...] = (
    (4, 14),
    (9, 31),
    (20, 38),
    (28, 84),
    (40, 59),
    (51, 67),
    (63, 81),
    (17, 7),
    (54, 34),
    (62, 19),
    (87, 24),
    (93, 73),
    (95, 75),
    (98, 79),
)

PRESETS: dict[str, tuple[ChuteSpec, ...]] = {"classic": CLASSIC_ENTRIES}


def load_preset(name: str) -> Result[Board, BoardError]:
    """Load and validate a named preset, or fail with an ``UnknownBoardError``."""
    entries = PRESETS.get(name)
    if entries is None:
        return _board_fail(UnknownBoardError(name))
    return _validate(entries).map(lambda chutes: Board(name, BOARD_SIZE, tuple(chutes)))


# A built-in preset is trusted in-repo; if someone edits it into a broken
# board, unwrap() fails fast at import — a loud bug, not a quiet one.
CLASSIC_BOARD = load_preset("classic").unwrap()


# --------------------------------------------------------------------------
# The dice: one roll attempt is an Option; a broken die is a PanicError
# --------------------------------------------------------------------------


class Session:
    """Fresh per game run, so an Effect replays identically from scratch.

    Holds the per-player die scripts (cycled, so they never run out), a
    seeded RNG for fair dice, and the roll counters that the transcript
    reads back. Created inside the game's thunk — never shared between
    runs.
    """

    def __init__(self, players: Iterable[Player], seed: int) -> None:
        self._rng = random.Random(seed)
        self._cycles: dict[str, Iterator[int | None] | None] = {
            player.name: itertools.cycle(player.pattern) if player.pattern else None
            for player in players
        }
        self.rolls: dict[str, int] = {}

    def roll(self, player: Player) -> Option[int]:
        """Return the next roll: ``Some(steps)`` or ``Nothing`` (cocked).

        A die that jams is a defect, not an outcome — it raises
        ``PanicError``, which no combinator here ever folds into an ``Err``.
        """
        self.rolls[player.name] = self.rolls.get(player.name, 0) + 1
        if self.rolls[player.name] == player.jams_on:
            panic(
                f"{player.name}'s die jammed and showed 0 — a fair die shows "
                "1..6 (broken dependency, not a game outcome)"
            )
        cycle = self._cycles[player.name]
        if cycle is not None:
            return from_optional(next(cycle))
        return Some(self._rng.randint(1, 6))


# --------------------------------------------------------------------------
# The engine: pure movement, then lazy turns composed from roll effects
# --------------------------------------------------------------------------


def _resolve(
    player: Player, square: int, steps: int, board: Board, round_no: int
) -> TurnEvent:
    """Move ``square`` by ``steps``: bounce on overshoot, ride at most one chute.

    Pure: same inputs, same event. Landing exactly on the last square wins;
    an overshoot bounces back off the far edge before chutes are consulted.
    """
    landing = square + steps
    if landing > board.size:
        landing = 2 * board.size - landing
    if landing == board.size:
        return TurnEvent(
            player.name, round_no, steps, square, board.size, None, won=True
        )
    match board.lookup(landing):
        case Some(chute):
            return TurnEvent(
                player.name,
                round_no,
                steps,
                square,
                chute.end,
                chute,
                won=chute.end == board.size,
            )
        case Nothing():
            return TurnEvent(
                player.name, round_no, steps, square, landing, None, won=False
            )


def _roll_effect(
    player: Player, session: Session, services: Services
) -> Effect[int, GameError]:
    """One turn's die: an Effect that retries a cocked roll, then gives up.

    The first attempt's ``Nothing`` (cocked) becomes an ``Err``; the retry
    policy re-rolls it once. If the re-roll is cocked too, the last ``Err``
    is returned and the turn is skipped — the game loop handles it as a
    value. ``sleep`` is injected, so retries cost no wall-clock time.
    """

    def one_attempt(_attempt_number: int) -> Result[int, GameError]:
        match session.roll(player):
            case Some(steps):
                # 0 or 7 from a die is impossible — a broken dependency, so
                # it panics here instead of ever becoming an Err.
                if not 1 <= steps <= 6:
                    panic(
                        f"{player.name}'s die showed {steps} — a fair die "
                        "shows 1..6 (broken dependency)"
                    )
                return Ok(steps)
            case Nothing():
                return _game_fail(CockedDieError(player.name))

    def thunk() -> Result[int, GameError]:
        return retry(
            one_attempt,
            REROLL_POLICY,
            sleep=services.sleep,
            should_retry=lambda error, _attempt: isinstance(error, CockedDieError),
        )

    return Effect(thunk)


def _after_roll(
    player: Player, square: int, steps: int, board: Board, round_no: int
) -> Effect[TurnEvent, GameError]:
    """Wrap the resolved turn as an Effect: pure movement, run lazily."""

    def thunk() -> Result[TurnEvent, GameError]:
        return Ok(_resolve(player, square, steps, board, round_no))

    return Effect(thunk)


def turn_effect(
    *,
    player: Player,
    square: int,
    round_no: int,
    board: Board,
    session: Session,
    services: Services,
) -> Effect[TurnEvent, GameError]:
    """One player's turn as a lazy pipeline: roll (with retry) then move.

    ``and_then`` threads the roll into the pure movement step; nothing runs
    until ``run_result()``.
    """
    return _roll_effect(player, session, services).and_then(
        lambda steps: _after_roll(player, square, steps, board, round_no)
    )


def _record(
    players: tuple[Player, ...],
    events: list[TurnEvent],
    positions: dict[str, int],
    session: Session,
    round_no: int,
) -> GameRecord:
    """Collapse a finished game into its record: winner, log, scoreboard."""
    moves = Counter(event.player for event in events)
    return GameRecord(
        winner=events[-1].player,
        rounds=round_no,
        events=tuple(events),
        standings=tuple(
            PlayerScore(player.name, positions[player.name])
            for player in sorted(players, key=lambda p: -positions[p.name])
        ),
        rerolls={
            player.name: session.rolls.get(player.name, 0) - moves[player.name]
            for player in players
        },
    )


def _play(
    players: tuple[Player, ...],
    board: Board,
    seed: int,
    round_cap: int,
    services: Services,
) -> Result[GameRecord, GameError]:
    """Drive one game to a winner or to the round cap.

    Turns run round-robin. A skipped turn (the die stayed cocked through
    every retry) is an event that does not move the player; the loop keeps
    going — only a winner or the cap ends the game.
    """
    session = Session(players, seed)
    positions: dict[str, int] = {player.name: 1 for player in players}
    events: list[TurnEvent] = []
    for round_no in range(1, round_cap + 1):
        for player in players:
            square = positions[player.name]
            outcome = turn_effect(
                player=player,
                square=square,
                round_no=round_no,
                board=board,
                session=session,
                services=services,
            ).run_result()
            match outcome:
                case Ok(event):
                    events.append(event)
                    positions[player.name] = event.to
                    if event.won:
                        return Ok(
                            _record(players, events, positions, session, round_no)
                        )
                case Err():
                    events.append(
                        TurnEvent(
                            player.name, round_no, None, square, square, None, won=False
                        )
                    )
    return _game_fail(GameStalledError(round_cap))


def game_effect(
    players: tuple[Player, ...],
    board: Board,
    seed: int,
    round_cap: int,
    services: Services,
) -> Effect[GameRecord, GameError]:
    """One whole game as a lazy Effect: building runs nothing; run() plays it.

    A fresh Session is created inside the thunk, so the effect is
    re-runnable — running it twice replays the same game from scratch.
    """

    def thunk() -> Result[GameRecord, GameError]:
        return _play(players, board, seed, round_cap, services)

    return Effect(thunk)


# --------------------------------------------------------------------------
# The wire boundary: Codec turns a Scoreboard into an envelope, and back
# --------------------------------------------------------------------------


def _encode_scoreboard(scoreboard: Scoreboard) -> dict[str, object]:
    return {
        "winner": scoreboard.winner,
        "rounds": scoreboard.rounds,
        "turns": scoreboard.turns,
        "standings": [
            {"name": score.name, "position": score.position}
            for score in scoreboard.standings
        ],
    }


def _decode_scoreboard(data: object) -> Result[Scoreboard, str]:
    """Strictly validate the wire form; every mismatch is an ``Err``."""
    if not isinstance(data, dict):
        return Err(f"expected a dict, got {type(data).__name__}")
    winner = data.get("winner")
    rounds = data.get("rounds")
    turns = data.get("turns")
    standings = data.get("standings")
    if not isinstance(winner, str):
        return Err("winner must be a string")
    if not isinstance(rounds, int):
        return Err("rounds must be an int")
    if not isinstance(turns, int):
        return Err("turns must be an int")
    if not isinstance(standings, list):
        return Err("standings must be a list")
    scores: list[PlayerScore] = []
    for entry in standings:
        if not isinstance(entry, dict):
            return Err("standings entries must be dicts")
        name = entry.get("name")
        position = entry.get("position")
        if not isinstance(name, str):
            return Err("standings names must be strings")
        if not isinstance(position, int):
            return Err("standings positions must be ints")
        scores.append(PlayerScore(name, position))
    return Ok(Scoreboard(winner, rounds, turns, tuple(scores)))


def _decode_error(data: object) -> Result[GameError, str]:
    """Error envelopes are logs, not data: they are never decoded back."""
    return Err("scoreboard errors are logs; they are not decoded back")


def scoreboard_codec() -> Codec[Scoreboard, GameError]:
    codec: Codec[Scoreboard, GameError] = Codec(
        _encode_scoreboard,
        lambda error: error.to_dict(),
        _decode_scoreboard,
        _decode_error,
    )
    return codec


# --------------------------------------------------------------------------
# The flaky leaderboard: exceptions at the edge, values inside
# --------------------------------------------------------------------------


class ScoreServer:
    """A scripted stand-in: the first ``blips`` uploads fail, then succeed."""

    def __init__(self, blips: int) -> None:
        self._blips = blips
        self.calls = 0

    def upload(self, payload: dict[str, object]) -> None:
        self.calls += 1
        if self._blips > 0:
            self._blips -= 1
            detail = "connection reset by the leaderboard"
            raise ScoreServerBlipError(detail)


def _translate_upload(exc: Exception) -> UploadError:
    """Map SDK exceptions to tagged domain errors — exceptions become values."""
    if isinstance(exc, ScoreServerBlipError):
        return NetworkBlipError(str(exc))
    return UnhandledError(exc)


def upload_scoreboard(
    codec: Codec[Scoreboard, GameError],
    scoreboard: Scoreboard,
    server: ScoreServer,
    services: Services,
) -> Result[None, UploadError]:
    """Upload one envelope, retrying only transient blips.

    ``attempt`` is the exception boundary: the server raises, the caller
    gets an ``Err``. ``retry`` re-runs the operation with a constant, no-op
    sleep; a blip is retried, anything else fails immediately.
    """
    envelope = codec.serialize_unsafe(Ok(scoreboard))

    def one_attempt(_attempt_number: int) -> Result[None, UploadError]:
        return attempt(lambda: server.upload(envelope), catch=_translate_upload)

    def thunk() -> Result[None, UploadError]:
        return retry(
            one_attempt,
            UPLOAD_POLICY,
            sleep=services.sleep,
            should_retry=lambda error, _attempt: isinstance(error, NetworkBlipError),
        )

    return thunk()


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------


def _describe_board_error(error: BoardError) -> str:
    """Describe a board failure; a missing handler is a bug (MatchError)."""
    return match_error(
        error,
        {
            "PortalToSelf": lambda e: f"chute {e.start}->{e.start} goes nowhere",
            "ChuteOutOfBounds": lambda e: (
                f"chute {e.start}->{e.end} leaves squares 1..{BOARD_SIZE}"
            ),
            "ChuteOnLastSquare": lambda e: (
                f"chute {e.start}->{e.end} starts on the last square"
            ),
            "OverlappingChutes": lambda e: (
                f"chutes {e.start}->{e.end} and another both start on {e.start}"
            ),
            "UnknownBoard": lambda e: f"no board preset named {e.name!r}",
        },
    )


def _describe_game_error(error: GameError) -> str:
    """Describe a game failure by tag, not by string-matching the message."""
    return match_error(
        error,
        {
            "CockedDie": lambda e: f"{e.player}'s die stayed cocked",
            "GameStalled": lambda e: f"no winner after {e.rounds} rounds",
        },
    )


def _turn_line(event: TurnEvent) -> str:
    """Render one turn: ``r5  Luna  rolled 6: 59 -> 63 -> 81 (ladder)``."""
    head = f"r{event.round:>2} {event.player:<5}"
    if event.roll is None:
        return f"{head} die cocked twice — stays at {event.frm}"
    raw = event.frm + event.roll
    if event.won:
        return f"{head} rolled {event.roll}: {event.frm} -> {event.to}  WINS"
    if event.via is not None:
        kind = "ladder" if event.via.is_ladder else "snake"
        tail = f" -> {event.via.start} -> {event.via.end} ({kind})"
    elif raw > BOARD_SIZE:
        tail = f" -> {raw} (bounce) -> {event.to}"
    else:
        tail = f" -> {event.to}"
    return f"{head} rolled {event.roll}: {event.frm}{tail}"


def _standings_line(standings: tuple[PlayerScore, ...]) -> str:
    """Thread the scoreboard through ``pipe`` into one line."""
    return pipe(
        standings,
        lambda scores: ", ".join(
            f"{score.name} @ {score.position}" for score in scores
        ),
    )


# --------------------------------------------------------------------------
# Demo data and the run
# --------------------------------------------------------------------------

# Luna: scripted attempts. The leading None makes her first roll come up
# cocked (retried once); the rest climb 1 -> 14 -> 38 -> 44 -> 50 -> snake
# 54 -> 34 -> ladder 40 -> 59 -> ladder 63 -> 81 -> 86 -> 92 -> 94 -> 100.
LUNA = Player("Luna", (None, 3, 6, 6, 6, 4, 6, 4, 5, 6, 2, 6))

# Zed: his first turn is double-cocked (skipped), then he slithers 5, 8, 13,
# hits snake 17 -> 7, rides ladder 9 -> 31, and chases Luna up the board.
ZED = Player("Zed", (None, None, 4, 3, 5, 4, 2, 3, 6, 4, 2))

MIRA = Player("Mira")
THEO = Player("Theo")
JUN = Player("Jun")

# Dice of ones: Tortoise and Snail advance one square per turn and can
# never reach square 100 inside the round cap — a guaranteed stall.
TORTOISE = Player("Tortoise", (1,))
SNAIL = Player("Snail", (1,))


def _section_one() -> None:
    print("== 1. the board — expected config failures are values ==")
    print("   a preset is validated chute by chute (traverse fails fast):")
    match load_preset("classic"):
        case Ok(board):
            ladders = sum(1 for chute in board.chutes if chute.is_ladder)
            snakes = len(board.chutes) - ladders
            print(
                f"   classic: {len(board.chutes)} chutes accepted "
                f"({ladders} ladders, {snakes} snakes)"
            )
        case Err(error):
            print(f"   classic rejected: {_describe_board_error(error)}")
    print("   a board that arrives over the wire is untrusted data:")
    match _validate(((4, 14), (17, 7), (40, 40))):
        case Ok(_):
            print("   (unreachable) wire board accepted")
        case Err(error):
            print(f"   rejected a wire board: {_describe_board_error(error)}")
    match _validate(((4, 14), (95, 101))):
        case Err(error):
            print(f"   rejected another wire board: {_describe_board_error(error)}")
        case Ok(_):
            print("   (unreachable) second wire board accepted")
    print("   an unknown preset is an Err too — recover to the house board:")
    match load_preset("royale"):
        case Err(error):
            print(f"   preset 'royale': {_describe_board_error(error)}")
        case Ok(_):
            print("   (unreachable) preset 'royale' accepted")
    match recover(load_preset("royale"), lambda _error: Ok(CLASSIC_BOARD)):
        case Ok(board):
            print(f"   recovered by falling back to the house board ({board.name})")
        case Err(error):
            print(f"   recover failed: {_describe_board_error(error)}")


def _section_two(services: Services) -> None:
    print()
    print("== 2. the dice tower — one race, played lazily ==")
    print(
        "   Luna vs Zed on the classic board. game_effect(...) is a lazy "
        "Effect: building it runs nothing."
    )
    game = game_effect(
        (LUNA, ZED), CLASSIC_BOARD, seed=0, round_cap=15, services=services
    )
    match game.run_result():
        case Ok(record):
            for event in record.events:
                print(f"   {_turn_line(event)}")
            print()
            print(f"   {record.winner} reached square 100 in round {record.rounds}")
            print(f"   standings: {_standings_line(record.standings)}")
            dice = ", ".join(
                f"{player.name} {record.rerolls[player.name]} reroll"
                + ("s" if record.rerolls[player.name] != 1 else "")
                for player in (LUNA, ZED)
            )
            print(f"   dice: {dice} (cocked rolls are retried once, then skipped)")
            match game.run_result():
                case Ok(replay):
                    identical = replay.winner == record.winner and len(
                        replay.events
                    ) == len(record.events)
                    print(
                        f"   replay: running the same Effect again produced the same "
                        f"winner ({replay.winner}) in {len(replay.events)} turns "
                        f"— identical: {identical}"
                    )
                case Err(error):
                    print(f"   replay stalled: {_describe_game_error(error)}")
        case Err(error):
            print(f"   the race stalled: {_describe_game_error(error)}")


def _section_three(services: Services, seed: int) -> None:
    print()
    print("== 3. the tournament — every game's outcome is a value ==")
    games: tuple[Game, ...] = (
        Game(
            "mira / theo / jun, fair dice",
            (MIRA, THEO, JUN),
            seed=seed,
            round_cap=15,
        ),
        Game(
            "tortoise / snail, dice of ones",
            (TORTOISE, SNAIL),
            seed=0,
            round_cap=10,
        ),
    )
    results = [
        game_effect(
            game.players, CLASSIC_BOARD, game.seed, game.round_cap, services
        ).run_result()
        for game in games
    ]
    for game, result in zip(games, results, strict=True):
        match result:
            case Ok(record):
                print(
                    f"   [{game.label}] {record.winner} wins in round {record.rounds}"
                )
            case Err(error):
                print(f"   [{game.label}] {_describe_game_error(error)}")
    finished, stalled = partition(results)
    print(
        f"   partition: {len(finished)} game(s) finished, "
        f"{len(stalled)} stalled (seed {seed})"
    )


def _section_four(services: Services) -> None:
    print()
    print("== 4. wire — a scoreboard survives the boundary ==")
    codec = scoreboard_codec()
    game = game_effect(
        (LUNA, ZED), CLASSIC_BOARD, seed=0, round_cap=15, services=services
    )
    match game.run_result():
        case Ok(record):
            scoreboard = Scoreboard(
                record.winner, record.rounds, len(record.events), record.standings
            )
            envelope = codec.serialize(Ok(scoreboard)).expect(
                "scoreboard encoding is total"
            )
            print(f"   envelope: {envelope}")
            match codec.deserialize(envelope):
                case Ok(decoded):
                    print(
                        f"   round trip: decoded == original: {decoded == scoreboard}"
                    )
                case Err(error):
                    print(f"   round trip rejected: {error.tag} ({error})")
            print("   the envelope is tampered with before it comes back...")
            payload = envelope["value"]
            if isinstance(payload, dict):
                payload["rounds"] = "not-an-int"
            match codec.deserialize(envelope):
                case Ok(_):
                    print("   (unreachable) tampered envelope accepted")
                case Err(error):
                    print(f"   rejected: {error.tag} ({error})")
            print("   uploading to a flaky leaderboard server...")
            server = ScoreServer(blips=2)
            match upload_scoreboard(codec, scoreboard, server, services):
                case Ok(None):
                    print(
                        f"   uploaded after {server.calls} attempts "
                        f"({server.calls - 1} transient blips retried)"
                    )
                case Err(error):
                    print(f"   upload failed: {error.tag}")
            stalled_envelope = codec.serialize(Err(GameStalledError(10))).expect(
                "error encoding is total"
            )
            print(f"   a stalled game is logged as: {stalled_envelope}")
        case Err(error):
            print(f"   the demo game stalled: {_describe_game_error(error)}")


def _section_five(services: Services, seed: int) -> int:
    """Run the defect demo: a die that jams panics at the boundary."""
    print()
    print("== 5. defect boundary — the one bug is reported, not folded ==")
    print("   Luna's die jams on her 8th roll: a physical impossibility.")
    luna = Player("Luna", (None, 3, 6, 6, 6, 4, 6, 4, 5, 6, 2, 6), jams_on=8)
    zed = Player("Zed", (1,))
    game = game_effect(
        (luna, zed), CLASSIC_BOARD, seed=seed, round_cap=15, services=services
    )
    try:
        game.run_result()
    except PanicError as defect:
        print(f"   {defect}")
        print(
            "   main() — the only place allowed to catch PanicError — "
            "reports the bug and exits 1. The panic was never an Err."
        )
        return 1
    print("   no panic raised (unexpected)")
    return 2


def main(argv: list[str]) -> int:
    """Entry point — the only place a PanicError is caught.

    Domain failures never reach this code: they are Err values handled in
    the sections above. A PanicError reaching here is a bug and is reported
    as one — never converted back into an Err.
    """
    break_die = "--break-die" in argv
    seed = TOURNEY_SEED
    for flag in argv:
        if flag.startswith("--seed="):
            seed = int(flag.removeprefix("--seed="))
    services = Services(sleep=lambda _seconds: None)  # injected: retries cost 0s
    _section_one()
    _section_two(services)
    _section_three(services, seed)
    _section_four(services)
    if break_die:
        return _section_five(services, seed)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
