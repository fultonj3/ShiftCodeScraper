# Shift Code Scraper & Redeemer

End-to-end tooling to scrape Borderlands SHiFT codes to a CSV and redeem them via Selenium. Supports single-user CLI runs and multi-user orchestration via a `.env` file.

**Modules**
- `ShiftCodeScraper.py` — Scrapes codes and appends only new ones to `shift_codes.csv`.
- `ShiftCodeRedeemer.py` — Logs in and redeems one or more codes in a single browser session.
- `ShiftCodeRunner.py` — Multi-user orchestrator: loads users from `.env`, runs scraper, redeems new codes for each user, and updates per-user status in the CSV.

## Features
- Regex validation and duplicate avoidance when scraping.
- Robust extraction with automatic fallback when selectors change.
- Resilient HTTP (timeouts + retries).
- Per-user redemption in a single login session per user.
- CSV status tracking per user (`Redeemed:<name>` columns), plus expiration info.
- Clear logging for successes, warnings, and errors.

## Requirements
- Python 3.8+
- See `requirements.txt` (includes `requests`, `beautifulsoup4`, `selenium`, `webdriver-manager`, `python-dotenv`).

Install:
```
python -m pip install -U pip
pip install -r requirements.txt
```

## Quick Start

Scrape only:
```
python ShiftCodeScraper.py            # Writes new codes to shift_codes.csv
python ShiftCodeScraper.py -v         # Verbose logs
python ShiftCodeScraper.py --dry-run  # Preview without writing CSV
```

Redeem (single user):
```
# Using env vars (recommended)
set SHIFT_USERNAME=your_email
set SHIFT_PASSWORD=your_password
python ShiftCodeRedeemer.py CODE1 CODE2

# Or pass via CLI
python ShiftCodeRedeemer.py --username your_email --password your_password CODE1 CODE2
```

Multi-user end-to-end:
```
# 1) Create .env (see format below)
# 2) Run the orchestrator
python ShiftCodeRunner.py
```

## .env (multi-user) format
Create a `.env` in the project root:
```
USERS=alice,bob

# alice
SHIFT_alice_USERNAME=alice@example.com
SHIFT_alice_PASSWORD=supersecret
SHIFT_alice_PLATFORM=steam   # or 1/2/3/4
SHIFT_alice_BROWSER=chrome   # chrome|edge (optional)
SHIFT_alice_HEADLESS=false   # true|false (optional)

# bob
SHIFT_bob_USERNAME=bob@example.com
SHIFT_bob_PASSWORD=anothersecret
SHIFT_bob_PLATFORM=3         # xbox

# Optional
CSV_PATH=shift_codes.csv
SCRAPER_URL=https://www.ign.com/wikis/borderlands-4/Borderlands_4_SHiFT_Codes
```

`ShiftCodeRunner.py` will:
- Ensure the CSV header is present and add per-user columns as `Redeemed:<name>`.
- Scrape for new codes and append them with `Date Added` and `Expiration`.
- For each user, log in once and redeem all new codes in a single session.
- Update `Redeemed:<name>` to `Yes` for statuses “Successfully Redeemed” or “Already Redeemed”.

## CSV Format
Header columns (auto-created/updated):
- `Code`
- `Date Added` (YYYY-MM-DD)
- `Expiration` (if known)
- `Redeemed` (original global column retained)
- `Redeemed:<user>` for each user defined in `.env`

## Notes & Limitations
- Browser: Chromium-based (`chrome` or `edge`) with drivers auto-managed by `webdriver-manager`.
- Profiles: Use `--profile` to keep sessions/cookies if desired.
- PlayStation: Currently not supported in the redeemer flow due to no linked PlayStation account for testing. The option exists but is treated as unsupported in practice.

## Troubleshooting
- Install deps: `pip install -r requirements.txt`
- HTTP 403/429 when scraping: retry later; the scraper already backs off.
- CSV locked (Windows): close any app that has `shift_codes.csv` open.
- Selenium driver issues: ensure Chrome/Edge is installed and up to date.

## Development
- Scraper pattern: `^[A-Z0-9]{5}(?:-[A-Z0-9]{5}){4}$`
- Defaults: source URL is the IGN Borderlands 4 wiki page.
- Keep changes focused and minimal; PRs welcome.

