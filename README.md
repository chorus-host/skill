# chorus.host skill

An agent skill and plugin for [chorus.host](https://chorus.host). It lets your coding agent:

- publish HTML files, static sites, reports, and dashboards to `https://<slug>.chorus.host`
- deploy APIs and webhooks as Cloudflare Workers at `https://<slug>.worker.chorus.host`

You don't need an account. An anonymous site lasts 24 hours and comes with a claim link; sign in with an emailed code to keep it.

Once it's installed, ask your agent to "publish this folder", "put this report online", or "deploy this Hono app".

## Install

Any agent that reads Agent Skills (Claude Code, Codex, Cursor, Gemini CLI, OpenCode, and others):

```bash
npx skills add chorus-host/skill -g
```

Claude Code plugin:

```text
/plugin marketplace add chorus-host/skill
/plugin install chorus-host@chorus-host
```

Gemini CLI extension:

```bash
gemini extensions install https://github.com/chorus-host/skill
```

Codex plugin:

```bash
codex plugin marketplace add chorus-host/skill
codex plugin add chorus-host@chorus-host
```

Cursor reads `.cursor-plugin/plugin.json` from this repo.

## MCP server

chorus.host also runs a remote MCP server at `https://chorus.host/mcp` (Streamable HTTP, no OAuth) with `publish_site`, `get_site`, and `get_docs` tools. The Gemini CLI extension connects to it automatically. In Claude Code:

```bash
claude mcp add --transport http chorus https://chorus.host/mcp
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

To make sites permanent, set `CHORUS_API_KEY` (or `BEACON_API_KEY`) to an API key, or save it as `{"apiKey": "chk_..."}` in `~/.config/beacon/config.json`, the file `beacon login` writes. Keys come from `POST https://chorus.host/v1/auth/verify-otp` or `beacon login`.

The script never uploads `.git`, `node_modules`, virtualenvs, files matched by the folder's `.gitignore` or `.beaconignore`, or files that usually hold secrets (`.env` and `.env.*`, `.npmrc`, `.netrc`, SSH keys, `*.pem`, `*.key`). It is the same script chorus.host serves at https://chorus.host/publish.py.

For workers and larger projects, use the `beacon` CLI:

```bash
curl -fsSL https://chorus.host/install.sh -o install-beacon.sh && sh install-beacon.sh
beacon deploy --pretty
```

## Contents

| Path | What it is |
|---|---|
| `skills/publish-website/SKILL.md` | The skill. It's the same file chorus.host serves at https://chorus.host/skill.md |
| `scripts/publish.py` | A zero-dependency publisher (Python standard library only) |
| `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` | Claude Code plugin and marketplace |
| `.codex-plugin/plugin.json` | Codex plugin |
| `.cursor-plugin/plugin.json` | Cursor plugin |
| `gemini-extension.json` | Gemini CLI extension. The skill is discovered from `skills/` |
| `assets/logo.svg` | Logo |

## Privacy and data

Everything this plugin sends goes to chorus.host or its file storage:

- API calls, including the MCP server at `https://chorus.host/mcp`, go to `https://chorus.host`.
- File contents are uploaded straight to Cloudflare R2 (`*.r2.cloudflarestorage.com`) through presigned URLs that the chorus.host API returns.
- Signing in sends your email address to chorus.host, which emails you a 6-digit code.
- `scripts/publish.py` reads an API key from `CHORUS_API_KEY`, `BEACON_API_KEY` or `~/.config/beacon/config.json` and sends it only to the chorus.host API (or to the URL you set in `CHORUS_API_URL`).
- The skill may download `publish.py` and the `beacon` CLI installer from chorus.host.

Anonymous sites are deleted after 24 hours. Sites and workers in an account stay until you delete them.

- Privacy policy: https://chorus.host/privacy
- Terms: https://chorus.host/terms
- Support: support@chorus.host

## Docs

- Agent reference: https://chorus.host/skill.md
- Human docs: https://chorus.host/docs
- Guides: https://chorus.host/guides

## License

MIT. See [LICENSE](LICENSE).
