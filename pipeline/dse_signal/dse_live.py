"""Fetch new end-of-day data from the Dhaka Stock Exchange and append it to the adjusted history.

Corporate actions: DSE reports each day's YCP (yesterday's closing price), which DSE itself
adjusts on the ex-date of a bonus or rights issue. If YCP differs from the close we stored for
the previous session, the ratio is the adjustment factor, and the whole stored history of that
stock is rescaled by it. That keeps the series continuous, the same way the StockNow export was.
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

COLS = ["Symbol", "Date", "Open", "High", "Low", "Close", "Volume"]
REL_TOL, ABS_TOL = 0.004, 0.05
# A genuine bonus or rights adjustment lowers the reference price. Factors outside this band
# are far more likely to be a data glitch (a zero or stale YCP) than a corporate action.
FACTOR_MIN, FACTOR_MAX = 0.1, 1.02


# DSE's archive does NOT adjust YCP for bonus issues (checked against the adjusted StockNow
# export), so equities also need a price-based rule. Circuit breakers stop a stock trading more
# than about 10% below its reference price, so a session whose HIGH is more than 11% below the
# previous close, with a real trading range, can only be an ex-date on an adjusted reference.
# Locked limit-down days (high == low) are genuine crashes and are left alone.
GAP_HIGH_MAX = 0.89
GAP_MIN_PRICE = 3.0
BONUS = np.array([0.05, 0.1, 0.12, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.5, 1.0])
SNAP = 1 / (1 + BONUS)


def gap_factor(prev, o, h, l) -> float:
    """Adjustment factor implied by an ex-date gap, or 1.0 if the session looks like trading."""
    if not (np.isfinite(prev) and prev >= GAP_MIN_PRICE and h > l and h / prev < GAP_HIGH_MAX):
        return 1.0
    r = o / prev
    k = int(np.argmin(np.abs(SNAP - r)))
    return float(SNAP[k]) if abs(SNAP[k] - r) / r < 0.03 else float(r)


def _is_event(prev, ycp) -> bool:
    if not (np.isfinite(prev) and prev > 0 and np.isfinite(ycp) and ycp > 0):
        return False
    gap = abs(ycp - prev)
    return gap > ABS_TOL and gap / prev > REL_TOL and FACTOR_MIN <= ycp / prev <= FACTOR_MAX


def fetch_legacy_archive(start: date, end: date, timeout: int = 120) -> pd.DataFrame:
    """DSE's day-end archive page (old.dsebd.org), all instruments, with a long timeout.

    The page is slow for wide date ranges but serves automated clients, unlike the newer
    JSON API, which answers 403 to cloud runners. bdshare's own parser reads the table."""
    from bdshare.stock import trading as T  # pinned version, see pipeline/requirements.txt
    from bdshare.util.helper import _fetch_table

    table = _fetch_table(
        T.vs.DSE_LEGACY_URL + T.vs.DSE_DEA_URL,
        params={"startDate": start.isoformat(), "endDate": end.isoformat(),
                "inst": "All Instrument", "archive": "data"},
        retries=2, pause=3.0, timeout=timeout, table_class=T._CLS_FIXED,
    )
    rows = T._parse_historical_rows(table)
    return _normalise(pd.DataFrame(rows)) if rows else pd.DataFrame(columns=COLS + ["YCP"])


def fetch_dse(start: date, end: date) -> pd.DataFrame:
    """All instruments between two dates (inclusive): the archive page first, then bdshare's
    own source selection as a fallback."""
    try:
        return fetch_legacy_archive(start, end)
    except Exception:
        from bdshare import get_hist_data  # imported here so scoring never needs network deps
        return _normalise(get_hist_data(start=start.isoformat(), end=end.isoformat()).reset_index())


def _normalise(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]
    need = {"date", "symbol", "open", "high", "low", "close", "volume", "ycp"}
    missing = need - set(df.columns)
    if missing:
        raise RuntimeError(f"DSE response is missing columns {sorted(missing)}; got {list(df.columns)}")
    out = pd.DataFrame({
        "Symbol": df["symbol"].astype(str).str.strip(),
        "Date": pd.to_datetime(df["date"]),
        "Open": pd.to_numeric(df["open"], errors="coerce"),
        "High": pd.to_numeric(df["high"], errors="coerce"),
        "Low": pd.to_numeric(df["low"], errors="coerce"),
        "Close": pd.to_numeric(df["close"], errors="coerce"),
        "Volume": pd.to_numeric(df["volume"], errors="coerce"),
        "YCP": pd.to_numeric(df["ycp"], errors="coerce"),
    })
    # Untraded instruments come back with zero volume; the history has none of those.
    out = out[(out["Volume"] > 0) & (out["Close"] > 0)]
    # Some feeds report 0 for open/high/low on thin days; fall back to the close.
    for c in ("Open", "High", "Low"):
        out[c] = out[c].where(out[c] > 0, out["Close"])
    out["High"] = out[["High", "Open", "Close"]].max(axis=1)
    out["Low"] = out[["Low", "Open", "Close"]].min(axis=1)
    return out.sort_values(["Date", "Symbol"]).reset_index(drop=True)


def merge_adjusted(hist: pd.DataFrame, new: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    """Append new raw rows to an adjusted history, back-adjusting on corporate actions."""
    hist = hist.copy()
    hist["Date"] = pd.to_datetime(hist["Date"])
    new = new[new["Date"] > hist["Date"].max()]
    events = []
    for d, day in new.groupby("Date", sort=True):
        last = hist.sort_values("Date").groupby("Symbol").tail(1).set_index("Symbol")["Close"]
        from .data import classify_instrument
        for r in day.itertuples(index=False):
            prev = last.get(r.Symbol, np.nan)
            factor, source = 1.0, None
            if classify_instrument(r.Symbol) == "equity":
                if _is_event(prev, r.YCP):
                    factor, source = r.YCP / prev, "ycp"
                elif (g := gap_factor(prev, r.Open, r.High, r.Low)) != 1.0:
                    factor, source = g, "gap"
            if source:
                m = hist["Symbol"] == r.Symbol
                hist.loc[m, ["Open", "High", "Low", "Close"]] *= factor
                hist.loc[m, "Volume"] = (hist.loc[m, "Volume"] / factor).round()
                events.append({"symbol": r.Symbol, "date": str(pd.Timestamp(d).date()),
                               "stored_close": round(float(prev), 4), "dse_ycp": float(r.YCP),
                               "factor": round(float(factor), 6), "source": source})
        hist = pd.concat([hist, day[COLS]], ignore_index=True)
    hist = hist.drop_duplicates(["Symbol", "Date"], keep="last").sort_values(["Symbol", "Date"])
    for c in ("Open", "High", "Low", "Close"):
        hist[c] = hist[c].round(4)
    return hist[COLS].reset_index(drop=True), events


def update_history(history_path: Path, today: date | None = None, log=print) -> int:
    """Fetch every session after the last stored date. Returns the number of new sessions."""
    hist = pd.read_csv(history_path, parse_dates=["Date"])
    last = hist["Date"].max().date()
    today = today or date.today()
    if last >= today:
        log(f"History already current at {last}")
        return 0
    log(f"Fetching DSE sessions {last + timedelta(days=1)} to {today}")
    new = fetch_dse(last + timedelta(days=1), today)
    if new.empty:
        log("DSE returned no new sessions (holiday or not yet published)")
        return 0
    merged, events = merge_adjusted(hist, new)
    sessions = int(new["Date"].nunique())
    merged.assign(Date=merged["Date"].dt.strftime("%Y-%m-%d")).to_csv(history_path, index=False)
    if events:
        ev_path = history_path.parent / "corporate_actions.csv"
        ev = pd.DataFrame(events)
        if ev_path.exists():
            ev = pd.concat([pd.read_csv(ev_path), ev], ignore_index=True)
        ev.to_csv(ev_path, index=False)
        log(f"Adjusted history for {len(events)} corporate action(s): "
            + ", ".join(f"{e['symbol']} x{e['factor']:.4f}" for e in events))
    log(f"Added {sessions} session(s), {len(new):,} rows; history now ends {merged['Date'].max().date()}")
    return sessions


# ---------------------------------------------------------------- multi-year backfill
def fetch_range(start: date, end: date, chunk_days: int = 31, pause: float = 3.0, log=print) -> pd.DataFrame:
    """Fetch a long range from the DSE archive. Each request covers up to a month; if it
    times out it is split in half, down to a single day. Days that still fail are skipped
    and reported rather than stopping the whole backfill."""
    import time

    parts, failed = [], []

    def grab(a: date, b: date) -> None:
        try:
            df = fetch_legacy_archive(a, b)
            parts.append(df)
            log(f"  {a} to {b}: {df['Date'].nunique() if len(df) else 0} sessions, {len(df):,} rows", flush=True)
        except Exception as e:
            days = (b - a).days + 1
            if days > 1:
                mid = a + timedelta(days=days // 2 - 1)
                log(f"  {a} to {b}: {type(e).__name__}, splitting", flush=True)
                time.sleep(pause)
                grab(a, mid)
                time.sleep(pause)
                grab(mid + timedelta(days=1), b)
            else:
                failed.append(str(a))
                log(f"  {a}: failed ({str(e)[:120]}), skipped", flush=True)
        time.sleep(pause)

    cur = start
    while cur <= end:
        stop = min(end, cur + timedelta(days=chunk_days - 1))
        grab(cur, stop)
        cur = stop + timedelta(days=1)
    out = pd.concat([p for p in parts if len(p)], ignore_index=True) if parts else pd.DataFrame(columns=COLS + ["YCP"])
    out.attrs["failed_days"] = failed
    return out.drop_duplicates(["Symbol", "Date"], keep="last").sort_values(["Symbol", "Date"]).reset_index(drop=True)


def reference_factors(raw: pd.DataFrame, ref: pd.DataFrame) -> pd.DataFrame:
    """Exact factors from an adjusted reference export: wherever the ratio reference/raw steps,
    the step is a corporate action on that date."""
    m = raw[["Symbol", "Date", "Close"]].merge(ref[["Symbol", "Date", "Close"]], on=["Symbol", "Date"],
                                                suffixes=("", "_ref")).sort_values(["Symbol", "Date"])
    m["ratio"] = m["Close_ref"] / m["Close"]
    prev = m.groupby("Symbol")["ratio"].shift(1)
    step = (prev / m["ratio"])
    hit = (step - 1).abs() > 0.01
    return m.loc[hit, ["Symbol", "Date"]].assign(factor=step[hit].to_numpy(), source="reference")


def detect_events(raw: pd.DataFrame, ref: pd.DataFrame | None = None) -> pd.DataFrame:
    """Corporate-action factors for every row that needs one. Priority: the reference export
    (exact) on its dates, then DSE's YCP, then the ex-date gap rule. Equities only."""
    from .data import classify_instrument

    d = raw.sort_values(["Symbol", "Date"]).reset_index(drop=True)
    eq = d["Symbol"].map(classify_instrument).eq("equity").to_numpy()
    prev = d.groupby("Symbol")["Close"].shift(1).to_numpy()
    ycp = d["YCP"].to_numpy() if "YCP" in d else np.full(len(d), np.nan)
    rows = []
    for i in np.flatnonzero(eq):
        if _is_event(prev[i], ycp[i]):
            rows.append((d.at[i, "Symbol"], d.at[i, "Date"], ycp[i] / prev[i], "ycp"))
        else:
            g = gap_factor(prev[i], d.at[i, "Open"], d.at[i, "High"], d.at[i, "Low"])
            if g != 1.0:
                rows.append((d.at[i, "Symbol"], d.at[i, "Date"], g, "gap"))
    ev = pd.DataFrame(rows, columns=["Symbol", "Date", "factor", "source"])
    if ref is not None and len(ref):
        rf = reference_factors(d, ref)
        rf = rf[rf["Symbol"].map(classify_instrument).eq("equity")]
        lo, hi = ref["Date"].min(), ref["Date"].max()
        # inside the reference window the reference is the truth, so drop rule-based guesses there
        ev = ev[~(ev["Symbol"].isin(ref["Symbol"].unique()) & ev["Date"].between(lo, hi))]
        ev = pd.concat([ev, rf], ignore_index=True)
    return ev.sort_values(["Symbol", "Date"]).reset_index(drop=True)


def apply_events(df: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    """Rescale every price before each event by its factor (volumes inversely)."""
    d = df.sort_values(["Symbol", "Date"]).reset_index(drop=True).copy()
    f = d[["Symbol", "Date"]].merge(events[["Symbol", "Date", "factor"]], on=["Symbol", "Date"], how="left")["factor"].astype(float).fillna(1.0)
    logf = pd.Series(np.log(f.to_numpy()), index=d.index)
    after = logf.groupby(d["Symbol"]).transform("sum") - logf.groupby(d["Symbol"]).cumsum()
    adj = np.exp(after.to_numpy())
    for c in ("Open", "High", "Low", "Close"):
        d[c] = (d[c] * adj).round(4)
    d["Volume"] = (d["Volume"] / adj).round()
    return d


def adjust_history(raw: pd.DataFrame, ref: pd.DataFrame | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Back-adjust a raw DSE panel in one pass (equivalent to merge_adjusted day by day)."""
    ev = detect_events(raw, ref)
    adj = apply_events(raw, ev)
    d = raw.sort_values(["Symbol", "Date"]).reset_index(drop=True)
    prev = d.groupby("Symbol")["Close"].shift(1)
    info = d[["Symbol", "Date"]].assign(stored_close=prev, dse_ycp=d.get("YCP"))
    events = ev.merge(info, on=["Symbol", "Date"], how="left").rename(columns={"Symbol": "symbol", "Date": "date"})
    return adj[COLS], events[["symbol", "date", "stored_close", "dse_ycp", "factor", "source"]]


def compare_with_reference(adj: pd.DataFrame, ref: pd.DataFrame) -> dict:
    """Check the DSE-built series against the StockNow adjusted export on their overlap.
    For each symbol the ratio of closes should be flat (any constant offset is a later
    corporate action that only one of the two series has applied)."""
    m = adj.merge(ref[["Symbol", "Date", "Close"]], on=["Symbol", "Date"], suffixes=("", "_ref"))
    m = m[(m["Close"] > 0) & (m["Close_ref"] > 0)]
    m["ratio"] = m["Close_ref"] / m["Close"]
    g = m.groupby("Symbol")["ratio"]
    disp = (g.max() / g.min() - 1)
    ok = disp < 0.01
    return {"overlap_rows": int(len(m)), "symbols": int(len(disp)),
            "consistent_share": round(float(ok.mean()), 4) if len(ok) else 0.0,
            "inconsistent": sorted(disp[~ok].round(4).to_dict().items(), key=lambda kv: -kv[1])[:25]}


def backfill(history_path: Path, start: date, end: date | None = None, min_consistency: float = 0.9,
             log=print) -> dict:
    """Rebuild the history from DSE itself from `start` to `end`, validated against the
    existing (StockNow) history on the dates they share. Writes nothing if validation fails."""
    import json

    end = end or date.today()
    log(f"Backfilling DSE day-end data {start} to {end}", flush=True)
    raw = fetch_range(start, end, log=log)
    if raw.empty:
        raise RuntimeError("DSE returned no data for the backfill range")
    ref = pd.read_csv(history_path, parse_dates=["Date"]) if history_path.exists() else None
    if ref is not None and history_path.name.startswith("eod.csv.gz"):
        ref_copy = history_path.parent / "stocknow_reference.csv.gz"
        ref = pd.read_csv(ref_copy, parse_dates=["Date"]) if ref_copy.exists() else None
    adj, events = adjust_history(raw, ref)
    report = {"start": str(start), "end": str(adj["Date"].max().date()), "rows": int(len(adj)),
              "failed_days": raw.attrs.get("failed_days", []),
              "symbols": int(adj["Symbol"].nunique()), "sessions": int(adj["Date"].nunique()),
              "corporate_actions": int(len(events))}
    if history_path.exists():
        ref = pd.read_csv(history_path, parse_dates=["Date"])
        report["validation"] = compare_with_reference(adj, ref)
        log(f"Validation vs existing history: {report['validation']['consistent_share']:.1%} of "
            f"{report['validation']['symbols']} symbols consistent")
        if report["validation"]["consistent_share"] < min_consistency:
            raise RuntimeError(f"Backfill failed validation, nothing written: {json.dumps(report['validation'])[:800]}")
        ref_copy = history_path.parent / "stocknow_reference.csv.gz"
        if not ref_copy.exists():
            ref.assign(Date=ref["Date"].dt.strftime("%Y-%m-%d")).to_csv(ref_copy, index=False)
    out = history_path if str(history_path).endswith(".gz") else history_path.with_suffix(".csv.gz")
    adj.assign(Date=adj["Date"].dt.strftime("%Y-%m-%d")).to_csv(out, index=False)
    if out != history_path and history_path.exists():
        history_path.unlink()
    events.assign(date=events["date"].dt.strftime("%Y-%m-%d")).round(6).to_csv(
        out.parent / "corporate_actions.csv", index=False)
    (out.parent / "backfill_report.json").write_text(json.dumps(report, indent=2))
    log(f"Wrote {out.name}: {report['rows']:,} rows, {report['symbols']} symbols, "
        f"{report['sessions']} sessions, {report['corporate_actions']} corporate actions")
    return report


def readjust(history_path: Path, log=print) -> pd.DataFrame:
    """Find and apply corporate actions missing from the stored history. Safe to rerun: once a
    gap is adjusted it no longer looks like a gap, and reference ratios become flat."""
    import json

    hist = pd.read_csv(history_path, parse_dates=["Date"])
    ref_path = history_path.parent / "stocknow_reference.csv.gz"
    ref = pd.read_csv(ref_path, parse_dates=["Date"]) if ref_path.exists() else None
    ev = detect_events(hist, ref)
    if ev.empty:
        log("No missing adjustments found")
        return ev
    adj = apply_events(hist, ev)
    adj.assign(Date=adj["Date"].dt.strftime("%Y-%m-%d"))[COLS].to_csv(history_path, index=False)
    out = ev.rename(columns={"Symbol": "symbol", "Date": "date"}).assign(date=lambda x: x["date"].dt.strftime("%Y-%m-%d"))
    log_path = history_path.parent / "corporate_actions.csv"
    old = pd.read_csv(log_path) if log_path.exists() else pd.DataFrame()
    if "source" not in old:  # earlier logs held only bond YCP noise from before equities were handled
        old = pd.DataFrame()
    pd.concat([old, out], ignore_index=True).round(6).to_csv(log_path, index=False)
    if ref is not None:
        rep_path = history_path.parent / "backfill_report.json"
        rep = json.loads(rep_path.read_text()) if rep_path.exists() else {}
        rep["validation_after_readjust"] = compare_with_reference(adj, ref)
        rep["equity_corporate_actions"] = int(len(ev))
        rep_path.write_text(json.dumps(rep, indent=2))
        log(f"Validation vs StockNow after readjust: {rep['validation_after_readjust']['consistent_share']:.1%}")
    log(f"Applied {len(ev)} equity adjustments: " + ", ".join(f"{r.Symbol} {pd.Timestamp(r.Date).date()} x{r.factor:.3f} ({r.source})" for r in ev.itertuples()))
    return ev
