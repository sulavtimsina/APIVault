# APIVault

Living API documentation for mobile apps. Capture traffic with [Proxyman](https://proxyman.io), import it here, and browse every API call organized by screen or flow.

![APIVault Screenshot](screenshot-placeholder.png)

## Quick Start

### 1. Import API calls

**From a Proxyman export:**
```bash
python3 import_session.py folder ./Raw_03-27-2026-14-33-50.folder/ "Photo Projects List" --redact
```

**From a cURL command:**
```bash
python3 import_session.py curl "Photo Projects List" -c 'curl -X POST https://api.example.com/v1/load -H "Content-Type: application/json" -d "{}"'
```

**Add a response later:**
```bash
python3 import_session.py add-response photo-projects-list 1 --body '{"status": "OK"}'
```

### 2. View

```bash
python3 -m http.server 8080
# Open http://localhost:8080
```

Or open `index.html` directly and use **+ cURL** button or drag & drop.

## Import Commands

### `folder` — Import Proxyman raw export

```bash
python3 import_session.py folder <proxyman_folder> <screen_name> [options]
```

| Flag | Description |
|------|-------------|
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

## Web Viewer Features

### + cURL button
Click **+ cURL** in the sidebar to paste a cURL command directly in the browser. Creates an in-memory session you can inspect immediately.

### Add Response
When viewing a call with no response, click **+ Add Response Body** in the response panel to paste the JSON response.

### Drag & Drop
Drag a Proxyman `.folder` export onto the page for ad-hoc viewing.

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `↑` / `k` | Previous API call |
| `↓` / `j` | Next API call |
| `Esc` | Close modals |

## GitHub Pages

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
