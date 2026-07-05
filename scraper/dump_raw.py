"""
dump_raw.py - one-time diagnostic, not part of the regular pipeline.

Saves the raw response Python actually receives from each site to disk, so
we can inspect real structure directly instead of guessing at heuristics
that keep grabbing the wrong nested array.

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
