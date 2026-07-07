# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ShiftCodeScraper is a Python automation tool that scrapes Borderlands SHiFT codes from the IGN wiki, stores them in a CSV, and redeems them for multiple users via Selenium browser automation against the Gearbox SHiFT rewards site.

## Running the Code

**Install dependencies:**
```bash
pip install -r requirements.txt
```

**Scraper only** (fetch new codes from IGN wiki → write to CSV):
```bash
python ShiftCodeScraper.py
python ShiftCodeScraper.py -v         # verbose logging
python ShiftCodeScraper.py --dry-run  # preview without writing
```

**Single-user redemption:**
```bash
export SHIFT_USERNAME=user@example.com
export SHIFT_PASSWORD=password
python ShiftCodeRedeemer.py CODE1 CODE2
# or via flags:
python ShiftCodeRedeemer.py --username user@example.com --password pwd CODE1 CODE2
```

**Multi-user end-to-end** (main use case — requires `.env` file):
```bash
python ShiftCodeRunner.py
```

There are no automated tests, linting configs, or CI pipelines in this project.

## Architecture

Three modules form a pipeline:

### ShiftCodeScraper.py
Scrapes `https://www.ign.com/wikis/borderlands-4/Borderlands_4_SHiFT_Codes` using `requests` + `BeautifulSoup`. Validates codes against the pattern `^[A-Z0-9]{5}(?:-[A-Z0-9]{5}){4}$`. Handles duplicate detection, expiration date extraction, CSV management (including schema upgrades from older 3-column headers), and optional Discord webhook notifications (batched to stay within Discord's 4096-char limit).

Primary HTML extraction uses class-based selectors (`span.task-name.bold.small`); falls back to a full page scan if those selectors fail.

### ShiftCodeRedeemer.py
Selenium-based browser automation targeting `https://shift.gearboxsoftware.com/rewards`. Supports Chrome and Edge via `webdriver-manager`. Key behaviors:
- Persists browser profile (cookies/session) across runs
- Searches for elements across iframes via `_find_in_all_frames()`
- Captures debug artifacts (screenshots, DOM dumps, console logs) to `DEBUG_ARTIFACTS_DIR` on errors
- Returns per-code status strings: `"Successfully Redeemed"`, `"Already Redeemed"`, `"Invalid Code"`, or `"Error: <msg>"`

### ShiftCodeRunner.py
Orchestrator that loads users from `.env`, runs the scraper once, then loops through each user running a separate Redeemer browser session. Manages per-user columns (`Redeemed:<username>`) in the CSV and posts a Discord summary of redemption counts when complete.

## Configuration

Copy `example.env` to `.env`:

```
USERS=alice,bob

SHIFT_alice_USERNAME=alice@example.com
SHIFT_alice_PASSWORD=secret123
SHIFT_alice_PLATFORM=steam          # steam | epic | xbox | playstation (or 1–4)
SHIFT_alice_BROWSER=chrome          # chrome | edge (default: chrome)
SHIFT_alice_HEADLESS=false          # true/false (default: false)

SHIFT_bob_USERNAME=bob@example.com
SHIFT_bob_PASSWORD=secret456
SHIFT_bob_PLATFORM=3                # Xbox

# Optional
CSV_PATH=shift_codes.csv
SCRAPER_URL=<url>                   # defaults to IGN Borderlands 4 wiki
DISCORD_WEBHOOK=<url>
DEBUG_ARTIFACTS_DIR=./debug
```

**This is a public repo.** Never put real credentials, tokens, webhook URLs, or other secrets/private info in this file or any committed file — `.env` (gitignored) is the only place for that.

## CSV Schema

Auto-created at `shift_codes.csv` (path overridable via `CSV_PATH`):

| Column | Notes |
|---|---|
| `Code` | Full SHiFT code string |
| `Date Added` | YYYY-MM-DD |
| `Expiration` | YYYY-MM-DD or blank |
| `Redeemed` | Yes/No (single-user mode) |
| `Redeemed:<username>` | Per-user columns added automatically by Runner |

Older 3-column CSVs (without `Expiration`) are auto-upgraded on first run.

## Known Limitations

- PlayStation redemption is not supported by the Redeemer.
- On Windows, CSV file locking may occur if multiple processes access the file simultaneously.
- Only Chromium-based browsers (Chrome, Edge) are supported by the Redeemer.
