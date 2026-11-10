"""Loading, validation, instrument classification and universe selection."""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

from .config import Config

REQUIRED = ["Symbol", "Date", "Open", "High", "Low", "Close", "Volume"]

# Closed-end funds and bonds trade on DSE alongside ordinary shares. They behave differently
# (NAV discounts, coupons), so they are kept out of the equity model.
_BOND = re.compile(r"(PBOND|BOND|SUKUK|\dPB)$")
_TBOND = re.compile(r"^(TB\d|BGTB|DBTB)")  # government treasury bonds listed on DSE
_FUND = re.compile(r"(MF|MF\d|MF\dS\d)$")
# Funds whose tickers do not follow the ...MF pattern. Extend this when new listings appear.
_FUND_EXPLICIT = {
    "ICB3RDNRB", "ICBAGRANI1", "ICBAMCL2ND", "ICBSONALI1", "PRIME1ICBA", "GRAMEENS2",
    "RELIANCE1", "SEMLFBSLGF", "SEMLIBBLSF", "VAMLRBBF", "FBFIF", "CAPITECGBF",
}


def classify_instrument(symbol: str) -> str:
    s = symbol.upper()
    if _BOND.search(s) or _TBOND.search(s):
        return "bond"
    if s in _FUND_EXPLICIT or _FUND.search(s):
        return "fund"
    return "equity"


def load_eod(path: str | Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    missing = set(REQUIRED) - set(df.columns)
    if missing:
        raise ValueError(f"CSV is missing columns: {sorted(missing)}")
    df = df[REQUIRED].copy()
    df["Date"] = pd.to_datetime(df["Date"])
    df = (df.drop_duplicates(["Symbol", "Date"], keep="last")
            .sort_values(["Symbol", "Date"]).reset_index(drop=True))
    for c in ["Open", "High", "Low", "Close"]:
        df[c] = df[c].astype(float)
    df["Volume"] = df["Volume"].astype(float)
    return df


def quality_report(df: pd.DataFrame, cfg: Config) -> dict:
    ret = df.groupby("Symbol")["Close"].pct_change()
    bad_ohlc = ((df.High < df[["Open", "Close"]].max(axis=1)) |
                (df.Low > df[["Open", "Close"]].min(axis=1)) | (df.Low <= 0))
    kinds = df.drop_duplicates("Symbol")["Symbol"].map(classify_instrument).value_counts()
    return {
        "rows": int(len(df)),
        "symbols": int(df.Symbol.nunique()),
        "trading_days": int(df.Date.nunique()),
        "start": str(df.Date.min().date()),
        "end": str(df.Date.max().date()),
        "instrument_mix": {k: int(v) for k, v in kinds.items()},
        "null_cells": int(df.isna().sum().sum()),
        "broken_candles": int(bad_ohlc.sum()),
        "zero_volume_rows": int((df.Volume == 0).sum()),
        "flat_bars": int((df.High == df.Low).sum()),
        "limit_like_moves": int((ret.abs() >= cfg.limit_move_threshold).sum()),
    }


def prepare(df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Add instrument type, trading flags and a point-in-time liquidity universe."""
    df = df.copy()
    df["kind"] = df["Symbol"].map(classify_instrument)
    g = df.groupby("Symbol", group_keys=False)
    df["ret_1d"] = g["Close"].pct_change()
    df["turnover"] = df["Close"] * df["Volume"]
    df["flat_bar"] = df["High"] == df["Low"]
    df["limit_move"] = df["ret_1d"].abs() >= cfg.limit_move_threshold
    df["age"] = g.cumcount()
    df["med_turnover_20"] = g["turnover"].transform(lambda s: s.rolling(20, min_periods=10).median())

    # Liquidity cut is computed per date across equities only, using information known at t.
    eq = df["kind"].eq("equity") & df["age"].ge(cfg.warmup_days)
    cut = (df[eq].groupby("Date")["med_turnover_20"]
             .quantile(cfg.liquidity_drop_quantile).rename("liq_cut"))
    df = df.merge(cut, left_on="Date", right_index=True, how="left")
    df["in_universe"] = eq & (df["med_turnover_20"] >= df["liq_cut"])
    return df.drop(columns="liq_cut")
