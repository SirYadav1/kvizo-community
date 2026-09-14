#!/usr/bin/env python3
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import hashes, serialization
import json, hashlib, base64, os

os.makedirs('/tmp/kvizo-community/keys', exist_ok=True)

# Generate keypair
private_key = Ed25519PrivateKey.generate()
public_key = private_key.public_key()

# Save keys
with open('/tmp/kvizo-community/keys/public_key.pem', 'wb') as f:
    f.write(public_key.public_bytes(encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo))
with open('/tmp/kvizo-community/keys/private_key.pem', 'wb') as f:
    f.write(private_key.private_bytes(encoding=serialization.Encoding.PEM, format=serialization.PrivateFormat.PKCS8, encryption_algorithm=serialization.NoEncryption()))

# Sign manifest
with open('/tmp/kvizo-community/manifest.json') as f:
    manifest_str = f.read()

manifest_hash = hashlib.sha256(manifest_str.encode()).digest()
signature = private_key.sign(manifest_hash)

sig_b64 = base64.b64encode(signature).decode()
pub_key_b64 = base64.b64encode(public_key.public_bytes(encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw)).decode()

signed_manifest = json.loads(manifest_str)
signed_manifest['signature'] = sig_b64
signed_manifest['public_key'] = pub_key_b64

with open('/tmp/kvizo-community/manifest.json', 'w') as f:
    json.dump(signed_manifest, f, indent=2)

print(f"Signed. Signature: {sig_b64[:30]}...")
print(f"Pubkey: {pub_key_b64[:30]}...")
