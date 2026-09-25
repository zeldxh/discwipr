# discwipr

Bulk delete your Discord messages via the search API. Rate limit handling and cursor pagination included.

## How to Get Cookies and Token

1. Open [Discord Canary](https://canary.discord.com) in your browser
2. Press **F12** → **Network** tab
3. Reload the page or click on any channel
4. Find a request to `@me` or `profile?`
5. Look at **Request Headers** → copy the `authorization` token
6. Go to the **Application** tab → **Cookies** → `https://canary.discord.com`
7. Copy: `__dcfduid`, `__sdcfduid` and `cf_clearance`. `__stripe_mid` is optional and may not appear in your cookies; if you cannot find it, leave `COOKIE_STRIPE_MID` unset

## Setup

Dependencies are installed inside a virtual environment (`.venv`), so nothing is added to your global Python.

Linux / macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
# edit .env with your credentials
python main.py
```

Windows (PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
# edit .env with your credentials
python main.py
```

Run `deactivate` when you are done. To remove everything, delete the `.venv` folder.

## Configuration (.env)

| Variable | Required | Description |
|----------|----------|-------------|
| `DISCORD_TOKEN` | Yes | Your Discord token |
| `DISCORD_USER_ID` | Yes | Your Discord user ID (enable dev mode → right-click profile) |
| `COOKIE_DCFduid` | Yes | Cookie from devtools |
| `COOKIE_SDCFduid` | Yes | Cookie from devtools |
| `COOKIE_STRIPE_MID` | No | Cookie from devtools |
| `COOKIE_CF_CLEARANCE` | No | Cookie from devtools (Cloudflare) |
| `Excluded_channels` | No | Array of channel/DM IDs to keep, e.g., `['123456789']` |
| `LOG_LEVEL` | No | debug, info, warning, error, critical (default: info) |

## Notes

- Uses the Discord Canary search API; respects rate limits with retries.
- Filters by author so only your messages are deleted.
- Tokens and cookies are stored in `.env` (already in `.gitignore`).
- Run with `LOG_LEVEL=DEBUG` to see full API responses.

## License

MIT License, see [LICENSE](LICENSE).
