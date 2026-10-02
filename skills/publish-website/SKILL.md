---
name: publish-website
description: >
  Publish websites to a live URL, no signup, or deploy APIs with a free
  account. Turns HTML, a folder, or a single PDF, image or other file into a
  public link that opens in the browser. Use when asked to "publish this",
  "host this", "put this online", "share this HTML file or report as a
  link", "make a website", "give me a link", "get a public URL", "share this
  PDF", "upload this file and give me a link", "share a temporary link that
  expires", "deploy this folder", "password protect this site", or "publish
  to beacon.host". Also use for backend work that static hosts can't do:
  "deploy an API", "add a backend to my site", "receive form submissions",
  "proxy an API with a secret key", "webhook endpoint", "GitHub or Stripe
  webhook receiver", or "deploy this Hono / Workers app". Sites live at
  {slug}.beacon.host; workers run on Cloudflare at
  {slug}.worker.beacon.host. Anonymous sites last 24 hours and can be
  claimed with a free account.
metadata:
  homepage: https://beacon.host
  version: "3.1.0"
---

# beacon.host: publish a website or deploy an API

Publish a file or folder and get back `https://<slug>.beacon.host`. Deploy a JavaScript or TypeScript API to `https://<slug>.worker.beacon.host`. API base URL: `https://beacon.host`.

## When to use

The user wants something online with a link: an HTML page, a static build (`dist/`, `build/`, `out/`, `public/`), a report, dashboard, slide deck, game, PDF or image. Or a temporary preview that expires on its own, or a page behind a password. Or they need a backend a static page can call: an API, a form handler, a GitHub or Stripe webhook receiver, a Hono or Workers app.

If you can't make network requests from where you run (a sandbox without internet), don't guess: tell the user to open https://beacon.host/html-to-url and drop or paste the file there.

## Requirements

`curl` and network access to `beacon.host`. The three-call API for big sites also needs `*.r2.cloudflarestorage.com` (file bytes go straight to storage through presigned URLs). Python 3 or the `beacon` CLI are optional shortcuts.

## Publish a file: one call, no account

```bash
curl -sS https://beacon.host/v1/publish -H 'X-Beacon-Client: claude-code/2.0' -F file=@index.html
```

The response is JSON: `url`, `claimUrl`, `claimToken`, `expiresAt`, and `fileUrl` (the direct link when you sent one file). A single `.html` file becomes the home page whatever it's called. More files: repeat `-F file=@path` (use `-F "file=@app.js;filename=js/app.js"` to keep a folder path), or zip the folder and send `-F archive=@site.zip`. Add `-F slug=my-site` to pick the subdomain, `-H 'Accept: text/plain'` to get only the link. Up to 4 MB of files per call without an API key, 10 MB with one; bigger sites use the three calls below.

Private link? Add `-F username=client -F password=...` and the site is behind a browser login prompt before it goes live, also without an account. Give the user the URL, username and password, and send the password separately from the link.

Shorter life? Add `-F expires=2h` (`90m`, `2h`, `7d` or RFC 3339). Without an account a site can only expire sooner than 24 hours.

## Big files and folders: three calls

Create the site with a file list, upload each file, go live. Files up to 250 MB each without an account.

```bash
F=index.html                                        # file to publish
CLIENT='X-Beacon-Client: claude-code/2.0'           # your harness/version, see below
HASH=$( (sha256sum "$F" 2>/dev/null || shasum -a 256 "$F") | cut -d' ' -f1)
SIZE=$(wc -c < "$F" | tr -d ' ')
curl -s https://beacon.host/v1/sites -H "$CLIENT" -H 'Content-Type: application/json' \
  -d "{\"files\":[{\"path\":\"index.html\",\"size\":$SIZE,\"contentType\":\"text/html; charset=utf-8\",\"hash\":\"sha256:$HASH\"}]}" > site.json
curl -s -X PUT "$(jq -r '.uploads.pending[0].uploadUrl' site.json)" \
  -H 'Content-Type: text/html; charset=utf-8' --data-binary @"$F"
curl -s -X POST "https://beacon.host$(jq -r .version.finalizeUrl site.json)" \
  -H "$CLIENT" -H "X-Claim-Token: $(jq -r .claimToken site.json)"
jq -r '.site.url, .claimUrl' site.json
```

No `jq`? Run the calls one at a time and copy the values out of the JSON yourself.

Rules:
- `hash` is `sha256:` plus 64 lowercase hex characters of the file bytes. `size` is in bytes.
- PUT each file in `uploads.pending` to its `uploadUrl` with exactly the `Content-Type` you declared. Files the server already has come back in `uploads.skipped`; don't upload those.
- Finalize an anonymous site with `X-Claim-Token: <claimToken>`. Without it you get `401`.
- More files: list them all in `files` (nested paths like `js/app.js` are fine) and PUT each one. `/` serves `index.html`.

## Publish a folder

```bash
curl -fsSLO https://beacon.host/publish.py      # download once
python3 publish.py ./dist                       # folder or single file
python3 publish.py ./dist my-slug               # pick the subdomain
```

Standard-library Python. Prints JSON with `url`, `slug`, `expiresAt`, `claimUrl` and, for one file, `fileUrl`, and saves the slug and claim token in `.beacon/` so running it again updates the same site. `--expires 2h` makes the link expire sooner. Set `BEACON_CLIENT=<harness>/<version>` to identify yourself.

Or the CLI (sites and workers): `curl -fsSL https://beacon.host/install.sh -o install-beacon.sh && sh install-beacon.sh`, then `beacon deploy --pretty`. Windows: `iwr https://beacon.host/install.ps1 -useb | iex`.

## Share a single file (PDF, image, HTML)

```bash
curl -sS https://beacon.host/v1/upload -F file=@report.pdf     # prints https://<slug>.beacon.host/report.pdf
```

Files keep their content type, so HTML renders and PDFs and images open in the browser instead of downloading. Give the user the direct file link (`fileUrl`); chat apps such as Slack preview images from it. The site root shows a small viewer page. `/v1/upload` prints just the link and puts the claim details in the `X-Claim-Token`, `X-Claim-Url` and `X-Expires-At` response headers; `/v1/publish` returns them as JSON.

## What to tell the user

1. Put the site URL on a line by itself, with nothing else on that line.
2. If the site is anonymous, say it expires in 24 hours, and give them the `claimUrl` so they can keep it. Copy it exactly as returned, character for character. Don't shorten, wrap or reformat it; the code after `#` is 47 characters and the link breaks if any are lost.
3. Never show an API key in the chat. The `claimUrl` already carries the claim code, so don't paste the `claimToken` separately.
4. If they ask how keeping the site works, link https://beacon.host/guides/host-static-site-no-signup#claim-the-site-later

```
Your site is live:

https://quiet-river-42.beacon.host

It will be deleted in 24 hours. To keep it, open this link and sign in with your email:
<claimUrl, exactly as returned>
```

Keep the `claimToken` (`ctk_...`) with the project. It is the only way to update, delete or claim an anonymous site.

## Sign up or sign in (email code)

There's no password. Signing up and signing in are the same two calls:

```bash
curl -s https://beacon.host/v1/auth/send-otp -H "$CLIENT" -H 'Content-Type: application/json' \
  -d '{"email":"user@example.com"}'
```

Ask the user: "I sent a 6-digit code to user@example.com. What is it?" Then:

```bash
curl -s https://beacon.host/v1/auth/verify-otp -H "$CLIENT" -H 'Content-Type: application/json' \
  -d '{"email":"user@example.com","code":"123456"}'
# -> {"apiKey":"chk_...","account":{"id":"...","email":"..."}}
```

Codes expire after 10 minutes, and 5 wrong tries cancel a code.

## Save the API key yourself

Write it to `~/.config/beacon/config.json` as `{"apiKey":"chk_..."}` and `chmod 600` the file. `publish.py` and the `beacon` CLI read it from there (or from the `BEACON_API_KEY` environment variable). Do this yourself; don't ask the user to, and don't show the key in the chat.

Send it as `Authorization: Bearer chk_...`. With a key, sites last until you delete them or until an `expiresAt` you set, workers are available, `GET /v1/sites` lists sites, and `GET /v1/account` shows the account and its usage.

Move an anonymous site into the account:

```
POST /v1/sites/<slug>/claim
Authorization: Bearer chk_...
{"claimToken": "ctk_..."}
```

## Identify your client

Send `X-Beacon-Client: <harness>/<version>` on every request, for example `claude-code/2.0`, `cursor/1.7`, `codex/0.40`, `hermes/1.2` or `my-script/1`. It's optional. It tells us which agents use beacon.host so we can fix what breaks for them.

## Update a site

```
POST /v1/sites/<slug>/versions          {"files": [...same manifest format...]}
X-Claim-Token: ctk_...   (anonymous site)   or   Authorization: Bearer chk_...   (owned site)
```

Upload the `pending` files, then POST the returned `finalizeUrl` with the same header. `POST /v1/sites` with a slug that exists returns `409`; use the versions endpoint instead. `GET /v1/sites/<slug>` (same headers) shows the site and its live version. Shortcut: `curl -sS "https://beacon.host/v1/publish?slug=<slug>" -H 'X-Claim-Token: ctk_...' -F file=@index.html` sends a new version in one call.

## Temporary links

Anonymous sites last 24 hours from the first publish and updates don't reset the clock; they can be made to expire sooner (`expires` on `/v1/publish`, `--expires` on publish.py, or `PATCH /v1/sites/<slug>/metadata` `{"expiresAt":"<RFC 3339>"}`), to any time up to 24 hours after the first publish, never later. With an API key any future time works, or `null` for none. At expiry the URL returns 404 and the site is deleted. More: https://beacon.host/guides/temporary-website-hosting

## Workers (API backends)

Serverless JavaScript/TypeScript (Hono works) on Cloudflare at `https://<slug>.worker.beacon.host`. Needs a beacon.host API key, not a Cloudflare account, and the URL stays up until you delete it. Sign-in works without a browser: POST `/v1/auth/send-otp` with the user's email, ask the user for the 6-digit code, then POST `/v1/auth/verify-otp`. Hono: `beacon init my-api --template hono && cd my-api && npm install && beacon deploy --pretty`. Replace `chk_...` with the key:

```bash
curl -s -X POST https://beacon.host/v1/workers -H "Authorization: Bearer chk_..." \
  -H 'Content-Type: application/json' -d '{"slug":"my-api"}'
curl -s -X POST https://beacon.host/v1/workers/my-api/deploy -H "Authorization: Bearer chk_..." \
  -F 'metadata={"entryPoint":"index.js","compatibilityDate":"2024-09-23","compatibilityFlags":["nodejs_compat"]}' \
  -F 'file=@index.js'
```

Upload a JavaScript ES module (`export default { fetch }`); compile TypeScript to JavaScript first. `beacon deploy` bundles npm imports with esbuild. Secrets: `PUT /v1/workers/<slug>/secrets/<NAME>` with `{"value":"..."}`; set them after the first deploy and they stay set across redeploys and rollbacks. Scheduled (cron) runs are not available yet. Workers have no built-in database or KV; keep state in an outside service and put its key in a secret. Form submissions are received and forwarded (email, a spreadsheet, your database), not stored. A site and a worker can't share a slug, so pair them with two: `my-app.beacon.host` (frontend) calls `my-app-api.worker.beacon.host` (API).

Webhook receiver: read the raw body with `await request.text()`, verify the sender's HMAC signature against a Worker secret, return 2xx within 10 s (GitHub does not retry), forward elsewhere for storage. Walkthrough with GitHub and Stripe code: https://beacon.host/guides/deploy-webhook-from-agent. Workers page: https://beacon.host/workers. Full worker reference: https://beacon.host/llms-full.txt

## Other site operations

| Do this | Call |
|---|---|
| Password-protect (anonymous sites too) | `PUT /v1/sites/<slug>/password` `{"username":"u","password":"p"}` (max 72 chars) |
| Remove password | `DELETE /v1/sites/<slug>/password` |
| Title / description / OG image / expiry | `PATCH /v1/sites/<slug>/metadata` `{"title":"...","description":"...","ogImagePath":"og.png","expiresAt":"..."}` |
| List versions | `GET /v1/sites/<slug>/versions` |
| Roll back | `POST /v1/sites/<slug>/versions/<versionId>/rollback` |
| Delete | `DELETE /v1/sites/<slug>` |
| Expired upload URLs (after 1 hour) | `POST /v1/sites/<slug>/versions/<versionId>/uploads/refresh` `{"paths":["index.html"]}` |

All of these take `X-Claim-Token` (anonymous) or `Authorization: Bearer` (owned).

## Errors

| Status | Meaning | Fix |
|---|---|---|
| 401 on finalize or update | Missing credentials | Send `X-Claim-Token` from the create response, or your Bearer key for owned sites |
| 404 on a site | Not your site, wrong key, or expired | Check `GET /v1/sites` |
| 405 | Wrong method | The `Allow` header lists the right one |
| 409 on create | Slug taken | Use another slug, or `POST /v1/sites/<slug>/versions` if it's yours |
| 400 on finalize | `file "x": not uploaded`, or size/hash mismatch | PUT the named file to its `uploadUrl` (the exact bytes you hashed), then finalize again |
| 409 on finalize | `version is not pending` | Already live; create a new version to change it |
| 429 | Rate limit | Anonymous: 5 publishes an hour per IP (new sites and updates). Sign in for 60 an hour |

Errors are JSON: `{"error":"..."}`, often with a `hint` and a `docs` link.

## Limits

Anonymous: sites last 24 hours, 250 MB per file, 5 publishes an hour. Signed in: permanent sites, 5 GB per file, 60 publishes an hour. Both: 10 GB per site and 10,000 files per version. Workers: 3 MB compressed bundle, 100 files, 20 deploys an hour. `GET /v1/limits` returns the current numbers.

If these docs and the live API disagree, trust the API: its error messages say what to fix.

## MCP server

Clients that speak MCP can publish without curl. The remote server is `https://beacon.host/mcp` (Streamable HTTP, no OAuth) with three tools: `publish_site` (send file contents, get the URL and claim link back), `get_site` and `get_docs`. Anonymous by default; send `Authorization: Bearer chk_...` to publish into an account.

```bash
claude mcp add --transport http beacon https://beacon.host/mcp
```

Setup for Codex, Cursor, VS Code, claude.ai and ChatGPT: https://beacon.host/mcp. `publish_site` takes up to 4 MB of file content per call without an API key and 10 MB with one, and optional `password` and `expires_at`; use the HTTP API above for anything bigger.

## Keep this skill

Install it for future sessions: `npx skills add beacon-host/skill -g`. Or save this file as `~/.claude/skills/publish-website/SKILL.md` (Claude Code) or `~/.agents/skills/publish-website/SKILL.md`.

## More

- Full API reference (every endpoint, workers, multipart uploads): https://beacon.host/llms-full.txt
- OpenAPI 3.1: https://beacon.host/openapi.json
- Human docs: https://beacon.host/docs
- Workers (APIs and webhooks): https://beacon.host/workers
- Guides: https://beacon.host/guides
- Compared with here.now, Netlify Drop and Vercel: https://beacon.host/vs/here-now
