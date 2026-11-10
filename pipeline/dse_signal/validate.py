"""Purged walk-forward validation, signal-quality metrics and a cost-aware backtest."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import Config
from .models import GBMRanker, scorecard_score


def walk_forward(panel: pd.DataFrame, cfg: Config) -> tuple[pd.DataFrame, list[dict]]:
    """Expanding-window walk-forward. A training row is kept only if its label window
    ends before the test block starts (purging), so no future return leaks into training.

    panel: universe rows with features; `target` is NaN where the label is unknown.
    Returns out-of-sample predictions for every universe row on the test dates."""
    labelled = panel[panel["target"].notna()]
    dates = np.sort(labelled["Date"].unique())
    min_train, block = cfg.min_train_dates, cfg.test_block_dates
    if len(dates) > cfg.long_history_dates:
        min_train = max(min_train, cfg.long_min_train_dates)
        block = max(block, int(np.ceil((len(dates) - min_train) / cfg.max_folds)))
    folds, preds = [], []
    k = min_train
    while k < len(dates):
        test_dates = dates[k:k + block]
        t0 = test_dates[0]
        train = labelled[(labelled["Date"] < t0) & (labelled["label_end_date"] < t0)]
        test = panel[panel["Date"].isin(test_dates)].copy()
        model = GBMRanker(cfg).fit(train)
        test["score_gbm"] = model.predict(test)
        test["fold"] = len(folds)
        preds.append(test)
        folds.append({
            "fold": len(folds),
            "train_start": str(pd.Timestamp(train["Date"].min()).date()),
            "train_end": str(pd.Timestamp(train["Date"].max()).date()),
            "test_start": str(pd.Timestamp(t0).date()),
            "test_end": str(pd.Timestamp(test_dates[-1]).date()),
            "train_rows": int(len(train)),
            "train_dates": int(train["Date"].nunique()),
        })
        k += block
    oos = pd.concat(preds)
    oos["score_card"] = scorecard_score(oos)
    return oos, folds


def daily_ic(oos: pd.DataFrame, col: str) -> pd.Series:
    m = oos["excess_ret"].notna()
    return (oos[m].groupby("Date")
            .apply(lambda d: d[col].corr(d["excess_ret"], method="spearman"), include_groups=False))


def quantile_returns(oos: pd.DataFrame, col: str, q: int = 5) -> pd.Series:
    m = oos["excess_ret"].notna()
    d = oos[m].copy()
    d["q"] = d.groupby("Date")[col].transform(lambda s: pd.qcut(s.rank(method="first"), q, labels=False) + 1)
    return d.groupby(["Date", "q"])["excess_ret"].mean().groupby("q").mean()


def decile_calibration(oos: pd.DataFrame, col: str) -> pd.DataFrame:
    """Empirical odds by score decile, out of sample. This is what a signal's confidence
    is read from: 'stocks in this decile beat the market X% of the time'."""
    m = oos["excess_ret"].notna()
    d = oos[m].copy()
    d["decile"] = d.groupby("Date")[col].transform(lambda s: pd.qcut(s.rank(method="first"), 10, labels=False) + 1)
    return d.groupby("decile").agg(
        hit_rate=("excess_ret", lambda x: float((x > 0).mean())),
        mean_excess=("excess_ret", "mean"),
        n=("excess_ret", "size"),
    )


def backtest(oos: pd.DataFrame, col: str, cfg: Config) -> pd.DataFrame:
    """Long-only top-bucket portfolio, rebalanced every `horizon` days so holding periods
    never overlap. Entry next open, exit close at t+h. Names that could not be filled
    (flat limit bar next day) earn zero. Costs charged on the share of names replaced."""
    dates = np.sort(oos.loc[oos["fwd_ret"].notna() | oos["excess_ret"].notna(), "Date"].unique())
    rebal = dates[::cfg.horizon]
    rows, prev = [], set()
    for t in rebal:
        d = oos[oos["Date"] == t]
        n = max(1, int(round(len(d) * cfg.buy_top_pct)))
        picks = d.nlargest(n, col)
        names = set(picks["Symbol"])
        turnover = 1.0 if not prev else len(names - prev) / len(names)
        gross = picks["fwd_ret"].fillna(0).mean()
        bench = d["fwd_ret"].mean()
        rows.append({"date": t, "n": n, "gross": gross, "turnover": turnover,
                     "cost": turnover * cfg.round_trip_cost, "bench": bench})
        prev = names
    bt = pd.DataFrame(rows).set_index("date")
    bt["net"] = bt["gross"] - bt["cost"]
    for c in ("gross", "net", "bench"):
        bt[f"cum_{c}"] = (1 + bt[c]).cumprod()
    return bt


def _max_dd(cum: pd.Series) -> float:
    return float((cum / cum.cummax() - 1).min())


def summarise(oos: pd.DataFrame, col: str, cfg: Config) -> dict:
    ic = daily_ic(oos, col)
    ic_nov = ic.iloc[::cfg.horizon]  # non-overlapping dates for an honest t-stat
    qr = quantile_returns(oos, col)
    bt = backtest(oos, col, cfg)
    return {
        "ic_mean": float(ic.mean()),
        "ic_std": float(ic.std()),
        "ic_positive_share": float((ic > 0).mean()),
        "ic_tstat_nonoverlap": float(ic_nov.mean() / (ic_nov.std() / np.sqrt(len(ic_nov)))) if len(ic_nov) > 2 else float("nan"),
        "n_ic_dates": int(len(ic)),
        "quintile_excess": {int(k): float(v) for k, v in qr.items()},
        "q5_minus_q1": float(qr.iloc[-1] - qr.iloc[0]),
        "bt_periods": int(len(bt)),
        "bt_gross_total": float(bt["cum_gross"].iloc[-1] - 1),
        "bt_net_total": float(bt["cum_net"].iloc[-1] - 1),
        "bt_bench_total": float(bt["cum_bench"].iloc[-1] - 1),
        "bt_net_hit_vs_bench": float((bt["net"] > bt["bench"]).mean()),
        "bt_avg_turnover": float(bt["turnover"].mean()),
        "bt_max_drawdown_net": _max_dd(bt["cum_net"]),
        "bt_max_drawdown_bench": _max_dd(bt["cum_bench"]),
        **_annualised(bt, cfg),
    }


def _annualised(bt: pd.DataFrame, cfg: Config) -> dict:
    """Annualised figures, assuming about 240 DSE sessions a year."""
    ppy = 240 / cfg.horizon
    n = len(bt)
    if n < 2:
        return {}
    ex = bt["net"] - bt["bench"]
    sd = ex.std()
    return {
        "bt_years": round(n / ppy, 2),
        "bt_ann_net": float(bt["cum_net"].iloc[-1] ** (ppy / n) - 1),
        "bt_ann_gross": float(bt["cum_gross"].iloc[-1] ** (ppy / n) - 1),
        "bt_ann_bench": float(bt["cum_bench"].iloc[-1] ** (ppy / n) - 1),
        "bt_info_ratio_net": float(ex.mean() / sd * np.sqrt(ppy)) if sd > 0 else float("nan"),
    }
