"""
SHiFT Code Redeemer (Selenium scaffold)

Usage examples:
  python ShiftCodeRedeemer.py ABCDE-FGHIJ-KLMNO-PQRST UVWXY-ZABCD-EFGHI-JKLMN
  python ShiftCodeRedeemer.py --headless ABCDE-FGHIJ-KLMNO-PQRST
  python ShiftCodeRedeemer.py --browser edge --url https://shift.gearboxsoftware.com/rewards CODE1 CODE2

This script sets up Selenium, opens a Chromium-based browser (Chrome by default),
and navigates to a hardcoded SHiFT rewards URL. It accepts any number of codes
as positional command-line arguments. Element selection for login and redemption
is intentionally left as TODOs so you can practice XPath.

Requirements (install once):
  pip install selenium webdriver-manager
"""

from __future__ import annotations

import argparse
import sys
from typing import List, Dict
import os

from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By

from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.microsoft import EdgeChromiumDriverManager


# Configurable constants
DEFAULT_URL = "https://shift.gearboxsoftware.com/rewards"

# Placeholder creds and platform (can be overridden via CLI/env)
# Options: 1 - Steam, 2 - Epic Games, 3 - Xbox, 4 - PlayStation
USERNAME = os.getenv("SHIFT_USERNAME", "")
PASSWORD = os.getenv("SHIFT_PASSWORD", "")
try:
    PLATFORM = int(os.getenv("SHIFT_PLATFORM", "1"))
except ValueError:
    PLATFORM = 1


def create_driver(
    browser: str,
    headless: bool = False,
    user_data_dir: str | None = None,
    binary_path: str | None = None,
):
    """Create and return a Selenium WebDriver for a Chromium-based browser.

    Args:
        browser: "chrome" or "edge".
        headless: Run without UI if True.
        user_data_dir: Optional path to a browser profile (to keep session/cookies).
        binary_path: Optional explicit browser binary path.
    """
    # If not provided, honor CHROME_PROFILE_DIR/BROWSER_PROFILE_DIR from the environment
    if not user_data_dir:
        user_data_dir = os.getenv("CHROME_PROFILE_DIR") or os.getenv(
            "BROWSER_PROFILE_DIR"
        )
    if browser == "edge":
        options = EdgeOptions()
        # Use Chromium Edge
        options.use_chromium = True
        if headless:
            options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1440,900")
        # options.add_argument("--remote-debugging-port=0")
        options.add_argument("--remote-debugging-pipe")
        if user_data_dir:
            options.add_argument(f"--user-data-dir={user_data_dir}")
        if binary_path:
            options.binary_location = binary_path

        service = EdgeService(EdgeChromiumDriverManager().install())
        driver = webdriver.Edge(service=service, options=options)
        return driver

    # Default to Chrome
    options = ChromeOptions()
    # options.add_experimental_option("detach", True)
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1440,900")
    options.add_argument("--remote-debugging-port=0")
    if user_data_dir:
        options.add_argument(f"--user-data-dir={user_data_dir}")
    if binary_path:
        options.binary_location = binary_path

    service = ChromeService(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    return driver


def login(
    driver,
    wait: WebDriverWait,
    username: str | None = None,
    password: str | None = None,
) -> None:

    print("[i] Logging in...")

    sign_in_btn = wait.until(
        EC.element_to_be_clickable((By.XPATH, "//input[@value='SIGN IN']"))
    )
    user_field = wait.until(
        EC.presence_of_element_located((By.XPATH, "//input[@id='user_email']"))
    )
    pass_field = wait.until(
        EC.presence_of_element_located((By.XPATH, "//input[@id='user_password']"))
    )

    user_field.send_keys(username or USERNAME)
    pass_field.send_keys(password or PASSWORD)
    sign_in_btn.click()

    print("[i] Login success!")


def go_to_rewards_page(driver, wait: WebDriverWait, url: str) -> None:
    print(f"[i] Navigating to: {url}")
    driver.get(url)
    # Wait for a known element on the rewards page (adjust as needed later)
    # This is safe to keep generic for now.
    wait.until(lambda d: d.execute_script("return document.readyState") == "complete")


def redeem_code(
    driver, wait: WebDriverWait, code: str, platform: int | None = None
) -> str:
    """Redeem a single SHiFT code. Returns True on apparent success.

    TODO: Replace placeholders with real XPath interactions once you inspect the page.
    Suggested flow:
      - Locate the code input box
      - Enter the code
      - Choose PLATFORM if required
      - Click Redeem / Submit
      - Wait for confirmation or error toast
    """
    print(f"[i] Redeeming code: {code}")
    # Example placeholders:
    # input_box = wait.until(EC.element_to_be_clickable((By.XPATH, "//input[@name='code']")))
    # input_box.clear(); input_box.send_keys(code)
    # driver.find_element(By.XPATH, "//button[.='Redeem']").click()
    # result = wait.until(EC.presence_of_element_located((By.XPATH, "//div[contains(@class,'toast')]")))
    # return "success" in result.text.lower()

    # Get the input box, send the code, and click check
    input_box = wait.until(
        EC.element_to_be_clickable((By.XPATH, "//input[@id='shift_code_input']"))
    )
    input_box.clear()
    input_box.send_keys(code)
    driver.find_element(By.XPATH, "//button[@id='shift_code_check']").click()

    # Check for validity
    wait.until(
        EC.presence_of_element_located(
            (By.XPATH, "//div[@class='sh_status_container_code_redemption']")
        )
    )
    error_check_one = driver.find_element(
        By.XPATH, "//div[@id='shift_code_instructions']"
    )
    error_check_two = driver.find_element(By.XPATH, "//div[@id='shift_code_error']")
    if (
        error_check_one.get_attribute("style") != "display: none;"
        or error_check_two.get_attribute("style") != "display: none;"
    ):
        print(f"[x] Invalid code: {code}")
        return "Invalid Code"
    # Select platform and redeem
    wait.until(
        EC.presence_of_element_located(
            (By.XPATH, "//form[@class='new_archway_code_redemption']")
        )
    )
    match (platform or PLATFORM):
        case 1:
            driver.find_element(By.XPATH, "//input[@value='Redeem for Steam']").click()
        case 2:
            driver.find_element(By.XPATH, "//input[@value='Redeem for Epic']").click()
        case 3:
            driver.find_element(
                By.XPATH, "//input[@value='Redeem for Xbox Live']"
            ).click()
    redeem_results = wait.until(
        EC.presence_of_element_located((By.XPATH, "//div[@class='alert notice']/p"))
    )
    if "successfully redeemed" in redeem_results.text.lower():
        return "Successfully Redeemed"

    return "Already Redeemed"


def redeem_codes_session(
    codes: List[str],
    *,
    browser: str = "chrome",
    headless: bool = False,
    url: str = DEFAULT_URL,
    user_data_dir: str | None = None,
    binary_path: str | None = None,
    wait_timeout: int = 20,
    username: str | None = None,
    password: str | None = None,
    platform: int | None = None,
) -> Dict[str, str]:
    """Redeem multiple codes in one browser session. Returns code->status."""
    driver = create_driver(
        browser=browser,
        headless=headless,
        user_data_dir=user_data_dir,
        binary_path=binary_path,
    )
    results: Dict[str, str] = {}
    try:
        wait = WebDriverWait(driver, wait_timeout)
        go_to_rewards_page(driver, wait, url)
        login(driver, wait, username=username, password=password)
        for code in codes:
            try:
                status = redeem_code(driver, wait, code, platform=platform)
            except Exception as e:
                status = f"Error: {e}"
            results[code] = status
    finally:
        try:
            driver.quit()
        except Exception:
            pass
    return results


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="SHiFT code redeemer (Selenium scaffold)"
    )
    parser.add_argument("codes", nargs="+", help="One or more SHiFT codes to redeem")
    parser.add_argument(
        "--browser",
        choices=["chrome", "edge"],
        default="chrome",
        help="Browser to use (default: chrome)",
    )
    parser.add_argument(
        "--headless", action="store_true", help="Run the browser headless"
    )
    parser.add_argument(
        "--url", default=DEFAULT_URL, help="Rewards page URL (override if needed)"
    )
    parser.add_argument(
        "--profile",
        dest="user_data_dir",
        help="Path to a browser profile (keeps session/cookies)",
    )
    parser.add_argument(
        "--binary",
        dest="binary_path",
        help="Explicit browser binary path (if non-standard)",
    )
    parser.add_argument(
        "--wait",
        type=int,
        default=20,
        help="Explicit wait timeout in seconds (default: 20)",
    )
    parser.add_argument(
        "--username", help="SHiFT account username (or env SHIFT_USERNAME)"
    )
    parser.add_argument(
        "--password", help="SHiFT account password (or env SHIFT_PASSWORD)"
    )
    parser.add_argument(
        "--platform",
        type=int,
        choices=[1, 2, 3, 4],
        help="Platform: 1 Steam, 2 Epic, 3 Xbox, 4 PlayStation (or env SHIFT_PLATFORM)",
    )
    return parser.parse_args(argv)


def main(argv: List[str]) -> int:
    args = parse_args(argv)

    print(f"[i] Starting Selenium with {args.browser} (headless={args.headless})")
    driver = create_driver(
        browser=args.browser,
        headless=args.headless,
        user_data_dir=args.user_data_dir,
        binary_path=args.binary_path,
    )

    try:
        wait = WebDriverWait(driver, args.wait)
        go_to_rewards_page(driver, wait, args.url)

        # Optional: perform login (leave as TODO for your XPath work)
        login(driver, wait)

        # Iterate through provided codes
        successes = 0
        for code in args.codes:
            ok = redeem_code(driver, wait, code)
            if ok:
                print(f"[✓] Redeemed: {code}")
                successes += 1
            else:
                print(f"[x] Could not confirm redemption: {code}")

        print(f"[i] Finished. {successes}/{len(args.codes)} codes confirmed.")
        return 0

    finally:
        print("[i] Closing browser")
        driver.quit()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
