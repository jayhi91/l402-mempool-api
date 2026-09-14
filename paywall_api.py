import os
import hashlib
import httpx
from fastapi import FastAPI, Header, HTTPException, status
from fastapi.responses import JSONResponse

app = FastAPI(title="L402 Mempool Telemetry API")

ALBY_ACCESS_TOKEN = os.getenv("ALBY_ACCESS_TOKEN", "")
ALBY_API_URL = "https://api.getalby.com"
MEMPOOL_FEES_URL = "https://mempool.space/api/v1/fees/recommended"
MEMPOOL_STATS_URL = "https://mempool.space/api/mempool"


def verify_alby_settlement(preimage: str, payment_hash: str) -> bool:
    """Cryptographically validates preimage hash locally and verifies payment with Alby API."""
    try:
        # 1. Cryptographic validation: SHA256(preimage) must match payment_hash
        calc_hash = hashlib.sha256(bytes.fromhex(preimage)).hexdigest()
        if calc_hash.lower() != payment_hash.lower():
            return False

        # 2. Query Alby API to confirm invoice status is settled
        headers = {"Authorization": f"Bearer {ALBY_ACCESS_TOKEN}"}
        resp = httpx.get(f"{ALBY_API_URL}/invoices/{payment_hash}", headers=headers, timeout=5.0)
        
        if resp.status_code == 200:
            invoice_data = resp.json()
            return invoice_data.get("settled") is True or invoice_data.get("state") == "SETTLED"
        return False
    except Exception as err:
        print(f"Settlement verification error: {err}")
        return False


def create_alby_invoice(amount_sats: int = 10, memo: str = "L402 Mempool Signal"):
    """Generates a real BOLT11 invoice via Alby API."""
    headers = {
        "Authorization": f"Bearer {ALBY_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {"amount": amount_sats, "memo": memo}
    resp = httpx.post(f"{ALBY_API_URL}/invoices", json=payload, headers=headers, timeout=5.0)
    
    if resp.status_code == 200:
        data = resp.json()
        return data.get("payment_request"), data.get("payment_hash")
    
    raise HTTPException(status_code=500, detail="Failed to generate Lightning invoice from Alby backend.")


@app.get("/api/v1/mempool-signal")
def get_mempool_signal(authorization: str = Header(None)):
    # Step 1: Validate incoming L402 Authorization header
    if authorization and authorization.startswith("L402 "):
        try:
            token = authorization.split("L402 ")[1].strip()
            preimage, payment_hash = token.split(":")
            
            # Enforce strict Alby settlement check (No mock authorization accepted)
            if verify_alby_settlement(preimage, payment_hash):
                with httpx.Client(timeout=10.0) as client:
                    fees = client.get(MEMPOOL_FEES_URL).json()
                    stats = client.get(MEMPOOL_STATS_URL).json()
                
                return {
                    "status": "success",
                    "congestion_level": "LOW" if fees.get("fastestFee", 0) <= 5 else "HIGH",
                    "recommended_fees_sat_vb": fees,
                    "mempool_stats": {
                        "unconfirmed_txs": stats.get("count"),
                        "vsize_bytes": stats.get("vsize"),
                        "total_fee_sats": stats.get("total_fee")
                    }
                }
        except Exception:
            pass # Invalid token format triggers 402 challenge below

    # Step 2: Issue 402 Payment Required challenge with a fresh Alby invoice
    invoice, payment_hash = create_alby_invoice(amount_sats=10)
    
    headers = {
        "WWW-Authenticate": f'L402 invoice="{invoice}", payment_hash="{payment_hash}"'
    }
    return JSONResponse(
        status_code=status.HTTP_402_PAYMENT_REQUIRED,
        headers=headers,
        content={
            "detail": "Payment Required",
            "invoice": invoice,
            "payment_hash": payment_hash,
            "price_sats": 10
        }
    )
def create_alby_invoice(amount_sats: int = 10, memo: str = "L402 Mempool Signal"):
    """Generates a real BOLT11 invoice via Alby API."""
    if not ALBY_ACCESS_TOKEN:
        raise HTTPException(
            status_code=500,
            detail="ALBY_ACCESS_TOKEN environment variable is missing on Render."
        )

    headers = {
        "Authorization": f"Bearer {ALBY_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {"amount": amount_sats, "memo": memo}
    
    try:
        resp = httpx.post(f"{ALBY_API_URL}/invoices", json=payload, headers=headers, timeout=5.0)
        if resp.status_code in (200, 201):
            data = resp.json()
            return data.get("payment_request"), data.get("payment_hash")
        
        raise HTTPException(
            status_code=500, 
            detail=f"Alby API Error ({resp.status_code}): {resp.text}"
        )
    except Exception as err:
        raise HTTPException(status_code=500, detail=f"Alby Request Exception: {str(err)}")
