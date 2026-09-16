#!/usr/bin/env python3
"""
Kvizo Community builder.

One job: turn quizzes/**/*.json into signed files that the Kvizo app will trust.

Outputs (repo root - that is what GitHub Pages and the Worker both serve):
  manifest.json       - index: every quiz + its SHA-256 (what the app verifies first)
  manifest.json.sig   - base64 Ed25519 signature over manifest.json
  community.json      - legacy bundle (older app versions read this)
  community.json.sig  - base64 Ed25519 signature over community.json
  public_key.hex      - the public key that matches the signing key (for auditing)

Trust model: the private key never leaves your machine / the CI secret. The app has
the public key compiled in, so ONLY holders of this key can publish quizzes that the
app will accept. The Cloudflare Worker is just a CDN in front of these files.

Usage:
  python3 build.py                     # validate + build + sign (needs the private key)
  python3 build.py --check             # validate quizzes only (no key needed, for PRs)
  python3 build.py --verify-only       # re-verify existing signatures
  python3 build.py --keygen            # print a fresh keypair (for rotation)

Private key sources, first one found wins:
  --key-file PATH | $ED25519_PRIVATE_KEY_FILE | $ED25519_PRIVATE_KEY
Accepted formats: 32-byte hex, 32-byte base64, base64 PKCS#8, PEM, OpenSSH.
"""
import argparse
import base64
import binascii
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
    from cryptography.hazmat.primitives import serialization
except ImportError:
    print("ERROR: missing dependency. run: pip install cryptography")
    sys.exit(1)

ROOT = Path(__file__).resolve().parent
QUIZZES_DIR = ROOT / "quizzes"
MANIFEST = ROOT / "manifest.json"
COMMUNITY = ROOT / "community.json"
PUBKEY_FILE = ROOT / "public_key.hex"

SCHEMA_VERSION = 2
LEGACY_SCHEMA_VERSION = 1
KEY_ID = "kvizo-pub-2026-09"

# The public key the shipped app trusts. Signing with anything else would produce
# data the app rejects, so we refuse to do it unless you explicitly opt out.
EXPECTED_PUBKEY_HEX = "bbbd809c2cf94f734f50868f5d6fd447d13526373539f21778ec145f970ef9c0"

MAX_QUESTIONS = 50
MIN_OPTIONS, MAX_OPTIONS = 2, 4  # app maps options to A/B/C/D; a 5th option is silently dropped
DIFFICULTIES = {"Easy", "Medium", "Hard", "Expert"}
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")
CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


# --------------------------------------------------------------------------- keys

def _load_private_key(raw: str) -> Ed25519PrivateKey:
    """Tolerant loader: hex, base64, PKCS#8, PEM or OpenSSH - pasted however it came."""
    s = raw.strip().strip('"').strip("'")
    if "BEGIN" in s:
        s = s.replace("\\n", "\n")
        data = s.encode()
        for loader in (serialization.load_pem_private_key, serialization.load_ssh_private_key):
            try:
                key = loader(data, password=None)
                if isinstance(key, Ed25519PrivateKey):
                    return key
            except Exception:
                pass
        raise ValueError("could not parse PEM/OpenSSH private key")

    compact = "".join(s.split())
    # raw 32-byte key as hex
    if re.fullmatch(r"[0-9a-fA-F]{64}", compact):
        return Ed25519PrivateKey.from_private_bytes(binascii.unhexlify(compact))
    # base64: either raw 32 bytes or a PKCS#8 blob (48 bytes with prefix)
    try:
        blob = base64.b64decode(compact + "=" * (-len(compact) % 4))
    except Exception as e:
        raise ValueError(f"key is not hex, base64 or PEM: {e}")
    if len(blob) == 32:
        return Ed25519PrivateKey.from_private_bytes(blob)
    if len(blob) == 48 and blob[:16] == bytes.fromhex("302e020100300506032b657004220420"):
        return Ed25519PrivateKey.from_private_bytes(blob[16:])
    try:
        key = serialization.load_der_private_key(blob, password=None)
        if isinstance(key, Ed25519PrivateKey):
            return key
    except Exception:
        pass
    raise ValueError(f"unsupported key blob ({len(blob)} bytes)")


def pubkey_hex(key: Ed25519PrivateKey) -> str:
    return key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
    ).hex()


def read_private_key(args) -> str:
    if args.key_file:
        return Path(args.key_file).read_text()
    for env in ("ED25519_PRIVATE_KEY", "ED25519_PRIVATE_KEY_PEM"):
        if os.environ.get(env):
            return os.environ[env]
    if os.environ.get("ED25519_PRIVATE_KEY_FILE"):
        return Path(os.environ["ED25519_PRIVATE_KEY_FILE"]).read_text()
    return ""


# ----------------------------------------------------------------------- validate

def validate_quiz(q: dict, path: Path) -> list:
    try:
        where = str(path.relative_to(ROOT))
    except ValueError:
        where = str(path)  # caller passed a not-yet-written path
    errs = []

    def need_str(field, maxlen):
        v = q.get(field)
        if not isinstance(v, str) or not v.strip():
            errs.append(f"{where}: missing/empty '{field}'")
        elif len(v) > maxlen:
            errs.append(f"{where}: '{field}' too long ({len(v)} > {maxlen})")
        elif CTRL_RE.search(v):
            errs.append(f"{where}: '{field}' contains control characters")

    quiz_id = q.get("id")
    if not isinstance(quiz_id, str) or not ID_RE.match(quiz_id):
        errs.append(f"{where}: 'id' must match {ID_RE.pattern} (got {quiz_id!r})")

    need_str("title", 120)
    need_str("category", 40)
    need_str("difficulty", 20)
    need_str("author", 60)

    if isinstance(q.get("difficulty"), str) and q["difficulty"] not in DIFFICULTIES:
        errs.append(f"{where}: difficulty {q['difficulty']!r} not in {sorted(DIFFICULTIES)}")

    questions = q.get("questions")
    if not isinstance(questions, list) or not questions:
        errs.append(f"{where}: needs a non-empty 'questions' array")
        return errs
    if len(questions) > MAX_QUESTIONS:
        errs.append(f"{where}: {len(questions)} questions (max {MAX_QUESTIONS})")

    for i, ques in enumerate(questions, start=1):
        tag = f"{where}: Q{i}"
        if not isinstance(ques, dict):
            errs.append(f"{tag} is not an object")
            continue
        text = ques.get("question")
        if not isinstance(text, str) or not text.strip():
            errs.append(f"{tag} missing question text")
        elif len(text) > 500:
            errs.append(f"{tag} question too long ({len(text)} > 500)")
        opts = ques.get("options")
        if not isinstance(opts, list) or not (MIN_OPTIONS <= len(opts) <= MAX_OPTIONS):
            errs.append(f"{tag} needs {MIN_OPTIONS}-{MAX_OPTIONS} options "
                        f"(got {len(opts) if isinstance(opts, list) else type(opts).__name__})")
            continue
        if any(not isinstance(o, str) or not o.strip() for o in opts):
            errs.append(f"{tag} has an empty option")
        if len({o.strip().lower() for o in opts if isinstance(o, str)}) != len(opts):
            errs.append(f"{tag} has duplicate options")
        ci = ques.get("correct_index")
        if not isinstance(ci, int) or not (0 <= ci < len(opts)):
            errs.append(f"{tag} correct_index {ci!r} out of range 0..{len(opts) - 1}")
        exp = ques.get("explanation")
        if exp is not None and (not isinstance(exp, str) or len(exp) > 500):
            errs.append(f"{tag} explanation must be a string under 500 chars")
    return errs


def collect_quizzes() -> tuple:
    """Returns (list of (path, raw_bytes, parsed), list of errors)."""
    files, errs = [], []
    if not QUIZZES_DIR.is_dir():
        return [], [f"{QUIZZES_DIR.name}/ directory not found"]
    for path in sorted(QUIZZES_DIR.rglob("*.json")):
        raw = path.read_bytes()
        try:
            quiz = json.loads(raw.decode("utf-8"))
        except Exception as e:
            errs.append(f"{path.relative_to(ROOT)}: invalid JSON ({e})")
            continue
        if not isinstance(quiz, dict):
            errs.append(f"{path.relative_to(ROOT)}: top level must be an object")
            continue
        errs.extend(validate_quiz(quiz, path))
        files.append((path, raw, quiz))

    seen = {}
    for path, _, quiz in files:
        qid = quiz.get("id")
        if qid in seen:
            errs.append(f"{path.relative_to(ROOT)}: duplicate id '{qid}' "
                        f"(also in {seen[qid].relative_to(ROOT)})")
        else:
            seen[qid] = path
    return files, errs


# -------------------------------------------------------------------------- build

def build_documents(files: list) -> tuple:
    """Builds (manifest_dict, legacy_bundle_dict). Deterministic: sorted by quiz id."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    ordered = sorted(files, key=lambda f: f[2]["id"])

    manifest_quizzes = []
    legacy_quizzes = []
    for path, raw, quiz in ordered:
        rel = path.relative_to(ROOT).as_posix()
        questions = quiz["questions"]
        manifest_quizzes.append({
            "id": quiz["id"],
            "title": quiz["title"],
            "category": quiz["category"],
            "difficulty": quiz["difficulty"],
            "author": quiz.get("author", "kvizo-community"),
            "questions_count": len(questions),
            "file": rel,
            "sha256": hashlib.sha256(raw).hexdigest(),
        })
        legacy_quizzes.append({
            "id": quiz["id"],
            "title": quiz["title"],
            "category": quiz["category"],
            "difficulty": quiz["difficulty"],
            "author": quiz.get("author", "kvizo-community"),
            "created_at": quiz.get("created_at", now),
            "questions": questions,
        })

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "key_id": KEY_ID,
        "issued_at": now,
        "count": len(manifest_quizzes),
        "quizzes": manifest_quizzes,
    }
    legacy = {
        "schema_version": LEGACY_SCHEMA_VERSION,
        "key_id": KEY_ID,
        "issued_at": now,
        "quizzes": legacy_quizzes,
    }
    return manifest, legacy


def dump_bytes(obj) -> bytes:
    return (json.dumps(obj, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def sign(key: Ed25519PrivateKey, data: bytes) -> str:
    return base64.b64encode(key.sign(data)).decode("ascii")


def write_pair(name: str, data: bytes, signature: str) -> None:
    """Writes <name> + <name>.sig. These are the exact bytes clients download."""
    (ROOT / name).write_bytes(data)
    (ROOT / (name + ".sig")).write_text(signature + "\n")


def verify_manifest_chain() -> list:
    """Every quiz file must be in manifest.json with a matching sha256, and every
    manifest entry must still exist. Catches "quiz edited/added but build not re-run"."""
    errs = []
    if not MANIFEST.exists():
        return ["manifest.json is missing"]
    try:
        manifest = json.loads(MANIFEST.read_text())
    except Exception as e:
        return [f"manifest.json is not valid JSON ({e})"]
    entries = {e["id"]: e for e in manifest.get("quizzes", [])}

    files, ferrs = collect_quizzes()
    errs.extend(ferrs)
    on_disk = set()
    for path, raw, quiz in files:
        qid = quiz["id"]
        on_disk.add(qid)
        rel = path.relative_to(ROOT).as_posix()
        entry = entries.get(qid)
        if entry is None:
            errs.append(f"{qid}: missing from manifest.json - run build.py and commit")
            continue
        if entry.get("file") != rel:
            errs.append(f"{qid}: manifest says {entry.get('file')} but file is {rel}")
        if entry.get("sha256") != hashlib.sha256(raw).hexdigest():
            errs.append(f"{qid}: sha256 changed since signing - run build.py and commit")
    for qid in entries:
        if qid not in on_disk:
            errs.append(f"{qid}: listed in manifest.json but the quiz file is gone")
    return errs


def verify_pair(name: str, pub_hex: str) -> list:
    errs = []
    data_f, sig_f = ROOT / name, ROOT / (name + ".sig")
    if not data_f.exists() or not sig_f.exists():
        return [f"{name}: missing data or .sig"]
    try:
        sig = base64.b64decode(sig_f.read_text().strip(), validate=True)
    except Exception as e:
        return [f"{name}.sig: signature is not base64 text ({e})"]
    try:
        Ed25519PublicKey.from_public_bytes(binascii.unhexlify(pub_hex)).verify(sig, data_f.read_bytes())
    except Exception:
        errs.append(f"{name}.sig: signature does NOT verify over {name}")
    return errs


# --------------------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser(description="Kvizo community quiz builder/signer")
    ap.add_argument("--check", action="store_true", help="validate quizzes only (no key needed)")
    ap.add_argument("--verify-only", action="store_true", help="re-verify existing signatures")
    ap.add_argument("--keygen", action="store_true", help="print a new keypair and exit")
    ap.add_argument("--key-file", help="path to the private key")
    ap.add_argument("--allow-untrusted-key", action="store_true",
                    help="sign with a key the app does NOT trust (testing only)")
    args = ap.parse_args()

    if args.keygen:
        sys.exit(keygen())

    files, errs = collect_quizzes()
    if errs:
        print("VALIDATION FAILED\n" + "\n".join("  - " + e for e in errs))
        return 1
    print(f"validated {len(files)} quizzes OK")

    if args.check:
        return 0

    if args.verify_only:
        pub_hex = PUBKEY_FILE.read_text().strip() if PUBKEY_FILE.exists() else EXPECTED_PUBKEY_HEX
        verrs = verify_pair("manifest.json", pub_hex) + verify_pair("community.json", pub_hex)
        verrs += verify_manifest_chain()
        if verrs:
            print("VERIFY FAILED\n" + "\n".join("  - " + e for e in verrs))
            return 1
        print(f"signatures OK + every quiz matches its manifest hash (key {pub_hex[:16]}...)")
        return 0

    raw_key = read_private_key(args)
    if not raw_key:
        print("ERROR: no private key. Set ED25519_PRIVATE_KEY (CI secret) or pass --key-file.\n"
              "       To validate without signing: python3 build.py --check")
        return 1
    try:
        key = _load_private_key(raw_key)
    except Exception as e:
        print(f"ERROR: could not load private key: {e}")
        return 1

    pub_hex = pubkey_hex(key)
    if pub_hex != EXPECTED_PUBKEY_HEX and not args.allow_untrusted_key:
        print(f"ERROR: this key is NOT the one the app trusts.\n"
              f"  derived public key : {pub_hex}\n"
              f"  app trusts         : {EXPECTED_PUBKEY_HEX}\n"
              f"Signing with it would ship quizzes the app rejects.\n"
              f"Rotate deliberately: update EXPECTED_PUBKEY_HEX here AND CommunityKeys.kt in the app,\n"
              f"or sign the key you actually use with --allow-untrusted-key (testing only).")
        return 1

    manifest, legacy = build_documents(files)
    manifest_bytes = dump_bytes(manifest)
    legacy_bytes = dump_bytes(legacy)

    write_pair("manifest.json", manifest_bytes, sign(key, manifest_bytes))
    write_pair("community.json", legacy_bytes, sign(key, legacy_bytes))
    PUBKEY_FILE.write_text(pub_hex + "\n")

    verrs = verify_pair("manifest.json", pub_hex) + verify_pair("community.json", pub_hex)
    if verrs:
        print("POST-SIGN VERIFY FAILED\n" + "\n".join("  - " + e for e in verrs))
        return 1

    print(f"signed {manifest['count']} quizzes with {pub_hex[:16]}... (key_id={KEY_ID})")
    print("  manifest.json + manifest.json.sig")
    print("  community.json + community.json.sig  (legacy bundle for older installs)")
    return 0


def keygen() -> int:
    key = Ed25519PrivateKey.generate()
    priv = key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    print("Keep the PRIVATE key secret (GitHub secret ED25519_PRIVATE_KEY, or offline).\n")
    print(f"  private (hex)  : {priv.hex()}")
    print(f"  private (b64)  : {base64.b64encode(priv).decode()}")
    print(f"  public  (hex)  : {pubkey_hex(key)}")
    print("\nFor a rotation, update CommunityKeys.kt in the app + EXPECTED_PUBKEY_HEX here,")
    print("ship the app, then start signing with the new key.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
