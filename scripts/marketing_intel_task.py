"""Daily marketing-intel task: harvest market questions + refresh demand.

Soft-fail: each step is independent and a failure (network, DDG rate-limit,
DB) is logged and reported in the exit summary instead of crashing the run.
Scheduled hourly as Windows task "KiaradMarketingIntel" (bounded budgets make
hourly runs safe: max 6 + 5 searches per run).
"""
import logging
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("kiarad_marketing_intel_task")


def step(name, func, **kwargs):
    try:
        result = func(**kwargs)
        log.info("%s: %s", name, result)
        return result
    except Exception:
        log.error("%s failed (soft):\n%s", name, traceback.format_exc())
        return None


def main() -> int:
    from db import engine
    from marketing_intel import ensure, _kerman_sales_counts

    # Warm up tables so both endpoints work even before first panel use.
    try:
        with engine.begin() as conn:
            ensure(conn)
    except Exception:
        log.error("ensure() failed:\n%s", traceback.format_exc())
        return 1

    with engine.connect() as conn:
        log.info("sales data present: %s", bool(_kerman_sales_counts(conn)[0]))

    harvest = step("harvest_questions", harvest_questions_call)
    demand = step("refresh_demand", refresh_demand_call)
    time.sleep(1)
    ok = (harvest is not None) or (demand is not None)
    log.info("done: harvest=%s demand=%s", bool(harvest), bool(demand))
    return 0 if ok else 1


def harvest_questions_call() -> dict:
    # Reuse the endpoint logic directly (no HTTP server needed in the task).
    from marketing_intel import harvest_questions
    return harvest_questions({"role": "ceo", "id": 0, "full_name": "scheduled-task"})


def refresh_demand_call() -> dict:
    from marketing_intel import refresh_demand
    return refresh_demand({"role": "ceo", "id": 0, "full_name": "scheduled-task"})


if __name__ == "__main__":
    sys.exit(main())
