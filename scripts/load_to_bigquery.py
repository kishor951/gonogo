"""Load the Urban Loom CSVs (from generate_shop_data.py) into BigQuery.

    gcloud auth application-default login          # once
    python scripts/load_to_bigquery.py             # project gonogo-511, dataset gonogo_shop
    python scripts/load_to_bigquery.py --project my-project --dataset gonogo_shop

Creates the dataset in asia-south1 if it is missing and replaces every table, including the
settings table (so any rules saved from the Business page go back to the defaults).
Needs google-cloud-bigquery (in backend/requirements.txt).
"""
import argparse
import pathlib
import sys

from google.cloud import bigquery

DATA = pathlib.Path(__file__).resolve().parent / "data"
LOCATION = "asia-south1"

F = bigquery.SchemaField
SCHEMAS = {
    "suppliers": [F("supplier_id", "STRING", "REQUIRED"), F("name", "STRING"), F("city", "STRING"),
                  F("lead_time_days", "INT64"), F("moq", "INT64")],
    "products": [F("sku", "STRING", "REQUIRED"), F("name", "STRING"), F("department", "STRING"),
                 F("category", "STRING"), F("brand", "STRING"), F("cost_inr", "INT64"),
                 F("price_inr", "INT64"), F("launch_date", "DATE"), F("supplier_id", "STRING"),
                 F("status", "STRING")],
    "customers": [F("customer_id", "STRING", "REQUIRED"), F("age_band", "STRING"), F("city", "STRING"),
                  F("first_order_date", "DATE")],
    "sales": [F("order_id", "STRING", "REQUIRED"), F("order_date", "DATE"), F("sku", "STRING"),
              F("qty", "INT64"), F("unit_price_inr", "INT64"), F("channel", "STRING"),
              F("customer_id", "STRING"), F("returned", "BOOL")],
    "inventory": [F("sku", "STRING", "REQUIRED"), F("on_hand", "INT64"), F("on_order", "INT64"),
                  F("reorder_point", "INT64"), F("last_received_date", "DATE")],
    "settings": [F("org_id", "STRING", "REQUIRED"), F("shop_name", "STRING"), F("rules_json", "STRING"),
                 F("updated_at", "TIMESTAMP"), F("profile_json", "STRING")],
}


def main():
    ap = argparse.ArgumentParser(description="Load the Urban Loom CSVs into BigQuery.")
    ap.add_argument("--project", default="gonogo-511")
    ap.add_argument("--dataset", default="gonogo_shop")
    args = ap.parse_args()

    missing = [t for t in SCHEMAS if not (DATA / f"{t}.csv").exists()]
    if missing:
        sys.exit(f"Missing {', '.join(m + '.csv' for m in missing)} in {DATA}. "
                 "Run python scripts/generate_shop_data.py first.")

    client = bigquery.Client(project=args.project)
    dataset = bigquery.Dataset(f"{args.project}.{args.dataset}")
    dataset.location = LOCATION
    client.create_dataset(dataset, exists_ok=True)
    print(f"Dataset {dataset.dataset_id} ready in {LOCATION}.")

    for table, schema in SCHEMAS.items():
        config = bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.CSV, skip_leading_rows=1, schema=schema,
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        )
        with open(DATA / f"{table}.csv", "rb") as f:
            job = client.load_table_from_file(f, f"{args.project}.{args.dataset}.{table}",
                                              job_config=config, location=LOCATION)
        job.result()
        print(f"  loaded {table}")

    print("\nRow counts:")
    for table in SCHEMAS:
        n = client.get_table(f"{args.project}.{args.dataset}.{table}").num_rows
        print(f"  {table:10} {n:>7,}")


if __name__ == "__main__":
    main()
