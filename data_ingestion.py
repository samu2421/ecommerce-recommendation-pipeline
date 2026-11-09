import os

import pandas as pd
from pymongo import MongoClient
from sqlalchemy import create_engine, inspect, text

# Connection settings (defaults work when running directly on the host machine)
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+psycopg2://samiksha:password123@localhost:5432/ecommerce_data"
)
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")

# Dataset location: CSV export (dd/mm/yy HH:MM dates) or the original UCI Excel file
DATASET_PATH = os.getenv("DATASET_PATH", "data/online_retail.csv")

TABLE_NAME = "sales_data"
BATCH_SIZE = 1000
COLUMNS = ["InvoiceNo", "StockCode", "Description", "Quantity",
           "InvoiceDate", "UnitPrice", "CustomerID", "Country"]
TEXT_DTYPES = {"InvoiceNo": str, "StockCode": str}


def clean_customer_id(value):
    """17850.0 / "17850.0" / 17850 -> "17850"; missing -> None."""
    if pd.isna(value):
        return None
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text or None


def prepare_batch(chunk, date_format=None):
    chunk = chunk.copy()
    chunk.columns = COLUMNS
    if date_format:
        chunk["InvoiceDate"] = pd.to_datetime(chunk["InvoiceDate"], format=date_format, errors="coerce")
    else:
        chunk["InvoiceDate"] = pd.to_datetime(chunk["InvoiceDate"], errors="coerce")
    chunk["CustomerID"] = chunk["CustomerID"].map(clean_customer_id).astype(object)
    return chunk


def iter_batches(path):
    if path.lower().endswith((".xlsx", ".xls")):
        # Excel cannot be streamed, so read once and slice into batches
        df = pd.read_excel(path, dtype=TEXT_DTYPES)
        for start in range(0, len(df), BATCH_SIZE):
            yield prepare_batch(df.iloc[start:start + BATCH_SIZE])
    else:
        reader = pd.read_csv(path, dtype=TEXT_DTYPES, encoding="utf-8-sig", chunksize=BATCH_SIZE)
        for chunk in reader:
            yield prepare_batch(chunk, date_format="%d/%m/%y %H:%M")


def get_ingest_mode():
    """Unset/empty (default): load only into an empty table. "replace": wipe and reload."""
    mode = os.getenv("INGEST_MODE", "").strip().lower()
    if mode not in ("", "replace"):
        raise ValueError(f"Unsupported INGEST_MODE={mode!r}; use INGEST_MODE=replace or leave it unset.")
    return mode


def should_load(existing_rows, mode):
    return mode == "replace" or existing_rows == 0


def count_sales_rows(engine):
    if not inspect(engine).has_table(TABLE_NAME):
        return 0
    with engine.connect() as conn:
        return conn.execute(text(f"SELECT COUNT(*) FROM {TABLE_NAME}")).scalar()


def ingest(engine, mongo_collection, path, mode=""):
    """Load the dataset into PostgreSQL and MongoDB. Returns rows inserted (0 if skipped)."""
    existing = count_sales_rows(engine)
    if not should_load(existing, mode):
        print(f"{TABLE_NAME} already contains {existing} rows; skipping ingestion. "
              "Set INGEST_MODE=replace to empty sales_data and unstructured_data and reload.")
        return 0

    if not os.path.exists(path):
        raise FileNotFoundError(f"Dataset not found at {path} (set DATASET_PATH)")

    if mode == "replace":
        print(f"INGEST_MODE=replace: emptying {TABLE_NAME} ({existing} rows) and unstructured_data...")
        if inspect(engine).has_table(TABLE_NAME):
            with engine.begin() as conn:
                conn.execute(text(f"DELETE FROM {TABLE_NAME}"))
        mongo_collection.delete_many({})

    print(f"Ingesting {path} in batches of {BATCH_SIZE} rows...")
    total = 0
    for batch in iter_batches(path):
        # PostgreSQL (table created by init_postgres.sql)
        batch.to_sql(TABLE_NAME, engine, if_exists="append", index=False)

        # MongoDB: store missing values as null rather than NaN/NaT
        records = batch.astype(object).where(batch.notna(), None).to_dict(orient="records")
        mongo_collection.insert_many(records)

        total += len(batch)
        if total % 50000 < BATCH_SIZE:
            print(f"{total} rows inserted into PostgreSQL and MongoDB...")

    print(f"Batch data ingestion completed successfully! {total} rows inserted.")
    return total


def main():
    mode = get_ingest_mode()
    engine = create_engine(DATABASE_URL)
    mongo_collection = MongoClient(MONGO_URI)["OnlineRetail"]["unstructured_data"]
    ingest(engine, mongo_collection, DATASET_PATH, mode)


if __name__ == "__main__":
    main()
