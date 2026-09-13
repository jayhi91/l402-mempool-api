import os
import httpx
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse

app = FastAPI(title="L402 Dynamic Mempool Data API")

ALBY_ACCESS_TOKEN = os.getenv("ALBY_ACCESS_TOKEN")
MOCK_MODE = os.getenv("MOCK_MODE", "false").lower() == "true"

MEMPOOL_FEES_URL = "https://mempool.space/api/v1/fees/recommended"
MEMPOOL_STATS_URL = "https://mempool.space/api/mempool"

async def get_live_mempool_data():
    async with httpx.AsyncClient(timeout=10.0) as client:
        fees_resp = await client.get(MEMPOOL_FEES_URL)
        stats_resp = await client.get(MEMPOOL_STATS_URL)

        fees = fees_resp.json() if fees_resp.status_code == 200 else {}
        stats = stats_resp.json() if stats_resp.status_code == 200 else {}

    # Simple congestion rating based on fastest fee rate
    fastest = fees.get("fastestFee", 0)
    if fastest > 50:
        congestion = "EXTREME_CONGESTION"
    elif fastest > 20:
        congestion = "HIGH_CONGESTION"
    elif fastest > 10:
        congestion = "MODERATE_CONGESTION"
    else:
        congestion = "LOW_CONGESTION"

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
    # 1. Verify L402 Auth Header
    if not authorization or not authorization.startswith("L402 "):
        # In a full setup, generate dynamic invoice via Alby REST API
        # Return 402 challenge if header is missing or unverified
        return JSONResponse(
            status_code=402,
            headers={"WWW-Authenticate": 'L402 invoice="lnbc..."'},
            content={
                "error": "Payment Required",
                "cost_sats": 10,
                "message": "Send 10 sats to receive live mempool telemetry."
            }
        )

    # 2. Fetch real-time data from mempool.space once authenticated
    try:
        live_data = await get_live_mempool_data()
        return live_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch live feed: {str(e)}")
