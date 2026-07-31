"""
Interactive Google OAuth Login & Real-Time Sync Inspection Script.

Flow:
1. Loads Google OAuth credentials from backend config / .env.
2. Starts a local HTTP listener to automatically capture the OAuth callback.
3. Displays a clickable Google OAuth Login URL in the terminal.
4. Exchanges code for real OAuth tokens and saves them.
5. Performs real Google Drive / Gmail sync (two-pass deletion + delta ingestion).
6. Displays live Celery / Sync logs, transformed UnifiedDocuments, and vector points indexed in Qdrant!
"""

import sys
import os

# Reconfigure stdout/stderr encoding to UTF-8 on Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
import asyncio
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import threading
import json
from datetime import datetime, timezone

# Ensure backend root is in sys.path
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.core.config import settings
from app.connectors.google.oauth import GoogleOAuthManager
from app.connectors.google.services.drive_service import DriveConnector
from app.connectors.google.services.gmail_service import GmailConnector
from app.services.indexer import indexer
from app.storage.qdrant_client import qdrant_client

# Configure logging to show live sync activity in terminal
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("interactive_sync")

# File-based Token Storage so tokens persist
TOKEN_FILE = os.path.join(backend_dir, ".tokens.json")


class FileTokenStore:
    """Persistent local token store."""

    def __init__(self, filepath=TOKEN_FILE):
        self.filepath = filepath
        self._tokens = self._load()

    def _load(self) -> dict:
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save(self) -> None:
        with open(self.filepath, "w") as f:
            json.dump(self._tokens, f, indent=2)

    def get_token(self, key: str) -> dict:
        return self._tokens.get(key)

    def set_token(self, key: str, token_data: dict) -> None:
        self._tokens[key] = token_data
        self._save()


# Shared callback container for HTTP server thread
auth_code_container = {"code": None, "error": None}


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """HTTP Request Handler to capture Google OAuth authorization code."""

    def do_GET(self):
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)

        if "code" in query:
            auth_code_container["code"] = query["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            html = """
            <html>
                <body style="font-family: Arial, sans-serif; text-align: center; padding-top: 50px; background: #0f172a; color: #f8fafc;">
                    <h1 style="color: #38bdf8;">✓ Google Account Connected!</h1>
                    <p style="font-size: 18px;">Authorization successful. You can close this browser tab and return to your terminal.</p>
                </body>
            </html>
            """
            self.wfile.write(html.encode("utf-8"))
        elif "error" in query:
            auth_code_container["error"] = query["error"][0]
            self.send_response(400)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(f"OAuth error: {query['error'][0]}".encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        # Silence HTTP server logs
        return


def start_local_callback_server(port=8000):
    """Start local HTTP server on port 8000."""
    try:
        server = HTTPServer(("localhost", port), OAuthCallbackHandler)
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        return server
    except Exception as e:
        logger.warning(f"Could not bind local HTTP server on port {port}: {e}")
        return None


from dotenv import load_dotenv

load_dotenv()


async def get_authorization_code(auth_code_container) -> str:
    """Get authorization code via auto-captured HTTP request or manual user prompt."""
    print("Waiting for browser login authentication...")
    
    # Try auto-capture for up to 2 seconds
    for _ in range(4):
        if auth_code_container.get("code"):
            return auth_code_container["code"]
        if auth_code_container.get("error"):
            raise Exception(f"OAuth error: {auth_code_container['error']}")
        await asyncio.sleep(0.5)

    print("\n" + "!" * 80)
    print(" 📌 ACTION REQUIRED: PASTE YOUR REDIRECT URL OR CODE BELOW")
    print("!" * 80)
    print("Since your backend is running in Docker on port 8000, your browser")
    print("redirected to http://localhost:8000 and displayed: {\"detail\":\"Not Found\"}.")
    print("\n👉 COPY the full URL from your browser address bar, and PASTE it below:")
    
    while True:
        user_input = await asyncio.to_thread(input, "\nPaste URL or Code: ")
        user_input = user_input.strip()

        if not user_input:
            print("⚠️ Input cannot be empty. Please paste the full URL or Authorization Code:")
            continue

        if "code=" in user_input:
            parsed = urlparse(user_input)
            query = parse_qs(parsed.query)
            if "code" in query:
                return query["code"][0]

        if len(user_input) > 10 and not user_input.startswith("http"):
            return user_input

        print("⚠️ Could not find a valid OAuth code in your input.")
        print("Please copy and paste the FULL URL from your browser address bar (starts with http://localhost:8000/...).")


async def run_sync_demo():
    print("\n" + "=" * 80)
    print(" 🚀 SNYQ GOOGLE AUTH & REAL-TIME SYNC DEMO")
    print("=" * 80 + "\n")

    client_id = (
        getattr(settings, "google_client_id", None)
        or os.getenv("GOOGLE_CLIENT_ID", "")
    )
    client_secret = (
        getattr(settings, "google_client_secret", None)
        or os.getenv("GOOGLE_CLIENT_SECRET", "")
    )
    redirect_uri = (
        getattr(settings, "google_redirect_uri", None)
        or os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/api/v1/connectors/google/callback")
    )

    if not client_id or not client_secret:
        print("❌ Error: GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET missing in .env")
        return

    token_store = FileTokenStore()
    scopes = [
        "https://www.googleapis.com/auth/drive.readonly",
        "https://www.googleapis.com/auth/gmail.readonly",
    ]

    oauth_manager = GoogleOAuthManager(
        token_store=token_store,
        client_id=client_id,
        client_secret=client_secret,
        scopes=scopes,
    )

    tenant_id = "tenant123"
    token_key = f"google_oauth:{tenant_id}"
    existing_token = token_store.get_token(token_key)

    if not existing_token:
        # Start local callback server to capture redirect code
        server = start_local_callback_server(port=8000)

        auth_url = oauth_manager.build_authorization_url(
            tenant_id=tenant_id,
            redirect_uri=redirect_uri,
        )

        print("📋 STEP 1: LOGIN WITH YOUR GOOGLE ACCOUNT")
        print("-" * 80)
        print("Please open the following link in your browser to authorize access:\n")
        print(f"\033[94m{auth_url}\033[0m\n")
        print("-" * 80)

        try:
            code = await get_authorization_code(auth_code_container)
        except Exception as e:
            print(f"❌ Authorization Failed: {e}")
            return

        print(f"✓ Authorization Code received: {code[:15]}...")

        # Exchange code for tokens
        print("Exchanging authorization code for OAuth tokens...")
        token_data = await oauth_manager.exchange_code_for_tokens(
            tenant_id=tenant_id,
            code=code,
            redirect_uri=redirect_uri,
        )
        print("✓ OAuth Access Token & Refresh Token saved successfully!")
    else:
        print("✓ Found existing saved OAuth credentials for tenant tenant123.")

    # Get valid access token
    access_token = await oauth_manager.get_valid_token(tenant_id)
    print(f"✓ Active OAuth Access Token verified ({len(access_token)} chars)\n")

    # Step 2: Choose Source to Sync
    print("=" * 80)
    print(" 🔄 STEP 2: RUN REAL-TIME DATA SYNCHRONIZATION")
    print("=" * 80)
    print("1. Google Gmail (Sync Emails)")
    print("2. Google Drive (Sync Files & Documents)")
    print("3. Both Gmail & Google Drive")

    choice = input("\nSelect option (1/2/3) [Default: 3]: ").strip() or "3"

    sources_to_sync = []
    if choice == "1":
        sources_to_sync = ["google_gmail"]
    elif choice == "2":
        sources_to_sync = ["google_drive"]
    else:
        sources_to_sync = ["google_gmail", "google_drive"]

    config = {"tenant_id": tenant_id, "mailbox_email": "user@example.com"}

    for source in sources_to_sync:
        print(f"\n▶ Starting Sync for {source.upper()}...")
        print("-" * 60)

        if source == "google_gmail":
            connector = GmailConnector(config, token_store, oauth_manager)
            print("Fetching recent Gmail messages...")
            delta_result = await connector.fetch_delta(
                since=datetime(1970, 1, 1, tzinfo=timezone.utc),
                cursor=None,
            )
            print(f"✓ Fetched {len(delta_result.documents)} raw emails from Gmail API.")

            if delta_result.documents:
                print("Transforming raw emails into UnifiedDocument format...")
                docs = await connector.transform(delta_result.documents)
                print(f"✓ Transformed {len(docs)} UnifiedDocuments.")

                print("Indexing documents & vector embeddings into Qdrant...")
                await indexer.bulk_index(docs, tenant_id)
                print(f"✓ Indexing Complete for Gmail!")

        elif source == "google_drive":
            connector = DriveConnector(config, token_store, oauth_manager)
            print("Fetching Google Drive file list...")
            delta_result = await connector.fetch_delta(
                since=datetime(1970, 1, 1, tzinfo=timezone.utc),
                cursor=None,
            )
            print(f"✓ Fetched {len(delta_result.documents)} raw files from Google Drive API.")

            if delta_result.documents:
                print("Transforming raw files into UnifiedDocument format...")
                docs = await connector.transform(delta_result.documents)
                print(f"✓ Transformed {len(docs)} UnifiedDocuments.")

                print("Indexing documents & vector embeddings into Qdrant...")
                await indexer.bulk_index(docs, tenant_id)
                print(f"✓ Indexing Complete for Google Drive!")

    # Step 3: View Synced & Chunked Vector Points in Qdrant
    print("\n" + "=" * 80)
    print(" 📊 STEP 3: INSPECT SYNCED & CHUNKED DATA IN QDRANT VECTOR DB")
    print("=" * 80 + "\n")

    try:
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        points, _ = qdrant_client.client.scroll(
            collection_name=qdrant_client.collection_name,
            scroll_filter=Filter(
                must=[FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id))]
            ),
            limit=10,
            with_payload=True,
            with_vectors=False,
        )

        print(f"Displaying {len(points)} Synced Vector Points for tenant '{tenant_id}':\n")
        for i, pt in enumerate(points, 1):
            payload = pt.payload
            print(f"--- [ Point #{i} ] ---")
            print(f"Point ID:    {pt.id}")
            print(f"Title:       {payload.get('title')}")
            print(f"Source:      {payload.get('source_type')}")
            print(f"URL:         {payload.get('url')}")
            print(f"Permissions: {payload.get('permissions')}")
            print(f"Metadata:    {json.dumps(payload.get('structured_metadata', {}), indent=2)}")
            print(f"Content Snippet: {str(payload.get('content', ''))[:150]}...")
            print("-" * 60)
    except Exception as e:
        print(f"⚠️ Note: Could not query Qdrant points directly: {e}")

    print("\n🎉 Sync Demo Completed Successfully!")


if __name__ == "__main__":
    asyncio.run(run_sync_demo())
