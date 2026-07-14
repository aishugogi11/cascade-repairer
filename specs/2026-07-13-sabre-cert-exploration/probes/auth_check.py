"""Sabre CERT auth smoke check — run this FIRST every probe/test session.

Detects a credential reset in seconds (Sabre periodically resets test creds).
Builds the /v2/auth/token Basic secret from the raw pair in config/.env:

    secret = base64( base64(SABRE_API_USER_ID) + ":" + base64(SABRE_API_SECRET) )

Prints only HTTP status and token metadata — never a credential or the token.
Exit 0 on success, 1 on failure.

Run (host python3.14 has no CA bundle; use the container):
    set -a && . ./config/.env && set +a && \
    docker compose exec -T -e SABRE_API_USER_ID -e SABRE_API_SECRET backend \
        python3 - < specs/2026-07-13-sabre-cert-exploration/probes/auth_check.py
"""
import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

CERT_BASE_URL = "https://api.cert.platform.sabre.com"


def build_secret(user_id: str, password: str) -> str:
    b64 = lambda s: base64.b64encode(s.encode()).decode()
    return b64(f"{b64(user_id)}:{b64(password)}")


def mint_token(base_url: str = CERT_BASE_URL) -> dict:
    """Returns the token response dict; raises urllib.error.HTTPError on 4xx/5xx."""
    secret = build_secret(
        os.environ["SABRE_API_USER_ID"], os.environ["SABRE_API_SECRET"]
    )
    req = urllib.request.Request(
        f"{base_url}/v2/auth/token",
        data=urllib.parse.urlencode({"grant_type": "client_credentials"}).encode(),
        headers={
            "Authorization": f"Basic {secret}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def main() -> int:
    for var in ("SABRE_API_USER_ID", "SABRE_API_SECRET"):
        if not os.environ.get(var):
            print(f"FAIL: {var} not set (source config/.env into the exec env)")
            return 1
    try:
        body = mint_token()
    except urllib.error.HTTPError as e:
        print(f"FAIL: HTTP {e.code} — credentials likely reset or malformed")
        print(e.read().decode()[:300])
        return 1
    tok = body.get("access_token", "")
    print("OK: token minted")
    print(f"  token_type: {body.get('type') or body.get('token_type')}")
    print(f"  expires_in: {body.get('expires_in')} s")
    print(f"  access_token: <{len(tok)} chars, prefix {tok[:6]}...>")
    return 0


if __name__ == "__main__":
    sys.exit(main())
