"""Thin BigQuery helper: runs a named .sql file from backend/sql with parameters."""
import asyncio
import pathlib
from functools import lru_cache

from config import DATASET, project_id

SQL_DIR = pathlib.Path(__file__).resolve().parent.parent / "sql"


@lru_cache(maxsize=1)
def _client():
    from google.cloud import bigquery
    return bigquery.Client(project=project_id())


def load_sql(name: str) -> str:
    """The query text, with {dataset} replaced by the shop's dataset (GONOGO_DATASET)."""
    return (SQL_DIR / f"{name}.sql").read_text().replace("{dataset}", DATASET)


def _param(key, value):
    from google.cloud import bigquery
    kind = "FLOAT64" if isinstance(value, float) else "INT64" if isinstance(value, int) else "STRING"
    return bigquery.ScalarQueryParameter(key, kind, value)


def _run_sync(name: str, params: dict) -> list[dict]:
    from google.cloud import bigquery
    config = bigquery.QueryJobConfig(query_parameters=[_param(k, v) for k, v in params.items()])
    job = _client().query(load_sql(name), job_config=config)
    return [dict(row.items()) for row in job.result()]


async def run(name: str, params: dict | None = None) -> list[dict]:
    """Run sql/<name>.sql without blocking the web server."""
    return await asyncio.to_thread(_run_sync, name, params or {})
