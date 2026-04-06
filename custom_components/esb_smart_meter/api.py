import json
import logging
import random
import re
import time
from datetime import datetime, timezone
from io import StringIO

import requests
from bs4 import BeautifulSoup

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://myaccount.esbnetworks.ie"
LOGIN_BASE = "https://login.esbnetworks.ie"
B2C_TENANT = "esbntwkscustportalprdb2c01.onmicrosoft.com"
B2C_POLICY = "B2C_1A_signup_signin"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
]


def _sleep(lo=1.5, hi=4.0):
    time.sleep(random.uniform(lo, hi))


class ESBNetworksAPI:
    def __init__(self, username: str, password: str, mprn: str, cache_path: str):
        self._username = username
        self._password = password
        self._mprn = mprn.replace(" ", "").strip()
        self._cache_path = cache_path
        self._session = None
        self._ua = random.choice(USER_AGENTS)

    def _base_headers(self):
        return {
            "User-Agent": self._ua,
            "Accept-Language": "en-IE,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
        }

    def _load_cached_session(self):
        try:
            with open(self._cache_path) as f:
                data = json.load(f)
            cookies = data.get("cookies", {})
            saved_at = data.get("saved_at", 0)
            age_hours = (time.time() - saved_at) / 3600
            if age_hours > 12:
                _LOGGER.info("ESB: cached session expired (%.1fh old)", age_hours)
                return None
            _LOGGER.info("ESB: loaded cached session (%.1fh old)", age_hours)
            return cookies
        except Exception:
            return None

    def _save_session(self, session: requests.Session):
        try:
            cookies = dict(session.cookies)
            with open(self._cache_path, "w") as f:
                json.dump({"cookies": cookies, "saved_at": time.time()}, f)
            _LOGGER.info("ESB: session cached")
        except Exception as e:
            _LOGGER.warning("ESB: could not cache session: %s", e)

    def _validate_session(self, cookies: dict) -> bool:
        """Check if cached session cookies still work."""
        try:
            s = requests.Session()
            s.headers.update(self._base_headers())
            for k, v in cookies.items():
                s.cookies.set(k, v)
            # GET portal page — returns 200 if authenticated, 302 if session expired
            r = s.get(f"{BASE_URL}/Api/HistoricConsumption", timeout=15, allow_redirects=False)
            if r.status_code == 200:
                _LOGGER.info("ESB: cached session is valid")
                self._session = s
                return True
            _LOGGER.warning("ESB: cached session invalid (status %s)", r.status_code)
        except Exception as e:
            _LOGGER.warning("ESB: session validation error: %s", e)
        return False

    def _login(self) -> bool:
        """Perform full Azure B2C login flow."""
        _LOGGER.info("ESB: starting login flow")
        s = requests.Session()
        s.headers.update(self._base_headers())

        # Step 1 — GET homepage, follow redirect to B2C login, extract SETTINGS
        try:
            r1 = s.get(BASE_URL, timeout=20)
            r1.raise_for_status()
        except Exception as e:
            _LOGGER.error("ESB: step 1 failed: %s", e)
            return False

        settings_match = re.findall(r"(?<=var SETTINGS = )\S*;", r1.text)
        if not settings_match:
            _LOGGER.error("ESB: could not find SETTINGS in login page")
            return False
        try:
            settings = json.loads(settings_match[0].rstrip(";"))
        except Exception as e:
            _LOGGER.error("ESB: could not parse SETTINGS JSON: %s", e)
            return False

        csrf = settings.get("csrf")
        trans_id = settings.get("transId")
        if not csrf or not trans_id:
            _LOGGER.error("ESB: missing csrf or transId in SETTINGS")
            return False

        _sleep()

        # Step 2 — POST credentials to SelfAsserted
        self_asserted_url = (
            f"{LOGIN_BASE}/{B2C_TENANT}/{B2C_POLICY}/SelfAsserted"
            f"?tx={trans_id}&p={B2C_POLICY}"
        )
        try:
            r2 = s.post(
                self_asserted_url,
                data={
                    "signInName": self._username,
                    "password": self._password,
                    "request_type": "RESPONSE",
                },
                headers={
                    "x-csrf-token": csrf,
                    "X-Requested-With": "XMLHttpRequest",
                    "Origin": LOGIN_BASE,
                    "Referer": r1.url,
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                    "Accept": "application/json, text/javascript, */*; q=0.01",
                },
                allow_redirects=False,
                timeout=20,
            )
        except Exception as e:
            _LOGGER.error("ESB: step 2 (SelfAsserted) failed: %s", e)
            return False

        try:
            r2_json = r2.json()
        except Exception:
            r2_json = {}
        if str(r2_json.get("status")) != "200":
            _LOGGER.error("ESB: login rejected (bad credentials?): %s", r2_json)
            return False

        _sleep()

        # Step 3 — GET confirmed page, extract hidden form
        confirmed_url = (
            f"{LOGIN_BASE}/{B2C_TENANT}/{B2C_POLICY}/api/CombinedSigninAndSignup/confirmed"
            f"?rememberMe=false&csrf_token={csrf}&tx={trans_id}&p={B2C_POLICY}"
        )
        try:
            r3 = s.get(confirmed_url, timeout=20)
            r3.raise_for_status()
        except Exception as e:
            _LOGGER.error("ESB: step 3 (confirmed) failed: %s", e)
            return False

        if "captcha" in r3.text.lower() or "robot" in r3.text.lower():
            _LOGGER.error("ESB: CAPTCHA detected — rate limit hit. Will retry next cycle.")
            return False

        soup3 = BeautifulSoup(r3.text, "html.parser")
        form = soup3.find("form", {"id": "auto"})
        if not form:
            _LOGGER.error("ESB: could not find auto-submit form in confirmed page")
            return False

        action_url = form.get("action", "")
        form_data = {inp.get("name"): inp.get("value", "") for inp in form.find_all("input") if inp.get("name")}

        _sleep()

        # Step 4 — POST to signin-oidc
        try:
            r4 = s.post(
                action_url,
                data=form_data,
                headers={
                    "Origin": LOGIN_BASE,
                    "Referer": r3.url,
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                allow_redirects=False,
                timeout=20,
            )
        except Exception as e:
            _LOGGER.error("ESB: step 4 (signin-oidc) failed: %s", e)
            return False

        _sleep()

        # Step 5 — GET myaccount homepage to finalise session
        try:
            r5 = s.get(BASE_URL, headers={"Referer": LOGIN_BASE}, timeout=20)
            r5.raise_for_status()
        except Exception as e:
            _LOGGER.error("ESB: step 5 (homepage finalise) failed: %s", e)
            return False

        _sleep(0.5, 1.5)

        _LOGGER.info("ESB: login successful")
        self._session = s
        self._save_session(s)
        return True

    def _get_xsrf_token(self) -> str | None:
        try:
            r = self._session.get(
                f"{BASE_URL}/af/t",
                headers={
                    "X-Returnurl": f"{BASE_URL}/Api/HistoricConsumption",
                    "Referer": f"{BASE_URL}/Api/HistoricConsumption",
                    "Accept": "*/*",
                },
                timeout=15,
            )
            r.raise_for_status()
            return r.json().get("token")
        except Exception as e:
            _LOGGER.error("ESB: failed to get XSRF token: %s", e)
            return None

    def download_csv(self) -> str | None:
        """Ensure authenticated, then POST to DownloadHdfPeriodic for CSV data."""
        # Try cached session first
        cached = self._load_cached_session()
        if cached and self._validate_session(cached):
            pass  # self._session set by _validate_session
        else:
            if not self._login():
                return None

        token = self._get_xsrf_token()
        if not token:
            # Session may have expired mid-flight — try fresh login
            _LOGGER.warning("ESB: no XSRF token, retrying with fresh login")
            if not self._login():
                return None
            token = self._get_xsrf_token()
        if not token:
            _LOGGER.error("ESB: could not get XSRF token after fresh login")
            return None

        _sleep(0.5, 1.5)

        try:
            r = self._session.post(
                f"{BASE_URL}/DataHub/DownloadHdfPeriodic",
                json={"mprn": self._mprn, "searchType": "intervalkwh"},
                headers={
                    "X-Xsrf-Token": token,
                    "X-Returnurl": f"{BASE_URL}/Api/HistoricConsumption",
                    "Referer": f"{BASE_URL}/Api/HistoricConsumption",
                    "Origin": BASE_URL,
                    "Content-Type": "application/json",
                },
                timeout=60,
            )
            r.raise_for_status()
        except Exception as e:
            _LOGGER.error("ESB: CSV download failed: %s", e)
            return None

        ct = r.headers.get("Content-Type", "")
        if len(r.content) < 100:
            _LOGGER.error("ESB: response too short (%d bytes): %s", len(r.content), r.text[:200])
            return None

        _LOGGER.info("ESB: downloaded %d bytes (ct=%s)", len(r.content), ct)
        return r.text


def parse_csv(csv_text: str) -> list[dict]:
    """Parse ESB CSV into list of {dt: datetime, kwh: float} for Active Import only."""
    import csv
    results = []
    reader = csv.DictReader(StringIO(csv_text))
    for row in reader:
        try:
            read_type = row.get("Read Type", "").strip()
            # Only import consumption, skip export rows
            if "Active Import" not in read_type:
                continue
            dt_str = row.get("Read Date and End Time", "").strip()
            value_str = row.get("Read Value", "").strip()
            if not dt_str or not value_str:
                continue
            dt = datetime.strptime(dt_str, "%d-%m-%Y %H:%M").replace(tzinfo=timezone.utc)
            kwh = float(value_str)
            results.append({"dt": dt, "kwh": kwh})
        except (ValueError, KeyError):
            continue
    results.sort(key=lambda x: x["dt"])
    _LOGGER.info("ESB: parsed %d import datapoints from CSV", len(results))
    return results
