# APIVault

Living API documentation for mobile apps. Capture traffic with [Proxyman](https://proxyman.io), import it here, and browse every API call organized by screen or flow.

![APIVault Screenshot](screenshot-placeholder.png)

## Quick Start

### 1. Start the server

```bash
python3 server.py
# Open http://localhost:8080
```

### 2. Create a session

Click **+ New Session** in the sidebar. Enter a name (e.g. "Sprint 42 API Capture") and pick a platform (iOS / Android / Web / Other).

### 3. Add API calls

With a session selected, use the toolbar buttons:

- **+ Paste cURL** — paste a cURL command with an optional screen/feature label
- **+ Import Files** — pick Proxyman `.txt` export files
- **Drag & drop** Proxyman files onto the call list

### 4. Import from CLI

**From a Proxyman export:**
```bash
python3 import_session.py folder ./Raw_03-27-2026-14-33-50.folder/ "Photo Projects List" --redact
```

**From a cURL command:**
```bash
python3 import_session.py curl "Photo Projects List" -c 'curl -X POST https://api.example.com/v1/load -H "Content-Type: application/json" -d "{}"'
```

**With a screen/feature label:**
```bash
python3 import_session.py curl "Photo Projects List" --label "Projects Grid" -c 'curl https://api.example.com/projects'
python3 import_session.py folder ./export.folder/ "Cart Flow" --label "Cart Page" --redact
```

**Add a response later:**
```bash
python3 import_session.py add-response photo-projects-list 1 --body '{"status": "OK"}'
```

## Import Commands

### `folder` — Import Proxyman raw export

```bash
python3 import_session.py folder <proxyman_folder> <screen_name> [options]
```

| Flag | Description |
|------|-------------|
| `--label "Screen Name"` | Screen/feature label applied to all imported calls |
| `--platform ios\|android` | Set platform (auto-detected from headers if omitted) |
| `--redact` | Replace `Authorization`, `Cookie`, `Set-Cookie`, `x-api-key` with `[REDACTED]` |
| `--data-dir ./data` | Custom data directory |

Backwards-compatible: you can omit the `folder` keyword if the first argument is a path.

### `curl` — Import a cURL command

```bash
python3 import_session.py curl <screen_name> [options]
```

| Flag | Description |
|------|-------------|
| `-c`, `--command` | cURL command string. If omitted, reads from stdin |
| `--label "Screen Name"` | Screen/feature label for this call |
| `--platform ios\|android` | Set platform (auto-detected from headers if omitted) |
| `--redact` | Redact sensitive headers |

If the session already exists, the call is **appended** to it. This is how you add multiple API calls to the same screen.

```bash
# Add first call
python3 import_session.py curl "Cart Checkout" -c 'curl https://api.example.com/cart'

# Add second call to same session
python3 import_session.py curl "Cart Checkout" -c 'curl -X POST https://api.example.com/checkout -d "{}"'

# Paste from clipboard (reads stdin)
pbpaste | python3 import_session.py curl "Cart Checkout"
```

### `add-response` — Add/update response for an existing call

```bash
python3 import_session.py add-response <slug> <call_id> [options]
```

| Flag | Description |
|------|-------------|
| `--status 200` | HTTP status code (default: 200) |
| `--body '{...}'` | Response body JSON string |
| `--body-file resp.json` | Read response body from file |

If `--body` and `--body-file` are both omitted, reads from stdin.

```bash
# Inline
python3 import_session.py add-response cart-checkout 1 --body '{"total": 9.99}'

# From file
python3 import_session.py add-response cart-checkout 1 --body-file response.json

# From clipboard
pbpaste | python3 import_session.py add-response cart-checkout 1 --status 200
```

## Server API

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/create-session` | POST | Create empty session `{name, platform}` |
| `/api/add-call` | POST | Add a call to a session `{name, platform, label, request, response?}` |
| `/api/update-response` | POST | Update response for a call `{slug, callId, statusCode, body}` |
| `/api/update-call-label` | POST | Update label for a call `{slug, callId, label}` |
| `/api/delete-session` | POST | Delete a session `{slug}` |

## Web Viewer Features

All changes made in the browser are **saved to disk** when `server.py` is running.

### Session Management
- **+ New Session** — create a session (name + platform) from the sidebar
- **Delete** — hover over a session in the sidebar to reveal the trash icon; confirms before deleting

### Adding Calls
With a session selected, the toolbar shows:
- **+ Paste cURL** — paste a cURL command with an optional screen/feature label
- **+ Import Files** — pick Proxyman `.txt` export files from disk

### Labels
Each API call can have a **screen/feature label** (e.g. "Photo Projects List", "Cart Page") to identify which screen triggered it. Labels appear in the call list table and can be edited inline in the detail panel.

### Add Response
When viewing a call with no response, click **+ Add Response Body** in the response panel to paste the JSON response.

### Drag & Drop
Drag a Proxyman `.folder` export onto the page. If a session is selected, calls are added to it.

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `↑` / `k` | Previous API call |
| `↓` / `j` | Next API call |
| `Esc` | Close modals |

## GitHub Pages (read-only)

GitHub Pages deploys a read-only viewer (no `server.py` = no saving). Use it for browsing already-imported data.

1. Push this repo to GitHub
2. Go to **Settings > Pages**
3. Set source to **Deploy from a branch**, branch: `main`, folder: `/ (root)`
4. Site: `https://<user>.github.io/APIVault/`

## Data Format

### `data/sessions.json` — Manifest

```json
{
  "sessions": [
    {
      "name": "Photo Projects List",
      "slug": "photo-projects-list",
      "platform": "ios",
      "importedAt": "2026-03-27T14:33:50Z",
      "callCount": 5
    }
  ]
}
```

### `data/<slug>/session.json` — Session detail

```json
{
  "name": "Photo Projects List",
  "importedAt": "2026-03-27T14:33:50Z",
  "platform": "ios",
  "calls": [
    {
      "id": "1",
      "label": "Projects Grid",
      "request": {
        "method": "POST",
        "url": "https://api.example.com/v1/load",
        "headers": { "Content-Type": "application/json" },
        "body": { "key": "value" }
      },
      "response": {
        "statusCode": 200,
        "statusText": "OK",
        "headers": {},
        "body": { "status": "OK" }
      }
    }
  ]
}
```

## License

Internal tooling — not for public distribution.
