#!/usr/bin/env python3
"""Parse Proxyman raw exports into structured JSON for APIVault viewer."""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


def slugify(name: str) -> str:
    """Convert a screen name to a URL-friendly slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


def discover_pairs(folder: Path) -> list[dict]:
    """Scan folder for [ID] Request/Response .txt pairs, matched by bracket ID."""
    files = {}
    pattern = re.compile(r"^\[(\d+)\]\s+(Request|Response)\s+-\s+(.+)\.txt$")

    for entry in sorted(folder.iterdir()):
        if not entry.is_file():
            continue
        m = pattern.match(entry.name)
        if not m:
            continue
        call_id, kind, _ = m.groups()
        files.setdefault(call_id, {})[kind.lower()] = entry

    pairs = []
    for call_id in sorted(files, key=int):
        pair = files[call_id]
        if "request" in pair and "response" in pair:
            pairs.append({"id": call_id, "request": pair["request"], "response": pair["response"]})
        elif "request" in pair:
            pairs.append({"id": call_id, "request": pair["request"], "response": None})
    return pairs


def parse_http_message(text: str, is_request: bool) -> dict:
    """Parse raw HTTP text into structured dict."""
    # Split on first blank line (headers vs body)
    parts = re.split(r"\r?\n\r?\n", text, maxsplit=1)
    header_block = parts[0]
    body_raw = parts[1] if len(parts) > 1 else ""

    lines = header_block.split("\n")
    first_line = lines[0].strip()
    headers = {}

    for line in lines[1:]:
        line = line.strip()
        if not line:
            continue
        colon = line.find(":")
        if colon == -1:
            continue
        key = line[:colon].strip()
        val = line[colon + 1 :].strip()
        # Accumulate duplicate headers (e.g. Set-Cookie)
        if key.lower() in [k.lower() for k in headers]:
            existing_key = next(k for k in headers if k.lower() == key.lower())
            existing = headers[existing_key]
            if isinstance(existing, list):
                existing.append(val)
            else:
                headers[existing_key] = [existing, val]
        else:
            headers[key] = val

    # Parse body as JSON if possible
    body = None
    body_text = body_raw.strip()
    if body_text:
        try:
            body = json.loads(body_text)
        except (json.JSONDecodeError, ValueError):
            body = body_text

    if is_request:
        # Parse: METHOD /path HTTP/1.1
        m = re.match(r"^(\S+)\s+(\S+)\s+HTTP/[\d.]+", first_line)
        method = m.group(1) if m else "GET"
        path = m.group(2) if m else "/"

        host = ""
        for k, v in headers.items():
            if k.lower() == "host":
                host = v if isinstance(v, str) else v[0]
                break
        url = f"https://{host}{path}" if host else path

        return {"method": method, "url": url, "headers": headers, "body": body}
    else:
        # Parse: HTTP/1.1 200 OK
        m = re.match(r"^HTTP/[\d.]+\s+(\d+)\s*(.*)", first_line)
        status_code = int(m.group(1)) if m else 0
        status_text = m.group(2).strip() if m else ""
        return {"statusCode": status_code, "statusText": status_text, "headers": headers, "body": body}


REDACT_HEADERS = {"authorization", "cookie", "set-cookie", "x-api-key"}


def redact_headers(headers: dict) -> dict:
    """Replace sensitive header values with [REDACTED]."""
    redacted = {}
    for k, v in headers.items():
        if k.lower() in REDACT_HEADERS:
            if isinstance(v, list):
                redacted[k] = ["[REDACTED]"] * len(v)
            else:
                redacted[k] = "[REDACTED]"
        else:
            redacted[k] = v
    return redacted


def detect_platform(pairs: list[dict]) -> str | None:
    """Auto-detect platform from x-chplat or User-Agent headers."""
    for pair in pairs:
        text = pair["request"].read_text(encoding="utf-8", errors="replace")
        for line in text.split("\n"):
            line_s = line.strip().lower()
            if line_s.startswith("x-chplat:"):
                val = line_s.split(":", 1)[1].strip()
                if val in ("ios", "android"):
                    return val
            if line_s.startswith("x-device-type:"):
                val = line_s.split(":", 1)[1].strip()
                if "ios" in val:
                    return "ios"
                if "android" in val:
                    return "android"
    return None


def process_session(folder: Path, name: str, platform: str, redact: bool) -> dict:
    """Process all request/response pairs in a Proxyman export folder."""
    pairs = discover_pairs(folder)
    if not pairs:
        print(f"Error: No request/response pairs found in {folder}", file=sys.stderr)
        sys.exit(1)

    # Auto-detect platform if needed
    if not platform:
        platform = detect_platform(pairs) or "unknown"

    calls = []
    for pair in pairs:
        req_text = pair["request"].read_text(encoding="utf-8", errors="replace")
        req = parse_http_message(req_text, is_request=True)

        resp = None
        if pair["response"]:
            resp_text = pair["response"].read_text(encoding="utf-8", errors="replace")
            resp = parse_http_message(resp_text, is_request=False)

        if redact:
            req["headers"] = redact_headers(req["headers"])
            if resp:
                resp["headers"] = redact_headers(resp["headers"])

        call = {"id": pair["id"], "request": req}
        if resp:
            call["response"] = resp
        else:
            call["response"] = {"statusCode": 0, "statusText": "No Response", "headers": {}, "body": None}
        calls.append(call)

    return {
        "name": name,
        "importedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "platform": platform,
        "calls": calls,
    }


def upsert_manifest(data_dir: Path, name: str, slug: str, platform: str, imported_at: str, call_count: int):
    """Update or insert session entry in sessions.json manifest."""
    manifest_path = data_dir / "sessions.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
    else:
        manifest = {"sessions": []}

    entry = {
        "name": name,
        "slug": slug,
        "platform": platform,
        "importedAt": imported_at,
        "callCount": call_count,
    }

    # Upsert by slug
    sessions = manifest["sessions"]
    found = False
    for i, s in enumerate(sessions):
        if s["slug"] == slug:
            sessions[i] = entry
            found = True
            break
    if not found:
        sessions.append(entry)

    # Sort by name
    sessions.sort(key=lambda s: s["name"].lower())
    manifest["sessions"] = sessions
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest_path


def main():
    parser = argparse.ArgumentParser(description="Import a Proxyman raw export into APIVault")
    parser.add_argument("proxyman_folder", help="Path to the Proxyman .folder export directory")
    parser.add_argument("screen_name", help='Screen/flow name (e.g. "Photo Projects List")')
    parser.add_argument("--platform", choices=["ios", "android"], default=None, help="Platform (auto-detected from headers if omitted)")
    parser.add_argument("--redact", action="store_true", help="Redact Authorization, Cookie, Set-Cookie, x-api-key values")
    parser.add_argument("--data-dir", default=None, help="Data directory (default: ./data relative to this script)")

    args = parser.parse_args()

    folder = Path(args.proxyman_folder).resolve()
    if not folder.is_dir():
        print(f"Error: {folder} is not a directory", file=sys.stderr)
        sys.exit(1)

    if args.data_dir:
        data_dir = Path(args.data_dir).resolve()
    else:
        data_dir = Path(__file__).resolve().parent / "data"

    slug = slugify(args.screen_name)
    session_dir = data_dir / slug
    session_dir.mkdir(parents=True, exist_ok=True)

    print(f"Scanning {folder}...")
    session = process_session(folder, args.screen_name, args.platform, args.redact)
    print(f"Found {len(session['calls'])} API call(s), platform: {session['platform']}")

    # Write session JSON
    session_path = session_dir / "session.json"
    session_path.write_text(json.dumps(session, indent=2) + "\n")
    print(f"Wrote {session_path}")

    # Update manifest
    manifest_path = upsert_manifest(
        data_dir,
        args.screen_name,
        slug,
        session["platform"],
        session["importedAt"],
        len(session["calls"]),
    )
    print(f"Updated {manifest_path}")
    print(f"\nView: open index.html or run 'python3 -m http.server 8080'")


if __name__ == "__main__":
    main()
