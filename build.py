#!/usr/bin/env python3
"""
Kvizo Community Builder
- Validates all quizzes
- Generates manifest.json with SHA-256 hashes
- Signs with Ed25519 (private key from env or file)
- Outputs community.json + community.json.sig (legacy compat)
"""
import json, hashlib, os, sys, time
from pathlib import Path
from keyutil import load_private_key

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization
except ImportError:
    print("ERROR: pip install cryptography")
    sys.exit(1)

ROOT = Path(__file__).parent
QUIZZES_DIR = ROOT / "quizzes"
MANIFEST_FILE = ROOT / "manifest.json"
COMMUNITY_FILE = ROOT / "community.json"
SIG_FILE = ROOT / "community.json.sig"

def validate_quiz(q, path):
    errors = []
    if not q.get("id"):
        errors.append(f"{path}: missing id")
    if not q.get("title"):
        errors.append(f"{path}: missing title")
    if not q.get("category"):
        errors.append(f"{path}: missing category")
    questions = q.get("questions", [])
    if len(questions) < 1:
        errors.append(f"{path}: no questions")
    if len(questions) > 50:
        errors.append(f"{path}: too many questions ({len(questions)} > 50)")
    for i, ques in enumerate(questions):
        if not ques.get("question"):
            errors.append(f"{path}: Q{i+1} missing question text")
        opts = ques.get("options", [])
        if len(opts) < 2 or len(opts) > 6:
            errors.append(f"{path}: Q{i+1} has {len(opts)} options (need 2-6)")
        ci = ques.get("correct_index")
        if ci is None or ci < 0 or ci >= len(opts):
            errors.append(f"{path}: Q{i+1} correct_index {ci} out of range")
    return errors

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()

def main():
    all_errors = []
    quizzes_data = []
    manifest_quizzes = []
    version_file = ROOT / ".version"
    version = 1
    if version_file.exists():
        version = int(version_file.read_text().strip()) + 1
    version_file.write_text(str(version))

    for cat_dir in sorted(QUIZZES_DIR.iterdir()):
        if not cat_dir.is_dir():
            continue
        for quiz_file in sorted(cat_dir.glob("*.json")):
            q = json.load(open(quiz_file))
            rel = str(quiz_file.relative_to(ROOT))
            errs = validate_quiz(q, rel)
            all_errors.extend(errs)
            quizzes_data.append(q)
            manifest_quizzes.append({
                "id": q["id"],
                "title": q["title"],
                "category": q.get("category", ""),
                "difficulty": q.get("difficulty", ""),
                "author": q.get("author", ""),
                "questions_count": len(q.get("questions", [])),
                "file": rel,
                "sha256": sha256_file(quiz_file),
            })

    if all_errors:
        print("VALIDATION FAILED:")
        for e in all_errors:
            print(f"  ❌ {e}")
        sys.exit(1)

    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    # Legacy: community.json
    community = {
        "schema_version": 1,
        "key_id": "kvizo-community-v1",
        "issued_at": now,
        "quizzes": quizzes_data,
    }
    COMMUNITY_FILE.write_text(json.dumps(community, indent=2))

    # New: manifest.json
    manifest = {
        "version": version,
        "key_id": "kvizo-community-v1",
        "issued_at": now,
        "total_quizzes": len(quizzes_data),
        "quizzes": manifest_quizzes,
    }
    MANIFEST_FILE.write_text(json.dumps(manifest, indent=2))

    # Sign
    private_key = os.environ.get("ED25519_PRIVATE_KEY_PEM")
    if private_key:
        key = load_private_key(private_key)
    else:
        key = Ed25519PrivateKey.generate()

    # Sign manifest.json
    sig_manifest = key.sign(json.dumps(manifest, indent=2).encode())
    (ROOT / "manifest.json.sig").write_bytes(sig_manifest)
    # Also sign community.json (legacy app verification)
    sig_community = key.sign(open(COMMUNITY_FILE, "rb").read())
    SIG_FILE.write_bytes(sig_community)
    print(f"signed manifest.json + community.json ({len(sig_manifest)} bytes)")

        pub = key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo
        )
        print(f"ephemeral key (NOT for production):")
        print(pub.decode())
        print("set ED25519_PRIVATE_KEY_PEM for production signing")

    print(f"✅ {len(quizzes_data)} quizzes | version {version} | issued {now}")
    print(f"   manifest.json + community.json + .sig written")

if __name__ == "__main__":
    main()
