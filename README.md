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
| `https://kvizo.indevs.in/` | the website (Cloudflare Pages, see Hosting below) |
| `https://kvizo.indevs.in/manifest.json` · `/community.json` | the same signed files, served from the site |
| `https://raw.githubusercontent.com/SirYadav1/kvizo-community/master/community.json` | the app's primary source |
| `https://cdn.jsdelivr.net/gh/SirYadav1/kvizo-community@master/community.json` | free CDN mirror, CORS enabled |

## Hosting

The website is a static bundle served by **Cloudflare Pages** at <https://kvizo.indevs.in>
(project `kvizo-site`, custom domain on the same Cloudflare account). Nothing to run, nothing to
pay: <https://kvizo.indevs.in> is the apex of the `kvizo.indevs.in` zone, which is a Cloudflare
zone, so Cloudflare creates the DNS record and the certificate itself.

````
push to master  ->  deploy-cloudflare.yml: build.py --verify-only  ->  wrangler pages deploy
````

`deploy-cloudflare.yml` assembles the publish directory (only `index.html`, `404.html`, `_headers`,
`assets/`, the signed data files, `categories.json` and `quizzes/` — the tooling and the stale
`docs/` copy stay out of the CDN) and uploads it with `wrangler pages deploy`. Cache rules live in
`_headers`, which the CDN reads from the publish directory; the rules are non-overlapping so each
path gets exactly one `Cache-Control` value.

`404.html` is not optional polish: without a top-level 404 page, Cloudflare Pages assumes the site
is a single-page app and answers **every** unknown path with `index.html` and a 200. With the file
present, a missing quiz answers 404, which is what a client should see.

Two repo secrets hold the credentials:

| Secret | Meaning |
|---|---|
| `CLOUDFLARE_API_TOKEN` | token with **Pages: Edit** (and DNS: Edit if you want the domain managed too) |
| `CLOUDFLARE_ACCOUNT_ID` | the Cloudflare account that owns the `kvizo-site` project |

Deploying by hand works the same way:

```bash
rm -rf public && mkdir -p public
cp index.html 404.html _headers public/ && cp -r assets public/assets
cp manifest.json manifest.json.sig community.json community.json.sig public_key.hex categories.json public/
cp -r quizzes public/quizzes
npx wrangler@4 pages deploy public --project-name=kvizo-site --branch=master
```

## Setup (already done, for the record)

- Repo secret `ED25519_PRIVATE_KEY` = private half of the key whose public half is in
  `public_key.hex` and embedded in the app.
- Changing that key means a **key rotation**: it has to be updated in the app and in
  `EXPECTED_PUBKEY_HEX` in `build.py`, in that order, and shipped.

`server/` (the old Express admin backend) and `worker/` (Cloudflare) are **not** part of this
pipeline and are not needed for it.
