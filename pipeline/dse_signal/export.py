"""Write the JSON files the web app and API read. Everything the UI shows comes from here."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .config import Config
from .features import FAMILIES, FEATURES

HISTORY_SESSIONS = 60


def _f(x, nd=6):
    """JSON-safe float."""
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return round(v, nd) if np.isfinite(v) else None


def _dump(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def model_json(booster, feature_names: list[str]) -> dict:
    """Compact tree arrays for the API's pure-Python predictor and TreeSHAP.
    Internal nodes and leaves share one array per tree; leaves have feature = -1."""
    dump = booster.dump_model()
    trees = []
    for t in dump["tree_info"]:
        feat, thr, left, right, value, cover, dleft = [], [], [], [], [], [], []

        def walk(node) -> int:
            i = len(feat)
            feat.append(-1); thr.append(0.0); left.append(-1); right.append(-1)
            value.append(0.0); cover.append(0.0); dleft.append(1)
            if "split_index" not in node:
                value[i] = float(node["leaf_value"])
                cover[i] = float(node.get("leaf_count", 0))
                return i
            if node.get("decision_type", "<=") != "<=":
                raise ValueError("Only numerical <= splits are supported")
            feat[i] = int(node["split_feature"])
            thr[i] = float(node["threshold"])
            value[i] = float(node.get("internal_value", 0.0))
            cover[i] = float(node.get("internal_count", 0))
            dleft[i] = 1 if node.get("default_left", True) else 0
            left[i] = walk(node["left_child"])
            right[i] = walk(node["right_child"])
            return i

        walk(t["tree_structure"])
        trees.append({"f": feat, "t": thr, "l": left, "r": right, "v": value, "c": cover, "d": dleft})
    return {"features": feature_names, "trees": trees}


def write_app_data(out_dir: Path, *, cfg: Config, panel: pd.DataFrame, raw: pd.DataFrame,
                   sig: pd.DataFrame, reg: dict, metrics_block: dict, booster,
                   model_info: dict, prepared: pd.DataFrame | None = None) -> None:
    out_dir = Path(out_dir)
    asof = sig["Date"].iloc[0]
    n = len(sig)

    # 1. Signals for the screener, with top drivers precomputed for every stock.
    prev_close = (raw.sort_values("Date").groupby("Symbol")["Close"]
                  .apply(lambda c: c.iloc[-2] if len(c) > 1 else np.nan))
    rows = []
    for rank, (_, r) in enumerate(sig.iterrows(), start=1):
        pc = prev_close.get(r["Symbol"], np.nan)
        drv = lambda lst: [{"feature": d["feature"], "value": _f(d["value"]), "shap": _f(d["shap"])} for d in lst]
        rows.append({
            "symbol": r["Symbol"], "close": _f(r["Close"], 2),
            "chg1d": _f(r["Close"] / pc - 1 if pc and np.isfinite(pc) else None, 5),
            "signal": r["signal"], "score": _f(r["score"], 5), "rank": rank,
            "pct": _f(r["pct"], 4), "decile": int(r["decile"]),
            "odds": _f(r["hist_hit_rate"], 4), "meanExcess": _f(r["hist_mean_excess"], 5),
            "fillRisk": bool(r["fill_risk"]),
            "for": drv(r["drivers_for"]), "against": drv(r["drivers_against"]),
        })
    counts = sig["signal"].value_counts().to_dict()

    # Every other company stock DSE traded recently is listed too, with the reason it has no call.
    unrated = _unrated_rows(prepared, raw, set(sig["Symbol"]), asof, cfg) if prepared is not None else []
    reasons = pd.Series([u["reason"] for u in unrated]).value_counts().to_dict() if unrated else {}
    _dump(out_dir / "signals.json", {"asof": str(asof.date()), "n": n, "rows": rows + unrated})

    # 2. Latest feature vector per stock (the what-if starting point) and slider ranges.
    day = panel[panel["Date"] == asof].set_index("Symbol")
    feats = {s: {f: _f(day.at[s, f]) for f in FEATURES} for s in day.index}
    ranges = {f: [_f(day[f].quantile(0.01)), _f(day[f].quantile(0.99))] for f in FEATURES}
    _dump(out_dir / "features.json", {"asof": str(asof.date()), "families": FAMILIES,
                                      "ranges": ranges, "values": feats})

    # 3. Price history for charts: last N sessions, close, volume and 20-day average.
    hist = {}
    listed = set(day.index) | {u["symbol"] for u in unrated}
    recent = raw.sort_values("Date").groupby("Symbol").tail(HISTORY_SESSIONS + 19)
    for s, g in recent.groupby("Symbol"):
        if s not in listed:
            continue
        ma = g["Close"].rolling(20).mean()
        g = g.assign(ma20=ma).tail(HISTORY_SESSIONS)
        hist[s] = [[str(d.date()), _f(o, 2), _f(h, 2), _f(l, 2), _f(c, 2), int(v), _f(m, 3)]
                   for d, o, h, l, c, v, m in zip(g["Date"], g["Open"], g["High"], g["Low"],
                                                   g["Close"], g["Volume"], g["ma20"])]
    _dump(out_dir / "history.json", {"cols": ["date", "open", "high", "low", "close", "volume", "ma20"],
                                     "data": hist})

    # 4. Market regime series.
    by_date = panel.groupby("Date").agg(breadth=("breadth_20", "first"), mkt10=("mkt_ret_10", "first"))
    regime_series = [{"date": str(d.date()), "breadth": _f(b, 4), "mkt10": _f(np.expm1(m), 5),
                      "riskOff": bool(b < cfg.risk_off_breadth and m < 0)}
                     for d, b, m in zip(by_date.index, by_date["breadth"], by_date["mkt10"])]
    _dump(out_dir / "regime.json", {"threshold": cfg.risk_off_breadth, "current": reg, "series": regime_series})

    # 5. Model evidence (validation is only refreshed on retrain; daily runs reuse it).
    _dump(out_dir / "metrics.json", metrics_block)

    # 6. Trees for the API's live scoring.
    _dump(out_dir / "model.json", model_json(booster, FEATURES))

    # 7. Meta.
    _dump(out_dir / "meta.json", {
        "asof": str(asof.date()),
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "universe": n,
        "counts": {k: int(counts.get(k, 0)) for k in ("BUY", "HOLD", "AVOID")} | {"NR": len(unrated)},
        "unratedReasons": {k: int(v) for k, v in reasons.items()},
        "liquidityCut": _f(_liq_cut(prepared, asof), 0) if prepared is not None else None,
        "regime": reg,
        "horizon": cfg.horizon,
        "roundTripCost": cfg.round_trip_cost,
        "buyTopPct": cfg.buy_top_pct_risk_off if reg["risk_off"] else cfg.buy_top_pct,
        "avoidBottomPct": cfg.avoid_bottom_pct,
        "model": model_info,
        "source": "Dhaka Stock Exchange end-of-day prices (history: StockNow adjusted export; updates: dsebd.org via bdshare)",
    })


ACTIVE_SESSIONS = 20


def _liq_cut(prepared: pd.DataFrame, asof) -> float | None:
    d = prepared[(prepared["Date"] == asof) & prepared["in_universe"]]
    return float(d["med_turnover_20"].min()) if len(d) else None


def _unrated_rows(prepared: pd.DataFrame, raw: pd.DataFrame, rated: set, asof, cfg: Config) -> list:
    """Company stocks traded in the last ACTIVE_SESSIONS sessions that get no Buy/Hold/Avoid call,
    each with the reason: too illiquid, too little history, or no trade on the latest session."""
    dates = np.sort(prepared["Date"].unique())
    since = dates[max(0, len(dates) - ACTIVE_SESSIONS)]
    eq = prepared[(prepared["kind"] == "equity") & (prepared["Date"] >= since) & ~prepared["Symbol"].isin(rated)]
    last = eq.sort_values("Date").groupby("Symbol").tail(1)
    prev = raw.sort_values("Date").groupby("Symbol")["Close"].apply(lambda c: c.iloc[-2] if len(c) > 1 else np.nan)
    out = []
    for r in last.sort_values("med_turnover_20", ascending=False).itertuples(index=False):
        if r.Date < asof:
            reason = "not_traded"
        elif r.age < cfg.warmup_days:
            reason = "new"
        elif not r.in_universe:
            reason = "illiquid"
        else:
            reason = "incomplete"
        pc = prev.get(r.Symbol, np.nan)
        out.append({"symbol": r.Symbol, "close": _f(r.Close, 2),
                    "chg1d": _f(r.Close / pc - 1, 5) if r.Date == asof and np.isfinite(pc) and pc else None,
                    "signal": "NR", "reason": reason, "lastTraded": str(pd.Timestamp(r.Date).date()),
                    "medTurnover": _f(r.med_turnover_20, 0), "score": None, "rank": None})
    return out
