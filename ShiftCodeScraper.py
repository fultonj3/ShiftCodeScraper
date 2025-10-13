"""
Shift Code Scraper for Borderlands 4

Purpose
- Scrapes SHiFT codes from a specified webpage and stores them in a CSV.
- Validates code format via regex and avoids duplicates.

CSV columns
- Code, Date Added (YYYY-MM-DD), Expiration, Redeemed (Yes/No)

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
    """Ensure CSV exists with a header including Expiration.

    - If the file does not exist or is empty, create with header:
      Code, Date Added, Expiration, Redeemed
    - If an older header (without Expiration) is detected as the first line,
      upgrade the header in-place while preserving existing rows.
    """
    desired_header = ["Code", "Date Added", "Expiration", "Redeemed"]

    if not path.exists() or path.stat().st_size == 0:
        mode = "x" if not path.exists() else "w"
        with path.open(mode, newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(desired_header)
        return

    # Attempt header upgrade if we detect the older 3-column header
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        if lines:
            first = lines[0].strip().lower()
            if first == ",".join(["code", "date added", "redeemed"]):
                # Rewrite with new header, insert blank Expiration for existing rows if any
                upgraded = [",".join(desired_header)]
                for row in csv.reader(lines[1:]):
                    if not row:
                        continue
                    # Insert empty Expiration between Date Added and Redeemed
                    if len(row) >= 3:
                        upgraded.append(
                            ",".join([row[0], row[1], "", row[2]])
                        )
                    else:
                        upgraded.append(
                            ",".join([row[0] if row else "", "", "", "No"])
                        )
                path.write_text("\n".join(upgraded) + "\n", encoding="utf-8")
    except Exception:
        # Be conservative: if anything odd, leave file as-is
        pass


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


def _collect_code_tokens_from_node_text(text: str) -> List[str]:
    tokens: List[str] = []
    for token in re.split(r"[^A-Za-z0-9-]+", text or ""):
        token = token.strip().upper()
        if token and CODE_REGEX.match(token):
            tokens.append(token)
    return tokens


def extract_code_expirations(html: str) -> dict[str, str]:
    """Extract a mapping of code -> expiration text from the Active codes table.

    Strategy: find the table following the "All Active Borderlands 4 SHiFT Codes"
    header. Rows tend to come in pairs: the first contains the code, the next
    contains reward and expiration. We pair them and pull the expiration text.

    Returns a dict mapping code (uppercased) to a human-readable expiration
    string (e.g., "No expiration", "Unknown Expiration ...", or the contents of
    the rendered event text such as "October 12, 2025 ...").
    """
    soup = BeautifulSoup(html, "html.parser")

    # Locate the Active section table
    active_anchor = soup.find(id="All_Active_Borderlands_4_SHiFT_Codes")
    table = None
    if active_anchor:
        h = active_anchor.find_parent(["h2", "h3"]) or active_anchor
        table = h.find_next("table")
    if not table:
        # Fallback: scan for the first table that contains a Limited-Time header
        for th in soup.find_all("th"):
            text = (th.get_text(strip=True) or "").lower()
            if "limited-time" in text or "permanent" in text:
                table = th.find_parent("table")
                if table:
                    break
    if not table:
        return {}

    trs = table.find_all("tr", recursive=True)
    mapping: dict[str, str] = {}
    i = 0
    while i < len(trs):
        tr = trs[i]
        # Find code(s) in this row
        row_codes: list[str] = []
        # Search text
        row_codes.extend(_collect_code_tokens_from_node_text(tr.get_text(" ", strip=True)))
        # Search attributes in inputs/labels as a bonus
        for tag in tr.find_all(True):
            for val in tag.attrs.values():
                if isinstance(val, str):
                    row_codes.extend(_collect_code_tokens_from_node_text(val))
                elif isinstance(val, Sequence):
                    for v in val:
                        if isinstance(v, str):
                            row_codes.extend(_collect_code_tokens_from_node_text(v))
        # Deduplicate
        row_codes = sorted({c.upper() for c in row_codes})

        if row_codes:
            # Default expiration text
            expiration = ""
            # Look ahead one row for the details
            if i + 1 < len(trs):
                nxt = trs[i + 1]
                # Prefer the second cell if present
                cells = nxt.find_all("td")
                exp_container = cells[1] if len(cells) >= 2 else nxt
                # If there is a div with class simple-event, take its text; else whole cell text
                evt = exp_container.find(class_="simple-event")
                if evt and evt.get_text(strip=True):
                    expiration = evt.get_text(" ", strip=True)
                else:
                    t = exp_container.get_text(" ", strip=True)
                    # Normalize common patterns
                    if not t:
                        expiration = ""
                    elif "no expiration" in t.lower():
                        expiration = "No expiration"
                    elif "unknown expiration" in t.lower():
                        # Keep the whole message so the user sees the last-checked note
                        expiration = t
                    else:
                        expiration = t
            # Record for all codes found in this row
            for code in row_codes:
                mapping[code] = expiration
            # Skip the following row as it's paired details
            i += 2
            continue

        i += 1

    return mapping


def _chunked(seq: Sequence[str], size: int) -> Iterable[Sequence[str]]:
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def post_discord_webhook(
    webhook_url: str,
    codes: Sequence[str],
    expirations: dict[str, str] | None = None,
    batch_size: int = 10,
) -> None:
    """Post newly found codes to a Discord webhook.

    To ensure all codes appear in a single message block per batch across
    Discord clients, this composes one embed per message and lists each code
    as a bullet line in the embed description: `CODE` — expiration.
    The description has a 4096 character limit; we chunk safely.
    """
    exp_map = {k.upper(): v for k, v in (expirations or {}).items()}

    if not codes:
        return

    # Reasonable line budget per message so we stay under 4096 chars
    # Fallback to original batch_size if provided explicitly
    max_chars = 3900
    session = requests_session()

    # Build lines once
    lines = [f"• `{code}` — {exp_map.get(code.upper(), '') or 'Unknown'}" for code in codes]

    current: list[str] = []
    current_len = 0
    def flush():
        nonlocal current, current_len
        if not current:
            return
        description = "\n".join(current)
        embed = {
            "title": "New Borderlands 4 SHiFT Codes",
            "url": DEFAULT_URL,
            "color": 0xBF1313,
            "description": description,
        }
        payload = {"embeds": [embed], "allowed_mentions": {"parse": []}}
        resp = session.post(webhook_url, json=payload, timeout=10)
        if resp.status_code not in (200, 204):
            raise RuntimeError(f"Webhook HTTP {resp.status_code}: {resp.text[:200]}")
        current = []
        current_len = 0

    for line in lines:
        # If adding this line would exceed our budget, flush first
        if current and (current_len + 1 + len(line) > max_chars):
            flush()
        current.append(line)
        current_len += (1 + len(line)) if current_len else len(line)

    flush()


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


def write_new_codes(
    path: Path,
    codes: Iterable[str],
    date_str: str,
    dry_run: bool = False,
    expirations: dict[str, str] | None = None,
) -> int:
    """Append new codes to CSV with date, expiration (if known), and default Redeemed flag.

    Returns the number of codes written.
    """
    exp_map = {k.upper(): v for k, v in (expirations or {}).items()}

    if dry_run:
        for code in codes:
            logging.info(
                "Would add code: %s (expires: %s)", code, exp_map.get(code.upper(), "")
            )
        return len(list(codes))

    wrote = 0
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        for code in codes:
            expiration = exp_map.get(code.upper(), "")
            writer.writerow([code, date_str, expiration, "No"])
            logging.info("Added code: %s%s", code, f" (expires: {expiration})" if expiration else "")
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
    # Optional Discord webhook for notifications
    parser.add_argument(
        "--discord-webhook",
        dest="discord_webhook",
        default=None,
        help="Discord webhook URL to post newly found codes (optional)",
    )
    parser.add_argument(
        "--webhook-batch-size",
        type=int,
        default=10,
        help="Max embeds per Discord message (default: 10; Discord limit)",
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

    # Build expiration mapping from the Active table for context in CSV
    exp_map = extract_code_expirations(html)
    today = dt.datetime.now().strftime("%Y-%m-%d")
    wrote = write_new_codes(
        csv_path, new_codes, today, dry_run=args.dry_run, expirations=exp_map
    )
    # Optionally post to Discord webhook if configured and not a dry run
    if (not args.dry_run) and args.discord_webhook and new_codes:
        try:
            post_discord_webhook(
                webhook_url=args.discord_webhook,
                codes=new_codes,
                expirations=exp_map,
                batch_size=args.webhook_batch_size,
            )
            logging.info("Posted %d new code(s) to Discord webhook.", len(new_codes))
        except Exception as e:
            logging.warning("Discord webhook failed: %s", e)
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
