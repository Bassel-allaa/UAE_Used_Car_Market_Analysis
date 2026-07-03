"""
diagnostic_report.py - one-time diagnostic, not part of the regular pipeline.

Dumps a full picture of the combined dataset (data/processed/uae_cars_combined_deduped.csv)
so we can plan the cleaning/EDA/analysis rebuild against real numbers instead
of piecemeal discoveries. Run once, share the output file, and we build the
brand_segment map + cleaning logic in one pass.

Usage:
    python scraper/diagnostic_report.py
"""

from pathlib import Path
import pandas as pd

pd.set_option("display.max_rows", None)


def main():
    project_root = Path(__file__).resolve().parent.parent
    path = project_root / "data" / "processed" / "uae_cars_combined_deduped.csv"
    df = pd.read_csv(path)

    out_path = project_root / "data" / "processed" / "_diagnostic_report.txt"
    lines = []

    def add(title, content):
        lines.append(f"\n{'='*70}\n{title}\n{'='*70}")
        lines.append(str(content))

    add("SHAPE", df.shape)
    add("COLUMNS + DTYPES", df.dtypes)
    add("NULL COUNTS", df.isna().sum())

    add("BRAND VALUE COUNTS (all)", df["brand"].value_counts(dropna=False).to_string())
    add("TOP 60 MODELS", df["model"].value_counts(dropna=False).head(60).to_string())
    add("CITY VALUE COUNTS", df["city"].value_counts(dropna=False).to_string())
    add("SOURCE VALUE COUNTS", df["source"].value_counts(dropna=False).to_string())
    add("TRANSMISSION VALUE COUNTS", df["transmission"].value_counts(dropna=False).to_string())

    add("YEAR describe()", df["year"].describe())
    add("YEAR value_counts (sorted)", df["year"].value_counts(dropna=False).sort_index().to_string())

    add("PRICE_AED describe()", df["price_aed"].describe())
    add("MILEAGE_KM describe()", df["mileage_km"].describe())

    # Rows missing critical fields - worth seeing which source they come from
    add("Rows with null brand, by source", df.loc[df["brand"].isna(), "source"].value_counts())
    add("Rows with null price_aed, by source", df.loc[df["price_aed"].isna(), "source"].value_counts())
    add("Rows with null year, by source", df.loc[df["year"].isna(), "source"].value_counts())
    add("Rows with null mileage_km, by source", df.loc[df["mileage_km"].isna(), "source"].value_counts())
    add("Rows with null model, by source", df.loc[df["model"].isna(), "source"].value_counts())

    # Duplicate URL check - sanity check dedup didn't miss exact-URL repeats
    add("Exact duplicate URLs remaining", df["url"].duplicated().sum())

    report = "\n".join(lines)
    out_path.write_text(report, encoding="utf-8")
    print(f"Wrote full diagnostic report -> {out_path}")
    print(f"({len(report)} chars) - please upload this file")


if __name__ == "__main__":
    main()
