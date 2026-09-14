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
