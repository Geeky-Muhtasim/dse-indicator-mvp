"""Command line for the signal pipeline.

    python pipeline/cli.py update            # fetch new DSE sessions, then rescore
    python pipeline/cli.py score             # rescore the latest stored session
    python pipeline/cli.py retrain           # walk-forward validate, retrain, rescore, HTML report
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dse_signal.config import Config  # noqa: E402
from dse_signal import pipeline  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="DSE explainable signal pipeline")
    sub = ap.add_subparsers(dest="cmd", required=True)
    up = sub.add_parser("update", help="fetch new DSE sessions and rescore")
    up.add_argument("--force-score", action="store_true", help="rescore even if no new data")
    sub.add_parser("score", help="rescore the latest stored session")
    bf = sub.add_parser("backfill", help="rebuild multi-year history from DSE, then retrain")
    bf.add_argument("--start", default="2020-01-01", help="first date to fetch (YYYY-MM-DD)")
    bf.add_argument("--min-consistency", type=float, default=0.9,
                    help="share of overlapping symbols that must agree with the existing history")
    rt = sub.add_parser("retrain", help="validate and retrain the model")
    rt.add_argument("--no-report", action="store_true")
    rt.add_argument("--min-ic", type=float, default=0.0, help="promote only above this OOS rank IC")
    a = ap.parse_args()

    cfg = Config()
    if a.cmd == "update":
        from dse_signal.dse_live import update_history
        added = update_history(pipeline.HISTORY)
        if added or a.force_score:
            pipeline.score(cfg)
        return 0
    if a.cmd == "backfill":
        from datetime import date
        from dse_signal.dse_live import backfill
        backfill(pipeline.HISTORY, date.fromisoformat(a.start), min_consistency=a.min_consistency)
        import importlib
        importlib.reload(pipeline)  # pick up eod.csv.gz as the history file
        pipeline.retrain(cfg)
        return 0
    if a.cmd == "score":
        pipeline.score(cfg)
        return 0
    pipeline.retrain(cfg, html_report=not a.no_report, min_ic_to_promote=a.min_ic)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
