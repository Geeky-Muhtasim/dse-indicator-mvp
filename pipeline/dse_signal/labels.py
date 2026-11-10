"""Forward-looking targets. These are the ONLY columns allowed to look into the future."""
from __future__ import annotations

import numpy as np
import pandas as pd


def add_forward_returns(df: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """Signal is known after the close on day t.
    Entry: open of t+1. Exit: close of t+h. A realistic EOD fill."""
    df = df.sort_values(["Symbol", "Date"]).copy()
    g = df.groupby("Symbol")
    entry = g["Open"].shift(-1)
    exit_ = g["Close"].shift(-horizon)
    df["fwd_ret"] = exit_ / entry - 1
    # Untradeable entries: the next day opens at a limit with no range, so a fill is doubtful.
    next_flat = g["flat_bar"].shift(-1).astype("boolean").fillna(True).astype(bool)
    df.loc[next_flat, "fwd_ret"] = np.nan
    df["label_end_date"] = g["Date"].shift(-horizon)
    return df


def add_excess_targets(df: pd.DataFrame) -> pd.DataFrame:
    """Excess return over the equal-weight universe, and its cross-sectional rank in [-1, 1].
    The rank target strips out the market's direction so the model learns stock selection."""
    df = df.copy()
    m = df["in_universe"] & df["fwd_ret"].notna()
    mean = df[m].groupby("Date")["fwd_ret"].transform("mean")
    df.loc[m, "excess_ret"] = df.loc[m, "fwd_ret"] - mean
    rank = df[m].groupby("Date")["excess_ret"].rank(pct=True)
    df.loc[m, "target"] = 2 * rank - 1
    return df


def triple_barrier(close: pd.Series, vol: pd.Series, horizon: int,
                   up_mult: float = 1.5, dn_mult: float = 1.0) -> pd.Series:
    """Lopez de Prado triple-barrier label for one symbol.
    +1 if the profit barrier is hit first, -1 if the stop is hit first, 0 if time runs out.
    Barriers scale with each day's volatility estimate (e.g. ATR %)."""
    c = close.to_numpy()
    s = vol.to_numpy()
    out = np.full(len(c), np.nan)
    for i in range(len(c) - horizon):
        if not np.isfinite(s[i]):
            continue
        path = c[i + 1:i + 1 + horizon] / c[i] - 1
        up = np.where(path >= up_mult * s[i])[0]
        dn = np.where(path <= -dn_mult * s[i])[0]
        first_up = up[0] if len(up) else horizon
        first_dn = dn[0] if len(dn) else horizon
        out[i] = 1 if first_up < first_dn else (-1 if first_dn < first_up else 0)
    return pd.Series(out, index=close.index)
