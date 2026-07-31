# Quick Fix Guide - Installation Issues

## Problem Summary

You encountered:
1. Dependency conflict between `pydantic` and `pydantic-core`
2. Missing `cryptography` module
3. Missing `app` module when running scripts

## ✅ Solution (Quick Fix)

Run these commands in PowerShell:

```powershell
cd C:\Users\prath\OneDrive\Desktop\SnyQ_Phase_2\backend

# 1. Activate virtual environment
.\venv\Scripts\activate

# 2. Reinstall dependencies with fixed requirements.txt
pip uninstall pydantic pydantic-core pydantic-settings -y
pip install -r requirements.txt

# 3. Verify installation
python -c "import asyncpg; import cryptography; import fastapi; import sqlalchemy; print('✓ All packages installed')"

# 4. Generate JWT keys
python scripts\generate_keys.py

# 5. Seed tenants (make sure Docker containers are running)
python scripts\seed_tenants.py

# 6. Run tests
pytest tests\test_signoff.py -v
```

---

## What Was Fixed

### 1. Fixed `requirements.txt`
- Removed explicit `pydantic-core==2.27.0` (let pydantic manage it)
- Added explicit `bcrypt` and `cryptography` versions

### 2. Fixed All Scripts
Updated these scripts to add the backend directory to Python path:
- `scripts/seed_tenants.py`
- `scripts/run_scim_sync.py`

Now they can import `app` modules correctly.

---

## Full Clean Reinstall (If Quick Fix Doesn't Work)

If the quick fix doesn't work, do a full clean reinstall:

```powershell
cd C:\Users\prath\OneDrive\Desktop\SnyQ_Phase_2\backend

# 1. Delete virtual environment
Remove-Item -Recurse -Force venv

# 2. Recreate virtual environment
python -m venv venv

# 3. Activate it
.\venv\Scripts\activate

# 4. Upgrade pip
python -m pip install --upgrade pip

# 5. Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# 6. Verify
python -c "import asyncpg; import cryptography; import fastapi; import sqlalchemy; print('✓ All packages installed')"

# 7. Generate keys
python scripts\generate_keys.py

# 8. Make sure Docker is running
docker-compose up -d

# 9. Seed tenants
python scripts\seed_tenants.py

# 10. Run tests
pytest tests\test_signoff.py -v
```

---

## 🐳 Alternative: Use Docker (Recommended)

**Easiest approach - No Python setup needed!**

```powershell
cd C:\Users\prath\OneDrive\Desktop\SnyQ_Phase_2\backend

# Generate JWT keys (first time only)
mkdir keys
docker run --rm -v ${PWD}/keys:/keys python:3.12-slim sh -c "pip install cryptography && python -c 'from cryptography.hazmat.primitives.asymmetric import rsa; from cryptography.hazmat.primitives import serialization; from cryptography.hazmat.backends import default_backend; private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend()); pem_private = private_key.private_bytes(encoding=serialization.Encoding.PEM, format=serialization.PrivateFormat.PKCS8, encryption_algorithm=serialization.NoEncryption()); pem_public = private_key.public_key().public_bytes(encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo); open(\"/keys/private.pem\", \"wb\").write(pem_private); open(\"/keys/public.pem\", \"wb\").write(pem_public); print(\"✓ Keys generated\")'"

# Run everything (build, setup, seed, test)
.\test-block-a.bat
```

This approach:
- ✅ No virtual environment needed
- ✅ No dependency conflicts
- ✅ Everything runs in Docker
- ✅ Clean, isolated environment

---

## Verification Commands

After installation, verify everything works:

```powershell
# Check Python packages
python -c "import asyncpg; print('asyncpg:', asyncpg.__version__)"
python -c "import cryptography; print('cryptography:', cryptography.__version__)"
python -c "import fastapi; print('fastapi:', fastapi.__version__)"

# Check Docker containers
docker ps

# Check keys exist
dir keys
# Should show: private.pem, public.pem

# Check .env exists
dir .env
```

---

## Common Issues & Solutions

### Issue: "ModuleNotFoundError: No module named 'app'"

**Solution:**
```powershell
# Make sure you're in the backend directory
cd C:\Users\prath\OneDrive\Desktop\SnyQ_Phase_2\backend

# Then run scripts
python scripts\seed_tenants.py
```

The scripts now add the backend directory to sys.path automatically.

---

### Issue: "ModuleNotFoundError: No module named 'cryptography'"

**Solution:**
```powershell
.\venv\Scripts\activate
pip install cryptography bcrypt
```

---

### Issue: "Cannot connect to database"

**Solution:**
```powershell
# Make sure Docker containers are running
docker-compose up -d

# Wait 10 seconds
Start-Sleep -Seconds 10

# Check status
docker-compose ps
```

---

### Issue: Dependency conflicts

**Solution:**
```powershell
# Use the fixed requirements.txt
pip install -r requirements.txt --force-reinstall --no-cache-dir
```

---

## Next Steps

Once installation is fixed:

1. **Generate JWT keys** (if not done):
   ```powershell
   python scripts\generate_keys.py
   ```

2. **Start Docker services**:
   ```powershell
   docker-compose up -d
   ```

3. **Seed tenants**:
   ```powershell
   python scripts\seed_tenants.py
   ```

4. **Run Block A tests**:
   ```powershell
   pytest tests\test_signoff.py -v
   ```

5. **Start the app**:
   ```powershell
   uvicorn app.main:app --reload
   # Visit: http://localhost:8000/docs
   ```

---

## Recommended Approach

**Use Docker for testing (simplest):**

See `QUICKSTART_DOCKER.md` for the complete Docker-based workflow. No Python virtual environment needed!

**Use local Python for development:**

Follow the "Quick Fix" section above to fix your current installation.
