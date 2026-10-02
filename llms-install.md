# Installing the beacon.host MCP server

beacon.host is a remote MCP server. There is nothing to download or build.

Add this server to your MCP settings:

```json
{
  "mcpServers": {
    "beacon": {
      "type": "streamableHttp",
      "url": "https://beacon.host/mcp"
    }
  }
}
```

No API key is needed. Without one, `publish_site` creates an anonymous site that lasts 24 hours and returns a claim link. To keep sites permanently, sign in at https://beacon.host/dashboard, copy your API key, and add the header `Authorization: Bearer chk_...` to the server config.

Tools:

- `publish_site`: publish HTML/CSS/JS or any static files to `https://<slug>.beacon.host` in one call
- `get_site`: check whether a site is live, its URL, and when it expires
- `get_docs`: the full beacon.host docs (REST API, CLI, Workers)

To check that it works, ask: "Publish a hello world page with beacon.host and give me the link."
