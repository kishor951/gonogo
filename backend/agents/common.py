"""Shared helpers: rupee formatting and the evidence format every agent returns.

Evidence shape (rendered generically by the web page):
{
  "summary": [["label", "value"], ...],
  "tables": [{"title": str, "columns": [...], "rows": [[...], ...]}],
  "links":  [{"title": str, "url": str}],
  "note":   str
}
"""


def inr(value) -> str:
    """Rupees with Indian digit grouping: ₹3,51,000."""
    if value is None:
        return "-"
    sign = "-" if value < 0 else ""
    digits = str(int(round(abs(value))))
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        digits = ",".join(groups + [tail])
    return f"{sign}₹{digits}"


def pct(value, digits=0) -> str:
    if value is None:
        return "-"
    return f"{value * 100:.{digits}f}%"


def evidence(summary=None, tables=None, links=None, note=None) -> dict:
    out = {}
    if summary:
        out["summary"] = summary
    if tables:
        out["tables"] = tables
    if links:
        out["links"] = links
    if note:
        out["note"] = note
    return out
