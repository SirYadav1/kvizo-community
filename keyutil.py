import base64
from cryptography.hazmat.primitives import serialization

def load_private_key(raw):
    r = raw.strip()
    if "-----" in r:
        parts = [p for p in r.split("-----") if p.strip()]
        b = "".join("".join(p.split()) for p in parts if "BEGIN" not in p and "END" not in p)
    else:
        b = "".join(r.split())
    body = base64.b64encode(base64.b64decode(b)).decode()
    lines = [body[i:i+64] for i in range(0, len(body), 64)]
    pem = "-----BEGIN PRIVATE KEY-----\n" + "\n".join(lines) + "\n-----END PRIVATE KEY-----\n"
    return serialization.load_pem_private_key(pem.encode(), password=None)
