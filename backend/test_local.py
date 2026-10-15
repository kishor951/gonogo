"""Run the agents from the command line, without the web page.

    python test_local.py            # real Gemini + BigQuery (needs Google Cloud access)
    GONOGO_MOCK=1 python test_local.py   # sample data, no Google Cloud
"""
import asyncio
import json

from agents.orchestrator import evaluate
from main import EvaluateRequest

CASES = [
    EvaluateRequest(name="High-waist active leggings", description="Squat-proof stretch leggings with a side phone pocket",
                    department="Women", category="Leggings", cost=450, price=1299),
    EvaluateRequest(name="Double-breasted wool overcoat", description="Long, heavy wool-blend winter overcoat",
                    department="Men", category="Outerwear & Coats", cost=6500, price=8999),
]


async def main():
    for case in CASES:
        out = await evaluate(case)
        print("=" * 70)
        print(f"{case.name}: {out['verdict'].upper()}  ({out['timing_ms'] / 1000:.1f}s)")
        print(out["headline"])
        for r in out["reasons"]:
            print(f"  - [{r['agent']}] {r['text']}")
        for c in out["checks"]:
            print(f"  {'PASS' if c['passed'] else 'FAIL'}  {c['label']}: {c['value']}")
        for name, a in out["agents"].items():
            print(f"  {name:8} {a['status']:6} {a['ms']} ms {a.get('error', '')}")
        print(json.dumps(out["key_numbers"], ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
