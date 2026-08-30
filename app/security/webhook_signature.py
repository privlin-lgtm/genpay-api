import hashlib
import hmac
import time

from fastapi import Header, HTTPException, Request

SIGNATURE_HEADER = "X-GenPay-Signature"
SIGNATURE_TOLERANCE_SECONDS = 300


def sign_payload(secret: str, raw_body: bytes, timestamp: int | None = None) -> str:
    """
    Build an `X-GenPay-Signature` header value the way the simulated processor
    would: `t=<unix_ts>,v1=<hex hmac-sha256 of "t.body">`. Stripe-style scheme —
    the timestamp is signed too, so a captured signature can't be replayed against
    a different payload, and it lets the verifier reject stale deliveries.
    """
    ts = timestamp if timestamp is not None else int(time.time())
    signed_payload = f"{ts}.{raw_body.decode('utf-8')}"
    digest = hmac.new(secret.encode("utf-8"), signed_payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"t={ts},v1={digest}"


def verify_webhook_signature(secret: str):
    """
    Returns a FastAPI dependency that validates the X-GenPay-Signature header
    against the raw request body and returns that raw body (so the route can
    parse it itself — by the time FastAPI would auto-parse a Pydantic body param,
    the raw bytes needed for signature verification are already gone).
    """

    async def _verify(
        request: Request,
        x_genpay_signature: str | None = Header(default=None, alias=SIGNATURE_HEADER),
    ) -> bytes:
        raw_body = await request.body()

        if not x_genpay_signature:
            raise HTTPException(
                status_code=401,
                detail={
                    "error": {
                        "code": "missing_signature",
                        "message": f"{SIGNATURE_HEADER} header is required",
                    }
                },
            )

        try:
            parts = dict(part.split("=", 1) for part in x_genpay_signature.split(","))
            timestamp = int(parts["t"])
            provided_signature = parts["v1"]
        except (KeyError, ValueError) as exc:
            raise HTTPException(
                status_code=401,
                detail={
                    "error": {
                        "code": "malformed_signature",
                        "message": f"Could not parse {SIGNATURE_HEADER} header",
                    }
                },
            ) from exc

        if abs(time.time() - timestamp) > SIGNATURE_TOLERANCE_SECONDS:
            raise HTTPException(
                status_code=401,
                detail={
                    "error": {
                        "code": "signature_expired",
                        "message": "Webhook timestamp is outside the tolerance window",
                    }
                },
            )

        expected_signature = sign_payload(secret, raw_body, timestamp).split("v1=")[1]
        if not hmac.compare_digest(expected_signature, provided_signature):
            raise HTTPException(
                status_code=401,
                detail={"error": {"code": "invalid_signature", "message": "Signature verification failed"}},
            )

        return raw_body

    return _verify
