# APIVault

Living API documentation for mobile apps. Capture traffic with [Proxyman](https://proxyman.io), import it here, and browse every API call organized by screen or flow.

![APIVault Screenshot](screenshot-placeholder.png)

## Quick Start

### 1. Export from Proxyman

In Proxyman, select the requests you want to capture, then **File > Export > Raw**.
This creates a `.folder` directory containing paired `[ID] Request - *.txt` / `[ID] Response - *.txt` files.

### 2. Import a session

```bash
python3 import_session.py ./Raw_03-27-2026-14-33-50.folder/ "Photo Projects List" --redact
```

### 3. View

```bash
python3 -m http.server 8080
# Open http://localhost:8080
```

Or just open `index.html` and drag & drop the Proxyman folder for ad-hoc viewing.

## Import Script

```
python3 import_session.py <proxyman_folder> <screen_name> [options]
```

| Flag | Description |
|------|-------------|
| `--platform ios\|android` | Set platform manually (auto-detected from `x-chplat` header if omitted) |
| `--redact` | Replace `Authorization`, `Cookie`, `Set-Cookie`, `x-api-key` values with `[REDACTED]` |
| `--data-dir ./data` | Custom data directory (default: `./data` relative to script) |

### Examples

```bash
# Import with auto-detected platform
python3 import_session.py ./exports/Raw_session.folder/ "Cart Checkout"

# Import with redaction and explicit platform
python3 import_session.py ./exports/Raw_session.folder/ "Home Screen" --platform android --redact

# Import to a custom data directory
python3 import_session.py ./exports/Raw_session.folder/ "Search Results" --data-dir /path/to/data
```

## GitHub Pages

1. Push this repo to GitHub
2. Go to **Settings > Pages**
3. Set source to **Deploy from a branch**, branch: `main`, folder: `/ (root)`
4. Your site will be live at `https://<user>.github.io/APIVault/`

## Drag & Drop

The viewer supports drag & drop for ad-hoc viewing without importing:

1. Open `index.html` (via a local server or directly)
2. Drag a Proxyman `.folder` export directory (or individual `.txt` files) onto the page
3. The API calls appear as an "Ad-hoc Import" session in the sidebar

This is useful for quick inspection without committing data to the repo.

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `↑` / `k` | Previous API call |
| `↓` / `j` | Next API call |

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
      "id": "26285",
      "request": {
        "method": "POST",
        "url": "https://www-qa2.cvs.com/retail/...",
        "headers": { "Host": "www-qa2.cvs.com", "..." : "..." },
        "body": { "data": { "..." : "..." } }
      },
      "response": {
        "statusCode": 200,
        "statusText": "OK",
        "headers": { "Content-Type": "application/json", "..." : "..." },
        "body": { "statusCode": "0000", "..." : "..." }
      }
    }
  ]
}
```

## License

Internal tooling — not for public distribution.
