import os
import re
import httpx

API_URL = "https://l402-mempool-api.onrender.com/api/v1/mempool-signal"
ALBY_API_URL = "https://api.getalby.com"
ALBY_ACCESS_TOKEN = os.getenv("ALBY_ACCESS_TOKEN", "")


def parse_l402_header(www_authenticate_header: str):
    if not www_authenticate_header:
        return None, None
    invoice_match = re.search(r'invoice="([^"]+)"', www_authenticate_header)
    hash_match = re.search(r'payment_hash="([^"]+)"', www_authenticate_header)
    return (
        invoice_match.group(1) if invoice_match else None,
        hash_match.group(1) if hash_match else None,
    )


def pay_invoice_via_alby(invoice: str, token: str):
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {"invoice": invoice}

    print("Sending automated payment request to Alby...")
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(
            f"{ALBY_API_URL}/payments/bolt11", json=payload, headers=headers
        )

        if resp.status_code in (200, 201):
            data = resp.json()
            preimage = (
                data.get("payment_preimage")
                or data.get("preimage")
                or (
                    data.get("payment", {}).get("payment_preimage")
                    if isinstance(data.get("payment"), dict)
                    else None
                )
            )
            print("Payment settled successfully!")
            return preimage
        else:
            raise Exception(f"Alby Payment Error ({resp.status_code}): {resp.text}")


def fetch_gated_mempool_signal():
    token = ALBY_ACCESS_TOKEN.strip()
    if not token:
        print("ERROR: ALBY_ACCESS_TOKEN environment variable is missing.")
        return

    with httpx.Client(timeout=60.0) as client:
        print(f"Connecting to gated endpoint: {API_URL}")
        res = client.get(API_URL)

        if res.status_code == 402:
            print("HTTP 402 Payment Required received.")
            auth_header = res.headers.get("WWW-Authenticate") or ""
            invoice, payment_hash = parse_l402_header(auth_header)

            # Fallback parsing for FastAPI nested response format: {"detail": {"invoice": ...}}
            if not invoice or not payment_hash:
                try:
                    body = res.json()
                    detail = (
                        body.get("detail", {})
                        if isinstance(body.get("detail"), dict)
                        else body
                    )
                    invoice = detail.get("invoice")
                    payment_hash = detail.get("payment_hash")
                except Exception:
                    pass

            if not invoice or not payment_hash:
                print(
                    f"ERROR: Could not parse invoice from response header or body.\nRaw Body: {res.text}"
                )
                return

            print(f"Invoice Received: {invoice[:25]}...")
            print(f"Payment Hash: {payment_hash}")

            preimage = pay_invoice_via_alby(invoice, token)

            if not preimage:
                print("ERROR: Could not extract preimage from Alby response.")
                return

            print("Submitting L402 authorization credentials...")
            l402_auth = f"L402 {preimage}:{payment_hash}"
            auth_headers = {"Authorization": l402_auth}

            final_res = client.get(API_URL, headers=auth_headers)
            print(f"\nSTATUS: {final_res.status_code}")
            print("--- Live Mempool Data Output ---")
            print(final_res.json())

        elif res.status_code == 200:
            print("STATUS: 200 (Already authenticated)")
            print(res.json())
        else:
            print(f"Request failed with status {res.status_code}: {res.text}")


if __name__ == "__main__":
    fetch_gated_mempool_signal()
