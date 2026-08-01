# Installation Guide - SnyQ Backend (Block A)

Choose your preferred installation method:

---

## Option 1: Quick Setup Script (Recommended) ⚡

### Linux/Mac
```bash
cd backend
chmod +x setup.sh
./setup.sh
```

### Windows
```cmd
cd backend
setup.bat
```

The setup script will:
- ✅ Create a virtual environment
- ✅ Install all dependencies
- ✅ Generate RSA keys for JWT
- ✅ Create .env file from template

After setup, just run:
```bash
docker-compose up -d
python scripts/seed_tenants.py
```

---

## Option 2: Using Poetry 📦

```bash
cd backend
poetry install
poetry run python scripts/generate_keys.py
```

---

## Option 3: Using pip + requirements.txt 🐍

### Linux/Mac
```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt  # For testing
python scripts/generate_keys.py
```

### Windows
```cmd
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
python scripts\generate_keys.py
```

---

## Option 4: Using Docker Only 🐳

```bash
cd backend
docker-compose up --build
```

This builds everything inside Docker - no local Python installation needed!

---

## Post-Installation

Regardless of which method you chose, complete the setup with:

### 1. Start Services
```bash
docker-compose up -d
```

### 2. Seed Development Tenants
```bash
python scripts/seed_tenants.py
```

### 3. Run Tests
```bash
pytest tests/test_signoff.py -v
```

### 4. Access the API
- **API Docs**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health

---

## Verification

Test that everything works:

```bash
# Health check
curl http://localhost:8000/health

# Should return: {"status": "healthy", ...}
```

---

## Next Steps

- Read `README.md` for comprehensive documentation
- See `QUICKSTART.md` for common tasks
- Run `pytest tests/test_signoff.py -v` to verify A1-A7 signoff criteria

---

## Troubleshooting

### Port Conflicts

If ports 5432 or 6379 are in use:
```bash
docker-compose down
# Edit docker-compose.yml to change ports
docker-compose up -d
```

### Permission Errors (Linux/Mac)

```bash
chmod +x setup.sh
chmod +x scripts/*.py
```

### Missing Dependencies

```bash
# Reinstall dependencies
pip install -r requirements.txt --force-reinstall
```

### Database Connection Errors

```bash
# Reset Docker volumes
docker-compose down -v
docker-compose up -d
```

---

## Environment Variables

Copy and edit `.env`:
```bash
cp .env.example .env
# Edit .env with your values
```

Key variables:
- `CONTROL_PLANE_DATABASE_URL` - Control-plane DB
- `REDIS_URL` - Redis connection string
- `VAULT_URL` - Leave blank for MockVaultClient (dev)

---

## Support

For issues, see:
- `README.md` - Full documentation
- `BUILD_SUMMARY.md` - Build details
- Architecture PDF - Design reference
