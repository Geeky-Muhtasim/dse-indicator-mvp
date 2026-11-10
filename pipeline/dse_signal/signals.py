"""Turn scores into Buy / Hold / Avoid calls with a regime gate and empirical confidence."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import Config
from .explain import drivers, rationale


def regime(day: pd.DataFrame, cfg: Config) -> dict:
    breadth = float(day["breadth_20"].iloc[0])
    mkt10 = float(np.expm1(day["mkt_ret_10"].iloc[0]))
    risk_off = breadth < cfg.risk_off_breadth and mkt10 < 0
    return {"breadth_20": breadth, "mkt_ret_10": mkt10, "risk_off": risk_off}


def make_signals(day: pd.DataFrame, scores: np.ndarray, sv: pd.DataFrame,
                 calib: pd.DataFrame, cfg: Config) -> tuple[pd.DataFrame, dict]:
    """day: universe rows for one date. calib: out-of-sample decile table.
    No shorting on DSE for retail, so the calls are Buy / Hold / Avoid."""
    reg = regime(day, cfg)
    d = day.copy()
    d["score"] = scores
    d["pct"] = d["score"].rank(pct=True)
    d["decile"] = np.ceil(d["pct"] * 10).clip(1, 10).astype(int)
    buy_cut = 1 - (cfg.buy_top_pct_risk_off if reg["risk_off"] else cfg.buy_top_pct)
    d["signal"] = np.where(d["pct"] > buy_cut, "BUY",
                  np.where(d["pct"] <= cfg.avoid_bottom_pct, "AVOID", "HOLD"))
    d["hist_hit_rate"] = d["decile"].map(calib["hit_rate"])
    d["hist_mean_excess"] = d["decile"].map(calib["mean_excess"])
    d["fill_risk"] = d["flat_bar"] | d["limit_move"]

    pos_l, neg_l, why = [], [], []
    for idx, row in d.iterrows():
        pos, neg = drivers(sv.loc[idx], row)
        pos_l.append(pos)
        neg_l.append(neg)
        why.append(rationale(row["signal"], pos, neg))
    d["drivers_for"], d["drivers_against"], d["rationale"] = pos_l, neg_l, why
    return d.sort_values("score", ascending=False), reg
