"""
inspect_outliers.py - one-time diagnostic, not part of the regular pipeline.

Pulls out the rows flagged by finalize_dataset.py as price/mileage suspects
so you can eyeball them before deciding whether to exclude, fix, or keep
them as-is.

Usage:
    python scraper/inspect_outliers.py
"""

from pathlib import Path
import pandas as pd

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 200)


def main():
    project_root = Path(__file__).resolve().parent.parent
    df = pd.read_csv(project_root / "data" / "processed" / "uae_cars_final_clean.csv")

    cols = ["source", "name", "brand", "model", "year", "mileage_km", "price_aed", "city", "url"]

    price_outliers = df.loc[df["price_suspect"], cols].sort_values("price_aed")
    mileage_outliers = df.loc[df["mileage_suspect"], cols].sort_values("mileage_km", ascending=False)

    out_dir = project_root / "data" / "processed"
    price_outliers.to_csv(out_dir / "_outliers_price.csv", index=False)
    mileage_outliers.to_csv(out_dir / "_outliers_mileage.csv", index=False)

    print(f"Price outliers ({len(price_outliers)} rows) -> {out_dir / '_outliers_price.csv'}")
    print(price_outliers.to_string())
    print()
    print(f"Mileage outliers ({len(mileage_outliers)} rows) -> {out_dir / '_outliers_mileage.csv'}")
    print(mileage_outliers.to_string())


if __name__ == "__main__":
    main()
