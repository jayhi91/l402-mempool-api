import hashlib
import os
import httpx
from fastapi import FastAPI, Header, HTTPException, Response, status

app = FastAPI()

ALBY_ACCESS_TOKEN = os.getenv("ALBY_ACCESS_TOKEN", "")
ALBY_API_URL = "https://api.getalby.com"


def create_alby_invoice(amount_sats: int = 10, memo: str = "L402 Mempool Signal"):
    """Generates a BOLT11 invoice via Alby REST API."""
    headers = {
        "Authorization": f"Bearer {ALBY_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "amount": amount_sats,
        "description": memo,
    }

    with httpx.Client(timeout=15.0) as client:
        resp = client.post(f"{ALBY_API_URL}/invoices", json=payload, headers=headers)
        if resp.status_code in (200, 201):
            data = resp.json()
            invoice = data.get("payment_request")
            payment_hash = data.get("payment_hash")
            return invoice, payment_hash
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to create Alby invoice: {resp.text}",
            )


def verify_l402_proof(authorization: str | None) -> tuple[bool, str]:
    """Validates the L402 Authorization header using SHA-256 cryptographic proof."""
    if not authorization:
        return False, "Missing Authorization header"

    auth_str = authorization.strip()
    if auth_str.startswith("L402 "):
        token_data = auth_str[5:].strip()
    elif auth_str.startswith("LSAT "):
        token_data = auth_str[5:].strip()
    else:
        return False, "Header format must be 'L402 <preimage>:<payment_hash>'"

    try:
        preimage_hex, payment_hash_hex = token_data.split(":", 1)
    except ValueError:
        return False, "Malformed L402 token format"

    # L402 Cryptographic Check: SHA-256(preimage) == payment_hash
    try:
        preimage_bytes = bytes.fromhex(preimage_hex)
        computed_hash = hashlib.sha256(preimage_bytes).hexdigest()
        if computed_hash.lower() == payment_hash_hex.lower():
            return True, payment_hash_hex
        return False, "SHA-256 hash of preimage does not match payment_hash"
    except Exception:
        return False, "Invalid hex encoding in preimage or hash"


@app.get("/api/v1/mempool-signal")
def get_mempool_signal(response: Response, authorization: str | None = Header(None)):
    is_valid, result = verify_l402_proof(authorization)

    if not is_valid:
        invoice, payment_hash = create_alby_invoice(amount_sats=10)

        response.headers["WWW-Authenticate"] = (
            f'L402 invoice="{invoice}", payment_hash="{payment_hash}"'
        )

        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "detail": "Payment Required",
                "invoice": invoice,
                "payment_hash": payment_hash,
                "price_sats": 10,
                "reason": result,
            },
        )

    # Return gated payload on valid L402 proof
    return {
        "status": "success",
        "congestion_level": "LOW",
        "recommended_fees_sat_vb": {
            "fastestFee": 1,
            "halfHourFee": 1,
            "hourFee": 1,
            "economyFee": 1,
            "minimumFee": 1,
        },
        "mempool_txs": 80669,
        "vsize_bytes": 41920560,
        "total_fee_sats": 9366957,
    }

