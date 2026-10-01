#!/usr/bin/env python3
"""Publish a folder or a single file to chorus.host. Python 3.8+, standard library only.

    curl -fsSLO https://chorus.host/publish.py   # download once
    python3 publish.py ./dist                    # a folder
    python3 publish.py report.html               # one file (an .html file is served as index.html)
    python3 publish.py ./dist my-site            # pick the subdomain: my-site.chorus.host

Without an API key the site is anonymous: it lasts 24 hours and the output
includes a claim URL the user can open to keep it. With an API key the site is
permanent. The key is read from CHORUS_API_KEY or BEACON_API_KEY, else from
~/.config/beacon/config.json ({"apiKey": "chk_..."}, the file `beacon login`
writes).

Never uploaded from a folder: .git and other version-control folders,
node_modules, virtualenvs, .beacon, anything matched by the folder's
.gitignore or .beaconignore, and files that usually hold secrets (.env and
.env.*, .npmrc, .pypirc, .netrc, SSH keys, *.pem, *.key, *.p12, *.pfx). Each
skipped path is listed on stderr and in the "skipped" output field.

Publishing the same path again from the same directory updates the same site.
The slug and claim token are kept per published path in ./.beacon/publish.json
(git-ignored through ./.beacon/.gitignore), so two different files published
from one folder get two different sites. Use --no-save to skip that.

Set CHORUS_CLIENT=<harness>/<version> (e.g. claude-code/2.0) to identify your
agent; it is sent as the X-Chorus-Client header.

Prints one JSON object on stdout (url, slug, claimUrl, ...) and a short
summary on stderr.
"""

import argparse
import fnmatch
import hashlib
import json
import math
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.request
import uuid

VERSION = "1.1.0"
DEFAULT_API_URL = "https://chorus.host"
DOCS_URL = "https://chorus.host/skill.md"
STATE_FILE = os.path.join(".beacon", "publish.json")
PART_SIZE = 8 * 1024 * 1024  # the server presigns multipart uploads in 8 MiB parts
HASH_CHUNK = 1024 * 1024

# Never published from a folder: version control, dependencies, local state, and
# files that usually hold secrets. The server refuses the secret names too.
SKIP_DIRS = {".git", ".hg", ".svn", "node_modules", ".beacon", "__pycache__", ".venv", "venv"}
SKIP_FILES = {".DS_Store", "Thumbs.db", "desktop.ini"}
SECRET_FILES = {".env", ".npmrc", ".pypirc", ".netrc", ".pgpass", ".git-credentials",
                "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519"}
SECRET_SUFFIXES = (".pem", ".key", ".p12", ".pfx")
IGNORE_FILES = (".gitignore", ".beaconignore")

# Deterministic types for common web files (mimetypes differs across systems).
# Text types carry a charset, matching what the beacon CLI sends.
WEB_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".htm": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".json": "application/json",
    ".map": "application/json",
    ".webmanifest": "application/manifest+json",
    ".txt": "text/plain; charset=utf-8",
    ".md": "text/markdown; charset=utf-8",
    ".csv": "text/csv; charset=utf-8",
    ".xml": "text/xml; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".avif": "image/avif",
    ".ico": "image/x-icon",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
    ".otf": "font/otf",
    ".wasm": "application/wasm",
    ".pdf": "application/pdf",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mp3": "audio/mpeg",
}


class PublishError(Exception):
    pass


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def content_type(name):
    ext = os.path.splitext(name)[1].lower()
    if ext in WEB_TYPES:
        return WEB_TYPES[ext]
    guessed = mimetypes.guess_type(name)[0]
    if not guessed:
        return "application/octet-stream"
    if guessed.startswith("text/"):
        return guessed + "; charset=utf-8"
    return guessed


def is_secret(name):
    lower = name.lower()
    return lower in SECRET_FILES or lower.startswith(".env.") or lower.endswith(SECRET_SUFFIXES)


# ── .gitignore / .beaconignore (the common subset of the syntax) ──
# Supported: comments, blank lines, "!" negation, trailing "/" (directories
# only), patterns with a "/" (anchored at the folder root) and patterns without
# one (matched against the name at any depth), and * ? [] ** wildcards. Only
# the ignore files at the root of the published folder are read, as with the
# beacon CLI.

def load_ignore_rules(root):
    rules = []
    for name in IGNORE_FILES:
        try:
            with open(os.path.join(root, name), encoding="utf-8", errors="replace") as f:
                lines = f.read().splitlines()
        except OSError:
            continue
        for line in lines:
            line = line.rstrip()
            if not line or line.startswith("#"):
                continue
            negate = line.startswith("!")
            if negate:
                line = line[1:]
            if line.startswith("\\"):
                line = line[1:]
            dir_only = line.endswith("/")
            line = line.rstrip("/")
            anchored = "/" in line
            line = line.lstrip("/")
            if line:
                rules.append((negate, dir_only, anchored, line))
    return rules


def is_ignored(rules, rel, is_dir):
    base = rel.rsplit("/", 1)[-1]
    ignored = False
    for negate, dir_only, anchored, pattern in rules:
        if dir_only and not is_dir:
            continue
        if anchored:
            hit = fnmatch.fnmatchcase(rel, pattern) or (
                pattern.startswith("**/") and fnmatch.fnmatchcase(rel, pattern[3:]))
        else:
            hit = fnmatch.fnmatchcase(base, pattern)
        if hit:
            ignored = not negate
    return ignored


def collect(source):
    """Return (entries, skipped). Each entry is (local_path, remote_path)."""
    if os.path.isfile(source):
        name = os.path.basename(source)
        if is_secret(name):
            raise PublishError("refusing to publish %s: it looks like a secrets file" % source)
        remote = "index.html" if name.lower().endswith((".html", ".htm")) else name
        return [(source, remote)], []
    if not os.path.isdir(source):
        raise PublishError("no such file or directory: %s" % source)
    rules = load_ignore_rules(source)
    entries, skipped = [], []
    for current, dirs, names in os.walk(source):
        kept = []
        for d in sorted(dirs):
            rel = os.path.relpath(os.path.join(current, d), source).replace(os.sep, "/")
            if d in SKIP_DIRS or is_ignored(rules, rel, True):
                skipped.append(rel + "/")
            else:
                kept.append(d)
        dirs[:] = kept
        for name in sorted(names):
            full = os.path.join(current, name)
            rel = os.path.relpath(full, source).replace(os.sep, "/")
            if name in SKIP_FILES or name in IGNORE_FILES:
                continue
            if is_secret(name):
                skipped.append(rel + " (looks like a secret)")
                continue
            if is_ignored(rules, rel, False) or not os.path.isfile(full):
                skipped.append(rel)
                continue
            entries.append((full, rel))
    return entries, skipped


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(HASH_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(entries):
    files, local = [], {}
    for path, remote in entries:
        ctype = content_type(remote)
        files.append({
            # The server percent-decodes manifest paths, so a literal "%" is sent as %25.
            # uploads.pending comes back decoded, i.e. equal to remote.
            "path": remote.replace("%", "%25"),
            "size": os.path.getsize(path),
            "contentType": ctype,
            "hash": "sha256:" + sha256_file(path),
        })
        local[remote] = (path, ctype, files[-1]["size"])
    return files, local


def config_api_key():
    cfg = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"), "beacon", "config.json")
    try:
        with open(cfg) as f:
            data = json.load(f)
    except (OSError, ValueError):
        return ""
    key = data.get("apiKey", "") if isinstance(data, dict) else ""
    return key if isinstance(key, str) else ""


class Client:
    def __init__(self, base, api_key):
        self.base = base.rstrip("/")
        self.api_key = api_key

    def headers(self, claim_token="", extra=None):
        h = {
            "Accept": "application/json",
            "User-Agent": "chorus-publish.py/%s (Python %d.%d)" % (VERSION, sys.version_info[0], sys.version_info[1]),
            "X-Chorus-Client": os.environ.get("CHORUS_CLIENT") or "publish.py/" + VERSION,
        }
        if self.api_key:
            h["Authorization"] = "Bearer " + self.api_key
        if claim_token:
            h["X-Claim-Token"] = claim_token
        h.update(extra or {})
        return h

    def call(self, method, path, body=None, claim_token="", extra=None, retries=0):
        url = path if path.startswith("http") else self.base + path
        data = json.dumps(body).encode() if body is not None else None
        headers = self.headers(claim_token, extra)
        if data is not None:
            headers["Content-Type"] = "application/json"
        for attempt in range(retries + 1):
            req = urllib.request.Request(url, data=data, method=method, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=60) as res:
                    raw = res.read()
                    return res.status, parse_json(raw)
            except urllib.error.HTTPError as e:
                if e.code in (502, 503, 504) and attempt < retries:
                    time.sleep(1 + attempt)
                    continue
                return e.code, parse_json(e.read())
            except urllib.error.URLError as e:
                if attempt < retries:
                    time.sleep(1 + attempt)
                    continue
                raise PublishError("cannot reach %s: %s" % (self.base, e.reason)) from None
        raise PublishError("unreachable")


def parse_json(raw):
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except ValueError:
        return {"error": raw.decode("utf-8", "replace")[:500]}


def error_text(status, res):
    msg = res.get("error", res) if isinstance(res, dict) else res
    text = "%s (HTTP %s)" % (msg, status)
    if status == 429:
        text += ". Anonymous publishing is rate limited per IP; set CHORUS_API_KEY for a higher limit"
    return text


def put_bytes(url, body, ctype, length):
    """PUT to a presigned URL. Returns the response ETag."""
    for attempt in range(3):
        if hasattr(body, "seek"):
            body.seek(0)
        req = urllib.request.Request(url, data=body, method="PUT", headers={
            "Content-Type": ctype,
            "Content-Length": str(length),
        })
        try:
            with urllib.request.urlopen(req, timeout=300) as res:
                res.read()
                return res.headers.get("ETag", "")
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300]
            if e.code >= 500 and attempt < 2:
                time.sleep(1 + attempt)
                continue
            raise PublishError("upload rejected (HTTP %s): %s" % (e.code, detail)) from None
        except urllib.error.URLError as e:
            if attempt < 2:
                time.sleep(1 + attempt)
                continue
            raise PublishError("upload failed: %s" % e.reason) from None
    raise PublishError("upload failed")


def upload(client, slug, version_id, pending, local, claim_token):
    """Upload pending files. Returns the paths the server gave no URL for."""
    missing_url = []
    for up in pending:
        path = up.get("path", "")
        if path not in local:
            raise PublishError("server asked for an unknown file: %r" % path)
        local_path, ctype, size = local[path]
        if up.get("uploadMethod") == "multipart":
            part_urls = up.get("partUrls") or []
            if not part_urls:
                missing_url.append(path)
                continue
            part_size = PART_SIZE if math.ceil(size / PART_SIZE) == len(part_urls) else -(-size // len(part_urls))
            parts = []
            with open(local_path, "rb") as f:
                for number, part_url in enumerate(part_urls, start=1):
                    chunk = f.read(part_size)
                    etag = put_bytes(part_url, chunk, ctype, len(chunk))
                    parts.append({"partNumber": number, "etag": etag})
                    log("  %s: part %d/%d" % (path, number, len(part_urls)))
            status, res = client.call(
                "POST", "/v1/sites/%s/versions/%s/uploads/complete" % (slug, version_id),
                {"path": path, "uploadId": up.get("uploadId", ""), "parts": parts}, claim_token)
            if status != 200:
                raise PublishError("completing upload of %s failed: %s" % (path, error_text(status, res)))
            continue
        url = up.get("uploadUrl") or ""
        if not url:
            missing_url.append(path)
            continue
        if size == 0:
            put_bytes(url, b"", ctype, 0)
        else:
            with open(local_path, "rb") as f:
                put_bytes(url, f, ctype, size)
    return missing_url


def state_key(source):
    """Key for the saved site: the published path, relative to the current folder when inside it."""
    absolute = os.path.abspath(source)
    try:
        rel = os.path.relpath(absolute, os.getcwd()).replace(os.sep, "/")
    except ValueError:  # different drive on Windows
        return absolute
    return absolute if rel == ".." or rel.startswith("../") else rel


def load_state():
    try:
        with open(STATE_FILE) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(state):
    try:
        os.makedirs(".beacon", exist_ok=True)
        ignore = os.path.join(".beacon", ".gitignore")
        existing = ""
        if os.path.exists(ignore):
            with open(ignore) as f:
                existing = f.read()
        if "publish.json" not in existing.split():
            with open(ignore, "a") as f:
                f.write(("" if existing.endswith("\n") or not existing else "\n") + "publish.json\n")
        tmp = STATE_FILE + ".tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(state, f, indent=2)
            f.write("\n")
        os.replace(tmp, STATE_FILE)
        return True
    except OSError as e:
        log("warning: could not save %s (%s); the next run will create a new site" % (STATE_FILE, e))
        return False


def create_site(client, files, slug):
    body = {"files": files}
    if slug:
        body["slug"] = slug
    key = {"Idempotency-Key": str(uuid.uuid4())}
    return client.call("POST", "/v1/sites", body, extra=key, retries=2)


def publish(args):
    base = (args.api_url or os.environ.get("CHORUS_API_URL") or DEFAULT_API_URL).rstrip("/")
    api_key = ""
    if not args.anonymous:
        api_key = os.environ.get("CHORUS_API_KEY") or os.environ.get("BEACON_API_KEY") or config_api_key()
    wanted_slug = (args.slug_flag or args.slug or "").strip().lower()

    entries, skipped = collect(args.path)
    if not entries:
        raise PublishError("nothing to publish in %s" % args.path)
    files, local = build_manifest(entries)
    total = sum(f["size"] for f in files)
    for path in skipped:
        log("skipped %s" % path)

    if args.dry_run:
        return {"dryRun": True, "apiUrl": base, "authenticated": bool(api_key), "slug": wanted_slug or None,
                "files": files, "skipped": skipped, "totalBytes": total}

    client = Client(base, api_key)
    key = state_key(args.path)
    state = load_state() if not args.no_save else {}
    sites = state.get("sites") if isinstance(state.get("sites"), dict) else {}
    saved = sites.get(key) or {}
    slug = wanted_slug or saved.get("slug", "")
    claim_token = saved.get("claimToken", "") if saved.get("slug") == slug else ""
    notes = []

    # A saved anonymous site plus an API key: claim it first so it stops expiring.
    if slug and api_key and claim_token:
        status, res = client.call("POST", "/v1/sites/%s/claim" % slug, {"claimToken": claim_token})
        if status == 200:
            notes.append("claimed %s with your API key; it no longer expires" % slug)
            claim_token = ""

    res, status, created = None, 0, False
    if slug and (api_key or claim_token):
        status, res = client.call("POST", "/v1/sites/%s/versions" % slug, {"files": files}, claim_token, retries=1)
        if status in (401, 404):
            notes.append("could not update %s (%s); creating a new site" % (slug, error_text(status, res)))
            res = None
    if res is None:
        claim_token = ""  # a new site gets its own token
        status, res = create_site(client, files, slug)
        created = True
        if status == 409 and slug and not wanted_slug:
            notes.append("slug %s is no longer available; publishing under a new slug" % slug)
            status, res = create_site(client, files, "")
    if status != 200:
        raise PublishError("publish failed: %s\nDocs: %s" % (error_text(status, res), DOCS_URL))

    site, version = res.get("site") or {}, res.get("version") or {}
    slug = site.get("slug", slug)
    if res.get("claimToken"):
        claim_token = res["claimToken"]
    uploads = res.get("uploads") or {}
    pending = uploads.get("pending") or []
    already = uploads.get("skipped") or []

    try:
        missing_url = upload(client, slug, version.get("id", ""), pending, local, claim_token)
    except PublishError:
        if created:
            # Don't leave a site that never went live holding its slug.
            client.call("DELETE", "/v1/sites/%s" % slug, claim_token=claim_token)
        raise
    if missing_url:
        notes.append(
            "the server returned no upload URL for %d file(s), so their bytes were not sent. "
            "This is expected from a beacon server in --dev-mode (no object storage); "
            "chorus.host always returns URLs." % len(missing_url))

    finalize_url = version.get("finalizeUrl") or "/v1/sites/%s/versions/%s/finalize" % (slug, version.get("id", ""))
    status, fin = client.call("POST", finalize_url, claim_token=claim_token, retries=1)
    if status == 409 and "not pending" in str(fin.get("error", "")):
        # A retried finalize whose first attempt already went through.
        status, fin = 200, {}
    if status != 200:
        raise PublishError("finalize failed: %s\nDocs: %s" % (error_text(status, fin), DOCS_URL))
    site = fin.get("site") or site
    live = fin.get("version") or {}
    if site.get("ownerId"):
        claim_token = ""  # owned sites are managed with the API key; a claim token no longer applies

    anonymous = bool(site.get("expiresAt")) and not site.get("ownerId")
    out = {
        "url": site.get("url"),
        "slug": slug,
        "anonymous": anonymous,
        "expiresAt": site.get("expiresAt"),
        "versionId": live.get("id") or version.get("id"),
        "status": live.get("status"),
        "created": created,
        "files": len(files),
        "uploaded": len(pending) - len(missing_url),
        "alreadyStored": len(already),
        "totalBytes": total,
    }
    if claim_token:
        out["claimUrl"] = res.get("claimUrl") or "%s/claim/%s#%s" % (base, slug, claim_token)
        out["claimToken"] = claim_token
    if missing_url:
        out["notUploaded"] = missing_url
    if skipped:
        out["skipped"] = skipped
    if notes:
        out["notes"] = notes

    if not args.no_save:
        entry = {"slug": slug}
        if claim_token:
            entry["claimToken"] = claim_token
        sites[key] = entry
        state["sites"] = sites
        if save_state(state):
            out["stateFile"] = STATE_FILE.replace(os.sep, "/")
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="publish.py",
        description="Publish a folder or file to chorus.host and print its URL. "
                    "Standard library only; no install needed.",
        epilog="Environment: CHORUS_API_KEY or BEACON_API_KEY (optional, makes sites permanent; "
               "falls back to ~/.config/beacon/config.json), CHORUS_API_URL (default %s), "
               "CHORUS_CLIENT (your agent, e.g. claude-code/2.0). Docs: %s" % (DEFAULT_API_URL, DOCS_URL),
    )
    parser.add_argument("path", help="folder or file to publish (use . for the current folder)")
    parser.add_argument("slug", nargs="?", default="", help="subdomain to use, e.g. my-site for my-site.chorus.host")
    parser.add_argument("--slug", dest="slug_flag", metavar="SLUG", default="", help="same as the positional slug")
    parser.add_argument("--api-url", default="", help="API base URL (default: $CHORUS_API_URL or %s)" % DEFAULT_API_URL)
    parser.add_argument("--anonymous", action="store_true", help="ignore any API key and publish a 24-hour anonymous site")
    parser.add_argument("--no-save", action="store_true", help="don't read or write ./.beacon/publish.json")
    parser.add_argument("--dry-run", action="store_true", help="print the manifest that would be sent, without any network calls")
    parser.add_argument("--version", action="version", version="%(prog)s " + VERSION)
    args = parser.parse_args(argv)

    try:
        out = publish(args)
    except PublishError as e:
        log("error: %s" % e)
        return 1
    except KeyboardInterrupt:
        return 130

    print(json.dumps(out, indent=2), flush=True)
    if out.get("dryRun"):
        log("dry run: %d file(s), %d bytes, nothing sent" % (len(out["files"]), out["totalBytes"]))
        return 0
    for note in out.get("notes", []):
        log("note: " + note)
    log("Published %d file(s) to %s" % (out["files"], out["url"]))
    if out.get("anonymous"):
        log("Anonymous site: it expires %s. To keep it, open the claimUrl and sign in." % out.get("expiresAt"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
