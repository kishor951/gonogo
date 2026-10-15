"""The sample store's departments and categories, read once from BigQuery and cached."""
from config import MOCK
from agents import bq, mock

_cache: list[dict] | None = None


async def get_categories() -> list[dict]:
    global _cache
    if _cache is None:
        _cache = mock.categories() if MOCK else await bq.run("categories")
    return _cache


def allowed_by_department(categories: list[dict]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for row in categories:
        out.setdefault(row["department"], []).append(row["category"])
    return {dept: sorted(set(cats)) for dept, cats in out.items()}
