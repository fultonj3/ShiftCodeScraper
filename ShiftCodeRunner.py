"""
Multi-user SHiFT runner.

- Loads users from .env
- Scrapes for new codes
- Redeems new codes per user in one browser session
- Updates CSV with per-user redeemed status
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from dotenv import load_dotenv

import ShiftCodeScraper as scraper
import ShiftCodeRedeemer as redeemer


@dataclass
class User:
    name: str
    username: str
    password: str
    platform: int
    browser: str = "chrome"
    headless: bool = False


PLATFORM_MAP = {
    "steam": 1,
    "epic": 2,
    "xbox": 3,
    "playstation": 4,
    "ps": 4,
}


def parse_platform(value: str | int | None) -> int:
    if value is None:
        return 1
    if isinstance(value, int):
        return value
    s = str(value).strip().lower()
    if s.isdigit():
        try:
            n = int(s)
            return n if n in (1, 2, 3, 4) else 1
        except ValueError:
            return 1
    return PLATFORM_MAP.get(s, 1)


def load_users_from_env() -> List[User]:
    users_var = os.getenv("USERS", "").strip()
    if not users_var:
        raise SystemExit("USERS not set in .env; expected comma-separated names (e.g., USERS=alice,bob)")
    names = [n.strip() for n in users_var.split(",") if n.strip()]
    users: List[User] = []
    for name in names:
        prefix = f"SHIFT_{name}_"
        uname = os.getenv(prefix + "USERNAME", "").strip()
        pwd = os.getenv(prefix + "PASSWORD", "").strip()
        plat_raw = os.getenv(prefix + "PLATFORM", "1")
        browser = os.getenv(prefix + "BROWSER", "chrome").strip().lower()
        headless = os.getenv(prefix + "HEADLESS", "false").strip().lower() in ("1", "true", "yes", "y")
        if not uname or not pwd:
            raise SystemExit(f"Missing credentials for user '{name}' (need {prefix}USERNAME and {prefix}PASSWORD)")
        users.append(
            User(
                name=name,
                username=uname,
                password=pwd,
                platform=parse_platform(plat_raw),
                browser=browser if browser in ("chrome", "edge") else "chrome",
                headless=headless,
            )
        )
    return users


def setup_logger() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def ensure_user_columns(csv_path: Path, users: List[User]) -> None:
    """Ensure the CSV has per-user redeemed columns (Redeemed:<name>)."""
    import csv as _csv
    if not csv_path.exists():
        scraper.ensure_csv_header(csv_path)
    # Read all rows via csv reader (handles commas in fields)
    rows: List[List[str]] = []
    with csv_path.open("r", newline="", encoding="utf-8") as f:
        reader = _csv.reader(f)
        rows = [r for r in reader]
    if not rows:
        scraper.ensure_csv_header(csv_path)
        with csv_path.open("r", newline="", encoding="utf-8") as f:
            reader = _csv.reader(f)
            rows = [r for r in reader]
    header = rows[0]
    changed = False
    for u in users:
        col = f"Redeemed:{u.name}"
        if col not in header:
            header.append(col)
            changed = True
    if not changed:
        return
    # Pad each data row to header length with 'No'
    for i in range(1, len(rows)):
        while len(rows[i]) < len(header):
            rows[i].append("No")
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = _csv.writer(f)
        writer.writerows(rows)


def set_user_status(csv_path: Path, code: str, user: str, yes: bool) -> None:
    import csv as _csv
    with csv_path.open("r", newline="", encoding="utf-8") as f:
        rows = [r for r in _csv.reader(f)]
    header = rows[0]
    col = f"Redeemed:{user}"
    if col not in header:
        header.append(col)
    col_idx = header.index(col)
    code_idx = 0  # 'Code'
    for i in range(1, len(rows)):
        row = rows[i]
        while len(row) < len(header):
            row.append("No")
        if (row[code_idx] or "").strip().upper() == code.strip().upper():
            row[col_idx] = "Yes" if yes else "No"
        rows[i] = row
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = _csv.writer(f)
        writer.writerows([header] + rows[1:])


def collect_new_codes(csv_path: Path, url: str) -> tuple[List[str], dict[str, str]]:
    """Scrape and append any new codes; return (new_codes, expirations_map)."""
    scraper.ensure_csv_header(csv_path)
    existing = scraper.read_existing_codes(csv_path)
    html = scraper.fetch_html(url)
    scraped = scraper.extract_codes(html)
    # Exclude expired section
    expired = scraper.extract_expired_codes(html)
    if expired:
        scraped = [c for c in scraped if c not in expired]
    new_codes = [c for c in scraped if c not in existing]
    # Write with expiration mapping
    exp_map = scraper.extract_code_expirations(html)
    import datetime as dt
    today = dt.datetime.now().strftime("%Y-%m-%d")
    scraper.write_new_codes(csv_path, new_codes, today, expirations=exp_map)
    return new_codes, exp_map


def main() -> int:
    setup_logger()
    load_dotenv()

    csv_path = Path(os.getenv("CSV_PATH", scraper.DEFAULT_CSV))
    url = os.getenv("SCRAPER_URL", scraper.DEFAULT_URL)
    users = load_users_from_env()

    logging.info("Found %d user(s)", len(users))
    new_codes, exp_map = collect_new_codes(csv_path, url)
    if not new_codes:
        logging.info("No new codes found. Nothing to redeem.")
        return 0

    ensure_user_columns(csv_path, users)

    # Track per-user successful redemptions for webhook summary
    user_success: Dict[str, int] = {}

    for u in users:
        logging.info("Redeeming %d code(s) for %s", len(new_codes), u.name)
        results: Dict[str, str] = redeemer.redeem_codes_session(
            new_codes,
            browser=u.browser,
            headless=u.headless,
            username=u.username,
            password=u.password,
            platform=u.platform,
        )
        success_count = 0
        for code, status in results.items():
            is_success = isinstance(status, str) and ("successfully redeemed" in status.lower())
            ok = isinstance(status, str) and (
                "successfully redeemed" in status.lower() or "already redeemed" in status.lower()
            )
            if not ok and str(status).lower().startswith("error:"):
                logging.error("%s: %s -> %s", u.name, code, status)
            elif not ok:
                logging.warning("%s: %s -> %s", u.name, code, status)
            else:
                logging.info("%s: %s -> %s", u.name, code, status)
            set_user_status(csv_path, code, u.name, ok)
            if is_success:
                success_count += 1
        user_success[u.name] = success_count

    # Optional Discord webhook summary including per-user success counts
    webhook_url = os.getenv("DISCORD_WEBHOOK", "").strip()
    if webhook_url and new_codes:
        try:
            scraper.post_discord_webhook_with_summary(
                webhook_url=webhook_url,
                codes=new_codes,
                expirations=exp_map,
                user_success_counts=user_success,
                total_attempted=len(new_codes),
            )
            logging.info("Posted new codes + redemption summary to Discord webhook.")
        except Exception as e:
            logging.warning("Discord webhook failed: %s", e)

    logging.info("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
