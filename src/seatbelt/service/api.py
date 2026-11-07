"""The guard's HTTP API.

Two kinds of caller, two kinds of credential (both sent as `Authorization: Bearer ...`):

  agent : the signed MANDATE TOKEN. Can submit payments and read its own payments only.
  admin : the ADMIN API KEY. Can issue/revoke mandates, approve/reject/retry payments,
          and read everything including the audit log.

Errors never leak internals: expected failures map to precise status codes; anything
unexpected becomes a generic 500 (details go to the server log only).
"""

import hmac
import logging
from datetime import timedelta
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import SecretStr, ValidationError

from seatbelt import __version__
from seatbelt.errors import (
    AuditIntegrityError,
    IdempotencyConflictError,
    InvalidTransitionError,
    MalformedMandateError,
    MandateError,
    MandateExpiredError,
    MandateNotYetValidError,
    MandateRevokedError,
    MandateSignatureError,
    NotFoundError,
)
from seatbelt.mandate import Mandate
from seatbelt.service.core import GuardService
from seatbelt.service.schemas import (
    ApproveBody,
    AuditEntry,
    IssueMandateBody,
    MandateIssued,
    PaymentBody,
    RejectBody,
    RevokeResult,
)
from seatbelt.store import ChainStatus, PaymentRecord, PaymentStatus, StoredMandate

log = logging.getLogger(__name__)

# Most specific first is not required (Starlette walks the MRO), but this reads clearly.
_STATUS_BY_ERROR: list[tuple[type[Exception], int]] = [
    (MandateRevokedError, 403),
    (MalformedMandateError, 401),
    (MandateSignatureError, 401),
    (MandateExpiredError, 401),
    (MandateNotYetValidError, 401),
    (MandateError, 422),
    (NotFoundError, 404),
    (IdempotencyConflictError, 409),
    (InvalidTransitionError, 409),
]


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status_code=401, detail=detail, headers={"WWW-Authenticate": "Bearer"})


def create_app(service: GuardService, admin_api_key: SecretStr) -> FastAPI:
    app = FastAPI(
        title="Seatbelt",
        version=__version__,
        description="A safety layer between AI agents and PayPal payments.",
    )
    app.state.service = service

    bearer = HTTPBearer(auto_error=False)
    admin_key = admin_api_key.get_secret_value().encode("utf-8")
    Creds = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]

    def is_admin(creds: HTTPAuthorizationCredentials | None) -> bool:
        return creds is not None and hmac.compare_digest(
            creds.credentials.encode("utf-8"), admin_key
        )

    def require_admin(creds: Creds) -> None:
        if not is_admin(creds):
            raise _unauthorized("admin credentials required")

    def admin_or_agent(creds: Creds) -> Mandate | None:
        """None means admin; otherwise the authenticated agent's mandate."""
        if creds is None:
            raise _unauthorized("credentials required")
        if is_admin(creds):
            return None
        return service.authenticate_agent(creds.credentials)

    Admin = Depends(require_admin)

    # ------------------------------------------------------------ error handling
    def _register(exc_type: type[Exception], status: int) -> None:
        @app.exception_handler(exc_type)
        async def _handler(_: Request, exc: Exception) -> JSONResponse:
            return JSONResponse(status_code=status, content={"detail": str(exc)})

    for exc_type, status in _STATUS_BY_ERROR:
        _register(exc_type, status)

    @app.exception_handler(AuditIntegrityError)
    async def _audit_integrity_error(
        _: Request, exc: AuditIntegrityError
    ) -> JSONResponse:
        log.error("payment operations blocked by audit integrity failure: %s", exc)
        return JSONResponse(
            status_code=503,
            content={
                "detail": "Payment operations are temporarily disabled due to an integrity check failure."
            },
        )

    @app.exception_handler(ValidationError)
    async def _validation(_: Request, exc: ValidationError) -> JSONResponse:
        errors = [{"loc": [str(p) for p in e["loc"]], "msg": e["msg"]} for e in exc.errors()]
        return JSONResponse(
            status_code=422, content={"detail": "invalid request", "errors": errors}
        )

    @app.exception_handler(Exception)
    async def _unexpected(_: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error", exc_info=exc)
        return JSONResponse(status_code=500, content={"detail": "internal server error"})

    # ------------------------------------------------------------ public
    @app.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    # ------------------------------------------------------------ admin: mandates
    @app.post("/v1/mandates", response_model=MandateIssued, tags=["admin"], dependencies=[Admin])
    def issue_mandate(body: IssueMandateBody) -> MandateIssued:
        mandate, token = service.issue_mandate(
            agent_id=body.agent_id,
            currency=body.currency,
            per_payment_limit=body.per_payment_limit,
            total_limit=body.total_limit,
            approval_threshold=body.approval_threshold,
            allowed_payees=body.allowed_payees,
            ttl=timedelta(minutes=body.ttl_minutes),
        )
        return MandateIssued(mandate=mandate, token=token)

    @app.get(
        "/v1/mandates/{mandate_id}",
        response_model=StoredMandate,
        tags=["admin"],
        dependencies=[Admin],
    )
    def get_mandate(mandate_id: str) -> StoredMandate:
        return service.get_mandate(mandate_id)

    @app.post(
        "/v1/mandates/{mandate_id}/revoke",
        response_model=RevokeResult,
        tags=["admin"],
        dependencies=[Admin],
    )
    def revoke_mandate(mandate_id: str) -> RevokeResult:
        return RevokeResult(payments_cancelled=service.revoke_mandate(mandate_id, "admin"))

    # ------------------------------------------------------------ agent: payments
    @app.post("/v1/payments", response_model=PaymentRecord, tags=["agent"])
    def submit_payment(body: PaymentBody, creds: Creds) -> PaymentRecord:
        if creds is None:
            raise _unauthorized("mandate token required")
        return service.submit_payment(
            creds.credentials,
            request_id=body.request_id,
            payee=body.payee,
            amount=body.amount,
            currency=body.currency,
            description=body.description,
        )

    @app.post("/v1/paypal/payments", response_model=PaymentRecord, tags=["agent"])
    def submit_paypal_payment(body: PaymentBody, creds: Creds) -> PaymentRecord:
        if creds is None:
            raise _unauthorized("mandate token required")

        return service.submit_paypal_payment(
            creds.credentials,
            request_id=body.request_id,
            payee=body.payee,
            amount=body.amount,
            currency=body.currency,
            description=body.description,
        )

    @app.get("/v1/paypal/return", response_model=PaymentRecord, tags=["paypal"])
    def paypal_return(
        token: Annotated[str, Query(min_length=1, max_length=128)]
    ) -> PaymentRecord:
        # PayPal's token is an untrusted order ID until checked against our DB
        # and verified with PayPal's Orders API.
        return service.process_paypal_return(token)

    @app.get("/v1/paypal/cancel", response_model=PaymentRecord, tags=["paypal"])
    def paypal_cancel(
        token: Annotated[str, Query(min_length=1, max_length=128)]
    ) -> PaymentRecord:
          # The order ID is untrusted until resolved from our DB and verified with PayPal.
          try:
             return service.process_paypal_cancel(token)
          except ValueError as exc:
             raise HTTPException(status_code=409, detail=str(exc)) from exc
    @app.get("/v1/payments/{payment_id}", response_model=PaymentRecord, tags=["agent", "admin"])
    def get_payment(
        payment_id: str, who: Annotated[Mandate | None, Depends(admin_or_agent)]
    ) -> PaymentRecord:
        payment = service.get_payment(payment_id)
        if who is not None and payment.mandate_id != who.mandate_id:
            raise NotFoundError(f"payment {payment_id} not found")  # don't reveal it exists
        return payment

    # ------------------------------------------------------------ admin: payments
    @app.get(
        "/v1/payments",
        response_model=list[PaymentRecord],
        tags=["admin"],
        dependencies=[Admin],
    )
    def list_payments(
        mandate_id: str | None = None,
        status: PaymentStatus | None = None,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> list[PaymentRecord]:
        return service.list_payments(
            mandate_id=mandate_id, status=status, limit=limit, offset=offset
        )

    @app.post(
        "/v1/payments/{payment_id}/approve",
        response_model=PaymentRecord,
        tags=["admin"],
        dependencies=[Admin],
    )
    def approve_payment(payment_id: str, body: ApproveBody) -> PaymentRecord:
        return service.approve_payment(payment_id, body.approver)

    @app.post(
        "/v1/payments/{payment_id}/reject",
        response_model=PaymentRecord,
        tags=["admin"],
        dependencies=[Admin],
    )
    def reject_payment(payment_id: str, body: RejectBody) -> PaymentRecord:
        return service.reject_payment(payment_id, body.approver, body.reason)

    @app.post(
        "/v1/payments/{payment_id}/retry",
        response_model=PaymentRecord,
        tags=["admin"],
        dependencies=[Admin],
    )
    def retry_payment(payment_id: str) -> PaymentRecord:
        return service.retry_payment(payment_id)

    # ------------------------------------------------------------ admin: audit
    @app.get("/v1/audit", response_model=list[AuditEntry], tags=["admin"], dependencies=[Admin])
    def list_audit(
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> list[AuditEntry]:
        return [AuditEntry(**e) for e in service.list_audit(limit=limit, offset=offset)]

    @app.get("/v1/audit/verify", response_model=ChainStatus, tags=["admin"], dependencies=[Admin])
    def verify_audit() -> ChainStatus:
        return service.verify_audit()

    @app.post(
        "/v1/audit/checkpoint",
        response_model=ChainStatus,
        tags=["admin"],
        dependencies=[Admin],
    )
    def create_audit_checkpoint() -> ChainStatus:
        try:
            return service.create_audit_checkpoint()
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    return app