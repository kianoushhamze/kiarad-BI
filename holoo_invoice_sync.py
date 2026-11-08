"""Compatibility entry point: project the latest verified feed, never guess ownership."""
import json
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()
from holoo_operational_sync import ProjectionError, sync_operational_snapshot

LOG = Path(__file__).resolve().parent / "logs" / "holoo_invoice_sync.log"


def record(receipt):
    """Task Scheduler discards stdout; keep a short history next to the logs."""
    try:
        LOG.parent.mkdir(exist_ok=True)
        with LOG.open("a", encoding="utf-8") as handle:
            handle.write(datetime.now().astimezone().isoformat(timespec="seconds") + " " + json.dumps(receipt, ensure_ascii=False) + "\n")
    except OSError:
        pass


def main():
    try:
        result = sync_operational_snapshot()
        record(result)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except ProjectionError as error:
        # The newest financial snapshot is still missing a source. Projecting it
        # would rewrite the mirror with partial data, so report and wait instead.
        receipt = {"status": "blocked_incomplete_source", "reason": str(error)[:80], "erp_writes": False}
        record(receipt)
        print(json.dumps(receipt, ensure_ascii=False))
        return 0
    except Exception as error:
        receipt = {"status": "failed", "error_type": type(error).__name__, "erp_writes": False}
        record(receipt)
        print(json.dumps(receipt, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
