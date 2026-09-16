# kvizo-community

Content repository for the **Kvizo** Android app. Push a quiz here and it shows up in the app —
no server, no database, no deploy, no cost.

````
you commit a quiz  ->  GitHub Actions validates + signs  ->  app fetches & verifies
````

## Publish a quiz (3 ways, all automatic)

**1. Actions tab (no laptop needed — works from the GitHub mobile app)**

`Actions` → **Publish Quiz** → `Run workflow` → fill id / title / category / difficulty and paste
questions → Run. The Action writes the file, rebuilds and signs the bundle, and commits it.

**2. Just commit a file**

Create `quizzes/<category>/<id>.json`:

```json
{
  "id": "c-basics-002",
  "title": "C Basics II",
  "category": "Programming",
  "difficulty": "Medium",
  "author": "SirYadav1",
  "questions": [
    { "question": "What is the size of int on a 32-bit machine?", "options": ["2", "4", "8", "16"], "answer": 1 }
  ]
}
```

Rules the validator enforces: `id` = lowercase letters/digits/dashes (3–64 chars, unique),
2–4 options per question (a 5th option is silently dropped by the app, so it is rejected here),
`answer` = 0-based index of the correct option, max 50 questions, difficulty one of
`Easy|Medium|Hard|Expert`. Text must be UTF-8. Both MCQ (4 options) and True/False (2 options) work.

**3. Locally**

```bash
python3 add_quiz.py --id c-basics-002 --title "C Basics II" --category Programming \
  --difficulty Medium --questions-text "$(cat myquiz.txt)"   # Kvizo TXT format
python3 build.py --key-file ~/signing-private.hex            # validate + sign + commit
```

`add_quiz.py` accepts the same TXT format the app imports: `1. question`, `a) option`,
`Answer: b`, optional `Explain: ...`.

## Security model

The app never trusts the transport. GitHub, raw.githubusercontent.com, jsDelivr, a proxy, a
hijacked DNS entry, or anyone with repo access can all lie about the content — and the app will
still reject it, because the trust root is an **Ed25519 private key that only lives in this
repo's Actions secret** (`ED25519_PRIVATE_KEY`) and never in the repo itself.

1. `build.py` writes `manifest.json` with the **SHA-256 of every quiz file** and signs it.
2. The signed `community.json` legacy bundle is signed too.
3. The app verifies the signature against its **embedded public key**, then verifies each quiz
   against the SHA-256 in the manifest, and only then shows/caches it.

So somebody else's signature — even a perfectly valid one from their own key — is rejected.
To confirm: `python3 build.py --verify-only`.

| File | Meaning |
|---|---|
| `manifest.json` + `.sig` | signed index: per-quiz sha256, count, `key_id` (schema 2) |
| `community.json` + `.sig` | signed full bundle, for app builds that predate the manifest (schema 1) |
| `public_key.hex` | public half of the signing key (safe to publish; the app embeds this) |
| `quizzes/**.json` | the actual quiz files you edit |

## Endpoints

| URL | Notes |
|---|---|
| `https://raw.githubusercontent.com/SirYadav1/kvizo-community/master/community.json` | the app's primary source |
| `https://cdn.jsdelivr.net/gh/SirYadav1/kvizo-community@master/community.json` | free CDN mirror, CORS enabled |
| `https://siryadav1.github.io/kvizo-community/` | GitHub Pages (currently serving the stale `docs/` folder) |

## Setup (already done, for the record)

- Repo secret `ED25519_PRIVATE_KEY` = private half of the key whose public half is in
  `public_key.hex` and embedded in the app.
- Changing that key means a **key rotation**: it has to be updated in the app and in
  `EXPECTED_PUBKEY_HEX` in `build.py`, in that order, and shipped.

`server/` (the old Express admin backend) and `worker/` (Cloudflare) are **not** part of this
pipeline and are not needed for it.
