"""
dump_raw.py - one-time diagnostic, not part of the regular pipeline.

Saves the raw response Python actually receives from each site to disk, so
we can inspect real structure directly instead of guessing at heuristics
that keep grabbing the wrong nested array.

Usage:
    python scraper/dump_raw.py opensooq
    python scraper/dump_raw.py autotraders

What to do with the output:

  opensooq -> writes data/raw/_debug_opensooq_next_data.json
    Open it in VS Code, Ctrl+F for a price you saw in the CSV (e.g. "60000")
    or a brand name ("Nissan"). Look at the key path around that match -
    paste me ~10-15 lines of context and I'll hardcode the exact path
    instead of the current "biggest array with a price key" guess.

  autotraders -> writes data/raw/_debug_autotraders_raw.html
    Open it and Ctrl+F for "car-card" or "AED" or a car you saw on the
    site (e.g. "Kia K5"). Two outcomes:
      - FOUND -> the data is embedded in the raw response (likely as a
        Next.js React Server Components payload inside a <script> tag,
        not standard HTML). Tell me and I'll write a parser for that.
      - NOT FOUND -> it's genuinely fetched by JS after load. We need the
        real network request from DevTools (try the "Fetch" filter, not
        just "XHR", and check if it only fires after scrolling).
"""

import sys
import json
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))
from common import new_session, get_soup, extract_next_data, logger

OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"


def dump_opensooq():
    session = new_session()
    soup = get_soup(session, "https://ae.opensooq.com/en/cars/cars-for-sale")
    if soup is None:
        logger.error("Fetch failed, nothing to dump")
        return
    next_data = extract_next_data(soup)
    if not next_data:
        logger.error("No __NEXT_DATA__ found")
        return
    out_path = OUT_DIR / "_debug_opensooq_next_data.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(next_data, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"Wrote {out_path} ({out_path.stat().st_size / 1024:.0f} KB) - open it and search for a real price/brand")


def dump_autotraders():
    session = new_session()
    session.get("https://uae.autotraders.ae/")  # warm up, harmless either way
    resp = session.get("https://uae.autotraders.ae/used-cars", timeout=15)
    out_path = OUT_DIR / "_debug_autotraders_raw.html"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(resp.text, encoding="utf-8")
    logger.info(f"HTTP {resp.status_code}, wrote {out_path} ({len(resp.text) / 1024:.0f} KB)")

    for needle in ["car-card", "AED", "self.__next_f.push"]:
        count = resp.text.count(needle)
        logger.info(f"  occurrences of '{needle}': {count}")


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in ("opensooq", "autotraders"):
        print("Usage: python scraper/dump_raw.py [opensooq|autotraders]")
        sys.exit(1)
    if sys.argv[1] == "opensooq":
        dump_opensooq()
    else:
        dump_autotraders()
