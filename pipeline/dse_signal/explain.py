"""SHAP attributions turned into grouped drivers and plain-language rationale."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .features import FAMILIES, FEATURES


def shap_values(model, X: pd.DataFrame) -> pd.DataFrame:
    """Per-row, per-feature contributions on the model's score scale.
    Row sum + base value = the model's score for that stock."""
    # LightGBM's pred_contrib is exact TreeSHAP; the last column is the expected value.
    contrib = model.model.predict(X[FEATURES], pred_contrib=True)
    out = pd.DataFrame(contrib[:, :-1], index=X.index, columns=FEATURES)
    out.attrs["base_value"] = float(contrib[0, -1]) if len(contrib) else 0.0
    return out


def family_importance(sv: pd.DataFrame) -> pd.Series:
    """Mean absolute contribution per feature family: what the model leans on overall."""
    return sv.abs().T.groupby(FAMILIES).sum().T.mean().sort_values(ascending=False)


def describe(feature: str, v: float) -> str:
    """Translate a raw feature value into a sentence fragment a trader would recognise."""
    if not np.isfinite(v):
        return feature
    pct = lambda x: f"{x:+.1%}"
    match feature:
        case "rs_rank_10" | "rs_rank_20":
            n = feature.split("_")[-1]
            return f"{n}-day return beats {v:.0%} of the market"
        case "ret_5" | "ret_10" | "ret_20":
            return f"{feature.split('_')[1]}-day return {pct(np.expm1(v))}"
        case "rsi_14":
            tag = " (overbought)" if v >= 70 else " (oversold)" if v <= 30 else ""
            return f"RSI {v:.0f}{tag}"
        case "macd_hist":
            return "MACD momentum turning up" if v > 0 else "MACD momentum turning down"
        case "ma_gap_10" | "ma_gap_20":
            n = feature.split("_")[-1]
            return f"price {abs(v):.1%} {'above' if v >= 0 else 'below'} its {n}-day average"
        case "ma_slope_10":
            return f"10-day average {'rising' if v >= 0 else 'falling'} {abs(v):.1%} over a week"
        case "range_pos_20":
            return f"price at {v:.0%} of its 20-day range"
        case "atr_pct_14":
            return f"average daily range {v:.1%} of price"
        case "bb_width_20":
            return f"Bollinger band width {v:.1%}"
        case "vol_ratio_5_20":
            return f"recent volatility {v:.1f}x its 20-day level"
        case "rel_volume":
            return f"volume {np.exp(v):.1f}x its 20-day median"
        case "obv_slope_10":
            return "on-balance volume accumulating" if v > 0 else "on-balance volume distributing"
        case "liquidity":
            return f"median turnover Tk {np.expm1(v) / 1e6:.1f} mn a day"
        case "breadth_20":
            return f"{v:.0%} of stocks above their 20-day average"
        case "mkt_ret_10":
            return f"market {pct(np.expm1(v))} over 10 days"
    return feature


def drivers(row_sv: pd.Series, row_x: pd.Series, k: int = 3) -> tuple[list[dict], list[dict]]:
    """Top supporting and opposing features for one stock."""
    s = row_sv.sort_values()
    to_dict = lambda f: {"feature": f, "family": FAMILIES[f], "shap": float(row_sv[f]),
                         "value": float(row_x[f]), "text": describe(f, float(row_x[f]))}
    pos = [to_dict(f) for f in s[s > 0].index[::-1][:k]]
    neg = [to_dict(f) for f in s[s < 0].index[:k]]
    return pos, neg


def rationale(signal: str, pos: list[dict], neg: list[dict]) -> str:
    """Template rationale built only from the SHAP drivers, so it cannot invent reasons."""
    lead = {"BUY": "Ranks near the top", "AVOID": "Ranks near the bottom", "HOLD": "Mid-pack"}[signal]
    if signal == "AVOID":
        main, against = neg, pos
    else:
        main, against = pos, neg
    s = lead
    if main:
        s += ": " + "; ".join(d["text"] for d in main[:2])
    if against:
        s += ". Against it: " + against[0]["text"]
    return s + "."
