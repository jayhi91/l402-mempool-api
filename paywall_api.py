import os
import logging
import requests
from typing import Optional
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse

# Setup logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("paywall_api")

app = FastAPI(title="L402 Mempool API")

# Environment configurations
MOCK_MODE = os.getenv("MOCK_MODE", "true").lower() == "true"
ALBY_ACCESS_TOKEN = os.getenv("ALBY_ACCESS_TOKEN", "")

# In-memory storage for used preimages
USED_PREIMAGES = set()


def create_invoice(amount_sats: int = 10):
    if MOCK_MODE:
        import uuid
        mock_id = str(uuid.uuid4())[:8]
        return f"hash_{mock_id}", f"lnbc_mock_invoice_{mock_id}"

    if not ALBY_ACCESS_TOKEN:
        logger.error("ALBY API ERROR: ALBY_ACCESS_TOKEN is missing or empty in Render environment variables.")
        return None, None

    url = "https://api.getalby.com/invoices"
    headers = {
        "Authorization": f"Bearer {ALBY_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "amount": amount_sats,
        "description": "L402 Mempool Signal Access"
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)

        if response.status_code not in (200, 201):
            logger.error(f"ALBY API ERROR [{response.status_code}]: {response.text}")
            return None, None

        data = response.json()
        payment_hash = data.get("payment_hash")
        payment_request = data.get("payment_request") # BOLT11 invoice string
        return payment_hash, payment_request

    except Exception as e:
        logger.error(f"ALBY REQUEST EXCEPTION: {str(e)}")
        return None, None


def fetch_live_mempool_signal():
    return {
        "status": "active",
        "signal": "BULLISH_MEMPOOL_CONGESTION",
        "recommended_fee_sat_vbyte": 18
    }


@app.get("/api/v1/mempool-signal")
async def get_mempool_signal(authorization: Optional[str] = Header(None)):
    # 1. Validate L402 authorization header if provided
    if authorization:
        try:
            token_type, credentials = authorization.split(" ", 1)
            if token_type.upper() == "L402":
                payment_hash, preimage = credentials.split(":", 1)

                if preimage and preimage not in USED_PREIMAGES:
                    USED_PREIMAGES.add(preimage)
                    logger.info(f"Successful L402 authentication for hash: {payment_hash}")
                    return {"mempool_signal": fetch_live_mempool_signal()}
                else:
                    logger.warning(f"Invalid payment verification attempt: {payment_hash}")
                    raise HTTPException(
                        status_code=401, detail="Invalid payment credentials."
                    )
        except ValueError:
            raise HTTPException(
                status_code=400, detail="Invalid L402 header format."
            )

    # 2. Generate invoice for unauthenticated requests
    payment_hash, invoice = create_invoice(amount_sats=10)

    if not invoice or not payment_hash:
        logger.error("Invoice creation failed in create_invoice(). Returning 500 error.")
        raise HTTPException(
            status_code=500,
            detail="Failed to generate Lightning invoice from Alby. Check Render logs for ALBY API ERROR details."
        )

    return JSONResponse(
        status_code=402,
        headers={"WWW-Authenticate": f'L402 invoice="{invoice}"'},
        content={
            "error": "Payment Required",
            "cost_sats": 10,
            "invoice": invoice,
            "payment_hash": payment_hash,
        },
    )
