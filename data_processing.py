import os

import pandas as pd
from pymongo import MongoClient

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")

# Connect to MongoDB
client = MongoClient(MONGO_URI)
db = client["OnlineRetail"]
collection = db["unstructured_data"]

# Fetch all records
cursor = collection.find({}, {"_id": 0})
df = pd.DataFrame(list(cursor))
if df.empty:
    raise SystemExit("No documents in OnlineRetail.unstructured_data. Run data_ingestion.py first.")

print("Columns in the DataFrame:", list(df.columns))

# Data Transformations
df['InvoiceDate'] = pd.to_datetime(df['InvoiceDate'])
df['TotalPrice'] = df['Quantity'] * df['UnitPrice']  # Compute total price per transaction
df['InvoiceYearMonth'] = df['InvoiceDate'].dt.to_period('M').astype(str)
df_filtered = df[df['TotalPrice'] > 100]  # Filter transactions where TotalPrice > 100
df_grouped = df.groupby(['InvoiceYearMonth', 'Country']).agg({'TotalPrice': 'sum'}).reset_index()  # Aggregate sales by month and country

# Display processed data
print("Filtered Data:\n", df_filtered.head())
print("\nGrouped Data:\n", df_grouped.head())

# Save processed data back to MongoDB, replacing the previous run's output
collection_processed = db["processed_data"]
collection_processed.delete_many({})
collection_processed.insert_many(df_grouped.to_dict(orient="records"))

print(f"Data processing completed successfully! {len(df_grouped)} documents written to processed_data.")
