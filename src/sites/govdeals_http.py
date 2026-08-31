import base64
import uuid
from typing import Any, Dict
from urllib.parse import quote

from src.core.config import target_state_names


GOVDEALS_SEARCH_URL = "https://maestro.lqdt1.com/search/list"
GOVDEALS_DETAIL_URL_TEMPLATE = "https://maestro.lqdt1.com/assets/{asset_id}/{account_id}/false"


def _target_state_names() -> list[str]:
    return target_state_names() or ["Texas"]


def _escape_facet_value(value: str) -> str:
    return value.replace(" ", "\\ ")


def _govdeals_state_filters() -> list[str]:
    return [
        f'{{!tag=stateDesc}}stateDesc:"{_escape_facet_value(state_name)}"'
        for state_name in _target_state_names()
    ]


def _build_govdeals_filtered_url() -> str:
    state_names = "^".join(_target_state_names())
    slug = _target_state_names()[0].lower().replace(" ", "-")
    return (
        f"https://www.govdeals.com/en/transportation/{slug}/filters"
        f"?stateName={quote(state_names)}&so=asc&sf=auctionclose"
    )


GOVDEALS_FILTERED_URL = _build_govdeals_filtered_url()
GOVDEALS_SUBSCRIPTION_KEY = "cf620d1d8f904b5797507dc5fd1fdb80"
GOVDEALS_API_KEY = "af93060f-337e-428c-87b8-c74b5837d6cd"
DEFAULT_GOVDEALS_BIZ_ID = "GD"
DEFAULT_GOVDEALS_SITE_ID = 1

CHROME_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/149.0.0.0 Safari/537.36"
)
SEC_CH_UA = '"Google Chrome";v="149", "Chromium";v="149", "Not)A;Brand";v="24"'


def govdeals_page_unique_id() -> str:
    return base64.b64encode(GOVDEALS_FILTERED_URL.encode("utf-8")).decode("ascii")


def build_govdeals_headers() -> Dict[str, str]:
    return {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Content-Type": "application/json",
        "Origin": "https://www.govdeals.com",
        "Referer": "https://www.govdeals.com/",
        "User-Agent": CHROME_USER_AGENT,
        "Ocp-Apim-Subscription-Key": GOVDEALS_SUBSCRIPTION_KEY,
        "x-api-key": GOVDEALS_API_KEY,
        "x-user-id": "-1",
        "x-user-timezone": "America/Chicago",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "cross-site",
        "sec-ch-ua": SEC_CH_UA,
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "x-api-correlation-id": str(uuid.uuid4()),
        "x-ecom-session-id": str(uuid.uuid4()),
        "x-page-unique-id": govdeals_page_unique_id(),
        "x-referer": GOVDEALS_FILTERED_URL,
    }


def build_govdeals_page_headers() -> Dict[str, str]:
    return {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.govdeals.com/",
        "User-Agent": CHROME_USER_AGENT,
    }


def build_govdeals_search_payload(page: int = 1) -> Dict[str, Any]:
    return {
        "categoryIds": "",
        "businessId": DEFAULT_GOVDEALS_BIZ_ID,
        "searchText": "*",
        "isQAL": False,
        "locationId": None,
        "model": "",
        "makebrand": "",
        "auctionTypeId": None,
        "page": page,
        "displayRows": 120,
        "sortField": "auctionclose",
        "sortOrder": "asc",
        "sessionId": str(uuid.uuid4()),
        "requestType": "search",
        "responseStyle": "fullResponse",
        "facets": [
            "categoryName",
            "auctionTypeID",
            "condition",
            "saleEventName",
            "sellerDisplayName",
            "product_pricecents",
            "isReserveMet",
            "hasBuyNowPrice",
            "isReserveNotMet",
            "sellerType",
            "warehouseId",
            "region",
            "currencyTypeCode",
            "countryDesc",
            "stateDesc",
            "city",
            "tierId",
        ],
        "facetsFilter": [
            '{!tag=product_category_external_id}product_category_external_id:"t6"',
            '{!tag=region}region:"Americas"',
            '{!tag=countryDesc}countryDesc:"United\\ States\\ of\\ America"',
            *_govdeals_state_filters(),
        ],
        "timeType": "",
        "sellerTypeId": None,
        "accountIds": [],
    }


def build_govdeals_detail_payload() -> Dict[str, Any]:
    return {
        "businessId": DEFAULT_GOVDEALS_BIZ_ID,
        "siteId": DEFAULT_GOVDEALS_SITE_ID,
    }


def safe_govdeals_headers(headers: Dict[str, str]) -> Dict[str, str]:
    safe = dict(headers)
    for key in ("Ocp-Apim-Subscription-Key", "x-api-key"):
        if key in safe:
            safe[key] = "<redacted>"
    return safe


def prime_govdeals_session(session) -> None:
    try:
        session.get(
            GOVDEALS_FILTERED_URL,
            headers=build_govdeals_page_headers(),
            timeout=30,
        )
    except Exception as exc:
        print(f"GovDeals anonymous session warmup failed; continuing without cookies: {exc}")
