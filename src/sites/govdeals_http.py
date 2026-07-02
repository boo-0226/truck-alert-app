import os
import uuid
from typing import Any, Dict


GOVDEALS_SUBSCRIPTION_KEY = "cf620d1d8f904b5797507dc5fd1fdb80"
GOVDEALS_API_KEY = "af93060f-337e-428c-87b8-c74b5837d6cd"
DEFAULT_GOVDEALS_BIZ_ID = "GD"
DEFAULT_GOVDEALS_SITE_ID = 1
GOVDEALS_TOKEN_MISSING_MESSAGE = "GovDeals API token missing"
GOVDEALS_UNAUTHORIZED_MESSAGE = "GovDeals API token expired or unauthorized"

CHROME_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/138.0.0.0 Safari/537.36"
)
SEC_CH_UA = '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"'


def _env_value(name: str) -> str:
    return os.getenv(name, "").strip()


def govdeals_access_token() -> str:
    return _env_value("GOVDEALS_ACCESS_TOKEN")


def govdeals_refresh_token() -> str:
    return _env_value("GOVDEALS_REFRESH_TOKEN")


def govdeals_user_id() -> str:
    return _env_value("GOVDEALS_USER_ID")


def govdeals_biz_id(default: str = DEFAULT_GOVDEALS_BIZ_ID) -> str:
    return _env_value("GOVDEALS_BIZ_ID") or default


def govdeals_site_id(default: Any = DEFAULT_GOVDEALS_SITE_ID) -> Any:
    raw = _env_value("GOVDEALS_SITE_ID")
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return raw


def build_govdeals_headers() -> Dict[str, str]:
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Origin": "https://www.govdeals.com",
        "Referer": "https://www.govdeals.com/",
        "User-Agent": CHROME_USER_AGENT,
        "Ocp-Apim-Subscription-Key": GOVDEALS_SUBSCRIPTION_KEY,
        "x-api-key": GOVDEALS_API_KEY,
        "x-user-timezone": "America/Chicago",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "cross-site",
        "sec-ch-ua": SEC_CH_UA,
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "x-api-correlation-id": str(uuid.uuid4()),
        "x-ecom-session-id": str(uuid.uuid4()),
    }

    access_token = govdeals_access_token()
    if access_token:
        if access_token.lower().startswith("bearer "):
            headers["Authorization"] = access_token
        else:
            headers["Authorization"] = f"Bearer {access_token}"

    user_id = govdeals_user_id()
    if user_id:
        headers["x-user-id"] = user_id

    return headers
