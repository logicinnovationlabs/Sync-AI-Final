"""Smoke: refresh token -> list Drive files + Gmail messages. Never prints token."""
from __future__ import annotations
import os, sys
from datetime import datetime, timedelta
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

import httpx

def main() -> int:
    cid = os.environ.get("GOOGLE_CLIENT_ID", "")
    secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")
    rt = os.environ.get("GOOGLE_REFRESH_TOKEN", "")
    if not all([cid, secret, rt]):
        print("SMOKE_FAIL missing_env_vars")
        return 2

    print("SMOKE: exchanging refresh_token for access_token (redacted)...")
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": cid,
                "client_secret": secret,
                "refresh_token": rt,
                "grant_type": "refresh_token",
            },
        )
    if resp.status_code != 200:
        body = resp.text
        # redact any accidental token echoes
        body = body.replace(rt, "[REDACTED_REFRESH]")
        print(f"SMOKE_FAIL token_refresh HTTP {resp.status_code}: {body[:400]}")
        return 1

    access = resp.json()["access_token"]
    print(f"SMOKE: access_token obtained (len={len(access)})")

    # Drive list
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials(token=access)
    drive = build("drive", "v3", credentials=creds, cache_discovery=False)
    dres = drive.files().list(pageSize=5, fields="files(id,name,mimeType)", q="trashed=false").execute()
    files = dres.get("files", [])
    print(f"SMOKE_DRIVE_OK count={len(files)}")
    for f in files:
        print(f"  drive_file id={f.get('id')} name={f.get('name')!r} mime={f.get('mimeType')}")

    gmail = build("gmail", "v1", credentials=creds, cache_discovery=False)
    gres = gmail.users().messages().list(userId="me", maxResults=5).execute()
    msgs = gres.get("messages", [])
    print(f"SMOKE_GMAIL_OK count={len(msgs)}")
    for m in msgs:
        print(f"  gmail_msg id={m.get('id')}")

    print("SMOKE_PASS")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
