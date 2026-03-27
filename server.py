#!/usr/bin/env python3
"""APIVault local server — serves the viewer and persists changes to data/ JSON files."""

import json
import sys
from datetime import datetime, timezone
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
import re

DATA_DIR = Path(__file__).resolve().parent / "data"


def slugify(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


def upsert_manifest(name: str, slug: str, platform: str, imported_at: str, call_count: int):
    manifest_path = DATA_DIR / "sessions.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
    else:
        manifest = {"sessions": []}

    entry = {"name": name, "slug": slug, "platform": platform, "importedAt": imported_at, "callCount": call_count}

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


class APIVaultHandler(SimpleHTTPRequestHandler):

    def do_POST(self):
        if self.path == "/api/add-call":
            self._handle_add_call()
        elif self.path == "/api/update-response":
            self._handle_update_response()
        else:
            self.send_error(404, "Not found")

    def _read_json_body(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        return json.loads(raw)

    def _send_json(self, status, data):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle_add_call(self):
        try:
            payload = self._read_json_body()
        except Exception:
            self.send_error(400, "Invalid JSON")
            return

        name = payload.get("name", "Untitled")
        platform = payload.get("platform", "unknown")
        request = payload.get("request")
        if not request or not request.get("url"):
            self._send_json(400, {"error": "Missing request.url"})
            return

        slug = slugify(name)
        session_dir = DATA_DIR / slug
        session_dir.mkdir(parents=True, exist_ok=True)
        session_path = session_dir / "session.json"

        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        if session_path.exists():
            session = json.loads(session_path.read_text())
        else:
            session = {"name": name, "importedAt": now, "platform": platform, "calls": []}

        # Generate next call ID
        max_id = 0
        for c in session.get("calls", []):
            try:
                max_id = max(max_id, int(c["id"]))
            except (ValueError, TypeError):
                pass
        call_id = str(max_id + 1)

        call = {
            "id": call_id,
            "request": request,
            "response": payload.get("response", {"statusCode": 0, "statusText": "Pending", "headers": {}, "body": None}),
        }
        session["calls"].append(call)

        session_path.write_text(json.dumps(session, indent=2) + "\n")
        upsert_manifest(session["name"], slug, session["platform"], now, len(session["calls"]))

        self._send_json(200, {"ok": True, "slug": slug, "callId": call_id, "callCount": len(session["calls"])})
        print(f"  Added call #{call_id} to '{name}' ({slug})")

    def _handle_update_response(self):
        try:
            payload = self._read_json_body()
        except Exception:
            self.send_error(400, "Invalid JSON")
            return

        slug = payload.get("slug")
        call_id = str(payload.get("callId", ""))
        status_code = payload.get("statusCode", 200)
        body = payload.get("body")

        if not slug or not call_id:
            self._send_json(400, {"error": "Missing slug or callId"})
            return

        session_path = DATA_DIR / slug / "session.json"
        if not session_path.exists():
            self._send_json(404, {"error": f"Session '{slug}' not found"})
            return

        session = json.loads(session_path.read_text())
        call = None
        for c in session.get("calls", []):
            if str(c["id"]) == call_id:
                call = c
                break

        if not call:
            self._send_json(404, {"error": f"Call #{call_id} not found"})
            return

        status_texts = {200: "OK", 201: "Created", 204: "No Content", 400: "Bad Request",
                        401: "Unauthorized", 403: "Forbidden", 404: "Not Found", 500: "Internal Server Error"}

        call["response"] = {
            "statusCode": status_code,
            "statusText": status_texts.get(status_code, ""),
            "headers": call.get("response", {}).get("headers", {}),
            "body": body,
        }

        session_path.write_text(json.dumps(session, indent=2) + "\n")
        self._send_json(200, {"ok": True})
        print(f"  Updated response for call #{call_id} in '{slug}'")

    def log_message(self, format, *args):
        # Only log API calls and errors, not every static file
        msg = format % args
        if "/api/" in msg or "404" in msg or "500" in msg:
            super().log_message(format, *args)


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    server = HTTPServer(("", port), APIVaultHandler)
    print(f"APIVault server running at http://localhost:{port}")
    print(f"Data directory: {DATA_DIR}")
    print("Press Ctrl+C to stop\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
