"""
Create RSA key pair for JWT signing (RS256).

Usage: python scripts/generate_keys.py
"""

from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from pathlib import Path


def generate_rsa_keypair():
    """Generate RSA key pair and save to keys/ directory."""
    keys_dir = Path("keys")
    keys_dir.mkdir(exist_ok=True)
    
    print("Generating RSA key pair...")
    
    # Generate private key
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    
    # Serialize private key
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    
    # Serialize public key
    public_key = private_key.public_key()
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    
    # Write keys
    private_key_path = keys_dir / "private.pem"
    public_key_path = keys_dir / "public.pem"
    
    private_key_path.write_bytes(private_pem)
    public_key_path.write_bytes(public_pem)
    
    print(f"✓ Generated private key: {private_key_path}")
    print(f"✓ Generated public key: {public_key_path}")
    print("\nKeys are ready for JWT signing (RS256)")


if __name__ == "__main__":
    generate_rsa_keypair()
