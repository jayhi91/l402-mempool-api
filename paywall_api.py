import os
import httpx
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse

app = FastAPI(title="L402 Live Mempool API")

ALBY_ACCESS_TOKEN = os.getenv("ALBY_ACCESS_TOKEN")

async def create_alby_invoice(amount_sats: int = 10):
    """Generates a mainnet invoice from Alby API."""
    if not ALBY_ACCESS_TOKEN:
        print("[ERROR] ALBY_ACCESS_TOKEN environment variable is missing on Render!")
        return None

    url = "https://api.getalby.com/invoices"
    headers = {
        "Authorization": f"Bearer {ALBY_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "amount": amount_sats,
        "description": "L402 Telemetry Payment"
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            print(f"[ALBY API] Status: {resp.status_code}, Response: {resp.text}")
            if resp.status_code in (200, 201):
                data = resp.json()
                return data.get("payment_request")
            return None
    except Exception as e:
        print(f"[ALBY API EXCEPTION] {str(e)}")
        return None

async def get_live_mempool_data():
    """Fetches real-time fee and mempool statistics from mempool.space."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        fees_resp = await client.get("https://mempool.space/api/v1/fees/recommended")
        stats_resp = await client.get("https://mempool.space/api/mempool")

        fees = fees_resp.json() if fees_resp.status_code == 200 else {}
        stats = stats_resp.json() if stats_resp.status_code == 200 else {}

    fastest = fees.get("fastestFee", 0)
    congestion = "EXTREME" if fastest > 50 else "HIGH" if fastest > 20 else "MODERATE" if fastest > 10 else "LOW"

    return {
        "status": "success",
        "congestion_level": congestion,
        "recommended_fees_sat_vbyte": {
            "fastest_block": fees.get("fastestFee"),
            "half_hour": fees.get("halfHourFee"),
            "one_hour": fees.get("hourFee"),
            "minimum": fees.get("minimumFee")
        },
        "mempool_stats": {
            "pending_transactions": stats.get("count"),
            "vsize_bytes": stats.get("vsize"),
            "total_fee_sats": stats.get("total_fee")
        }
    }

@app.get("/api/v1/mempool-signal")
async def get_mempool_signal(authorization: str = Header(None)):
    # 1. Unauthenticated: Return 402 with real Alby invoice
    if not authorization or not authorization.startswith("L402 "):
        invoice = await create_alby_invoice(10)
        if not invoice:
            return JSONResponse(
                status_code=500,
                content={"error": "Failed to generate Lightning invoice from Alby Hub."}
            )
        return JSONResponse(
            status_code=402,
            headers={"WWW-Authenticate": f'L402 invoice="{invoice}"'},
            content={
                "error": "Payment Required",
                "cost_sats": 10,
                "invoice": invoice
            }
        )

    # 2. Authenticated: Fetch live mempool.space data
    try:
        return await get_live_mempool_data()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch live data: {str(e)}")
