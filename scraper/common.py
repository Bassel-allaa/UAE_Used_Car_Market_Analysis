"""
common.py — shared utilities for the multi-source UAE used-car scraper.

Drop this into: D:\\Final_Projects\\dubizzle-uae-cars\\src\\common.py

Used by every extractor (dubicars.py, autotraders.py, opensooq.py) so cleaning
logic and request handling stays consistent across sources.
"""

import re
import time
import random
import json
import hashlib
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any

import requests
from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
)
logger = logging.getLogger("scraper")

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
}

CITY_MAP = {
    "dubai": "Dubai",
    "abu-dhabi": "Abu Dhabi",
    "abudhabi": "Abu Dhabi",
    "abu dhabi": "Abu Dhabi",
    "sharjah": "Sharjah",
    "ajman": "Ajman",
    "ras-al-khaimah": "Ras Al Khaimah",
    "ras al khaimah": "Ras Al Khaimah",
    "rak": "Ras Al Khaimah",
    "fujairah": "Fujairah",
    "umm-al-quwain": "Umm Al Quwain",
    "umm al quwain": "Umm Al Quwain",
    "al-ain": "Al Ain",
    "al ain": "Al Ain",
}

RAW_COLUMNS = [
    "source", "listing_id", "name", "brand", "model", "year",
    "transmission", "mileage_km", "price_aed", "city", "url",
]


# --------------------------------------------------------------------------
# Networking
# --------------------------------------------------------------------------

def new_session() -> requests.Session:
    """Fresh session per batch, matching the pattern that worked for CarSwitch."""
    s = requests.Session()
    s.headers.update(DEFAULT_HEADERS)
    return s


def get_soup(session: requests.Session, url: str, timeout: int = 15) -> Optional[BeautifulSoup]:
    """GET a page and return parsed soup, or None on failure/non-200."""
    try:
        resp = session.get(url, timeout=timeout)
    except requests.RequestException as e:
        logger.warning(f"Request failed for {url}: {e}")
        return None

    if resp.status_code == 429:
        logger.warning(f"HTTP 429 (throttled) for {url}")
        return None
    if resp.status_code != 200:
        logger.warning(f"HTTP {resp.status_code} for {url}")
        logger.warning(f"Response headers: {dict(resp.headers)}")
        snippet = resp.text[:500].replace("\n", " ")
        logger.warning(f"Response body snippet: {snippet}")
        return None

    return BeautifulSoup(resp.text, "html.parser")


def polite_delay(min_s: float = 5.0, max_s: float = 9.0):
    """Random delay between individual page requests. Same rhythm as CarSwitch."""
    time.sleep(random.uniform(min_s, max_s))


# --------------------------------------------------------------------------
# JSON-LD extraction (try this first on every site — cheap, structured, and
# it's what made CarSwitch trivial to scrape)
# --------------------------------------------------------------------------

def extract_json_ld_items(soup: BeautifulSoup) -> List[dict]:
    """Pull every JSON-LD block off a page, flattened into a list of dicts.
    Handles @graph and itemListElement wrapping, which car-listing sites
    commonly use for SEO structured data.
    """
    items: List[dict] = []
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = tag.string or tag.get_text()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue

        candidates = data if isinstance(data, list) else [data]
        for d in candidates:
            if not isinstance(d, dict):
                continue
            if "@graph" in d and isinstance(d["@graph"], list):
                items.extend(x for x in d["@graph"] if isinstance(x, dict))
            elif "itemListElement" in d and isinstance(d["itemListElement"], list):
                for el in d["itemListElement"]:
                    item = el.get("item", el) if isinstance(el, dict) else None
                    if isinstance(item, dict):
                        items.append(item)
            else:
                items.append(d)
    return items


def filter_vehicle_items(items: List[dict]) -> List[dict]:
    """Keep only JSON-LD items that look like a vehicle/car/product listing."""
    wanted_types = {"car", "vehicle", "product"}
    out = []
    for item in items:
        t = item.get("@type")
        types = {t.lower()} if isinstance(t, str) else {x.lower() for x in (t or [])}
        if types & wanted_types:
            out.append(item)
    return out


def extract_next_data(soup: BeautifulSoup) -> Optional[dict]:
    """Pull the __NEXT_DATA__ JSON blob out of a Next.js-rendered page."""
    tag = soup.find("script", id="__NEXT_DATA__")
    if not tag or not tag.string:
        return None
    try:
        return json.loads(tag.string)
    except json.JSONDecodeError:
        return None


def find_listing_arrays(obj: Any, min_items: int = 5, required_keywords: Optional[List[str]] = None) -> Optional[List[dict]]:
    """Recursively search a nested JSON structure (e.g. __NEXT_DATA__) for
    the array that holds individual listings. Returns the largest list of
    dicts found anywhere in the tree with at least `min_items` entries.

    If `required_keywords` is given (e.g. ["price"]), a candidate array only
    qualifies if its items actually contain a key matching each keyword —
    this matters because Next.js data blobs often contain several large
    arrays (taxonomies, filter chips, "popular models" widgets) that are
    NOT the listings, and a plain "biggest list of dicts" heuristic can
    grab one of those instead.
    """
    candidates: List[list] = []

    def item_has_keywords(d: dict) -> bool:
        if not required_keywords:
            return True
        keys_lower = [k.lower() for k in d.keys()]
        return all(any(kw in k for k in keys_lower) for kw in required_keywords)

    def walk(o):
        if isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            if len(o) >= min_items and all(isinstance(x, dict) for x in o):
                sample = o[:3]
                if all(item_has_keywords(x) for x in sample):
                    candidates.append(o)
            for x in o:
                walk(x)

    walk(obj)
    if not candidates:
        return None
    return max(candidates, key=len)


def deep_find_value(obj: Any, keywords: List[str], max_depth: int = 3, _depth: int = 0):
    """Recursively search a dict/list for the first scalar value whose key
    contains any of `keywords` (case-insensitive). Used to pull fields like
    price/mileage/year out of a listing dict without knowing its exact
    schema in advance.
    """
    if _depth > max_depth:
        return None
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, (str, int, float)) and any(kw in k.lower() for kw in keywords):
                return v
        for v in obj.values():
            result = deep_find_value(v, keywords, max_depth, _depth + 1)
            if result is not None:
                return result
    elif isinstance(obj, list):
        for item in obj:
            result = deep_find_value(item, keywords, max_depth, _depth + 1)
            if result is not None:
                return result
    return None


# --------------------------------------------------------------------------
# Field cleaning
# --------------------------------------------------------------------------

def clean_price(text: Optional[str]) -> Optional[int]:
    if text is None:
        return None
    s = re.sub(r"[^\d]", "", str(text))
    return int(s) if s else None


def clean_mileage(text: Optional[str]) -> Optional[int]:
    if text is None:
        return None
    s = str(text).lower()
    match = re.search(r"([\d,]+)", s)
    if not match:
        return None
    value = int(match.group(1).replace(",", ""))
    if "mile" in s and "km" not in s:
        value = round(value * 1.60934)
    return value


def clean_year(text) -> Optional[int]:
    if text is None:
        return None
    match = re.search(r"\b(19|20)\d{2}\b", str(text))
    return int(match.group()) if match else None


def normalize_city(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    key = str(text).strip().lower()
    return CITY_MAP.get(key, str(text).strip().title())


BRANDS = [
    "Land Rover", "Range Rover", "Mercedes-Benz", "Mercedes", "Rolls-Royce",
    "Aston Martin", "Alfa Romeo", "Great Wall", "Toyota", "Nissan", "Honda",
    "Hyundai", "Kia", "BMW", "Audi", "Porsche", "Lexus", "Infiniti", "Ford",
    "Chevrolet", "GMC", "Cadillac", "Jeep", "MG", "Geely", "Chery", "Tesla",
    "Suzuki", "Mazda", "Renault", "Peugeot", "Volkswagen", "Volvo", "Jaguar",
    "Maserati", "Bentley", "Ferrari", "Lamborghini", "McLaren", "Dodge",
    "Chrysler", "Subaru", "Mitsubishi", "MINI", "Citroen", "Skoda", "Fiat",
    "Lincoln", "Genesis", "BYD", "Haval", "Changan", "JAC", "GAC",
]


def extract_brand_model(title: Optional[str]):
    """Best-effort brand/model split from a free-text listing title."""
    if not title:
        return None, None
    for b in BRANDS:
        idx = title.lower().find(b.lower())
        if idx != -1:
            rest = title[idx + len(b):].strip()
            rest = re.sub(r"^\s*(19|20)\d{2}\s*", "", rest)
            words = rest.split()
            model = words[0] if words else None
            if model and len(words) > 1 and model.lower() in ("grand", "range", "land", "model"):
                model = " ".join(words[:2])
            return b, model
    return None, None


def make_listing_id(source: str, url_or_key: str) -> str:
    return hashlib.md5(f"{source}:{url_or_key}".encode()).hexdigest()[:12]


# --------------------------------------------------------------------------
# Pagination helper — discovers the next-page URL from the page itself
# instead of assuming a query-param pattern, since that varies per site
# and I couldn't verify it without seeing live markup.
# --------------------------------------------------------------------------

def find_next_page_url(soup: BeautifulSoup, current_url: str) -> Optional[str]:
    from urllib.parse import urljoin

    link = soup.find("a", attrs={"rel": "next"})
    if link and link.get("href"):
        return urljoin(current_url, link["href"])

    link = soup.find("link", attrs={"rel": "next"})
    if link and link.get("href"):
        return urljoin(current_url, link["href"])

    for a in soup.find_all("a", href=True):
        text = a.get_text(strip=True).lower()
        if text in ("next", "›", "»", "next page") or "next" in (a.get("aria-label", "").lower()):
            return urljoin(current_url, a["href"])

    return None


def save_batch(rows: List[Dict[str, Any]], out_path: Path):
    import pandas as pd
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows, columns=RAW_COLUMNS)
    df.to_csv(out_path, index=False)
    logger.info(f"Saved {len(df)} rows -> {out_path}")
