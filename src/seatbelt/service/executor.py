"""How an approved payment actually moves money.

The guard decides WHETHER to pay; an executor does the paying. Keeping them separate means
the guard logic is tested without any network, and the PayPal-backed executor plugs in
without changing it.

Contract: `execute` must either move the money exactly once and return its ids, or raise
ExecutionError meaning the money did NOT move. The payment_id is a stable idempotency key,
so calling execute again for the same payment must never pay twice.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Protocol

from seatbelt.errors import ExecutionError
from seatbelt.store.models import PaymentRecord


@dataclass(frozen=True)
class ExecutionResult:
    capture_id: str
    order_id: str | None = None


class PaymentExecutor(Protocol):
    def execute(self, payment: PaymentRecord) -> ExecutionResult: ...


class FakeExecutor:
    """Simulated payments for tests and local development. Never talks to PayPal."""

    def __init__(self, *, fail_for_payees: set[str] | None = None) -> None:
        self._fail_for = {p.lower() for p in (fail_for_payees or set())}
        self._lock = threading.Lock()
        self.executed: list[str] = []  # payment ids, in call order

    def execute(self, payment: PaymentRecord) -> ExecutionResult:
        with self._lock:
            self.executed.append(payment.payment_id)
        if payment.payee in self._fail_for:
            raise ExecutionError(f"simulated failure paying {payment.payee}")
        short = payment.payment_id[:16]
        return ExecutionResult(capture_id=f"SIM-CAP-{short}", order_id=f"SIM-ORD-{short}")