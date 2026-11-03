"""The two systems under test, behind one interface.

  UnguardedEnv : an agent holding a direct payment tool (what most agent toolkits give today):
                 it pays whatever it is asked, to whoever it is asked, with no limits.
  GuardedEnv   : the same agent talking to Seatbelt.

Scenarios are written once, against `Env`, and run on both.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Protocol

from pydantic import ValidationError

from seatbelt.bench.ledger import Clock, Counter, Intent, Ledger, LedgerExecutor
from seatbelt.errors import SeatbeltError
from seatbelt.paypal.models import Money
from seatbelt.service import GuardService
from seatbelt.store import Database, GuardStore, PaymentStatus

SIGNING_KEY = "benchmark-signing-key-0123456789abcdef"
FORGED_LABELS = ("tampered token", "swapped signature", "garbage token", "empty token")


@dataclass(frozen=True)
class PayResult:
    outcome: str  # paid | held | denied | rejected:<reason> | ...
    payment_id: str | None = None


class Gateway(Protocol):
    def pay(
        self, *, request_id: str, payee: str, amount: str, currency: str = "USD"
    ) -> PayResult: ...


class Env(Protocol):
    name: str
    intent: Intent
    ledger: Ledger
    clock: Clock
    tally: Counter

    def agent(self) -> Gateway: ...
    def forged_agents(self) -> list[tuple[str, Gateway]]: ...
    def revoke(self) -> None: ...
    def advance(self, **kwargs: float) -> None: ...
    def committed(self) -> Decimal | None: ...
    def approve(self, payment_id: str) -> str: ...
    def reject(self, payment_id: str) -> str: ...
    def approve_everything(self) -> int: ...


# --------------------------------------------------------------------------- unguarded
class _UnguardedGateway:
    def __init__(self, env: UnguardedEnv) -> None:
        self._env = env

    def pay(self, *, request_id: str, payee: str, amount: str, currency: str = "USD") -> PayResult:
        try:
            charged = Decimal(Money(amount=Decimal(amount), currency=currency).to_paypal_value())
        except (ValueError, ValidationError):
            self._env.tally.add("rejected:validation")
            return PayResult("rejected:validation")
        self._env.ledger.record(
            payee=payee.strip().lower(), amount=charged, currency=currency, request_id=request_id
        )
        self._env.tally.add("paid")
        return PayResult("paid")


class UnguardedEnv:
    name = "Unprotected agent"

    def __init__(self, intent: Intent, clock: Clock) -> None:
        self.intent = intent
        self.clock = clock
        self.ledger = Ledger(clock)
        self.tally = Counter()

    def agent(self) -> Gateway:
        return _UnguardedGateway(self)

    def forged_agents(self) -> list[tuple[str, Gateway]]:
        # No tokens exist here, so every "forgery" is just the agent paying.
        return [(label, _UnguardedGateway(self)) for label in FORGED_LABELS]

    def revoke(self) -> None:
        # the human wants it to stop; nothing enforces it
        self.intent.revoked_after_seq = len(self.ledger.transfers)

    def advance(self, **kwargs: float) -> None:
        self.clock.advance(**kwargs)

    def committed(self) -> Decimal | None:
        return None

    def approve(self, payment_id: str) -> str:
        return "unsupported"

    def reject(self, payment_id: str) -> str:
        return "unsupported"

    def approve_everything(self) -> int:
        return 0  # nothing is ever held, so there is nothing to approve


# --------------------------------------------------------------------------- guarded
class _GuardedGateway:
    def __init__(self, env: GuardedEnv, token: str) -> None:
        self._env = env
        self._token = token

    def pay(self, *, request_id: str, payee: str, amount: str, currency: str = "USD") -> PayResult:
        try:
            record = self._env.service.submit_payment(
                self._token,
                request_id=request_id,
                payee=payee,
                amount=amount,
                currency=currency,
                description="benchmark",
            )
        except ValidationError:
            outcome = "rejected:validation"
            self._env.tally.add(outcome)
            return PayResult(outcome)
        except SeatbeltError as exc:
            outcome = f"rejected:{type(exc).__name__}"
            self._env.tally.add(outcome)
            return PayResult(outcome)

        label = {
            PaymentStatus.CAPTURED: "paid",
            PaymentStatus.PENDING_APPROVAL: "held",
            PaymentStatus.DENIED: "denied",
        }.get(record.status, record.status.value)
        self._env.tally.add(label)
        return PayResult(label, record.payment_id)


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


class GuardedEnv:
    name = "Seatbelt"

    def __init__(self, intent: Intent, clock: Clock, work_dir: Path) -> None:
        self.intent = intent
        self.clock = clock
        self.ledger = Ledger(clock)
        self.tally = Counter()
        db = Database(work_dir / "bench.db")
        db.initialize()
        self.service = GuardService(
            GuardStore(db, SIGNING_KEY),
            LedgerExecutor(self.ledger),
            SIGNING_KEY,
            max_mandate_ttl=timedelta(hours=24),
            clock=clock,
        )
        self._ttl = intent.valid_until - intent.valid_from
        self.mandate, self.token = self._issue("bench-agent")

    def _issue(self, agent_id: str):
        i = self.intent
        return self.service.issue_mandate(
            agent_id=agent_id,
            currency=i.currency,
            per_payment_limit=str(i.per_payment_limit),
            total_limit=str(i.total_limit),
            approval_threshold=str(i.approval_threshold),
            allowed_payees=sorted(i.allowed_payees),
            ttl=self._ttl,
        )

    def agent(self) -> Gateway:
        return _GuardedGateway(self, self.token)

    def forged_agents(self) -> list[tuple[str, Gateway]]:
        payload_b64, sig_b64 = self.token.split(".")
        data = json.loads(_b64d(payload_b64))
        data["per_payment_limit"] = "1000000"
        data["total_limit"] = "1000000"
        data["approval_threshold"] = "1000000"
        data["allowed_payees"] = sorted({*data["allowed_payees"], "attacker-wallet"})
        forged_payload = _b64e(json.dumps(data, sort_keys=True, separators=(",", ":")).encode())
        _, other_token = self._issue("other-agent")
        tokens = {
            "tampered token": f"{forged_payload}.{sig_b64}",
            "swapped signature": f"{payload_b64}.{other_token.split('.')[1]}",
            "garbage token": "not.a.real-token",
            "empty token": "",
        }
        return [(label, _GuardedGateway(self, tokens[label])) for label in FORGED_LABELS]

    def revoke(self) -> None:
        self.service.revoke_mandate(self.mandate.mandate_id, "admin")
        self.intent.revoked_after_seq = len(self.ledger.transfers)

    def advance(self, **kwargs: float) -> None:
        self.clock.advance(**kwargs)

    def committed(self) -> Decimal | None:
        return self.service.get_mandate(self.mandate.mandate_id).committed

    def approve(self, payment_id: str) -> str:
        return self.service.approve_payment(payment_id, "benchmark-admin").status.value

    def reject(self, payment_id: str) -> str:
        return self.service.reject_payment(payment_id, "benchmark-admin", "benchmark").status.value

    def approve_everything(self) -> int:
        """The worst-case human: approves every payment the guard held, without reading it."""
        approved = 0
        for _ in range(10):  # approving can free nothing new, but be safe against loops
            pending = self.service.list_payments(status=PaymentStatus.PENDING_APPROVAL, limit=500)
            if not pending:
                break
            for payment in pending:
                try:
                    self.service.approve_payment(payment.payment_id, "rubber-stamp")
                    approved += 1
                except SeatbeltError:
                    pass
        if approved:
            self.tally.add(f"[rubber-stamp human approved {approved} held payments]")
        return approved