"""Two entry points:

retrain(): walk-forward validation, final model, evidence. Run weekly or after adding history.
score():   rescore the latest day with the saved model. Run daily after new data arrives.
"""
from __future__ import annotations

import json
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from . import data, explain, export, features, labels, report, signals, validate
from .config import Config
from .features import FEATURES
from .models import GBMRanker

warnings.filterwarnings("ignore", category=UserWarning)

ROOT = Path(__file__).resolve().parents[2]
_HIST_DIR = ROOT / "data" / "history"
# The backfill writes a compressed multi-year file; the original 60-day export is plain CSV.
HISTORY = _HIST_DIR / "eod.csv.gz" if (_HIST_DIR / "eod.csv.gz").exists() else _HIST_DIR / "eod.csv"
MODEL_DIR = ROOT / "data" / "model"
APP_DIR = ROOT / "data" / "app"
REPORT_DIR = ROOT / "reports"


def build_panel(raw: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    df = data.prepare(raw, cfg)
    df = features.build_features(df)
    df = labels.add_forward_returns(df, cfg.horizon)
    df = labels.add_excess_targets(df)
    ok = df["in_universe"] & df[FEATURES].notna().all(axis=1)
    return df[ok].copy()


def _ic_series(oos: pd.DataFrame, col: str) -> tuple[list, str]:
    """Daily rank IC, or monthly means once there are too many days to draw as bars."""
    ic = validate.daily_ic(oos, col)
    ic.index = pd.to_datetime(ic.index)
    freq = "daily"
    if len(ic) > 150:
        ic = ic.groupby(ic.index.to_period("M")).mean()
        ic.index = ic.index.to_timestamp()
        freq = "monthly"
    return [{"date": str(pd.Timestamp(d).date()), "ic": round(float(v), 4)} for d, v in ic.items()], freq


def _bt_rows(bt: pd.DataFrame) -> list:
    return [{"date": str(pd.Timestamp(d).date()), **{k: round(float(v), 5) for k, v in r.items()}}
            for d, r in bt.iterrows()]


def retrain(cfg: Config | None = None, log=print, html_report: bool = True,
            min_ic_to_promote: float = 0.0) -> dict:
    """Validate, and promote the new model only if its out-of-sample rank IC clears the bar."""
    cfg = cfg or Config()
    raw = data.load_eod(HISTORY)
    quality = data.quality_report(raw, cfg)
    panel = build_panel(raw, cfg)
    log(f"Panel: {len(panel):,} stock-days over {panel['Date'].nunique()} dates")

    oos, folds = validate.walk_forward(panel, cfg)
    metrics = {"gbm": validate.summarise(oos, "score_gbm", cfg),
               "card": validate.summarise(oos, "score_card", cfg)}
    calib = validate.decile_calibration(oos, "score_gbm")
    ic = metrics["gbm"]["ic_mean"]
    log(f"Out-of-sample rank IC {ic:.3f} (scorecard {metrics['card']['ic_mean']:.3f})")

    model_path = MODEL_DIR / "model_lgbm.txt"
    promoted = ic > min_ic_to_promote or not model_path.exists()
    labelled = panel[panel["target"].notna()]
    model = GBMRanker(cfg).fit(labelled)
    sample = labelled.sample(min(3000, len(labelled)), random_state=cfg.seed)
    fam_imp = explain.family_importance(explain.shap_values(model, sample))

    if promoted:
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        model.save(model_path)
        info = {"version": datetime.now(timezone.utc).strftime("%Y%m%d"), "trainedThrough":
                str(labelled["Date"].max().date()), "trainRows": int(len(labelled)),
                "promoted": True, "oosIc": round(ic, 4)}
        log("New model promoted")
    else:
        old = json.loads((APP_DIR / "meta.json").read_text())["model"]
        info = {**old, "lastAttempt": datetime.now(timezone.utc).strftime("%Y%m%d"),
                "lastAttemptIc": round(ic, 4), "promoted": False}
        log(f"New model NOT promoted (IC {ic:.3f} <= {min_ic_to_promote}); keeping the previous one")

    metrics_block = {
        "asofValidation": str(panel["Date"].max().date()),
        "quality": quality, "folds": folds, "summary": metrics,
        "icSeries": (icser := _ic_series(oos, "score_gbm"))[0], "icFreq": icser[1],
        "calibration": [{"decile": int(d), "hitRate": round(float(r.hit_rate), 4),
                         "meanExcess": round(float(r.mean_excess), 5), "n": int(r.n)}
                        for d, r in calib.iterrows()],
        "backtest": {"gbm": _bt_rows(validate.backtest(oos, "score_gbm", cfg)),
                     "card": _bt_rows(validate.backtest(oos, "score_card", cfg))},
        "familyImportance": {k: round(float(v), 5) for k, v in fam_imp.items()},
        "config": {"horizon": cfg.horizon, "roundTripCost": cfg.round_trip_cost,
                   "commissionBps": cfg.commission_bps_per_side, "slippageBps": cfg.slippage_bps_per_side},
    }
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    (MODEL_DIR / "pending_metrics.json").write_text(json.dumps(metrics_block))
    if promoted:
        (MODEL_DIR / "metrics.json").write_text(json.dumps(metrics_block))
        (MODEL_DIR / "model_info.json").write_text(json.dumps(info))

    res = score(cfg, log=log, raw=raw, panel=panel)

    if html_report:
        REPORT_DIR.mkdir(exist_ok=True)
        bt_g = validate.backtest(oos, "score_gbm", cfg)
        bt_c = validate.backtest(oos, "score_card", cfg)
        breadth = panel.groupby("Date")["breadth_20"].first()
        rep = {"cfg": cfg, "asof": res["asof"], "quality": quality, "metrics": metrics, "folds": folds,
               "signals": res["signals"], "regime": res["regime"], "n_universe": len(res["signals"]),
               "charts": {"ic": report.chart_ic(validate.daily_ic(oos, "score_gbm")),
                          "quint": report.chart_quintiles(metrics["gbm"]["quintile_excess"],
                                                          metrics["card"]["quintile_excess"]),
                          "calib": report.chart_calibration(calib), "eq": report.chart_equity(bt_g, bt_c),
                          "fam": report.chart_families(fam_imp),
                          "breadth": report.chart_breadth(breadth, cfg.risk_off_breadth)}}
        (REPORT_DIR / "report.html").write_text(report.build(rep), encoding="utf-8")
    return res


def score(cfg: Config | None = None, log=print, raw=None, panel=None) -> dict:
    """Score the latest date with the saved model and write the app data."""
    cfg = cfg or Config()
    raw = raw if raw is not None else data.load_eod(HISTORY)
    panel = panel if panel is not None else build_panel(raw, cfg)
    model = GBMRanker.load(MODEL_DIR / "model_lgbm.txt", cfg)
    metrics_block = json.loads((MODEL_DIR / "metrics.json").read_text())
    info = json.loads((MODEL_DIR / "model_info.json").read_text())
    calib = pd.DataFrame(metrics_block["calibration"]).set_index("decile").rename(
        columns={"hitRate": "hit_rate", "meanExcess": "mean_excess"})

    asof = panel["Date"].max()
    day = panel[panel["Date"] == asof]
    sv = explain.shap_values(model, day)
    sig, reg = signals.make_signals(day, model.predict(day), sv, calib, cfg)
    reg = {k: (bool(v) if isinstance(v, (bool, np.bool_)) else round(float(v), 5)) for k, v in reg.items()}

    export.write_app_data(APP_DIR, cfg=cfg, panel=panel, raw=raw, sig=sig, reg=reg,
                          metrics_block=metrics_block, booster=model.model.booster_, model_info=info)
    counts = sig["signal"].value_counts().to_dict()
    log(f"Scored {asof.date()}: {counts.get('BUY', 0)} Buy, {counts.get('AVOID', 0)} Avoid, "
        f"{'risk-off' if reg['risk_off'] else 'normal'} regime")
    return {"asof": str(asof.date()), "signals": sig, "regime": reg}
