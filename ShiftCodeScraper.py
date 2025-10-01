"""
Shift Code Scraper for Borderlands 4

Purpose
- Scrapes SHiFT codes from a specified webpage and stores them in a CSV.
- Validates code format via regex and avoids duplicates.

CSV columns
- Code, Date Added (YYYY-MM-DD), Redeemed (Yes/No)

Notes
- Optionally targets a specific tag/class when provided; warns if not found
  and falls back to a robust page-wide scan for code-shaped tokens.
- Includes timeouts, basic retries, and structured logging.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import logging
import re
import sys
from pathlib import Path
from typing import Iterable, List, Sequence, Set

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Defaults and configuration
DEFAULT_URL = "https://www.ign.com/wikis/borderlands-4/Borderlands_4_SHiFT_Codes"
DEFAULT_CSV = "shift_codes.csv"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# Optional class-based targeting to future-proof selector changes
# Keep tokens stable; omit dynamic framework class names
CLASS_TAG_DEFAULT = "span"
CLASS_TOKENS_DEFAULT: Sequence[str] = ("task-name", "bold", "small")

# Regex pattern for valid SHiFT codes (5 groups of 5 alphanumerics, hyphen separated)
CODE_REGEX = re.compile(r"^[A-Z0-9]{5}(?:-[A-Z0-9]{5}){4}$")


def setup_logger(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(levelname)s: %(message)s",
    )


def requests_session() -> requests.Session:
    """Create a requests session with basic retry/backoff."""
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def ensure_csv_header(path: Path) -> None:
    """Create CSV with header if it doesn't exist, or add a header if missing."""
    if not path.exists():
        with path.open("x", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Code", "Date Added", "Redeemed"])
        return

    # If file exists but first row isn't a header, leave as-is (backwards compatible)
    # We only add a header to an empty existing file.
    if path.stat().st_size == 0:
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Code", "Date Added", "Redeemed"])


def read_existing_codes(path: Path) -> Set[str]:
    """Read existing codes from CSV (ignores empty lines and normalizes to uppercase)."""
    if not path.exists():
        return set()
    codes: Set[str] = set()
    try:
        with path.open("r", newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            for row in reader:
                if not row:
                    continue
                token = (row[0] or "").strip().upper()
                # Skip a potential header row
                if token == "CODE":
                    continue
                if CODE_REGEX.match(token):
                    codes.add(token)
    except Exception as exc:
        logging.warning("Failed to read existing CSV '%s': %s", path, exc)
    return codes


def fetch_html(url: str, timeout: float = 10.0) -> str:
    """Fetch page HTML with retries and timeout."""
    session = requests_session()
    try:
        resp = session.get(url, timeout=timeout)
        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code}")
        return resp.text
    except Exception as exc:
        raise RuntimeError(f"Failed to fetch '{url}': {exc}") from exc


def extract_codes(html: str) -> List[str]:
    """Parse HTML and extract unique SHiFT codes found anywhere in text.

    This avoids brittle class-based selectors by scanning text for tokens
    that match the SHiFT code pattern.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Gather text chunks and split on whitespace/punctuation-ish boundaries.
    # Also check attribute strings that sometimes hold codes.
    candidates: Set[str] = set()

    # 1) All text nodes
    for text in soup.stripped_strings:
        for token in re.split(r"[^A-Za-z0-9-]+", text):
            token = token.strip().upper()
            if token and CODE_REGEX.match(token):
                candidates.add(token)

    # 2) Obvious attributes (href, data-*, etc.) — defensive but cheap
    for tag in soup.find_all(True):
        for attr_val in tag.attrs.values():
            if isinstance(attr_val, str):
                for token in re.split(r"[^A-Za-z0-9-]+", attr_val):
                    token = token.strip().upper()
                    if token and CODE_REGEX.match(token):
                        candidates.add(token)
            elif isinstance(attr_val, Sequence):
                for v in attr_val:
                    if not isinstance(v, str):
                        continue
                    for token in re.split(r"[^A-Za-z0-9-]+", v):
                        token = token.strip().upper()
                        if token and CODE_REGEX.match(token):
                            candidates.add(token)

    return sorted(candidates)


def extract_expired_codes(html: str) -> Set[str]:
    """Extract codes listed under the 'All Expired SHiFT Codes' section.

    Attempts to locate the expired section via its anchor id or a table header
    text. Returns an empty set if the section cannot be found.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Prefer the explicit header anchor id
    expired_anchor = soup.find(id="All_Expired_SHiFT_Codes_in_Borderlands_4")
    table = None
    if expired_anchor:
        h = expired_anchor.find_parent(["h2", "h3"]) or expired_anchor
        table = h.find_next("table")
    else:
        # Fallback: a table with a header that starts with 'All Expired SHiFT Codes'
        for th in soup.find_all("th"):
            text = (th.get_text(strip=True) or "").lower()
            if text.startswith("all expired shift codes"):
                table = th.find_parent("table")
                if table:
                    break

    if not table:
        return set()

    expired: Set[str] = set()
    for text in table.stripped_strings:
        for token in re.split(r"[^A-Za-z0-9-]+", text):
            token = token.strip().upper()
            if token and CODE_REGEX.match(token):
                expired.add(token)
    return expired


def try_extract_by_class(html: str, tag: str, class_tokens: Sequence[str]) -> tuple[List[str], bool]:
    """Attempt to extract codes from elements matching tag + all class tokens.

    Returns a tuple (codes, matched) where `matched` indicates whether any
    elements matched the selector at all. If elements matched but yielded no
    valid codes, the codes list will be empty.
    """
    soup = BeautifulSoup(html, "html.parser")
    selector = tag
    if class_tokens:
        selector += "." + ".".join(token.strip() for token in class_tokens if token.strip())
    try:
        elements = soup.select(selector)
    except Exception as exc:
        logging.debug("Invalid selector '%s': %s", selector, exc)
        return ([], False)

    if not elements:
        return ([], False)

    candidates: Set[str] = set()
    for el in elements:
        text = el.get_text(" ", strip=True)
        for token in re.split(r"[^A-Za-z0-9-]+", text):
            token = token.strip().upper()
            if token and CODE_REGEX.match(token):
                candidates.add(token)
    return (sorted(candidates), True)


def write_new_codes(path: Path, codes: Iterable[str], date_str: str, dry_run: bool = False) -> int:
    """Append new codes to CSV with date and default Redeemed flag.

    Returns the number of codes written.
    """
    if dry_run:
        for code in codes:
            logging.info("Would add code: %s", code)
        return len(list(codes))

    wrote = 0
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        for code in codes:
            writer.writerow([code, date_str, "No"])
            logging.info("Added code: %s", code)
            wrote += 1
    return wrote


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scrape and append Borderlands SHiFT codes to CSV.")
    parser.add_argument("--url", default=DEFAULT_URL, help="Source page URL")
    parser.add_argument("--csv", dest="csv_path", default=DEFAULT_CSV, help="CSV output path")
    parser.add_argument("--dry-run", action="store_true", help="Show results without writing the CSV")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")
    # Optional class-based targeting
    parser.add_argument("--class-tag", default=CLASS_TAG_DEFAULT, help="HTML tag for class-based scan (default: span)")
    parser.add_argument(
        "--class-token",
        action="append",
        default=None,
        help="Class token to match (can be repeated). Defaults to stable tokens if omitted.",
    )
    parser.add_argument(
        "--no-class-hint",
        action="store_true",
        help="Disable class-based scan and only use robust page-wide scan.",
    )
    parser.add_argument(
        "--pause",
        action="store_true",
        help="Pause for Enter before exiting (useful when double-clicked).",
    )
    parser.add_argument(
        "--include-expired",
        action="store_true",
        help="Include codes listed in the 'Expired' section (default: exclude)",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str]) -> int:
    args = parse_args(argv)
    setup_logger(verbose=args.verbose)

    csv_path = Path(args.csv_path)
    ensure_csv_header(csv_path)
    existing = read_existing_codes(csv_path)
    logging.info("Existing codes: %d", len(existing))

    try:
        html = fetch_html(args.url)
    except RuntimeError as e:
        logging.error("%s", e)
        return 1

    # Determine class tokens to use (unless disabled)
    class_tokens: Sequence[str] | None
    if args.no_class_hint:
        class_tokens = None
    else:
        class_tokens = args.class_token if args.class_token else CLASS_TOKENS_DEFAULT

    scraped: List[str] = []
    used_selector = False
    if class_tokens:
        class_codes, matched = try_extract_by_class(html, args.class_tag, class_tokens)
        used_selector = matched
        if matched:
            logging.info("Class-based scan matched %d element(s)", len(class_codes))
            if not class_codes:
                logging.warning("Matched elements but found no valid codes; falling back to page-wide scan")
        else:
            logging.warning(
                "No elements matched selector: %s.%s; falling back to page-wide scan",
                args.class_tag,
                "." + ".".join(class_tokens),
            )
        scraped = class_codes

    if not scraped:
        scraped = extract_codes(html)

    logging.info("Found %d codes on page%s", len(scraped), " (fallback scan)" if not used_selector else "")

    # Exclude explicitly expired codes (by page section) unless requested
    if not args.include_expired:
        expired = extract_expired_codes(html)
        if expired:
            before = len(scraped)
            scraped = [c for c in scraped if c not in expired]
            removed = before - len(scraped)
            logging.info("Excluded %d expired code(s) via page section", removed)
        else:
            logging.debug("No expired section or no expired codes found.")

    new_codes = [c for c in scraped if c not in existing]
    logging.info("New codes to add: %d", len(new_codes))

    today = dt.datetime.now().strftime("%Y-%m-%d")
    wrote = write_new_codes(csv_path, new_codes, today, dry_run=args.dry_run)
    if args.dry_run:
        logging.info("Dry run complete. No changes written.")
    else:
        logging.info("Wrote %d new code(s).", wrote)

    return 0


if __name__ == "__main__":
    exit_code = main(sys.argv[1:])
    # Keep console window open when double-clicked (no args), or when --pause is provided.
    try:
        if ("--pause" in sys.argv) or (len(sys.argv) == 1 and sys.stdin and sys.stdin.isatty()):
            sys.stdout.flush()
            input("Press Enter to exit...")
    except Exception:
        pass
    sys.exit(exit_code)
