"""A runnable checkout pipeline — pyeffect applied to one coherent order flow.

This is not a feature tour; it is one application that meets the library's
one rule at every boundary:

* **Expected failures are values.** No such order, unknown SKU, out of
  stock, a declined card, a gateway timeout — each is an ``Err`` carrying a
  ``TaggedError`` with a ``tag`` you can match on.
* **Impossible states are bugs and panic.** The gateway settling a different
  amount than it was quoted is a broken invariant, so ``panic()`` fires at
  the exact line instead of returning a wrong receipt.
* **``Panic`` is caught exactly once** — at the process boundary in
  ``main()``, which is the only place allowed to catch it.

Run it from this directory (``pyeffect`` resolves to the repo this example
lives in, see ``pyproject.toml``):

    uv run python main.py                      # healthy flow, exit 0
    uv run python main.py --break-settlement   # inject a bug, watch the
                                               # defect boundary report it

Each section of the transcript is one library module:

    == 1. quote   == ``Option`` lookup, ``Result`` validation, ``do``-notation,
                     ``traverse`` (fail fast), tagged errors, ``pipe``
    == 2. checkout== lazy ``Effect`` composition via ``do_effect``, ``partition``
                     (keep every outcome), ``attempt`` as the exception boundary
    == 3. retry   == ``retry`` + ``Policy``: exponential backoff, ``should_retry``,
                     injected ``sleep``
    == 4. wire    == ``Codec``: serialize/deserialize a ``Result`` to an
                     envelope; a tampered envelope comes back as an ``Err``
"""

from __future__ import annotations

import json
import sys
import time
from collections.abc import Callable, Generator, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from pyeffect import (
    Codec,
    Effect,
    Err,
    Nothing,
    Ok,
    Panic,
    Policy,
    Result,
    Some,
    TaggedError,
    UnhandledException,
    attempt,
    do,
    do_effect,
    from_optional,
    match_error,
    panic,
    partition,
    pipe,
    retry,
    traverse,
)

# --------------------------------------------------------------------------
# Domain data
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Line:
    sku: str
    qty: int


@dataclass(frozen=True, slots=True)
class Order:
    order_id: str
    user: str
    card_token: str
    lines: tuple[Line, ...]


@dataclass(frozen=True, slots=True)
class PricedOrder:
    order: Order
    total_cents: int


@dataclass(frozen=True, slots=True)
class Payment:
    auth: str
    settled_cents: int


@dataclass(frozen=True, slots=True)
class Receipt:
    order_id: str
    user: str
    total_cents: int
    auth: str


# --------------------------------------------------------------------------
# The error vocabulary: tagged errors, one pipeline-wide union
# --------------------------------------------------------------------------


class OrderNotFound(TaggedError, tag="OrderNotFound"):
    def __init__(self, order_id: str) -> None:
        self.order_id = order_id
        super().__init__(f"no order {order_id}")


class UnknownSku(TaggedError, tag="UnknownSku"):
    def __init__(self, order_id: str, sku: str) -> None:
        self.order_id = order_id
        self.sku = sku
        super().__init__(f"order {order_id} references unknown sku {sku}")


class ValidationError(TaggedError, tag="ValidationError"):
    def __init__(self, order_id: str, reasons: list[str]) -> None:
        self.order_id = order_id
        self.reasons = reasons
        super().__init__(f"order {order_id} is invalid: {'; '.join(reasons)}")


class OutOfStock(TaggedError, tag="OutOfStock"):
    def __init__(self, order_id: str, sku: str, available: int) -> None:
        self.order_id = order_id
        self.sku = sku
        self.available = available
        super().__init__(f"{sku} has only {available} in stock")


class GatewayTimeout(TaggedError, tag="GatewayTimeout"):
    """Transient: retryable."""

    def __init__(self, order_id: str, detail: str) -> None:
        self.order_id = order_id
        super().__init__(detail)


class CardDeclined(TaggedError, tag="CardDeclined"):
    """Terminal: never retried."""

    def __init__(self, order_id: str, reason: str) -> None:
        self.order_id = order_id
        self.reason = reason
        super().__init__(reason)


type CheckoutError = (
    OrderNotFound
    | UnknownSku
    | ValidationError
    | OutOfStock
    | GatewayTimeout
    | CardDeclined
    | UnhandledException
)


def fail[X](error: CheckoutError) -> Result[X, CheckoutError]:
    """Build an ``Err`` at the pipeline's error type.

    Python generics are invariant, so ``Err[ValidationError]`` is not an
    ``Err[CheckoutError]`` — this helper widens once, at one place.
    """

    return Err(error)


# --------------------------------------------------------------------------
# Dependencies (injected so the demo is deterministic and runs offline)
# --------------------------------------------------------------------------


@dataclass
class Catalog:
    prices: dict[str, int]


@dataclass
class Inventory:
    stock: dict[str, int]


@dataclass
class Store:
    orders: dict[str, Order]


class GatewayTimeoutError(Exception):
    """The SDK's transient failure — raised, because SDKs raise."""


class CardDeclinedError(Exception):
    """The SDK's terminal failure — raised, because SDKs raise."""


type GatewayOutcome = Literal["timeout", "declined", "ok"]


class PaymentGateway:
    """A scripted stand-in for a third-party gateway.

    ``charge`` raises on failure like a real SDK. Each order id maps to a
    per-attempt script that is consumed one outcome at a time and defaults
    to ``"ok"``.
    """

    def __init__(
        self,
        scenarios: Mapping[str, Sequence[GatewayOutcome]],
        *,
        settle_shift: int = 0,
    ) -> None:
        self._scenarios = {
            order_id: list(outcomes) for order_id, outcomes in scenarios.items()
        }
        self._settle_shift = settle_shift  # a buggy build can settle off-quote
        self.attempts: dict[str, int] = {}
        self.outcomes: dict[str, list[str]] = {}

    def charge(self, order_id: str, card_token: str, amount_cents: int) -> Payment:
        remaining = self._scenarios.get(order_id, [])
        outcome = remaining.pop(0) if remaining else "ok"
        self.attempts[order_id] = self.attempts.get(order_id, 0) + 1
        self.outcomes.setdefault(order_id, []).append(outcome)
        if outcome == "timeout":
            raise GatewayTimeoutError("the gateway did not respond in time")
        if outcome == "declined":
            raise CardDeclinedError("insufficient funds")
        return Payment(
            auth=f"AUTH-{order_id}",
            settled_cents=amount_cents + self._settle_shift,
        )


def translate_gateway_error(order_id: str, exc: Exception) -> CheckoutError:
    """Map SDK exceptions to tagged domain errors — exceptions become values.

    Domain errors carry the order they happened for, so an error survives
    ``partition`` and still tells you which order failed.
    """

    if isinstance(exc, GatewayTimeoutError):
        return GatewayTimeout(order_id, str(exc))
    if isinstance(exc, CardDeclinedError):
        return CardDeclined(order_id, str(exc))
    return UnhandledException(exc)


@dataclass
class Services:
    store: Store
    catalog: Catalog
    inventory: Inventory
    gateway: PaymentGateway
    sleep: Callable[[float], None] = time.sleep


# --------------------------------------------------------------------------
# Pure pipeline: lookup -> validate -> price (Result do-notation)
# --------------------------------------------------------------------------


def _lookup(store: Store, order_id: str) -> Result[Order, CheckoutError]:
    """Expected absence is an ``Option``; match on the variants."""

    match from_optional(store.orders.get(order_id)):
        case Some(order):
            return Ok(order)
        case Nothing():
            return fail(OrderNotFound(order_id))


def _validate(order: Order) -> Result[Order, CheckoutError]:
    """Business rules that can refuse are expected failures: values."""

    problems = [
        f"{line.sku}: qty must be >= 1, got {line.qty}"
        for line in order.lines
        if line.qty < 1
    ]
    if not order.lines:
        problems.append("order has no items")
    if problems:
        return fail(ValidationError(order.order_id, problems))
    return Ok(order)


def _price(catalog: Catalog, order: Order) -> Result[int, CheckoutError]:
    total = 0
    for line in order.lines:
        price = catalog.prices.get(line.sku)
        if price is None:
            return fail(UnknownSku(order.order_id, line.sku))
        total += price * line.qty
    return Ok(total)


def price_order(
    store: Store, catalog: Catalog, order_id: str
) -> Result[PricedOrder, CheckoutError]:
    """Price one order, linearly.

    ``do`` unwraps one ``Result`` per ``for`` clause; an ``Err``
    short-circuits the whole expression. The success type flows precisely
    through every step.
    """

    return do(
        Ok(PricedOrder(order=order, total_cents=total))
        for order in _lookup(store, order_id)
        for total in _price(catalog, order)
    )


# --------------------------------------------------------------------------
# Impure steps: reservation and payment (exceptions at the edge, values inside)
# --------------------------------------------------------------------------


def reserve(inventory: Inventory, priced: PricedOrder) -> Result[None, CheckoutError]:
    """Check every line first, then decrement: a failed order changes nothing."""

    for line in priced.order.lines:
        available = inventory.stock.get(line.sku, 0)
        if available < line.qty:
            return fail(OutOfStock(priced.order.order_id, line.sku, available))
    for line in priced.order.lines:
        inventory.stock[line.sku] -= line.qty
    return Ok(None)


def charge_with_retry(
    gateway: PaymentGateway,
    order: Order,
    amount_cents: int,
    *,
    sleep: Callable[[float], None],
) -> Result[Payment, CheckoutError]:
    """Charge with exponential backoff; only transient failures are retried."""

    policy = Policy(max_attempts=3, delay=0.05, backoff="exponential", jitter=0.2)

    def one_attempt(attempt_number: int) -> Result[Payment, CheckoutError]:
        # The SDK raises; attempt() is the exception boundary that turns
        # the failure into an Err value (a Panic would still propagate).
        return attempt(
            lambda: gateway.charge(order.order_id, order.card_token, amount_cents),
            catch=lambda exc: translate_gateway_error(order.order_id, exc),
        )

    return retry(
        one_attempt,
        policy,
        sleep=sleep,  # injected: tests pass a no-op, prod passes time.sleep
        should_retry=lambda error, _attempt: isinstance(error, GatewayTimeout),
    )


# --------------------------------------------------------------------------
# The lazy pipeline: Effects composed with do_effect
# --------------------------------------------------------------------------


def price_effect(services: Services, order_id: str) -> Effect[PricedOrder, CheckoutError]:
    return Effect(lambda: price_order(services.store, services.catalog, order_id))


def reserve_effect(services: Services, priced: PricedOrder) -> Effect[None, CheckoutError]:
    return Effect(lambda: reserve(services.inventory, priced))


def charge_effect(services: Services, priced: PricedOrder) -> Effect[Payment, CheckoutError]:
    return Effect(
        lambda: charge_with_retry(
            services.gateway, priced.order, priced.total_cents, sleep=services.sleep
        )
    )


def receipt_effect(
    services: Services, priced: PricedOrder, payment: Payment
) -> Effect[Receipt, CheckoutError]:
    """Build the receipt — checking the one invariant that must hold."""

    def thunk() -> Result[Receipt, CheckoutError]:
        if payment.settled_cents != priced.total_cents:
            # Impossible unless a dependency is buggy, so it panics at the
            # exact line; the defect boundary in main() reports the bug.
            panic(
                f"gateway settled {payment.settled_cents}c but order "
                f"{priced.order.order_id} was quoted {priced.total_cents}c"
            )
        receipt = Receipt(
            order_id=priced.order.order_id,
            user=priced.order.user,
            total_cents=priced.total_cents,
            auth=payment.auth,
        )
        return Ok(receipt)

    return Effect(thunk)


def checkout_effect(services: Services, order_id: str) -> Effect[Receipt, CheckoutError]:
    """Checkout one order as a lazy pipeline: nothing runs until ``run_result``.

    ``do_effect`` is do-notation for effects: each ``for`` clause runs one
    effect (a failure short-circuits), and the first expression is the
    final effect. Dependencies are captured in the thunks' closures.
    """

    def build() -> Generator[Effect[Receipt, CheckoutError], None, None]:
        return (
            receipt_effect(services, priced, payment)
            for priced in price_effect(services, order_id)
            for _reserved in reserve_effect(services, priced)
            for payment in charge_effect(services, priced)
        )

    return do_effect(build)


# --------------------------------------------------------------------------
# The wire boundary: Codec turns Result[Receipt, CheckoutError] into dicts
# --------------------------------------------------------------------------


def encode_receipt(receipt: Receipt) -> dict[str, object]:
    return {
        "order_id": receipt.order_id,
        "user": receipt.user,
        "total_cents": receipt.total_cents,
        "auth": receipt.auth,
    }


def decode_receipt(data: object) -> Result[Receipt, object]:
    """Strictly validate the wire form; every mismatch is an ``Err`` (expected)."""

    if not isinstance(data, dict):
        return Err((f"expected a dict, got {type(data).__name__}",))
    order_id = data.get("order_id")
    user = data.get("user")
    total_cents = data.get("total_cents")
    auth = data.get("auth")
    if not isinstance(order_id, str):
        return Err(("order_id must be a string",))
    if not isinstance(user, str):
        return Err(("user must be a string",))
    if not isinstance(auth, str):
        return Err(("auth must be a string",))
    if not isinstance(total_cents, int):
        return Err(("total_cents must be an int",))
    return Ok(Receipt(order_id, user, total_cents, auth))


def encode_error(error: CheckoutError) -> dict[str, object]:
    """Error envelopes keep tag + message; payload fields are dropped."""

    return error.to_dict()


def decode_error(data: object) -> Result[CheckoutError, object]:
    """Error envelopes are logs, not data: they are never decoded back."""

    return Err(("error envelopes are logs; they are not decoded back",))


def receipt_codec() -> Codec[Receipt, CheckoutError]:
    codec: Codec[Receipt, CheckoutError] = Codec(
        encode_receipt,
        encode_error,
        decode_receipt,
        decode_error,
    )
    return codec


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------


def _render_total(cents: int) -> str:
    """``pipe`` threads a value through pure steps, left to right."""

    return pipe(cents, lambda c: c / 100, lambda d: f"${d:.2f}")


def _failure_message(error: CheckoutError) -> str:
    """Every tag in the union has a handler — forget one and match_error
    raises ``MatchError`` (a Panic) instead of printing garbage."""

    return match_error(
        error,
        {
            "OrderNotFound": lambda e: f"order {e.order_id} was not found",
            "UnknownSku": lambda e: f"order {e.order_id}: sku {e.sku} is not in the catalog",
            "ValidationError": lambda e: f"order {e.order_id} is invalid: {', '.join(e.reasons)}",
            "OutOfStock": lambda e: f"order {e.order_id}: sku {e.sku} is out of stock (only {e.available} left)",
            "GatewayTimeout": lambda e: f"order {e.order_id}: gateway timed out ({e})",
            "CardDeclined": lambda e: f"order {e.order_id}: payment declined ({e.reason})",
            "UnhandledException": lambda e: f"unexpected failure: {e}",
        },
    )


# --------------------------------------------------------------------------
# Demo data and the run
# --------------------------------------------------------------------------


def _demo_services(*, settle_shift: int = 0) -> Services:
    store = Store(
        orders={
            "A100": Order("A100", "ada", "tok-ada", (Line("mug", 1), Line("tee", 1))),
            "B200": Order("B200", "bob", "tok-bob", (Line("tee", 1),)),
            "C300": Order("C300", "cyn", "tok-cyn", (Line("cap", 2),)),
            # D400's sku is in the catalog but under-stocked (fails at reserve).
            "D400": Order("D400", "dee", "tok-dee", (Line("rare-mug", 10),)),
            # E500 references a sku the catalog does not know (fails at price).
            "E500": Order("E500", "eli", "tok-eli", (Line("tee", 1), Line("vaporware", 1))),
        }
    )
    catalog = Catalog(prices={"mug": 1200, "tee": 2500, "cap": 1800, "rare-mug": 15000})
    inventory = Inventory(stock={"mug": 50, "tee": 20, "cap": 5, "rare-mug": 3})
    gateway = PaymentGateway(
        {
            "A100": ["timeout", "timeout", "ok"],  # two timeouts, then success
            "B200": ["declined"],  # terminal: should_retry refuses, no retries
        },
        settle_shift=settle_shift,
    )
    return Services(store, catalog, inventory, gateway)


def _run(services: Services) -> None:
    codec = receipt_codec()

    print("== 1. quote every order — traverse fails fast ==")
    quotes = traverse(
        lambda order_id: price_order(services.store, services.catalog, order_id),
        ("A100", "B200", "C300", "D400", "E500"),
    )
    match quotes:
        case Ok(priced_orders):
            for priced in priced_orders:
                print(f"   {priced.order.order_id}: {_render_total(priced.total_cents)}")
        case Err(error):
            print(f"   quoting stopped at: {_failure_message(error)}")
            print("   (A100-D400 priced fine, but traverse is all-or-nothing)")

    print()
    print("== 2. checkout each order — effects run, partition keeps every outcome ==")
    results = [
        checkout_effect(services, order_id).run_result()
        for order_id in ("A100", "B200", "C300", "D400")
    ]
    receipts, failures = partition(results)
    for receipt in receipts:
        print(
            f"   {receipt.order_id}: charged {_render_total(receipt.total_cents)} "
            f"[{receipt.auth}]"
        )
    for error in failures:
        print(f"   {_failure_message(error)}")

    print()
    print("== 3. retry policy — only transient failures retry ==")
    for order_id in sorted(services.gateway.attempts):
        attempts = services.gateway.attempts[order_id]
        outcomes = services.gateway.outcomes[order_id]
        if outcomes[-1] != "ok":
            verdict = "terminal, not retried"
        elif len(outcomes) == 1:
            verdict = "succeeded on the first attempt"
        else:
            verdict = "retried until ok"
        print(f"   {order_id}: {attempts} attempt(s) {outcomes} ({verdict})")
    print("   (sleep was injected: exponential backoff 50ms base, 20% jitter)")

    print()
    print("== 4. wire boundary — Codec round-trips a Result through a dict ==")
    a100 = next(receipt for receipt in receipts if receipt.order_id == "A100")
    envelope = codec.serialize(Ok(a100)).expect("receipt encoding is total")
    print(f"   envelope: {json.dumps(envelope)}")
    match codec.deserialize(envelope):
        case Ok(roundtrip):
            print(
                f"   round trip: {roundtrip.order_id} "
                f"{_render_total(roundtrip.total_cents)} (decoded == original: "
                f"{roundtrip == a100})"
            )
        case Err(issue):
            print(f"   round trip failed: {issue}")  # unreachable: encoder is total
    # A tampered envelope is an expected wire failure: it decodes to an Err.
    payload = envelope["value"]
    if isinstance(payload, dict):
        payload["total_cents"] = "not-an-int"  # corrupt the wire payload
    match codec.deserialize(envelope):
        case Ok(_):
            print("   tampered envelope decoded?!")  # unreachable
        case Err(issue):
            print(f"   tampered envelope rejected: {type(issue).__name__}")
    declined = codec.serialize(Err(CardDeclined("B200", "insufficient funds"))).expect(
        "error encoding is total"
    )
    print(f"   declined order is logged as: {json.dumps(declined)}")


def main(argv: list[str]) -> int:
    """Entry point — the only place a Panic is caught (the defect boundary).

    Domain failures never reach this code: they are ``Err`` values handled
    above. A ``Panic`` reaching here is a bug, and it is reported as one —
    never converted back into an ``Err``.
    """

    break_settlement = "--break-settlement" in argv
    services = _demo_services(settle_shift=1 if break_settlement else 0)
    try:
        _run(services)
    except Panic as defect:
        print()
        print("== a Panic reached the defect boundary (this is a bug) ==")
        print(f"   {type(defect).__name__}: {defect}")
        if defect.cause is not None:
            print(f"   cause: {defect.cause!r}")
        print("   the checkout crashed instead of writing a wrong receipt")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
