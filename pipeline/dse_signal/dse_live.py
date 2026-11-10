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


def _is_event(prev, ycp) -> bool:
    if not (np.isfinite(prev) and prev > 0 and np.isfinite(ycp) and ycp > 0):
        return False
    gap = abs(ycp - prev)
    return gap > ABS_TOL and gap / prev > REL_TOL and FACTOR_MIN <= ycp / prev <= FACTOR_MAX


def fetch_dse(start: date, end: date) -> pd.DataFrame:
    """All instruments between two dates (inclusive) from dsebd.org, via bdshare."""
    from bdshare import get_hist_data  # imported here so scoring never needs network deps

    df = get_hist_data(start=start.isoformat(), end=end.isoformat())
    df = df.reset_index()
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
        for r in day.itertuples(index=False):
            prev = last.get(r.Symbol, np.nan)
            if _is_event(prev, r.YCP):
                factor = r.YCP / prev
                m = hist["Symbol"] == r.Symbol
                hist.loc[m, ["Open", "High", "Low", "Close"]] *= factor
                hist.loc[m, "Volume"] = (hist.loc[m, "Volume"] / factor).round()
                events.append({"symbol": r.Symbol, "date": str(pd.Timestamp(d).date()),
                               "stored_close": round(float(prev), 4), "dse_ycp": float(r.YCP),
                               "factor": round(float(factor), 6)})
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
def fetch_range(start: date, end: date, chunk_days: int = 31, pause: float = 1.5, log=print) -> pd.DataFrame:
    """Fetch a long range from DSE in month-sized chunks, retrying each chunk."""
    import time

    parts, cur = [], start
    while cur <= end:
        stop = min(end, cur + timedelta(days=chunk_days - 1))
        for attempt in range(4):
            try:
                df = fetch_dse(cur, stop)
                parts.append(df)
                log(f"  {cur} to {stop}: {df['Date'].nunique()} sessions, {len(df):,} rows")
                break
            except Exception as e:  # holidays-only chunks raise "no data"; network errors retry
                msg = str(e)
                if "No historical data" in msg or "No basic historical" in msg:
                    log(f"  {cur} to {stop}: no sessions")
                    break
                if attempt == 3:
                    raise RuntimeError(f"Chunk {cur} to {stop} failed after retries: {msg}") from e
                time.sleep(5 * (attempt + 1))
        time.sleep(pause)
        cur = stop + timedelta(days=1)
    out = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    return out.drop_duplicates(["Symbol", "Date"], keep="last").sort_values(["Symbol", "Date"]).reset_index(drop=True)


def adjust_history(raw: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Back-adjust a raw DSE panel in one pass.

    On each corporate-action day the factor is YCP / previous stored close. Every price before
    that day is multiplied by the product of all later factors, which is exactly what applying
    merge_adjusted day by day would do, but vectorized for years of data."""
    d = raw.sort_values(["Symbol", "Date"]).reset_index(drop=True).copy()
    prev = d.groupby("Symbol")["Close"].shift(1)
    ev = np.array([_is_event(p, y) for p, y in zip(prev.to_numpy(), d["YCP"].to_numpy())])
    f = np.where(ev, d["YCP"] / prev, 1.0)
    logf = pd.Series(np.log(f), index=d.index)
    # Sum of log-factors strictly after each row, within its symbol.
    after = logf.groupby(d["Symbol"]).transform("sum") - logf.groupby(d["Symbol"]).cumsum()
    adj = np.exp(after.to_numpy())
    for c in ("Open", "High", "Low", "Close"):
        d[c] = (d[c] * adj).round(4)
    d["Volume"] = (d["Volume"] / adj).round()
    # prev and YCP are raw (unadjusted) values, as DSE reported them that day.
    events = d.loc[ev, ["Symbol", "Date"]].assign(
        stored_close=prev[ev].to_numpy(), dse_ycp=d.loc[ev, "YCP"].to_numpy(), factor=f[ev]
    ).rename(columns={"Symbol": "symbol", "Date": "date"})
    return d[COLS], events


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
    log(f"Backfilling DSE day-end data {start} to {end}")
    raw = fetch_range(start, end, log=log)
    if raw.empty:
        raise RuntimeError("DSE returned no data for the backfill range")
    adj, events = adjust_history(raw)
    report = {"start": str(start), "end": str(adj["Date"].max().date()), "rows": int(len(adj)),
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
