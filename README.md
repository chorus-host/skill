# publish-website: an agent skill that deploys a website and returns a live URL

Ask your coding agent to "publish this", "host this" or "put this online" and it uploads the folder to [beacon.host](https://beacon.host) and hands back `https://<slug>.beacon.host`. No account needed. Works in Claude Code, Codex, Cursor, Gemini CLI, OpenCode and any agent that reads SKILL.md.

What it hosts:

- HTML reports, dashboards and mini apps, plus whole static sites, PDFs and images, at `https://<slug>.beacon.host`
- APIs and webhook receivers as Cloudflare Workers at `https://<slug>.worker.beacon.host` (free account, no Cloudflare account)

What your agent returns:

```text
Your site is live:

https://quiet-river-42.beacon.host

It will be deleted in 24 hours. To keep it, open this link and sign in with your email:
https://beacon.host/claim/quiet-river-42#ctk_...
```

An anonymous site lasts 24 hours; the claim link keeps it, and signing in takes an emailed code, no password. How claiming works: https://beacon.host/guides/host-static-site-no-signup#claim-the-site-later

No shell in your agent? Use the MCP server instead: `claude mcp add --transport http beacon https://beacon.host/mcp` (setup for other clients: https://beacon.host/mcp).

## Install

Any agent that reads Agent Skills (Claude Code, Codex, Cursor, Gemini CLI, OpenCode, and others):

```bash
npx skills add beacon-host/skill -g
```

Claude Code plugin:

```text
/plugin marketplace add beacon-host/skill
/plugin install beacon-host@beacon-host
```

Gemini CLI extension:

```bash
gemini extensions install https://github.com/beacon-host/skill
```

Codex plugin:

```bash
codex plugin marketplace add beacon-host/skill
codex plugin add beacon-host@beacon-host
```

Cursor reads `.cursor-plugin/plugin.json` from this repo.

## MCP server

beacon.host also runs a remote MCP server at `https://beacon.host/mcp` (Streamable HTTP, no OAuth) with `publish_site`, `get_site`, and `get_docs` tools. The Gemini CLI extension connects to it automatically. In Claude Code:

```bash
claude mcp add --transport http beacon https://beacon.host/mcp
```

## Publish without an agent

`scripts/publish.py` publishes a folder or a single file. It needs Python 3.8+ and nothing else.

```bash
python3 scripts/publish.py ./dist             # a folder
python3 scripts/publish.py report.html        # one HTML file, served as index.html
python3 scripts/publish.py ./dist my-site     # choose the subdomain
python3 scripts/publish.py --help
```

It prints JSON with `url`, `slug`, `expiresAt`, and, for anonymous sites, `claimUrl`. Running it again on the same path updates the same site. The slug and claim token are saved in `./.beacon/publish.json`, which is git-ignored.

To make sites permanent, set `BEACON_API_KEY` to an API key, or save it as `{"apiKey": "chk_..."}` in `~/.config/beacon/config.json`, the file `beacon login` writes. Keys come from `POST https://beacon.host/v1/auth/verify-otp` or `beacon login`.

The script never uploads `.git`, `node_modules`, virtualenvs, files matched by the folder's `.gitignore` or `.beaconignore`, or files that usually hold secrets (`.env` and `.env.*`, `.npmrc`, `.netrc`, SSH keys, `*.pem`, `*.key`). It is the same script beacon.host serves at https://beacon.host/publish.py.

For workers and larger projects, use the `beacon` CLI:

```bash
curl -fsSL https://beacon.host/install.sh -o install-beacon.sh && sh install-beacon.sh
beacon deploy --pretty
```

## Contents

| Path | What it is |
|---|---|
| `skills/publish-website/SKILL.md` | The skill. It's the same file beacon.host serves at https://beacon.host/skill.md |
| `scripts/publish.py` | A zero-dependency publisher (Python standard library only) |
| `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` | Claude Code plugin and marketplace |
| `.codex-plugin/plugin.json` | Codex plugin |
| `.cursor-plugin/plugin.json` | Cursor plugin |
| `gemini-extension.json` | Gemini CLI extension. The skill is discovered from `skills/` |
| `assets/logo.svg` | Logo |

## Privacy and data

Everything this plugin sends goes to beacon.host or its file storage:

- API calls, including the MCP server at `https://beacon.host/mcp`, go to `https://beacon.host`.
- File contents are uploaded straight to Cloudflare R2 (`*.r2.cloudflarestorage.com`) through presigned URLs that the beacon.host API returns.
- Signing in sends your email address to beacon.host, which emails you a 6-digit code.
- `scripts/publish.py` reads an API key from `BEACON_API_KEY` or `~/.config/beacon/config.json` and sends it only to the beacon.host API (or to the URL you set in `BEACON_API_URL`).
- The skill may download `publish.py` and the `beacon` CLI installer from beacon.host.

Anonymous sites are deleted after 24 hours. Sites and workers in an account stay until you delete them.

- Privacy policy: https://beacon.host/privacy
- Terms: https://beacon.host/terms
- Support: support@beacon.host

## Docs

- Agent reference: https://beacon.host/skill.md
- Human docs: https://beacon.host/docs
- Guides: https://beacon.host/guides

## License

MIT. See [LICENSE](LICENSE).
