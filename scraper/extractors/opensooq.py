import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

sys.path.append(str(Path(__file__).resolve().parent.parent))
from common import (
    new_session, get_soup, polite_delay, save_batch, logger,
    extract_next_data, clean_price, clean_mileage, clean_year,
    normalize_city, make_listing_id,
)

SOURCE_NAME = "opensooq"
BASE_SEARCH_URL = "https://ae.opensooq.com/en/cars/cars-for-sale"
DOMAIN = "https://ae.opensooq.com"


def parse_listing(item: dict) -> Optional[Dict[str, Any]]:
    title = item.get("title")
    if not title:
        return None

    # highlights format: "Nissan " Frontier " 2,022 " Used" (raguleft/right
    # angle-quote separators observed in the dump - split defensively)
    highlights = item.get("highlights", "") or ""
    parts = [p.strip() for p in highlights.replace("\u00bb", "|").split("|") if p.strip()]
    brand = parts[0] if len(parts) > 0 else None
    model = parts[1] if len(parts) > 1 else None
    year = clean_year(title)  # more reliable than parts[2], which is comma-formatted e.g. "2,022"

    price = clean_price(item.get("price_amount"))
    mileage = clean_mileage(item.get("kilometers_Cars_value_i"))
    city = normalize_city(item.get("city_label")) if item.get("city_label") else None

    post_url = item.get("post_url") or ""
    url = f"{DOMAIN}{post_url}" if post_url.startswith("/") else post_url

    listing_id = item.get("id")

    return {
        "source": SOURCE_NAME,
        "listing_id": make_listing_id(SOURCE_NAME, str(listing_id) if listing_id else url),
        "name": title,
        "brand": brand,
        "model": model,
        "year": year,
        "transmission": None,  # not present in this payload; leave blank
        "mileage_km": mileage,
        "price_aed": price,
        "city": city,
        "url": url,
    }


def parse_page(soup, url: str) -> List[Dict[str, Any]]:
    next_data = extract_next_data(soup)
    if not next_data:
        logger.warning(f"No __NEXT_DATA__ found on {url}")
        return []

    try:
        items = next_data["props"]["pageProps"]["serpApiResponse"]["listings"]["items"]
    except (KeyError, TypeError):
        logger.warning(f"Expected listings path not found in __NEXT_DATA__ for {url} "
                        f"- site structure may have changed since this was built")
        return []

    results = []
    for item in items:
        parsed = parse_listing(item)
        if parsed:
            results.append(parsed)
    return results


def scrape_batch(start_page: int, num_pages: int, batch_name: str, out_dir: Path, checkpoint_every: int = 20):
    session = new_session()
    all_rows = []
    out_path = out_dir / f"opensooq_{batch_name}.csv"

    try:
        for i, page_num in enumerate(range(start_page, start_page + num_pages), start=1):
            url = BASE_SEARCH_URL if page_num == 1 else f"{BASE_SEARCH_URL}?page={page_num}"
            logger.info(f"[opensooq] page {page_num}: {url}")
            soup = get_soup(session, url)
            if soup is None:
                break

            rows = parse_page(soup, url)
            if not rows:
                logger.info(f"[opensooq] no listings found on page {page_num}, stopping")
                break

            all_rows.extend(rows)
            logger.info(f"[opensooq] +{len(rows)} listings (running total {len(all_rows)})")

            if i % checkpoint_every == 0:
                save_batch(all_rows, out_path)
                logger.info(f"[opensooq] checkpoint saved at page {page_num}")

            polite_delay()
    except KeyboardInterrupt:
        logger.warning("[opensooq] interrupted by user - saving what was collected so far")
    except Exception as e:
        logger.error(f"[opensooq] crashed: {e} - saving what was collected so far")

    save_batch(all_rows, out_path)
    return all_rows


if __name__ == "__main__":
    out_dir = Path(__file__).resolve().parent.parent.parent / "data" / "raw"
    scrape_batch(start_page=1, num_pages=400, batch_name="master_raw", out_dir=out_dir)
