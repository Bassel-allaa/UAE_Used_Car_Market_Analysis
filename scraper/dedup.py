"""
dedup.py - cross-source deduplication.

Drop into: D:\\Final_Projects\\dubizzle-uae-cars\\src\\dedup.py
(overwrite the previous version - dubicars removed since that site is off
the list, and this version documents the schema mismatch between
carswitch_clean.csv (already has engineered features) and the two raw
master files (not yet cleaned) - see merge_and_dedup() notes below.

Usage:
    python scraper/dedup.py
"""

import logging
from pathlib import Path
from itertools import combinations
from typing import Optional

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s")
logger = logging.getLogger("dedup")


def make_hash(row) -> str:
    """Fuzzy key: brand + model + year + price-bucket(1000) + mileage-bucket(1000).
    Deliberately ignores city and exact price/mileage so the same physical
    car cross-posted with slightly different rounding still matches.
    """
    brand = str(row.get("brand") or "").strip().lower()
    model = str(row.get("model") or "").strip().lower()
    year = str(int(row.get("year")) if pd.notna(row.get("year")) else 0)

    price = row.get("price_aed")
    price_bucket = str(int(price // 1000)) if pd.notna(price) else "na"

    mileage = row.get("mileage_km")
    mileage_bucket = str(int(mileage // 1000)) if pd.notna(mileage) else "na"

    return f"{brand}:{model}:{year}:{price_bucket}:{mileage_bucket}"


def load_source(path: Path, source_name: str) -> Optional[pd.DataFrame]:
    if not path.exists():
        logger.warning(f"Not found, skipping: {path}")
        return None
    df = pd.read_csv(path)
    if "source" not in df.columns:
        df["source"] = source_name
    df["_hash"] = df.apply(make_hash, axis=1)
    logger.info(f"Loaded {len(df)} rows from {source_name}")
    return df


def pairwise_overlap_report(frames: dict):
    """Print duplicate-rate stats between every pair of sources."""
    print("\n--- Cross-source overlap ---")
    for (name_a, df_a), (name_b, df_b) in combinations(frames.items(), 2):
        hashes_a = set(df_a["_hash"])
        hashes_b = set(df_b["_hash"])
        overlap = hashes_a & hashes_b
        pct_a = 100 * len(overlap) / len(hashes_a) if hashes_a else 0
        pct_b = 100 * len(overlap) / len(hashes_b) if hashes_b else 0
        print(f"{name_a} <-> {name_b}: {len(overlap)} shared listings "
              f"({pct_a:.1f}% of {name_a}, {pct_b:.1f}% of {name_b})")


def merge_and_dedup(data_dir: Path, output_path: Path):
    # NOTE on schema: carswitch_clean.csv already went through 02_cleaning.ipynb
    # (has car_age, price_tier, brand_segment, mileage_per_year on top of the
    # base columns). The two new raw files don't have those yet - that's
    # expected. pd.concat aligns by column name and fills missing ones with
    # NaN, so this merge is safe; you'll re-run feature engineering on the
    # FULL combined set afterward (step 3 in the guide) rather than trying
    # to patch the engineered columns in here.
    sources = {
        "carswitch": data_dir / "processed" / "carswitch_clean.csv",
        "autotraders": data_dir / "raw" / "autotraders_master_raw.csv",
        "opensooq": data_dir / "raw" / "opensooq_master_raw.csv",
    }

    frames = {}
    for name, path in sources.items():
        df = load_source(path, name)
        if df is not None:
            frames[name] = df

    if not frames:
        logger.error("No source files found. Check paths in `sources` above.")
        return

    pairwise_overlap_report(frames)

    combined = pd.concat(frames.values(), ignore_index=True)
    before = len(combined)

    # Keep first occurrence of each fuzzy hash. Priority order: carswitch >
    # autotraders > opensooq (matches dict order above via pd.concat order) -
    # so if the same car is cross-posted, the carswitch version wins. Change
    # the dict order above if you'd rather a different source win.
    combined = combined.drop_duplicates(subset="_hash", keep="first")
    after = len(combined)

    combined = combined.drop(columns=["_hash"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(output_path, index=False)

    print(f"\nCombined rows before dedup: {before}")
    print(f"Combined rows after dedup:  {after}")
    print(f"Removed as duplicates:      {before - after} ({100*(before-after)/before:.1f}%)")
    print(f"Saved -> {output_path}")


if __name__ == "__main__":
    project_root = Path(__file__).resolve().parent.parent
    merge_and_dedup(
        data_dir=project_root / "data",
        output_path=project_root / "data" / "processed" / "uae_cars_combined_deduped.csv",
    )
