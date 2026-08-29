# Secret handling & safe distribution

## Incident class: working-tree zip leaks

Git history can be clean while a **zip of the working tree** still ships secrets.
`.gitignore` only protects `git add` / `git archive` / clones — **not** Explorer
“Compress folder”, OneDrive “Download as zip” of a synced folder, or
`Compress-Archive` over the whole tree.

### What must never leave the machine in an archive

| Path / pattern | Why |
|----------------|-----|
| `.env`, `.env.docker`, `backend/.env`, `frontend/.env.local` | OAuth client secrets, API keys |
| `backend/keys/*.pem` | JWT signing private key |
| `.venv/`, `venv/`, `node_modules/` | Local junk (and sometimes cached secrets) |
| `*.pem`, `*.key`, `credentials.json`, service-account JSON | Key material |

### Safe ways to share code

1. **Preferred:** `git clone` / push a branch / PR (remote must not contain secrets).
2. **Archive:** `scripts/package-safe-archive.ps1` (Windows) or `scripts/package-safe-archive.sh` (Unix).
   These use **`git archive`**, so only tracked files are included.
3. If you must zip a worktree, use the script’s filtered fallback and never hand-zip the folder.

```powershell
# From repo root (Windows)
.\scripts\package-safe-archive.ps1
```

```bash
# Unix / Git Bash
bash scripts/package-safe-archive.sh
```

## Connector token encryption (Fernet) & Redis

Connector OAuth blobs are encrypted with Fernet. The **root key must not live in Redis**
next to the ciphertext.

| Rule | Detail |
|------|--------|
| Root key | Vault `kv/platform/google-oauth-fernet` and/or `TOKEN_ENCRYPTION_KEY` |
| Per-tenant keys | HKDF-derived from the root (`app/connectors/token_crypto.py`) |
| Redis | Holds **ciphertext only**; legacy key `kv_platform_google_oauth_fernet` is scrubbed on load |
| `TOKEN_ENCRYPTION_KEY` | Must be a real Fernet key — passphrases / sha256 fallback are rejected |
| Redis auth | Outside development/test, `REDIS_URL` must include a password |
| Redis bind | Compose publishes `127.0.0.1:6379` only (not `0.0.0.0`) |

Generate a Fernet key for local / workers:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Set the same value as `TOKEN_ENCRYPTION_KEY` on the API and Celery workers (or store it
only in a shared Vault and point both at `VAULT_URL`).

Redis URL shape:

```text
redis://:YOUR_REDIS_PASSWORD@redis:6379/0
```

## Assume burned credentials (do this now)

If a raw working-tree zip was shared, treat these as **compromised**:

### 1. Google OAuth client secret

1. Open [Google Cloud Console](https://console.cloud.google.com/) → APIs & Services → Credentials.
2. Open the OAuth 2.0 Client ID used by SynQ.
3. **Reset secret** / create a new client secret; delete the old `GOCSPX-…` value.
4. Update local only (never commit):
   - `.env`
   - `.env.docker`
   - `backend/.env`
   - Render / Railway / Vercel env panels
5. Restart API + Celery (`docker compose restart app celery_worker`).

### 2. JWT signing keypair

Regenerate under `backend/keys/` (already gitignored):

```powershell
cd backend
python -c "from pathlib import Path; from cryptography.hazmat.primitives.asymmetric import rsa; from cryptography.hazmat.primitives import serialization; keys=Path('keys'); keys.mkdir(exist_ok=True); k=rsa.generate_private_key(public_exponent=65537, key_size=2048); (keys/'private.pem').write_bytes(k.private_bytes(encoding=serialization.Encoding.PEM, format=serialization.PrivateFormat.TraditionalOpenSSL, encryption_algorithm=serialization.NoEncryption())); (keys/'public.pem').write_bytes(k.public_key().public_bytes(encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo)); print('ok')"
```

Or with OpenSSL:

```bash
cd backend
mkdir -p keys
openssl genrsa -out keys/private.pem 2048
openssl rsa -in keys/private.pem -pubout -out keys/public.pem
```

Then restart the API. **All existing access/refresh tokens are invalid** after rotation — users must sign in again.

If production mounts JWT PEMs as secret files (Render), replace those secret files too.

### 3. Microsoft / OpenRouter / other secrets in the same zip

If the zip also contained `.env.docker`, rotate **every** secret that was present there (Microsoft client secret, OpenRouter keys, etc.) the same way: revoke in the provider console, put the new value only in env panels / local gitignored files.

## Templates vs live values

- `backend/.env.example` and `frontend/.env.example` may list **empty** keys and comments.
- They must **never** contain live `GOCSPX-…`, Azure secrets, or PEM blocks.
- Copy examples → local `.env*` and fill secrets there.

## Checklist before sharing code

- [ ] No `.env*` in the package (except `*.example`)
- [ ] No `backend/keys/`
- [ ] Package built with `scripts/package-safe-archive.*` or `git archive`
- [ ] Google client secret rotated if a previous raw zip existed
- [ ] JWT keypair regenerated if a previous raw zip existed
- [ ] Deploy env vars updated to the new secret / new PEM mount
