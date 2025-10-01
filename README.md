# Shift Code Scraper

Scrapes Borderlands SHiFT codes from a webpage and appends them to a CSV. The scraper validates code format, avoids duplicates, and offers both class-based targeting (for stability) and a robust page‑wide fallback scan.

## Features

- Validates SHiFT codes with a strict regex (5×5 alphanumerics with hyphens).
- Avoids duplicates by reading existing CSV and normalizing to uppercase.
- Optional class-based targeting with clear warnings and automatic fallback.
- Resilient HTTP client with timeout and basic retry/backoff.
- Structured logging with `--verbose` for debug details.
- Non-destructive `--dry-run` mode to preview changes.

## Requirements

- Python 3.8+
- Packages: `requests`, `beautifulsoup4`
  - Optional (faster HTML parsing): `lxml`

Install dependencies:

```bash
python -m pip install -U pip
pip install requests beautifulsoup4 lxml
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
- `--class-tag <tag>`: HTML tag for class-based scan. Default: `span`.
- `--class-token <token>`: Repeatable class token(s) to match. If omitted, uses stable defaults.
- `--no-class-hint`: Disable class-based scan and use page-wide fallback only.

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
```

## CSV Format

The CSV contains a header row (auto-created) with columns:

- `Code`
- `Date Added` (YYYY-MM-DD)
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
3. Fetches the source page with a retrying session and a desktop User-Agent.
4. Attempts a class-based extraction when enabled; warns if no elements match.
5. Falls back to a page-wide text scan to find code-shaped tokens.
6. Appends only new codes to the CSV.

## Scheduling

- Windows Task Scheduler: run `python ShiftCodeScraper.py` on a schedule.
- Cron (macOS/Linux): `0 */6 * * * /usr/bin/python3 /path/ShiftCodeScraper.py >> /path/shift.log 2>&1`

## Troubleshooting

- Missing packages: `pip install requests beautifulsoup4 lxml`
- HTTP 403/429: The script retries and sets a desktop UA. Try again later or lower frequency.
- No codes found: Use `-v` to see logs. Try `--no-class-hint` to force fallback scan or adjust `--class-token`.
- CSV permission errors (Windows): Ensure the CSV isn’t open in another application.

## Development Notes

- Core module: `ShiftCodeScraper.py`
- Defaults: selector tag `span`, class tokens `task-name`, `bold`, `small`.
- Code pattern: `^[A-Z0-9]{5}(?:-[A-Z0-9]{5}){4}$`

Contributions welcome via pull requests. Please keep changes focused and include a short description of behavior or rationale.

