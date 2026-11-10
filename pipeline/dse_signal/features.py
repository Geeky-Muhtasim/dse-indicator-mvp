"""Point-in-time features. Every value at date t uses only data up to and including t."""
from __future__ import annotations

import numpy as np
import pandas as pd

# Feature -> family. Families are what the explanations are grouped by.
FAMILIES = {
    "ret_5": "Momentum", "ret_10": "Momentum", "ret_20": "Momentum",
    "rsi_14": "Momentum", "macd_hist": "Momentum",
    "ma_gap_10": "Trend", "ma_gap_20": "Trend", "ma_slope_10": "Trend", "range_pos_20": "Trend",
    "atr_pct_14": "Volatility", "bb_width_20": "Volatility", "vol_ratio_5_20": "Volatility",
    "rel_volume": "Volume", "obv_slope_10": "Volume", "liquidity": "Volume",
    "rs_rank_10": "Relative strength", "rs_rank_20": "Relative strength",
    "breadth_20": "Market regime", "mkt_ret_10": "Market regime",
}
FEATURES = list(FAMILIES)


def _rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    rs = up / dn.replace(0, np.nan)
    out = 100 - 100 / (1 + rs)
    return out.where(dn > 0, 100.0).where(up.notna())


def _per_symbol(x: pd.DataFrame) -> pd.DataFrame:
    c, h, l, v = x["Close"], x["High"], x["Low"], x["Volume"]
    o = pd.DataFrame(index=x.index)
    for n in (5, 10, 20):
        o[f"ret_{n}"] = np.log(c / c.shift(n))
    o["rsi_14"] = _rsi(c)
    ema12, ema26 = c.ewm(span=12, adjust=False).mean(), c.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    o["macd_hist"] = (macd - macd.ewm(span=9, adjust=False).mean()) / c

    ma10, ma20 = c.rolling(10).mean(), c.rolling(20).mean()
    o["ma_gap_10"] = c / ma10 - 1
    o["ma_gap_20"] = c / ma20 - 1
    o["ma_slope_10"] = ma10 / ma10.shift(5) - 1
    hi20, lo20 = h.rolling(20).max(), l.rolling(20).min()
    o["range_pos_20"] = ((c - lo20) / (hi20 - lo20)).where(hi20 > lo20, 0.5)

    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    o["atr_pct_14"] = tr.rolling(14).mean() / c
    o["bb_width_20"] = 4 * c.rolling(20).std() / ma20
    r = np.log(c).diff()
    o["vol_ratio_5_20"] = r.rolling(5).std() / r.rolling(20).std()

    o["rel_volume"] = np.log1p(v) - np.log1p(v.rolling(20).median())
    obv = (np.sign(c.diff()).fillna(0) * v).cumsum()
    o["obv_slope_10"] = (obv - obv.shift(10)) / (10 * v.rolling(20).mean())
    o["liquidity"] = np.log1p((c * v).rolling(20).median())
    return o


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """df must come from data.prepare(). Returns df with feature columns added."""
    df = df.sort_values(["Symbol", "Date"]).copy()
    feats = df.groupby("Symbol", group_keys=False).apply(_per_symbol, include_groups=False)
    df = df.join(feats)

    uni = df["in_universe"]
    # Cross-sectional relative strength, ranked within the tradeable universe on each date.
    for n in (10, 20):
        df[f"rs_rank_{n}"] = df[uni].groupby("Date")[f"ret_{n}"].rank(pct=True)

    # Market regime: same value for every stock on a date.
    above = (df["ma_gap_20"] > 0).astype(float).where(df["ma_gap_20"].notna())
    breadth = above[uni].groupby(df.loc[uni, "Date"]).mean().rename("breadth_20")
    # Market return uses all equities so it is available from the first days of history.
    eq = df["kind"].eq("equity")
    mkt = df[eq].groupby("Date")["ret_1d"].mean().rename("mkt_ret_1d")
    mkt_ret_10 = np.log1p(mkt).rolling(10).sum().rename("mkt_ret_10")
    regime = pd.concat([breadth, mkt_ret_10], axis=1, sort=True)
    df = df.merge(regime, left_on="Date", right_index=True, how="left")
    return df
