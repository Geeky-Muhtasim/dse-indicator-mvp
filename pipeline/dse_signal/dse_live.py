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
            if not (np.isfinite(prev) and prev > 0 and np.isfinite(r.YCP) and r.YCP > 0):
                continue
            gap = abs(r.YCP - prev)
            if gap > ABS_TOL and gap / prev > REL_TOL:
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
