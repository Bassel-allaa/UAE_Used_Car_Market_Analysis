"""
recon.py — RUN THIS FIRST, for each site, before trusting the extractors.

I (Claude) confirmed these three sites return real pages with no bot-block
wall, but I can't see raw HTML/CSS class names from here the way your
browser's dev tools can. This script dumps what actually exists on the page
so we can lock in real selectors instead of guessed ones.

Usage:
    python src/recon.py https://www.dubicars.com/dubai/used
    python src/recon.py https://uae.autotraders.ae/used-cars
    python src/recon.py https://ae.opensooq.com/en/cars/cars-for-sale

What to do with the output:
    1. Check "JSON-LD blocks found" — if it lists Car/Vehicle/Product types,
       tell me and I'll switch that extractor to pure JSON-LD (easiest case).
    2. Check "Candidate listing links" — these are hrefs that look like
       individual listing pages. Paste me 3-4 real examples and I'll write
       an exact regex/selector instead of the generic one.
    3. Check "Pagination candidates" — tells us if next-page is a
       rel="next" link, a "Next" button, or numbered links, so
       find_next_page_url() in common.py actually works.
    4. Open one listing URL in your browser, right-click a price/mileage
       element -> Inspect, and send me the class name if the fallback
       parser in the extractor doesn't pick it up correctly on a test run.
"""

import sys
import re
from collections import Counter
from urllib.parse import urljoin

from common import new_session, get_soup, extract_json_ld_items, find_next_page_url


def recon(url: str):
    session = new_session()
    soup = get_soup(session, url)
    if soup is None:
        print(f"Could not fetch {url} — check the URL or your connection.")
        return

    print("=" * 70)
    print(f"URL: {url}")
    print(f"Page title: {soup.title.string.strip() if soup.title else '(none)'}")
    print(f"Raw HTML length: {len(str(soup))} chars")

    # 1. JSON-LD
    items = extract_json_ld_items(soup)
    print(f"\nJSON-LD blocks found: {len(items)}")
    if items:
        types = Counter(str(i.get("@type")) for i in items)
        for t, count in types.most_common(10):
            print(f"    @type={t}: {count}")
        print("    Sample keys of first item:", list(items[0].keys())[:15])

    # 2. Look for a Next.js / Nuxt / __NEXT_DATA__ style embedded JSON blob
    next_data = soup.find("script", id="__NEXT_DATA__")
    print(f"\n__NEXT_DATA__ present: {bool(next_data)}")
    nuxt_data = soup.find("script", id="__NUXT_DATA__")
    print(f"__NUXT_DATA__ present: {bool(nuxt_data)}")

    # 3. Candidate listing links: hrefs containing digits (common for listing
    #    IDs) that aren't nav/footer boilerplate
    hrefs = [a.get("href") for a in soup.find_all("a", href=True)]
    candidates = [h for h in hrefs if re.search(r"\d{4,}", h or "")]
    candidates = [urljoin(url, h) for h in candidates]
    counter = Counter(candidates)
    print(f"\nCandidate listing links (href containing 4+ digit numbers): {len(counter)} unique")
    for link, _ in counter.most_common(8):
        print(f"    {link}")

    # 4. Pagination
    next_url = find_next_page_url(soup, url)
    print(f"\nfind_next_page_url() result: {next_url}")
    numbered = [a for a in soup.find_all("a", href=True) if a.get_text(strip=True).isdigit()]
    print(f"Numbered pagination links found: {len(numbered)}")
    if numbered:
        print("    e.g.:", [urljoin(url, a['href']) for a in numbered[:5]])

    # 5. Rough listing count on page (elements mentioning AED, a strong
    #    signal for price blocks even without knowing the class name)
    aed_hits = len(re.findall(r"AED\s?[\d,]+", soup.get_text()))
    print(f"\nText occurrences of 'AED <number>': {aed_hits} (rough proxy for # of listings on page)")
    print("=" * 70)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python src/recon.py <url>")
        sys.exit(1)
    recon(sys.argv[1])
