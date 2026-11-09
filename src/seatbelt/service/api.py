"""The guard's HTTP API.

Two kinds of caller, two kinds of credential (both sent as `Authorization: Bearer ...`):

  agent : the signed MANDATE TOKEN. Can submit payments and read its own payments only.
  admin : the ADMIN API KEY. Can issue/revoke mandates, approve/reject/retry payments,
          and read everything including the audit log.

Errors never leak internals: expected failures map to precise status codes; anything
unexpected becomes a generic 500 (details go to the server log only).
"""

import hmac
import json
import logging
from datetime import timedelta
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import SecretStr, ValidationError

from seatbelt import __version__
from seatbelt.errors import (
    PayPalError,
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

_SAFE_ERROR_DETAILS: dict[type[Exception], str] = {
    MandateRevokedError: "This mandate has been revoked.",
    MalformedMandateError: "The mandate token is malformed.",
    MandateSignatureError: "The mandate signature is invalid.",
    MandateExpiredError: "The mandate has expired.",
    MandateNotYetValidError: "The mandate is not yet valid.",
    MandateError: "The mandate is invalid or cannot be used.",
    NotFoundError: "The requested resource was not found.",
    IdempotencyConflictError: "The request ID was already used with different details.",
    InvalidTransitionError: "This action is not allowed in the current payment state.",
}


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status_code=401, detail=detail, headers={"WWW-Authenticate": "Bearer"})


def create_app(service: GuardService, admin_api_key: SecretStr) -> FastAPI:
    app = FastAPI(
        title="Seatbelt",
        version=__version__,
        description="A safety layer between AI agents and PayPal payments.",
    )
    app.state.service = service

    from seatbelt.service.request_limits import RequestBodyLimitMiddleware

    app.add_middleware(
        RequestBodyLimitMiddleware,
        max_body_bytes=1024 * 1024,
        paypal_webhook_max_body_bytes=256 * 1024,
    )

    from seatbelt.service.rate_limit import InMemoryRateLimiter

    app.state.rate_limiter = InMemoryRateLimiter()
    rate_limits = {
        ("POST", "/v1/mandates"): 10,
        ("POST", "/v1/payments"): 30,
        ("POST", "/v1/paypal/payments"): 30,
        ("POST", "/v1/paypal/webhook"): 60,
    }

    @app.middleware("http")
    async def enforce_rate_limits(request, call_next):
        from fastapi.responses import JSONResponse

        limit = rate_limits.get((request.method, request.url.path))
        if limit is not None:
            client_ip = request.client.host if request.client else "unknown"
            allowed, retry_after = app.state.rate_limiter.allow(
                f"{request.method}:{request.url.path}:{client_ip}",
                limit=limit,
                window_seconds=60,
            )
            if not allowed:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Too many requests. Please try again later."},
                    headers={"Retry-After": str(retry_after)},
                )

        return await call_next(request)

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
            log.warning("request rejected error_type=%s", type(exc).__name__)
            detail = _SAFE_ERROR_DETAILS[exc_type]
            return JSONResponse(status_code=status, content={"detail": detail})

    for exc_type, status in _STATUS_BY_ERROR:
        _register(exc_type, status)

    @app.exception_handler(AuditIntegrityError)
    async def _audit_integrity_error(
        _: Request, exc: AuditIntegrityError
    ) -> JSONResponse:
        log.error("payment operations blocked by audit integrity failure error_type=%s", type(exc).__name__)
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
        log.error("unhandled error type=%s", type(exc).__name__)
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

    @app.post("/v1/paypal/webhook", tags=["paypal"])
    async def paypal_webhook(request: Request) -> JSONResponse:
        """Receive PayPal events authenticated by PayPal postback verification."""
        max_body_bytes = 256 * 1024
        content_length = request.headers.get("content-length")

        if content_length is not None:
            try:
                if int(content_length) > max_body_bytes:
                    raise HTTPException(status_code=413, detail="Webhook body too large")
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid content length")

        content_type = request.headers.get("content-type", "")
        if content_type.split(";", 1)[0].strip().lower() != "application/json":
            raise HTTPException(status_code=415, detail="Expected application/json")

        raw_body = await request.body()
        if len(raw_body) > max_body_bytes:
            raise HTTPException(status_code=413, detail="Webhook body too large")

        try:
            event = json.loads(raw_body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise HTTPException(status_code=400, detail="Invalid webhook JSON")

        if not isinstance(event, dict):
            raise HTTPException(status_code=400, detail="Webhook JSON must be an object")

        paypal_headers = {
            "PAYPAL-AUTH-ALGO": request.headers.get("paypal-auth-algo", ""),
            "PAYPAL-CERT-URL": request.headers.get("paypal-cert-url", ""),
            "PAYPAL-TRANSMISSION-ID": request.headers.get("paypal-transmission-id", ""),
            "PAYPAL-TRANSMISSION-SIG": request.headers.get("paypal-transmission-sig", ""),
            "PAYPAL-TRANSMISSION-TIME": request.headers.get("paypal-transmission-time", ""),
        }

        try:
            result = service.handle_paypal_webhook(paypal_headers, event, raw_body)
            return JSONResponse(status_code=200, content=result)
        except PermissionError:
            raise HTTPException(
                status_code=401,
                detail="PayPal webhook signature verification failed",
            )
        except NotFoundError:
            raise HTTPException(status_code=404, detail="PayPal order not found")
        except InvalidTransitionError:
            raise HTTPException(
                status_code=409,
                detail="PayPal webhook conflicts with payment state",
            )
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid PayPal webhook event")
        except (PayPalError, RuntimeError) as exc:
            log.error("PayPal webhook processing unavailable error_type=%s", type(exc).__name__)
            raise HTTPException(
                status_code=503,
                detail="PayPal webhook processing is temporarily unavailable",
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
            # Preserve the known, user-actionable state conflict. Do not expose
            # arbitrary verification/provider exception text.
            if str(exc) == "PayPal order is not in a cancellable state":
                detail = "PayPal order is not in a cancellable state"
            else:
                detail = "PayPal cancellation could not be completed"
            log.warning(
                "PayPal cancellation rejected error_type=%s",
                type(exc).__name__,
            )
            raise HTTPException(status_code=409, detail=detail) from exc

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
            log.error("audit checkpoint unavailable error_type=%s", type(exc).__name__)
            raise HTTPException(
                status_code=503,
                detail="Audit checkpoint is temporarily unavailable",
            ) from exc
        except ValueError as exc:
            log.warning("audit checkpoint rejected error_type=%s", type(exc).__name__)
            raise HTTPException(
                status_code=409,
                detail="Audit checkpoint could not be created",
            ) from exc

    return app