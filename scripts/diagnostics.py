"""Robustness diagnostics for the signal. Run: python scripts/diagnostics.py

1. Liquidity: is the rank IC still there among the most liquid stocks?
2. Turnover: holding periods of 5, 10 and 20 sessions, with and without a hold band
   (enter in the top 10%, keep until the stock leaves the top 30%).
3. Volatility tilt: excess return measured against stocks of similar volatility, and the
   portfolio's beta to the equal-weight market.
Writes data/model/diagnostics.json.
"""
import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))

from dse_signal import data, validate  # noqa: E402
from dse_signal.config import Config  # noqa: E402
from dse_signal.pipeline import HISTORY, build_panel  # noqa: E402


def ic_by(oos: pd.DataFrame, col: str, target: str, bucket: str, n: int = 3) -> dict:
    d = oos[oos[target].notna()].copy()
    d["b"] = d.groupby("Date")[bucket].transform(lambda s: pd.qcut(s.rank(method="first"), n, labels=False))
    out = {}
    for b, g in d.groupby("b"):
        ic = g.groupby("Date").apply(lambda x: x[col].corr(x[target], method="spearman"))
        nov = ic.dropna()
        out[int(b)] = {"ic": round(float(nov.mean()), 4), "positive": round(float((nov > 0).mean()), 3),
                       "t": round(float(nov.mean() / nov.std() * np.sqrt(len(nov) / 5)), 2)}
    return out


def band_backtest(oos: pd.DataFrame, col: str, cfg: Config, enter: float, exit_: float) -> pd.DataFrame:
    """Hold the top `enter` names; keep a holding while it stays in the top `exit_`.
    Rebalanced every `horizon` sessions so holding periods do not overlap."""
    dates = np.sort(oos.loc[oos["fwd_ret"].notna(), "Date"].unique())
    held, rows = [], []
    for t in dates[::cfg.horizon]:
        d = oos[oos["Date"] == t].copy()
        d["pct"] = d[col].rank(pct=True)
        n = max(1, int(round(len(d) * enter)))
        keep = [s for s in held if s in set(d.loc[d["pct"] > 1 - exit_, "Symbol"])]
        add = [s for s in d.sort_values(col, ascending=False)["Symbol"] if s not in keep][: max(0, n - len(keep))]
        new = keep + add
        turnover = 1.0 if not held else len(set(new) - set(held)) / len(new)
        r = d.set_index("Symbol")["fwd_ret"]
        rows.append({"date": t, "gross": float(r.reindex(new).fillna(0).mean()), "bench": float(r.mean()),
                     "turnover": turnover, "cost": turnover * cfg.round_trip_cost,
                     "vol_bench": float(d.set_index("Symbol").reindex(new)["vol_peer_ret"].mean())})
        held = new
    bt = pd.DataFrame(rows).set_index("date")
    bt["net"] = bt["gross"] - bt["cost"]
    return bt


def summarise_bt(bt: pd.DataFrame, cfg: Config) -> dict:
    ppy = 240 / cfg.horizon
    n = len(bt)
    ann = lambda r: float((1 + r).prod() ** (ppy / n) - 1)
    ex = bt["net"] - bt["bench"]
    exv = bt["net"] - bt["vol_bench"]
    beta = float(np.cov(bt["gross"], bt["bench"])[0, 1] / np.var(bt["bench"], ddof=1))
    alpha = float((bt["gross"] - beta * bt["bench"]).mean() * ppy)
    return {
        "periods": n, "years": round(n / ppy, 2), "turnover": round(float(bt["turnover"].mean()), 3),
        "ann_gross": round(ann(bt["gross"]), 4), "ann_net": round(ann(bt["net"]), 4),
        "ann_market": round(ann(bt["bench"]), 4), "ann_vol_peers": round(ann(bt["vol_bench"]), 4),
        "ir_vs_market": round(float(ex.mean() / ex.std() * np.sqrt(ppy)), 2),
        "ir_vs_vol_peers": round(float(exv.mean() / exv.std() * np.sqrt(ppy)), 2),
        "t_vs_market": round(float(ex.mean() / ex.std() * np.sqrt(n)), 2),
        "t_vs_vol_peers": round(float(exv.mean() / exv.std() * np.sqrt(n)), 2),
        "beta": round(beta, 2), "alpha_gross_ann": round(alpha, 4),
    }


def run(horizon: int, raw: pd.DataFrame) -> dict:
    cfg = Config()
    cfg.horizon = cfg.test_block_dates = horizon
    panel = build_panel(raw, cfg)
    oos, _ = validate.walk_forward(panel, cfg)
    # Volatility peers: mean forward return of stocks in the same ATR quintile that day.
    oos["vq"] = oos.groupby("Date")["atr_pct_14"].transform(lambda s: pd.qcut(s.rank(method="first"), 5, labels=False))
    oos["vol_peer_ret"] = oos.groupby(["Date", "vq"])["fwd_ret"].transform("mean")
    oos["vol_neutral_ex"] = oos["fwd_ret"] - oos["vol_peer_ret"]
    res = {"horizon": horizon,
           "ic": round(float(validate.daily_ic(oos, "score_gbm").mean()), 4),
           "ic_by_liquidity_tercile": ic_by(oos, "score_gbm", "excess_ret", "liquidity"),
           "ic_vol_neutral": round(float(oos[oos["vol_neutral_ex"].notna()].groupby("Date").apply(
               lambda x: x["score_gbm"].corr(x["vol_neutral_ex"], method="spearman")).mean()), 4)}
    res["top10"] = summarise_bt(band_backtest(oos, "score_gbm", cfg, 0.10, 0.10), cfg)
    res["band_10_30"] = summarise_bt(band_backtest(oos, "score_gbm", cfg, 0.10, 0.30), cfg)
    # Liquid-only portfolio: restrict to the most liquid third each day.
    liq = oos[oos.groupby("Date")["liquidity"].rank(pct=True) > 2 / 3]
    res["liquid_third_band"] = summarise_bt(band_backtest(liq, "score_gbm", cfg, 0.10, 0.30), cfg)
    return res


if __name__ == "__main__":
    raw = data.load_eod(HISTORY)
    out = [run(h, raw) for h in (5, 10, 20)]
    (ROOT / "data" / "model" / "diagnostics.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=1))
