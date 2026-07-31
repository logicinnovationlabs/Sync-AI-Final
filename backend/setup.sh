#!/bin/bash
# Quick setup script for SnyQ Backend (Block A)
# Usage: ./setup.sh

set -e

echo "================================================"
echo "SnyQ Backend - Block A Setup"
echo "================================================"

# Check if Python 3.12+ is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.12+"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
echo "✓ Found Python $PYTHON_VERSION"

# Create virtual environment
if [ ! -d "venv" ]; then
    echo ""
    echo "Creating virtual environment..."
    python3 -m venv venv
    echo "✓ Virtual environment created"
else
    echo "✓ Virtual environment already exists"
fi

# Activate virtual environment
echo ""
echo "Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo ""
echo "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt
echo "✓ Dependencies installed"

# Install dev dependencies (optional)
read -p "Install development dependencies? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    pip install -r requirements-dev.txt
    echo "✓ Development dependencies installed"
fi

# Generate JWT keys
echo ""
echo "Generating JWT keys..."
if [ ! -f "keys/private.pem" ]; then
    python scripts/generate_keys.py
    echo "✓ JWT keys generated"
else
    echo "✓ JWT keys already exist"
fi

# Copy .env.example if .env doesn't exist
echo ""
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "✓ Created .env file from .env.example"
    echo "⚠️  Please edit .env with your configuration"
else
    echo "✓ .env file already exists"
fi

echo ""
echo "================================================"
echo "✅ Setup Complete!"
echo "================================================"
echo ""
echo "Next steps:"
echo "1. Start services: docker-compose up -d"
echo "2. Seed tenants:   python scripts/seed_tenants.py"
echo "3. Run tests:      pytest tests/test_signoff.py -v"
echo "4. Start app:      uvicorn app.main:app --reload"
echo ""
echo "API Docs: http://localhost:8000/docs"
echo "================================================"
