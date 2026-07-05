import sys
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
from urllib.parse import urljoin

sys.path.append(str(Path(__file__).resolve().parent.parent))
from common import (
    new_session, get_soup, polite_delay, save_batch, logger,
    find_next_page_url, clean_price, clean_mileage, clean_year,
    normalize_city, make_listing_id,
)

SOURCE_NAME = "autotraders"
START_URL = "https://uae.autotraders.ae/used-cars"


def parse_card(card, page_url: str) -> Optional[Dict[str, Any]]:
    link = card.find("a", class_="car-card-content-link") or card.find("a", class_="car-card-media-link")
    if not link or not link.get("href"):
        return None
    url = urljoin(page_url, link["href"])

    title_el = card.find("h2", class_="car-card-title")
    title = title_el.get_text(" ", strip=True) if title_el else None

    subline_el = card.find("div", class_="car-card-subline")
    brand, model = None, None
    if subline_el:
        subline = subline_el.get_text(" ", strip=True)
        pieces = [p.strip() for p in re.split(r"\s+-\s+", subline) if p.strip()]
        if len(pieces) >= 2:
            brand, model = pieces[0], pieces[1]
        elif pieces:
            brand = pieces[0]

    meta_el = card.find("div", class_="car-card-meta")
    city = None
    if meta_el:
        meta_text = meta_el.get_text(" ", strip=True)
        m = re.search(r"Cars in (.+)", meta_text)
        city = normalize_city(m.group(1).strip()) if m else None

    year, mileage = None, None
    for chip in card.find_all("span", class_="chip"):
        chip_text = chip.get_text(" ", strip=True)
        if chip_text.lower().startswith("year"):
            year = clean_year(chip_text)
        elif chip_text.lower().startswith("km"):
            mileage = clean_mileage(chip_text)

    price_el = card.find(class_="car-card-price-amount")
    price = clean_price(price_el.get_text(" ", strip=True)) if price_el else None

    if not year:
        year = clean_year(title)

    return {
        "source": SOURCE_NAME,
        "listing_id": make_listing_id(SOURCE_NAME, url),
        "name": title,
        "brand": brand,
        "model": model,
        "year": year,
        "transmission": None,
        "mileage_km": mileage,
        "price_aed": price,
        "city": city,
        "url": url,
    }


def parse_page(soup, url: str) -> List[Dict[str, Any]]:
    results = []
    for card in soup.find_all("div", class_="car-card"):
        parsed = parse_card(card, url)
        if parsed:
            results.append(parsed)
    return results


def scrape_batch(max_pages: int, batch_name: str, out_dir: Path, checkpoint_every: int = 20):
    session = new_session()
    all_rows = []
    url = START_URL
    page_num = 1
    out_path = out_dir / f"autotraders_{batch_name}.csv"

    try:
        while url and page_num <= max_pages:
            logger.info(f"[autotraders] page {page_num}: {url}")
            soup = get_soup(session, url)
            if soup is None:
                break

            rows = parse_page(soup, url)
            if not rows:
                logger.info(f"[autotraders] no car-card listings found on page {page_num}, stopping")
                break

            all_rows.extend(rows)
            logger.info(f"[autotraders] +{len(rows)} listings (running total {len(all_rows)})")

            if page_num % checkpoint_every == 0:
                save_batch(all_rows, out_path)
                logger.info(f"[autotraders] checkpoint saved at page {page_num}")

            next_url = find_next_page_url(soup, url)
            if not next_url or next_url == url:
                logger.info("[autotraders] no next-page link found, stopping")
                break
            url = next_url
            page_num += 1
            polite_delay()
    except KeyboardInterrupt:
        logger.warning("[autotraders] interrupted by user - saving what was collected so far")
    except Exception as e:
        logger.error(f"[autotraders] crashed: {e} - saving what was collected so far")

    save_batch(all_rows, out_path)
    return all_rows


if __name__ == "__main__":
    out_dir = Path(__file__).resolve().parent.parent.parent / "data" / "raw"
    scrape_batch(max_pages=750, batch_name="master_raw", out_dir=out_dir)
