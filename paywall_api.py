import hashlib
import os
import httpx
from fastapi import FastAPI, Header, HTTPException, Response, status

app = FastAPI()

ALBY_ACCESS_TOKEN = os.getenv("ALBY_ACCESS_TOKEN", "")
ALBY_API_URL = "https://api.getalby.com"


def verify_l402_proof(authorization: str | None) -> tuple[bool, str]:
    """
    Validates the L402 Authorization header.
    Returns (is_valid, payment_hash_or_reason).
    """
    if not authorization:
        return False, "Missing Authorization header"

    # Support both L402 and LSAT prefix standards
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

    # Step 1: Local SHA-256 cryptographic check
    try:
        preimage_bytes = bytes.fromhex(preimage_hex)
        computed_hash = hashlib.sha256(preimage_bytes).hexdigest()
        if computed_hash.lower() != payment_hash_hex.lower():
            return False, "SHA-256 hash of preimage does not match payment_hash"
    except Exception:
        return False, "Invalid hex encoding in preimage or hash"

    # Step 2: Query Alby API to confirm invoice settlement status
    try:
        headers = {"Authorization": f"Bearer {ALBY_ACCESS_TOKEN}"}
        url = f"{ALBY_API_URL}/invoices/{payment_hash_hex}"

        with httpx.Client(timeout=10.0) as client:
            resp = client.get(url, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                is_settled = data.get("settled") is True or data.get("state") == "SETTLED"
                if is_settled:
                    return True, payment_hash_hex
                return False, "Invoice is generated but not yet settled"
            else:
                return False, f"Alby invoice check failed (HTTP {resp.status_code})"
    except Exception as e:
        return False, f"Error reaching Alby server: {str(e)}"


@app.get("/api/v1/mempool-signal")
def get_mempool_signal(response: Response, authorization: str | None = Header(None)):
    is_valid, result = verify_l402_proof(authorization)

    if not is_valid:
        # Generate a fresh invoice via Alby if payment is missing or invalid
        invoice, payment_hash = create_alby_invoice(amount_sats=10)

        # Set WWW-Authenticate header per L402 spec
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
