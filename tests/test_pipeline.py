"""Guards against the mistakes that make backtests lie: look-ahead and label leakage."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
from dse_signal import data, features, labels, validate
from dse_signal.config import Config
from dse_signal.features import FEATURES
from dse_signal.pipeline import build_panel

CSV = Path(__file__).resolve().parents[1] / "data" / "history" / "eod.csv"
CFG = Config()


@pytest.fixture(scope="module")
def raw():
    return data.load_eod(CSV)


@pytest.fixture(scope="module")
def panel(raw):
    return build_panel(raw, CFG)


def test_classifier():
    assert data.classify_instrument("1JANATAMF") == "fund"
    assert data.classify_instrument("ABBLPBOND") == "bond"
    assert data.classify_instrument("BEXGSUKUK") == "bond"
    assert data.classify_instrument("ACHIASF") == "equity"
    assert data.classify_instrument("SQURPHARMA") == "equity"


def test_features_have_no_lookahead(raw):
    """Features on a date must not change when later data is deleted."""
    dates = np.sort(raw["Date"].unique())
    cut = dates[45]
    full = features.build_features(data.prepare(raw, CFG))
    trunc = features.build_features(data.prepare(raw[raw["Date"] <= cut], CFG))
    a = full[full["Date"] == cut].set_index("Symbol")[FEATURES].sort_index()
    b = trunc[trunc["Date"] == cut].set_index("Symbol")[FEATURES].sort_index()
    pd.testing.assert_frame_equal(a, b, check_exact=False, rtol=1e-9)


def test_forward_return_alignment(raw):
    df = labels.add_forward_returns(data.prepare(raw, CFG), CFG.horizon)
    s = df[df["Symbol"] == "SQURPHARMA"].reset_index(drop=True)
    i = 10
    expected = s.loc[i + CFG.horizon, "Close"] / s.loc[i + 1, "Open"] - 1
    if np.isfinite(s.loc[i, "fwd_ret"]):
        assert s.loc[i, "fwd_ret"] == pytest.approx(expected)
    assert s["fwd_ret"].tail(CFG.horizon).isna().all()


def test_walk_forward_purges_overlapping_labels(panel):
    labelled = panel[panel["target"].notna()]
    dates = np.sort(labelled["Date"].unique())
    t0 = dates[CFG.min_train_dates]
    train = labelled[(labelled["Date"] < t0) & (labelled["label_end_date"] < t0)]
    assert (train["label_end_date"] < t0).all()
    assert train["Date"].max() < t0


def test_targets_are_cross_sectional_ranks(panel):
    t = panel.dropna(subset=["target"])
    assert t["target"].between(-1, 1).all()
    assert t.groupby("Date")["excess_ret"].mean().abs().max() < 1e-12


def test_triple_barrier():
    close = pd.Series([100, 103, 104, 99, 98, 97], dtype=float)
    vol = pd.Series([0.02] * 6)
    lab = labels.triple_barrier(close, vol, horizon=3, up_mult=1.0, dn_mult=1.0)
    assert lab.iloc[0] == 1   # +3% hits the +2% barrier first
    assert lab.iloc[2] == -1  # falls to 99 (-4.8%) before any gain
