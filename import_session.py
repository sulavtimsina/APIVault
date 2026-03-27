#!/usr/bin/env python3
"""Parse Proxyman raw exports and cURL commands into structured JSON for APIVault viewer."""

import argparse
import json
import re
import shlex
import sys
from datetime import datetime, timezone
from pathlib import Path


def slugify(name: str) -> str:
    """Convert a screen name to a URL-friendly slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


def get_data_dir(args_data_dir: str | None) -> Path:
    if args_data_dir:
        return Path(args_data_dir).resolve()
    return Path(__file__).resolve().parent / "data"


# ---------------------------------------------------------------------------
# Proxyman folder parsing
# ---------------------------------------------------------------------------

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
        val = line[colon + 1:].strip()
        if key.lower() in [k.lower() for k in headers]:
            existing_key = next(k for k in headers if k.lower() == key.lower())
            existing = headers[existing_key]
            if isinstance(existing, list):
                existing.append(val)
            else:
                headers[existing_key] = [existing, val]
        else:
            headers[key] = val

    body = None
    body_text = body_raw.strip()
    if body_text:
        try:
            body = json.loads(body_text)
        except (json.JSONDecodeError, ValueError):
            body = body_text

    if is_request:
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


def detect_platform_from_pairs(pairs: list[dict]) -> str | None:
    for pair in pairs:
        text = pair["request"].read_text(encoding="utf-8", errors="replace")
        plat = detect_platform_from_text(text)
        if plat:
            return plat
    return None


def detect_platform_from_text(text: str) -> str | None:
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


def detect_platform_from_headers(headers: dict) -> str | None:
    for k, v in headers.items():
        val = (v if isinstance(v, str) else v[0]).lower()
        if k.lower() == "x-chplat" and val in ("ios", "android"):
            return val
        if k.lower() == "x-device-type":
            if "ios" in val:
                return "ios"
            if "android" in val:
                return "android"
    return None


def process_folder(folder: Path, name: str, platform: str | None, redact: bool) -> dict:
    pairs = discover_pairs(folder)
    if not pairs:
        print(f"Error: No request/response pairs found in {folder}", file=sys.stderr)
        sys.exit(1)

    if not platform:
        platform = detect_platform_from_pairs(pairs) or "unknown"

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
        call["response"] = resp if resp else {"statusCode": 0, "statusText": "No Response", "headers": {}, "body": None}
        calls.append(call)

    return {
        "name": name,
        "importedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "platform": platform,
        "calls": calls,
    }


# ---------------------------------------------------------------------------
# cURL parsing
# ---------------------------------------------------------------------------

def parse_curl(curl_str: str) -> dict:
    """Parse a cURL command string into a request dict."""
    # Normalize line continuations
    curl_str = curl_str.replace("\\\n", " ").replace("\\\r\n", " ")
    try:
        tokens = shlex.split(curl_str)
    except ValueError as e:
        print(f"Error parsing cURL command: {e}", file=sys.stderr)
        sys.exit(1)

    # Remove 'curl' if first token
    if tokens and tokens[0] == "curl":
        tokens = tokens[1:]

    method = "GET"
    url = ""
    headers = {}
    body = None

    i = 0
    while i < len(tokens):
        tok = tokens[i]

        if tok in ("-X", "--request"):
            i += 1
            if i < len(tokens):
                method = tokens[i].upper()

        elif tok in ("-H", "--header"):
            i += 1
            if i < len(tokens):
                hdr = tokens[i]
                colon = hdr.find(":")
                if colon != -1:
                    key = hdr[:colon].strip()
                    val = hdr[colon + 1:].strip()
                    if key.lower() in [k.lower() for k in headers]:
                        existing_key = next(k for k in headers if k.lower() == key.lower())
                        existing = headers[existing_key]
                        if isinstance(existing, list):
                            existing.append(val)
                        else:
                            headers[existing_key] = [existing, val]
                    else:
                        headers[key] = val

        elif tok in ("-d", "--data", "--data-raw", "--data-binary", "--data-ascii"):
            i += 1
            if i < len(tokens):
                body_str = tokens[i]
                try:
                    body = json.loads(body_str)
                except (json.JSONDecodeError, ValueError):
                    body = body_str
                # If -d is used and method is still GET, switch to POST
                if method == "GET":
                    method = "POST"

        elif tok in ("--compressed", "-s", "--silent", "-S", "--show-error",
                      "-k", "--insecure", "-L", "--location", "-v", "--verbose",
                      "-i", "--include"):
            pass  # Skip flags without args

        elif tok.startswith("-"):
            # Unknown flag — skip it and its argument if it doesn't start with -
            if i + 1 < len(tokens) and not tokens[i + 1].startswith("-"):
                i += 1

        else:
            # Positional arg = URL
            if not url:
                url = tok

        i += 1

    if not url:
        print("Error: No URL found in cURL command", file=sys.stderr)
        sys.exit(1)

    return {"method": method, "url": url, "headers": headers, "body": body}


# ---------------------------------------------------------------------------
# Session I/O
# ---------------------------------------------------------------------------

def load_session(session_path: Path) -> dict:
    if session_path.exists():
        return json.loads(session_path.read_text())
    return None


def save_session(session_path: Path, session: dict):
    session_path.parent.mkdir(parents=True, exist_ok=True)
    session_path.write_text(json.dumps(session, indent=2) + "\n")


def next_call_id(session: dict) -> str:
    """Generate next sequential call ID for a session."""
    max_id = 0
    for call in session.get("calls", []):
        try:
            max_id = max(max_id, int(call["id"]))
        except (ValueError, TypeError):
            pass
    return str(max_id + 1)


def upsert_manifest(data_dir: Path, name: str, slug: str, platform: str, imported_at: str, call_count: int):
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

    sessions = manifest["sessions"]
    found = False
    for i, s in enumerate(sessions):
        if s["slug"] == slug:
            sessions[i] = entry
            found = True
            break
    if not found:
        sessions.append(entry)

    sessions.sort(key=lambda s: s["name"].lower())
    manifest["sessions"] = sessions
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest_path


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_folder(args):
    folder = Path(args.proxyman_folder).resolve()
    if not folder.is_dir():
        print(f"Error: {folder} is not a directory", file=sys.stderr)
        sys.exit(1)

    data_dir = get_data_dir(args.data_dir)
    slug = slugify(args.screen_name)
    session_dir = data_dir / slug

    print(f"Scanning {folder}...")
    session = process_folder(folder, args.screen_name, args.platform, args.redact)
    print(f"Found {len(session['calls'])} API call(s), platform: {session['platform']}")

    save_session(session_dir / "session.json", session)
    print(f"Wrote {session_dir / 'session.json'}")

    manifest_path = upsert_manifest(data_dir, args.screen_name, slug, session["platform"], session["importedAt"], len(session["calls"]))
    print(f"Updated {manifest_path}")


def cmd_curl(args):
    data_dir = get_data_dir(args.data_dir)
    slug = slugify(args.screen_name)
    session_path = data_dir / slug / "session.json"

    # Get cURL command
    if args.command:
        curl_str = args.command
    else:
        print("Paste your cURL command (press Ctrl+D when done):")
        curl_str = sys.stdin.read().strip()

    if not curl_str:
        print("Error: No cURL command provided", file=sys.stderr)
        sys.exit(1)

    req = parse_curl(curl_str)

    if args.redact:
        req["headers"] = redact_headers(req["headers"])

    # Detect platform from headers if not specified
    platform = args.platform
    if not platform:
        platform = detect_platform_from_headers(req["headers"]) or "unknown"

    # Load or create session
    session = load_session(session_path)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if session:
        call_id = next_call_id(session)
        platform = session["platform"]  # Keep existing platform
    else:
        call_id = "1"
        session = {
            "name": args.screen_name,
            "importedAt": now,
            "platform": platform,
            "calls": [],
        }

    call = {
        "id": call_id,
        "request": req,
        "response": {"statusCode": 0, "statusText": "Pending", "headers": {}, "body": None},
    }
    session["calls"].append(call)

    save_session(session_path, session)
    print(f"Added call #{call_id}: {req['method']} {req['url']}")
    print(f"Wrote {session_path}")

    manifest_path = upsert_manifest(data_dir, session["name"], slug, platform, now, len(session["calls"]))
    print(f"Updated {manifest_path}")
    print(f"\nTo add a response later:\n  python3 import_session.py add-response {slug} {call_id}")


def cmd_add_response(args):
    data_dir = get_data_dir(args.data_dir)
    session_path = data_dir / args.slug / "session.json"

    session = load_session(session_path)
    if not session:
        print(f"Error: No session found at {session_path}", file=sys.stderr)
        sys.exit(1)

    # Find the call
    call = None
    for c in session["calls"]:
        if c["id"] == args.call_id:
            call = c
            break

    if not call:
        ids = [c["id"] for c in session["calls"]]
        print(f"Error: Call ID '{args.call_id}' not found. Available IDs: {', '.join(ids)}", file=sys.stderr)
        sys.exit(1)

    # Get response body
    if args.body_file:
        body_text = Path(args.body_file).read_text(encoding="utf-8")
    elif args.body:
        body_text = args.body
    else:
        print("Paste the response body JSON (press Ctrl+D when done):")
        body_text = sys.stdin.read().strip()

    if not body_text:
        print("Error: No response body provided", file=sys.stderr)
        sys.exit(1)

    try:
        body = json.loads(body_text)
    except (json.JSONDecodeError, ValueError):
        body = body_text

    status_code = args.status or 200
    status_text = {200: "OK", 201: "Created", 204: "No Content", 400: "Bad Request",
                   401: "Unauthorized", 403: "Forbidden", 404: "Not Found",
                   500: "Internal Server Error"}.get(status_code, "")

    call["response"] = {
        "statusCode": status_code,
        "statusText": status_text,
        "headers": call.get("response", {}).get("headers", {}),
        "body": body,
    }

    save_session(session_path, session)
    print(f"Updated call #{args.call_id} with {status_code} response")
    print(f"Wrote {session_path}")


def main():
    parser = argparse.ArgumentParser(description="Import API data into APIVault")
    subparsers = parser.add_subparsers(dest="subcommand")

    # --- folder subcommand ---
    p_folder = subparsers.add_parser("folder", help="Import a Proxyman raw export folder")
    p_folder.add_argument("proxyman_folder", help="Path to the Proxyman .folder export directory")
    p_folder.add_argument("screen_name", help='Screen/flow name (e.g. "Photo Projects List")')
    p_folder.add_argument("--platform", choices=["ios", "android"], default=None)
    p_folder.add_argument("--redact", action="store_true", help="Redact sensitive headers")
    p_folder.add_argument("--data-dir", default=None)

    # --- curl subcommand ---
    p_curl = subparsers.add_parser("curl", help="Import a cURL command as an API call")
    p_curl.add_argument("screen_name", help='Screen/flow name (e.g. "Photo Projects List")')
    p_curl.add_argument("-c", "--command", default=None, help="cURL command string (or omit to read from stdin)")
    p_curl.add_argument("--platform", choices=["ios", "android"], default=None)
    p_curl.add_argument("--redact", action="store_true", help="Redact sensitive headers")
    p_curl.add_argument("--data-dir", default=None)

    # --- add-response subcommand ---
    p_resp = subparsers.add_parser("add-response", help="Add/update a response body for an existing call")
    p_resp.add_argument("slug", help="Session slug (e.g. photo-projects-list)")
    p_resp.add_argument("call_id", help="Call ID to update")
    p_resp.add_argument("--status", type=int, default=200, help="HTTP status code (default: 200)")
    p_resp.add_argument("--body", default=None, help="Response body JSON string")
    p_resp.add_argument("--body-file", default=None, help="Path to file containing response body JSON")
    p_resp.add_argument("--data-dir", default=None)

    # Backwards compatibility: if first arg looks like a path, inject 'folder' subcommand
    if len(sys.argv) > 1 and sys.argv[1] not in ("folder", "curl", "add-response", "-h", "--help"):
        arg1 = sys.argv[1]
        if arg1.startswith("./") or arg1.startswith("/") or arg1.endswith(".folder") or arg1.endswith(".folder/"):
            sys.argv.insert(1, "folder")

    args = parser.parse_args()

    if not args.subcommand:
        if True:
            parser.print_help()
            print("\nExamples:")
            print("  python3 import_session.py folder ./Raw_export.folder/ \"Screen Name\" --redact")
            print("  python3 import_session.py curl \"Screen Name\" -c 'curl -X POST https://...'")
            print("  python3 import_session.py add-response screen-name 1 --body '{\"key\":\"value\"}'")
            sys.exit(0)

    if args.subcommand == "folder":
        cmd_folder(args)
    elif args.subcommand == "curl":
        cmd_curl(args)
    elif args.subcommand == "add-response":
        cmd_add_response(args)


if __name__ == "__main__":
    main()
