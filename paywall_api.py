import os
import uuid
import logging
import requests
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# 1. Load Environment Configuration
load_dotenv()

MOCK_MODE = os.getenv("MOCK_MODE", "true").lower() == "true"
ALBY_ACCESS_TOKEN = os.getenv("ALBY_ACCESS_TOKEN", "")
MEMPOOL_URL = os.getenv(
    "MEMPOOL_URL", "https://mempool.space/api/v1/fees/recommended"
)

# 2. Configure Structured Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("L402_Service")

# 3. Setup Rate Limiter (Prevents Challenge Spam)
limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="L402 Mempool Signal API")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

MOCK_PAYMENTS = {}
USED_PREIMAGES = set()


def create_invoice(amount_sats: int = 10):
    if MOCK_MODE:
        raw_id = uuid.uuid4().hex[:12]
        payment_hash = f"hash_{raw_id}"
        mock_preimage = f"preimage_{raw_id}"
        invoice_str = f"lnbc100n1mock_invoice_{payment_hash}"
        MOCK_PAYMENTS[payment_hash] = mock_preimage
        logger.info(f"Generated mock invoice: {payment_hash}")
        return payment_hash, invoice_str

    # Production Alby API Integration
    url = "https://api.getalby.com/invoices"
    headers = {
        "Authorization": f"Bearer {ALBY_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {"amount": amount_sats, "memo": "Mempool Signal API Access (L402)"}
    res = requests.post(url, json=payload, headers=headers)
    data = res.json()
    return data.get("payment_hash"), data.get("payment_request")


def check_payment(payment_hash: str, preimage: str = None) -> bool:
    if MOCK_MODE:
        expected = MOCK_PAYMENTS.get(payment_hash)
        return expected is not None and expected == preimage

    url = f"https://api.getalby.com/invoices/{payment_hash}"
    headers = {"Authorization": f"Bearer {ALBY_ACCESS_TOKEN}"}
    res = requests.get(url, headers=headers)
    return res.status_code == 200 and res.json().get("settled", False)


def fetch_live_mempool_signal():
    res = requests.get(MEMPOOL_URL)
    fees = res.json()
    fastest = fees.get("fastestFee", 0)

    signal = (
        "BUY_AND_TRANSACT_CHEAP"
        if fastest <= 10
        else "NEUTRAL" if fastest <= 30 else "HIGH_CONGESTION_WAIT"
    )
    return {
        "signal": signal,
        "fastestFee": fastest,
        "halfHourFee": fees.get("halfHourFee"),
        "minimumFee": fees.get("minimumFee"),
    }


@app.get("/api/v1/mempool-signal")
@limiter.limit("10/minute") # Limits requests to 10 per minute per IP
def get_mempool_signal(request: Request, authorization: str = Header(None)):
    if authorization and authorization.startswith("L402 "):
        try:
            token = authorization.split(" ")[1]
            payment_hash, preimage = token.split(":")

            if preimage in USED_PREIMAGES:
                logger.warning(
                    f"Replay attempt blocked for preimage: {preimage[:10]}..."
                )
                raise HTTPException(
                    status_code=401, detail="Payment preimage already spent."
                )

            if check_payment(payment_hash, preimage):
                USED_PREIMAGES.add(preimage)
                logger.info(
                    f"Successful L402 authentication for hash: {payment_hash}"
                )
                return {
                    "status": "success",
                    "authenticated_via": "L402 Protocol",
                    "mempool_signal": fetch_live_mempool_signal(),
                }
            else:
                logger.warning(
                    f"Invalid payment verification attempt: {payment_hash}"
                )
                raise HTTPException(
                    status_code=401, detail="Invalid payment credentials."
                )

        except ValueError:
            raise HTTPException(
                status_code=400, detail="Invalid L402 header format."
            )

    payment_hash, invoice = create_invoice(amount_sats=10)
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