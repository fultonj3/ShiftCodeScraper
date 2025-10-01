# Shift Code Scraper

Scrapes Borderlands SHiFT codes from a webpage and appends them to a CSV. The scraper validates code format, avoids duplicates, and offers both class‑based targeting (for stability) and a robust page‑wide fallback scan.

## Features

- Validates SHiFT codes with a strict regex (5×5 alphanumerics with hyphens).
- Avoids duplicates by reading existing CSV and normalizing to uppercase.
- Optional class‑based targeting with clear warnings and automatic fallback.
- Resilient HTTP client with timeout and basic retry/backoff.
- Structured logging with `--verbose` for debug details.
- Non‑destructive `--dry-run` mode to preview changes.
- Excludes codes listed under the page's "All Expired SHiFT Codes" section by default (override with `--include-expired`).
- Optional `--pause` to keep the console open when double‑clicked.

## Requirements

- Python 3.8+
- Packages: `requests`, `beautifulsoup4`
  - Optional (faster HTML parsing): `lxml`

Install dependencies (or use `requirements.txt`):

```bash
python -m pip install -U pip
pip install -r requirements.txt
# optional parser speedup
pip install lxml
```

## Quick Start

```bash
python ShiftCodeScraper.py            # Scrape and write to shift_codes.csv
python ShiftCodeScraper.py -v         # Verbose logs
python ShiftCodeScraper.py --dry-run  # Show what would be written
```

Default source URL: `https://www.ign.com/wikis/borderlands-4/Borderlands_4_SHiFT_Codes`

## CLI Options

- `--url <URL>`: Page to scrape. Defaults to the IGN Borderlands 4 wiki page.
- `--csv <path>`: CSV output path. Defaults to `shift_codes.csv`.
- `--dry-run`: Print actions without writing the CSV.
- `-v, --verbose`: Enable debug logging.
- `--class-tag <tag>`: HTML tag for class‑based scan. Default: `span`.
- `--class-token <token>`: Repeatable class token(s) to match. If omitted, uses stable defaults.
- `--no-class-hint`: Disable class‑based scan and use page‑wide fallback only.
- `--include-expired`: Include codes listed under the page's "All Expired SHiFT Codes" section (default: exclude).
- `--pause`: Prompt to press Enter before exiting (useful when double‑clicked).

Examples:

```bash
# Use default class hint (and fallback if it fails)
python ShiftCodeScraper.py --dry-run -v

# Provide class tokens explicitly
python ShiftCodeScraper.py --class-tag span \
  --class-token task-name --class-token bold --class-token small

# Disable class-based scan entirely
python ShiftCodeScraper.py --no-class-hint

# Custom output location
python ShiftCodeScraper.py --csv data/shift_codes.csv

# Include expired (opt‑in)
python ShiftCodeScraper.py --include-expired

# Keep window open after run (helpful when double‑clicking)
python ShiftCodeScraper.py --pause
```

## CSV Format

The CSV contains a header row (auto‑created) with columns:

- `Code`
- `Date Added` (YYYY‑MM‑DD)
- `Redeemed` (`Yes`/`No`, new codes default to `No`)

By default, data is written to `shift_codes.csv`. This file is ignored by `.gitignore` to keep generated data out of version control. If you previously committed it, untrack it:

```bash
git rm --cached shift_codes.csv
git add .gitignore
git commit -m "Ignore generated CSV"
```

## How It Works

1. Ensures the CSV exists and has a header.
2. Loads existing codes (skips header, normalizes to uppercase).
3. Fetches the source page with a retrying session and a desktop User‑Agent.
4. Attempts a class‑based extraction when enabled; warns if no elements match.
5. Falls back to a page‑wide text scan to find code‑shaped tokens.
6. Appends only new codes to the CSV.

When enabled, class‑based scan runs first; if no elements match, the script warns and falls back to a full page scan. If `--include-expired` is not provided, any codes found in the "All Expired SHiFT Codes" section are filtered out.

## Build a Windows .exe

Create a single‑file executable with PyInstaller.

```powershell
python -m pip install pyinstaller
python -m PyInstaller --onefile --name ShiftCodeScraper --icon dist\favicon.ico ShiftCodeScraper.py
```

- The exe is created at `dist\ShiftCodeScraper.exe`.
- If `pyinstaller` isn’t on PATH, invoking as a module (`python -m PyInstaller ...`) avoids PATH issues.
- Run with flags as usual:

```powershell
dist\ShiftCodeScraper.exe --dry-run -v
dist\ShiftCodeScraper.exe --no-class-hint --pause
```

## Release on GitHub (manual)

1. Commit and push code.
2. Build the exe (above), test it.
3. In GitHub → Releases → Draft a new release:
   - Tag (e.g., `v1.0.0`), title, notes.
   - Upload `dist\ShiftCodeScraper.exe` as an asset.

## Scheduling

- Windows Task Scheduler: run `python ShiftCodeScraper.py` on a schedule.
- Cron (macOS/Linux): `0 */6 * * * /usr/bin/python3 /path/ShiftCodeScraper.py >> /path/shift.log 2>&1`

## Troubleshooting

- Missing packages: `pip install -r requirements.txt`
- HTTP 403/429: The script retries and sets a desktop UA. Try again later or lower frequency.
- No codes found: Use `-v` to see logs. Try `--no-class-hint` to force fallback scan or adjust `--class-token`.
- CSV permission errors (Windows): Ensure the CSV isn’t open in another application.

## Development Notes

- Core module: `ShiftCodeScraper.py`
- Defaults: selector tag `span`, class tokens `task-name`, `bold`, `small`.
- Code pattern: `^[A-Z0-9]{5}(?:-[A-Z0-9]{5}){4}$`
- Requirements file: `requirements.txt`

Contributions welcome via pull requests. Please keep changes focused and include a short description of behavior or rationale.

