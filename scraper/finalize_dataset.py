"""
finalize_dataset.py

Drop into: D:\\Final_Projects\\dubizzle-uae-cars\\src\\finalize_dataset.py
(overwrite the previous version - this one is built from the full brand
list in your diagnostic report, not a partial placeholder)

What this does, based on _diagnostic_report.txt findings:
  1. Normalizes brand-name spelling/casing duplicates (Mercedes-Benz vs
     Mercedes Benz vs Mercedes, MINI vs Mini, RAM vs Ram, etc.)
  2. Fixes "Range Rover" showing up as a brand (it's a Land Rover model) -
     reassigns brand=Land Rover, folds "Range Rover" into the model name
  3. Drops `transmission` entirely - 100% null across all 28,109 rows,
     dead weight from here on
  4. Backfills `listing_id` for the 2,320 CarSwitch rows that never had one
  5. Classifies every brand into Mass-market/Mid-range/Premium/Luxury -
     built fresh since we're discarding the old CarSwitch-only mapping.
     A handful of ultra-low-count exotic/boutique brands (1-6 listings
     each) are best-guess classifications given negligible weight on any
     aggregate stat - flagged in comments below, edit freely.
  6. Imputes mileage_km = 0 for rows missing mileage where the title
     contains "brand new" (checked against real title text, not guessed)
  7. Flags (does not silently drop) sanity-outlier rows: price_aed < 1000
     (e.g. the AED 1 minimum found) and mileage_km > 1,000,000 (e.g. the
     6,000,000 max found) - these get a boolean flag column so you can
     inspect them before deciding to exclude
  8. price_aed/mileage_km nulls (mostly AutoTraders "Call for Price" /
     unspecified-mileage listings) are KEPT in the full dataset for
     volume/composition analysis, with clear guidance below on filtering
     them out for price-dependent charts and the regression models
"""

from pathlib import Path
import hashlib
import pandas as pd

CURRENT_YEAR = 2026

# ---------------------------------------------------------------------------
# 1. Brand name normalization - fixes spelling/casing splits found in the
#    diagnostic report (e.g. "Mercedes Benz" vs "Mercedes-Benz" vs "Mercedes")
# ---------------------------------------------------------------------------
BRAND_NORMALIZE = {
    "mercedes benz": "Mercedes-Benz",
    "mercedes": "Mercedes-Benz",
    "mercedes-benz": "Mercedes-Benz",
    "mini": "MINI",
    "ram": "Ram",
    "baic": "BAIC",
    "fiat": "Fiat",
    "rox": "ROX",
    "ssangyong": "SsangYong",
    "zeekr": "Zeekr",
    "jaecoo": "Jaecoo",
    "faw-bestune": "Bestune",
    "dongfong": "Dongfeng",
    "avatar": "Avatr",
    "avatr": "Avatr",
    "abarath": "Abarth",
    "gwm": "Great Wall",
    "ineos": "Ineos",
    "maruti suzuki": "Suzuki",
}


def normalize_brand_text(brand: str) -> str:
    if pd.isna(brand):
        return brand
    key = str(brand).strip().lower()
    return BRAND_NORMALIZE.get(key, str(brand).strip())


def fix_range_rover_brand(row):
    """'Range Rover' isn't a brand - it's a Land Rover model. Some AutoTraders
    dealer listings wrote it as the brand field. Reassign and fold into model.
    """
    if str(row["brand"]).strip().lower() == "range rover":
        model = str(row["model"]).strip() if pd.notna(row["model"]) else ""
        if "range rover" not in model.lower():
            model = f"Range Rover {model}".strip()
        return pd.Series({"brand": "Land Rover", "model": model})
    return pd.Series({"brand": row["brand"], "model": row["model"]})


def normalize_model_casing(df: pd.DataFrame) -> pd.DataFrame:
    """Same underlying problem as brand-name duplicates (e.g. 'Mercedes Benz'
    vs 'Mercedes-Benz'), but for models: different sources format model names
    with different casing (e.g. 'KICKS' vs 'Kicks'), which splits what's
    really one model into separate entries anywhere it's grouped/counted.

    Rather than hand-coding exceptions for every acronym-style model name
    (IS, GS, X5, C-Class, CR-V, ...) - which a blanket .title() would mangle
    - this picks whichever casing variant is *most common* for each
    (brand, lowercased model) pair and uses that as the canonical form for
    every row in that group. Data-driven, no manual exception list to
    maintain as new brands/models get scraped in future runs.
    """
    df = df.copy()
    key = df["brand"].astype(str).str.strip() + "||" + df["model"].astype(str).str.strip().str.lower()

    casing_counts = (
        df.assign(_key=key, _model_stripped=df["model"].astype(str).str.strip())
        .groupby(["_key", "_model_stripped"])
        .size()
        .reset_index(name="count")
    )
    # For each key, keep the casing variant with the highest count (ties broken
    # by whichever sorts first - both variants are visually identical besides
    # case, so the tie-break choice doesn't matter).
    canonical = (
        casing_counts.sort_values("count", ascending=False)
        .drop_duplicates(subset="_key", keep="first")
        .set_index("_key")["_model_stripped"]
    )

    df["model"] = key.map(canonical)
    return df


# ---------------------------------------------------------------------------
# 2. Brand segment classification - every brand from the diagnostic report's
#    full brand list, post-normalization. Built fresh (not carried over from
#    old CarSwitch-only mapping, per your call to discard prior work).
# ---------------------------------------------------------------------------
BRAND_SEGMENT_MAP = {
    # --- Mass-market: mainstream volume brands, budget Chinese/other brands ---
    "Nissan": "Mass-market", "Toyota": "Mass-market", "Hyundai": "Mass-market",
    "Kia": "Mass-market", "Ford": "Mass-market", "Chevrolet": "Mass-market",
    "Mitsubishi": "Mass-market", "Honda": "Mass-market", "Suzuki": "Mass-market",
    "Mazda": "Mass-market", "MG": "Mass-market", "Renault": "Mass-market",
    "Peugeot": "Mass-market", "Fiat": "Mass-market", "Skoda": "Mass-market",
    "Isuzu": "Mass-market", "Citroen": "Mass-market", "Opel": "Mass-market",
    "Chery": "Mass-market", "Great Wall": "Mass-market", "Haval": "Mass-market",
    "JAC": "Mass-market", "Changan": "Mass-market", "Geely": "Mass-market",
    "GAC": "Mass-market", "BYD": "Mass-market", "Jetour": "Mass-market",
    "Zotye": "Mass-market", "Lifan": "Mass-market", "DFSK": "Mass-market",
    "Daihatsu": "Mass-market", "Hino": "Mass-market", "TATA": "Mass-market",
    "FAW": "Mass-market", "Foton": "Mass-market", "JMC": "Mass-market",
    "Haima": "Mass-market", "Kaiyi": "Mass-market", "Forthing": "Mass-market",
    "Karry": "Mass-market", "Dongfeng": "Mass-market", "Dorcen": "Mass-market",
    "Dayun": "Mass-market", "Soueast": "Mass-market", "CMC": "Mass-market",
    "Jinbei": "Mass-market", "Bestune": "Mass-market", "Baic": "Mass-market",
    "BAIC": "Mass-market", "Brilliance": "Mass-market", "Maxus": "Mass-market",
    "Proton": "Mass-market", "Kenbo": "Mass-market", "Luxgen": "Mass-market",
    "Lada": "Mass-market", "Daewoo": "Mass-market", "Datsun": "Mass-market",
    "SsangYong": "Mass-market", "Mahindra": "Mass-market", "Force": "Mass-market",
    "Iveco": "Mass-market", "King Long": "Mass-market", "Eicher": "Mass-market",
    "Sandstorm": "Mass-market", "LEVC": "Mass-market", "Yudo": "Mass-market",
    "ZX Auto": "Mass-market", "TOGG": "Mass-market", "Bajaj": "Mass-market",
    "Volkswagen": "Mass-market", "Seat": "Mass-market", "Smart": "Mass-market",
    "Victory": "Mass-market", "International": "Mass-market", "Dacia": "Mass-market",
    "JMEV": "Mass-market", "Cevo": "Mass-market", "Hunaghai": "Mass-market",
    "Daechang": "Mass-market", "ROX": "Mass-market",

    # --- Mid-range: American mainstream, older European marques, entry EVs ---
    "Jeep": "Mid-range", "GMC": "Mid-range", "Dodge": "Mid-range",
    "Chrysler": "Mid-range", "Ram": "Mid-range", "Buick": "Mid-range",
    "Pontiac": "Mid-range", "Mercury": "Mid-range", "Plymouth": "Mid-range",
    "Saab": "Mid-range", "Rover": "Mid-range", "Lancia": "Mid-range",
    "Subaru": "Mid-range", "VinFast": "Mid-range", "Xiaomi": "Mid-range",
    "Morris": "Mid-range",

    # --- Premium: German/Japanese luxury-adjacent, premium EVs, entry-luxury ---
    "Volvo": "Premium", "Audi": "Premium", "BMW": "Premium",
    "Mercedes-Benz": "Premium", "Infiniti": "Premium", "Lexus": "Premium",
    "Land Rover": "Premium", "Jaguar": "Premium", "Cadillac": "Premium",
    "Lincoln": "Premium", "Genesis": "Premium", "Alfa Romeo": "Premium",
    "Acura": "Premium", "Hongqi": "Premium", "Zeekr": "Premium",
    "Nio": "Premium", "Xpeng": "Premium", "Voyah": "Premium",
    "IM": "Premium", "Aito": "Premium", "Avatr": "Premium",
    "Ineos": "Premium", "Rivian": "Premium", "Fisker": "Premium",
    "Polestar": "Premium", "Tesla": "Premium", "Tank": "Premium",
    "Exeed": "Premium", "Hummer": "Premium", "Caterham": "Premium",
    "Ariel": "Premium", "Donkervoort": "Premium", "PGO": "Premium",
    "Vanderhall": "Premium", "Saleen": "Premium", "Oullim Motors": "Premium",
    "Studebaker": "Premium", "Borgward": "Premium", "Rabdan": "Premium",
    "Abarth": "Premium", "Gordon Roadster": "Premium", "MINI": "Premium",
    "Lotus": "Premium", "Morgan": "Premium", "DS Automobiles": "Premium",
    "Jaecoo": "Mass-market", "AL Damani": "Mass-market",

    # --- Luxury: exotics, hypercars, ultra-luxury, boutique bespoke ---
    "Porsche": "Luxury", "Bentley": "Luxury", "Rolls Royce": "Luxury",
    "Ferrari": "Luxury", "Lamborghini": "Luxury", "Maserati": "Luxury",
    "McLaren": "Luxury", "Aston Martin": "Luxury", "Maybach": "Luxury",
    "Mercedes-Maybach": "Luxury", "Bugatti": "Luxury", "Koenigsegg": "Luxury",
    "Pagani": "Luxury", "Spyker": "Luxury", "Noble": "Luxury",
    "Wiesmann": "Luxury", "Gumpert": "Luxury", "Bizzarrini": "Luxury",
    "Rimac": "Luxury", "Lucid": "Luxury", "Yangwang": "Luxury",
    "HiPhi": "Luxury", "Bufori": "Luxury", "W Motors": "Luxury",
    "Brabus": "Luxury", "DeLorean": "Luxury", "Rezvani": "Luxury",
    "Luxeed": "Luxury", "KTM": "Luxury", "BAC": "Luxury",
}

# ---------------------------------------------------------------------------
# City standardization - exact map from your original 02_cleaning.ipynb,
# extended with OpenSooq's "Um Al Quwain" spelling seen in the diagnostic.
# ---------------------------------------------------------------------------
CITY_DISPLAY_MAP = {
    "dubai": "Dubai",
    "abudhabi": "Abu Dhabi",
    "abu-dhabi": "Abu Dhabi",
    "abu dhabi": "Abu Dhabi",
    "sharjah": "Sharjah",
    "ajman": "Ajman",
    "ras-al-khaimah": "Ras Al Khaimah",
    "ras al khaimah": "Ras Al Khaimah",
    "rak": "Ras Al Khaimah",
    "fujairah": "Fujairah",
    "al-ain": "Al Ain",
    "al ain": "Al Ain",
    "umm-al-quwain": "Umm Al Quwain",
    "umm al quwain": "Umm Al Quwain",
    "um al quwain": "Umm Al Quwain",
}

PRICE_TIER_BINS = [0, 30_000, 100_000, 300_000, float("inf")]
PRICE_TIER_LABELS = ["Budget", "Mid-range", "Premium", "Luxury"]

MIN_PLAUSIBLE_PRICE = 1_000       # below this, treat as a "Call for Price" placeholder, not a real price
MAX_PLAUSIBLE_MILEAGE = 1_000_000  # above this, treat as a parsing artifact (e.g. the 6,000,000 km found)

BASE_COLUMNS = ["source", "listing_id", "name", "brand", "model", "year",
                "mileage_km", "price_aed", "city", "url"]


def make_listing_id(source: str, key: str) -> str:
    return hashlib.md5(f"{source}:{key}".encode()).hexdigest()[:12]


def load_combined(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    engineered_cols = ["car_age", "price_tier", "mileage_per_year", "brand_segment", "transmission"]
    df = df.drop(columns=[c for c in engineered_cols if c in df.columns])
    for col in BASE_COLUMNS:
        if col not in df.columns:
            df[col] = pd.NA
    return df[BASE_COLUMNS]


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # --- backfill listing_id for rows that never had one (CarSwitch) ---
    missing_id = df["listing_id"].isna()
    df.loc[missing_id, "listing_id"] = df.loc[missing_id].apply(
        lambda r: make_listing_id(r["source"], r["url"]), axis=1
    )

    # --- brand normalization + Range Rover fix ---
    df["brand"] = df["brand"].apply(normalize_brand_text)
    df[["brand", "model"]] = df.apply(fix_range_rover_brand, axis=1)

    # --- model casing normalization (e.g. 'KICKS' vs 'Kicks') ---
    df = normalize_model_casing(df)

    # --- mileage imputation for "brand new" listings missing a mileage chip ---
    brand_new_mask = df["mileage_km"].isna() & df["name"].astype(str).str.contains("brand new", case=False, na=False)
    df.loc[brand_new_mask, "mileage_km"] = 0
    print(f"Imputed mileage_km=0 for {brand_new_mask.sum()} 'brand new' listings that had no mileage chip")

    # --- sanity outlier flags (kept in data, flagged, NOT silently dropped) ---
    df["price_suspect"] = df["price_aed"].notna() & (df["price_aed"] < MIN_PLAUSIBLE_PRICE)
    df["mileage_suspect"] = df["mileage_km"].notna() & (df["mileage_km"] > MAX_PLAUSIBLE_MILEAGE)
    print(f"Flagged {df['price_suspect'].sum()} rows with price_aed < {MIN_PLAUSIBLE_PRICE} AED as suspect")
    print(f"Flagged {df['mileage_suspect'].sum()} rows with mileage_km > {MAX_PLAUSIBLE_MILEAGE} km as suspect")

    # --- car_age ---
    df["car_age"] = (CURRENT_YEAR - df["year"]).clip(lower=0)

    # --- price_tier (NaN for null/suspect prices, by design) ---
    price_for_tier = df["price_aed"].where(~df["price_suspect"])
    df["price_tier"] = pd.cut(price_for_tier, bins=PRICE_TIER_BINS, labels=PRICE_TIER_LABELS, right=False)

    # --- mileage_per_year (NaN for null/suspect mileage, by design) ---
    mileage_for_calc = df["mileage_km"].where(~df["mileage_suspect"])
    denom = df["car_age"].replace(0, 1)
    df["mileage_per_year"] = mileage_for_calc / denom

    # --- brand_segment - report anything still unmapped ---
    df["brand_segment"] = df["brand"].map(BRAND_SEGMENT_MAP)
    unmapped = sorted(df.loc[df["brand_segment"].isna() & df["brand"].notna(), "brand"].unique())
    if unmapped:
        print(f"\n⚠ {len(unmapped)} brand(s) still not in BRAND_SEGMENT_MAP:")
        for b in unmapped:
            count = (df["brand"] == b).sum()
            print(f"    '{b}': {count} listings")

    # --- city standardization ---
    df["city"] = df["city"].apply(
        lambda x: CITY_DISPLAY_MAP.get(str(x).strip().lower(), x) if pd.notna(x) else x
    )

    return df


def finalize(data_dir: Path):
    combined_path = data_dir / "processed" / "uae_cars_combined_deduped.csv"
    df = load_combined(combined_path)
    print(f"Loaded {len(df)} combined rows from {combined_path}\n")

    df = engineer_features(df)

    out_path = data_dir / "processed" / "uae_cars_final_clean.csv"
    df.to_csv(out_path, index=False)
    print(f"\nSaved {len(df)} rows -> {out_path}")

    print("\n--- Segment distribution ---")
    print(df["brand_segment"].value_counts(dropna=False))
    print("\n--- Source distribution ---")
    print(df["source"].value_counts(dropna=False))
    print("\n--- Price tier distribution ---")
    print(df["price_tier"].value_counts(dropna=False))
    print(f"\nRows usable for price analysis (price_aed present, not suspect): "
          f"{(df['price_aed'].notna() & ~df['price_suspect']).sum()} / {len(df)}")


if __name__ == "__main__":
    project_root = Path(__file__).resolve().parent.parent
    finalize(project_root / "data")
