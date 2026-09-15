#!/usr/bin/env python3
"""Sign community.json + manifest.json with your private key. Run manually when needed."""
import sys, os
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from keyutil import load_private_key
import json

ROOT = Path(__file__).parent

# Get key from env or prompt
private_key = os.environ.get("ED25519_PRIVATE_KEY_PEM")
if not private_key:
    print("Paste your PRIVATE KEY (end with Enter + Ctrl-D):")
    private_key = sys.stdin.read()

key = load_private_key(private_key)

# Re-generate community.json from quizzes (in case it changed)
# Just sign what exists
for target, sig_name in [("manifest.json", "manifest.json.sig"), ("community.json", "community.json.sig")]:
    data = open(ROOT / target, "rb").read()
    sig = key.sign(data)
    (ROOT / sig_name).write_bytes(sig)
    print(f"signed {sig_name} ({len(sig)} bytes) for {target}")

print("DONE")
